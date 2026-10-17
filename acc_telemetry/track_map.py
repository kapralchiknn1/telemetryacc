# -*- coding: utf-8 -*-
"""Эталонный контур трассы для демо-режима (условные метры)."""

import math

def _make_reference_track():
    """Замкнутый сплайн, похожий на реальную трассу (Monza-ish + шпильки)."""
    pts = []
    # длинная прямая
    for i in range(0, 30):
        pts.append((i * 12.0, 0.0))
    # Variante-del-Tamburo а-ля шикана
    pts += [(360, 8), (372, 26), (380, 48), (382, 70)]
    # правый поворот
    for a in range(0, 91, 10):
        r = 60
        cx, cy = 382 - r, 70 + r
        x = cx + r * math.cos(math.radians(a))
        y = cy - r * math.sin(math.radians(a))
        pts.append((x, y))
    # back straight
    for i in range(1, 25):
        pts.append((322 - i * 12.0, 130))
    # левая изогнутая часть
    for a in range(0, 121, 12):
        r = 55
        cx, cy = 42, 130 + r
        x = cx + r * math.cos(math.radians(180 - a))
        y = cy + r * math.sin(math.radians(180 - a))
        pts.append((x, y))
    # финальная шикана и прямая к старту
    pts += [(-13, 185), (-25, 160), (-28, 120), (-20, 70), (-5, 25)]
    return pts

REFERENCE_TRACK = _make_reference_track()
