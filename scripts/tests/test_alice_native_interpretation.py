"""Initial/current reported meaning, explicit revisions and immutable senses."""
import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import torch
from torch.nn import functional as F

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import test_alice_word_grounding as fixtures
from scripts.alice_memory.conceptual_mind import ConceptualMind, save
from scripts.alice_memory.continuous_experiment import load_scheduler
from scripts.alice_memory.native_grounding import NativeGrounding, restore as restore_grounding
from scripts.alice_memory.native_interpretation import NativeInterpretations, NativeStatement, SlotWeights, restore
from scripts.alice_memory.native_sensor import NativeObservation
from scripts.alice_memory.online_memory import OnlineMemory
from scripts.alice_memory.persistent_runtime import close_agent
from scripts.alice_memory.runtime_store import RuntimeStore


def statement(subject='pai', sequence=0, moment=0, relation='autor', at=2., corrects=(), origin='person'):
    return NativeStatement(moment, relation, subject, hashlib.sha256(f'teacher-{sequence}'.encode()).hexdigest(), sequence, at, origin, corrects)


def packet(axis, at, sequence):
    return NativeObservation('image', F.one_hot(torch.tensor(axis), 128).float(), at, sequence, '0' * 64, origin='person')


class InterpretationContracts(unittest.TestCase):
    def setUp(self):
        self.native = NativeGrounding()
        self.addCleanup(self.native.moments.close)
        self.native.observe([packet(0, 1., 0)], 1.)
        self.native.advance(10.)

    def test_diagonal_one_hot_rls_matches_dense_updates_and_untouched_queries(self):
        sparse = SlotWeights(4)
        dense = OnlineMemory(4, 64)
        generator = torch.Generator().manual_seed(71)
        for slot in (0, 2, 0, 1, 2, 3):
            target = torch.randn(64, generator=generator, dtype=torch.float64) * .1
            key = F.one_hot(torch.tensor(slot), 4).double()
            sparse.write(slot, target)
            dense.write(key, target, strength=10.)
            self.assertTrue(torch.allclose(sparse.weights.T, dense.weights, atol=1e-10, rtol=0))
            self.assertTrue(torch.allclose(sparse.precision, dense.precision.diag(), atol=1e-10, rtol=0))
            for address in range(4):
                cue = F.one_hot(torch.tensor(address), 4).double()
                self.assertTrue(torch.allclose(sparse.weights[address], dense.weights @ cue, atol=1e-10, rtol=0))

    def test_father_to_mother_correction_preserves_initial_sources_and_perception(self):
        sensory = self.native.moments.snapshot()
        working = self.native.working.clone()
        self.assertFalse(self.native.interpret(0, 'autor')['supported'])
        first = self.native.teach_interpretation(statement())
        self.assertEqual(self.native.interpret(0, 'autor')['subject'], 'pai')
        revised = self.native.teach_interpretation(statement('mae', 1, at=3., corrects=(first['version'],)))
        self.assertEqual(self.native.interpret(0, 'autor')['subject'], 'mae')
        initial = self.native.interpret(0, 'autor', 'initial')
        self.assertEqual(initial['subject'], 'pai')
        self.assertEqual(initial['sources'][0]['acquired_at'], 2.)
        self.assertEqual(self.native.interpret(0, 'autor')['sources'][0]['acquired_at'], 3.)
        self.assertEqual(revised['corrected'], [0])
        self.assertFalse(initial['directly_observed'])
        self.assertEqual(self.native.moments.traces, sensory['traces'])
        self.assertTrue(torch.equal(self.native.moments.routes, sensory['routes']))
        self.assertTrue(torch.equal(self.native.working, working))
        self.assertEqual(self.native.observations, 1)

    def test_conflicting_statements_stay_ambiguous_until_explicit_correction(self):
        self.native.teach_interpretation(statement())
        self.native.teach_interpretation(statement('mae', 1, at=3.))
        conflict = self.native.interpret(0, 'autor')
        self.assertEqual(conflict['reason'], 'conflicting_statements')
        self.assertIsNone(conflict['subject'])
        self.assertEqual(conflict['versions'], [0, 1])
        self.native.teach_interpretation(statement('tio', 2, at=4., corrects=(0, 1)))
        self.assertEqual(self.native.interpret(0, 'autor')['subject'], 'tio')
        self.assertEqual(self.native.interpret(0, 'autor', 'initial')['subject'], 'pai')

    def test_same_report_consensus_and_partial_correction_preserve_other_active_claims(self):
        self.native.teach_interpretation(statement())
        self.native.teach_interpretation(statement('pai', 1, at=3.))
        self.assertEqual(self.native.interpret(0, 'autor')['versions'], [0, 1])
        self.assertEqual(self.native.interpret(0, 'autor')['subject'], 'pai')
        self.native.teach_interpretation(statement('mae', 2, at=4., corrects=(1,)))
        self.assertEqual(self.native.interpret(0, 'autor')['reason'], 'conflicting_statements')
        self.assertEqual(self.native.interpret(0, 'autor')['versions'], [0, 2])

    def test_new_meaning_lives_in_weights_not_provenance_and_erasure_or_swapping_changes_it(self):
        self.native.teach_interpretation(statement())
        self.native.teach_interpretation(statement('mae', 1, at=3., corrects=(0,)))
        encoded = json.dumps(self.native.interpretations.records)
        self.assertNotIn('pai', encoded)
        self.assertNotIn('mae', encoded)
        bank = self.native.interpretations.bank
        bank.weights[[0, 1]] = bank.weights[[1, 0]]
        self.assertEqual(self.native.interpret(0, 'autor')['subject'], 'pai')
        self.assertEqual(self.native.interpret(0, 'autor', 'initial')['subject'], 'mae')
        bank.weights.zero_()
        self.assertFalse(self.native.interpret(0, 'autor')['supported'])
        self.assertFalse(self.native.interpret(0, 'autor', 'initial')['supported'])

    def test_other_moment_and_other_relation_are_not_rewritten(self):
        self.native.observe([packet(1, 10., 1)], 10.)
        self.native.teach_interpretation(statement('colega', 0, moment=1, at=10.))
        self.native.teach_interpretation(statement('pai', 1, at=10.))
        self.native.teach_interpretation(statement('boa', 2, relation='impressao', at=10.))
        self.native.teach_interpretation(statement('mae', 3, at=10., corrects=(1,)))
        self.assertEqual(self.native.interpret(1, 'autor')['subject'], 'colega')
        self.assertEqual(self.native.interpret(0, 'impressao')['subject'], 'boa')
        self.assertEqual(self.native.interpret(0, 'autor')['subject'], 'mae')

    def test_bad_stale_cross_moment_or_self_updates_leave_prior_state(self):
        self.native.teach_interpretation(statement())
        self.native.teach_interpretation(statement('mae', 1, at=3., corrects=(0,)))
        before = self.native.interpretations.snapshot()
        for bad in (statement('tio', 2, at=4., corrects=(0,)), statement('tio', 2, moment=1, at=4.),
                    statement('tio', 2, at=.5), statement('tio', 2, at=2.), statement('tio', 2, relation='local', at=4., corrects=(1,))):
            with self.assertRaises(ValueError):
                self.native.teach_interpretation(bad)
        self.assertFalse(self.native.teach_interpretation(statement('tio', 1, at=4.))['learned'])
        self.assertFalse(self.native.teach_interpretation(statement('tio', 2, at=4., origin='self'))['learned'])
        self.assertEqual(self.native.interpretations.records, before['records'])
        self.assertTrue(torch.equal(self.native.interpretations.bank.weights, before['bank']['weights']))

    def test_capacity_rejects_new_version_without_erasing_old(self):
        self.native.interpretations = NativeInterpretations(capacity=1)
        self.native.teach_interpretation(statement())
        with self.assertRaises(ValueError):
            self.native.teach_interpretation(statement('mae', 1, at=3., corrects=(0,)))
        self.assertEqual(self.native.interpret(0, 'autor')['subject'], 'pai')

    def test_restore_preserves_versions_and_refuses_bad_lineage_hidden_rows_and_nan(self):
        self.native.teach_interpretation(statement())
        self.native.teach_interpretation(statement('mae', 1, at=3., corrects=(0,)))
        payload = self.native.interpretations.snapshot()
        resumed = restore(payload, self.native.moments, self.native.clock)
        self.assertEqual(resumed.query(0, 'autor')['subject'], 'mae')
        self.assertEqual(resumed.query(0, 'autor', 'initial')['subject'], 'pai')
        damaged = copy.deepcopy(payload)
        damaged['records'][1]['corrects'] = [1]
        with self.assertRaises(ValueError):
            restore(damaged, self.native.moments, self.native.clock)
        for alteration in ('nan', 'hidden', 'unused', 'precision'):
            damaged = copy.deepcopy(payload)
            if alteration == 'nan':
                damaged['bank']['weights'][0, 0] = float('nan')
            elif alteration == 'hidden':
                damaged['bank']['weights'][50, 0] = 1.
            elif alteration == 'unused':
                damaged['bank']['weights'][0, 50] = 1.
            else:
                damaged['bank']['precision'][0] = 1000.
            with self.assertRaises(ValueError):
                restore(damaged, self.native.moments, self.native.clock)

    def test_legacy_grounding_does_not_invent_interpretations(self):
        self.native.teach_interpretation(statement())
        payload = self.native.snapshot()
        payload['format'] = 2
        payload.pop('interpretations')
        payload.pop('dynamics')
        payload.pop('attention')
        payload.pop('received_observations')
        payload.pop('links')
        payload.pop('naming_proofs')
        resumed = restore_grounding(payload, self.native.clock)
        self.addCleanup(resumed.moments.close)
        self.assertFalse(resumed.interpret(0, 'autor')['supported'])
        self.assertEqual(resumed.observations, self.native.observations)


class InterpretationIntegrationContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.WrittenGroundingTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        fixtures.WrittenGroundingTests.tearDownClass()

    def test_shared_owner_portable_and_paged_restart_preserve_revised_meaning_without_model(self):
        fixture = fixtures.WrittenGroundingTests()
        self.addCleanup(fixture.doCleanups)
        core = ConceptualMind(fixture.fixture(False))
        self.addCleanup(core.close)
        at = core.clock + .1
        core.perceive_native([packet(0, at, 0)], .1)
        core.teach_native_interpretation(statement(at=at))
        core.tick(.1)
        core.teach_native_interpretation(statement('mae', 1, at=core.clock, corrects=(0,)))
        temporary = tempfile.TemporaryDirectory(dir=ROOT / 'bin')
        self.addCleanup(temporary.cleanup)
        folder = Path(temporary.name)
        portable = folder / 'portable.pt'
        save(portable, core)
        self.assertEqual(torch.load(portable, weights_only=True)['format'], 57)
        with RuntimeStore(folder / 'runtime') as store:
            store.submit(store.capture(core), core.clock)
            self.assertEqual(store.finish()['status'], 'committed')
            paged = store.candidates()[0][0]
            self.assertEqual(torch.load(paged, weights_only=True)['format'], 58)
        code = '''
import sys
from pathlib import Path
from scripts.alice_memory.continuous_experiment import load_scheduler
from scripts.alice_memory.persistent_runtime import close_agent
for path in sys.argv[1:]:
    a,m,_=load_scheduler(Path(path),worker_factory=lambda op: (_ for _ in ()).throw(AssertionError('No model')))
    try:
        assert a.native.interpret(0,'autor')['subject']=='mae'
        assert a.native.interpret(0,'autor','initial')['subject']=='pai'
        assert a.native.observations==1
        assert len(a.native.moments.traces)==1
    finally:close_agent(a,m)
'''
        child = subprocess.run([sys.executable, '-c', code, str(portable), str(paged)], cwd=ROOT, text=True, capture_output=True, timeout=45)
        self.assertEqual(child.returncode, 0, child.stderr)


if __name__ == '__main__':
    unittest.main()
