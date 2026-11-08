"""External naming, immutable sensory binding and one-worker lifecycle."""
import copy
import json
import subprocess
import sys
import unittest
from dataclasses import asdict
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from scripts.alice_memory.native_name_language import NativeNameLanguage, validate_plan
from scripts.alice_memory.conceptual_mind import restore, save
from scripts.alice_memory.continuous_experiment import load_scheduler
from scripts.alice_memory.persistent_runtime import close_agent, configure_language
from test_alice_concept_teaching import FakeLanguage
import test_alice_native_query as native_tests
import test_alice_word_grounding as fixtures

MESSAGE = 'Porra, essa imagem se chama lumo.'


class NameProtocolContracts(unittest.TestCase):
    def test_parser_only_receives_message_and_copies_literal_single_word(self):
        fake = FakeLanguage({'name_fragment': 'lumo'})
        plan = NativeNameLanguage(fake).parse(MESSAGE)
        self.assertEqual(plan.name_fragment, 'lumo')
        self.assertEqual(fake.request['messages'][1]['content'], MESSAGE)
        self.assertNotIn('moment_ref', json.dumps(fake.request))
        for draft in ({'name_fragment': 'invented'}, {'name_fragment': 'imagem'}, {'name_fragment': 'umo'}):
            with self.assertRaises(ValueError):
                NativeNameLanguage(FakeLanguage(draft)).parse(MESSAGE)
        wrong = {**asdict(plan), 'modality': 'audio'}
        with self.assertRaises(ValueError):
            validate_plan(wrong, MESSAGE, 'fixture')

    def test_question_negation_report_hypothesis_and_alternatives_cannot_teach(self):
        for message in ('Essa imagem se chama lumo?', 'Essa imagem não é lumo.',
                        'Ele disse que essa imagem é lumo.', 'Talvez essa imagem seja lumo.',
                        'Essa imagem é lumo ou tavi.'):
            with self.assertRaises(ValueError):
                NativeNameLanguage(FakeLanguage({'name_fragment': 'lumo'})).parse(message)
            plan = NativeNameLanguage(FakeLanguage({'name_fragment': None})).parse(message)
            self.assertTrue(plan.uncertain)
        process = subprocess.run([sys.executable, '-c', "import sys;import scripts.alice_memory.native_name_language;assert 'torch' not in sys.modules"],
                                 cwd=ROOT, capture_output=True, text=True, timeout=20)
        self.assertEqual(process.returncode, 0, process.stderr)

    def test_literal_binding_uses_same_canonical_identity_as_name_weights(self):
        for candidate in ('lumo', 'Lumo', 'Ｌｕｍｏ'):
            plan = NativeNameLanguage(FakeLanguage({'name_fragment': candidate})).parse(MESSAGE)
            self.assertEqual(plan.name_fragment, candidate)
        with self.assertRaises(ValueError):
            NativeNameLanguage(FakeLanguage({'name_fragment': 'ı'})).parse('Esse som se chama i.')


class NameLifecycleContracts(unittest.TestCase):
    setUp = native_tests.NativeLifecycleContracts.setUp
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

    def configure(self, mode='normal', delay=0., modality='image', fragment='lumo'):
        self.config.write_text(json.dumps({'mode': mode, 'delay': delay, 'name_modality': modality, 'name_fragment': fragment}), encoding='utf-8')

    def finish_name(self, core, number):
        self.until(core, lambda: core.native_namings.jobs[number]['status'] in core.native_namings.terminal)
        return core.take_native_name(number)

    def test_delayed_name_teaches_original_image_without_binding_new_frame_or_audio(self):
        core = self.core(False)
        original = core.native.active['packets'][0]
        count = core.native.observations
        self.configure(delay=.3)
        number = core.submit_native_name(MESSAGE)
        self.frame(core, other=True)
        current = core.native.active['packets'][0]
        response = self.finish_name(core, number)
        self.assertEqual(response['status'], 'completed', response)
        self.assertEqual(core.native.recognize(original)['name'], 'lumo')
        self.assertFalse(core.native.recognize(current)['supported'])
        self.assertFalse(core.native.evoke('lumo', 'audio')['supported'])
        self.assertEqual(core.native.observations, count + 2)
        self.assertEqual(core.native.naming_proofs[0]['moment_ref']['id'], 0)
        self.assertEqual(len(core.native.sources), 1)
        self.assertEqual(core.native.sources[0]['samples'], {'image': original.sample_sha256})

    def test_uncertain_invented_and_ambiguous_messages_do_not_learn(self):
        core = self.core(False)
        for mode, message, modality in (('normal', MESSAGE + '?', 'image'), ('invent_claim', MESSAGE, 'image'),
                                        ('normal', 'Isso se chama lumo.', 'unspecified')):
            self.configure(mode, modality=modality)
            result = self.finish_name(core, core.submit_native_name(message))
            self.assertIn(result['status'], ('failed', 'uncertain'))
            self.assertFalse(core.native.names)
        self.configure(modality='unspecified')
        result = self.finish_name(core, core.submit_native_name('Isso se chama lumo.', focus='image'))
        self.assertEqual(result['status'], 'completed')
        self.assertFalse(core.native.evoke('lumo', 'audio')['supported'])

    def test_unattended_channel_self_stale_and_duplicate_requests_are_refused(self):
        core = self.core(False)
        with self.assertRaises(ValueError):
            core.submit_native_name(MESSAGE, origin='self')
        number = core.submit_native_name(MESSAGE)
        with self.assertRaises(ValueError):
            core.submit_native_name(MESSAGE)
        with self.assertRaises(ValueError):
            configure_language(core, 'http://127.0.0.1:11439', 'fixture')
        core.native_namings.cancel(number)
        core.take_native_name(number)
        core.configure_native_attention('learned')
        self.frame(core)
        self.configure(modality='audio')
        result = self.finish_name(core, core.submit_native_name('Esse som se chama lumo.'))
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['learning']['reason'], 'named_modality_was_not_attended')
        self.assertFalse(core.native.names)
        core.tick(31.)
        with self.assertRaises(ValueError):
            core.submit_native_name(MESSAGE)

    def test_forgotten_target_is_not_reconstructed_from_llm_or_current_frame(self):
        from scripts.alice_memory.native_impact import MomentValues
        core = self.core(False)
        memory = core.native.moments
        memory.capacity = memory.hot_limit = 1
        memory.routes = memory.routes[:1].clone()
        memory.values = MomentValues(1)
        self.configure(delay=.3)
        number = core.submit_native_name(MESSAGE)
        self.frame(core, other=True)
        self.assertIsNone(memory.get(0))
        result = self.finish_name(core, number)
        self.assertEqual(result['learning'], {'learned': False, 'reason': 'no_retained_named_moment'})
        self.assertFalse(core.native.names)

    def test_quiet_input_does_not_implicitly_name_previous_perception(self):
        core = self.core(False)
        core.configure_native_attention('quiet')
        self.frame(core, other=True)
        with self.assertRaises(ValueError):
            core.submit_native_name(MESSAGE)
        self.assertFalse(core.native.names)

    def test_pending_and_completed_restart_preserve_binding_without_second_write(self):
        core = self.core(False)
        number = core.submit_native_name(MESSAGE)
        core.tick(.05)
        checkpoint = self.folder / 'naming.pt'
        save(checkpoint, core)
        core.close()
        resumed, mind, _ = load_scheduler(checkpoint, self.folder / 'resumed', self.factory)
        self.addCleanup(lambda: close_agent(resumed, mind))
        self.assertEqual(resumed.native_namings.jobs[number]['status'], 'waiting')
        self.until(resumed, lambda: resumed.native_namings.jobs[number]['status'] == 'completed')
        completed = restore(resumed.snapshot(), self.folder / 'completed', self.factory)
        self.addCleanup(completed.close)
        completed.tick(.1)
        self.assertEqual(len(completed.native.sources), 1)
        self.assertEqual(completed.take_native_name(number)['status'], 'completed')
        bad = copy.deepcopy(resumed.snapshot())
        bad['native_namings']['jobs'][0]['moment_ref']['sources']['image']['sha256'] = 'b' * 64
        with self.assertRaises(ValueError):
            restore(bad, self.folder / 'bad', self.factory)

    def test_legacy_checkpoint_migrates_without_inventing_naming_proofs(self):
        core = self.core(False)
        old = core.snapshot()
        old['format'] = 53
        old.pop('native_namings')
        old.pop('interactions')
        old['native']['format'] = 7
        old['native'].pop('naming_proofs')
        resumed = restore(old, self.folder / 'legacy', self.factory)
        self.addCleanup(resumed.close)
        self.assertFalse(resumed.native_namings.jobs)
        self.assertFalse(resumed.native.naming_proofs)
        self.assertEqual(resumed.snapshot()['format'], 57)

    def test_clarification_reply_teaches_old_perception_at_actual_reply_time(self):
        core = self.core(False)
        original = core.native.active['packets'][0]
        self.configure('invent_claim')
        number = core.submit_native_name(MESSAGE)
        self.until(core, lambda: core.native_namings.jobs[number]['status'] == 'failed')
        question = core.native_name_clarification(number)
        self.assertEqual(question['focus'], 'image')
        self.assertEqual(question['moment_ref']['id'], 0)
        self.assertTrue(question['initiative_is_supplied'])
        core.tick(31.)
        self.frame(core, other=True)
        current = core.native.active['packets'][0]
        issued = core.clock
        count = core.native.observations
        result = core.reply_native_name(number, 'Lumo')
        self.assertTrue(result['learned'])
        self.assertEqual(core.native.recognize(original)['name'], 'lumo')
        self.assertFalse(core.native.recognize(current)['supported'])
        self.assertEqual(core.native.observations, count)
        self.assertEqual(core.native.sources[-1]['acquired_at'], issued)
        self.assertEqual(core.native.naming_proofs[-1]['language']['kind'], 'external_word_reply')
        self.assertIsNone(core.native_name_clarification(number))
        with self.assertRaises(ValueError):
            core.reply_native_name(number, 'lumo')

    def test_reply_resolves_modality_and_resumes_without_duplicate_teaching(self):
        core = self.core(False)
        self.configure(modality='unspecified')
        number = core.submit_native_name('Isso se chama lumo.')
        self.until(core, lambda: core.native_namings.jobs[number]['status'] == 'failed')
        self.assertIsNone(core.native_name_clarification(number)['focus'])
        with self.assertRaises(ValueError):
            core.reply_native_name(number, 'lumo')
        checkpoint = self.folder / 'clarification.pt'
        save(checkpoint, core)
        resumed, mind, _ = load_scheduler(checkpoint, self.folder / 'reply', self.factory)
        self.addCleanup(lambda: close_agent(resumed, mind))
        resumed.reply_native_name(number, 'lumo', 'audio')
        completed = restore(resumed.snapshot(), self.folder / 'reply-completed', self.factory)
        self.addCleanup(completed.close)
        completed.tick(.1)
        self.assertEqual(len(completed.native.sources), 1)
        self.assertTrue(completed.native.evoke('lumo', 'audio')['supported'])
        self.assertFalse(completed.native.evoke('lumo', 'image')['supported'])
        bad = copy.deepcopy(resumed.snapshot())
        bad['native_namings']['jobs'][0]['reply']['word'] = 'tavi'
        with self.assertRaises(ValueError):
            restore(bad, self.folder / 'bad-reply', self.factory)

    def test_explicit_old_moment_and_legacy_queue_preserve_selection_rules(self):
        core = self.core(False)
        core.tick(31.)
        with self.assertRaises(ValueError):
            core.submit_native_name(MESSAGE)
        number = core.submit_native_name(MESSAGE, moment=0)
        result = self.finish_name(core, number)
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['learning']['retained_moment'], 0)
        original = self.core(False)
        original.submit_native_name(MESSAGE)
        old = original.snapshot()
        old['native_namings']['format'] = 1
        for job in old['native_namings']['jobs']:
            job.pop('selected')
            job.pop('reply')
        migrated = restore(old, self.folder / 'queue1', self.factory)
        self.addCleanup(migrated.close)
        self.assertFalse(migrated.native_namings.jobs[1]['selected'])
        self.assertIsNone(migrated.native_namings.jobs[1]['reply'])

    def test_expired_or_forgotten_context_cannot_accept_word_reply(self):
        core = self.core(False)
        self.configure('invent_claim')
        number = core.submit_native_name(MESSAGE)
        self.until(core, lambda: core.native_namings.jobs[number]['status'] == 'failed')
        core.tick(60.)
        for _ in range(5):
            core.tick(60.)
        self.assertIsNone(core.native_name_clarification(number))
        with self.assertRaises(ValueError):
            core.reply_native_name(number, 'lumo')
        self.assertFalse(core.native.names)
        from scripts.alice_memory.native_impact import MomentValues
        forgotten = self.core(False)
        memory = forgotten.native.moments
        memory.capacity = memory.hot_limit = 1
        memory.routes = memory.routes[:1].clone()
        memory.values = MomentValues(1)
        number = forgotten.submit_native_name(MESSAGE)
        self.until(forgotten, lambda: forgotten.native_namings.jobs[number]['status'] == 'failed')
        self.frame(forgotten, other=True)
        self.assertIsNone(memory.get(0))
        self.assertIsNone(forgotten.native_name_clarification(number))
        with self.assertRaises(ValueError):
            forgotten.reply_native_name(number, 'lumo')
        self.assertFalse(forgotten.native.names)


if __name__ == '__main__':
    unittest.main()
