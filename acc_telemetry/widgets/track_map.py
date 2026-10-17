# -*- coding: utf-8 -*-
"""
Карта трассы (Tkinter Canvas) с позициями пилота и соперников.

Координаты машин из пакета QUITTLY приходят в миллиметрах в мировой системе
координат ACC. Карта автоматически центрируется по всем машинам и
масштабируется, поэтому контур корректно отображается при любом смещении.
Колесо мыши - зум, двойной клик - сброс зума.
"""

import tkinter as tk
import math


class TrackMap(tk.Frame):
    def __init__(self, master, store, width=460, height=320, **kw):
        super().__init__(master, bg="#10151c", **kw)
        self.store = store
        self.width = width
        self.height = height
        self.canvas = tk.Canvas(self, width=width, height=height,
                                bg="#0b0f15", highlightthickness=1,
                                highlightbackground="#2a3644")
        self.canvas.pack(fill="both", expand=True)
        self.zoom = 1.0
        # контур трассы из ACC Python API (список мировых точек (x,y,z))
        self.api_points = None
        # история позиций локальной машины для "следа"
        self.trail = []

        self.canvas.bind("<MouseWheel>", self._on_wheel)      # Windows/Mac
        self.canvas.bind("<Button-4>", lambda e: self._wheel(1.1))   # Linux
        self.canvas.bind("<Button-5>", lambda e: self._wheel(0.9))
        self.canvas.bind("<Double-Button-1>", lambda e: self._reset_zoom())

    def _on_wheel(self, event):
        self._wheel(1.1 if event.delta > 0 else 0.9)

    def _wheel(self, factor):
        self.zoom = max(0.4, min(4.0, self.zoom * factor))
        self.redraw()

    def _reset_zoom(self):
        self.zoom = 1.0
        self.redraw()

    def set_api_points(self, pts):
        """Контур трассы из ACC Python API (sTrackMapNodes)."""
        self.api_points = pts

    # ---------- преобразование координат ----------
    def _bounds_from_cars(self, coords):
        xs = [c[0] for c in coords]
        ys = [c[1] for c in coords]
        cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
        spread = max(max(xs) - min(xs), max(ys) - min(ys), 1)
        return cx, cy, spread

    def world_to_screen(self, wx, wy, cx, cy, scale):
        sx = self.width / 2 + (wx - cx) * scale * self.zoom
        sy = self.height / 2 - (wy - cy) * scale * self.zoom
        return sx, sy

    # ---------- отрисовка ----------
    def redraw(self):
        s = self.store
        c = self.canvas
        c.delete("all")
        coords = s.car_coordinates
        if not coords:
            c.create_text(self.width/2, self.height/2,
                          text="Нет данных о позициях машин\n(запустите игру или демо-режим)",
                          fill="#5a6b7d", font=("Segoe UI", 11), justify="center")
            return
        cx, cy, spread = self._bounds_from_cars(coords)
        scale = (min(self.width, self.height) * 0.42) / (spread * 1.4)

        # контур трассы
        if self.api_points and len(self.api_points) >= 4:
            pts = []
            for p in self.api_points:
                sx, sy = self.world_to_screen(p[0], p[1], cx, cy, scale)
                pts.extend([sx, sy])
            pts += pts[:2]
            c.create_line(pts, fill="#1e2c3c", width=12, smooth=True, joinstyle="round")
            c.create_line(pts, fill="#2c4058", width=7, smooth=True, joinstyle="round")
            c.create_line(pts, fill="#3a5574", width=2, smooth=True, dash=(6, 4))
        else:
            self._draw_cloud(c, coords, cx, cy, scale)

        # след локальной машины
        if s.local_idx < len(coords):
            wx, wy, wz = coords[s.local_idx]
            sx, sy = self.world_to_screen(wx, wy, cx, cy, scale)
            if not self.trail or math.hypot(sx - self.trail[-1][0], sy - self.trail[-1][1]) > 2:
                self.trail.append((sx, sy))
                if len(self.trail) > 240:
                    self.trail.pop(0)
            flat = [v for p in self.trail for v in p]
            if len(flat) >= 4:
                c.create_line(flat, fill="#ffd24a33"[:7], width=2)

        # машины: сначала соперники, локальная поверх
        items = []
        for idx in range(len(coords)):
            wx, wy, wz = coords[idx]
            sx, sy = self.world_to_screen(wx, wy, cx, cy, scale)
            ang = self._angle(idx, coords)
            is_local = (idx == s.local_idx)
            color = "#ffd24a" if is_local else self._class_color(idx, s)
            items.append((idx, sx, sy, ang, color, is_local))
        for it in items:
            if not it[5]:
                self._draw_car(c, it[1], it[2], it[3], it[4], False, "")
        for it in items:
            if it[5]:
                self._draw_car(c, it[1], it[2], it[3], it[4], True, "YOU")

        # подписи дистанции до ближайших соперников
        self._draw_gaps(c, coords, cx, cy, scale)

        c.create_text(10, 12, anchor="w", text=s.track_name,
                      fill="#8fa3b8", font=("Consolas", 10, "bold"))
        c.create_text(self.width - 10, 12, anchor="e",
                      text=f"zoom {self.zoom:.1f}x  (колесо мыши)",
                      fill="#42536a", font=("Consolas", 8))

    def _draw_cloud(self, c, coords, cx, cy, scale):
        all_pts = []
        for wx, wy, wz in coords:
            sx, sy = self.world_to_screen(wx, wy, cx, cy, scale)
            all_pts.append((sx, sy))
        flat = [v for p in all_pts for v in p]
        if len(flat) >= 4:
            c.create_line(flat, fill="#16202c", width=16, smooth=True, capstyle="round")
            c.create_line(flat, fill="#1f2e3f", width=9, smooth=True, capstyle="round")

    def _angle(self, idx, coords):
        s = self.store
        vx = vy = None
        if idx < len(s.car_vel_x) and idx < len(s.car_vel_y):
            vx, vy = s.car_vel_x[idx], s.car_vel_y[idx]
        if vx is None or (vx == 0 and vy == 0):
            cur = coords[idx]
            nxt = coords[(idx + 1) % len(coords)]
            dx, dy = nxt[0] - cur[0], nxt[1] - cur[1]
        else:
            dx, dy = vx, vy
        a = math.degrees(math.atan2(dy, dx))
        return -a  # инверсия оси Y экрана

    def _class_color(self, idx, s):
        cls = ""
        if idx < len(s.car_classes):
            cls = s.car_classes[idx].upper()
        if "AM" in cls and "PRO-AM" not in cls:
            return "#4ac8ff"
        if "PRO-AM" in cls or "SILVER" in cls:
            return "#9ee84a"
        return "#dfe6ee"

    def _draw_car(self, c, x, y, ang, color, is_local, label):
        L = 16 if is_local else 11
        W = 8 if is_local else 6
        rad = math.radians(ang)
        ca, sa = math.cos(rad), math.sin(rad)
        pts = [(-L/2, -W/2), (L/2, -W*0.35), (L/2, W*0.35), (-L/2, W/2)]
        screen = []
        for px, py in pts:
            rx = px * ca - py * sa
            ry = px * sa + py * ca
            screen.extend([x + rx, y + ry])
        outline = "#ffffff" if is_local else "#0b0f15"
        c.create_polygon(screen, fill=color, outline=outline,
                         width=2 if is_local else 1)
        if is_local:
            c.create_oval(x-18, y-18, x+18, y+18, outline="#ffd24a", width=1)
            c.create_text(x, y-26, text=label, fill="#ffd24a",
                          font=("Consolas", 9, "bold"))

    def _draw_gaps(self, c, coords, cx, cy, scale):
        s = self.store
        if s.local_idx >= len(coords):
            return
        lx, ly = coords[s.local_idx][0], coords[s.local_idx][1]
        sx, sy = self.world_to_screen(lx, ly, cx, cy, scale)
        dists = []
        for idx, (wx, wy, wz) in enumerate(coords):
            if idx == s.local_idx:
                continue
            d = math.hypot(wx - lx, wy - ly) / 1000.0
            dists.append((d, idx))
        dists.sort()
        for d, idx in dists[:3]:
            wx, wy, wz = coords[idx]
            tx, ty = self.world_to_screen(wx, wy, cx, cy, scale)
            label = f"{d:.0f} m" if d > 3 else f"{d:.1f} m"
            c.create_line(sx, sy, tx, ty, fill="#33465c", dash=(2, 3))
            c.create_text(tx, ty - 14, text=label, fill="#9fb2c6",
                          font=("Consolas", 8))
