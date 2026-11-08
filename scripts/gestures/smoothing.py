"""Time-based pointer smoothing: damp small jitter without dragging fast movements behind."""
import math


class PointerFilter:
    def __init__(self):
        self.position = None
        self.timestamp = None

    def reset(self):
        self.position = self.timestamp = None

    def feed(self, x, y, amount, now):
        if self.position is None or self.timestamp is None or amount <= 0:
            self.position, self.timestamp = (x, y), now
            return x, y
        dt = max(.001, min(.25, now - self.timestamp))
        error = math.hypot(x - self.position[0], y - self.position[1])
        # More filtering near rest; fast/large moves get a short response time.
        tau = (.008 + .08 * amount) / (1 + error / 12)
        alpha = 1 - math.exp(-dt / tau)
        px, py = self.position
        self.position = (px + alpha * (x - px), py + alpha * (y - py))
        self.timestamp = now
        return self.position
