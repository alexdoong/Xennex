"""Latency and failure-mode regressions; synthetic data and fake devices only."""
import queue
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gestures.smoothing import PointerFilter
from gestures.capture import LatestFrame
from gestures.action_errors import TargetUnavailable
from gestures.control import ControlSession
from test_gestures import engine, binding, hand, FakeActions


class PerformanceTests(unittest.TestCase):
    def test_maximum_smoothing_does_not_drag_fast_moves_behind(self):
        f = PointerFilter()
        f.feed(0, 0, .9, 0)
        x, _ = f.feed(500, 0, .9, 1/30)
        self.assertGreater(x, 450)
        old_filter = 500 * (1 - .9)
        self.assertLess(old_filter, 100)

    def test_smoothing_damps_small_jitter(self):
        f = PointerFilter()
        f.feed(100, 100, .9, 0)
        results = [f.feed(100 + (-1)**i * 2, 100, .9, (i+1)/30)[0] for i in range(30)]
        self.assertLess(max(results)-min(results), 2)

    def test_smoothing_uses_elapsed_time(self):
        def position(fps):
            f = PointerFilter()
            f.feed(0, 0, .9, 0)
            for i in range(1, int(fps*.2)+1):
                x, _ = f.feed(10, 0, .9, i/fps)
            return x
        self.assertLess(abs(position(15)-position(60)), 1)

    def test_failed_window_target_keeps_control_enabled(self):
        class MissingTarget(FakeActions):
            def execute(self, event, config): raise TargetUnavailable('not a titlebar')
        session = ControlSession(MissingTarget(), lambda: 0)
        session.arm(True)
        with self.assertRaises(TargetUnavailable): session.execute({'phase':'begin'}, {})
        self.assertTrue(session.armed)
        self.assertEqual(session.actions.events[-1], 'release')

    def test_rejected_pinch_requires_release_before_retry(self):
        e = engine(binding())
        e.feed(hand('pinch'), 0)
        self.assertEqual(e.feed(hand('pinch'), .3)[0]['phase'], 'begin')
        e.reject_current()
        self.assertEqual(e.feed(hand('pinch'), 1), [])
        e.feed(hand('point'), 1.1)
        e.feed(hand('pinch'), 1.2)
        self.assertEqual(e.feed(hand('pinch'), 1.5)[0]['phase'], 'begin')

    def test_latest_frame_discards_backlog_and_is_not_replayed(self):
        class FakeCapture:
            def __init__(self): self.frames = queue.Queue(); self.released = False
            def read(self):
                try: return True, self.frames.get(timeout=.02)
                except queue.Empty: return False, None
            def release(self): self.released = True
        source = FakeCapture()
        frames = LatestFrame(lambda: source)
        try:
            for i in range(3): source.frames.put(i)
            with frames.condition:
                self.assertTrue(frames.condition.wait_for(lambda: frames.sequence == 3, timeout=1))
            self.assertEqual(frames.take()[0], 2)
            self.assertIsNone(frames.take(timeout=.001))
        finally:
            frames.close()
        self.assertTrue(source.released)

    def test_capture_error_reaches_consumer_and_releases_device(self):
        class BrokenCapture:
            released = False
            def read(self): raise RuntimeError('camera failed')
            def release(self): self.released = True
        source = BrokenCapture()
        frames = None
        with self.assertRaisesRegex(RuntimeError, 'camera failed'):
            frames = LatestFrame(lambda: source)
            frames.take()
        if frames:
            frames.close()
        self.assertTrue(source.released)


if __name__ == '__main__':
    unittest.main()
