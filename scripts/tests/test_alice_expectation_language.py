"""Expectation/fact separation, real kernel dependence and stale generation."""
import copy
import json
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import torch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.alice_memory.episodic_memory import EpisodicMemory
from scripts.alice_memory.expectation_language import (ExpectationEvidence, ExpectationLanguage,
    GroundedExpectationLanguage, question_from_file, state_digest)
from scripts.alice_memory.grounded_mind import GroundedMind
from scripts.alice_memory.language_input import QuestionPlan
from scripts.alice_memory.neural_semantic_memory import NeuralSemanticMemory
from scripts.alice_memory.semantic_memory import SemanticMemory


class LanguageFixture(ExpectationLanguage):
    def __init__(self):
        super().__init__("http://127.0.0.1:11438", "fixture")
        self.body = None
        self.draft = None
        self.on_generation = None

    def metadata(self):
        return {"size": 1, "digest": "fixture", "name": self.model}

    def admit(self, metadata):
        pass

    def _request(self, path, body=None):
        self.body = copy.deepcopy(body)
        evidence = json.loads(body["messages"][1]["content"].split("\nPERGUNTA:")[0].split("\n", 1)[1])
        draft = self.draft or {"text": "Eu esperaria esse padrão, sem afirmar que aconteceu.",
            "expectations": {} if evidence is None else {evidence["target"]: evidence["value"]},
            "factual_claims": {}, "uncertain": evidence is None}
        if self.on_generation:
            self.on_generation()
        return {"done": True, "done_reason": "stop", "message": {"content": json.dumps(draft)}}


class WordsFixture(torch.nn.Module):
    """Deterministic known lexical cues; sensory learning is evaluated separately."""
    def __init__(self):
        super().__init__()
        self.names = ["vimuq", "torbe", "neva"]
        self.register_buffer("learned", torch.ones(1))

    def cue(self, names):
        if not self.learned.item() or any(name not in self.names for name in names):
            return {"supported": False, "reason": "unsupported_symbols"}
        cue = torch.zeros(4, 4, dtype=torch.float64)
        for name in names:
            field, category = {"vimuq": (0, 0), "torbe": (3, 0), "neva": (1, 0)}[name]
            cue[field, category] = 1
        return {"supported": True, "cue": cue.flatten(), "names": names}


class ExpectationLanguageContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        torch.set_num_threads(1)

    def fixture(self):
        memory = EpisodicMemory(40)
        model = NeuralSemanticMemory(memory, seed=3917)
        model.bank.config["inner_steps"] = 16
        for index in range(24):
            category = index % 2
            cue = torch.nn.functional.one_hot(torch.tensor([category, 0, category, 0]), 4).flatten().double()
            episode = memory.observe(cue, index + 1., True)
            model.consolidate(memory, episode, memory.clock)
        agent = GroundedMind.__new__(GroundedMind)
        agent.agent = SimpleNamespace(semantic=model, clock=memory.clock,
            mind=SimpleNamespace(actor=SimpleNamespace(policy=torch.nn.Identity(),
                session=SimpleNamespace(memory=memory, perception=torch.nn.Identity()))))
        agent.words = WordsFixture()
        return agent, LanguageFixture()

    def query(self, agent, language):
        question = 'Quem você esperaria em "vimuq" em "torbe" com "neva"?'
        plan = QuestionPlan("autor", ("vimuq", "torbe", "neva"), False, "fixture", "fixture", "q", "p", 0.)
        with patch("scripts.alice_memory.expectation_language.LanguageInput.parse", return_value=plan):
            return GroundedExpectationLanguage(agent, language).query(question)

    def test_learned_expectation_is_not_a_factual_claim_or_a_write(self):
        agent, language = self.fixture()
        before = state_digest(agent)
        result = self.query(agent, language)
        self.assertTrue(result["accepted"])
        self.assertEqual(result["proposal"]["expectations"], {"autor": "pai"})
        self.assertEqual(result["proposal"]["factual_claims"], {})
        shape = language.body['format']['properties']['expectations']
        self.assertEqual(shape['properties'], {'autor': {'type': 'string', 'const': 'pai'}})
        self.assertEqual(shape['required'], ['autor'])
        self.assertIs(shape['additionalProperties'], False)
        self.assertNotIn('vimuq', language.body['messages'][1]['content'])
        self.assertNotIn('torbe', language.body['messages'][1]['content'])
        self.assertFalse(result["free_text_verified"])
        self.assertFalse(result["autobiographical_write"])
        self.assertEqual(before, state_digest(agent))
        self.assertNotIn("EVIDÊNCIAS", language.body["messages"][1]["content"])

    def test_erasing_neural_weights_removes_expectation_despite_route_metadata(self):
        agent, language = self.fixture()
        for parameter in agent.semantic.bank.network.parameters():
            parameter.data.zero_()
        result = self.query(agent, language)
        self.assertTrue(result["accepted"])
        self.assertIsNone(result["evidence"])
        self.assertEqual(result["proposal"]["expectations"], {})
        self.assertTrue(result["proposal"]["uncertain"])

    def test_unknown_names_and_unknown_targets_do_not_query_kernel(self):
        agent, _ = self.fixture()
        with patch.object(agent.semantic, "predict", wraps=agent.semantic.predict) as predictor:
            self.assertIsNone(agent.expect_names(["unknownsymbol"], 2)["prediction"])
            self.assertEqual(agent.expect_names(["vimuq"], 1)["reason"], "target_not_learned")
            predictor.assert_not_called()
        for field in (-1, 4, True):
            with self.assertRaises(ValueError):
                agent.expect_names(["vimuq"], field)

    def test_language_cannot_turn_a_prediction_into_a_fact_or_replace_its_value(self):
        for draft in ({"text": "Foi a mãe", "expectations": {"autor": "mae"}, "factual_claims": {}, "uncertain": False},
                      {"text": "Foi o pai", "expectations": {"autor": "pai"}, "factual_claims": {"autor": "pai"}, "uncertain": False},
                      {"text": "Não sei", "expectations": {}, "factual_claims": {}, "uncertain": True}):
            agent, language = self.fixture()
            language.draft = draft
            result = self.query(agent, language)
            self.assertFalse(result["accepted"])
            self.assertIsNone(result["proposal"])

    def test_revision_during_generation_invalidates_even_unchanged_output(self):
        agent, language = self.fixture()
        memory = agent.mind.actor.session.memory
        language.on_generation = lambda: memory.blocks[0].revisions.add_(1)
        result = self.query(agent, language)
        self.assertFalse(result["accepted"])
        self.assertFalse(result["state_unchanged"])
        self.assertIsNone(result["proposal"])
        self.assertEqual(result["reason"], "state_changed_during_generation")

    def test_lexical_update_during_generation_invalidates_delivery(self):
        agent, language = self.fixture()
        language.on_generation = lambda: agent.words.learned.zero_()
        self.assertFalse(self.query(agent, language)["accepted"])

    def test_changed_witness_weights_are_checked_again_without_a_metadata_update(self):
        agent, language = self.fixture()
        expectation = agent.expect_names(["vimuq", "torbe", "neva"], 2)["prediction"]
        episode = expectation["source_episode"]
        language.on_generation = lambda: agent.mind.actor.session.memory.blocks[episode].banks[-1].weights.zero_()
        self.assertFalse(self.query(agent, language)["accepted"])

    def test_bridge_checks_proposal_again_instead_of_trusting_worker_flag(self):
        agent, language = self.fixture()
        original = language.propose_expectation
        def forged(question, evidence):
            return replace(original(question, evidence), expectations={"autor": "mae"}, evidence_sha256="0" * 64)
        language.propose_expectation = forged
        self.assertFalse(self.query(agent, language)["accepted"])

    def test_empty_evidence_cannot_assert_certainty(self):
        language = LanguageFixture()
        language.draft = {"text": "Eu sei", "expectations": {}, "factual_claims": {}, "uncertain": False}
        self.assertFalse(language.propose_expectation("Quem?", None).structured_expectations_supported)

    def test_default_conditional_backend_remains_usable_without_neural_reason_fields(self):
        agent, language = self.fixture()
        memory = agent.mind.actor.session.memory
        agent.agent.semantic = SemanticMemory(memory.capacity, forgetting=1.)
        for episode in range(len(memory.blocks)):
            agent.semantic.consolidate(memory, episode, memory.clock)
        result = self.query(agent, language)
        self.assertTrue(result["accepted"])
        self.assertEqual(result["proposal"]["expectations"], {"autor": "pai"})

    def test_evidence_cannot_claim_calibration_or_a_value_outside_the_learned_domain(self):
        evidence = ExpectationEvidence("autor", "pai", .9, "observed_complete_cue", "a" * 64)
        for altered in (replace(evidence, confidence_is_calibrated=True), replace(evidence, value="amigo"),
                        replace(evidence, confidence=True), replace(evidence, state_sha256="bad"),
                        replace(evidence, kind="episodic_fact")):
            with self.assertRaises(ValueError):
                altered.validate()

    def test_question_file_preserves_portuguese_quotes_and_rejects_oversize_before_inference(self):
        parent = ROOT / "bin" / "AliceWordTests"
        parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=parent) as folder:
            path = Path(folder) / "question.txt"
            question = 'Quem você esperaria em "vimuq"?'
            path.write_text(question, encoding="utf-8-sig")
            self.assertEqual(question_from_file(path), question)
            path.write_text("x" * 16004, encoding="utf-8")
            with self.assertRaises(ValueError):
                question_from_file(path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
