"""External feedback reaches attention/impact weights through the human channel."""
import copy
import sys
import unittest
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from scripts.alice_memory.conceptual_mind import restore
from scripts.alice_memory.interaction_inbox import digest, validate
from scripts.alice_memory.persistent_runtime import close_agent, native_attention_actions
from scripts.alice_memory.online_memory import OnlineMemory
import test_alice_interactions as interactions
import test_alice_native_feedback as feedback
import test_alice_word_grounding as fixtures


class FeedbackInteractionContracts(unittest.TestCase):
    setUp = feedback.FeedbackLifecycleContracts.setUp
    configure = feedback.FeedbackLifecycleContracts.configure
    factory = feedback.FeedbackLifecycleContracts.factory
    until = feedback.FeedbackLifecycleContracts.until
    core = feedback.FeedbackLifecycleContracts.core
    frame = feedback.FeedbackLifecycleContracts.frame
    decision = feedback.FeedbackLifecycleContracts.decision
    inbox = interactions.InteractionOwnerContracts.inbox
    ingest = interactions.InteractionOwnerContracts.ingest
    commits = interactions.InteractionOwnerContracts.commits
    setUpClass = classmethod(lambda cls: fixtures.WrittenGroundingTests.setUpClass())
    tearDownClass = classmethod(lambda cls: fixtures.WrittenGroundingTests.tearDownClass())

    def evaluate(self, core, inbox, action, text='Porra, gostei disso.'):
        identifier, request = self.ingest(core, inbox, 'feedback', {'text': text, 'action': action})
        self.until(core, lambda: core.interactions.records[identifier]['status'] in ('completed', 'failed'))
        return identifier, request

    def test_learning_is_bound_to_selected_action_despite_a_new_situation(self):
        for text, sign in (('Porra, gostei disso.', 1), ('Não gostei disso.', -1)):
            core = self.core(False)
            inbox = self.inbox(core)
            action = self.decision(core)
            original = copy.deepcopy(core.native.attention.pending[action])
            identifier, _ = self.ingest(core, inbox, 'feedback', {'text': text, 'action': action})
            core.tick(.05)
            self.frame(core, other=True)
            observations = core.native.observations
            self.until(core, lambda: core.interactions.records[identifier]['status'] == 'completed')
            source = core.native.attention.sources[-1]
            self.assertEqual(source['id'], action)
            self.assertEqual(source['moment_ref'], original['moment_ref'])
            values = core.native.attention.banks[original['action']].weights @ original['key']
            self.assertGreater(sign * float(values[1]), .8)
            self.assertEqual(core.native.observations, observations)
            self.assertFalse(core.native.interpretations.records)

    def test_quiet_feedback_changes_value_without_creating_a_sensory_episode(self):
        core = self.core(False)
        inbox = self.inbox(core)
        self.decision(core)
        action = self.decision(core)
        choice = core.native.attention.pending[action]
        self.assertEqual(choice['action'], 'quiet')
        observed, moments = core.native.observations, core.native.moments.next_id
        identifier, _ = self.evaluate(core, inbox, action, 'Foi agradável ficar em silêncio.')
        self.assertEqual(core.interactions.records[identifier]['status'], 'completed')
        self.assertGreater(float((core.native.attention.banks['quiet'].weights @ choice['key'])[1]), .8)
        self.assertEqual(core.interactions.records[identifier]['result']['learning']['memory_impact'], {'learned': False, 'reason': 'no_retained_attended_moment'})
        self.assertEqual((core.native.observations, core.native.moments.next_id), (observed, moments))

    def test_unknown_expired_and_uncertain_feedback_do_not_write(self):
        core = self.core(False)
        inbox = self.inbox(core)
        for action in (99999,):
            identifier, _ = self.evaluate(core, inbox, action)
            self.assertEqual(core.interactions.records[identifier]['status'], 'failed')
        action = self.decision(core)
        identifier, _ = self.evaluate(core, inbox, action, 'Gostei disso?')
        self.assertEqual(core.interactions.records[identifier]['status'], 'failed')
        core.tick(60.)
        core.tick(1.)
        identifier, _ = self.evaluate(core, inbox, action)
        self.assertEqual(core.interactions.records[identifier]['status'], 'failed')
        self.assertFalse(core.native.attention.sources)
        self.assertEqual(int(core.native.moments.values.updates.sum()), 0)

    def test_durable_replay_and_new_process_do_not_learn_a_second_time(self):
        core = self.core(False)
        inbox = self.inbox(core)
        action = self.decision(core)
        identifier, request = self.evaluate(core, inbox, action)
        core.interactions.ingest(request)
        core.tick(.05)
        fallback = self.commits(core, inbox, self.folder / 'durable')
        self.assertIsNone(core.interactions.records[identifier]['job'])
        fresh, mind, _ = interactions.load_scheduler(fallback, self.folder / 'reloaded', self.factory)
        self.addCleanup(lambda: close_agent(fresh, mind))
        fresh.interactions.ingest(request)
        fresh.tick(.05)
        self.assertEqual(len(fresh.native.attention.sources), 1)
        self.assertEqual(int(fresh.native.moments.values.updates.sum()), 1)
        self.assertEqual(fresh.interactions.records[identifier]['status'], 'completed')

    def test_pending_feedback_resumes_with_its_original_action(self):
        core = self.core(False)
        inbox = self.inbox(core)
        action = self.decision(core)
        identifier, _ = self.ingest(core, inbox, 'feedback', {'text': 'Gostei disso.', 'action': action})
        core.tick(.05)
        state = core.snapshot()
        core.close()
        fresh = restore(state, self.folder / 'pending', self.factory)
        self.addCleanup(fresh.close)
        self.until(fresh, lambda: fresh.interactions.records[identifier]['status'] == 'completed')
        self.assertEqual(fresh.native.attention.sources[-1]['id'], action)
        self.assertEqual(len(fresh.native.attention.sources), 1)

    def test_completed_provenance_is_checked_after_the_cognitive_job_is_released(self):
        core = self.core(False)
        inbox = self.inbox(core)
        action = self.decision(core)
        self.evaluate(core, inbox, action)
        self.commits(core, inbox, self.folder / 'confirmed')
        state = core.snapshot()
        for key, changed in (('action', action + 1), ('text', 'Não gostei disso.')):
            bad = copy.deepcopy(state)
            item = bad['interactions']['records'][-1]
            item['request']['payload'][key] = changed
            item['request_sha256'] = digest(item['request'])
            with self.assertRaises(ValueError): restore(bad, self.folder / ('tamper-' + key), self.factory)
        bad = copy.deepcopy(state)
        bad['interactions']['format'] = 4
        with self.assertRaises(ValueError): restore(bad, self.folder / 'downgrade', self.factory)

    def test_queue_backpressure_and_status_expose_only_eligible_choices(self):
        core = self.core(False)
        inbox = self.inbox(core)
        actions = [self.decision(core) for _ in range(5)]
        numbers = [core.submit_native_feedback('Gostei disso.', action) for action in actions[:4]]
        self.assertEqual([item['id'] for item in native_attention_actions(core)], [actions[4]])
        identifier, _ = self.ingest(core, inbox, 'feedback', {'text': 'Gostei disso.', 'action': actions[4]})
        self.assertEqual(core.interactions.records[identifier]['status'], 'queued')
        self.until(core, lambda: core.native_feedbacks.jobs[numbers[0]]['status'] in core.native_feedbacks.terminal)
        core.take_native_feedback(numbers[0])
        self.until(core, lambda: core.interactions.records[identifier]['status'] == 'completed')
        core.tick(60.)
        core.tick(1.)
        self.assertFalse(native_attention_actions(core))

    def test_feedback_history_changes_the_choice_with_the_same_current_input(self):
        for preferred in ('image', 'quiet'):
            core = self.core(False)
            inbox = self.inbox(core)
            for index in range(6):
                action = self.decision(core)
                chosen = core.native.attention.pending[action]['action']
                message = 'Gostei disso.' if chosen == preferred else 'Não gostei disso.'
                identifier, _ = self.evaluate(core, inbox, action, message)
                self.assertEqual(core.interactions.records[identifier]['status'], 'completed')
                self.commits(core, inbox, self.folder / ('history-' + preferred + str(index)))
            action = self.decision(core)
            self.assertEqual(core.native.attention.pending[action]['action'], preferred)
            if preferred == 'quiet':
                for bank in core.native.attention.banks.values():
                    bank.weights.zero_()
                action = self.decision(core)
                self.assertEqual(core.native.attention.pending[action]['action'], 'image')


if __name__ == '__main__':
    unittest.main()
