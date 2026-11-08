"""Optional native RLS interop checks; .NET only, no sensors or installed LLM."""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import torch

from scripts.alice_memory.native_experiment import evaluate, state
from scripts.alice_memory.online_memory import OnlineMemory

ROOT = Path(__file__).resolve().parents[2]


@unittest.skipUnless(shutil.which("dotnet"), "Native optional laboratory requires .NET SDK")
class NativeMemoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        result = subprocess.run(["dotnet", "build", str(ROOT / "scripts/tests/AliceRuntimeTests/AliceRuntimeTests.csproj"),
                                 "-c", "Release", "--nologo"], cwd=ROOT, capture_output=True, text=True, timeout=120,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if result.returncode:
            raise RuntimeError(result.stdout + result.stderr)
        cls.runtime = ROOT / "bin/AliceRuntimeTests/net8.0/AliceRuntimeTests.dll"
        torch.set_num_threads(1)

    def call(self, fixture):
        with tempfile.TemporaryDirectory(prefix="AliceNative-") as directory:
            path = Path(directory)
            (path / "input.json").write_text(json.dumps(fixture, allow_nan=False), encoding="utf-8")
            result = subprocess.run(["dotnet", str(self.runtime), str(path / "input.json"), str(path / "output.json")],
                                    cwd=ROOT, capture_output=True, text=True, timeout=30,
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            output = json.loads((path / "output.json").read_text()) if (path / "output.json").exists() else None
            return result, output

    def case(self, size=17, values=4):
        generator = torch.Generator().manual_seed(83)
        vectors = torch.randn(24, size, generator=generator, dtype=torch.float64)
        vectors /= vectors.norm(dim=1, keepdim=True)
        targets = torch.randn(24, values, generator=generator, dtype=torch.float64)
        return {"name": "independent-random", "initial": state(OnlineMemory(size, values)),
                "steps": [{"key": key.tolist(), "value": value.tolist(), "strength": (.3, 1, 4)[index % 3]}
                          for index, (key, value) in enumerate(zip(vectors, targets))],
                "queries": vectors[:8].tolist()}

    def test_native_internal_guards_and_checkpoint(self):
        result = subprocess.run(["dotnet", str(self.runtime), "--self-test"], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_independent_weighted_batch_and_resumed_update_both_shapes(self):
        for size, values in ((17, 4), (256, 32)):
            with self.subTest(shape=(size, values)):
                case = self.case(size, values)
                result, output = self.call({"format": 1, "banks": [case]})
                self.assertEqual(result.returncode, 0, result.stderr)
                check = evaluate(case, output["banks"][0])
                self.assertTrue(check["passed"], check)
                self.assertEqual(output["banks"][0]["measurement"]["allocatedBytes"], 0)

    def test_checkpoint_schema_has_no_examples(self):
        result, output = self.call({"format": 1, "banks": [self.case()]})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(set(output["banks"][0]["state"]), {"keySize", "valueSize", "weights", "precision", "writes"})

    def test_wrong_shape_strength_and_unknown_fields_rejected(self):
        for kind in ("shape", "strength", "unknown"):
            with self.subTest(kind=kind):
                case = self.case()
                if kind == "shape":
                    case["steps"][0]["key"] = [1]
                elif kind == "strength":
                    case["steps"][0]["strength"] = -1
                else:
                    case["secretExtra"] = 2
                result, output = self.call({"format": 1, "banks": [case]})
                self.assertEqual(result.returncode, 1)
                self.assertIsNone(output)

    def test_null_checkpoint_and_nonpositive_covariance_rejected(self):
        for kind in ("null", "covariance"):
            with self.subTest(kind=kind):
                case = self.case()
                if kind == "null":
                    case["initial"]["weights"] = None
                else:
                    case["initial"]["precision"][0] = -1
                result, output = self.call({"format": 1, "banks": [case]})
                self.assertEqual(result.returncode, 1)
                self.assertIsNone(output)


if __name__ == "__main__":
    unittest.main()
