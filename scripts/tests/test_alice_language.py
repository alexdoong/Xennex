"""Language provenance/contract checks without loading a model or opening sockets."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.alice_memory.language import LocalLanguage, MemoryEvidence, LanguageProposal
from scripts.alice_memory.episodic_language import run as run_episodic, write_report


class LanguageBridgeTests(unittest.TestCase):
    def evidence(self, view: str = "current", author: str = "mae") -> MemoryEvidence:
        return MemoryEvidence("synthetic-episode", view, (("autor", author),), 1.0)

    def request(self, draft: dict, info: dict | None = None):
        def response(path, body=None):
            if path == "/api/tags":
                return {"models": [{"name": "gemma3:4b", "size": 3338792448, "digest": "test-local-digest"}]}
            if path == "/api/show":
                return info if info is not None else {"capabilities": ["completion"]}
            self.payload = body
            return {"done": True, "done_reason": "stop", "message": {"content": json.dumps(draft)}}
        return response

    def propose(self, draft, evidence, info=None):
        with patch.object(LocalLanguage, "_request", side_effect=self.request(draft, info)), \
             patch("scripts.alice_memory.language.physical_memory", return_value={"total_bytes": 32e9, "used_bytes": 12e9}):
            return LocalLanguage("http://127.0.0.1:11438").propose("Quem preparou a comida?", evidence)

    def test_current_recall_has_provenance_without_becoming_a_weight_update(self) -> None:
        result = self.propose({"text": "A mãe preparou.", "claims": {"autor": "mae"}, "uncertain": False},
                              (self.evidence("initial", "pai"), self.evidence()))
        self.assertTrue(result.structured_claims_supported)
        self.assertFalse(result.free_text_verified)
        self.assertEqual(result.model_digest, "test-local-digest")
        self.assertEqual(len(result.evidence_sha256), 64)
        self.assertEqual(self.payload["options"]["num_gpu"], 0)
        self.assertEqual(self.payload["keep_alive"], 0)
        self.assertNotIn('"pai"', self.payload["messages"][1]["content"])
        self.assertIsInstance(self.payload["format"], dict)

    def test_initial_interpretation_is_available_only_when_explicitly_selected(self) -> None:
        draft = {"text": "Inicialmente foi atribuído ao pai.", "claims": {"autor": "pai"}, "uncertain": False}
        with patch.object(LocalLanguage, "_request", side_effect=self.request(draft)), \
             patch("scripts.alice_memory.language.physical_memory", return_value={"total_bytes": 32e9, "used_bytes": 12e9}):
            result = LocalLanguage("http://127.0.0.1:11438").propose(
                "Qual era a interpretação inicial?", (self.evidence("initial", "pai"), self.evidence()), "initial")
        self.assertTrue(result.structured_claims_supported)
        self.assertNotIn('"mae"', self.payload["messages"][1]["content"])

    def test_old_interpretation_is_not_accepted_as_current(self) -> None:
        result = self.propose({"text": "O pai preparou.", "claims": {"autor": "pai"}, "uncertain": False},
                              (self.evidence("initial", "pai"), self.evidence()))
        self.assertFalse(result.structured_claims_supported)
        self.assertIn("unsupported_claim:autor", result.violations)

    def test_empty_evidence_requires_uncertainty_and_no_personal_claim(self) -> None:
        good = self.propose({"text": "Não sei.", "claims": {}, "uncertain": True}, ())
        bad = self.propose({"text": "Seu pai.", "claims": {"autor": "pai"}, "uncertain": False}, ())
        self.assertTrue(good.structured_claims_supported)
        self.assertFalse(bad.structured_claims_supported)
        self.assertIn("unsubstantiated_certainty", bad.violations)

    def test_remote_models_and_non_loopback_endpoints_are_rejected(self) -> None:
        for endpoint in ("https://127.0.0.1:11438", "http://localhost:11438", "http://127.0.0.1.evil:11438",
                         "http://user:pass@127.0.0.1:11438", "http://127.0.0.1:11438/?redirect=x"):
            with self.assertRaises(ValueError):
                LocalLanguage(endpoint)
        with self.assertRaisesRegex(ValueError, "Cloud"):
            self.propose({"text": "", "claims": {}, "uncertain": True}, (),
                         {"remote_host": "cloud.example", "capabilities": ["completion"]})

    def test_incomplete_or_malformed_generation_does_not_get_a_valid_proposal(self) -> None:
        with self.assertRaisesRegex(ValueError, "contract"):
            self.propose({"text": "Hello", "claims": {}, "uncertain": True, "control": "execute"}, ())

    def test_pressure_blocks_inference_before_chat_request(self) -> None:
        requests = []
        response = self.request({"text": "", "claims": {}, "uncertain": True})
        def record(path, body=None):
            requests.append(path)
            return response(path, body)
        with patch.object(LocalLanguage, "_request", side_effect=record), \
             patch("scripts.alice_memory.language.physical_memory", return_value={"total_bytes": 32e9, "used_bytes": 24e9}):
            with self.assertRaisesRegex(RuntimeError, "RAM budget"):
                LocalLanguage("http://127.0.0.1:11438").propose("Pergunta", ())
        self.assertNotIn("/api/chat", requests)

    def test_explicit_experimental_ram_budget_admits_tiny_model_without_changing_default(self):
        from scripts.alice_memory.language import AdmissionDeferred
        metadata = {'size': 1000000000}
        with patch('scripts.alice_memory.language.physical_memory', return_value={'total_bytes': 32e9, 'used_bytes': 26e9}):
            with self.assertRaises(AdmissionDeferred):
                LocalLanguage('http://127.0.0.1:11438').admit(metadata)
            LocalLanguage('http://127.0.0.1:11438', ram_fraction=.9).admit(metadata)
        for invalid in (True, .49, .91, float('nan')):
            with self.assertRaises(ValueError):
                LocalLanguage('http://127.0.0.1:11438', ram_fraction=invalid)

    def test_different_episode_evidence_cannot_be_mixed_in_a_flat_claim(self) -> None:
        other = MemoryEvidence("other-episode", "current", (("autor", "colega"),), 1.0)
        with self.assertRaisesRegex(ValueError, "one current episode"):
            LocalLanguage("http://127.0.0.1:11438").propose("Pergunta", (self.evidence(), other))

    def test_omission_of_an_available_requested_fact_is_not_a_supported_answer(self) -> None:
        draft = {"text": "Não foi o pai.", "claims": {}, "uncertain": False}
        with patch.object(LocalLanguage, "_request", side_effect=self.request(draft)), \
             patch("scripts.alice_memory.language.physical_memory", return_value={"total_bytes": 32e9, "used_bytes": 12e9}):
            result = LocalLanguage("http://127.0.0.1:11438").propose(
                "Foi o pai? Quem foi?", (self.evidence(),), required_attributes=("autor",))
        self.assertFalse(result.structured_claims_supported)
        self.assertIn("omitted_claim:autor", result.violations)

    def test_unknown_relationship_attributes_are_not_turned_into_known_facts(self) -> None:
        with patch.object(LocalLanguage, "_request", side_effect=self.request(
                {"text": "Não tenho evidência de vínculo.", "claims": {}, "uncertain": True})), \
             patch("scripts.alice_memory.language.physical_memory", return_value={"total_bytes": 32e9, "used_bytes": 12e9}):
            result = LocalLanguage("http://127.0.0.1:11438").propose(
                "Você gosta de mim?", (), required_attributes=("vinculo",))
        self.assertTrue(result.structured_claims_supported)
        self.assertEqual(result.claims, {})

    def test_requested_attributes_are_validated_before_model_access(self) -> None:
        with patch.object(LocalLanguage, "metadata") as metadata:
            for keys in (["autor"], ("autor", "autor"), ("",)):
                with self.assertRaises(ValueError):
                    LocalLanguage("http://127.0.0.1:11438").propose("Pergunta", (), required_attributes=keys)
            metadata.assert_not_called()


class ProbeJournalTests(unittest.TestCase):
    def folder(self):
        parent = ROOT / "bin" / "AliceLanguageTests"
        parent.mkdir(parents=True, exist_ok=True)
        temporary = tempfile.TemporaryDirectory(dir=parent)
        self.addCleanup(temporary.cleanup)
        return Path(temporary.name)

    def bundle(self):
        return {"checkpoint_sha256": "a" * 64, "cue_sha256": "b" * 64,
                "window": [1., 2.], "unwindowed_ambiguous": True, "unwindowed_evidence": (),
                "evidence": (MemoryEvidence("episode", "initial", (("autor", "pai"),), 1.),
                             MemoryEvidence("episode", "current", (("autor", "mae"), ("impressao", "agradavel")), 1.))}

    def draft(self, claims):
        return LanguageProposal("Texto a revisar.", claims, not claims, True, (),
                                "mock", "digest", "a" * 64, "b" * 64, .01)

    def test_interrupted_third_case_preserves_two_completed_cases_without_success(self):
        folder = self.folder() / "interrupted"
        good = self.draft({"autor": "mae", "impressao": "agradavel"})
        with patch.object(LocalLanguage, "propose", side_effect=[good, good, KeyboardInterrupt()]):
            with self.assertRaises(KeyboardInterrupt):
                run_episodic("http://127.0.0.1:11438", "mock", self.bundle(), folder)
        report = json.loads((folder / "report.json").read_text(encoding="utf-8"))
        self.assertEqual([p["case"] for p in report["proposals"]], ["neutral", "leading"])
        self.assertEqual(report["completed_cases"], 2)
        self.assertFalse(report["completed"])
        self.assertFalse(report["accepted"])
        self.assertEqual(list(folder.glob("*.tmp")), [])

    def test_completion_requires_all_cases_and_each_previous_case_is_persisted(self):
        folder = self.folder() / "completed"
        observed = []
        def propose(question, evidence, view, required):
            report = json.loads((folder / "report.json").read_text(encoding="utf-8"))
            observed.append(report["completed_cases"])
            self.assertFalse(report["accepted"])
            available = {key: value for item in evidence if item.interpretation == view for key, value in item.attributes}
            return self.draft({key: available[key] for key in required if key in available})
        with patch.object(LocalLanguage, "propose", side_effect=propose):
            result = run_episodic("http://127.0.0.1:11438", "mock", self.bundle(), folder)
        self.assertEqual(observed, list(range(7)))
        self.assertTrue(result["completed"])
        self.assertTrue(result["accepted"])
        self.assertEqual(result["completed_cases"], 7)
        self.assertEqual(json.loads((folder / "report.json").read_text(encoding="utf-8")),
                         json.loads(json.dumps(result)))

    def test_failed_report_replace_keeps_previous_complete_json_and_cleans_temporary(self):
        folder = self.folder()
        path = folder / "report.json"
        previous = {"completed_cases": 2, "accepted": False}
        write_report(path, previous)
        with patch("scripts.alice_memory.episodic_language.os.replace", side_effect=OSError("injected write failure")):
            with self.assertRaises(OSError):
                write_report(path, {"completed_cases": 3, "accepted": False})
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), previous)
        self.assertEqual(list(folder.glob("*.tmp")), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
