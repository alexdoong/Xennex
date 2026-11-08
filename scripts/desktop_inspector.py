#!/usr/bin/env python3
"""Desktop UI Inspector & Window Capture Utility for Antigravity AI Agent.

Enables the AI agent to capture high-fidelity screenshots of native desktop applications
(Xennex, Codex, Chrome, etc.) and full dual-monitor setups.
Bridges from the sandbox window station to WinSta0\\Default using Win32 API.
"""

from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from PIL import Image, ImageGrab

# Set stdout to UTF-8
sys.stdout.reconfigure(encoding="utf-8")

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)


def attach_to_default_desktop() -> bool:
    """Attaches current thread to the interactive 'Default' desktop on WinSta0."""
    try:
        # 0x01FF = DESKTOP_ALL_ACCESS
        h_default = user32.OpenDesktopW("Default", 0, False, 0x01FF)
        if not h_default:
            # Fallback with READOBJECTS | WRITEOBJECTS | SWITCHDESKTOP
            h_default = user32.OpenDesktopW("Default", 0, False, 0x0103)
        if h_default:
            return bool(user32.SetThreadDesktop(h_default))
    except Exception as e:
        print(f"[Warning: Failed to switch to Default desktop]: {e}", file=sys.stderr)
    return False


def get_visible_windows() -> List[Dict[str, Any]]:
    """Lists visible top-level windows on the Default desktop."""
    windows: List[Dict[str, Any]] = []

    def enum_cb(hwnd: int, lparam: int) -> bool:
        if user32.IsWindowVisible(hwnd):
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buff = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buff, length + 1)
                title = buff.value.strip()
                if title:
                    rect = wintypes.RECT()
                    user32.GetWindowRect(hwnd, ctypes.byref(rect))
                    w = rect.right - rect.left
                    h = rect.bottom - rect.top
                    # Exclude invisible or tiny utility windows
                    if w > 10 and h > 10:
                        windows.append({
                            "hwnd": hwnd,
                            "title": title,
                            "bounds": {
                                "left": rect.left,
                                "top": rect.top,
                                "right": rect.right,
                                "bottom": rect.bottom,
                                "width": w,
                                "height": h,
                            }
                        })
        return True

    # Use EnumDesktopWindows if possible, or EnumWindows
    h_desk = user32.GetThreadDesktop(kernel32.GetCurrentThreadId())
    user32.EnumDesktopWindows(h_desk, WNDENUMPROC(enum_cb), 0)
    return windows


def find_target_window(query: str) -> Optional[Dict[str, Any]]:
    windows = get_visible_windows()
    query_lower = query.lower()

    # Exact match first
    for w in windows:
        if w["title"].lower() == query_lower:
            return w

    # Substring match
    for w in windows:
        if query_lower in w["title"].lower():
            return w

    return None


def capture(
    target: str = "desktop",
    output_path: Optional[str] = None,
    crop_window: bool = True
) -> Dict[str, Any]:
    """Captures a window or the entire desktop, saving to PNG."""
    attach_to_default_desktop()

    # Keep screenshots outside the repository unless the caller chooses a path.
    if not output_path:
        artifact_dir = Path(os.environ.get("TEMP", ".")) / "Xennex" / "Screenshots"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        clean_target = "".join(c if c.isalnum() or c in "_-" else "_" for c in target).strip("_")
        dest_file = artifact_dir / f"screenshot_{clean_target}_{timestamp}.png"
    else:
        dest_file = Path(output_path)

    dest_file.parent.mkdir(parents=True, exist_ok=True)

    # 1. Full Desktop Grab
    full_img = ImageGrab.grab(all_screens=True)
    if not full_img:
        return {"success": False, "error": "ImageGrab returned None"}

    if target.lower() == "desktop":
        full_img.save(str(dest_file), format="PNG")
        return {
            "success": True,
            "target": "desktop",
            "mode": "fullscreen",
            "resolution": {"width": full_img.width, "height": full_img.height},
            "output_path": str(dest_file),
            "timestamp": datetime.now().isoformat()
        }

    # 2. Window Specific Grab
    target_win = find_target_window(target)
    if not target_win:
        all_wins = [{"hwnd": w["hwnd"], "title": w["title"]} for w in get_visible_windows()[:15]]
        return {
            "success": False,
            "error": f"Window matching '{target}' not found.",
            "available_windows": all_wins
        }

    b = target_win["bounds"]
    if crop_window:
        # Bounds may have negative coordinates on multi-monitor setups
        # ImageGrab(all_screens=True) starts at the minimum virtual screen coord
        # We clamp coordinates to image dimensions
        crop_box = (
            max(0, b["left"]),
            max(0, b["top"]),
            min(full_img.width, b["right"]),
            min(full_img.height, b["bottom"])
        )
        try:
            cropped = full_img.crop(crop_box)
            cropped.save(str(dest_file), format="PNG")
            return {
                "success": True,
                "target": target,
                "window_title": target_win["title"],
                "hwnd": target_win["hwnd"],
                "bounds": b,
                "output_path": str(dest_file),
                "resolution": {"width": cropped.width, "height": cropped.height},
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            full_img.save(str(dest_file), format="PNG")
            return {
                "success": True,
                "target": target,
                "window_title": target_win["title"],
                "warning": f"Crop failed ({e}), saved full screen.",
                "output_path": str(dest_file),
                "resolution": {"width": full_img.width, "height": full_img.height}
            }

    full_img.save(str(dest_file), format="PNG")
    return {
        "success": True,
        "target": target,
        "window_title": target_win["title"],
        "bounds": b,
        "output_path": str(dest_file),
        "resolution": {"width": full_img.width, "height": full_img.height}
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Desktop UI Inspector & Capture Utility")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # list
    list_parser = subparsers.add_parser("list", help="List visible top-level windows")

    # capture
    cap_parser = subparsers.add_parser("capture", help="Capture screenshot of a window or desktop")
    cap_parser.add_argument("--target", default="desktop", help="Window title query, or 'desktop'")
    cap_parser.add_argument("--output", help="Optional output image path")
    cap_parser.add_argument("--no-crop", action="store_true", help="Don't crop, capture full screen")

    args = parser.parse_args()

    if args.command == "list":
        attach_to_default_desktop()
        wins = get_visible_windows()
        print(json.dumps(wins, indent=2, ensure_ascii=False))
        return 0

    elif args.command == "capture":
        res = capture(args.target, args.output, crop_window=not args.no_crop)
        print(json.dumps(res, indent=2, ensure_ascii=False))
        return 0 if res.get("success") else 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
