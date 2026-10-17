# -*- coding: utf-8 -*-
"""Панели телеметрии: тахометр, скорость, шины, ветер, позиция."""

import tkinter as tk
import math


class SpeedDial(tk.Canvas):
    """Круговой спидометр + дуга оборотов."""

    def __init__(self, master, store, size=210, **kw):
        super().__init__(master, width=size, height=size, bg="#0b0f15",
                         highlightthickness=0, **kw)
        self.store = store
        self.size = size
        self.max_kmh = 300
        self.redline = 7600

    def redraw(self):
        c = self
        w = self.size
        c.delete("all")
        s = self.store
        cx, cy = w/2, w/2
        r = w*0.40
        a0, a1 = 135, 405  # градусы, как в приборных панелях
        # фон дуги
        self._arc(cx, cy, r, a0, a1, "#1c2836", 12)
        # деления
        for i in range(0, self.max_kmh + 1, 30):
            ang = math.radians(a0 + (a1 - a0) * i / self.max_kmh)
            x1 = cx + (r - 14) * math.cos(ang); y1 = cy - (r - 14) * math.sin(ang)
            x2 = cx + (r - 4) * math.cos(ang); y2 = cy - (r - 4) * math.sin(ang)
            c.create_line(x1, y1, x2, y2, fill="#4a5c70")
            tx = cx + (r - 26) * math.cos(ang); ty = cy - (r - 26) * math.sin(ang)
            c.create_text(tx, ty, text=str(i), fill="#6d8098", font=("Consolas", 7))
        # дуга скорости
        v = min(s.speed_kmh, self.max_kmh)
        if v > 1:
            self._arc(cx, cy, r, a0, a0 + (a1 - a0) * v / self.max_kmh, "#2ecc71", 12)
        # дуга оборотов (внутренняя)
        r2 = r - 20
        self._arc(cx, cy, r2, a0, a1, "#16202c", 8)
        rpm_frac = min(1.0, s.rpm / 8000.0)
        col = "#e74c3c" if s.rpm > self.redline else "#3498db"
        if rpm_frac > 0.01:
            self._arc(cx, cy, r2, a0, a0 + (a1 - a0) * rpm_frac, col, 8)
        # центр: скорость и передача
        gear_txt = {0: "N", 1: "R"}.get(-s.gear, "") or str(max(0, s.gear))
        if s.gear == 0:
            gear_txt = "N"
        elif s.gear < 0:
            gear_txt = "R"
        else:
            gear_txt = str(s.gear)
        c.create_text(cx, cy - 12, text=f"{s.speed_kmh:.0f}",
                      fill="#ffffff", font=("Consolas", 30, "bold"))
        c.create_text(cx, cy + 16, text="km/h", fill="#6d8098", font=("Consolas", 9))
        c.create_text(cx, cy + 42, text=gear_txt,
                      fill="#ffd24a" if s.gear > 0 else "#4a5c70",
                      font=("Consolas", 22, "bold"))
        c.create_text(cx, cy - 46, text=f"{s.rpm} RPM",
                      fill="#e74c3c" if s.rpm > self.redline else "#9fb2c6",
                      font=("Consolas", 9, "bold"))

    def _arc(self, cx, cy, r, a0, a1, color, width):
        steps = max(2, int(abs(a1 - a0) / 6))
        pts = []
        for i in range(steps + 1):
            ang = math.radians(a0 + (a1 - a0) * i / steps)
            pts.append(cx + r * math.cos(ang))
            pts.append(cy - r * math.sin(ang))
        self.create_line(pts, fill=color, width=width, capstyle="round", joinstyle="round")


class TyrePanel(tk.Canvas):
    """Четыре колеса: температура протектора/середины, цвет по перегреву."""

    HOT = "#e74c3c"; WARM = "#f39c12"; OK = "#2ecc71"; COLD = "#3498db"

    def __init__(self, master, store, width=230, height=190, **kw):
        super().__init__(master, width=width, height=height, bg="#0b0f15",
                         highlightthickness=0, **kw)
        self.store = store

    def _color(self, t):
        if t >= 105: return self.HOT
        if t >= 95: return self.WARM
        if t >= 75: return self.OK
        return self.COLD

    def redraw(self):
        c = self
        c.delete("all")
        s = self.store
        labels = ["FL", "FR", "RL", "RR"]
        pos = [(0.26, 0.30), (0.74, 0.30), (0.26, 0.78), (0.74, 0.78)]
        w = int(c.winfo_width() or self.winfo_reqwidth())
        h = int(c.winfo_height() or self.winfo_reqheight())
        for i, (fx, fy) in enumerate(pos):
            x, y = w * fx, h * fy
            out = s.tyres_out[i] if i < len(s.tyres_out) else 0
            inn = s.tyres_in[i] if i < len(s.tyres_in) else 0
            col = self._color(out)
            c.create_rectangle(x-34, y-30, x+34, y+30, fill="#141b24",
                               outline="#2a3644")
            c.create_text(x, y-16, text=labels[i], fill="#6d8098",
                          font=("Consolas", 8, "bold"))
            c.create_oval(x-16, y-8, x+16, y+24, fill=col, outline="#0b0f15")
            c.create_text(x, y+8, text=f"{out:.0f}°", fill="#0b0f15",
                          font=("Consolas", 9, "bold"))
            c.create_text(x, y+26, text=f"in {inn:.0f}°", fill="#5a6b7d",
                          font=("Consolas", 7))


class WindRose(tk.Canvas):
    """Роза ветров + скорость ветра."""

    def __init__(self, master, store, size=150, **kw):
        super().__init__(master, width=size, height=size, bg="#0b0f15",
                         highlightthickness=0, **kw)
        self.store = store

    def redraw(self):
        c = self
        w = int(c.winfo_width() or self.winfo_reqwidth())
        h = int(c.winfo_height() or self.winfo_reqheight())
        c.delete("all")
        s = self.store
        cx, cy = w/2, h/2 + 6
        r = min(w, h) * 0.34
        c.create_oval(cx-r, cy-r, cx+r, cy+r, outline="#2a3644")
        for lbl, ang in [("N", 90), ("E", 0), ("S", 270), ("W", 180)]:
            x = cx + (r + 9) * math.cos(math.radians(ang))
            y = cy - (r + 9) * math.sin(math.radians(ang))
            c.create_text(x, y, text=lbl, fill="#4a5c70", font=("Consolas", 8))
        a = math.radians(s.wind_dir_deg)
        # вектор: куда дует ветер
        ex = cx + r * 0.8 * math.cos(a)
        ey = cy - r * 0.8 * math.sin(a)
        c.create_line(cx, cy, ex, ey, fill="#4ac8ff", width=3, arrow="last",
                      arrowshape=(9, 12, 4))
        c.create_text(cx, 12, text=f"ВЕТЕР", fill="#6d8098", font=("Consolas", 8, "bold"))
        kmh = s.wind_speed_ms * 3.6
        c.create_text(cx, cy + r + 16,
                      text=f"{s.wind_speed_ms:.1f} m/s ({kmh:.0f} km/h) {s.wind_dir_label}",
                      fill="#cfd8e3", font=("Consolas", 9, "bold"))


class PositionList(tk.Frame):
    """Список пилотов с позициями; локальный пилот подсвечен."""

    def __init__(self, master, store, width=300, height=300, **kw):
        super().__init__(master, bg="#0b0f15", highlightthickness=1,
                         highlightbackground="#2a3644", **kw)
        self.store = store
        self.canvas = tk.Canvas(self, bg="#0b0f15", highlightthickness=0)
        self.scroll = tk.Scrollbar(self, command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scroll.set)
        self.scroll.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.canvas.bind("<MouseWheel>", self._wheel)
        self.canvas.bind("<Button-4>", lambda e: self._wheel_delta(-1))
        self.canvas.bind("<Button-5>", lambda e: self._wheel_delta(1))

    def _wheel(self, event):
        self._wheel_delta(-1 if event.delta > 0 else 1)

    def _wheel_delta(self, n):
        self.canvas.yview_scroll(n, "units")

    def redraw(self):
        c = self.canvas
        c.delete("all")
        s = self.store
        n = s.num_cars or len(s.car_coordinates)
        if n == 0:
            c.create_text(10, 12, anchor="w", text="Нет данных о гонке",
                          fill="#5a6b7d", font=("Segoe UI", 10))
            return
        # ранжирование машин: по пройденной дистанции (lap + frac) если есть,
        # иначе по индексу позиции из ROUNDS для локального
        order = list(range(n))
        try:
            import numpy as np
            coords = np.array(s.car_coordinates) if s.car_coordinates else None
        except Exception:
            coords = None
        row_h = 26
        total_h = row_h * (n + 1)
        c.configure(scrollregion=(0, 0, 300, max(total_h, 100)))
        w = int(c.winfo_width() or 300)
        # позиция относительно локальной: сортировка по дистанции вдоль трассы
        rel = []
        lx = ly = 0
        if s.local_idx < len(s.car_coordinates):
            lx, ly = s.car_coordinates[s.local_idx][0], s.car_coordinates[s.local_idx][1]
        for idx in range(n):
            name = s.car_names[idx] if idx < len(s.car_names) else f"Car {idx+1}"
            cls = s.car_classes[idx] if idx < len(s.car_classes) else ""
            d = 0.0
            if idx < len(s.car_coordinates):
                wx, wy, wz = s.car_coordinates[idx]
                d = (wx - lx) * 0  # расстояние вычисляется ниже через проекцию
            rel.append((idx, name, cls))
        # показываем локального на его реальной позиции P
        my_pos = s.pos or 1
        rows = []
        shown_local_row = None
        # порядок: строки вокруг игрока по индексу машины (в демо это стартовый порядок)
        for k, (idx, name, cls) in enumerate(rel):
            p = k + 1
            # корректируем чтобы локальный был на своей позиции
            if idx == s.local_idx:
                p = my_pos
                shown_local_row = (idx, name, cls, p)
            rows.append((idx, name, cls, p))
        if shown_local_row:
            rows.remove(shown_local_row)
            rows.insert(my_pos - 1, shown_local_row)
        rows.sort(key=lambda t: t[3])
        for row, (idx, name, cls, p) in enumerate(rows):
            y = row * row_h + 6
            is_me = (idx == s.local_idx)
            bg = "#1a2433" if is_me else ("#10161d" if row % 2 else "#0b0f15")
            c.create_rectangle(0, y - 2, w, y + row_h - 4, fill=bg, outline="")
            pc = "#ffd24a" if is_me else "#9fb2c6"
            c.create_text(14, y + 9, text=f"P{p}", fill=pc,
                          font=("Consolas", 11, "bold"), anchor="w")
            cc = {"Pro": "#e8e8e8", "Pro-Am": "#9ee84a", "Am": "#4ac8ff"}.get(cls, "#9fb2c6")
            c.create_text(58, y + 9, text=name[:22], fill="#cfd8e3" if is_me else "#8fa3b8",
                          font=("Consolas", 10, "bold" if is_me else "normal"), anchor="w")
            c.create_text(w - 12, y + 9, text=cls, fill=cc,
                          font=("Consolas", 8), anchor="e")


class WeatherBar(tk.Frame):
    """Верхняя панель погоды: асфальт, воздух, дождь, трасса."""

    def __init__(self, master, store, **kw):
        super().__init__(master, bg="#10151c", **kw)
        self.store = store
        self.items = {}
        specs = [("TRACK", "#8fa3b8"), ("ASPHALT", "#e67e22"),
                 ("AIR", "#4ac8ff"), ("CONDITION", "#9ee84a")]
        for i, (label, color) in enumerate(specs):
            tk.Label(self, text=label, bg="#10151c", fg="#4a5c70",
                     font=("Consolas", 8)).grid(row=0, column=i, padx=14, sticky="w")
            v = tk.Label(self, text="--", bg="#10151c", fg=color,
                         font=("Consolas", 13, "bold"))
            v.grid(row=1, column=i, padx=14, sticky="w")
            self.items[label] = v

    def redraw(self):
        s = self.store
        self.items["TRACK"].config(text=s.track_name)
        self.items["ASPHALT"].config(text=f"{s.pad_temp:.1f} °C")
        self.items["AIR"].config(text=f"{s.air_temp:.1f} °C")
        wet = "WET" if s.wetness > 0.5 else "DRY"
        self.items["CONDITION"].config(text=f"{wet} · {s.weather_label}")
