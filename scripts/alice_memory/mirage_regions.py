"""Import object geometry from an offline Mirage result for the same image."""
from .native_regions import MAX_REGIONS


def object_boxes(envelope, image, digest):
    if (not isinstance(envelope, dict) or set(envelope) != {'image_sha256', 'result'}
            or envelope['image_sha256'] != digest or not isinstance(envelope['result'], dict)):
        raise ValueError('Mirage output must be bound to the SHA-256 of this image.')
    from PIL import Image
    try:
        with Image.open(image) as source:
            width, height = source.size
    except Image.DecompressionBombError as error:
        raise ValueError('Native image exceeds its pixel budget.') from error
    if width * height > 4_000_000:
        raise ValueError('Native image exceeds its pixel budget.')
    return select_boxes(envelope['result'], width, height)


def select_boxes(result, width, height, *, skip_scene=False):
    objects = result.get('objects') if isinstance(result, dict) else None
    if not isinstance(objects, list) or len(objects) > 64:
        raise ValueError('Mirage output requires a bounded objects list.')
    proposals = []
    for item in objects:
        if not isinstance(item, dict):
            raise ValueError('Invalid Mirage object.')
        box, score = item.get('bbox'), item.get('score')
        if (not isinstance(box, list) or len(box) != 4 or any(type(x) is not int or not 0 <= x <= 1000 for x in box)
                or not box[0] < box[2] or not box[1] < box[3]
                or type(score) not in (int, float) or not 0 <= score <= 1):
            raise ValueError('Invalid Mirage box or detection score.')
        left, top, right, bottom = box
        if skip_scene and (right - left) * (bottom - top) >= 800_000:
            continue
        pixels = [left * width // 1000, top * height // 1000,
                  (right * width + 999) // 1000, (bottom * height + 999) // 1000]
        proposals.append((score, pixels))
    selected = []
    for _, box in sorted(proposals, key=lambda item: -item[0]):
        if box not in selected:
            selected.append(box)
        if len(selected) == MAX_REGIONS:
            break
    return selected or None
