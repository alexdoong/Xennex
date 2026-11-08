"""Concurrent ownership, neural causality, failure atomicity and restart."""
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

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.alice_memory.episodic_experiment import create as create_perception, packets as single_packets
from scripts.alice_memory.experience_signals import samples
from scripts.alice_memory.process_metrics import Budget
from scripts.alice_memory.scene_binding import ParticipantBinding, data, evaluate, train
from scripts.alice_memory.scene_experiment import create, drive, query
from scripts.alice_memory.scene_memory import restore, save
from scripts.alice_memory.scene_signals import SceneObservation, packets, scene


class ConcurrentMemoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        torch.set_num_threads(1)
        cls.base, _ = create_perception(17, Budget(100000, 120))
        torch.set_num_threads(1)
        cls.binding = ParticipantBinding()
        train(cls.binding, data(cls.base.perception, 68117, 512), 69117)
        folder = ROOT / "bin/AliceSceneTests"
        folder.mkdir(parents=True, exist_ok=True)
        cls.directory = tempfile.TemporaryDirectory(dir=folder)
        cls.folder = Path(cls.directory.name)

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def setUp(self):
        self.agent = create(self.base.perception, self.base.boundary, self.binding)
        self.rng = random.Random(70117)
        self.values = ((0, 0, 0, 0), (1, 1, 1, 1))

    def frame(self, values=None, masks=((True,) * 4, (True,) * 4)):
        return drive(self.agent, values or self.values, self.rng, masks)

    def assert_nested_equal(self, left, right):
        if isinstance(left, torch.Tensor):
            self.assertTrue(torch.equal(left, right))
        elif isinstance(left, dict):
            self.assertEqual(set(left), set(right))
            for key in left:
                self.assert_nested_equal(left[key], right[key])
        elif isinstance(left, list):
            self.assertEqual(len(left), len(right))
            for before, after in zip(left, right):
                self.assert_nested_equal(before, after)
        else:
            self.assertEqual(left, right)

    def test_position_changes_keep_two_events_and_correct_partial_cue_recall(self):
        self.frame()
        for _ in range(4):
            result = self.frame(tuple(reversed(self.values)))
            self.assertEqual({item["region"]: item["track"] for item in result["events"]}, {1: 0, 0: 1})
            self.assertEqual(len(self.agent.memory.blocks), 2)
        window = (.1, self.agent.clock)
        for value, author in zip(self.values, ("pai", "mae")):
            self.assertEqual(query(self.agent, value, self.rng, window)["recall"]["autor"], author)
        self.assertEqual([trace.observations for trace in self.agent.memory.traces], [5, 5])

    def test_one_activity_change_does_not_end_the_other_ongoing_episode(self):
        self.frame()
        self.frame(((2, 0, 0, 0), self.values[1]))
        self.assertEqual(len(self.agent.memory.blocks), 3)
        self.assertEqual([track["episode"] for track in self.agent.tracks], [2, 1])
        self.assertEqual(self.agent.memory.traces[0].ended, .1)
        self.assertEqual(self.agent.memory.traces[1].ended, .2)
        self.assertEqual(self.agent.memory.traces[1].observations, 2)

    def test_capacity_rejects_whole_simultaneous_step_before_any_mutation(self):
        self.agent = create(self.base.perception, self.base.boundary, self.binding, capacity=2)
        self.frame()
        before = copy.deepcopy(self.agent.snapshot())
        with self.assertRaisesRegex(ValueError, "capacity"):
            self.frame(((2, 0, 0, 0), (3, 1, 1, 1)))
        self.assert_nested_equal(before, self.agent.snapshot())

    def test_missing_participant_and_duplicate_owner_abstain_without_overwriting_past(self):
        self.frame()
        before = {key: value.clone() for key, value in self.agent.memory.blocks[0].state_dict().items()}
        result = self.frame(masks=((True, True, False, True), (True,) * 4))
        self.assertEqual(result["unassigned_regions"], [0])
        self.assertEqual(self.agent.memory.traces[0].observations, 1)
        self.assert_nested_equal(before, self.agent.memory.blocks[0].state_dict())
        result = self.frame((self.values[0], (1, 1, 0, 1)))
        self.assertEqual(result["ambiguous_regions"], [0, 1])
        self.assertEqual(result["events"], [])
        self.assertEqual(len(self.agent.memory.blocks), 2)

    def test_modality_conflict_and_self_emission_do_not_create_external_facts(self):
        self.frame()
        before = copy.deepcopy(self.agent.memory.state_dict())
        image, audio = scene(self.values, self.rng)
        result = self.agent.step(packets(image, audio.flip(0), .2, 2), .1)
        self.assertEqual(result["events"], [])
        own = SceneObservation("image", image, .3, 4, "self", action_id=0)
        self.assertEqual(self.agent.step([own], .1)["events"], [])
        self.assert_nested_equal(before, self.agent.memory.state_dict())

    def test_directed_revision_and_initial_interpretation_preserve_other_participant(self):
        for _ in range(3):
            self.frame()
        window = (.1, self.agent.clock)
        cue_image, cue_audio = samples(self.values[0], self.rng, (True, False, False, True))
        evidence_image, evidence_audio = samples((0, 0, 2, 0), self.rng, (False, False, True, False))
        result = self.agent.base.revise(single_packets(cue_image, cue_audio, self.agent.clock, 0),
                                        single_packets(evidence_image, evidence_audio, self.agent.clock, 2), 2, 0., window)
        self.assertTrue(result["revised"])
        self.assertEqual(query(self.agent, self.values[0], self.rng, window)["recall"]["autor"], "colega")
        self.assertEqual(query(self.agent, self.values[0], self.rng, window, "initial")["recall"]["autor"], "pai")
        self.assertEqual(query(self.agent, self.values[1], self.rng, window)["recall"]["autor"], "mae")
        with torch.no_grad():
            for bank in self.agent.memory.blocks[0].banks:
                bank.weights.zero_()
        result = query(self.agent, self.values[0], self.rng, window)
        self.assertIsNone(result["recall"])

    def test_correspondence_requires_binding_weights_and_reserved_pairs_generalize(self):
        held_out = data(self.base.perception, 71117, 256, evaluation=True)
        trained = evaluate(self.binding, held_out)
        self.assertGreaterEqual(trained["match_recall"], .98)
        self.assertLessEqual(trained["false_match_rate"], .02)
        zero = copy.deepcopy(self.binding)
        with torch.no_grad():
            for parameter in zero.parameters():
                parameter.zero_()
        self.agent = create(self.base.perception, self.base.boundary, zero)
        self.frame()
        self.frame(tuple(reversed(self.values)))
        self.assertEqual(len(self.agent.memory.blocks), 4)
        self.assertEqual(evaluate(zero, held_out)["match_recall"], 0)

    def test_gaps_advance_one_clock_without_inventing_events_and_reencounter_is_new(self):
        self.frame()
        self.agent.tick(3.)
        self.assertEqual(self.agent.clock, self.agent.memory.clock)
        self.assertEqual(len(self.agent.memory.blocks), 2)
        self.frame()
        self.assertEqual(len(self.agent.memory.blocks), 4)
        self.assertEqual(len(self.agent.tracks), 2)

    def test_each_sense_can_write_two_events_and_the_other_sense_can_recall_them(self):
        for write_mode, read_mode in (("image", "audio"), ("audio", "image")):
            with self.subTest(write_mode=write_mode):
                self.agent = create(self.base.perception, self.base.boundary, self.binding)
                for _ in range(3):
                    drive(self.agent, self.values, self.rng, modality=write_mode)
                for value, author in zip(self.values, ("pai", "mae")):
                    answer = query(self.agent, value, self.rng, (.1, self.agent.clock), modality=read_mode)
                    self.assertEqual(answer["recall"]["autor"], author)

    def test_future_or_malformed_scene_is_rejected_before_state_changes(self):
        self.frame()
        state = copy.deepcopy(self.agent.snapshot())
        image, audio = scene(self.values, self.rng)
        bad = [SceneObservation("image", image, 2., 2),
               SceneObservation("audio", audio[:, :100], .2, 3)]
        for observation in bad:
            with self.assertRaises(ValueError):
                self.agent.step([observation], .1)
            self.assert_nested_equal(state, self.agent.snapshot())

    def test_checkpoint_ownership_layout_and_sources_reject_corruption_without_rng_change(self):
        self.frame()
        state = self.agent.snapshot()
        failures = []
        value = copy.deepcopy(state)
        value["tracks"][0]["episode"] = value["tracks"][1]["episode"]
        failures.append(value)
        value = copy.deepcopy(state)
        value["binding_source"]["perception_sha256"] = "0" * 64
        failures.append(value)
        value = copy.deepcopy(state)
        value["binding"]["layers.0.weight"][0, 0] = float("nan")
        failures.append(value)
        value = copy.deepcopy(state)
        value["tracks"][0]["previous"] = torch.zeros(16)
        failures.append(value)
        rng = torch.get_rng_state().clone()
        for value in failures:
            with self.assertRaises((ValueError, RuntimeError)):
                restore(value)
            self.assertTrue(torch.equal(rng, torch.get_rng_state()))
        resumed = restore(state)
        state["tracks"][0]["previous"].zero_()
        self.assertGreater(float(resumed.tracks[0]["previous"].sum()), 0)

    def test_fresh_process_needs_only_checkpoint_and_next_raw_scene(self):
        self.frame()
        folder = self.folder / "fresh"
        folder.mkdir()
        save(folder / "state.pt", self.agent)
        image, audio = scene(tuple(reversed(self.values)), self.rng)
        torch.save({"image": image, "audio": audio}, folder / "next.pt")
        script = """import json,sys,torch
from pathlib import Path
from scripts.alice_memory.scene_memory import load,save
from scripts.alice_memory.scene_signals import packets
torch.set_num_threads(1)
p=Path(sys.argv[1]);a=load(p/'state.pt');raw=torch.load(p/'next.pt',weights_only=True)
r=a.step(packets(raw['image'],raw['audio'],a.clock+.1,a.base.steps*2),.1)
save(p/'after.pt',a);print(json.dumps(r))
"""
        child = subprocess.run([sys.executable, "-c", script, str(folder)], cwd=ROOT,
                               capture_output=True, text=True, timeout=20,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.assertEqual(child.returncode, 0, child.stderr)
        expected = self.agent.step(packets(image, audio, self.agent.clock + .1, self.agent.base.steps * 2), .1)
        self.assertEqual(json.loads(child.stdout), expected)
        saved = torch.load(folder / "after.pt", weights_only=True)
        self.assert_nested_equal(saved["base"]["memory"], self.agent.snapshot()["base"]["memory"])


if __name__ == "__main__":
    unittest.main()

