"""Geometry and sequence matching. No camera, filesystem or desktop side effects."""
import math


def distance(a, b):
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def valid_hand(points):
    return (isinstance(points, list) and len(points) == 21 and
            all(isinstance(p, list) and len(p) == 3 and
                all(isinstance(v, (int, float)) and math.isfinite(v) for v in p) for p in points))


def shape(points):
    """Wrist-relative, palm-scaled coordinates, retaining hand orientation."""
    scale = max(distance(points[0], points[9]), distance(points[5], points[17]), 0.001)
    return [[(v - origin) / scale for v, origin in zip(p, points[0])] for p in points]


def legacy_shape(points):
    relative = [[p[0] - points[0][0], p[1] - points[0][1]] for p in points]
    scale = max(max(math.hypot(*p) for p in relative), 0.001)
    return [[v / scale for v in p] for p in relative]


def shape_distance(a, b):
    return sum(distance(x, y) for x, y in zip(a, b)) / 21


def pinch_ratio(points):
    return distance(points[4], points[8]) / max(distance(points[5], points[17]), 0.001)


def open_palm(points):
    return all(distance(points[tip], points[0]) > distance(points[joint], points[0]) * 1.16
               for tip, joint in ((8, 6), (12, 10), (16, 14), (20, 18)))


def resample(frames, count=16):
    if not frames:
        return []
    return [frames[round(i * (len(frames) - 1) / (count - 1))] for i in range(count)]


def sequence_features(frames):
    import numpy as np
    frames = np.asarray(resample(frames), dtype=float)
    if not frames.size:
        return None
    wrists = frames[:, :1, :]
    scale = np.maximum(np.linalg.norm(frames[:, 0] - frames[:, 9], axis=1),
                       np.linalg.norm(frames[:, 5] - frames[:, 17], axis=1))
    shapes = (frames - wrists) / np.maximum(scale, .001)[:, None, None]
    paths = frames[:, 0, :2] - frames[0, 0, :2]
    return shapes, paths


def feature_sequence_distance(a, b):
    """Vectorized shape costs + bounded 16x16 DTW; retains trajectory direction."""
    import numpy as np
    if a is None or b is None:
        return float('inf')
    sa, pa = a
    sb, pb = b
    costs = np.linalg.norm(sa[:, None] - sb[None], axis=3).mean(axis=2)
    costs += 3 * np.linalg.norm(pa[:, None] - pb[None], axis=2)
    previous = [0.0] + [float('inf')] * len(sb)
    for row in costs.tolist():
        current = [float('inf')]
        for j, cost in enumerate(row):
            current.append(cost + min(previous[j], previous[j + 1], current[j]))
        previous = current
    return previous[-1] / max(len(sa), len(sb))


def sequence_distance(a, b):
    return feature_sequence_distance(sequence_features(a), sequence_features(b))
