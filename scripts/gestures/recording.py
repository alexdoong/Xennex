"""Record a bounded sample after a countdown; loss of tracking invalidates it."""
from .features import resample, distance


class Recorder:
    def __init__(self, gesture_id, source, now):
        self.id, self.source = gesture_id, source
        self.start = now + 3
        self.duration = 1.0 if source == 'pose' else 2.0
        self.frames = []
        self.hand = None
        self.last_frame = None

    def feed(self, points, now, hand):
        if now < self.start:
            return {'stage': 'countdown', 'remaining': round(self.start - now, 1)}
        if points is None or (self.hand and hand != self.hand):
            return {'stage': 'error', 'message': 'Mantenha a mesma mão visível durante toda a gravação.'}
        if self.last_frame is not None and now - self.last_frame > 0.3:
            return {'stage': 'error', 'message': 'A captura interrompeu durante a amostra. Grave novamente.'}
        self.hand = hand
        self.last_frame = now
        self.frames.append(points)
        if now - self.start < self.duration:
            return {'stage': 'recording', 'remaining': round(self.duration - (now - self.start), 1)}
        if len(self.frames) < 8:
            return {'stage': 'error', 'message': 'Poucos quadros recebidos. Confira a câmera.'}
        if self.source == 'motion' and max(distance(p[0], self.frames[0][0]) for p in self.frames) < 0.07:
            return {'stage': 'error', 'message': 'Movimento muito pequeno. Use Pose para uma mão parada.'}
        return {'stage': 'done', 'sample': {'frames': resample(self.frames, 8 if self.source == 'pose' else 16),
                                         'duration': self.duration, 'hand': self.hand}}
