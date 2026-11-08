"""Grounded-language boundary, evaluator isolation and interruption journal."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.alice_memory.grounded_language import read_questions, run
from scripts.alice_memory.language import LanguageProposal
from scripts.alice_memory.language_input import QuestionPlan


class GroundedLanguageTests(unittest.TestCase):
    def setUp(self):
        parent = ROOT / "bin" / "AliceWordTests"
        parent.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=parent)
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)
        self.checkpoint = self.folder / "agent.pt"
        self.checkpoint.write_bytes(b"mock checkpoint for boundary isolation")
        self.questions = self.folder / "questions.json"

    def case(self, name="unknown"):
        return {"case": name, "question": 'Quem estava envolvido durante "vimuq" em "unknownsymbol"?',
                "field": "autor", "view": "current", "window": [1., 2.], "expected": {}}

    def write_cases(self, cases):
        self.questions.write_text(json.dumps({"format": 1, "cases": cases}), encoding="utf-8")

    def plan(self, field="autor", names=("vimuq", "unknownsymbol"), uncertain=False):
        return QuestionPlan(field, names, uncertain, "fixture", "digest", "question", "prompt", .1)

    def proposal(self):
        return LanguageProposal("Não sei.", {}, True, True, (), "fixture", "digest", "evidence", "prompt", .1)

    def run_mock(self, agent, plans, proposals, digests=("same", "same")):
        with patch("scripts.alice_memory.grounded_language.load", return_value=agent), \
             patch("scripts.alice_memory.grounded_language.learned_digest", side_effect=digests), \
             patch("scripts.alice_memory.grounded_language.LanguageInput.parse", side_effect=plans) as parser, \
             patch("scripts.alice_memory.grounded_language.LocalLanguage.propose", side_effect=proposals) as proposer:
            report = run("http://127.0.0.1:11438", "fixture", self.checkpoint, self.questions, self.folder / "out")
        return report, parser, proposer

    def test_unknown_meaning_never_queues_action_or_supplies_oracle_facts(self):
        self.write_cases([self.case()])
        agent = MagicMock()
        agent.query_names.return_value = {"grounding_supported": False, "reason": "unsupported_symbols", "result": None}
        report, parser, proposer = self.run_mock(agent, [self.plan()], [self.proposal()])
        self.assertTrue(report["accepted"])
        parser.assert_called_once_with(self.case()["question"])
        agent.query_names.assert_called_once_with(["vimuq", "unknownsymbol"], "current", (1., 2.))
        agent.request_names.assert_not_called()
        agent.tick.assert_not_called()
        self.assertEqual(proposer.call_args.args[1], ())
        agent.mind.actor.session.memory.close.assert_called_once()

    def test_uncertain_language_plan_does_not_query_memory(self):
        case = self.case("identity")
        case.update(question="Você gosta de mim?", field="unknown", window=None)
        self.write_cases([case])
        agent = MagicMock()
        report, _, proposer = self.run_mock(agent, [self.plan("unknown", (), True)], [self.proposal()])
        self.assertTrue(report["accepted"])
        agent.query_names.assert_not_called()
        self.assertEqual(proposer.call_args.args[1], ())

    def test_weight_change_prevents_acceptance_even_with_valid_answers(self):
        self.write_cases([self.case()])
        agent = MagicMock()
        agent.query_names.return_value = {"grounding_supported": False, "result": None}
        report, _, _ = self.run_mock(agent, [self.plan()], [self.proposal()], ("before", "after"))
        self.assertTrue(report["completed"])
        self.assertFalse(report["accepted"])
        self.assertFalse(report["learned_weights_unchanged"])

    def test_interrupt_retains_first_case_and_closes_memory(self):
        self.write_cases([self.case("first"), self.case("second")])
        agent = MagicMock()
        agent.query_names.return_value = {"grounding_supported": False, "result": None}
        with self.assertRaises(KeyboardInterrupt):
            self.run_mock(agent, [self.plan(), self.plan()], [self.proposal(), KeyboardInterrupt()])
        report = json.loads((self.folder / "out" / "report.json").read_text(encoding="utf-8"))
        self.assertEqual(report["completed_cases"], 1)
        self.assertFalse(report["completed"])
        self.assertFalse(report["accepted"])
        self.assertIn("KeyboardInterrupt", report["fatal_error"])
        agent.mind.actor.session.memory.close.assert_called_once()

    def test_invalid_evaluator_bundle_is_rejected_before_loading_models(self):
        for changes in ({"window": [2., 1.]}, {"window": [True, 2.]}, {"window": "12"},
                        {"expected": {"vinculo": "amigo"}}, {"field": "vinculo"}):
            self.write_cases([{**self.case(), **changes}])
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                read_questions(self.questions)


if __name__ == "__main__":
    unittest.main(verbosity=2)
