# -*- coding: utf-8 -*-
"""Стилизованная 2D-схема GT-машины, не модель конкретной марки."""

import math


def draw_car_topdown(canvas, x, y, angle_deg, scale=1.0, body="#c0392b",
                     accent="#1a1a1a", tag=""):
    """Рисует стилизованную машину GT3 сверху в точке (x,y), повёрнутую на angle_deg."""
    # размеры в "юнитах" (умножаются на scale)
    L, W = 44, 20
    rad = math.radians(angle_deg)
    ca, sa = math.cos(rad), math.sin(rad)

    def T(px, py):
        rx = px * ca - py * sa
        ry = px * sa + py * ca
        return x + rx * scale, y + ry * scale

    items = []
    # тени колёс
    for wx, wy in [(-L*0.32, -W*0.55), (-L*0.32, W*0.55),
                   (L*0.30, -W*0.55), (L*0.30, W*0.55)]:
        p1 = T(wx - 6, wy - 3); p2 = T(wx + 6, wy + 3)
        canvas.create_rectangle(p1[0], p1[1], p2[0], p2[1], fill="#111", outline="", tag=tag)
    # корпус: нос сужается, корма шире + антикрыло
    hull = [(-L*0.5, -W*0.28), (-L*0.15, -W*0.42), (L*0.28, -W*0.40),
            (L*0.48, -W*0.22), (L*0.48, W*0.22), (L*0.28, W*0.40),
            (-L*0.15, W*0.42), (-L*0.5, W*0.28)]
    pts = []
    for px, py in hull:
        pts.extend(T(px, py))
    canvas.create_polygon(pts, fill=body, outline="#0a0a0a", width=1, tag=tag)
    # лобовое стекло / кабина
    cab = [(-L*0.10, -W*0.30), (L*0.18, -W*0.26), (L*0.18, W*0.26), (-L*0.10, W*0.30)]
    pts = []
    for px, py in cab:
        pts.extend(T(px, py))
    canvas.create_polygon(pts, fill="#16212e", outline="#0a0a0a", width=1, tag=tag)
    # заднее антикрыло
    w1 = T(L*0.5, -W*0.5); w2 = T(L*0.5, W*0.5)
    canvas.create_line(w1[0], w1[1], w2[0], w2[1], fill=accent, width=max(2, int(4*scale)), tag=tag)
    w1 = T(L*0.42, -W*0.5); w2 = T(L*0.42, W*0.5)
    canvas.create_line(w1[0], w1[1], w2[0], w2[1], fill=accent, width=max(1, int(2*scale)), tag=tag)
    # передний сплиттер
    f1 = T(-L*0.52, -W*0.35); f2 = T(-L*0.52, W*0.35)
    canvas.create_line(f1[0], f1[1], f2[0], f2[1], fill=accent, width=max(1, int(3*scale)), tag=tag)


class RivalModelPanel:
    def __init__(self, canvas):
        self.canvas = canvas
        self.selected = None

    def render(self, state):
        c = self.canvas
        c.delete("all")
        w, h = c.winfo_width(), c.winfo_height()
        own = state.cars.get(state.selected_id)
        rivals = [car for car in state.cars.values() if car.car_id != state.selected_id]
        rival = state.cars.get(self.selected) if self.selected != state.selected_id else None
        if rival is None and rivals:
            nearby = [car for car in rivals if own and own.located and car.located]
            rival = (min(nearby, key=lambda car: math.hypot(car.x-own.x, car.y-own.y))
                     if nearby else rivals[0])
        if rival is None:
            c.create_text(w/2, h/2, text="Нет данных о соперниках", fill="#8295aa")
            return
        draw_car_topdown(c, w/2, h*.30, 270, scale=min(1.8, h / 120), body="#69c3f0")
        lines = [rival.name or f"Car {rival.car_id}", rival.model or "Модель неизвестна",
                 f"P{rival.position or '--'} · {rival.cup}" + (" · PIT" if rival.in_pit else "")]
        if own and own.located and rival.located:
            lines.append(f"По прямой: {math.hypot(rival.x-own.x, rival.y-own.y):.1f} м")
        for i, line in enumerate(lines):
            c.create_text(w/2, h*.57+i*min(19, h*.10), text=line, fill="#d4dfeb", font=("Segoe UI", 10))
        c.create_text(w/2, 12, text="2D-схема · выбор в таблице", fill="#8295aa", font=("Segoe UI", 9))
