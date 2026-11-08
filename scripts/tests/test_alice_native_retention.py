"""Bounded episodic retention with persistent learning and lifetime provenance."""
import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import torch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from scripts.alice_memory.native_grounding import NativeGrounding, restore as restore_grounding
from scripts.alice_memory.native_moments import NativeMoments, restore as restore_moments
from scripts.alice_memory.native_interpretation import NativeStatement
from scripts.alice_memory.native_query import signature
from scripts.alice_memory.native_stream import restore as restore_stream
from scripts.alice_memory.native_statement_language import parts as statement_parts
from scripts.alice_memory.runtime_store import RuntimeStore
from scripts.alice_memory.continuous_experiment import load_scheduler
from scripts.alice_memory.persistent_runtime import close_agent
from scripts.alice_memory.grounded_mind import WrittenName
from test_alice_native_moments import packet
import test_alice_native_stream as stream_fixtures


def small_archive(native, capacity=2):
    native.moments.close()
    native.moments = NativeMoments(capacity, 1)


class RetentionContracts(unittest.TestCase):
    def setUp(self):
        torch.set_num_threads(1)
        self.native = NativeGrounding()
        self.addCleanup(self.native.moments.close)
        small_archive(self.native)
        self.addCleanup(self.native.moments.close)

    def observe(self, axis, at, sequence):
        return self.native.observe([packet(axis=axis, at=at, sequence=sequence)], at)

    def test_full_archive_keeps_learning_predicting_and_does_not_reuse_an_identity(self):
        for index in range(8):
            self.assertEqual(self.observe(index, float(index + 1), index)['moment'], index)
        memory = self.native.moments
        self.assertEqual([trace['id'] for trace in memory.traces], [6, 7])
        self.assertEqual(memory.next_id, 8)
        self.assertEqual(memory.total_observations, 8)
        self.assertEqual(self.native.observations, 8)
        self.assertEqual(self.native.dynamics.frames, 8)
        self.assertEqual(self.native.dynamics.pairs, 7)
        self.assertEqual(memory.connection.execute('SELECT id FROM moments ORDER BY id').fetchall(), [(6,), (7,)])
        self.assertIsNone(memory.get(0))
        self.assertFalse(memory.recall([packet(axis=0)], 9.)['supported'])
        self.assertEqual(memory.recall([packet(axis=6)], 9.)['moment']['id'], 6)
        self.assertEqual(list(memory.cache), [6])

    def test_reactivation_can_preserve_an_old_episode_over_a_cold_one(self):
        self.observe(0, 1., 0)
        self.observe(1, 2., 1)
        memory = self.native.moments
        self.assertTrue(memory.recall([packet(axis=0)], 1000.)['supported'])
        self.native.advance(1000.)
        self.observe(2, 1001., 2)
        self.assertEqual([trace['id'] for trace in memory.traces], [0, 2])
        self.assertIsNone(memory.get(1))

    def test_failed_replacement_rolls_back_sql_routes_counters_and_old_recollection(self):
        self.observe(0, 1., 0)
        self.observe(1, 2., 1)
        before = self.native.moments.snapshot()
        with patch('scripts.alice_memory.native_moments.MAX_ARCHIVE', 1):
            with self.assertRaises(ValueError):
                self.native.moments.capture([packet(axis=2, at=3., sequence=2)], 3.)
        after = self.native.moments.snapshot()
        self.assertEqual(after['traces'], before['traces'])
        self.assertEqual(after['next_id'], before['next_id'])
        self.assertTrue(torch.equal(after['routes'], before['routes']))
        self.assertTrue(self.native.moments.recall([packet(axis=0)], 3.)['supported'])

    def test_learned_name_survives_its_training_episode_without_recreating_that_episode(self):
        self.observe(0, 1., 0)
        self.native.teach(WrittenName('nivo', 1., 0), 1.)
        self.observe(1, 2., 1)
        self.observe(2, 3., 2)
        meaning = self.native.evoke('nivo', 'image')
        self.assertTrue(meaning['supported'])
        self.assertIsNone(self.native.moments.get(0))
        self.assertFalse(self.native.recall_moments([packet(axis=0)])['supported'])
        resumed = restore_grounding(self.native.snapshot(), 3.)
        self.addCleanup(resumed.moments.close)
        self.assertTrue(resumed.evoke('nivo', 'image')['supported'])
        self.assertEqual(resumed.moments.next_id, 3)
        self.assertEqual(resumed.dynamics.frames, 3)

    def test_report_and_correction_keep_original_witness_after_sensory_forgetting(self):
        self.observe(0, 1., 0)
        self.native.teach_interpretation(NativeStatement(0, 'autor', 'pai', 'a' * 64, 0, 1.))
        original = self.native.moments.reference(0)
        self.observe(1, 2., 1)
        self.observe(2, 3., 2)
        self.native.teach_interpretation(NativeStatement(0, 'autor', 'mae', 'b' * 64, 1, 3., corrects=(0,)))
        self.assertEqual(self.native.interpret(0, 'autor')['subject'], 'mae')
        self.assertEqual(self.native.interpret(0, 'autor', 'initial')['subject'], 'pai')
        self.assertFalse(self.native.interpret(2, 'autor')['supported'])
        self.assertEqual(self.native.interpretations.records[1]['moment_ref'], original)
        resumed = restore_grounding(self.native.snapshot(), 3.)
        self.addCleanup(resumed.moments.close)
        self.assertEqual(resumed.interpret(0, 'autor')['subject'], 'mae')
        self.assertIsNone(resumed.moments.get(0))
        damaged = self.native.snapshot()
        damaged['interpretations']['records'][1]['moment_ref']['id'] = 2
        with self.assertRaises(ValueError):
            restore_grounding(damaged, 3.)

    def test_sparse_identity_restore_and_invalid_lifetime_counters(self):
        for index in range(4):
            self.observe(index, float(index + 1), index)
        payload = self.native.moments.snapshot()
        resumed = restore_moments(payload, 4.)
        self.addCleanup(resumed.close)
        self.assertEqual(resumed.recall([packet(axis=2)], 5.)['moment']['id'], 2)
        for field, value in (('next_id', 2), ('total_observations', 2)):
            broken = copy.deepcopy(payload)
            broken[field] = value
            with self.assertRaises(ValueError):
                restore_moments(broken, 4.)
        broken = copy.deepcopy(payload)
        broken['traces'][0]['id'] = 0  # Same physical row cannot rename its SQL bank.
        with self.assertRaises(ValueError):
            restore_moments(broken, 4.)

    def test_legacy_portable_archive_migrates_counts_without_inventing_experiences(self):
        self.observe(0, 1., 0)
        payload = self.native.moments.snapshot()
        payload['format'] = 1
        payload.pop('next_id')
        payload.pop('total_observations')
        payload.pop('values')
        for trace in payload['traces']:
            trace.pop('impact')
        resumed = restore_moments(payload, 1.)
        self.addCleanup(resumed.close)
        self.assertEqual((resumed.next_id, resumed.total_observations), (1, 1))
        self.assertTrue(resumed.recall([packet()], 2.)['supported'])

    def test_query_signature_detects_eviction_even_for_identical_content(self):
        self.observe(0, 1., 0)
        self.observe(0, 2., 1)
        plan = {'window_fragment': None, 'basis': 'relative'}
        before = signature(self.native, plan)
        self.observe(0, 3., 2)
        self.assertNotEqual(before, signature(self.native, plan))

    def test_literal_language_addresses_lifetime_ids_beyond_retained_capacity(self):
        plan = statement_parts('No momento 999999, associe "autor" a "mae".')
        self.assertFalse(plan['uncertain'])
        self.assertEqual(plan['moment'], 999999)
        self.assertTrue(statement_parts('No momento 1000000, associe "autor" a "mae".')['uncertain'])


class RetentionIntegrationContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stream_fixtures.StreamContracts.setUpClass()

    @classmethod
    def tearDownClass(cls):
        stream_fixtures.StreamContracts.tearDownClass()

    def test_unacknowledged_completion_survives_eviction_and_paged_restart_without_replay(self):
        helper = stream_fixtures.StreamContracts()
        helper.setUp()
        self.addCleanup(helper.doCleanups)
        agent = helper.core()
        small_archive(agent.native, 1)
        number = helper.submit(agent, name=None)
        helper.until(agent, lambda: helper.finished(agent, number))
        job = agent.native_stream.jobs[number]
        self.assertEqual(job['status'], 'completed')
        original_ref = copy.deepcopy(job['moment_ref'])
        at = agent.clock + .1
        agent.perceive_native([packet(axis=5, at=at, sequence=number + 1)], .1)
        self.assertIsNone(agent.native.moments.get(original_ref['id']))
        restored_stream = restore_stream(agent.native_stream.snapshot(), agent)
        self.assertEqual(restored_stream.jobs[number]['moment_ref'], original_ref)
        broken = agent.native_stream.snapshot()
        broken['jobs'][0]['moment_ref']['source_context']['source_sequence'] += 1
        with self.assertRaises(ValueError):
            restore_stream(broken, agent)
        with RuntimeStore(helper.folder / 'runtime') as store:
            store.submit(store.capture(agent), agent.clock)
            self.assertEqual(store.finish()['status'], 'committed')
            path = store.candidates()[0][0]
        resumed, mind, _ = load_scheduler(path)
        try:
            self.assertEqual(resumed.native.observations, 2)
            self.assertEqual(resumed.native.moments.next_id, 2)
            self.assertEqual(resumed.native_stream.jobs[number]['moment_ref'], original_ref)
            resumed.native_stream.configure(helper.inbox, helper.factory)
            self.assertFalse(resumed.native_stream.ingest(job['frame'], job['manifest'], job['received_wall']))
        finally:
            close_agent(resumed, mind)

    def test_page_collection_preserves_both_recovery_generations_after_replacement(self):
        helper = stream_fixtures.StreamContracts()
        helper.setUp()
        self.addCleanup(helper.doCleanups)
        agent = helper.core()
        small_archive(agent.native, 1)
        with RuntimeStore(helper.folder / 'runtime') as store:
            first_page = None
            for index in range(3):
                at = agent.clock + .1
                agent.perceive_native([packet(axis=index, at=at, sequence=index)], .1)
                pending = store.capture(agent)
                if first_page is None:
                    first_page = store.root / 'native-pages' / (pending.payload['native']['moments']['pages'][0]['sha256'] + '.page')
                store.submit(pending, agent.clock)
                self.assertEqual(store.finish()['status'], 'committed')
                if index == 1:
                    self.assertTrue(first_page.exists(), 'Previous recovery generation lost its sensory bank.')
            self.assertFalse(first_page.exists(), 'Unused owned page survived beyond both recovery generations.')
            for index, (path, _) in enumerate(store.candidates()):
                resumed, mind, _ = load_scheduler(path)
                try:
                    self.assertEqual([trace['id'] for trace in resumed.native.moments.traces], [2 - index])
                    self.assertTrue(resumed.native.recall_moments([packet(axis=2 - index)])['supported'])
                finally:
                    close_agent(resumed, mind)


if __name__ == '__main__':
    unittest.main()
