#!/usr/bin/env python3
"""ComfyUI Local Bridge & Asset Generation Utility for Xennex.

Provides seamless integration between Antigravity agent workflows and the local
ComfyUI installation (running at 127.0.0.1:8188 or on-disk models).
Zero external dependencies (uses standard library urllib, json, pathlib).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8188
DEFAULT_COMFY_DIR = Path(r"E:\confy\instance\ComfyUI\ComfyUI")
DEFAULT_DESKTOP_EXE = Path(r"E:\confy\Comfy Desktop\Comfy Desktop.exe")


def get_base_url(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> str:
    return f"http://{host}:{port}"


def request_json(url: str, method: str = "GET", data: Optional[Dict[str, Any]] = None, timeout: float = 3.0) -> Optional[Dict[str, Any]]:
    req_data = None
    headers = {"User-Agent": "Xennex-Antigravity-Bridge/1.0"}
    if data is not None:
        req_data = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=req_data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            if response.status == 200:
                raw = response.read().decode("utf-8")
                return json.loads(raw)
    except Exception:
        return None
    return None


def check_status(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> Dict[str, Any]:
    url = f"{get_base_url(host, port)}/system_stats"
    stats = request_json(url, timeout=2.0)
    if stats:
        return {
            "online": True,
            "url": get_base_url(host, port),
            "system": stats.get("system", {}),
            "devices": stats.get("devices", []),
        }

    # If offline, check local disk presence
    desktop_exists = DEFAULT_DESKTOP_EXE.exists()
    comfy_dir_exists = DEFAULT_COMFY_DIR.exists()
    return {
        "online": False,
        "url": get_base_url(host, port),
        "desktop_installed": desktop_exists,
        "desktop_exe": str(DEFAULT_DESKTOP_EXE) if desktop_exists else None,
        "comfy_dir": str(DEFAULT_COMFY_DIR) if comfy_dir_exists else None,
        "hint": "ComfyUI is offline. Launch 'Comfy Desktop.exe' to enable live generation API."
    }


def list_models_from_disk(comfy_dir: Path = DEFAULT_COMFY_DIR) -> Dict[str, List[str]]:
    models_dir = comfy_dir / "models"
    result: Dict[str, List[str]] = {
        "checkpoints": [],
        "loras": [],
        "unet": [],
        "vae": []
    }
    if not models_dir.exists():
        return result

    for category in result.keys():
        cat_path = models_dir / category
        if cat_path.exists():
            for f in cat_path.glob("*.*"):
                if f.suffix.lower() in [".safetensors", ".ckpt", ".gguf", ".pt", ".bin"] and not f.name.startswith("put_"):
                    result[category].append(f.name)

    return result


def list_models_online(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> Optional[Dict[str, List[str]]]:
    url = f"{get_base_url(host, port)}/object_info"
    info = request_json(url, timeout=5.0)
    if not info:
        return None

    result: Dict[str, List[str]] = {
        "checkpoints": [],
        "loras": [],
        "samplers": []
    }
    # Extract checkpoints from CheckpointLoaderSimple
    ckpt_node = info.get("CheckpointLoaderSimple", {}).get("input", {}).get("required", {}).get("ckpt_name", [])
    if ckpt_node and isinstance(ckpt_node[0], list):
        result["checkpoints"] = ckpt_node[0]

    # Extract loras from LoraLoader
    lora_node = info.get("LoraLoader", {}).get("input", {}).get("required", {}).get("lora_name", [])
    if lora_node and isinstance(lora_node[0], list):
        result["loras"] = lora_node[0]

    # Extract samplers from KSampler
    sampler_node = info.get("KSampler", {}).get("input", {}).get("required", {}).get("sampler_name", [])
    if sampler_node and isinstance(sampler_node[0], list):
        result["samplers"] = sampler_node[0]

    return result


def queue_prompt(prompt_workflow: Dict[str, Any], client_id: str = "xennex-agent", host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> Optional[str]:
    url = f"{get_base_url(host, port)}/prompt"
    payload = {"prompt": prompt_workflow, "client_id": client_id}
    res = request_json(url, method="POST", data=payload, timeout=10.0)
    if res and "prompt_id" in res:
        return res["prompt_id"]
    return None


def get_history(prompt_id: str, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> Optional[Dict[str, Any]]:
    url = f"{get_base_url(host, port)}/history/{prompt_id}"
    return request_json(url, timeout=5.0)


def wait_for_completion(prompt_id: str, timeout_sec: int = 180, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> Optional[List[Dict[str, str]]]:
    start = time.time()
    while time.time() - start < timeout_sec:
        hist = get_history(prompt_id, host, port)
        if hist and prompt_id in hist:
            data = hist[prompt_id]
            outputs = data.get("outputs", {})
            images: List[Dict[str, str]] = []
            for _, node_output in outputs.items():
                if "images" in node_output:
                    for img in node_output["images"]:
                        images.append(img)
            return images
        time.sleep(2.0)
    return None


def download_image(filename: str, subfolder: str = "", folder_type: str = "output", output_dest: Path = Path("."), host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> Optional[Path]:
    params = urllib.parse.urlencode({
        "filename": filename,
        "subfolder": subfolder,
        "type": folder_type
    })
    url = f"{get_base_url(host, port)}/view?{params}"
    try:
        output_dest.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(url, str(output_dest))
        return output_dest
    except Exception as e:
        print(f"[Error downloading image]: {e}", file=sys.stderr)
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description="ComfyUI Local Bridge for Xennex")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Status
    status_parser = subparsers.add_parser("status", help="Check ComfyUI server status")
    status_parser.add_argument("--host", default=DEFAULT_HOST)
    status_parser.add_argument("--port", type=int, default=DEFAULT_PORT)

    # Models
    models_parser = subparsers.add_parser("models", help="List available models and LoRAs (online or disk)")
    models_parser.add_argument("--host", default=DEFAULT_HOST)
    models_parser.add_argument("--port", type=int, default=DEFAULT_PORT)

    # Queue Prompt
    queue_parser = subparsers.add_parser("queue", help="Queue a prompt workflow JSON")
    queue_parser.add_argument("--workflow", required=True, help="Path to workflow JSON file")
    queue_parser.add_argument("--output", help="Optional destination path for generated image")
    queue_parser.add_argument("--host", default=DEFAULT_HOST)
    queue_parser.add_argument("--port", type=int, default=DEFAULT_PORT)

    args = parser.parse_args()

    if args.command == "status":
        info = check_status(args.host, args.port)
        print(json.dumps(info, indent=2))
        return 0

    elif args.command == "models":
        online_models = list_models_online(args.host, args.port)
        if online_models:
            print(json.dumps({"source": "online_api", **online_models}, indent=2))
        else:
            disk_models = list_models_from_disk()
            print(json.dumps({"source": "disk_scan", **disk_models}, indent=2))
        return 0

    elif args.command == "queue":
        wf_path = Path(args.workflow)
        if not wf_path.exists():
            print(f"Error: Workflow file '{wf_path}' not found.", file=sys.stderr)
            return 1
        with open(wf_path, "r", encoding="utf-8") as f:
            wf = json.load(f)
        prompt_id = queue_prompt(wf, host=args.host, port=args.port)
        if not prompt_id:
            print("Failed to queue prompt to ComfyUI.", file=sys.stderr)
            return 1
        print(f"Queued prompt: {prompt_id}")
        if args.output:
            print(f"Waiting for completion and downloading to {args.output}...")
            images = wait_for_completion(prompt_id, host=args.host, port=args.port)
            if images:
                first = images[0]
                dest = download_image(first["filename"], first.get("subfolder", ""), first.get("type", "output"), Path(args.output), host=args.host, port=args.port)
                if dest:
                    print(f"Saved image to: {dest}")
                    return 0
            print("Failed to retrieve generated image.", file=sys.stderr)
            return 1
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
