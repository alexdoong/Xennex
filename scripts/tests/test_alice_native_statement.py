"""Literal reported meaning, correction lineage and single-owner language."""
import copy
import subprocess
import sys
import unittest
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import test_alice_native_query as native_tests
import test_alice_word_grounding as fixtures
from test_alice_concept_teaching import FakeLanguage
from scripts.alice_memory.conceptual_mind import restore
from scripts.alice_memory.native_statement_language import NativeStatementLanguage, parts, validate_plan
from scripts.alice_memory.persistent_runtime import configure_language

INITIAL = 'No momento 0, associe "autor" a "pai".'
CORRECTION = 'Corrija o momento 0: "autor" passa a ser "mae"; substitua [0].'


class StatementProtocolContracts(unittest.TestCase):
    def test_parser_receives_only_message_and_all_fields_are_literal(self):
        fake = FakeLanguage(parts(CORRECTION))
        plan = asdict(NativeStatementLanguage(fake).parse(CORRECTION))
        self.assertEqual(fake.request['messages'][1]['content'], CORRECTION)
        self.assertEqual(plan['corrects'], [0])
        for key, bad in (('subject', 'invented'), ('relation', 'outro'), ('moment', 1), ('corrects', [1]), ('message_sha256', '0' * 64)):
            with self.assertRaises(ValueError):
                validate_plan({**plan, key: bad}, CORRECTION, 'fixture')

    def test_negation_unclear_correction_and_non_declaration_never_teach(self):
        for text in ('Não associe no momento 0 "autor" a "pai".', 'Talvez associe no momento 0 "autor" a "pai".',
                     'Corrija o momento 0 "autor" para "mae".', 'No momento 0, associe "autor" a "pai"; [0].',
                     'Quem é "autor" do momento 0?', 'Associe momento 0 "autor" a "mae" e momento 1 também.'):
            self.assertTrue(NativeStatementLanguage(FakeLanguage(parts(text))).parse(text).uncertain)

    def test_protocol_does_not_load_neural_mind(self):
        child = subprocess.run([sys.executable, '-c', "import sys; import scripts.alice_memory.native_statement_language; assert 'torch' not in sys.modules"], cwd=ROOT, text=True, capture_output=True, timeout=20)
        self.assertEqual(child.returncode, 0, child.stderr)


class StatementLifecycleContracts(unittest.TestCase):
    setUp = native_tests.NativeLifecycleContracts.setUp
    configure = native_tests.NativeLifecycleContracts.configure
    factory = native_tests.NativeLifecycleContracts.factory
    until = native_tests.NativeLifecycleContracts.until
    core = native_tests.NativeLifecycleContracts.core
    frame = native_tests.NativeLifecycleContracts.frame

    @classmethod
    def setUpClass(cls):
        fixtures.WrittenGroundingTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        fixtures.WrittenGroundingTests.tearDownClass()

    def teach(self, core, text):
        number = core.submit_native_statement(text)
        self.until(core, lambda: core.native_statements.jobs[number]['status'] in core.native_statements.terminal)
        result = core.take_native_statement(number)
        self.assertEqual(result['status'], 'completed', result)
        return result

    def test_portuguese_father_mother_changes_current_but_keeps_initial_and_senses(self):
        core = self.core()
        observations = core.native.observations
        moments = len(core.native.moments.traces)
        first = self.teach(core, INITIAL)
        self.assertEqual(first['learning']['version'], 0)
        second = self.teach(core, CORRECTION)
        self.assertEqual(second['learning']['corrected'], [0])
        self.assertEqual(core.native.interpret(0, 'autor')['subject'], 'mae')
        self.assertEqual(core.native.interpret(0, 'autor', 'initial')['subject'], 'pai')
        self.assertEqual(core.native.observations, observations)
        self.assertEqual(len(core.native.moments.traces), moments)
        self.assertTrue(all(worker.process.poll() is not None for worker in self.workers))

    def test_unsupported_invented_or_stale_correction_does_not_update_weights(self):
        core = self.core()
        self.teach(core, INITIAL)
        self.configure('invent_claim')
        number = core.submit_native_statement(CORRECTION)
        self.until(core, lambda: core.native_statements.jobs[number]['status'] in core.native_statements.terminal)
        self.assertEqual(core.take_native_statement(number)['status'], 'failed')
        self.assertEqual(core.native.interpret(0, 'autor')['subject'], 'pai')
        self.configure()
        self.teach(core, CORRECTION)
        number = core.submit_native_statement(CORRECTION)
        self.until(core, lambda: core.native_statements.jobs[number]['status'] in core.native_statements.terminal)
        self.assertEqual(core.take_native_statement(number)['status'], 'failed')
        self.assertEqual(len(core.native.interpretations.records), 2)
        with self.assertRaises(ValueError):
            core.submit_native_statement(INITIAL, origin='self')

    def test_pending_parser_and_completed_record_survive_restart_without_relearning(self):
        core = self.core()
        number = core.submit_native_statement(INITIAL)
        core.tick(.05)
        payload = core.snapshot()
        self.assertEqual(payload['native_statements']['jobs'][0]['status'], 'waiting')
        core.close()
        resumed = restore(payload, self.folder / 'resume', self.factory)
        self.addCleanup(resumed.close)
        self.until(resumed, lambda: resumed.native_statements.jobs[number]['status'] == 'completed')
        snapshot = resumed.snapshot()
        resumed.close()
        fresh = restore(snapshot, self.folder / 'fresh', lambda op: (_ for _ in ()).throw(AssertionError('No model')))
        self.addCleanup(fresh.close)
        self.assertEqual(fresh.take_native_statement(number)['status'], 'completed')
        self.assertEqual(len(fresh.native.interpretations.records), 1)
        self.assertEqual(fresh.native.interpret(0, 'autor')['subject'], 'pai')
        corrupted = copy.deepcopy(snapshot)
        corrupted['native_statements']['jobs'][0]['learning']['version'] = 10
        with self.assertRaises(ValueError):
            restore(corrupted, self.folder / 'invalid', self.factory)

    def test_queue_budget_deferral_and_model_change_guard_keep_statement_source(self):
        core = self.core()
        self.configure('deferred')
        ids = [core.submit_native_statement(INITIAL) for _ in range(4)]
        with self.assertRaises(ValueError):
            core.submit_native_statement(INITIAL)
        self.until(core, lambda: core.native_statements.jobs[ids[0]]['deferrals'] > 0)
        with self.assertRaises(ValueError):
            configure_language(core, model='other')
        self.assertFalse(core.native.interpretations.records)
        for number in ids:
            core.native_statements.cancel(number)
        self.assertTrue(all(worker.process.poll() is not None for worker in self.workers))


if __name__ == '__main__':
    unittest.main()
