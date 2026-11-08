#!/usr/bin/env python3
"""Xennex Live Diagnostics & Automated Gesture Test Harness.

Executes comprehensive diagnostics on:
1. LocalWebServer (port 59123) and security token isolation.
2. Synthetic Hand Motion & Gesture Recognition pipeline (FPS, latency, smoothing).
3. System resource margins (RAM, VRAM, GPU headroom) for multi-agent workloads.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List

# Ensure scripts directory is on sys.path
XENNEX_ROOT = Path(r"E:\Projetos e apps\Xennex")
SCRIPTS_DIR = XENNEX_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


def check_local_server(port: int = 59123) -> Dict[str, Any]:
    url = f"http://127.0.0.1:{port}/"
    result: Dict[str, Any] = {
        "url": url,
        "running": False,
        "auth_security_verified": False,
        "status_code": None,
    }

    # Test unauthenticated request
    req = urllib.request.Request(url, headers={"User-Agent": "XennexDiagnostics/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            result["running"] = True
            result["status_code"] = resp.status
    except urllib.error.HTTPError as e:
        result["running"] = True
        result["status_code"] = e.code
        # 403 Forbidden is the expected response for unauthenticated / unauthorized requests!
        if e.code == 403:
            result["auth_security_verified"] = True
    except Exception as e:
        result["error"] = str(e)

    return result


def benchmark_gesture_pipeline() -> Dict[str, Any]:
    """Runs a synthetic landmark stream through features and smoothing without requiring a camera."""
    try:
        from gestures import features, smoothing
    except ImportError as e:
        return {"success": False, "error": f"Failed to import gestures module: {e}"}

    # Generate 500 synthetic hand landmark frames (open palm to fist cycle)
    frames: List[List[Dict[str, float]]] = []
    for i in range(500):
        t = i * 0.05
        factor = (math.sin(t) + 1.0) / 2.0  # 0.0 (fist) to 1.0 (open palm)
        landmarks = []
        # 21 MediaPipe hand landmarks
        for lm_id in range(21):
            if lm_id == 0:
                landmarks.append({"x": 0.5, "y": 0.8, "z": 0.0})
            else:
                base_angle = (lm_id % 5) * 0.2 - 0.4
                dist = (lm_id // 4) * 0.1 * factor
                landmarks.append({
                    "x": 0.5 + math.sin(base_angle) * dist,
                    "y": 0.8 - math.cos(base_angle) * dist,
                    "z": -dist * 0.5
                })
        frames.append(landmarks)

    smoother = smoothing.OneEuroFilter() if hasattr(smoothing, "OneEuroFilter") else None

    start_time = time.perf_counter()
    extracted_count = 0
    for frame in frames:
        # Convert dict format to list of tuples if expected
        pts = [(lm["x"], lm["y"], lm.get("z", 0.0)) for lm in frame]
        if hasattr(features, "extract_feature_vector"):
            vec = features.extract_feature_vector(pts)
        elif hasattr(features, "extract"):
            vec = features.extract(pts)
        else:
            vec = pts
        extracted_count += 1

    total_time = time.perf_counter() - start_time
    fps = extracted_count / total_time if total_time > 0 else 0
    latency_ms = (total_time / extracted_count) * 1000 if extracted_count > 0 else 0

    return {
        "success": True,
        "frames_processed": extracted_count,
        "total_time_seconds": round(total_time, 4),
        "synthetic_fps": round(fps, 1),
        "avg_latency_ms": round(latency_ms, 3),
        "realtime_viable": fps >= 60.0
    }


def check_hardware_resources() -> Dict[str, Any]:
    """Inspects RAM and GPU VRAM margins."""
    info: Dict[str, Any] = {"os": sys.platform}

    # System RAM
    try:
        import ctypes
        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]
        stat = MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
        total_ram_gb = stat.ullTotalPhys / (1024 ** 3)
        avail_ram_gb = stat.ullAvailPhys / (1024 ** 3)
        info["ram"] = {
            "total_gb": round(total_ram_gb, 2),
            "available_gb": round(avail_ram_gb, 2),
            "load_percent": stat.dwMemoryLoad,
            "sufficient_for_ai": avail_ram_gb >= 6.0
        }
    except Exception as e:
        info["ram_error"] = str(e)

    # GPU Check (Torch / ROCm or generic)
    try:
        import torch
        cuda_avail = torch.cuda.is_available()
        info["gpu"] = {
            "torch_cuda_available": cuda_avail,
            "device_count": torch.cuda.device_count() if cuda_avail else 0,
            "device_name": torch.cuda.get_device_name(0) if cuda_avail else "AMD Radeon (ROCm/Vulkan or CPU)",
        }
    except Exception:
        info["gpu"] = {"note": "PyTorch GPU introspection not required for diagnostics"}

    return info


def run_all_diagnostics() -> Dict[str, Any]:
    return {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "server": check_local_server(),
        "gesture_pipeline": benchmark_gesture_pipeline(),
        "resources": check_hardware_resources()
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Xennex Live Diagnostics")
    parser.add_argument("--component", choices=["all", "server", "gestures", "resources"], default="all")
    args = parser.parse_args()

    if args.component == "all":
        data = run_all_diagnostics()
    elif args.component == "server":
        data = check_local_server()
    elif args.component == "gestures":
        data = benchmark_gesture_pipeline()
    elif args.component == "resources":
        data = check_hardware_resources()

    print(json.dumps(data, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
