"""Consolidation contracts; predictive quality belongs to held-out pilots."""
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

from scripts.alice_memory.semantic_memory import SemanticMemory, restore as restore_semantic
from scripts.alice_memory.episodic_memory import EpisodicMemory
from scripts.alice_memory.episodic_experiment import create, packets
from scripts.alice_memory.episodic_session import EpisodicSession
from scripts.alice_memory.experience_signals import samples
from scripts.alice_memory.memory_actor import MemoryActor, RecallPolicy, train
from scripts.alice_memory.continuous_mind import ContinuousMind
from scripts.alice_memory.temporal32 import Temporal32
from scripts.alice_memory.temporal_mind import TemporalMind
from scripts.alice_memory.consolidating_mind import ConsolidatingMind, load, save
from scripts.alice_memory.continuous_experiment import run as run_scheduler
from scripts.alice_memory.process_metrics import Budget
from scripts.alice_memory.episodic_language import extract as extract_language
from scripts.alice_memory.contracts import Observation


def cue(values):
    return torch.nn.functional.one_hot(torch.tensor(values), num_classes=4).flatten().double()


class SemanticContracts(unittest.TestCase):
    def source(self):
        memory = EpisodicMemory()
        memory.observe(cue((0, 0, 1, 0)), 1., True)
        return memory, SemanticMemory()

    def test_targets_require_neural_weights_even_when_addresses_remain(self):
        memory, model = self.source()
        memory.blocks[0].banks[6].weights.zero_()
        before = model.snapshot()
        self.assertFalse(model.consolidate(memory, 0, 1.)["learned"])
        self.assertEqual(model.bank.writes.item(), 0)
        self.assertTrue(torch.equal(model.versions, before["state"]["versions"]))

    def test_each_episode_revision_is_consolidated_once(self):
        memory, model = self.source()
        self.assertTrue(model.consolidate(memory, 0, 1.)["learned"])
        self.assertEqual(model.bank.writes.item(), 3)
        state = copy.deepcopy(model.state_dict())
        self.assertFalse(model.consolidate(memory, 0, 1.)["learned"])
        self.assertTrue(all(torch.equal(value, model.state_dict()[name]) for name, value in state.items()))
        changed = memory.revise(cue((0, 0, 1, 0)), 2, torch.tensor([0., 0., 1., 0., 0.]), 2.)
        memory.clock = 2.
        self.assertTrue(changed["revised"])
        self.assertTrue(model.consolidate(memory, 0, 2.)["learned"])
        self.assertEqual(model.bank.writes.item(), 6)
        self.assertEqual(model.versions[0].item(), 1)

    def test_target_in_query_cannot_change_the_prediction_or_modify_input(self):
        memory, model = self.source()
        model.consolidate(memory, 0, 1.)
        first = cue((0, 0, 0, 0))
        second = cue((0, 0, 3, 0))
        saved = second.clone()
        self.assertEqual(model.predict(first), model.predict(second))
        self.assertTrue(torch.equal(saved, second))
        self.assertTrue(model.predict(first)["hypothesis"])

    def test_revision_of_an_input_field_reconsolidates_the_association(self):
        memory, model = self.source()
        model.consolidate(memory, 0, 1.)
        changed = memory.revise(cue((0, 0, 1, 0)), 3, torch.tensor([0., 1., 0., 0., 0.]), 2.)
        memory.clock = 2.
        self.assertTrue(changed["revised"])
        self.assertTrue(model.consolidate(memory, 0, 2.)["learned"])
        self.assertEqual(model.versions[0].item(), 1)
        self.assertEqual(model.bank.writes.item(), 6)

    def test_unlearned_and_missing_cues_abstain(self):
        _, model = self.source()
        self.assertFalse(model.predict(cue((3, 3, 3, 3)))["supported"])
        self.assertFalse(model.predict(torch.zeros(16, dtype=torch.float64))["supported"])

    def test_equally_predictive_conflicting_sources_abstain(self):
        model = SemanticMemory()
        for group in range(3):
            for category in range(4):
                key = torch.zeros(15, dtype=torch.float64)
                key[group * 5 + category] = key[group * 5 + 4] = 1
                value = torch.nn.functional.one_hot(torch.tensor((group + category) % 4), num_classes=4).double()
                model.bank.write(key, value)
        self.assertFalse(model.predict(cue((0, 0, 0, 0)))["supported"])

    def test_invalid_or_future_source_does_not_mutate_weights(self):
        memory, model = self.source()
        before = model.bank.weights.clone()
        for index, now in ((-1, 1.), (0, 2.), (False, 1.)):
            with self.assertRaises(ValueError):
                model.consolidate(memory, index, now)
        self.assertTrue(torch.equal(before, model.bank.weights))

    def test_restoration_checks_precision_and_source_versions(self):
        memory, model = self.source()
        model.consolidate(memory, 0, 1.)
        resumed = restore_semantic(model.snapshot(), memory)
        self.assertEqual(model.predict(cue((0, 0, 2, 0))), resumed.predict(cue((0, 0, 2, 0))))
        for kind in ("future", "unknown_source", "precision", "dtype"):
            payload = model.snapshot()
            if kind == "future":
                payload["state"]["versions"][0] = 1
            elif kind == "unknown_source":
                payload["state"]["versions"][1] = 0
            elif kind == "precision":
                payload["state"]["bank.precision"][0, 0] = -1
            else:
                payload["state"]["bank.weights"] = payload["state"]["bank.weights"].float()
            with self.assertRaises(ValueError):
                restore_semantic(payload, memory)


class ConsolidatingMindContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        parent = ROOT / "bin" / "AliceConsolidationTests"
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
        agent = ConsolidatingMind(TemporalMind(base, Temporal32(), session.perception.state_dict()))
        image, sound = samples((0, 0, 1, 0), random.Random(17))
        agent.perceive(packets(image, sound, .1, 0), .1)
        return agent, image, sound

    def test_new_episode_consolidates_previous_without_changing_its_facts(self):
        agent, _, _ = self.fixture()
        before = copy.deepcopy(agent.mind.actor.session.memory.blocks[0].state_dict())
        image, sound = samples((1, 2, 0, 1), random.Random(18))
        result = agent.perceive(packets(image, sound, 3.1, 2), 3.)
        self.assertTrue(result["consolidation"]["learned"])
        self.assertTrue(all(torch.equal(value, agent.mind.actor.session.memory.blocks[0].state_dict()[name]) for name, value in before.items()))

    def test_past_revision_updates_consolidation_without_replacing_present_scene(self):
        agent, image, sound = self.fixture()
        agent.consolidate_current()
        previous = agent.mind.actor.session.previous.clone()
        temporal = copy.deepcopy(agent.temporal)
        temporal.advance(None, .2)
        changed_image, changed_sound = samples((0, 0, 0, 0), random.Random(19), (False, False, True, False))
        cues = packets(image, sound, agent.clock, 0)
        result = agent.revise(cues, packets(changed_image, changed_sound, agent.clock + .2, 2), 2, .2, (.1, .1))
        self.assertTrue(result["revised"])
        self.assertTrue(result["consolidation"]["learned"])
        self.assertEqual(agent.semantic.versions[0].item(), 1)
        self.assertEqual(agent.temporal.observations, 1)
        self.assertTrue(torch.equal(agent.temporal.hidden, temporal.hidden))
        self.assertTrue(torch.equal(agent.mind.actor.session.previous, previous))
        self.assertEqual(agent.clock, agent.temporal.clock)
        session = agent.mind.actor.session
        partial_image, partial_sound = samples((0, 0, 1, 0), random.Random(20), (True, True, False, True))
        partial = packets(partial_image, partial_sound, agent.clock, 0)
        self.assertEqual(session.query(partial, "initial", (.1, .1))["recall"]["autor"], "mae")
        self.assertEqual(session.query(partial, "current", (.1, .1))["recall"]["autor"], "pai")

    def test_idle_scheduler_keeps_semantic_weights_and_restores_all_components(self):
        agent, _, _ = self.fixture()
        agent.consolidate_current()
        path = self.folder / "scheduler-source.pt"
        save(path, agent)
        report = run_scheduler(path, self.folder / "scheduler", steps=20, period=.1)
        self.assertTrue(report["accepted"])
        self.assertEqual(report["semantic_writes_after"], report["semantic_writes_before"])
        resumed = load(self.folder / "scheduler" / "mind.pt")
        for _ in range(20):
            agent.tick(.1)
        self.assertEqual(agent.tick(.1), resumed.tick(.1))
        self.assertTrue(torch.equal(agent.temporal.hidden, resumed.temporal.hidden))
        self.assertTrue(torch.equal(agent.semantic.bank.weights, resumed.semantic.bank.weights))

    def test_invalid_nested_consolidation_preserves_callers_rng(self):
        agent, _, _ = self.fixture()
        path = self.folder / "invalid.pt"
        save(path, agent)
        payload = torch.load(path, weights_only=True)
        payload["semantic"]["state"]["bank.precision"][0, 0] = float("nan")
        torch.save(payload, path)
        before = torch.get_rng_state().clone()
        with self.assertRaises(ValueError):
            load(path)
        self.assertTrue(torch.equal(before, torch.get_rng_state()))

    def test_optional_neural_backend_shares_source_clock_and_resumes_next_consolidation(self):
        agent, image, sound = self.fixture()
        from scripts.alice_memory.consolidating_mind import checkpoint_payload, restore
        agent = ConsolidatingMind(agent.agent, semantic_backend="neural", seed=71)
        session = agent.mind.actor.session
        self.assertIs(agent.semantic._source(), session.memory)
        self.assertTrue(agent.consolidate_current()["learned"])
        resumed = restore(checkpoint_payload(agent))
        self.assertIs(resumed.semantic._source(), resumed.mind.actor.session.memory)
        self.assertIsNot(resumed.semantic._source(), session.memory)
        inputs = packets(image, sound, agent.clock + 3., 2)
        self.assertEqual(agent.perceive(inputs, 3.), resumed.perceive(inputs, 3.))
        self.assertEqual(agent.consolidate_current(), resumed.consolidate_current())
        self.assertEqual(agent.clock, agent.temporal.clock)
        for name, value in agent.semantic.state_dict().items():
            self.assertTrue(torch.equal(value, resumed.semantic.state_dict()[name]))
        self.assertTrue(torch.equal(agent.semantic.index.generator.get_state(), resumed.semantic.index.generator.get_state()))

    def test_optional_neural_backend_revises_past_without_replacing_present(self):
        agent, image, sound = self.fixture()
        agent = ConsolidatingMind(agent.agent, semantic_backend="neural")
        agent.consolidate_current()
        session = agent.mind.actor.session
        previous = session.previous.clone()
        changed_image, changed_sound = samples((0, 0, 0, 0), random.Random(19), (False, False, True, False))
        result = agent.revise(packets(image, sound, agent.clock, 0),
                              packets(changed_image, changed_sound, agent.clock + .2, 2), 2, .2, (.1, .1))
        self.assertTrue(result["revised"])
        self.assertTrue(result["consolidation"]["learned"])
        self.assertEqual(int(agent.semantic.versions[0]), 1)
        self.assertEqual(agent.semantic.pending_sources(), [])
        self.assertTrue(torch.equal(previous, session.previous))
        self.assertEqual(agent.clock, agent.temporal.clock)

    def test_projected_backend_factory_and_shared_owner_checkpoint(self):
        agent, image, sound = self.fixture()
        from scripts.alice_memory.consolidating_mind import checkpoint_payload, restore
        from scripts.alice_memory.projected_semantic_memory import ProjectedSemanticMemory
        agent = ConsolidatingMind(agent.agent, semantic_backend="neural-projected")
        self.assertIsInstance(agent.semantic, ProjectedSemanticMemory)
        self.assertTrue(agent.consolidate_current()["learned"])
        resumed = restore(checkpoint_payload(agent))
        self.assertIs(resumed.semantic._source(), resumed.mind.actor.session.memory)
        self.assertEqual(int(resumed.semantic.projection.fitted_writes), int(resumed.semantic.bank.writes))
        inputs = packets(image, sound, agent.clock + 3., 2)
        self.assertEqual(agent.perceive(inputs, 3.), resumed.perceive(inputs, 3.))
        self.assertEqual(agent.consolidate_current(), resumed.consolidate_current())
        self.assertTrue(all(torch.equal(value, resumed.semantic.state_dict()[name]) for name, value in agent.semantic.state_dict().items()))

    def test_own_generated_perceptions_do_not_create_consolidated_evidence(self):
        agent, image, sound = self.fixture()
        agent.consolidate_current()
        before = copy.deepcopy(agent.semantic.state_dict())
        now = agent.clock + .1
        action = agent.issue_scripted(1, 2)
        agent.perceive([Observation("image", image, now, 2, "self", action_id=action.sequence),
                       Observation("audio", sound, now, 3, "self", action_id=action.sequence)], .1)
        self.assertEqual(len(agent.mind.actor.session.memory.blocks), 1)
        self.assertTrue(all(torch.equal(value, agent.semantic.state_dict()[name]) for name, value in before.items()))

    def test_language_extracts_episode_facts_even_when_expectation_weights_disagree(self):
        agent, image, _ = self.fixture()
        agent.consolidate_current()
        agent.semantic.bank.weights.zero_()
        agent.semantic.bank.weights[3].fill_(100.)
        path, png = self.folder / "language.pt", self.folder / "language.png"
        save(path, agent)
        pixels = (image.permute(1, 2, 0) * 255).round().to(torch.uint8)
        Image.frombytes("RGB", (32, 32), bytes(pixels.flatten().tolist())).save(png)
        evidence = extract_language(path, png, (.1, .1))
        self.assertEqual(dict(evidence["evidence"][1]["attributes"])["autor"], "mae")
        self.assertNotIn("semantic", json.dumps(evidence))

    def test_fresh_process_continues_only_from_integrated_checkpoint(self):
        agent, _, _ = self.fixture()
        agent.consolidate_current()
        path = self.folder / "process.pt"
        save(path, agent)
        child = subprocess.run([sys.executable, "-c",
            "import json,sys,torch;from pathlib import Path;from scripts.alice_memory.consolidating_mind import load;"
            "torch.set_num_threads(2);a=load(Path(sys.argv[1]));a.tick(.1);"
            "print(json.dumps({'clock':a.clock,'hidden':a.temporal.hidden.tolist(),"
            "'weights':a.semantic.bank.weights.tolist(),'duplicate':a.consolidate_current()}))", str(path)],
            cwd=ROOT, check=True, capture_output=True, text=True, timeout=30)
        actual = json.loads(child.stdout)
        agent.tick(.1)
        self.assertEqual(actual["clock"], agent.clock)
        self.assertTrue(torch.equal(torch.tensor(actual["weights"], dtype=torch.float64), agent.semantic.bank.weights))
        self.assertTrue(torch.equal(torch.tensor(actual["hidden"]), agent.temporal.hidden))
        self.assertFalse(actual["duplicate"]["learned"])


if __name__ == "__main__":
    torch.set_num_threads(2)
    unittest.main(verbosity=2)
