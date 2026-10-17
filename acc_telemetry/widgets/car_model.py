# -*- coding: utf-8 -*-
"""3D-модель машины GT3 (вид сверху) для Tkinter Canvas."""

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
    """Панель 'Модель соперника': рисует локальную машину и ближайшего соперника
    в виде 3D-моделей (top-down), показывает их относительный поворот и дистанцию."""

    def __init__(self, canvas, store):
        self.canvas = canvas
        self.store = store

    def redraw(self):
        c = self.canvas
        w = int(c.winfo_width() or 300)
        h = int(c.winfo_height() or 180)
        c.delete("all")
        s = self.store
        coords = s.car_coordinates
        if not coords or s.local_idx >= len(coords):
            c.create_text(w/2, h/2, text="Ожидание данных о машинах...",
                          fill="#5a6b7d", font=("Segoe UI", 10))
            return
        lx, ly = coords[s.local_idx][0], coords[s.local_idx][1]
        # ближайший соперник
        best = None
        bestd = 1e18
        for idx, (wx, wy, wz) in enumerate(coords):
            if idx == s.local_idx:
                continue
            d = math.hypot(wx - lx, wy - ly)
            if d < bestd:
                bestd, best = d, idx
        if best is None:
            return
        # углы машин из векторов скорости
        a_me = self._angle(s.local_idx)
        a_rv = self._angle(best)
        rel = (a_rv - a_me + 180) % 360 - 180
        # позиции на панели
        cxm, cym = w * 0.30, h * 0.52
        cxr, cyr = w * 0.72, h * 0.42
        # дистанция влияет на масштаб соперника (перспектива)
        dm = bestd / 1000.0
        sc_me = 1.15
        sc_rv = max(0.45, min(1.15, 6.0 / (dm + 1.2)))
        color_rv = "#dfe6ee"
        if best < len(s.car_classes):
            cls = s.car_classes[best].upper()
            if "AM" in cls and "PRO-AM" not in cls:
                color_rv = "#4ac8ff"
            elif "PRO-AM" in cls or "SILVER" in cls:
                color_rv = "#9ee84a"
        draw_car_topdown(c, cxm, cym, a_me + 90, sc_me, body="#ffd24a", tag="me")
        draw_car_topdown(c, cxr, cyr, a_rv + 90, sc_rv, body=color_rv, tag="rv")
        name = s.car_names[best] if best < len(s.car_names) else f"Car {best+1}"
        c.create_text(cxm, h - 16, text="ВЫ", fill="#ffd24a", font=("Consolas", 9, "bold"))
        c.create_text(cxr, h - 16, text=name[:16], fill="#9fb2c6", font=("Consolas", 9))
        c.create_text(w/2, 16,
                      text=f"Дистанция: {dm:.1f} m   Отн. курс: {rel:+.0f}°",
                      fill="#cfd8e3", font=("Consolas", 10, "bold"))
        # линия взгляда
        c.create_line(cxm, cym, cxr, cyr, fill="#2a3644", dash=(3, 4))

    def _angle(self, idx):
        s = self.store
        vx = vy = 0
        if idx < len(s.car_vel_x):
            vx = s.car_vel_x[idx]
        if idx < len(s.car_vel_y):
            vy = s.car_vel_y[idx]
        if vx == 0 and vy == 0:
            coords = s.car_coordinates
            cur = coords[idx]
            nxt = coords[(idx + 1) % len(coords)]
            vx, vy = nxt[0]-cur[0], nxt[1]-cur[1]
        return math.degrees(math.atan2(vy, vx))
