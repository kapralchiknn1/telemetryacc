"""World-coordinate map. Outlines are real data or explicitly a recorded driving trail."""
import math
import tkinter as tk
from collections import deque


class TrackMap(tk.Canvas):
    def __init__(self, master, **kw):
        super().__init__(master, bg='#0b0f15', highlightthickness=0, width=500, height=350, **kw)
        self.zoom = 1.0
        self.outline = []
        self.trail = deque(maxlen=10000)
        self.key = None
        self.bounds = None
        self.bind('<MouseWheel>', lambda e: self.wheel(1.1 if e.delta > 0 else 1 / 1.1))
        self.bind('<Button-4>', lambda e: self.wheel(1.1))
        self.bind('<Button-5>', lambda e: self.wheel(1 / 1.1))
        self.bind('<Double-Button-1>', lambda e: self.reset_zoom())

    def wheel(self, factor):
        self.zoom = max(.4, min(5, self.zoom * factor))

    def reset_zoom(self):
        self.zoom = 1.0

    def reset(self):
        self.key = None
        self.trail.clear()
        self.bounds = None

    def render(self, state, outline=()):
        self.delete('all')
        w, h = max(10, self.winfo_width()), max(10, self.winfo_height())
        key = (state.track, state.demo, state.selected_id)
        if key != self.key:
            self.reset()
            self.key = key
        cars = [c for c in state.cars.values() if c.located]
        own = state.cars.get(state.selected_id)
        if own and own.located and (not self.trail or math.dist((own.x, own.y), self.trail[-1]) >= 2):
            self.trail.append((own.x, own.y))
        self.outline = list(outline)
        points = self.outline or list(self.trail)
        all_points = points + [(c.x, c.y) for c in cars]
        if not all_points:
            self.create_text(w/2, h/2, text='Ожидание позиций машин', fill='#8295aa', font=('Segoe UI', 12))
            return
        xs, ys = zip(*all_points)
        limits = (min(xs), min(ys), max(xs), max(ys))
        if self.outline or self.bounds is None:
            self.bounds = limits
        else:
            a, b, c, d = self.bounds
            self.bounds = (min(a, limits[0]), min(b, limits[1]), max(c, limits[2]), max(d, limits[3]))
        a, b, c, d = self.bounds
        cx, cy = (a+c)/2, (b+d)/2
        scale = min((w-50)/max(50, c-a), (h-70)/max(50, d-b)) * self.zoom

        def project(x, y):
            return w/2 + (x-cx)*scale, h/2 - (y-cy)*scale

        if len(points) > 1:
            drawn = points + points[:1] if self.outline else points
            flat = [v for p in drawn for v in project(*p)]
            self.create_line(flat, fill='#243b53', width=9 if self.outline else 3, joinstyle='round')
        if self.outline and len(self.trail) > 1:
            flat = [v for p in self.trail for v in project(*p)]
            self.create_line(flat, fill='#7a7037', width=2)
        for car in sorted(cars, key=lambda c: c.car_id == state.selected_id):
            x, y = project(car.x, car.y)
            own = car.car_id == state.selected_id
            color = '#ffd24a' if own else '#69c3f0' if car.in_pit else '#d4dfeb'
            r = 7 if own else 4
            self.create_oval(x-r, y-r, x+r, y+r, fill=color, outline='#0b0f15')
            self.create_text(x, y-14, text=('ВЫ' if state.player_id >= 0 else 'ФОКУС') if own
                             else str(car.position or car.car_id), fill=color, font=('Consolas', 9))
        subtitle = 'Контур трассы' if self.outline else 'Записанный след (не готовый контур)'
        self.create_text(10, 12, anchor='w', text=state.track, fill='#d4dfeb', font=('Consolas', 11, 'bold'))
        self.create_text(10, h-14, anchor='w', text=subtitle, fill='#8295aa', font=('Segoe UI', 9))
        self.create_text(w-10, 12, anchor='e', text=f'{self.zoom:.1f}x', fill='#8295aa')
