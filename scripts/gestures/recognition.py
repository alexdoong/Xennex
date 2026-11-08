"""Temporal recognition produces begin/update/end/trigger events, never OS input."""
from collections import deque
from .features import distance, shape, shape_distance, legacy_shape, sequence_features, feature_sequence_distance, pinch_ratio, open_palm, valid_hand


class GestureEngine:
    def __init__(self, config):
        self.config = config
        self.templates = {g['id']: [sequence_features(s['frames']) for s in g.get('samples', [])]
                          for g in config.get('gestures', []) if g.get('source') == 'motion'}
        self.history = deque()
        self.candidate = None
        self.candidate_since = 0
        self.active = None
        self.latched = set()
        self.cooldowns = {}
        self.pinch = False
        self.hand = None
        self.release_since = None
        self.rejected = None

    def reset(self):
        events = []
        if self.active:
            events.append({'phase': 'end', 'gesture': self.active})
        self.history.clear()
        self.candidate = self.active = self.hand = None
        self.latched.clear()
        self.pinch = False
        self.release_since = None
        self.rejected = None
        return events

    def reject_current(self):
        self.rejected = self.candidate
        self.active = None

    def feed(self, points, now, hand='Right'):
        if not valid_hand(points) or (self.hand and self.hand != hand):
            return self.reset()
        selected = self.config.get('hand', 'Any')
        if selected != 'Any' and selected != hand:
            return self.reset()
        self.hand = hand
        ratio = pinch_ratio(points)
        self.pinch = ratio < (0.42 if self.pinch else 0.28)
        self.history.append((now, points))
        while self.history and now - self.history[0][0] > 3:
            self.history.popleft()
        matches = []
        palm = open_palm(points)
        current_shape = shape(points)
        recent_features = {}
        for gesture in self.config.get('gestures', []):
            if not gesture.get('enabled', True):
                continue
            source = gesture.get('source')
            score = None
            if source == 'pinch' and self.pinch:
                score = 0
            elif source == 'open_palm' and palm and not self.pinch:
                score = 0
            elif source == 'point' and not self.pinch:
                if (distance(points[8], points[0]) > distance(points[6], points[0]) * 1.2 and
                        distance(points[12], points[0]) < distance(points[10], points[0]) * 1.15):
                    score = 0
            elif source and source.startswith('swipe_') and palm and not self.pinch:
                recent = [(t, p) for t, p in self.history if now - t <= 0.45]
                if len(recent) >= 3 and now - recent[0][0] >= 0.10:
                    dx = points[0][0] - recent[0][1][0][0]
                    dy = points[0][1] - recent[0][1][0][1]
                    threshold = self.config.get('swipeThreshold', 0.18)
                    direction = None
                    if abs(dx) >= threshold and abs(dx) > abs(dy) * 1.5:
                        direction = 'right' if dx > 0 else 'left'
                    elif abs(dy) >= threshold and abs(dy) > abs(dx) * 1.5:
                        direction = 'down' if dy > 0 else 'up'
                    if source == 'swipe_' + str(direction):
                        score = 0
            elif source == 'pose':
                scores = []
                for sample in gesture.get('samples', []):
                    if sample.get('legacy'):
                        scores.append(shape_distance(legacy_shape(points), sample['frames'][0]))
                    elif sample.get('frames'):
                        scores.append(sum(shape_distance(current_shape, shape(p)) for p in sample['frames']) / len(sample['frames']))
                if scores:
                    score = min(scores)
            elif source == 'motion':
                scores = []
                for sample_index, sample in enumerate(gesture.get('samples', [])):
                    duration = sample.get('duration', 1.5)
                    for factor in (0.7, 1.0, 1.3):
                        recent = [(t, p) for t, p in self.history if now - t <= duration * factor]
                        if len(recent) < 5 or now - recent[0][0] < duration * factor * 0.75:
                            continue
                        if distance(recent[0][1][0], points[0]) < 0.035 and max(distance(p[0], recent[0][1][0]) for _, p in recent) < 0.07:
                            continue
                        key = duration * factor
                        if key not in recent_features:
                            recent_features[key] = sequence_features([p for _, p in recent])
                        scores.append(feature_sequence_distance(recent_features[key], self.templates[gesture['id']][sample_index]))
                if scores:
                    score = min(scores)
            threshold = gesture.get('threshold', 0.22)
            if score is not None and score <= threshold:
                matches.append((score / threshold, gesture))
        matches.sort(key=lambda item: (item[1]['source'] not in ('pose', 'motion'), item[0]))
        # Ambiguous learned gestures do not execute arbitrary bindings.
        winner = matches[0][1] if matches else None
        if len(matches) > 1 and matches[0][1]['source'] in ('pose', 'motion') and matches[1][1]['source'] in ('pose', 'motion') and matches[1][0] - matches[0][0] < 0.12:
            winner = None
        events = []
        winner_id = winner['id'] if winner else None
        if self.active and self.active['id'] != winner_id:
            events.append({'phase': 'end', 'gesture': self.active})
            self.active = None
        if not winner:
            if self.release_since is None:
                self.release_since = now
            if now - self.release_since >= 0.25:
                self.latched.clear()
        else:
            self.release_since = None
        if self.candidate != winner_id:
            self.candidate = winner_id
            self.candidate_since = now
        if self.rejected != winner_id:
            self.rejected = None
        if not winner or self.rejected == winner_id:
            return events
        continuous = winner['action']['type'] in ('pointer', 'drag_window', 'drag_mouse', 'scroll')
        hold = winner.get('holdMs', 220) / 1000
        if winner['source'].startswith('swipe_') or winner['source'] == 'motion':
            hold = 0
        if now - self.candidate_since < hold:
            return events
        position = points[8][:2]
        if continuous:
            phase = 'update' if self.active else 'begin'
            self.active = winner
            events.append({'phase': phase, 'gesture': winner, 'position': position})
        elif (winner_id not in self.latched and now >= self.cooldowns.get(winner_id, 0) and
              (not winner['source'].startswith('swipe_') or now >= self.cooldowns.get('_swipe', 0))):
            self.latched.add(winner_id)
            self.cooldowns[winner_id] = now + winner.get('cooldownMs', 1000) / 1000
            events.append({'phase': 'trigger', 'gesture': winner, 'position': position})
            if winner['source'].startswith('swipe_'):
                self.cooldowns['_swipe'] = self.cooldowns[winner_id]
            if winner['source'].startswith('swipe_') or winner['source'] == 'motion':
                self.history.clear()
                self.latched.discard(winner_id)
        return events
