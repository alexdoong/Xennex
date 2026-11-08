"""Bounded visual addresses derived from explicitly selected image crops."""
import torch

from .native_sensor import DIMENSION

MAX_REGIONS = 4
MIN_SIMILARITY = .9
MIN_GAP = .04
DETECTION_STATUSES = ('detected', 'no_useful_box', 'detector_error')


def validate_boxes(boxes):
    if not isinstance(boxes, list) or not 1 <= len(boxes) <= MAX_REGIONS:
        raise ValueError('An image requires one to four region boxes.')
    seen = set()
    for box in boxes:
        if not isinstance(box, list) or len(box) != 4 or any(type(x) is not int for x in box):
            raise ValueError('A region box requires four integer pixel coordinates.')
        left, top, right, bottom = box
        if not (0 <= left < right <= 4_000_000 and 0 <= top < bottom <= 4_000_000) or tuple(box) in seen:
            raise ValueError('Invalid or duplicate image region.')
        seen.add(tuple(box))


def validate_regions(record, source_sha256, boxes=None):
    if not isinstance(record, dict) or set(record) != {'source_sha256', 'boxes', 'routes'} or record['source_sha256'] != source_sha256:
        raise ValueError('Visual regions lost their source image.')
    validate_boxes(record['boxes'])
    if boxes is not None and record['boxes'] != boxes:
        raise ValueError('Visual regions changed the requested boxes.')
    routes = record['routes']
    if (not isinstance(routes, torch.Tensor) or routes.device.type != 'cpu' or routes.dtype != torch.float32
            or routes.shape != (len(record['boxes']), DIMENSION) or not torch.isfinite(routes).all()
            or not torch.allclose(routes.norm(dim=1), torch.ones(len(record['boxes'])), atol=1e-5, rtol=0)):
        raise ValueError('Invalid visual region addresses.')


def match(records, query, exclude=None):
    """Rank moments by their strongest crop pair, without treating boxes as identities."""
    pairs = [(moment, record['routes']) for moment, record in records.items() if moment != exclude]
    if not pairs:
        return []
    scores = (torch.cat([routes for _, routes in pairs]) @ query['routes'].T).amax(dim=1)
    groups = scores.split([len(routes) for _, routes in pairs])
    peaks = torch.stack([group.max() for group in groups]).clamp(-1, 1).tolist()
    return sorted(zip((moment for moment, _ in pairs), peaks), key=lambda item: (-item[1], item[0]))
