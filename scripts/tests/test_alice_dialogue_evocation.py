"""Actual named evocation, published relevance feedback and persistent credit."""
import copy
import json
import subprocess
import sys
import unittest
from pathlib import Path

import torch
from torch.nn import functional as F

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_alice_dialogue as dialogue
from scripts.alice_memory.conceptual_mind import restore
from scripts.alice_memory.dialogue_evocation import capture, validate_binding
from scripts.alice_memory.dialogue_language import DialogueLanguage
from scripts.alice_memory.interaction_inbox import digest, validate as validate_request
from scripts.alice_memory.native_sensor import NativeObservation
from scripts.alice_memory.recall_feedback import available
from scripts.alice_memory.grounded_mind import WrittenName


class DialogueEvocationContracts(unittest.TestCase):
    setUp = dialogue.DialogueContracts.setUp
    configure = dialogue.DialogueContracts.configure
    factory = dialogue.DialogueContracts.factory
    until = dialogue.DialogueContracts.until
    core = dialogue.DialogueContracts.core
    frame = dialogue.DialogueContracts.frame
    inbox = dialogue.DialogueContracts.inbox
    ingest = dialogue.DialogueContracts.ingest
    commits = dialogue.DialogueContracts.commits
    sensory = dialogue.DialogueContracts.sensory
    receive = dialogue.DialogueContracts.receive
    talk = dialogue.DialogueContracts.talk
    setUpClass = classmethod(dialogue.DialogueContracts.setUpClass.__func__)
    tearDownClass = classmethod(dialogue.DialogueContracts.tearDownClass.__func__)

    def perceive(self, core, pairs):
        at = core.clock + .1
        packets = [NativeObservation(modality, F.one_hot(torch.tensor(axis), 128).float(), at,
            core.native.received_observations, '0' * 64, origin='person') for modality, axis in pairs]
        return core.perceive_native(packets, .1)

    def prepared(self):
        core = self.core(False)
        core.native.configure_implicit_recall(True)
        self.perceive(core, [('image', 60), ('audio', 61)])
        self.perceive(core, [('image', 50), ('audio', 51)])
        self.assertTrue(core.teach_native_name(WrittenName('maruvi', core.clock, 0, origin='person'))['learned'])
        self.perceive(core, [('image', 62), ('audio', 63)])
        self.perceive(core, [('image', 50), ('audio', 52)])
        human = self.inbox(core)
        self.sensory(core)
        return core, human

    def published(self, core, human):
        identifier, _ = self.talk(core, human, 'Vamos conversar sobre maruvi.')
        self.assertEqual(core.interactions.records[identifier]['status'], 'completed')
        self.commits(core, human, self.folder / 'commits')
        return identifier

    def test_named_ambiguity_evokes_without_claiming_a_factual_answer_or_repeating_on_poll(self):
        core, human = self.prepared()
        before = core.native.observations
        identifier, _ = self.talk(core, human, 'Quem fez maruvi?')
        record = core.interactions.records[identifier]
        context = core.dialogues.jobs[record['job']]['context']
        association = context['association']
        self.assertEqual(association['sensory']['reason'], 'ambiguous_moments')
        self.assertIsNone(association['memory'])
        evoked = association['evocation']
        self.assertEqual(len(evoked['entries']), 2)
        self.assertEqual({entry['moment_ref']['id'] for entry in evoked['entries']}, {2, 4})
        self.assertIsNotNone(evoked['choice'])
        self.assertEqual(core.native.observations, before + 1)
        working = core.native.working.clone()
        heats = [core.native.moments.get(number)['recalls'] for number in (2, 4)]
        for _ in range(3): self.assertTrue(core.dialogues.current(context))
        self.assertTrue(torch.equal(working, core.native.working))
        self.assertEqual(heats, [core.native.moments.get(number)['recalls'] for number in (2, 4)])
        core.tick(.1)
        self.assertTrue(core.dialogues.current(context))
        self.assertEqual(available(core), [])

    def test_published_feedback_updates_only_preference_and_replay_is_rejected(self):
        core, human = self.prepared()
        identifier = self.published(core, human)
        self.assertEqual(available(core)[0]['about'], identifier)
        counts = core.native.observations, core.native.moments.next_id, len(core.native.sources)
        facts = {number: core.native.moments.bank(number).outputs.clone() for number in (2, 4)}
        target, request = self.ingest(core, human, 'recall_feedback', {'about': identifier, 'relevance': 1.})
        core.tick(.05)
        self.assertEqual(core.interactions.records[target]['status'], 'completed')
        self.assertEqual(int(core.native.recall_preference.bank.writes), 1)
        self.assertEqual(counts, (core.native.observations, core.native.moments.next_id, len(core.native.sources)))
        self.assertTrue(all(torch.equal(value, core.native.moments.bank(number).outputs) for number, value in facts.items()))
        self.assertTrue(core.interactions.ingest(request))
        second, _ = self.ingest(core, human, 'recall_feedback', {'about': identifier, 'relevance': -1.})
        core.tick(.05)
        self.assertEqual(core.interactions.records[second]['status'], 'failed')
        self.assertEqual(int(core.native.recall_preference.bank.writes), 1)
        self.assertEqual(available(core), [])

    def test_restart_keeps_actual_credit_and_consumed_feedback_without_retraining(self):
        core, human = self.prepared()
        identifier = self.published(core, human)
        fresh = restore(core.snapshot(), self.folder / 'fresh', self.factory)
        self.addCleanup(fresh.close)
        feedback, _ = self.ingest(fresh, human, 'recall_feedback', {'about': identifier, 'relevance': -1.})
        fresh.tick(.05)
        self.assertEqual(fresh.interactions.records[feedback]['status'], 'completed')
        saved = fresh.snapshot()
        again = restore(saved, self.folder / 'again', self.factory)
        self.addCleanup(again.close)
        self.assertTrue(torch.equal(fresh.native.recall_preference.bank.weights, again.native.recall_preference.bank.weights))
        self.assertEqual(int(again.native.recall_preference.bank.writes), 1)
        damaged = copy.deepcopy(saved)
        item = next(item for item in damaged['interactions']['records'] if item['request']['id'] == feedback)
        item['request']['payload']['relevance'] = 1.
        item['request_sha256'] = digest(item['request'])
        with self.assertRaises(ValueError): restore(damaged, self.folder / 'forged', self.factory)

    def test_expired_credit_and_legacy_envelope_cannot_assert_new_feedback(self):
        core, human = self.prepared()
        identifier = self.published(core, human)
        core.tick(31.); core.tick(31.)
        self.assertEqual(available(core), [])
        feedback, request = self.ingest(core, human, 'recall_feedback', {'about': identifier, 'relevance': 1.})
        core.tick(.05)
        self.assertEqual(core.interactions.records[feedback]['status'], 'failed')
        self.assertEqual(int(core.native.recall_preference.bank.writes), 0)
        request['format'] = 6
        with self.assertRaises(ValueError): validate_request(request)

    def test_background_perception_does_not_starve_expression_but_content_loss_revises(self):
        core, human = self.prepared()
        self.configure(delay=.3)
        identifier, _ = self.talk(core, human, 'Vamos conversar sobre maruvi.', wait=False)
        self.until(core, lambda: any(job['status'] == 'parsing' for job in core.dialogues.jobs.values()))
        self.perceive(core, [('image', 80)])
        self.perceive(core, [('image', 50)])
        self.until(core, lambda: core.interactions.records[identifier]['status'] in ('completed', 'failed'))
        self.assertEqual(core.interactions.records[identifier]['status'], 'completed')
        self.assertEqual(next(iter(core.dialogues.jobs.values()))['revisions'], 0)
        second, _ = self.talk(core, human, 'Quem fez maruvi?', wait=False)
        self.until(core, lambda: any(job['status'] == 'parsing' for job in core.dialogues.jobs.values()))
        for number in (2, 4): core.native.moments.bank(number).outputs.zero_()
        self.until(core, lambda: core.interactions.records[second]['status'] in ('completed', 'failed'))
        self.assertEqual(core.interactions.records[second]['status'], 'completed')
        self.assertGreater(core.dialogues.jobs[core.interactions.records[second]['job']]['revisions'], 0)

    def test_quiet_and_content_ablation_do_not_invent_recollections(self):
        core, human = self.prepared()
        core.native.attention.configure('quiet')
        identifier, _ = self.talk(core, human, 'Vamos conversar sobre maruvi.')
        context = core.interactions.records[identifier]['result']['data']['evidence']
        self.assertNotIn('evocation', context['association'])
        self.assertEqual(available(core), [])
        core.native.attention.configure('full')
        previous = capture(core.native, 'maruvi', 'maruvi')
        for number in (2, 4): core.native.moments.bank(number).outputs.zero_()
        from scripts.alice_memory.dialogue_evocation import current
        self.assertFalse(current(core.native, previous))
        self.assertEqual(capture(core.native, 'maruvi', 'maruvi')['entries'], [])

    def test_language_receipt_stays_light_and_does_not_reveal_vectors_or_sensory_content(self):
        core, human = self.prepared()
        identifier, _ = self.talk(core, human, 'Vamos conversar sobre maruvi.')
        context = core.interactions.records[identifier]['result']['data']['evidence']
        fake = dialogue.FakeLanguage({'text': 'Tenho lembranças relacionadas.'})
        DialogueLanguage(fake).express('Vamos conversar sobre maruvi.', context)
        body = json.loads(fake.request['messages'][1]['content'])
        self.assertEqual(body['owner_context']['association']['evocation']['recalled_count'], 2)
        self.assertFalse(body['owner_context']['association']['evocation']['reference_resolved'])
        self.assertNotIn('evoked_sha256', json.dumps(body))
        child = subprocess.run([sys.executable, '-c',
            "import json,sys;from scripts.alice_memory.dialogue_language import validate_context;"
            "x=json.load(sys.stdin);validate_context(x['context'],x['question']);assert 'torch' not in sys.modules"],
            cwd=ROOT, input=json.dumps({'context': context, 'question': 'Vamos conversar sobre maruvi.'}),
            capture_output=True, text=True, timeout=20)
        self.assertEqual(child.returncode, 0, child.stderr)
        changed = copy.deepcopy(context['association']['evocation'])
        changed['credit_sha256'] = '0'*64
        with self.assertRaises(ValueError): validate_binding(core.native, changed)


if __name__ == '__main__':
    torch.set_num_threads(1)
    unittest.main()
