"""Native text acquisition and bounded generated speech share the continuous owner."""
import copy
import json
import sys
import time
import subprocess
import unittest
from unittest.mock import patch
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from scripts.alice_memory.ui_gateway import execute
from scripts.alice_memory.native_inbox import NativeInbox
from scripts.alice_memory.native_process import NativeProcess
from scripts.alice_memory.native_interpretation import NativeStatement
from scripts.alice_memory.conceptual_mind import restore
from scripts.alice_memory.interaction_inbox import digest
from scripts.alice_memory.persistent_runtime import close_agent
from scripts.alice_memory.dialogue_language import DialogueLanguage
from test_alice_concept_teaching import FakeLanguage
import test_alice_context_report as contexts
import test_alice_word_grounding as fixtures


class DialogueContracts(unittest.TestCase):
    setUp = contexts.ContextOwnerContracts.setUp
    configure = contexts.ContextOwnerContracts.configure
    factory = contexts.ContextOwnerContracts.factory
    until = contexts.ContextOwnerContracts.until
    core = contexts.ContextOwnerContracts.core
    frame = contexts.ContextOwnerContracts.frame
    inbox = contexts.ContextOwnerContracts.inbox
    ingest = contexts.ContextOwnerContracts.ingest
    commits = contexts.ContextOwnerContracts.commits
    relate = contexts.ContextOwnerContracts.relate
    setUpClass = classmethod(lambda cls: fixtures.WrittenGroundingTests.setUpClass())
    tearDownClass = classmethod(lambda cls: fixtures.WrittenGroundingTests.tearDownClass())

    def sensory(self, core):
        # This subprocess encodes fixture tensors, not a real model. Admission
        # behavior is covered separately by test_alice_native_stream.py.
        measured = patch('scripts.alice_memory.native_process.physical_memory',
                         return_value={'total_bytes': 32 * 1024**3, 'used_bytes': 8 * 1024**3})
        measured.start()
        self.addCleanup(measured.stop)
        root = self.folder / ('typed-' + str(len(getattr(self, 'native_workers', []))))
        root.mkdir()
        (root / 'seed.pt').write_bytes(b'not-loaded-by-typed-publication')
        self.typed_root = root
        inbox = NativeInbox(root / 'sensory')
        self.native_config = root / 'fixture.json'
        self.native_config.write_text(json.dumps({'delay': .02}), encoding='utf-8')
        self.native_workers = []
        def factory(jobs):
            self.assertFalse(any(worker.process.poll() is None for worker in self.workers))
            worker = NativeProcess(jobs, inbox, root / 'workers', root, Path(sys.executable), .9,
                'scripts.tests.alice_fake_native_worker', {'ALICE_FAKE_NATIVE_CONFIG': str(self.native_config)})
            self.native_workers.append(worker)
            return worker
        core.native_stream.configure(inbox, factory)
        return inbox

    def receive(self, core, text):
        ref = execute(self.typed_root, {'action': 'text', 'text': text})
        inbox = core.native_stream.inbox
        frame = inbox.available(core.native_stream.last_source_sequence)[-1]
        core.native_stream.ingest(frame, inbox.read(frame), time.time())
        return {key: ref[key] for key in ('stream_id', 'sequence')}

    def talk(self, core, human, text='Oi, vamos conversar.', about=None, wait=True):
        frame = self.receive(core, text)
        identifier, request = self.ingest(core, human, 'talk', {'text': text, 'frame': frame, 'about': about})
        if wait:
            self.until(core, lambda: core.interactions.records[identifier]['status'] in ('completed', 'failed'))
        return identifier, request

    def test_multiline_text_is_a_native_experience_and_speech_is_not_automatic_teaching(self):
        core = self.core(False)
        human = self.inbox(core)
        self.sensory(core)
        before = core.native.observations
        names = core.native.names.copy()
        identifier, _ = self.talk(core, human, 'Oi!\nPorra, tudo bem?')
        record = core.interactions.records[identifier]
        self.assertEqual(record['status'], 'completed', record)
        self.assertEqual(core.native.observations, before + 1)
        value = record['result']['data']
        self.assertTrue(value['evidence']['input']['acquired'])
        self.assertEqual(value['proposal']['origin'], 'self')
        self.assertFalse(value['proposal']['factual_text_verified'])
        self.assertFalse(value['proposal']['autobiographical_write'])
        self.assertIsNone(record['result']['learning'])
        self.assertEqual(core.native.names, names)
        self.assertFalse(core.native.interpretations.records)
        self.assertFalse(list(self.typed_root.glob('typed-*.txt')))
        self.assertTrue(all(worker.process.poll() is not None for worker in self.native_workers))

    def test_quiet_receives_text_without_asserting_a_new_sensory_episode(self):
        core = self.core(False)
        core.configure_native_attention('quiet')
        human = self.inbox(core)
        self.sensory(core)
        before = core.native.observations, core.native.moments.next_id
        identifier, _ = self.talk(core, human)
        self.assertEqual(core.interactions.records[identifier]['status'], 'completed')
        self.assertFalse(core.interactions.records[identifier]['result']['data']['evidence']['input']['acquired'])
        self.assertEqual((core.native.observations, core.native.moments.next_id), before)

    def test_different_text_cannot_reuse_a_received_frame(self):
        core = self.core(False)
        human = self.inbox(core)
        self.sensory(core)
        frame = self.receive(core, 'Um texto de verdade.')
        identifier, _ = self.ingest(core, human, 'talk', {'text': 'Outro texto.', 'frame': frame, 'about': None})
        self.until(core, lambda: core.interactions.records[identifier]['status'] == 'failed')
        self.assertFalse(core.dialogues.jobs)

    def test_new_interpretation_during_expression_revises_the_context(self):
        core = self.core(True)
        human = self.inbox(core)
        parent = self.relate(core, human)
        self.sensory(core)
        self.configure(delay=.3)
        identifier, _ = self.talk(core, human, 'Quem fez isso agora?', parent, wait=False)
        self.until(core, lambda: any(job['status'] == 'parsing' for job in core.dialogues.jobs.values()))
        core.native.teach_interpretation(NativeStatement(0, 'autor', 'mãe', 'b'*64, len(core.native.interpretations.records), core.clock, corrects=(0,)))
        self.until(core, lambda: core.interactions.records[identifier]['status'] == 'completed')
        data = core.interactions.records[identifier]['result']['data']
        self.assertEqual(data['evidence']['memory']['reports']['current']['subject'], 'mãe')
        self.assertIn('mãe', data['memory_text'])
        self.assertIn('mãe', data['proposal']['text'])
        self.assertGreater(next(iter(core.dialogues.jobs.values()))['revisions'], 0)

    def test_pending_and_durable_dialogue_survive_restart_without_relearning(self):
        core = self.core(False)
        human = self.inbox(core)
        self.sensory(core)
        identifier, request = self.talk(core, human, wait=False)
        self.until(core, lambda: any(job['status'] == 'parsing' for job in core.dialogues.jobs.values()))
        state = core.snapshot()
        observations = core.native.observations
        core.close()
        fresh = restore(state, self.folder / 'pending', self.factory)
        self.addCleanup(fresh.close)
        self.until(fresh, lambda: fresh.interactions.records[identifier]['status'] == 'completed')
        fallback = self.commits(fresh, human, self.folder / 'durable')
        resumed, mind, _ = contexts.interactions.load_scheduler(fallback, self.folder / 'restart', self.factory)
        self.addCleanup(lambda: close_agent(resumed, mind))
        resumed.interactions.ingest(request)
        resumed.tick(.1)
        self.assertEqual(resumed.native.observations, observations)
        self.assertEqual(resumed.interactions.records[identifier]['status'], 'completed')

    def test_generated_false_claim_is_not_promoted_to_owner_memory(self):
        core = self.core(True)
        human = self.inbox(core)
        parent = self.relate(core, human)
        self.sensory(core)
        config = json.loads(self.config.read_text(encoding='utf-8'))
        config['dialogue_text'] = 'Eu lembro que foi um alienígena.'
        self.config.write_text(json.dumps(config), encoding='utf-8')
        weights = core.native.interpretations.bank.weights.clone()
        identifier, _ = self.talk(core, human, 'Quem fez isso?', parent)
        record = core.interactions.records[identifier]
        self.assertEqual(record['status'], 'completed', record)
        self.assertFalse(record['result']['data']['proposal']['factual_text_verified'])
        self.assertEqual(record['result']['data']['evidence']['memory']['reports']['current']['subject'], 'pai')
        self.assertTrue(torch.equal(weights, core.native.interpretations.bank.weights))

    def test_received_frame_and_about_are_checked_after_the_job_is_taken(self):
        core = self.core(False)
        human = self.inbox(core)
        self.sensory(core)
        self.talk(core, human)
        self.commits(core, human, self.folder / 'confirmed')
        state = core.snapshot()
        bad = copy.deepcopy(state)
        record = bad['interactions']['records'][-1]
        record['request']['payload']['frame']['sequence'] += 1
        record['request_sha256'] = digest(record['request'])
        with self.assertRaises(ValueError): restore(bad, self.folder / 'forged-frame', self.factory)
        bad = copy.deepcopy(state)
        record = bad['interactions']['records'][-1]
        record['result']['data']['proposal']['factual_text_verified'] = True
        with self.assertRaises(ValueError): restore(bad, self.folder / 'forged-truth', self.factory)

    def test_working_dialogue_is_bounded_and_marked_generated(self):
        core = self.core(False)
        human = self.inbox(core)
        self.sensory(core)
        for index in range(4):
            identifier, _ = self.talk(core, human, 'Mensagem ' + str(index))
            self.assertEqual(core.interactions.records[identifier]['status'], 'completed')
            history = core.interactions.records[identifier]['result']['data']['evidence']['history']
            self.assertEqual(len(history), min(index, 2))
            self.assertTrue(all(item['origin'] == 'self_generated_response' for item in history))
            self.commits(core, human, self.folder / ('turn-' + str(index)))

    def test_language_receives_a_projection_without_transport_ids_or_full_memory(self):
        core = self.core(False)
        human = self.inbox(core)
        self.sensory(core)
        question = 'Oi, tudo bem?'
        identifier, _ = self.talk(core, human, question)
        context = core.interactions.records[identifier]['result']['data']['evidence']
        fake = FakeLanguage({'text': 'Oi! Vamos conversar.'})
        proposal = DialogueLanguage(fake).express(question, context)
        content = fake.request['messages'][1]['content']
        self.assertNotIn(context['input']['frame']['stream_id'], content)
        self.assertNotIn(context['input']['sha256'], content)
        self.assertNotIn(context['signature'], content)
        self.assertFalse(proposal.factual_text_verified)
        self.assertEqual(fake.request['options']['num_ctx'], 2048)
        self.assertEqual(fake.request['options']['num_predict'], 512)

    def test_language_protocol_import_does_not_load_neural_memory(self):
        child = subprocess.run([sys.executable, '-c', "import sys;import scripts.alice_memory.dialogue_language;assert 'torch' not in sys.modules"], cwd=ROOT, capture_output=True, text=True, timeout=20)
        self.assertEqual(child.returncode, 0, child.stderr)

    def test_unrelated_previous_topic_does_not_enter_selected_memory_context(self):
        core = self.core(True)
        human = self.inbox(core)
        parent = self.relate(core, human)
        self.sensory(core)
        first, _ = self.talk(core, human, 'Quero conversar sobre formigas.')
        self.assertEqual(core.interactions.records[first]['status'], 'completed')
        self.commits(core, human, self.folder / 'previous-topic')
        second, _ = self.talk(core, human, 'Quem é o autor?', parent)
        record = core.interactions.records[second]
        self.assertEqual(record['status'], 'completed', record)
        self.assertFalse(record['result']['data']['evidence']['history'])
        self.assertEqual(record['result']['data']['evidence']['memory']['reports']['current']['subject'], 'pai')

    def test_model_comparison_has_identical_context_and_restores_erased_weights(self):
        from scripts.alice_memory.dialogue_model_probe import cases
        from scripts.alice_memory.dialogue_language import validate_context
        core = self.core(True)
        human = self.inbox(core)
        self.relate(core, human)
        saved = core.native.interpretations.bank.weights.clone()
        counts = core.native.observations, core.native.moments.next_id
        first, second = cases(core), cases(core)
        self.assertEqual(first, second)
        self.assertEqual(len(first), 8)
        for item in first:
            validate_context(item['context'], item['question'])
            self.assertFalse(item['context']['input']['acquired'])
        erased = next(item for item in first if item['name'] == 'erased_with_generated_history')
        self.assertTrue(erased['context']['history'])
        self.assertIsNone(erased['expected_owner_values']['current'])
        self.assertFalse(erased['context']['memory']['reports']['current']['supported'])
        self.assertTrue(torch.equal(saved, core.native.interpretations.bank.weights))
        self.assertEqual(counts, (core.native.observations, core.native.moments.next_id))

    def test_model_comparison_restores_weights_when_erased_control_fails(self):
        from scripts.alice_memory import dialogue_model_probe as probe
        core = self.core(True)
        human = self.inbox(core)
        self.relate(core, human)
        saved = core.native.interpretations.bank.weights.clone()
        original = probe.resolve_reference
        calls = []
        def fail_in_erased_control(*args):
            calls.append(None)
            if len(calls) == 3:
                self.assertFalse(torch.count_nonzero(core.native.interpretations.bank.weights))
                raise RuntimeError('deliberate control failure')
            return original(*args)
        with patch.object(probe, 'resolve_reference', side_effect=fail_in_erased_control):
            with self.assertRaisesRegex(RuntimeError, 'deliberate control failure'):
                probe.cases(core)
        self.assertTrue(torch.equal(saved, core.native.interpretations.bank.weights))

    def test_model_comparison_reports_backend_failures_without_quality_approval(self):
        from scripts.alice_memory import dialogue_model_probe as probe
        core = self.core(True)
        human = self.inbox(core)
        self.relate(core, human)
        source = self.folder / 'unchanged-source.pt'
        source.write_bytes(b'checkpoint reader is injected for this backend failure test')
        checksum = probe.digest(source)
        with patch.object(probe, 'load_scheduler', return_value=(core, None, None)), \
                patch.object(probe, 'close_agent') as close, \
                patch.object(probe, 'DialogueLanguage') as language:
            language.return_value.express.side_effect = RuntimeError('resource admission denied')
            report = probe.run(source, self.folder / 'comparison', 'http://127.0.0.1:11438', 'fixture')
        self.assertFalse(report['protocol_completed'])
        self.assertFalse(report['quality_approved'])
        self.assertTrue(report['source_unchanged'])
        self.assertEqual(report['completed'], 0)
        self.assertEqual(report['total'], 8)
        self.assertTrue(all('resource admission denied' in item['error'] for item in report['cases']))
        self.assertEqual(probe.digest(source), checksum)
        close.assert_called_once_with(core, None)

    def test_separate_expression_model_preserves_parser_memory_and_completed_history(self):
        from scripts.alice_memory.persistent_runtime import configure_dialogue
        core = self.core(True)
        human = self.inbox(core)
        parent = self.relate(core, human)
        self.sensory(core)
        parser = core.agent.model
        weights = core.native.interpretations.bank.weights.clone()
        configure_dialogue(core, 'fixture-expression')
        first, _ = self.talk(core, human, 'Quem foi?', parent)
        self.assertEqual(core.interactions.records[first]['result']['data']['proposal']['model'], 'fixture-expression')
        self.commits(core, human, self.folder / 'expression-first')
        configure_dialogue(core, '')
        second, _ = self.talk(core, human, 'E antes?', parent)
        self.assertEqual(core.interactions.records[second]['result']['data']['proposal']['model'], parser)
        self.commits(core, human, self.folder / 'expression-second')
        state = core.snapshot()
        core.close()
        fresh = restore(state, self.folder / 'expression-resumed', self.factory)
        self.addCleanup(fresh.close)
        self.assertIsNone(fresh.dialogues.model)
        self.assertEqual(fresh.agent.model, parser)
        self.assertEqual(fresh.interactions.records[first]['result']['data']['proposal']['model'], 'fixture-expression')
        self.assertEqual(fresh.interactions.records[second]['result']['data']['proposal']['model'], parser)
        self.assertTrue(torch.equal(weights, fresh.native.interpretations.bank.weights))

    def test_pending_expression_keeps_its_model_after_selection_change_and_restart(self):
        from scripts.alice_memory.persistent_runtime import configure_dialogue
        core = self.core(False)
        human = self.inbox(core)
        self.sensory(core)
        self.configure(delay=.3)
        configure_dialogue(core, 'fixture-first')
        identifier, _ = self.talk(core, human, wait=False)
        self.until(core, lambda: bool(core.dialogues.jobs))
        configure_dialogue(core, 'fixture-next')
        state = core.snapshot()
        self.assertEqual(state['interactions']['dialogues']['jobs'][0]['model'], 'fixture-first')
        core.close()
        fresh = restore(state, self.folder / 'expression-pending', self.factory)
        self.addCleanup(fresh.close)
        self.assertEqual(fresh.dialogues.model, 'fixture-next')
        self.until(fresh, lambda: fresh.interactions.records[identifier]['status'] in ('completed', 'failed'))
        record = fresh.interactions.records[identifier]
        self.assertEqual(record['status'], 'completed', record)
        self.assertEqual(record['result']['data']['proposal']['model'], 'fixture-first')
        bad = fresh.snapshot()
        bad['interactions']['dialogues']['jobs'][0]['model'] = 'fixture-impostor'
        with self.assertRaises(ValueError): restore(bad, self.folder / 'expression-forged', self.factory)

    def test_legacy_dialogue_queue_migrates_and_invalid_expression_selection_is_atomic(self):
        from scripts.alice_memory.persistent_runtime import configure_dialogue
        core = self.core(False)
        human = self.inbox(core)
        self.sensory(core)
        identifier, _ = self.talk(core, human)
        state = core.snapshot()
        queue = state['interactions']['dialogues']
        queue['format'] = 1
        queue.pop('model')
        for job in queue['jobs']: job.pop('model')
        core.close()
        fresh = restore(state, self.folder / 'expression-legacy', self.factory)
        self.addCleanup(fresh.close)
        self.assertEqual(fresh.dialogues.snapshot()['format'], 2)
        self.assertIsNone(fresh.dialogues.model)
        self.assertEqual(fresh.interactions.records[identifier]['status'], 'completed')
        configure_dialogue(fresh, 'fixture-valid')
        configure_dialogue(fresh, None)
        for value in ('has space', '\n', 'x'*129, 17):
            with self.assertRaises(ValueError): configure_dialogue(fresh, value)
            self.assertEqual(fresh.dialogues.model, 'fixture-valid')

    def test_auto_recall_reads_named_senses_without_selected_parent_and_warms_once(self):
        core = self.core(True)
        human = self.inbox(core)
        self.relate(core, human)
        self.sensory(core)
        weights = core.native.interpretations.bank.weights.clone()
        count = core.native.moments.get(0)['recalls']
        identifier, _ = self.talk(core, human, 'Quem é o autor de MARUVI?')
        record = core.interactions.records[identifier]
        self.assertEqual(record['status'], 'completed', record)
        data = record['result']['data']
        context = data['evidence']
        self.assertIsNone(context['about'])
        self.assertIsNone(context['memory'])
        association = context['association']
        self.assertEqual(association['reason'], 'recalled_topic')
        self.assertEqual(association['sensory']['moment_id'], 0)
        self.assertEqual(association['memory']['reports']['current']['subject'], 'pai')
        self.assertIn('pai', data['memory_text'])
        self.assertIn('pai', data['proposal']['text'])
        job = next(iter(core.dialogues.jobs.values()))
        for _ in range(3): self.assertTrue(core.dialogues.current(job['context']))
        self.assertEqual(core.native.moments.get(0)['recalls'], count + 1)
        self.assertTrue(torch.equal(weights, core.native.interpretations.bank.weights))
        fake = FakeLanguage({'text': 'O relato aponta para pai.'})
        DialogueLanguage(fake).express(job['question'], context)
        body = json.loads(fake.request['messages'][1]['content'])
        self.assertEqual(body['owner_context']['memory']['reports']['current']['subject'], 'pai')
        self.assertNotIn(context['input']['frame']['stream_id'], fake.request['messages'][1]['content'])
        from scripts.alice_memory.dialogue_language import validate_context
        damaged = copy.deepcopy(context)
        damaged['state']['names'] = []
        with self.assertRaises(ValueError): validate_context(damaged, job['question'])
        child = subprocess.run([sys.executable, '-c',
            "import json,sys;from scripts.alice_memory.dialogue_language import validate_context;"
            "x=json.loads(sys.stdin.read());validate_context(x['context'],x['question']);assert 'torch' not in sys.modules"],
            input=json.dumps({'context': context, 'question': job['question']}), cwd=ROOT,
            capture_output=True, text=True, timeout=20)
        self.assertEqual(child.returncode, 0, child.stderr)

    def test_auto_recall_requires_name_episode_and_interpretation_weights(self):
        from scripts.alice_memory.dialogue_recall import resolve
        core = self.core(True)
        human = self.inbox(core)
        self.relate(core, human)
        received = {'acquired': True}
        question = 'Quem é maruvi?'
        self.assertEqual(resolve(core.native, question, received)['reason'], 'recalled_topic')
        saved = {name: bank.weights.clone() for name, bank in core.native.writers.items()}
        try:
            for bank in core.native.writers.values(): bank.weights.zero_()
            self.assertEqual(resolve(core.native, question, received)['reason'], 'sensory_unavailable')
        finally:
            for name, bank in core.native.writers.items(): bank.weights.copy_(saved[name])

    def test_auto_recall_episodic_and_report_ablation_never_copies_metadata(self):
        from scripts.alice_memory.dialogue_recall import resolve
        core = self.core(True)
        human = self.inbox(core)
        self.relate(core, human)
        received, question = {'acquired': True}, 'Quem é maruvi?'
        bank = core.native.moments.bank(0)
        saved = bank.outputs.clone()
        bank.outputs.zero_()
        self.assertEqual(resolve(core.native, question, received)['reason'], 'sensory_unavailable')
        bank.outputs.copy_(saved)
        core.native.interpretations.bank.weights.zero_()
        value = resolve(core.native, question, received)
        self.assertEqual(value['reason'], 'recalled_topic')
        self.assertIsNone(value['memory']['reports']['current']['subject'])
        self.assertFalse(value['memory']['reports']['current']['supported'])

    def test_auto_recall_preserves_unknown_quiet_and_ambiguous_sensory_cases(self):
        from scripts.alice_memory.dialogue_recall import resolve
        core = self.core(True)
        human = self.inbox(core)
        self.relate(core, human)
        self.assertEqual(resolve(core.native, 'maruviz', {'acquired': True})['reason'], 'no_name_cue')
        quiet = resolve(core.native, 'maruvi', {'acquired': False})
        self.assertEqual(quiet['reason'], 'unattended')
        self.assertIsNone(quiet['memory'])
        from scripts.alice_memory.grounded_mind import WrittenName
        self.frame(core, other=True)
        self.assertTrue(core.teach_native_name(WrittenName('outro', core.clock, 777, origin='person'))['learned'])
        self.assertEqual(resolve(core.native, 'maruvi e outro', {'acquired': True})['reason'], 'ambiguous_name_cues')
        self.frame(core)
        value = resolve(core.native, 'maruvi', {'acquired': True})
        self.assertEqual(value['sensory']['reason'], 'ambiguous_moments')
        self.assertIsNone(value['memory'])

    def test_auto_recall_revises_when_a_report_changes_during_expression(self):
        core = self.core(True)
        human = self.inbox(core)
        self.relate(core, human)
        self.sensory(core)
        self.configure(delay=.3)
        identifier, _ = self.talk(core, human, 'Quem é maruvi?', wait=False)
        self.until(core, lambda: any(job['status'] == 'parsing' for job in core.dialogues.jobs.values()))
        core.native.teach_interpretation(NativeStatement(0, 'autor', 'mãe', 'b'*64, len(core.native.interpretations.records), core.clock, corrects=(0,)))
        self.until(core, lambda: core.interactions.records[identifier]['status'] == 'completed')
        data = core.interactions.records[identifier]['result']['data']
        self.assertEqual(data['evidence']['association']['memory']['reports']['initial']['subject'], 'pai')
        self.assertEqual(data['evidence']['association']['memory']['reports']['current']['subject'], 'mãe')
        self.assertIn('mãe', data['proposal']['text'])
        self.assertGreater(next(iter(core.dialogues.jobs.values()))['revisions'], 0)

    def test_auto_recall_does_not_choose_between_roles_or_replace_explicit_selection(self):
        from scripts.alice_memory.dialogue_recall import resolve
        core = self.core(True)
        human = self.inbox(core)
        self.assertEqual(resolve(core.native, 'maruvi', {'acquired': True})['reason'], 'no_report')
        parent = self.relate(core, human)
        core.native.teach_interpretation(NativeStatement(0, 'cor', 'azul', 'c'*64,
            len(core.native.interpretations.records), core.clock))
        self.assertEqual(resolve(core.native, 'maruvi', {'acquired': True})['reason'], 'ambiguous_relations')
        self.sensory(core)
        identifier, _ = self.talk(core, human, 'Quem é maruvi?', parent)
        data = core.interactions.records[identifier]['result']['data']
        self.assertIsNone(data['evidence']['association'])
        self.assertEqual(data['evidence']['memory']['reports']['current']['subject'], 'pai')

    def test_auto_recall_pending_and_taken_records_restore_and_reject_changed_binding(self):
        core = self.core(True)
        human = self.inbox(core)
        self.relate(core, human)
        self.sensory(core)
        self.configure(delay=.3)
        identifier, _ = self.talk(core, human, 'Quem é maruvi?', wait=False)
        self.until(core, lambda: any(job['status'] == 'parsing' for job in core.dialogues.jobs.values()))
        state = core.snapshot()
        core.close()
        fresh = restore(state, self.folder / 'auto-pending', self.factory)
        self.addCleanup(fresh.close)
        self.until(fresh, lambda: fresh.interactions.records[identifier]['status'] == 'completed')
        self.commits(fresh, human, self.folder / 'auto-committed')
        state = fresh.snapshot()
        self.assertFalse(state['interactions']['dialogues']['jobs'])
        resumed = restore(state, self.folder / 'auto-taken', self.factory)
        self.addCleanup(resumed.close)
        data = resumed.interactions.records[identifier]['result']['data']
        self.assertIn('pai', data['memory_text'])
        self.assertEqual(data['evidence']['association']['memory']['reports']['current']['subject'], 'pai')
        bad = copy.deepcopy(state)
        record = next(item for item in bad['interactions']['records'] if item['request']['id'] == identifier)
        association = record['result']['data']['evidence']['association']
        association['binding']['version'] = 999
        from scripts.alice_memory.dialogue_recall import signature
        association['signature'] = signature(association)
        with self.assertRaises(ValueError): restore(bad, self.folder / 'auto-forged', self.factory)

    def test_runtime_wraps_legacy_language_owner_before_configuring_expression(self):
        from scripts.alice_memory.language_coordinator import save
        from scripts.alice_memory.persistent_runtime import run
        from scripts.alice_memory.continuous_experiment import load_scheduler
        core = self.core(False)
        source = self.folder / 'legacy-language.pt'
        save(source, core.agent)
        core.close()
        runtime = self.folder / 'expression-runtime'
        report = run(runtime, source, seconds=.4, language_backend='fixture',
                     dialogue_model='fixture-expression', native_attention='quiet')
        self.assertEqual(report['phase'], 'stopped')
        pointer = json.loads((runtime / 'current.json').read_text(encoding='utf-8'))
        fresh, mind, _ = load_scheduler(runtime / pointer['current']['file'])
        self.addCleanup(lambda: close_agent(fresh, mind))
        self.assertEqual(fresh.dialogues.model, 'fixture-expression')
        self.assertEqual(fresh.native.attention.mode, 'quiet')


if __name__ == '__main__': unittest.main()
