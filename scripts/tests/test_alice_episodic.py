"""Sensory episode formation, directed revisions, memory causality and persistence."""
from __future__ import annotations

import copy
import json
import random
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import torch
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.alice_memory.contracts import Observation
from scripts.alice_memory.episodic_experiment import create, drive, meals, packets, partial_queries, revision_benchmark
from scripts.alice_memory.episodic_memory import EpisodicMemory
from scripts.alice_memory.episodic_session import EpisodicSession, load, save
from scripts.alice_memory.experience_perception import semantic
from scripts.alice_memory.experience_signals import samples, stories
from scripts.alice_memory.memory_action_experiment import evaluate as evaluate_actions
from scripts.alice_memory.memory_actor import MemoryActor, RecallPolicy, load as load_actor, save as save_actor, train
from scripts.alice_memory.process_metrics import Budget
from scripts.alice_memory.episodic_language import extract as extract_language, read_bundle


class EpisodicTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture = ROOT / "bin" / "AliceEpisodicTests"
        fixture.mkdir(parents=True, exist_ok=True)
        cls.directory = tempfile.TemporaryDirectory(dir=fixture)
        cls.folder = Path(cls.directory.name)
        cls.template, cls.perception_report = create(17, Budget(100000, 120))
        cls.policy = RecallPolicy()
        train(cls.policy, 1017, Budget(100000, 120))

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def session(self, capacity=64):
        return EpisodicSession(self.template.perception, self.template.boundary, EpisodicMemory(capacity))

    def assert_state_equal(self, left, right):
        self.assertEqual(left.memory.metadata(), right.memory.metadata())
        for key, value in left.snapshot().items():
            actual = right.snapshot()[key]
            if isinstance(value, torch.Tensor):
                self.assertTrue(torch.equal(value, actual), key)
            else:
                self.assertEqual(value, actual, key)
        for key, value in left.memory.state_dict().items():
            self.assertTrue(torch.equal(value, right.memory.state_dict()[key]), key)

    def test_new_combinations_and_missing_sensor_regions_are_recognized(self):
        for modality in ("image", "audio"):
            score = self.perception_report["perception"][modality]
            self.assertGreaterEqual(score["known_field_recall"], .9)
            self.assertLessEqual(score["false_known_on_missing"], .05)
            self.assertGreater(score["latent_variance"], .005)

    def test_event_boundaries_do_not_receive_oracle_annotations(self):
        records = stories(4017, 24)
        original, altered = self.session(), self.session()
        score = drive(original, records)
        self.assertGreaterEqual(score["f1"], .85)
        changed = [{**record, "truth": (3, 3, 3, 3), "episode": 999, "boundary": False} for record in records]
        drive(altered, changed)
        self.assert_state_equal(original, altered)

    def test_partial_image_and_audio_recover_missing_attributes_without_false_clues(self):
        session = self.session()
        records = stories(4017, 24)
        drive(session, records)
        result = partial_queries(session, records, 5017)
        for modality in ("image", "audio"):
            self.assertGreaterEqual(result[modality]["complete_recall"], .9)
            self.assertLessEqual(result[modality]["false_recall"], .05)

    def test_repeated_meals_have_distinct_times_and_directed_corrections(self):
        result = revision_benchmark(self.template, 7017, 32)
        self.assertGreaterEqual(result["directed_corrections_preserved"], .95)
        self.assertGreaterEqual(result["ambiguous_identical_meals_abstained"], .95)

    def test_language_evidence_comes_from_recalled_weights_and_preserves_interpretations(self):
        session = self.session()
        meal = meals(session, 6017)
        checkpoint, image = self.folder / "language.pt", self.folder / "language-cue.png"
        save(checkpoint, session)
        values = (meal["cue_image"].permute(1, 2, 0) * 255).round().to(torch.uint8)
        Image.frombytes("RGB", (32, 32), bytes(values.flatten().tolist())).save(image)
        before = checkpoint.read_bytes()
        bundle = extract_language(checkpoint, image, meal["window"])
        evidence = {item["interpretation"]: dict(item["attributes"]) for item in bundle["evidence"]}
        self.assertEqual(evidence["initial"]["autor"], "pai")
        self.assertEqual(evidence["current"]["autor"], "mae")
        self.assertTrue(bundle["unwindowed_ambiguous"])
        self.assertEqual(bundle["unwindowed_evidence"], [])
        self.assertFalse(bundle["confidence_is_calibrated"])
        self.assertEqual(before, checkpoint.read_bytes())
        path = self.folder / "language-evidence.json"
        path.write_text(json.dumps(bundle), encoding="utf-8")
        self.assertEqual(len(read_bundle(path)["evidence"]), 2)
        for block in session.memory.blocks:
            for bank in block.banks:
                bank.weights.zero_()
        save(checkpoint, session)
        self.assertEqual(extract_language(checkpoint, image, meal["window"])["evidence"], [])

    def test_ambiguous_target_and_uncertain_evidence_do_not_change_belief(self):
        session = self.session()
        result = meals(session, 6017)
        before = {key: value.clone() for key, value in session.memory.state_dict().items()}
        cue = packets(result["cue_image"], result["cue_audio"], session.clock, 0)
        blank_image, blank_audio = samples((0, 0, 0, 0), random.Random(53), (False,) * 4)
        evidence = packets(blank_image, blank_audio, session.clock + .2, 2, "audio")
        rejected = session.revise(cue, evidence, 2, .2, result["window"])
        self.assertFalse(rejected["revised"])
        for key, value in before.items():
            self.assertTrue(torch.equal(value, session.memory.state_dict()[key]), key)
        self.assertTrue(session.query(cue)["ambiguous"])

    def test_own_feedback_and_absence_do_not_become_external_episodes(self):
        session = self.session()
        image, audio = samples((1, 0, 0, 1), random.Random(41))
        packet = Observation("audio", audio, .2, 1, "self", action_id=1)
        session.step([packet], .2)
        session.tick(.2)
        self.assertEqual(len(session.memory.blocks), 0)
        self.assertFalse(session.seen)

    def test_disagreeing_modalities_abstain_on_conflicting_author(self):
        session = self.session()
        image, _ = samples((1, 0, 0, 1), random.Random(55))
        _, audio = samples((1, 0, 1, 1), random.Random(56))
        distributions, _ = session.interpret(packets(image, audio, 0, 0))
        _, known = semantic(distributions)
        self.assertFalse(known[2])

    def test_temporary_occlusion_does_not_create_another_experience(self):
        session = self.session()
        rng = random.Random(92)
        for frame in range(12):
            visible = (True,) * 4 if frame in (0, 11) else (True, False, False, True)
            image, audio = samples((1, 0, 0, 1), rng, visible)
            session.step(packets(image, audio, session.clock + .2, frame * 2), .2)
        self.assertEqual(len(session.memory.blocks), 1)
        image, audio = samples((1, 0, 0, 1), rng, (True, False, False, True))
        recalled = session.query(packets(image, audio, session.clock, 0))
        self.assertEqual(recalled["recall"]["autor"], "pai")

    def test_index_metadata_cannot_replace_erased_associative_weights(self):
        session = self.session()
        result = meals(session, 6017)
        cue = packets(result["cue_image"], result["cue_audio"], session.clock, 0)
        before = session.memory.metadata()
        for block in session.memory.blocks:
            for bank in block.banks:
                bank.weights.zero_()
        recalled = session.query(cue, window=result["window"])
        self.assertIsNone(recalled["recall"])
        self.assertEqual(before, session.memory.metadata())

    def test_future_data_and_capacity_failure_preserve_committed_state(self):
        session = self.session(1)
        before = copy.deepcopy(session)
        with self.assertRaisesRegex(ValueError, "future"):
            session.step([Observation("image", torch.zeros(3, 32, 32), 1, 0)], .2)
        self.assert_state_equal(before, session)
        image, audio = samples((1, 0, 0, 1), random.Random(57))
        session.step(packets(image, audio, .2, 0), .2)
        before = copy.deepcopy(session)
        image, audio = samples((3, 3, 3, 3), random.Random(58))
        with self.assertRaisesRegex(ValueError, "capacity"):
            session.step(packets(image, audio, .4, 2), .2)
        self.assert_state_equal(before, session)

    def test_checkpoint_continues_exactly_without_preceding_stream(self):
        session = self.session()
        records = stories(4017, 8)
        drive(session, records[:24])
        path = self.folder / "continuity.pt"
        save(path, session)
        restored = load(path)
        drive(session, records[24:])
        drive(restored, records[24:])
        self.assert_state_equal(session, restored)

    def test_new_process_recalls_corrected_author_from_weights_and_raw_cue_only(self):
        session = self.session()
        result = meals(session, 6017)
        path = self.folder / "anonymous.pt"
        cue_path = self.folder / "cue.png"
        save(path, session)
        pixels = (result["cue_image"].permute(1, 2, 0) * 255).round().to(torch.uint8)
        Image.frombytes("RGB", (32, 32), bytes(pixels.flatten().tolist())).save(cue_path)
        command = [sys.executable, "-m", "scripts.alice_memory", "episodic-query", "--checkpoint", str(path),
                   "--image", str(cue_path), "--window-start", str(result["window"][0]), "--window-end", str(result["window"][1])]
        response = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=60, encoding="utf-8")
        self.assertEqual(response.returncode, 0, response.stderr)
        self.assertEqual(json.loads(response.stdout)["recall"]["autor"], "mae")
        self.assertFalse(hasattr(session, "history"))

    def test_invalid_checkpoint_does_not_change_global_rng(self):
        session = self.session()
        meals(session, 6017)
        path = self.folder / "invalid.pt"
        save(path, session)
        payload = torch.load(path, weights_only=True)
        payload["metadata"]["traces"][0]["ended"] = float("nan")
        torch.save(payload, path)
        rng = torch.get_rng_state().clone()
        with self.assertRaises(ValueError):
            load(path)
        self.assertTrue(torch.equal(rng, torch.get_rng_state()))

    def test_memory_changes_actions_on_same_partial_current_cues(self):
        session = self.session()
        records = stories(9017, 32)
        drive(session, records)
        observations = [trace.observations for trace in session.memory.traces]
        actor = MemoryActor(session, self.policy)
        result = evaluate_actions(actor, records, 11017)
        self.assertGreaterEqual(result["success"]["memory"], .8)
        self.assertGreaterEqual(result["gain_over_no_memory_pp"], 20)
        self.assertGreater(result["success"]["memory"], result["success"]["shuffled"])
        self.assertEqual(observations, [trace.observations for trace in session.memory.traces])
        self.assertGreater(actor.self_feedback, 50)
        self.assertLessEqual(len(actor.pending), 32)

    def test_pending_self_feedback_survives_restore_and_duplicate_has_no_echo(self):
        session = self.session()
        result = meals(session, 6017)
        actor = MemoryActor(session, self.policy)
        cue = packets(result["cue_image"], result["cue_audio"], session.clock, 0)
        initial = actor.respond(cue, 2, result["window"], "initial")
        current = actor.respond(cue, 2, result["window"])
        self.assertEqual(initial["action"]["signal"], 0)
        self.assertEqual(current["action"]["signal"], 1)
        path = self.folder / "actor.pt"
        save_actor(path, actor)
        restored = load_actor(path)
        self.assertEqual(actor.pending, restored.pending)
        _, sound = samples((0, 0, 1, 0), random.Random(60), (False, False, True, False))
        own = Observation("audio", sound, session.clock + .2, 1, "self", action_id=actor.last_action.sequence)
        left = actor.feedback([own], .2)
        right = restored.feedback([own], .2)
        self.assertEqual(left, right)
        self.assert_state_equal(actor.session, restored.session)
        self.assertTrue(torch.equal(actor.last_feedback, restored.last_feedback))
        actions = actor.actions
        self.assertEqual(actor.feedback([own], .2)["accepted"], 0)
        self.assertEqual(actor.actions, actions)

    def test_new_process_action_uses_only_checkpoint_and_partial_sensory_cue(self):
        session = self.session()
        result = meals(session, 6020)
        actor = MemoryActor(session, self.policy)
        path, cue_path = self.folder / "isolated-actor.pt", self.folder / "actor-cue.png"
        save_actor(path, actor)
        pixels = (result["cue_image"].permute(1, 2, 0) * 255).round().to(torch.uint8)
        Image.frombytes("RGB", (32, 32), bytes(pixels.flatten().tolist())).save(cue_path)
        cues = packets(result["cue_image"], result["cue_audio"], session.clock, 0, "image")
        expected = actor.respond(cues, 2, result["window"])
        response = subprocess.run([sys.executable, "-m", "scripts.alice_memory", "memory-respond",
                                   "--checkpoint", str(path), "--field", "2", "--image", str(cue_path),
                                   "--window-start", str(result["window"][0]), "--window-end", str(result["window"][1])],
                                  cwd=ROOT, capture_output=True, text=True, timeout=60, encoding="utf-8")
        self.assertEqual(response.returncode, 0, response.stderr)
        self.assertEqual(json.loads(response.stdout)["action"], expected["action"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
