"""Temporal/memory integration contracts; quality is assessed by separate pilots.

The temporal fixture is intentionally untrained for protocol checks. CLI model
admission requires a passed report; real held-out gains are not claimed by tests.
"""
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

from scripts.alice_memory.continuous_mind import ContinuousMind
from scripts.alice_memory.contracts import Observation
from scripts.alice_memory.episodic_experiment import create, packets
from scripts.alice_memory.episodic_session import EpisodicSession
from scripts.alice_memory.experience_signals import samples
from scripts.alice_memory.memory_actor import MemoryActor, RecallPolicy, train
from scripts.alice_memory.temporal32 import Temporal32
from scripts.alice_memory.temporal_mind import TemporalMind, load, load_models, save
from scripts.alice_memory.episodic_language import extract as extract_language
from scripts.alice_memory.process_metrics import Budget
from scripts.alice_memory.continuous_experiment import run as run_scheduler


class TemporalMindTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        parent = ROOT / "bin" / "AliceTemporalMindTests"
        parent.mkdir(parents=True, exist_ok=True)
        cls.directory = tempfile.TemporaryDirectory(dir=parent)
        cls.folder = Path(cls.directory.name)
        cls.template, _ = create(17, Budget(100000, 120))
        cls.policy = RecallPolicy()
        train(cls.policy, 1017, Budget(100000, 120))

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def fixture(self):
        session = EpisodicSession(self.template.perception, self.template.boundary)
        base = ContinuousMind(MemoryActor(session, self.policy))
        agent = TemporalMind(base, Temporal32(), session.perception.state_dict())
        image, sound = samples((0, 0, 1, 0), random.Random(17))
        agent.perceive(packets(image, sound, .1, 0), .1)
        return agent, image, sound

    def test_unvalidated_models_are_rejected_before_deserializing_weights(self):
        folder = self.folder / "unvalidated"
        folder.mkdir(exist_ok=True)
        (folder / "models.pt").write_bytes(b"not a torch file")
        (folder / "report.json").write_text(json.dumps({"accepted": False}), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "evaluation gate"):
            load_models(folder / "models.pt")

    def test_a_different_perceptual_basis_is_rejected(self):
        agent, _, _ = self.fixture()
        different = {name: value.clone() for name, value in agent.mind.actor.session.perception.state_dict().items()}
        different["head.weight"] += .01
        with self.assertRaisesRegex(ValueError, "different sensory"):
            TemporalMind(agent.mind, Temporal32(), different)

    def test_internal_forecasts_do_not_create_episodes_or_strengthen_facts(self):
        agent, _, _ = self.fixture()
        before = {name: value.clone() for name, value in agent.mind.actor.session.memory.state_dict().items()}
        for _ in range(10):
            agent.tick(.1)
        self.assertEqual(agent.temporal.observations, 1)
        self.assertEqual(len(agent.mind.actor.session.memory.blocks), 1)
        self.assertTrue(agent.forecasts()["hypothesis"])
        self.assertTrue(all(torch.equal(value, agent.mind.actor.session.memory.state_dict()[name]) for name, value in before.items()))

    def test_answering_about_activity_is_speech_not_an_activity_actuator(self):
        agent, image, sound = self.fixture()
        agent.request(packets(image, sound, agent.clock, 0), 0, (.1, .1))
        response = agent.tick(.1)
        self.assertEqual(response["action"]["kind"], "emit")
        self.assertEqual(agent.temporal.command[0, 6].item(), 1.)
        self.assertEqual(agent.temporal.command[0, 4].item(), 0.)

    def test_own_returns_advance_time_without_external_temporal_observation(self):
        agent, _, _ = self.fixture()
        action = agent.issue_scripted(2, 0)
        _, own = samples((2, 0, 0, 0), random.Random(18), (True, False, False, False))
        agent.hear([Observation("audio", own, agent.clock + .1, action.sequence, "self", action_id=action.sequence)], .1)
        self.assertEqual(agent.temporal.observations, 1)
        self.assertEqual(agent.clock, agent.temporal.clock)
        self.assertEqual(agent.mind.actor.self_feedback, 1)

    def test_long_gap_is_unknown_time_and_keeps_clocks_synchronized(self):
        agent, _, _ = self.fixture()
        before = copy.deepcopy(agent.mind.actor.session.memory.metadata()["traces"])
        agent.unobserved_gap(600.)
        self.assertEqual(agent.clock, agent.temporal.clock)
        self.assertAlmostEqual(agent.clock, 600.1)
        self.assertEqual(agent.temporal.observations, 1)
        self.assertEqual(before, agent.mind.actor.session.memory.metadata()["traces"])

    def test_resume_has_identical_next_state_and_does_not_require_model_reports(self):
        agent, _, _ = self.fixture()
        agent.issue_scripted(1, 2)
        path = self.folder / "resume.pt"
        save(path, agent)
        resumed = load(path)
        self.assertEqual(agent.tick(.1), resumed.tick(.1))
        self.assertTrue(torch.equal(agent.temporal.hidden, resumed.temporal.hidden))
        self.assertTrue(torch.equal(agent.temporal.last_prediction, resumed.temporal.last_prediction))

    def test_scheduler_preserves_temporal_state_and_checkpoint_format(self):
        agent, _, _ = self.fixture()
        path = self.folder / "scheduler-source.pt"
        save(path, agent)
        report = run_scheduler(path, self.folder / "scheduler", steps=20, period=.1)
        self.assertTrue(report["accepted"])
        self.assertTrue(report["temporal_core_active"])
        self.assertEqual(report["temporal_observations_after"], 1)
        resumed = load(self.folder / "scheduler" / "mind.pt")
        for _ in range(20):
            agent.tick(.1)
        self.assertEqual(resumed.clock, agent.clock)
        self.assertTrue(torch.equal(agent.temporal.hidden, resumed.temporal.hidden))
        self.assertEqual(resumed.tick(.1), agent.tick(.1))

    def test_fresh_process_loads_only_the_agent_checkpoint(self):
        agent, _, _ = self.fixture()
        path = self.folder / "process.pt"
        save(path, agent)
        child = subprocess.run([sys.executable, "-c",
            "import json,sys,torch;from pathlib import Path;from scripts.alice_memory.temporal_mind import load;"
            "torch.set_num_threads(2);a=load(Path(sys.argv[1]));a.tick(.1);"
            "print(json.dumps({'clock':a.clock,'hidden':a.temporal.hidden.tolist(),'forecast':a.forecasts()}))", str(path)],
            cwd=ROOT, check=True, capture_output=True, text=True, timeout=30)
        result = json.loads(child.stdout)
        agent.tick(.1)
        self.assertEqual(result["clock"], agent.clock)
        self.assertTrue(torch.equal(torch.tensor(result["hidden"]), agent.temporal.hidden))

    def test_invalid_nested_snapshot_preserves_the_callers_rng(self):
        agent, _, _ = self.fixture()
        path = self.folder / "bad.pt"
        save(path, agent)
        original = torch.load(path, weights_only=True)
        for kind in ("hidden", "clock", "prediction", "command", "core"):
            value = copy.deepcopy(original)
            if kind == "hidden":
                value["temporal"]["hidden"][0, 0] = float("nan")
            elif kind == "clock":
                value["temporal"]["clock"] += 1
            elif kind == "prediction":
                value["temporal"]["last_prediction"].zero_()
            elif kind == "command":
                value["temporal"]["command"][0, 0] = 1
            else:
                value["core"]["head.weight"] = value["core"]["head.weight"].double()
            torch.save(value, path)
            rng = torch.get_rng_state().clone()
            with self.assertRaises(ValueError):
                load(path)
            self.assertTrue(torch.equal(rng, torch.get_rng_state()), kind)

    def test_language_evidence_comes_from_facts_and_not_forecast_vectors(self):
        agent, image, _ = self.fixture()
        path, cue = self.folder / "language.pt", self.folder / "cue.png"
        save(path, agent)
        pixels = (image.permute(1, 2, 0) * 255).round().to(torch.uint8)
        Image.frombytes("RGB", (32, 32), bytes(pixels.flatten().tolist())).save(cue)
        evidence = extract_language(path, cue, (.1, .1))
        self.assertEqual(len(evidence["evidence"]), 2)
        self.assertEqual(dict(evidence["evidence"][1]["attributes"])["autor"], "mae")
        self.assertNotIn("forecast", json.dumps(evidence))


if __name__ == "__main__":
    unittest.main(verbosity=2)
