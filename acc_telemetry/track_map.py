"""Illustrative demo circuit + validated custom world-coordinate outlines."""
import math


def _make_reference_track():
    # Fictional circuit in metres. A closed interpolating curve, not a real ACC map.
    anchors = [(0, 0), (450, 0), (530, 50), (500, 140), (390, 170),
               (400, 270), (280, 330), (160, 300), (140, 200),
               (230, 160), (160, 110), (0, 120), (-80, 60)]
    result = []
    for i, p1 in enumerate(anchors):
        p0, p2, p3 = anchors[i-1], anchors[(i+1) % len(anchors)], anchors[(i+2) % len(anchors)]
        for step in range(12):
            t = step / 12
            result.append(tuple(.5 * ((2*p1[k]) + (-p0[k]+p2[k])*t
                + (2*p0[k]-5*p1[k]+4*p2[k]-p3[k])*t*t
                + (-p0[k]+3*p1[k]-3*p2[k]+p3[k])*t*t*t) for k in (0, 1)))
    return result


REFERENCE_TRACK = _make_reference_track()


def load_track(path):
    """Read a user-supplied outline. Coordinates must match ACC world x/z in metres."""
    import json
    from pathlib import Path
    source = Path(path)
    if source.stat().st_size > 2_000_000:
        raise ValueError('Слишком большой контур (максимум 2 МБ)')
    data = json.loads(source.read_text(encoding='utf-8-sig'))
    points = data.get('points') if isinstance(data, dict) else data
    if not isinstance(points, list) or not 3 <= len(points) <= 20000:
        raise ValueError('Нужен список из 3..20000 точек')
    result = []
    for point in points:
        if not isinstance(point, list) or len(point) != 2:
            raise ValueError('Точка должна иметь вид [x, y]')
        if any(isinstance(v, bool) or not isinstance(v, (int, float))
               or not math.isfinite(v) for v in point):
            raise ValueError('Координаты должны быть конечными числами')
        result.append(tuple(map(float, point)))
    if max(math.dist(result[0], p) for p in result) < 1:
        raise ValueError('Контур должен иметь ненулевой размер')
    return result
