"""Learned importance, internal tasks, causal outcomes and restart integrity."""
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
from scripts.alice_memory.continuous_mind import ContinuousMind, load, save
from scripts.alice_memory.episodic_experiment import create, packets
from scripts.alice_memory.episodic_session import EpisodicSession
from scripts.alice_memory.experience_signals import samples
from scripts.alice_memory.importance import Consequence
from scripts.alice_memory.importance_experiment import ConsequenceWorld, evaluate
from scripts.alice_memory.memory_actor import MemoryActor, RecallPolicy, train
from scripts.alice_memory.process_metrics import Budget
from scripts.alice_memory.episodic_language import extract as extract_language


class ContinuousMindTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        parent = ROOT / "bin" / "AliceContinuousTests"
        parent.mkdir(parents=True, exist_ok=True)
        cls.directory = tempfile.TemporaryDirectory(dir=parent)
        cls.folder = Path(cls.directory.name)
        session, _ = create(17, Budget(100000, 120))
        policy = RecallPolicy()
        train(policy, 1017, Budget(100000, 120))
        cls.template = MemoryActor(session, policy)

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def fixture(self, seed=55):
        actor = MemoryActor(EpisodicSession(self.template.session.perception, self.template.session.boundary), self.template.policy)
        mind, world = ContinuousMind(actor), ConsequenceWorld(seed)
        truth = (0, 0, 1, 0)
        episode, window = world.encounter(mind, truth)
        image, sound = samples(truth, random.Random(seed + 1), (True, False, False, True))
        cues = packets(image, sound, mind.clock, 0)
        return mind, world, truth, episode, window, cues

    def test_learned_value_beats_recency_and_noise_and_reverses_with_consequences(self):
        _, report, _ = evaluate(self.template, 33017, Budget(100000, 120))
        self.assertTrue(report["accepted"])
        self.assertEqual(report["later_answer_success_with_one_slot"]["learned"], 1)
        self.assertTrue(report["reactivation_does_not_retrain_truth_or_value"])

    def test_pending_task_can_act_on_an_internal_tick_without_resending_cues(self):
        mind, _, truth, _, window, cues = self.fixture()
        mind.request(cues, 2, window)
        self.assertIsNone(mind.tick(.05)["action"])
        result = mind.tick(.05)
        self.assertTrue(result["resumed_pending"])
        self.assertEqual(result["action"]["signal"], truth[2])
        self.assertIsNone(mind.task)

    def test_reactivation_changes_access_not_original_age_truth_or_learned_value(self):
        mind, world, truth, episode, window, _ = self.fixture()
        world.ask(mind, truth, window)
        before = copy.deepcopy(mind.actor.session.memory.metadata())
        weights = {key: value.clone() for key, value in mind.actor.session.memory.state_dict().items()}
        values = mind.importance.values.weights.clone()
        result = mind.tick(2.)
        self.assertEqual(result["evoked"]["episode"], episode)
        self.assertTrue(result["evoked"]["hypothesis"])
        self.assertIsNone(result["action"])
        self.assertEqual(before["traces"], mind.actor.session.memory.metadata()["traces"])
        self.assertGreaterEqual(mind.importance.accesses[episode].item(), 2)
        self.assertTrue(torch.equal(values, mind.importance.values.weights))
        self.assertTrue(all(torch.equal(value, mind.actor.session.memory.state_dict()[key]) for key, value in weights.items()))

    def test_utility_weights_are_goal_specific_and_not_only_access_metadata(self):
        mind, world, truth, episode, window, _ = self.fixture()
        world.ask(mind, truth, window)
        self.assertGreater(mind.importance.durable(episode, 2), .8)
        self.assertEqual(mind.importance.durable(episode, 1), 0.)
        for _ in range(10):
            mind.importance.access(episode, mind.clock)
        mind.importance.values.weights.zero_()
        self.assertEqual(mind.importance.durable(episode, 2), 0.)

    def test_new_consequences_can_reduce_old_value_without_rewriting_the_event(self):
        mind, world, truth, episode, window, _ = self.fixture()
        for _ in range(8):
            world.ask(mind, truth, window)
        high = mind.importance.durable(episode, 2)
        original = {key: value.clone() for key, value in mind.actor.session.memory.blocks[episode].state_dict().items()}
        for _ in range(64):
            world.ask(mind, truth, window, noisy=True)
        self.assertLess(mind.importance.durable(episode, 2), high - .4)
        self.assertTrue(all(torch.equal(value, mind.actor.session.memory.blocks[episode].state_dict()[key]) for key, value in original.items()))

    def test_ambiguous_facts_are_not_resolved_by_high_importance(self):
        mind, world, truth, _, window, cues = self.fixture()
        world.ask(mind, truth, window)
        world.encounter(mind, (0, 2, 2, 0))
        cues = [Observation(packet.modality, packet.payload, mind.clock, 0, packet.origin) for packet in cues]
        mind.request(cues, 2)
        response = mind.tick(.1)
        self.assertTrue(response["recall"]["ambiguous"])
        self.assertEqual(response["action"]["kind"], "wait")

    def test_duplicate_unknown_and_self_generated_rewards_do_not_train_value(self):
        mind, _, _, _, window, cues = self.fixture()
        mind.request(cues, 2, window)
        action = mind.tick(.1)["action"]
        reward = Consequence(action["sequence"], mind.clock, 1., .5, .1)
        self.assertEqual(mind.consequences([reward], 0.)["accepted"], 1)
        before = mind.importance.values.weights.clone()
        self.assertEqual(mind.consequences([reward, Consequence(1000, mind.clock, 1., 1., 0.)], 0.)["stale"], 2)
        with self.assertRaises(ValueError):
            mind.consequences([Consequence(action["sequence"], mind.clock, 1., .5, .1, "self")], 0.)
        self.assertTrue(torch.equal(before, mind.importance.values.weights))
        self.assertEqual(mind.consequences_received, 1)

    def test_invalid_batch_is_rejected_before_any_consequence_or_clock_commit(self):
        mind, _, _, _, window, cues = self.fixture()
        mind.request(cues, 2, window)
        action = mind.tick(.1)["action"]
        clock, before = mind.clock, mind.importance.values.weights.clone()
        with self.assertRaises(ValueError):
            mind.consequences([Consequence(action["sequence"], clock, 1., .5, .1),
                               Consequence(action["sequence"], clock + 2, 1., .5, .1)], .1)
        self.assertEqual(mind.clock, clock)
        self.assertIn(action["sequence"], mind.credits)
        self.assertTrue(torch.equal(before, mind.importance.values.weights))

    def test_long_offline_gap_preserves_history_and_expires_pending_work(self):
        mind, world, truth, episode, window, cues = self.fixture()
        world.ask(mind, truth, window)
        mind.request(cues, 2, window)
        before_clock, original = mind.clock, copy.deepcopy(mind.actor.session.memory.metadata())
        learned = mind.importance.durable(episode, 2)
        mind.unobserved_gap(600.)
        self.assertAlmostEqual(mind.clock, before_clock + 600.)
        self.assertEqual(mind.unobserved_seconds, 600.)
        self.assertIsNone(mind.task)
        self.assertEqual(len(mind.credits), 0)
        self.assertEqual(mind.actor.pending, {})
        self.assertEqual(original["traces"], mind.actor.session.memory.metadata()["traces"])
        self.assertEqual(mind.importance.durable(episode, 2), learned)
        self.assertIsNone(mind.tick(0.)["action"])

    def test_pending_task_and_action_attribution_survive_atomic_checkpoint(self):
        mind, _, truth, _, window, cues = self.fixture()
        mind.request(cues, 2, window)
        path = self.folder / "pending.pt"
        save(path, mind)
        restored = load(path)
        self.assertEqual(mind.tick(.1), restored.tick(.1))
        save(path, mind)
        restored = load(path)
        action = mind.actor.last_action
        _, sound = samples(truth, random.Random(9), (False, False, True, False))
        returned = Observation("audio", sound, mind.clock + .1, action.sequence, "self", action_id=action.sequence)
        self.assertEqual(mind.hear([returned], .1), restored.hear([returned], .1))
        outcome = Consequence(action.sequence, mind.clock + .1, 1., .5, .1)
        self.assertEqual(mind.consequences([outcome], .1), restored.consequences([outcome], .1))
        self.assertEqual(mind.snapshot()["internal"], restored.snapshot()["internal"])
        self.assertTrue(torch.equal(mind.importance.values.weights, restored.importance.values.weights))

    def test_fresh_process_resumes_only_checkpoint_with_no_history_or_query_file(self):
        mind, _, truth, _, window, cues = self.fixture()
        mind.request(cues, 2, window)
        path = self.folder / "fresh.pt"
        save(path, mind)
        child = subprocess.run([sys.executable, "-c",
            "import json,sys,torch; from pathlib import Path; "
            "from scripts.alice_memory.continuous_mind import load; torch.set_num_threads(2); "
            "print(json.dumps(load(Path(sys.argv[1])).tick(.1)['action']))", str(path)],
            cwd=ROOT, capture_output=True, text=True, timeout=30, check=True)
        action = json.loads(child.stdout)
        self.assertEqual(action["signal"], truth[2])
        self.assertEqual(action, mind.tick(.1)["action"])

    def test_invalid_nested_state_does_not_change_global_torch_rng(self):
        mind, _, _, _, window, cues = self.fixture()
        mind.request(cues, 2, window)
        path = self.folder / "bad.pt"
        save(path, mind)
        original = torch.load(path, weights_only=True)
        for mutation in ("covariance", "dtype", "clock", "task", "credit"):
            payload = copy.deepcopy(original)
            if mutation == "covariance":
                payload["importance"]["values.precision"][0, 0] = -1
            if mutation == "dtype":
                payload["importance"]["updates"] = payload["importance"]["updates"].float()
            if mutation == "clock":
                payload["importance"]["last_access"][0] = float("nan")
            if mutation == "task":
                payload["state"]["task"]["issued"] = mind.clock + 1
            if mutation == "credit":
                payload["state"]["credits"] = {999: (0, 2, mind.clock)}
            torch.save(payload, path)
            rng = torch.get_rng_state().clone()
            with self.assertRaises(ValueError):
                load(path)
            self.assertTrue(torch.equal(rng, torch.get_rng_state()), mutation)

    def test_priority_ranking_does_not_mutate_its_perceptual_cue(self):
        mind, _, _, _, window, cues = self.fixture()
        mind.request(cues, 2, window)
        before = mind.task["cue"].clone()
        mind.importance.rank(mind.actor.session.memory, mind.task["cue"], 2, mind.clock)
        self.assertTrue(torch.equal(before, mind.task["cue"]))

    def test_occluded_field_does_not_carry_over_from_a_different_episode(self):
        mind, world, _, _, _, _ = self.fixture()
        truth = (3, 2, 3, 2)
        image, _ = samples(truth, world.rng)
        _, conflicting = samples((3, 2, 0, 2), world.rng, (False, False, True, False))
        first = mind.perceive(packets(image, conflicting, mind.clock + 3, mind.actor.session.steps * 2), 3.)
        self.assertTrue(first["new_episode"])
        self.assertFalse(first["known"][2])
        self.assertEqual(mind.actor.session.previous.reshape(4, 4)[2].sum().item(), 0.)
        _, revealed = samples(truth, world.rng, (False, False, True, False))
        next_frame = mind.perceive(packets(image, revealed, mind.clock + .1, mind.actor.session.steps * 2), .1)
        self.assertFalse(next_frame["new_episode"])
        self.assertEqual(first["episode"], next_frame["episode"])
        self.assertEqual(len(mind.actor.session.memory.blocks), 2)

    def test_old_mind_format_preserves_its_original_context_behavior(self):
        mind, _, _, _, _, _ = self.fixture()
        mind.context_reset = False
        path = self.folder / "legacy-mind.pt"
        save(path, mind)
        self.assertEqual(torch.load(path, weights_only=True)["format"], 15)
        self.assertFalse(load(path).context_reset)

    def test_delayed_consequences_cannot_grow_past_the_queue_budget(self):
        mind, world, truth, _, window, cues = self.fixture()
        for _ in range(32):
            mind.request(cues, 2, window)
            action = mind.tick(.1)["action"]
            _, sound = samples(truth, world.rng, (False, False, True, False))
            mind.hear([Observation("audio", sound, mind.clock + .1, action["sequence"], "self",
                                   action_id=action["sequence"])], .1)
        self.assertEqual(len(mind.credits), 32)
        self.assertEqual(mind.actor.pending, {})
        mind.request(cues, 2, window)
        blocked = mind.tick(.1)
        self.assertEqual(blocked["reason"], "consequence_queue_full")
        self.assertIsNone(blocked["action"])
        self.assertIsNotNone(mind.task)
        mind.unobserved_gap(60.1)
        self.assertEqual(len(mind.credits), 0)
        self.assertIsNone(mind.task)

    def test_internal_work_budget_defers_the_task_until_capacity_recovers(self):
        mind, _, truth, _, window, cues = self.fixture()
        mind.request(cues, 2, window)
        mind.internal.energy = 0.
        blocked = mind.tick(0.)
        self.assertEqual(blocked["reason"], "functional_work_budget")
        self.assertIsNotNone(mind.task)
        self.assertEqual(mind.tick(.5)["action"]["signal"], truth[2])

    def test_language_reads_mind_facts_without_promoting_importance_to_truth_confidence(self):
        mind, world, truth, _, window, cues = self.fixture()
        world.ask(mind, truth, window)
        checkpoint, image = self.folder / "mind-language.pt", self.folder / "mind-language.png"
        save(checkpoint, mind)
        pixels = (cues[0].payload.permute(1, 2, 0) * 255).round().to(torch.uint8)
        Image.frombytes("RGB", (32, 32), bytes(pixels.flatten().tolist())).save(image)
        first = extract_language(checkpoint, image, window)
        mind.importance.values.weights.zero_()
        save(checkpoint, mind)
        second = extract_language(checkpoint, image, window)
        for before, after in zip(first["evidence"], second["evidence"]):
            self.assertEqual(before["attributes"], after["attributes"])
            self.assertEqual(before["confidence"], after["confidence"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
