"""GPU admission and unchanged language contracts without a model or GPU request."""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from scripts.alice_memory.language import AdmissionDeferred, LocalLanguage, MemoryEvidence
from scripts.alice_memory.language_gpu_worker import GIB, GpuLanguage, GpuExpectationLanguage, validate_snapshot
from scripts.alice_memory.expectation_protocol import ExpectationEvidence
from scripts.alice_memory.language_input import LanguageInput
from scripts.alice_memory.language_worker import execute
from scripts.alice_memory.language_process import LanguageProcess


def snapshot(ram=8., vram=2.):
    return {"ramTotalGb": 32., "ramUsedGb": ram, "vramTotalGb": 16., "vramUsedGb": vram,
            "gpuName": "measured-adapter", "capturedAt": datetime.now(timezone.utc).isoformat()}


class GpuLanguageTests(unittest.TestCase):
    def setUp(self):
        self.language = GpuLanguage("http://127.0.0.1:11438", "fixture")
        self.metadata = {"size": 3 * GIB, "name": "fixture", "digest": "fixture-digest"}

    def test_gpu_requires_headroom_in_both_global_budgets(self):
        for ram, vram, reason in ((21., 2., "RAM"), (8., 9., "VRAM")):
            with self.subTest(budget=reason), patch("scripts.alice_memory.language_gpu_worker.resource_snapshot", return_value=snapshot(ram, vram)):
                with self.assertRaisesRegex(AdmissionDeferred, reason) as caught:
                    self.language.admit(self.metadata)
                self.assertEqual(caught.exception.reserve_bytes, 4 * GIB)
        with patch("scripts.alice_memory.language_gpu_worker.resource_snapshot", return_value=snapshot(20., 8.)):
            self.language.admit(self.metadata)  # Exactly 75%, including the full cold reserve.

    def test_gpu_expectation_uses_measured_admission_and_keeps_factual_claims_empty(self):
        language = GpuExpectationLanguage("http://127.0.0.1:11438", "fixture")
        response = {"done": True, "message": {"content": json.dumps({"text": "Eu esperaria o pai.",
                    "expectations": {"autor": "pai"}, "factual_claims": {}, "uncertain": False})}}
        evidence = ExpectationEvidence("autor", "pai", .9, "observed_complete_cue", "a" * 64)
        with patch.object(language, "metadata", return_value=self.metadata), \
             patch("scripts.alice_memory.language_gpu_worker.resource_snapshot", return_value=snapshot()), \
             patch.object(LocalLanguage, "_request", return_value=response) as request:
            proposal = language.propose_expectation("Quem você esperaria?", evidence)
        self.assertTrue(proposal.structured_expectations_supported)
        self.assertEqual(proposal.factual_claims, {})
        self.assertTrue(language.admission_record["admitted"])
        self.assertEqual(request.call_args.args[1]["options"]["num_gpu"], -1)

    def test_absent_invalid_or_stale_vram_cannot_be_treated_as_free(self):
        malformed = []
        for field, value in (("vramUsedGb", None), ("vramUsedGb", -1), ("vramUsedGb", float("nan")),
                             ("vramUsedGb", 17), ("vramTotalGb", True), ("ramTotalGb", 0), ("gpuName", "")):
            sample = snapshot()
            sample[field] = value
            malformed.append(sample)
        for offset in (-6, 6):
            sample = snapshot()
            sample["capturedAt"] = (datetime.now(timezone.utc) + timedelta(seconds=offset)).isoformat()
            malformed.append(sample)
        for sample in malformed:
            with self.subTest(sample=sample), patch("scripts.alice_memory.language_gpu_worker.resource_snapshot", return_value=sample), \
                 patch("scripts.alice_memory.language_gpu_worker.physical_memory", return_value={"used_bytes": 8 * GIB, "total_bytes": 32 * GIB}):
                with self.assertRaisesRegex(AdmissionDeferred, "telemetry unavailable"):
                    self.language.admit(self.metadata)

    def test_telemetry_process_failure_is_a_deferral_and_never_calls_chat(self):
        operation = {"endpoint": self.language.endpoint, "model": "fixture", "stage": "parse", "token": "a" * 32,
                     "question": 'Quem estava em "zilu"?', "evidence": (), "view": "current", "required": []}
        with patch.object(LocalLanguage, "metadata", return_value=self.metadata), \
             patch("scripts.alice_memory.language_gpu_worker.resource_snapshot", side_effect=TimeoutError("measured probe timeout")), \
             patch("scripts.alice_memory.language_gpu_worker.physical_memory", return_value={"used_bytes": 8 * GIB, "total_bytes": 32 * GIB}), \
             patch.object(LocalLanguage, "_request") as request:
            result = execute(operation, GpuLanguage)
        self.assertEqual(result["status"], "deferred")
        self.assertIn("probe timeout", result["value"]["reason"])
        request.assert_not_called()

    def test_gpu_changes_only_placement_and_keeps_parser_evidence_free(self):
        draft = {"field": "autor", "names": ["zilu"], "uncertain": False}
        with patch.object(LocalLanguage, "metadata", return_value=self.metadata), \
             patch("scripts.alice_memory.language_gpu_worker.resource_snapshot", return_value=snapshot()), \
             patch.object(LocalLanguage, "_request", return_value={"done": True, "message": {"content": json.dumps(draft)}}) as request:
            plan = LanguageInput(self.language).parse('Quem estava em "zilu"?')
        payload = request.call_args.args[1]
        self.assertEqual(payload["options"]["num_gpu"], -1)
        self.assertEqual(payload["options"]["num_ctx"], 1024)
        self.assertEqual(payload["keep_alive"], 0)
        self.assertFalse(plan.meanings_supplied_to_parser)
        self.assertNotIn("EVIDÊNCIAS", payload["messages"][1]["content"])

    def test_gpu_does_not_relax_factual_validation(self):
        evidence = (MemoryEvidence("episode", "current", (("autor", "mae"),), 1.),)
        draft = {"text": "Foi o pai.", "claims": {"autor": "pai"}, "uncertain": False}
        with patch.object(LocalLanguage, "metadata", return_value=self.metadata), \
             patch("scripts.alice_memory.language_gpu_worker.resource_snapshot", return_value=snapshot()), \
             patch.object(LocalLanguage, "_request", return_value={"done": True, "message": {"content": json.dumps(draft)}}):
            proposal = self.language.propose("Quem fez?", evidence)
        self.assertFalse(proposal.structured_claims_supported)
        self.assertIn("unsupported_claim:autor", proposal.violations)
        self.assertFalse(proposal.free_text_verified)

    def test_request_placement_copy_does_not_mutate_cpu_payload(self):
        payload = {"options": {"num_gpu": 0, "num_ctx": 1024}, "messages": []}
        original = copy.deepcopy(payload)
        with patch.object(LocalLanguage, "_request", return_value={}):
            self.language._request("/api/chat", payload)
        self.assertEqual(payload, original)

    def test_cpu_default_and_gpu_opt_in_reject_fake_backend(self):
        from scripts.alice_memory.language_loop_experiment import run
        from pathlib import Path
        with self.assertRaisesRegex(ValueError, "installed backend"):
            run(Path("missing.pt"), Path("missing.json"), Path("missing"), backend="test", device="gpu")
        with patch("scripts.alice_memory.language.physical_memory", return_value={"used_bytes": 8 * GIB, "total_bytes": 32 * GIB}):
            LocalLanguage(self.language.endpoint).admit(self.metadata)

    def test_nonretained_gpu_admission_record_is_cleaned_with_owned_exchange(self):
        from pathlib import Path
        with tempfile.TemporaryDirectory(prefix="AliceGpuCleanup-") as root:
            worker = LanguageProcess.__new__(LanguageProcess)
            worker.root = Path(root).resolve()
            worker.folder = worker.root / "owned"
            worker.folder.mkdir()
            worker.request = worker.folder / "request.json"
            worker.output = worker.folder / "result.json"
            worker.process, worker.retain_files = None, False
            (worker.folder / "gpu-admission.json").write_text("{}", encoding="utf-8")
            worker.close()
            self.assertFalse(worker.folder.exists())


if __name__ == "__main__":
    unittest.main()
