"""Question plans cannot insert definitions or facts into the learning loop."""
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.alice_memory.language import LocalLanguage
from scripts.alice_memory.language_input import LanguageInput, references


class QuestionInputTests(unittest.TestCase):
    def parse(self, draft, question='Quem estava envolvido durante "vimuq" em “torbe”?', **response):
        language = LocalLanguage("http://127.0.0.1:11438")
        metadata = {"name": language.model, "size": 100, "digest": "fixture"}
        payload = {"done": True, "done_reason": "stop", "message": {"content": json.dumps(draft)}, **response}
        with patch.object(language, "metadata", return_value=metadata), patch.object(language, "admit") as admission, patch.object(language, "_request", return_value=payload) as request:
            plan = LanguageInput(language).parse(question)
        admission.assert_called_once_with(metadata)
        return plan, request.call_args.args[1]

    def test_literal_references_and_grammar_without_definitions(self):
        plan, body = self.parse({"field": "autor", "names": ["TORBE", "vimuq"], "uncertain": False})
        self.assertEqual((plan.field, plan.names), ("autor", ("torbe", "vimuq")))
        self.assertFalse(plan.meanings_supplied_to_parser)
        self.assertEqual(body["messages"][1]["content"], 'Quem estava envolvido durante "vimuq" em “torbe”?')
        self.assertNotIn("vimuq", body["messages"][0]["content"])
        self.assertNotIn("evidence", body)
        self.assertEqual((body["keep_alive"], body["options"]["num_gpu"]), (0, 0))
        self.assertEqual(body['format']['properties']['names']['const'], ['vimuq', 'torbe'])

    def test_omitted_invented_and_duplicate_references_rejected(self):
        for names in (["vimuq"], ["vimuq", "torbe", "pai"], ["vimuq", "torbe", "TORBE"]):
            with self.subTest(names=names), self.assertRaises(ValueError):
                self.parse({"field": "autor", "names": names, "uncertain": False})

    def test_missing_evidence_is_a_question_hypothesis_not_a_fact(self):
        plan, _ = self.parse({"field": "unknown", "names": [], "uncertain": True}, "Você gosta de mim?")
        self.assertTrue(plan.uncertain)
        with self.assertRaises(ValueError):
            self.parse({"field": "autor", "names": [], "uncertain": False}, "Quem estava envolvido?")

    def test_malformed_and_incomplete_outputs_rejected(self):
        for draft in ({"field": "autor", "names": ["vimuq", "torbe"], "uncertain": False, "fact": "pai"},
                      {"field": [], "names": [], "uncertain": True},
                      {"field": "autor", "names": "vimuq", "uncertain": False},
                      {"field": "autor", "names": ["vimuq", "torbe"], "uncertain": 1}):
            with self.subTest(draft=draft), self.assertRaises(ValueError):
                self.parse(draft)
        with self.assertRaises(ValueError):
            self.parse({"field": "autor", "names": ["vimuq", "torbe"], "uncertain": False}, done_reason="length")

    def test_input_bounds_and_quotes_checked_before_inference(self):
        self.assertEqual(references('"VIMUQ" e “vimuq”'), ["vimuq"])
        for question in ('"vimuq', '“vimuq"', '"duas palavras"', "a" * 4001,
                         " ".join('"name' + str(i) + '"' for i in range(9))):
            with self.subTest(question=question[:40]), self.assertRaises(ValueError):
                references(question)

    def test_question_parser_shares_ram_admission(self):
        language = LocalLanguage("http://127.0.0.1:11438")
        with patch.object(language, "metadata", return_value={"size": 1000}), patch("scripts.alice_memory.language.physical_memory", return_value={"total_bytes": 1000, "used_bytes": 950}), patch.object(language, "_request") as request:
            with self.assertRaises(RuntimeError):
                LanguageInput(language).parse('Quem estava com "vimuq"?')
            request.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
