"""Anonymous moment learning, factor equivalence, paging and faithful history."""
import copy
import hashlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
import weakref
from pathlib import Path
from unittest.mock import patch

import torch
from torch.nn import functional as F

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from scripts.alice_memory.native_fast_weights import NativeFastWeights, restore as restore_factors
from scripts.alice_memory.native_moments import NativeMoments, cue_key, restore
from scripts.alice_memory.native_sensor import NativeObservation
from scripts.alice_memory.native_grounding import NativeGrounding, restore as restore_grounding
from scripts.alice_memory.online_memory import OnlineMemory
from scripts.alice_memory.native_encoder_worker import run as encode_worker
from scripts.alice_memory.conceptual_mind import ConceptualMind, save
from scripts.alice_memory.continuous_experiment import load_scheduler
from scripts.alice_memory.persistent_runtime import close_agent
import test_alice_word_grounding as fixtures


def packet(modality='image', axis=0, at=1., sequence=0, origin='environment'):
    latent = F.one_hot(torch.tensor(axis), 128).float()
    return NativeObservation(modality, latent, at, sequence, hashlib.sha256((modality + str(axis)).encode()).hexdigest(), origin=origin)


class FactorContracts(unittest.TestCase):
    def test_factors_match_dense_rls_after_every_write_and_for_unseen_queries(self):
        rng = torch.Generator().manual_seed(17)
        factor = NativeFastWeights()
        dense = OnlineMemory(132, 384)
        for index in range(3):
            latent = F.normalize(torch.randn(128, generator=rng), dim=0)
            cue = NativeObservation(('image', 'audio', 'text')[index], latent, 1., index, '0' * 64)
            key = cue_key(cue)
            target = torch.randn(384, generator=rng, dtype=torch.float64)
            factor.write(key, target)
            dense.write(key, target, strength=10.)
            for query in (key, torch.randn(132, generator=rng, dtype=torch.float64)):
                self.assertTrue(torch.allclose(factor.read(query), dense.weights @ query, atol=1e-9, rtol=1e-9))
                self.assertAlmostEqual(factor.variance(query), float(dense.variance(query)), places=8)
            restored = restore_factors(factor.snapshot())
            self.assertTrue(torch.equal(restored.read(key), factor.read(key)))
        with self.assertRaises(ValueError):
            factor.write(key, target)

    def test_bad_rank_nan_hidden_factor_rows_and_indefinite_covariance_are_rejected(self):
        factor = NativeFastWeights()
        factor.write(cue_key(packet()), torch.ones(384, dtype=torch.float64))
        for field, value in (('writes', 0), ('inputs', torch.full((3, 132), float('nan'), dtype=torch.float64)),
                             ('covariance', torch.ones(3, 132, dtype=torch.float64) * 100.)):
            broken = copy.deepcopy(factor.snapshot())
            broken[field] = value
            with self.assertRaises(ValueError):
                restore_factors(broken)
        broken = factor.snapshot()
        broken['outputs'][2, 0] = 1.
        with self.assertRaises(ValueError):
            restore_factors(broken)


class MomentContracts(unittest.TestCase):
    def archive(self, capacity=16, hot_limit=2):
        value = NativeMoments(capacity, hot_limit)
        self.addCleanup(value.close)
        return value

    def test_frame_without_name_learns_cross_modal_episode_in_weights(self):
        memory = self.archive()
        first = packet('image', 0)
        sound = packet('audio', 3)
        memory.capture([first, sound], 1.)
        result = memory.recall([first], 2., targets=['audio'])
        self.assertTrue(result['supported'])
        self.assertTrue(torch.equal(result['representations']['audio'], sound.latent))
        self.assertFalse(result['autobiographical_write'])
        self.assertEqual(result['moment']['acquired_at'], 1.)
        self.assertEqual(result['moment']['recalls'], 1)
        memory.bank(0).outputs.zero_()
        self.assertFalse(memory.recall([first], 3., targets=['audio'])['supported'])

    def test_identical_content_at_two_times_remains_ambiguous_until_temporal_cue(self):
        memory = self.archive()
        memory.capture([packet(), packet('audio', 3)], 1.)
        memory.capture([packet(at=10., sequence=1), packet('audio', 3, 10., 1)], 10.)
        result = memory.recall([packet()], 20., targets=['audio'])
        self.assertFalse(result['supported'])
        self.assertEqual(result['reason'], 'ambiguous_moments')
        older = memory.recall([packet()], 20., window=[.5, 1.5], targets=['audio'])
        newer = memory.recall([packet()], 20., window=[9.5, 10.5], targets=['audio'])
        self.assertEqual(older['moment']['id'], 0)
        self.assertEqual(newer['moment']['id'], 1)

    def test_output_availability_does_not_silently_select_an_ambiguous_moment(self):
        memory = self.archive()
        memory.capture([packet(), packet('audio', 3)], 1.)
        memory.capture([packet(at=10., sequence=1)], 10.)
        self.assertEqual(memory.recall([packet()], 20., targets=['audio'])['reason'], 'ambiguous_moments')
        result = memory.recall([packet()], 20., window=[9., 11.], targets=['audio'])
        self.assertEqual(result['reason'], 'unobserved_target')

    def test_two_cues_disambiguate_a_shared_visual_scene_with_distinct_sounds(self):
        memory = self.archive()
        memory.capture([packet(), packet('audio', 3)], 1.)
        memory.capture([packet(at=10., sequence=1), packet('audio', 4, 10., 1)], 10.)
        result = memory.recall([packet(), packet('audio', 4)], 20.)
        self.assertTrue(result['supported'])
        self.assertEqual(result['moment']['id'], 1)

    def test_disk_pages_have_bounded_cache_and_restore_without_original_database(self):
        memory = self.archive(capacity=12, hot_limit=2)
        for index in range(8):
            memory.capture([packet(axis=index, at=float(index+1), sequence=index)], float(index+1))
        self.assertEqual(len(memory.cache), 2)
        self.assertGreater(memory.evictions, 0)
        state = memory.snapshot()
        path = memory.path
        memory.close()
        self.assertFalse(path.exists())
        resumed = restore(state, 8.)
        self.addCleanup(resumed.close)
        self.assertEqual(len(resumed.cache), 0)
        for index in range(8):
            result = resumed.recall([packet(axis=index)], 9.)
            self.assertTrue(result['supported'])
            self.assertEqual(result['moment']['id'], index)
            self.assertLessEqual(len(resumed.cache), 2)

    def test_missing_or_corrupt_cold_page_is_rejected_instead_of_fabricated(self):
        memory = self.archive(hot_limit=1)
        memory.capture([packet()], 1.)
        memory.capture([packet(axis=1, at=2., sequence=1)], 2.)
        with memory.connection:
            memory.connection.execute('UPDATE moments SET bank=? WHERE id=0', (b'corrupt',))
        with self.assertRaises(ValueError):
            memory.recall([packet()], 3.)

    def test_bad_frame_or_disk_budget_preserves_archive_and_source_state(self):
        memory = self.archive()
        with self.assertRaises(ValueError):
            memory.capture([packet(origin='self')], 1.)
        with self.assertRaises(ValueError):
            memory.capture([packet(), packet('audio', at=2.)], 2.)
        with patch('scripts.alice_memory.native_moments.MAX_ARCHIVE', 1):
            with self.assertRaises(ValueError):
                memory.capture([packet()], 1.)
        self.assertFalse(memory.traces)
        self.assertEqual(memory.connection.execute('SELECT COUNT(*) FROM moments').fetchone()[0], 0)
        self.assertFalse(memory.routes.count_nonzero())

    def test_importance_freshness_and_reactivation_are_separate_and_never_break_ambiguity(self):
        memory = self.archive()
        memory.capture([packet()], 1.)
        memory.capture([packet(at=1000., sequence=1)], 1000.)
        memory.recall([packet()], 2000., window=[0., 2.])
        result = memory.recall([packet()], 2001.)
        self.assertEqual(result['reason'], 'ambiguous_moments')
        candidates = {item['id']: item for item in result['candidates']}
        self.assertGreater(candidates[0]['importance'], candidates[1]['importance'])
        self.assertLess(candidates[0]['freshness'], candidates[1]['freshness'])
        self.assertGreater(candidates[0]['reactivation'], candidates[1]['reactivation'])
        self.assertEqual(len(memory.traces), 2)

    def test_restore_rejects_changed_routes_masks_sources_and_hidden_tail(self):
        memory = self.archive()
        memory.capture([packet()], 1.)
        original = memory.snapshot()
        for field, value in (('known', [True, True, False]), ('acquired_at', 3.), ('sources', {})):
            damaged = copy.deepcopy(original)
            damaged['traces'][0][field] = value
            with self.assertRaises(ValueError):
                restore(damaged, 1.)
        damaged = copy.deepcopy(original)
        damaged['routes'][10, 0, 0] = 1.
        with self.assertRaises(ValueError):
            restore(damaged, 1.)

    def test_external_utc_cue_selects_moment_without_rewriting_its_relative_clock(self):
        memory = self.archive()
        context = {'stream_id': 'a' * 32, 'source_sequence': 0, 'captured_wall': 1800000000., 'received_wall': 1800000001.}
        memory.capture([packet()], 1., context)
        second = {**context, 'source_sequence': 1, 'captured_wall': 1800000100., 'received_wall': 1800000101.}
        memory.capture([packet(at=2., sequence=1)], 2., second)
        result = memory.recall([packet()], 3., utc_window=[1800000099., 1800000102.])
        self.assertTrue(result['supported'])
        self.assertEqual(result['moment']['id'], 1)
        self.assertEqual(result['moment']['acquired_at'], 2.)
        self.assertEqual(result['moment']['source_context'], second)
        resumed = restore(memory.snapshot(), 3.)
        self.addCleanup(resumed.close)
        self.assertEqual(resumed.recall([packet()], 3., utc_window=[1799999999., 1800000002.])['moment']['id'], 0)


class IntegrationContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.WrittenGroundingTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        fixtures.WrittenGroundingTests.tearDownClass()

    def test_legacy_observations_are_not_reconstructed_into_fictional_moments(self):
        ground = NativeGrounding()
        self.addCleanup(ground.moments.close)
        ground.observe([packet()], 1.)
        old = ground.snapshot()
        old['format'] = 1
        old.pop('moments')
        old.pop('interpretations')
        old.pop('dynamics')
        old.pop('attention')
        old.pop('received_observations')
        old.pop('links')
        old.pop('naming_proofs')
        migrated = restore_grounding(old, 1.)
        self.addCleanup(migrated.moments.close)
        self.assertEqual(migrated.observations, 1)
        self.assertEqual(migrated.moments.pre_archive_observations, 1)
        self.assertFalse(migrated.moments.traces)

    def test_same_owner_fresh_process_preserves_anonymous_moment_without_encoder(self):
        fixture = fixtures.WrittenGroundingTests()
        self.addCleanup(fixture.doCleanups)
        agent = ConceptualMind(fixture.fixture(False))
        self.addCleanup(agent.close)
        before = agent.temporal.observations
        agent.perceive_native([packet(at=.1), packet('audio', 3, .1)], .1)
        self.assertFalse(agent.native.names)
        self.assertEqual(len(agent.native.moments.traces), 1)
        self.assertEqual(agent.temporal.observations, before)
        temporary = tempfile.TemporaryDirectory(dir=ROOT/'bin')
        self.addCleanup(temporary.cleanup)
        checkpoint = Path(temporary.name)/'anonymous.pt'
        save(checkpoint, agent)
        code="from pathlib import Path; import sys,torch; from scripts.alice_memory.continuous_experiment import load_scheduler; from scripts.alice_memory.native_sensor import NativeObservation; from scripts.alice_memory.persistent_runtime import close_agent; a,m,_=load_scheduler(Path(sys.argv[1])); p=NativeObservation('image',torch.nn.functional.one_hot(torch.tensor(0),128).float(),.1,0,'0'*64); r=a.native.recall_moments([p],targets=['audio']); assert r['supported']; assert int(r['representations']['audio'].argmax())==3; assert not a.native.names; assert 'sentence_transformers' not in sys.modules; close_agent(a,m)"
        process = subprocess.run([sys.executable,'-c',code,str(checkpoint)],cwd=ROOT,text=True,capture_output=True,timeout=45)
        self.assertEqual(process.returncode,0,process.stderr)

    def test_sequential_encoder_releases_previous_model_and_preserves_receipt_order(self):
        temporary = tempfile.TemporaryDirectory(dir=ROOT/'bin')
        self.addCleanup(temporary.cleanup)
        folder = Path(temporary.name)
        (folder/'signals').mkdir()
        items=[]
        for index, modality in enumerate(('audio','image','text')):
            filename=str(index)*32+{'image':'.png','audio':'.wav','text':'.txt'}[modality]
            (folder/'signals'/filename).write_bytes(modality.encode())
            items.append({'modality':modality,'file':filename,'sequence':index,'acquired_at':1.,'origin':'person'})
        request=folder/'request.json'
        request.write_text(json.dumps({'format':1,'token':'a'*32,'mode':'sequential','ram_fraction':.9,
                                      'model_folder':str(folder),'items':items}),encoding='utf-8')
        modes=[]
        living=weakref.WeakSet()
        case=self
        class FakeEncoder:
            def __init__(self, root, mode, fraction):
                case.assertFalse(living, 'Previous modality model remains resident.')
                living.add(self);modes.append(mode)
            def encode(self, path, modality, at, sequence, origin):
                return NativeObservation(modality, packet(axis=sequence).latent, at, sequence,
                                         hashlib.sha256(path.read_bytes()).hexdigest(),origin=origin)
        with patch('scripts.alice_memory.native_encoder_worker.NativeEncoder',FakeEncoder):
            encode_worker(request,folder/'result.pt')
        result=torch.load(folder/'result.pt',map_location='cpu',weights_only=True)
        self.assertEqual(modes,['image','audio'])
        self.assertEqual([item['modality'] for item in result['items']],['audio','image','text'])
        self.assertEqual([item['sequence'] for item in result['items']],[0,1,2])


if __name__ == '__main__':
    unittest.main()
