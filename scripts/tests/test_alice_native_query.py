"""Portuguese memory query, learned cue, actual factual text and restart."""
import copy
import json
import subprocess
import sys
import time
import unittest
from dataclasses import asdict
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import test_alice_concept_query as query_tests
import test_alice_word_grounding as fixtures
from test_alice_concept_teaching import FakeLanguage
from scripts.alice_memory.conceptual_mind import save, restore
from scripts.alice_memory.continuous_experiment import load_scheduler
from scripts.alice_memory.grounded_mind import WrittenName
from scripts.alice_memory.native_query import resolve
from scripts.alice_memory.native_query_language import NativeQueryLanguage, validate_plan, validate_expression, phrases
from scripts.alice_memory.native_sensor import NativeObservation
from scripts.alice_memory.persistent_runtime import close_agent, run

QUESTION = 'Alice, você lembra de "maruvi" pela imagem?'


def draft(question=QUESTION):
    from scripts.alice_memory.native_query_language import literal_parts
    names, modalities, windows, unclear = literal_parts(question)
    return {'name': None if unclear else names[0], 'modalities': [] if unclear else modalities,
            'window_fragment': None if unclear or not windows else windows[0],
            'basis': 'utc' if 'UTC' in question and not unclear else 'relative', 'uncertain': unclear}


class NativeProtocolContracts(unittest.TestCase):
    def test_parser_receives_question_only_and_literal_names_cues_windows_are_checked(self):
        fake = FakeLanguage(draft())
        plan = asdict(NativeQueryLanguage(fake).parse(QUESTION))
        self.assertEqual(fake.request['messages'][1]['content'], QUESTION)
        self.assertNotIn('memória:', json.dumps(fake.request))
        for key, value in (('name', 'invented'), ('modalities', ['audio']), ('window_fragment', '[1; 2]'), ('question_sha256', '0' * 64)):
            damaged = {**plan, key: value}
            with self.assertRaises(ValueError):
                validate_plan(damaged, QUESTION, 'fixture')
        source = 'Lembra de "maruvi" pela voz em UTC [1700000000,1; 1700000001,2]?'
        parsed = NativeQueryLanguage(FakeLanguage(draft(source))).parse(source)
        self.assertEqual(parsed.basis, 'utc')
        self.assertEqual(parsed.modalities, ['audio'])

    def test_repeated_name_multiple_windows_and_name_that_is_modality_word_are_distinguished(self):
        for question in ('Lembra de "maruvi" e "maruvi"?', 'Lembra de "maruvi" ou "outro"?',
                         'Lembra de "maruvi" em [1; 2] ou [3; 4]?'):
            self.assertTrue(NativeQueryLanguage(FakeLanguage(draft(question))).parse(question).uncertain)
        question = 'Lembra de "imagem"?'
        plan = NativeQueryLanguage(FakeLanguage(draft(question))).parse(question)
        self.assertEqual(plan.name, 'imagem')
        self.assertFalse(plan.modalities)

    def test_protocol_worker_import_does_not_load_torch_or_memory(self):
        child = subprocess.run([sys.executable, '-c', "import sys; import scripts.alice_memory.native_query_language; assert 'torch' not in sys.modules; assert 'scripts.alice_memory.native_query' not in sys.modules"], cwd=ROOT, capture_output=True, text=True, timeout=20)
        self.assertEqual(child.returncode, 0, child.stderr)

    def test_uncertainty_grammar_cannot_omit_an_explicit_image_cue_in_a_certain_plan(self):
        fake = FakeLanguage(draft())
        NativeQueryLanguage(fake).parse(QUESTION)
        variants = fake.request['format']['anyOf']
        certain = next(item for item in variants if item['properties']['uncertain']['const'] is False)
        uncertain = next(item for item in variants if item['properties']['uncertain']['const'] is True)
        self.assertEqual(certain['properties']['modalities']['const'], ['image'])
        self.assertEqual(uncertain['properties']['modalities']['const'], [])
        invalid = {**draft(), 'modalities': []}
        with self.assertRaises(ValueError):
            NativeQueryLanguage(FakeLanguage(invalid)).parse(QUESTION)


class NativeLifecycleContracts(unittest.TestCase):
    setUp = query_tests.QueryLifecycleContracts.setUp
    configure = query_tests.QueryLifecycleContracts.configure
    factory = query_tests.QueryLifecycleContracts.factory
    until = query_tests.QueryLifecycleContracts.until

    @classmethod
    def setUpClass(cls):
        fixtures.WrittenGroundingTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        fixtures.WrittenGroundingTests.tearDownClass()

    def core(self, learned=True):
        core = query_tests.QueryLifecycleContracts.core(self, learned=False)
        self.frame(core, teach=learned)
        return core

    def frame(self, core, teach=False, other=False):
        at = core.clock + .1
        sequence = core.native.observations
        packets = [NativeObservation(name, torch.nn.functional.one_hot(torch.tensor(axis + (10 if other else 0)), 128).float(), at,
                   sequence, '0' * 64, origin='person') for name, axis in (('image', 0), ('audio', 3))]
        core.perceive_native(packets, .1)
        if teach:
            label = WrittenName('maruvi', at, len(core.native.sources), origin='person')
            self.assertTrue(core.teach_native_name(label)['learned'])
        return at

    def answer(self, core, question=QUESTION):
        number = core.submit_native_question(question)
        self.until(core, lambda: core.native_queries.jobs[number]['status'] in core.native_queries.terminal)
        reply = core.take_native_answer(number)
        self.assertEqual(reply['status'], 'completed', reply)
        return reply

    def test_name_learned_later_evokes_earlier_unnamed_moment_and_ambiguity_is_preserved(self):
        core = self.core(False)
        first = core.native.moments.traces[0]['acquired_at']
        before = self.answer(core)
        self.assertEqual(before['evidence']['reason'], 'unlearned_native_meaning')
        self.frame(core, teach=True)
        ambiguous = self.answer(core)
        self.assertEqual(ambiguous['evidence']['reason'], 'ambiguous_moments')
        question = QUESTION[:-1] + f' no intervalo [{first-.01:.6f}; {first+.01:.6f}]?'
        remembered = self.answer(core, question)
        self.assertTrue(remembered['evidence']['supported'])
        self.assertEqual(remembered['evidence']['moment_id'], 0)
        self.assertEqual(remembered['evidence']['modalities'], ['image', 'audio'])
        self.assertTrue(remembered['factual_text_verified'])

    def test_query_does_not_write_percepts_or_labels_or_change_present_contents(self):
        core = self.core()
        count, lessons = core.native.observations, len(core.native.sources)
        banks = {name: {key: value.clone() for key, value in bank.state_dict().items()} for name, bank in core.native.writers.items()}
        working, clock = core.native.working.clone(), core.clock
        response = self.answer(core)
        self.assertTrue(response['evidence']['supported'])
        self.assertEqual(core.native.observations, count)
        self.assertEqual(len(core.native.sources), lessons)
        self.assertEqual(len(core.native.moments.traces), 1)
        self.assertTrue(torch.allclose(core.native.working, working * 2. ** (-(core.clock-clock)/5.), atol=1e-5))
        self.assertTrue(all(torch.equal(value, core.native.writers[name].state_dict()[key]) for name, values in banks.items() for key, value in values.items()))

    def test_erased_name_or_moment_weights_abstain_and_unknown_modality_does_not_invent(self):
        core = self.core()
        missing = self.answer(core, 'Lembra de "maruvi" pelo texto?')
        self.assertFalse(missing['evidence']['supported'])
        self.assertEqual(missing['evidence']['reason'], 'unlearned_native_meaning')
        core.native.moments.bank(0).outputs.zero_()
        erased = self.answer(core)
        self.assertFalse(erased['evidence']['supported'])
        self.assertEqual(erased['evidence']['reason'], 'unlearned_weights')
        core.native.writers['image'].weights.zero_()
        absent = self.answer(core)
        self.assertFalse(absent['evidence']['supported'])

    def test_fabricated_factual_text_is_rejected_even_with_valid_evidence_hash(self):
        core = self.core()
        plan = asdict(NativeQueryLanguage(FakeLanguage(draft())).parse(QUESTION))
        evidence = resolve(core.native, plan, QUESTION, reactivate=False)
        expression = asdict(NativeQueryLanguage(FakeLanguage({'text': phrases(evidence)[0]})).express(evidence))
        expression['text'] = 'Lembro que seu pai estava cozinhando.'
        with self.assertRaises(ValueError):
            validate_expression(expression, evidence, 'fixture')
        self.configure('native_bad_expression')
        number = core.submit_native_question(QUESTION)
        self.until(core, lambda: core.native_queries.jobs[number]['status'] in core.native_queries.terminal)
        self.assertEqual(core.native_queries.jobs[number]['status'], 'failed')

    def test_new_matching_frame_during_expression_requeries_before_delivery(self):
        core = self.core()
        number = core.submit_native_question(QUESTION)
        self.until(core, lambda: core.native_queries.jobs[number]['status'] == 'expressing')
        self.frame(core)
        self.until(core, lambda: core.native_queries.jobs[number]['status'] in core.native_queries.terminal)
        reply = core.take_native_answer(number)
        self.assertEqual(reply['status'], 'completed', reply)
        self.assertGreater(reply['revisions'], 0)
        self.assertEqual(reply['evidence']['reason'], 'ambiguous_moments')

    def test_changes_after_completion_invalidate_delivery_and_preserve_worker_reservation(self):
        core = self.core()
        number = core.submit_native_question(QUESTION)
        self.until(core, lambda: core.native_queries.jobs[number]['status'] == 'completed')
        core.native.writers['image'].weights.zero_()
        self.assertIsNone(core.take_native_answer(number))
        self.until(core, lambda: core.native_queries.jobs[number]['status'] == 'completed')
        reply = core.take_native_answer(number)
        self.assertFalse(reply['evidence']['supported'])
        self.assertGreater(reply['revisions'], 0)
        self.assertTrue(all(worker.process.poll() is not None for worker in self.workers))

    def test_pending_parse_and_completed_answer_survive_restart_without_reactivation_or_model(self):
        core = self.core()
        number = core.submit_native_question(QUESTION)
        core.tick(.05)
        snapshot = core.snapshot()
        self.assertEqual(snapshot['native_queries']['jobs'][0]['status'], 'waiting')
        core.close()
        resumed = restore(snapshot, self.folder / 'restart', self.factory)
        self.addCleanup(resumed.close)
        self.until(resumed, lambda: resumed.native_queries.jobs[number]['status'] == 'completed')
        saved = self.folder / 'completed.pt'
        save(saved, resumed)
        recalls = resumed.native.moments.traces[0]['recalls']
        resumed.close()
        fresh, mind, _ = load_scheduler(saved, worker_factory=lambda op: (_ for _ in ()).throw(AssertionError('No worker')))
        try:
            self.assertEqual(fresh.native.moments.traces[0]['recalls'], recalls)
            self.assertEqual(fresh.take_native_answer(number)['status'], 'completed')
        finally:
            close_agent(fresh, mind)

    def test_queue_bounds_expiry_cancel_and_resource_deferral_preserve_memory(self):
        core = self.core()
        ids = [core.submit_native_question(QUESTION, ttl=5.) for _ in range(4)]
        with self.assertRaises(ValueError):
            core.submit_native_question(QUESTION)
        core.native_queries.cancel(ids[0])
        self.configure('deferred')
        self.until(core, lambda: core.native_queries.jobs[ids[1]]['deferrals'] > 0)
        core.unobserved_gap(6.)
        core.tick(0.)
        self.assertEqual(core.native_queries.jobs[ids[1]]['status'], 'failed')
        self.assertEqual(len(core.native.moments.traces), 1)
        self.assertEqual(core.native.observations, 2)

    def test_legacy_migration_and_finite_runtime_mode_native(self):
        core = self.core()
        old = core.snapshot()
        old['format'] = 45
        old.pop('native_feedbacks')
        old.pop('native_namings')
        old.pop('interactions')
        old.pop('native_queries')
        old.pop('native_statements')
        old.pop('native_meaning_queries')
        migrated = restore(old, self.folder / 'old', self.factory)
        self.addCleanup(migrated.close)
        self.assertFalse(migrated.native_queries.jobs)
        self.assertIs(migrated.native_queries.native, migrated.native)
        checkpoint = self.folder / 'start.pt'
        save(checkpoint, core)
        report = run(self.folder / 'runtime', checkpoint, seconds=2., question=QUESTION,
                     question_mode='native', language_backend='fixture')
        self.assertEqual(report['phase'], 'stopped')
        self.assertEqual(report['native_state']['observations'], 2)
        self.assertTrue(report['workers_terminal'])
        self.assertTrue(report['native_query_jobs'])

    def test_corrupted_saved_evidence_is_rejected_and_future_window_abstains(self):
        core = self.core()
        future = self.answer(core, f'Lembra de "maruvi" em [{core.clock+1:.6f}; {core.clock+2:.6f}]?')
        self.assertFalse(future['evidence']['supported'])
        number = core.submit_native_question(QUESTION)
        self.until(core, lambda: core.native_queries.jobs[number]['status'] == 'completed')
        snapshot = core.snapshot()
        snapshot['native_queries']['jobs'][0]['evidence']['modalities'] = ['text']
        with self.assertRaises(ValueError):
            restore(snapshot, self.folder / 'invalid', self.factory)


if __name__ == '__main__':
    unittest.main()
