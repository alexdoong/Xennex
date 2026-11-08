"""Versioned percepts, weight-only names, cross-modal recall and integration."""
import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

import torch
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from scripts.alice_memory.conceptual_mind import ConceptualMind, save
from scripts.alice_memory.continuous_experiment import load_scheduler
from scripts.alice_memory.grounded_mind import WrittenName
from scripts.alice_memory.language import AdmissionDeferred
from scripts.alice_memory.native_encoder import NativeEncoder, verify_model
from scripts.alice_memory.native_batch import validate_receipt
from scripts.alice_memory.native_grounding import NativeGrounding, restore
from scripts.alice_memory.native_sensor import NativeObservation, REPRESENTATION
from scripts.alice_memory.persistent_runtime import close_agent
import test_alice_word_grounding as fixtures


def packet(modality='image', axis=0, time=1., sequence=0, origin='environment'):
    latent = torch.nn.functional.one_hot(torch.tensor(axis), 128).float()
    return NativeObservation(modality, latent, time, sequence, hashlib.sha256((modality + str(axis)).encode()).hexdigest(), origin=origin)


class NativeAssociationContracts(unittest.TestCase):
    def taught(self):
        memory = NativeGrounding()
        for sequence, name in enumerate(('nivo', 'tazi', 'lendo')):
            now = float(sequence + 1)
            memory.observe([packet(axis=sequence, time=now, sequence=sequence),
                            packet('audio', sequence + 3, now, sequence)], now)
            self.assertTrue(memory.teach(WrittenName(name, now, sequence), now)['learned'])
        return memory

    def test_named_associations_use_weights_and_cross_modal_values_without_raw_history(self):
        memory = self.taught()
        for index, name in enumerate(memory.names):
            visual = packet(axis=index)
            self.assertEqual(memory.recognize(visual)['name'], name)
            recalled = memory.cross(visual, 'audio')
            self.assertTrue(recalled['supported'])
            self.assertTrue(torch.equal(recalled['latent'], packet('audio', index + 3).latent))
            self.assertFalse(recalled['autobiographical_write'])
        self.assertNotIn('latent', json.dumps(memory.sources))
        memory.readers['image'].weights.zero_()
        self.assertFalse(memory.recognize(packet())['supported'])

    def test_unknown_region_and_unseen_target_modality_abstain(self):
        memory = self.taught()
        self.assertFalse(memory.recognize(packet(axis=100))['supported'])
        self.assertFalse(memory.evoke('unknown', 'image')['supported'])
        self.assertFalse(memory.evoke('nivo', 'text')['supported'])
        self.assertFalse(NativeGrounding().recognize(packet())['supported'])

    def test_self_generated_stale_and_unsynchronized_inputs_do_not_teach(self):
        memory = NativeGrounding()
        result = memory.observe([packet(origin='self')], 1.)
        self.assertEqual(result['encoded'], 0)
        memory.observe([packet()], 1.)
        self.assertFalse(memory.teach(WrittenName('nivo', 1., 0, 'self', 1), 1.)['learned'])
        self.assertFalse(memory.teach(WrittenName('nivo', .5, 0), 1.)['learned'])
        memory.advance(2.)
        self.assertFalse(memory.teach(WrittenName('nivo', 1., 0), 2.)['learned'])
        self.assertEqual(memory.observe([packet()], 2.)['encoded'], 0)
        self.assertFalse(memory.sources)

    def test_frame_and_representation_validation_precede_changes(self):
        memory = NativeGrounding()
        invalid = packet()
        object.__setattr__(invalid, 'representation', 'other-encoder')
        with self.assertRaises(ValueError):
            memory.observe([invalid], 1.)
        with self.assertRaises(ValueError):
            memory.observe([packet(), packet('audio', time=1.1)], 2.)
        self.assertEqual(memory.observations, 0)
        self.assertEqual(memory.clock, 0.)

    def test_native_snapshot_restores_weights_provenance_active_frame_and_detaches_tensors(self):
        memory = self.taught()
        snapshot = memory.snapshot()
        resumed = restore(snapshot, 3.)
        self.assertEqual(resumed.recognize(packet())['name'], 'nivo')
        self.assertTrue(torch.equal(resumed.cross(packet(), 'audio')['latent'], packet('audio', 3).latent))
        memory.active['packets'][0].latent.zero_()
        self.assertEqual(snapshot['active']['packets'][0]['latent'].norm(), 1.)
        for field, value in (('representation', 'different'), ('observations', -1), ('label_sequence', {})):
            damaged = copy.deepcopy(snapshot)
            damaged[field] = value
            with self.assertRaises(ValueError):
                restore(damaged, 3.)
        damaged = copy.deepcopy(snapshot)
        damaged['readers']['image']['writes'] += 1
        with self.assertRaises(ValueError):
            restore(damaged, 3.)

    def test_failed_second_modality_update_keeps_all_banks_and_name_registry(self):
        memory = NativeGrounding()
        memory.observe([packet(), packet('audio', 3)], 1.)
        from scripts.alice_memory.online_memory import OnlineMemory
        original = OnlineMemory.write
        calls = []
        def fail(bank, *args, **kwargs):
            calls.append(bank)
            if len(calls) == 3:
                raise ValueError('second channel refused')
            return original(bank, *args, **kwargs)
        with patch.object(OnlineMemory, 'write', fail):
            with self.assertRaises(ValueError):
                memory.teach(WrittenName('nivo', 1., 0), 1.)
        self.assertFalse(memory.names)
        self.assertFalse(memory.sources)
        self.assertFalse(memory.active['consumed'])
        self.assertTrue(all(bank.writes == 0 for bank in (*memory.readers.values(), *memory.writers.values())))


class NativeFileContracts(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir=ROOT / 'bin')
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)
        self.encoder = NativeEncoder(self.folder)

    def test_local_pixels_and_unicode_text_are_bound_to_the_bytes_actually_read(self):
        image = self.folder / 'image.png'
        Image.new('RGB', (224, 224), 'red').save(image)
        signal, digest = self.encoder.read_signal(image, 'image')
        self.assertEqual(signal['image'].getpixel((0, 0)), (255, 0, 0))
        self.assertEqual(digest, hashlib.sha256(image.read_bytes()).hexdigest())
        text = self.folder / 'text.txt'
        text.write_text('Porra, um círculo vermelho.', encoding='utf-8')
        signal, digest = self.encoder.read_signal(text, 'text')
        self.assertEqual(signal, 'Porra, um círculo vermelho.')
        self.assertEqual(digest, hashlib.sha256(text.read_bytes()).hexdigest())

    def test_audio_stays_pcm_and_does_not_need_a_transcript(self):
        audio = self.folder / 'audio.wav'
        with wave.open(str(audio), 'wb') as stream:
            stream.setnchannels(1)
            stream.setsampwidth(2)
            stream.setframerate(16000)
            stream.writeframes(b'\0\0' * 32000)
        signal, digest = self.encoder.read_signal(audio, 'audio')
        self.assertEqual(signal['audio'].shape, (32000,))
        self.assertEqual(digest, hashlib.sha256(audio.read_bytes()).hexdigest())
        self.assertEqual(set(signal), {'audio'})

    def test_budget_bad_mode_missing_manifest_and_no_optional_framework_import(self):
        with patch('scripts.alice_memory.native_encoder.physical_memory', return_value={'used_bytes': 80, 'total_bytes': 100}):
            with self.assertRaises(AdmissionDeferred):
                self.encoder.admit()
            NativeEncoder(self.folder, ram_fraction=.9).admit(9)
        with self.assertRaises(ValueError):
            NativeEncoder(self.folder, ram_fraction=.95)
        with self.assertRaises(ValueError):
            NativeEncoder(self.folder, mode='gpu')
        with self.assertRaises(OSError):
            verify_model(self.folder)
        result = subprocess.run([sys.executable, '-c', "import sys; import scripts.alice_memory.native_encoder; assert 'sentence_transformers' not in sys.modules"],
                                cwd=ROOT, text=True, capture_output=True, timeout=25)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_worker_receipt_binds_identity_modality_time_and_the_same_source_bytes(self):
        signals = self.folder / 'signals'
        signals.mkdir()
        path = signals / ('a' * 32 + '.txt')
        path.write_text('hello', encoding='utf-8')
        percept = packet('text')
        object.__setattr__(percept, 'sample_sha256', hashlib.sha256(path.read_bytes()).hexdigest())
        items = [{'modality': 'text', 'file': path.name, 'sequence': 0, 'acquired_at': 1., 'origin': 'environment'}]
        payload = {'format': 1, 'token': 'b' * 32, 'representation': REPRESENTATION, 'items': [vars(percept).copy()], 'resources': {}}
        self.assertEqual(len(validate_receipt(payload, items, self.folder, 'b' * 32)), 1)
        for name, value in (('modality', 'audio'), ('sequence', 1), ('acquired_at', 2.), ('origin', 'person')):
            damaged = copy.deepcopy(payload)
            damaged['items'][0][name] = value
            with self.assertRaises(ValueError):
                validate_receipt(damaged, items, self.folder, 'b' * 32)
        with self.assertRaises(ValueError):
            validate_receipt(payload, items, self.folder, 'c' * 32)
        path.write_text('changed', encoding='utf-8')
        with self.assertRaises(ValueError):
            validate_receipt(payload, items, self.folder, 'b' * 32)


class NativeMindContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.WrittenGroundingTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        fixtures.WrittenGroundingTests.tearDownClass()

    def setUp(self):
        self.fixture = fixtures.WrittenGroundingTests()
        self.addCleanup(self.fixture.doCleanups)
        self.agent = ConceptualMind(self.fixture.fixture(False))
        temporary = tempfile.TemporaryDirectory(dir=ROOT / 'bin')
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)

    def test_one_clock_and_checkpoint_restore_native_learning_without_inventing_synthetic_observations(self):
        observed = self.agent.temporal.observations
        memory = self.agent.mind.actor.session.memory
        episodes = len(memory.blocks)
        self.agent.perceive_native([packet(time=.1), packet('audio', 3, .1)], .1)
        self.assertEqual(self.agent.native.clock, self.agent.clock)
        self.assertTrue(self.agent.teach_native_name(WrittenName('nivo', .1, 0))['learned'])
        self.assertEqual(self.agent.temporal.observations, observed)
        self.assertEqual(len(memory.blocks), episodes)
        checkpoint = self.folder / 'native.pt'
        save(checkpoint, self.agent)
        resumed, mind, _ = load_scheduler(checkpoint)
        self.addCleanup(lambda: close_agent(resumed, mind))
        self.assertEqual(resumed.native.recognize(packet())['name'], 'nivo')
        self.assertTrue(torch.equal(resumed.native.cross(packet(), 'audio')['latent'], packet('audio', 3).latent))
        self.assertEqual(resumed.snapshot()['format'], 57)

    def test_invalid_native_frame_does_not_advance_the_existing_core(self):
        initial = self.agent.clock
        with self.assertRaises(ValueError):
            self.agent.perceive_native([packet(time=1.)], .1)
        self.assertEqual(self.agent.clock, initial)
        self.assertEqual(self.agent.native.observations, 0)

    def test_runtime_resumes_native_names_and_working_state_without_loading_encoder(self):
        from scripts.alice_memory.persistent_runtime import run
        self.agent.perceive_native([packet(time=.1)], .1)
        self.agent.teach_native_name(WrittenName('nivo', .1, 0))
        checkpoint, store = self.folder / 'native.pt', self.folder / 'runtime'
        save(checkpoint, self.agent)
        first = run(store, checkpoint, seconds=.2)
        second = run(store, seconds=.2)
        self.assertEqual(first['native_state']['names'], ['nivo'])
        self.assertEqual(second['native_state']['lessons'], 1)
        self.assertEqual(second['native_state']['observations'], 1)
        self.assertEqual(second['native_state']['clock'], second['clock'])
        self.assertLess(second['native_state']['working_norm'], first['native_state']['working_norm'])
        self.assertFalse(second['native_state']['live_sensor_inbox'])
        self.assertTrue(second['recovery']['resumed'])


if __name__ == '__main__':
    unittest.main()
