"""Exclusive, expiring permission to issue desktop input (also usable with a fake adapter)."""
import threading
import time
from .action_errors import TargetUnavailable


class ControlSession:
    def __init__(self, actions, clock=time.monotonic):
        self.actions, self.clock = actions, clock
        self.lock = threading.RLock()
        self.armed = False
        self.deadline = 0
        self.pause_reason = None

    def arm(self, enabled):
        with self.lock:
            self.armed = False
            self.actions.release()
            self.deadline = self.clock() + 0.8
            self.armed = enabled
            self.pause_reason = None

    def heartbeat(self):
        with self.lock:
            expired = self.watchdog()
            self.deadline = self.clock() + 0.8
            return expired

    def watchdog(self):
        with self.lock:
            if not self.armed:
                return False
            reason = 'Esc pressionado' if self.actions.emergency() else (
                'captura ou processamento sem responder por 800 ms' if self.clock() > self.deadline else None)
            if reason:
                self.arm(False)
                self.pause_reason = reason
                return True
            return False

    def execute(self, event, config):
        with self.lock:
            self.watchdog()
            if event['phase'] == 'end':
                self.actions.release()
            elif self.armed:
                try:
                    self.actions.execute(event, config)
                except TargetUnavailable:
                    self.actions.release()
                    raise
                except Exception:
                    self.arm(False)
                    raise
