"""Explicit camera benchmark: reports timings only and never imports the Windows input adapter."""
import argparse
import json
import statistics
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gestures.tracking import HandTracker

parser = argparse.ArgumentParser()
parser.add_argument('--camera', type=int, required=True)
parser.add_argument('--seconds', type=float, default=15)
args = parser.parse_args()
tracker = HandTracker(args.camera)
latency, inference, intervals = [], [], []
detected, count = 0, 0
start = previous = last_report = time.monotonic()
try:
    while time.monotonic() - start < args.seconds:
        frame, points, hand = tracker.read('Any')
        now = time.monotonic()
        if tracker.fresh:
            intervals.append(now - previous)
            previous = now
            count += 1
            detected += points is not None
            latency.append(tracker.metrics['frameAgeMs'])
            inference.append(tracker.metrics['inferenceMs'])
        if now - last_report >= 15:
            print(json.dumps({'seconds': round(now-start), 'frames': count, 'fps': round(count/(now-start),1)}), flush=True)
            last_report = now
finally:
    tracker.close()
def p95(values):
    return round(sorted(values)[int((len(values)-1)*.95)], 2) if values else None
print(json.dumps({'seconds': round(time.monotonic()-start,1), 'frames': count,
    'fps': round(count/max(.001,time.monotonic()-start),1), 'hand_frames': detected,
    'inference_p95_ms': p95(inference), 'frame_age_p95_ms': p95(latency),
    'interval_p95_ms': p95([v*1000 for v in intervals]),
    'max_interval_ms': round(max(intervals, default=0)*1000,1)}), flush=True)
