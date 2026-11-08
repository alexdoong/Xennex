"""Capture continuously into a single slot so inference never works through a stale queue."""
import threading
import time


class LatestFrame:
    def __init__(self, capture_factory, clock=time.monotonic):
        self.capture_factory, self.clock = capture_factory, clock
        self.capture = None
        self.ready = False
        self.condition = threading.Condition()
        self.frame = None
        self.timestamp = 0
        self.sequence = self.consumed = 0
        self.error = None
        self.stopped = False
        self.thread = threading.Thread(target=self._read, daemon=True)
        self.thread.start()
        with self.condition:
            self.condition.wait_for(lambda: self.ready or self.error, timeout=10)
            if self.error:
                raise self.error
            if not self.ready:
                self.stopped = True
                raise RuntimeError('A câmera demorou demais para abrir.')

    def _read(self):
        failures = 0
        try:
            self.capture = self.capture_factory()
            with self.condition:
                self.ready = True
                self.condition.notify_all()
            while not self.stopped:
                ok, frame = self.capture.read()
                if self.stopped:
                    break
                if not ok:
                    failures += 1
                    if failures >= 10:
                        raise RuntimeError('A câmera parou de fornecer imagens.')
                    time.sleep(.02)
                    continue
                failures = 0
                with self.condition:
                    self.frame, self.timestamp = frame, self.clock()
                    self.sequence += 1
                    self.condition.notify_all()
        except Exception as error:
            with self.condition:
                self.error = error
                self.condition.notify_all()
        finally:
            if self.capture is not None:
                self.capture.release()
                self.capture = None

    def take(self, timeout=.1):
        with self.condition:
            self.condition.wait_for(lambda: self.sequence != self.consumed or self.error or self.stopped, timeout)
            if self.error:
                raise self.error
            if self.sequence == self.consumed or self.stopped:
                return None
            self.consumed = self.sequence
            return self.frame, self.timestamp

    def close(self):
        with self.condition:
            self.stopped = True
            self.condition.notify_all()
        # Only the capture thread owns/release VideoCapture; never race a blocked native read.
        self.thread.join(timeout=1)
