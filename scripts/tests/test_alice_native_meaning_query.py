"""Reported interpretation questions use learned cues and preserve revisions."""
import copy
import subprocess
import sys
import unittest
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import test_alice_native_statement as statements
from test_alice_concept_teaching import FakeLanguage
from scripts.alice_memory.conceptual_mind import restore, save
from scripts.alice_memory.native_meaning_language import NativeMeaningLanguage, parts, phrases, validate_expression, validate_plan, validate_evidence
from scripts.alice_memory.native_meaning_query import resolve
from scripts.alice_memory.persistent_runtime import configure_language, run

QUESTION = 'Qual é a informação atual de "maruvi" sobre "autor", pela imagem?'


class MeaningProtocolContracts(unittest.TestCase):
    def test_parser_receives_only_question_and_checks_literal_view_relation_and_cue(self):
        fake = FakeLanguage(parts(QUESTION))
        plan = asdict(NativeMeaningLanguage(fake).parse(QUESTION))
        self.assertEqual(fake.request['messages'][1]['content'], QUESTION)
        for key, wrong in (('relation', 'invented'), ('name', 'outro'), ('view', 'initial'), ('modalities', ['audio'])):
            with self.assertRaises(ValueError):
                validate_plan({**plan, key: wrong}, QUESTION, 'fixture')
        self.assertEqual(parts(QUESTION.replace('atual', 'primeira'))['view'], 'initial')
        self.assertEqual(parts(QUESTION.replace('atual', 'o que mudou'))['view'], 'comparison')
        self.assertTrue(parts('Explique o que é aprender.')['uncertain'])

    def test_protocol_is_independent_of_torch_and_neural_memory(self):
        child = subprocess.run([sys.executable, '-c', "import sys; import scripts.alice_memory.native_meaning_language; assert 'torch' not in sys.modules"], cwd=ROOT, capture_output=True, text=True, timeout=20)
        self.assertEqual(child.returncode, 0, child.stderr)


class MeaningLifecycleContracts(unittest.TestCase):
    setUp = statements.StatementLifecycleContracts.setUp
    configure = statements.StatementLifecycleContracts.configure
    factory = statements.StatementLifecycleContracts.factory
    until = statements.StatementLifecycleContracts.until
    core = statements.StatementLifecycleContracts.core
    frame = statements.StatementLifecycleContracts.frame
    teach = statements.StatementLifecycleContracts.teach
    setUpClass = classmethod(statements.StatementLifecycleContracts.setUpClass.__func__)
    tearDownClass = classmethod(statements.StatementLifecycleContracts.tearDownClass.__func__)

    def answer(self, core, question=QUESTION):
        number = core.submit_native_meaning_question(question)
        self.until(core, lambda: core.native_meaning_queries.jobs[number]['status'] in core.native_meaning_queries.terminal)
        reply = core.take_native_meaning_answer(number)
        self.assertEqual(reply['status'], 'completed', reply)
        return reply

    def test_initial_current_and_comparison_keep_reports_separate_from_perception(self):
        core = self.core()
        self.teach(core, statements.INITIAL)
        self.teach(core, statements.CORRECTION)
        observed = core.native.observations
        current = self.answer(core)
        initial = self.answer(core, QUESTION.replace('atual', 'primeira'))
        compare = self.answer(core, QUESTION.replace('atual', 'o que mudou'))
        self.assertEqual(current['evidence']['reports']['current']['subject'], 'mae')
        self.assertEqual(initial['evidence']['reports']['initial']['subject'], 'pai')
        self.assertIn('"pai"', compare['proposal']['text'])
        self.assertIn('"mae"', compare['proposal']['text'])
        self.assertIn('relatos recebidos', compare['proposal']['text'])
        self.assertFalse(current['evidence']['reports']['current']['directly_observed'])
        self.assertEqual(core.native.observations, observed)
        self.assertEqual(len(core.native.moments.traces), 1)
        self.assertEqual(len(core.native.interpretations.records), 2)

    def test_relation_presence_cannot_choose_between_matching_moments(self):
        core = self.core()
        at = core.native.moments.traces[0]['acquired_at']
        self.teach(core, statements.INITIAL)
        self.frame(core)
        reply = self.answer(core)
        self.assertEqual(reply['evidence']['sensory']['reason'], 'ambiguous_moments')
        self.assertEqual(reply['evidence']['reports'], {})
        timed = QUESTION[:-1] + f' em [{at-.01:.6f}; {at+.01:.6f}]?'
        self.assertEqual(self.answer(core, timed)['evidence']['reports']['current']['subject'], 'pai')

    def test_correction_during_expression_and_after_completion_invalidates_delivery(self):
        core = self.core()
        self.teach(core, statements.INITIAL)
        number = core.submit_native_meaning_question(QUESTION)
        self.until(core, lambda: core.native_meaning_queries.jobs[number]['status'] == 'expressing')
        from scripts.alice_memory.native_interpretation import NativeStatement
        core.teach_native_interpretation(NativeStatement(0, 'autor', 'mae', 'a' * 64, 1, core.clock, 'person', (0,)))
        self.until(core, lambda: core.native_meaning_queries.jobs[number]['status'] == 'completed')
        job = core.native_meaning_queries.jobs[number]
        self.assertGreater(job['revisions'], 0)
        self.assertEqual(job['evidence']['reports']['current']['subject'], 'mae')
        core.native.interpretations.bank.weights.zero_()
        self.assertIsNone(core.take_native_meaning_answer(number))
        self.until(core, lambda: core.native_meaning_queries.jobs[number]['status'] == 'completed')
        reply = core.take_native_meaning_answer(number)
        self.assertFalse(reply['evidence']['reports']['current']['supported'])

    def test_fabricated_observation_and_malformed_source_provenance_are_rejected(self):
        core = self.core()
        self.teach(core, statements.INITIAL)
        plan = asdict(NativeMeaningLanguage(FakeLanguage(parts(QUESTION))).parse(QUESTION))
        evidence = resolve(core.native, plan, QUESTION, reactivate=False)
        expression = asdict(NativeMeaningLanguage(FakeLanguage({'text': phrases(evidence)[0]})).express(evidence))
        with self.assertRaises(ValueError):
            validate_expression({**expression, 'text': 'Eu vi seu pai cozinhar.'}, evidence, 'fixture')
        damaged = copy.deepcopy(evidence)
        damaged['reports']['current']['sources'][0]['id'] = False
        with self.assertRaises(ValueError):
            validate_evidence(damaged)
        damaged = copy.deepcopy(evidence)
        damaged['reports']['current']['directly_observed'] = True
        with self.assertRaises(ValueError):
            validate_evidence(damaged)

    def test_pending_and_completed_queries_restore_with_same_native_owner(self):
        core = self.core()
        self.teach(core, statements.INITIAL)
        number = core.submit_native_meaning_question(QUESTION)
        with self.assertRaises(ValueError):
            configure_language(core, model='other')
        snapshot = core.snapshot()
        core.close()
        resumed = restore(snapshot, self.folder / 'resume', self.factory)
        self.addCleanup(resumed.close)
        self.assertIs(resumed.native_meaning_queries.native, resumed.native)
        self.until(resumed, lambda: resumed.native_meaning_queries.jobs[number]['status'] == 'completed')
        saved = resumed.snapshot()
        resumed.close()
        fresh = restore(saved, self.folder / 'fresh', lambda op: (_ for _ in ()).throw(AssertionError('No model')))
        self.addCleanup(fresh.close)
        self.assertEqual(fresh.take_native_meaning_answer(number)['status'], 'completed')
        damaged = copy.deepcopy(saved)
        damaged['native_meaning_queries']['jobs'][0]['evidence']['reports']['current']['subject'] = 'invented'
        with self.assertRaises(ValueError):
            restore(damaged, self.folder / 'invalid', self.factory)

    def test_finite_runtime_exposes_meaning_jobs_and_migrates_previous_checkpoint(self):
        core = self.core()
        self.teach(core, statements.INITIAL)
        older = core.snapshot()
        older.pop('native_namings')
        older.pop('interactions')
        older['format'] = 49
        older.pop('native_feedbacks')
        older.pop('native_meaning_queries')
        migrated = restore(older, self.folder / 'old', self.factory)
        self.addCleanup(migrated.close)
        self.assertFalse(migrated.native_meaning_queries.jobs)
        checkpoint = self.folder / 'start.pt'
        save(checkpoint, core)
        report = run(self.folder / 'runtime', checkpoint, seconds=2., question=QUESTION, question_mode='meaning', language_backend='fixture')
        self.assertEqual(report['phase'], 'stopped')
        self.assertTrue(report['workers_terminal'])
        self.assertTrue(report['native_meaning_query_jobs'])
        self.assertEqual(report['native_state']['observations'], 2)

    def test_checkpoint_with_answer_older_than_a_correction_requeries_after_restart(self):
        core = self.core()
        self.teach(core, statements.INITIAL)
        number = core.submit_native_meaning_question(QUESTION)
        self.until(core, lambda: core.native_meaning_queries.jobs[number]['status'] == 'completed')
        self.teach(core, statements.CORRECTION)
        snapshot = core.snapshot()
        core.close()
        resumed = restore(snapshot, self.folder / 'stale', self.factory)
        self.addCleanup(resumed.close)
        self.assertIsNone(resumed.take_native_meaning_answer(number))
        self.until(resumed, lambda: resumed.native_meaning_queries.jobs[number]['status'] == 'completed')
        self.assertEqual(resumed.take_native_meaning_answer(number)['evidence']['reports']['current']['subject'], 'mae')


if __name__ == '__main__':
    unittest.main()
