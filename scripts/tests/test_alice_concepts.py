"""New taught concepts, withheld compositions, inquiry and integrated restart."""
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from scripts.alice_memory.concept_memory import ConceptLesson, ConceptMemory, restore
from scripts.alice_memory.conceptual_mind import ConceptualMind, save
from scripts.alice_memory.continuous_experiment import load_scheduler
from scripts.alice_memory.reactivation_index import source_digest
from scripts.alice_memory.runtime_snapshot import capture
import test_alice_word_grounding as fixtures


def lesson(memory, name, x, matrix, offset=(0., 0.), now=10.):
    value = torch.tensor(matrix, dtype=torch.float64) @ torch.tensor(x, dtype=torch.float64) + torch.tensor(offset)
    return ConceptLesson(name, tuple(x), tuple(value.tolist()), "external-teacher", memory.sequence + 1, now)


def teach(memory, name, matrix, offset=(0., 0.), now=10.):
    for x in ((0., 0.), (1., 0.), (-1., 0.), (0., 1.), (0., -1.), (1., 1.)):
        memory.teach(lesson(memory, name, x, matrix, offset, now), now)


class ConceptContracts(unittest.TestCase):
    def test_unseen_vectors_are_computed_from_new_weights_without_answer_lookup(self):
        memory = ConceptMemory()
        self.assertFalse(memory.predict("nivo", [.3, -.7])["supported"])
        matrix, offset = [[.7, -.2], [.4, .6]], [.1, -.15]
        teach(memory, "nivo", matrix, offset)
        for x in ((.3, -.7), (-.8, .2), (1.2, -1.1)):
            result = memory.predict("nivo", list(x))
            self.assertTrue(result["supported"])
            expected = torch.tensor(matrix).double() @ torch.tensor(x).double() + torch.tensor(offset)
            self.assertTrue(torch.allclose(torch.tensor(result["value"]).double(), expected, atol=.002, rtol=0))
        snapshot = memory.snapshot()
        self.assertEqual(set(snapshot["sources"]["nivo"][0]), {"source", "sequence", "acquired_at", "origin"})
        memory.banks["nivo"].weights.zero_()
        expected = torch.tensor(matrix).double() @ torch.tensor([.3, -.7]).double() + torch.tensor(offset)
        self.assertGreater(torch.tensor(memory.predict("nivo", [.3, -.7])["value"]).sub(expected).abs().max().item(), .1)

    def test_untrained_direction_abstains_and_inquiry_selects_missing_information(self):
        memory = ConceptMemory()
        for x in ((0., 0.), (1., 0.), (-1., 0.)):
            memory.teach(lesson(memory, "nivo", x, [[1., 0.], [0., 2.]]), 10.)
        self.assertTrue(memory.predict("nivo", [.5, 0.])["supported"])
        self.assertFalse(memory.predict("nivo", [0., .5])["supported"])
        options = [{"concept": "nivo", "input": [1., 0.], "cost": 0.},
                   {"concept": "nivo", "input": [0., 1.], "cost": 0.}]
        inquiry = memory.choose_inquiry(options)
        self.assertEqual(inquiry["input"], [0., 1.])
        before = memory.uncertainty("nivo", [.2, .8])
        memory.teach(lesson(memory, inquiry["concept"], inquiry["input"], [[1., 0.], [0., 2.]]), 10.)
        self.assertLess(memory.uncertainty("nivo", [.2, .8]), before / 100)
        self.assertTrue(memory.predict("nivo", [.2, .8])["supported"])

    def test_composition_order_uses_both_learned_premises_without_composition_examples(self):
        memory = ConceptMemory()
        teach(memory, "nivo", [[1., .5], [0., 1.]])
        teach(memory, "zalu", [[0., -1.], [1., 0.]])
        result = memory.hypothesize(["nivo", "zalu"], [.3, .7], 10.)
        self.assertTrue(result["supported"])
        self.assertEqual(set(result["premises"]), {"nivo", "zalu"})
        self.assertFalse(result["autobiographical_write"])
        self.assertTrue(torch.allclose(torch.tensor(result["value"]), torch.tensor([-.7, .65]), atol=.002, rtol=0))
        reverse = memory.compose(["zalu", "nivo"], [.3, .7])
        self.assertGreater((torch.tensor(result["value"]) - torch.tensor(reverse["value"])).abs().max().item(), .1)
        self.assertFalse(memory.compose(["nivo", "unknown"], [.3, .7])["supported"])

    def test_external_verification_is_not_self_teaching_and_changed_premise_invalidates(self):
        memory = ConceptMemory()
        teach(memory, "nivo", [[1., 0.], [0., 1.]])
        teach(memory, "zalu", [[2., 0.], [0., 2.]])
        dependent = memory.hypothesize(["nivo"], [.3, .7], 10.)
        independent = memory.hypothesize(["zalu"], [.3, .7], 10.)
        writes = memory.lessons
        self.assertEqual(memory.verify(dependent["id"], [.3, .7], "test-result", 10.)["status"], "verified_example")
        self.assertEqual(memory.lessons, writes)
        changed = memory.teach(lesson(memory, "nivo", [.3, .7], [[2., 0.], [0., 2.]], now=11.), 11.)
        self.assertEqual(changed["invalidated"], [dependent["id"]])
        self.assertFalse(memory.verify(dependent["id"], [.6, 1.4], "test-result", 11.)["accepted"])
        self.assertEqual(memory.hypotheses[independent["id"]]["status"], "untested")
        self.assertEqual(memory.verify(independent["id"], [0., 0.], "test-result", 11.)["status"], "contradicted")

    def test_stale_invalid_and_self_generated_lessons_cannot_change_weights(self):
        memory = ConceptMemory()
        item = lesson(memory, "nivo", [1., 0.], [[1., 0.], [0., 1.]])
        memory.teach(item, 10.)
        before = memory.banks["nivo"].weights.clone()
        self.assertFalse(memory.teach(item, 10.)["learned"])
        for invalid in (ConceptLesson("nivo", (1., 0.), (1., 0.), "self", 1, 10., "deduced"),
                        ConceptLesson("nivo", (True, 0.), (1., 0.), "teacher", 1, 10.),
                        ConceptLesson("nivo", (1., 0.), (float('nan'), 0.), "teacher", 1, 10.),
                        ConceptLesson("nivo", (1., 0.), (1., 0.), "teacher", 1, 11.)):
            with self.assertRaises(ValueError):
                memory.teach(invalid, 10.)
        self.assertTrue(torch.equal(before, memory.banks["nivo"].weights))
        self.assertEqual(memory.lessons, 1)

    def test_snapshot_detaches_and_restore_rejects_invalid_provenance_and_covariance(self):
        memory = ConceptMemory()
        teach(memory, "nivo", [[1., 0.], [0., 1.]])
        number = memory.hypothesize(["nivo"], [.3, .7], 10.)["id"]
        payload = memory.snapshot()
        memory.verify(number, [.3, .7], "test", 10.)
        restored = restore(payload, 10.)
        self.assertEqual(restored.hypotheses[number]["status"], "untested")
        for field in ("covariance", "sequence", "source", "premise", "prediction", "counter"):
            damaged = copy.deepcopy(payload)
            if field == "covariance":
                damaged["banks"]["nivo"]["precision"][0, 0] = -1.
            elif field == "sequence":
                damaged["sources"]["nivo"][1]["sequence"] = 0
            elif field == "source":
                damaged["sources"]["nivo"][0]["origin"] = "deduced"
            elif field == "premise":
                damaged["hypotheses"][number]["premises"]["nivo"] -= 1
            elif field == "prediction":
                damaged["hypotheses"][number]["prediction"][0] += 1.
            else:
                damaged["next_hypothesis"] = 10 ** 100
            with self.assertRaises(ValueError):
                restore(damaged, 10.)

    def test_cost_changes_inquiry_without_using_unknown_teacher_answers(self):
        memory = ConceptMemory()
        result = memory.choose_inquiry([{"concept": "a", "input": [0., 1.], "cost": 100.},
                                       {"concept": "b", "input": [1., 0.], "cost": 0.}])
        self.assertEqual(result["concept"], "b")
        self.assertEqual(memory.lessons, 0)
        with self.assertRaises(ValueError):
            memory.choose_inquiry([{"concept": "b", "input": [1., 0.], "cost": 0., "answer": [1., 0.]}])

    def test_capacity_refuses_new_concept_without_erasing_the_first(self):
        memory = ConceptMemory()
        for index in range(32):
            memory.teach(lesson(memory, str(index), [1., 0.], [[1., 0.], [0., 1.]]), 10.)
        before = memory.banks['0'].weights.clone()
        with self.assertRaises(ValueError):
            memory.teach(lesson(memory, 'overflow', [1., 0.], [[1., 0.], [0., 1.]]), 10.)
        self.assertEqual(len(memory.banks), 32)
        self.assertEqual(memory.lessons, 32)
        self.assertTrue(torch.equal(before, memory.banks['0'].weights))


class ConceptualMindContracts(unittest.TestCase):
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
        self.fixture.perceive(self.agent)
        self.agent.consolidate_current()
        temporary = tempfile.TemporaryDirectory(dir=ROOT / 'bin')
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)

    def test_abstract_teaching_preserves_episodes_and_fresh_process_resumes_pending_inquiry(self):
        memory = self.agent.mind.actor.session.memory
        before = [source_digest(block) for block in memory.blocks]
        observed = self.agent.temporal.observations
        teach(self.agent.concepts, 'nivo', [[.7, -.2], [.4, .6]], now=self.agent.clock)
        inquiry_id = self.agent.request_study([{'concept': 'nivo', 'input': [.3, -.7], 'cost': 0.},
                                               {'concept': 'unknown', 'input': [0., 1.], 'cost': 0.}])
        checkpoint, result_path = self.folder / 'mind.pt', self.folder / 'child.json'
        save(checkpoint, self.agent)
        code = "from pathlib import Path; import json,sys,torch; from scripts.alice_memory.continuous_experiment import load_scheduler; from scripts.alice_memory.persistent_runtime import close_agent; torch.set_num_threads(1); a,m,_=load_scheduler(Path(sys.argv[1])); p=a.concepts.compose(['nivo'],[.3,-.7]); t=a.tick(.1); Path(sys.argv[2]).write_text(json.dumps({'prediction':p,'inquiry':t['concept_inquiry'],'hidden':a.temporal.hidden.tolist()})); close_agent(a,m)"
        process = subprocess.run([sys.executable, '-c', code, str(checkpoint), str(result_path)], cwd=ROOT, capture_output=True, text=True, timeout=60)
        self.assertEqual(process.returncode, 0, process.stderr)
        child = json.loads(result_path.read_text())
        self.assertEqual(child['prediction'], self.agent.concepts.compose(['nivo'], [.3, -.7]))
        result = self.agent.tick(.1)
        self.assertEqual(child['inquiry'], result['concept_inquiry'])
        self.assertEqual(child['hidden'], self.agent.temporal.hidden.tolist())
        self.assertEqual(result['concept_inquiry']['id'], inquiry_id)
        self.assertEqual(result['concept_inquiry']['concept'], 'unknown')
        self.assertEqual(observed, self.agent.temporal.observations)
        self.assertTrue(all(torch.equal(value, source_digest(memory.blocks[i])) for i, value in enumerate(before)))

    def test_emitted_inquiry_persists_until_taken_and_snapshot_restores_single_owner(self):
        self.agent.request_study([{'concept': 'unknown', 'input': [0., 1.], 'cost': 0.}])
        inquiry = self.agent.tick(.1)['concept_inquiry']
        checkpoint = self.folder / 'mind.pt'
        from scripts.alice_memory.loop_checkpoint import atomic_write
        atomic_write(checkpoint, capture(self.agent))
        restored, mind, _ = load_scheduler(checkpoint)
        self.addCleanup(mind.actor.session.memory.close)
        self.assertIs(restored.agent.mind, mind)
        self.assertIs(restored.agent.words.perception, mind.actor.session.perception)
        self.assertEqual(restored.inquiries[inquiry['id']], inquiry)
        self.assertEqual(restored.take_inquiry(inquiry['id']), inquiry)
        self.assertIsNone(restored.take_inquiry(inquiry['id']))
        self.assertIsNone(restored.tick(.1)['concept_inquiry'])

    def test_persistent_runtime_commits_and_resumes_concepts_and_unacknowledged_inquiry(self):
        from scripts.alice_memory.persistent_runtime import run
        from scripts.alice_memory.runtime_store import RuntimeStore
        teach(self.agent.concepts, 'nivo', [[.7, -.2], [.4, .6]], now=self.agent.clock)
        expected = self.agent.concepts.compose(['nivo'], [.3, -.7])
        self.agent.request_study([{'concept': 'unknown', 'input': [0., 1.], 'cost': 0.}])
        checkpoint, store_path = self.folder / 'mind.pt', self.folder / 'runtime'
        save(checkpoint, self.agent)
        first = run(store_path, checkpoint, seconds=.2)
        second = run(store_path, seconds=.2)
        self.assertEqual(first['phase'], 'stopped')
        self.assertEqual(second['phase'], 'stopped')
        self.assertTrue(second['recovery']['resumed'])
        self.assertEqual(first['concept_inquiries'], second['concept_inquiries'])
        self.assertEqual(len(second['concept_inquiries']), 1)
        with RuntimeStore(store_path) as store:
            restored, mind, _ = load_scheduler(store.candidates()[0][0])
            self.addCleanup(mind.actor.session.memory.close)
            self.assertEqual(restored.concepts.compose(['nivo'], [.3, -.7]), expected)
            self.assertEqual(len(restored.inquiries), 1)


if __name__ == '__main__':
    unittest.main()
