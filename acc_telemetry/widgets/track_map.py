"""World-coordinate map with drag/zoom and local/team-car following."""
import math
import tkinter as tk
from collections import deque
from acc_telemetry.camera import MapCamera


class TrackMap(tk.Canvas):
    def __init__(self, master, on_view_change=None, **kw):
        super().__init__(master, bg='#0a0a0a', highlightthickness=0, width=500, height=350, **kw)
        self.camera = MapCamera()
        self.on_view_change = on_view_change
        self.outline = []
        self.trail = deque(maxlen=10000)
        self.key = None
        self.trail_target = None
        self.bounds = None
        self.target_id = None  # None = local player, or clearly labelled UDP focus
        self.target_position = None
        self.target_name = ''
        self.notice = ''
        self.drag_origin = None
        self.bind('<MouseWheel>', self._mouse_wheel)
        self.bind('<Button-4>', lambda e: self.wheel(1.15, e.x, e.y))
        self.bind('<Button-5>', lambda e: self.wheel(1 / 1.15, e.x, e.y))
        self.bind('<ButtonPress-1>', self._drag_start)
        self.bind('<B1-Motion>', self._drag_move)
        self.bind('<ButtonRelease-1>', self._drag_end)
        self.bind('<Double-Button-1>', lambda e: self.fit_all())

    @property
    def zoom(self):
        return self.camera.zoom

    def _changed(self):
        if self.on_view_change:
            self.on_view_change(self.camera.follow)

    def _mouse_wheel(self, event):
        if event.delta:
            # Windows wheel detents are 120; fractional trackpad input still works.
            steps = max(-4, min(4, event.delta / 120))
            if abs(steps) < 1:
                steps = 1 if steps > 0 else -1
            self.wheel(1.15 ** steps, event.x, event.y)
        return 'break'

    def wheel(self, factor, x=None, y=None):
        self.camera.wheel(factor, x, y)
        self.notice = ''
        self._changed()

    def fit_all(self):
        self.camera.fit_all()
        self.notice = ''
        self._changed()

    def reset_zoom(self):
        self.fit_all()

    def set_follow(self, enabled):
        self.camera.set_follow(enabled, self.target_position)
        self.notice = ''
        self._changed()

    def follow_player(self):
        self.target_id = None
        self.target_position = None  # never briefly center a previously selected rival
        self.camera.focus()
        self.notice = ''
        self._changed()

    def follow_car(self, car_id):
        if car_id is None:
            self.notice = 'Сначала выберите пилота в таблице'
            return
        self.target_id = car_id
        self.target_position = None
        self.camera.focus()
        self.notice = ''
        self._changed()

    def _drag_start(self, event):
        self.drag_origin = event.x, event.y
        self.configure(cursor='fleur')

    def _drag_move(self, event):
        if self.drag_origin is None:
            return
        x, y = self.drag_origin
        dx, dy = event.x - x, event.y - y
        if dx or dy:
            self.camera.pan(dx, dy)
            self.notice = ''
            self.drag_origin = event.x, event.y
            self._changed()
        return 'break'

    def _drag_end(self, event):
        self.drag_origin = None
        self.configure(cursor='')

    def reset(self):
        self.key = None
        self.trail.clear()
        self.trail_target = None
        self.bounds = None
        self.camera = MapCamera()
        self.target_id = self.target_position = None
        self.target_name = self.notice = ''
        self.drag_origin = None
        self._changed()

    def render(self, state, outline=()):
        self.delete('all')
        w, h = max(10, self.winfo_width()), max(10, self.winfo_height())
        key = (state.track, state.demo)
        if key != self.key:
            self.reset()
            self.key = key
        cars = [c for c in state.cars.values() if c.located]
        observed_id = state.selected_id if self.target_id is None else self.target_id
        observed = state.cars.get(observed_id)
        if self.trail_target != observed_id:
            self.trail.clear()
            self.trail_target = observed_id
        self.target_position = (observed.x, observed.y) if observed and observed.located else None
        if self.target_id is not None:
            self.target_name = (observed.name or f'Car {observed_id}') if observed else f'Car {observed_id}'
        else:
            self.target_name = 'Свой пилот' if state.player_id >= 0 else 'Фокус UDP (игрок не определён)'
        if self.target_position and (not self.trail or math.dist(self.target_position, self.trail[-1]) >= 2):
            self.trail.append(self.target_position)
        self.outline = list(outline)
        points = self.outline or list(self.trail)
        all_points = points + [(c.x, c.y) for c in cars]
        if all_points:
            xs, ys = zip(*all_points)
            limits = min(xs), min(ys), max(xs), max(ys)
            if self.outline or self.bounds is None:
                self.bounds = limits
            else:
                a, b, c, d = self.bounds
                self.bounds = min(a, limits[0]), min(b, limits[1]), max(c, limits[2]), max(d, limits[3])
        if self.bounds is None:
            self.create_text(w/2, h/2, text='Ожидание позиций машин', fill='#aaaaaa', font=('Segoe UI', 12))
            return
        self.camera.update(self.bounds, w, h, self.target_position)
        project = self.camera.project
        if len(points) > 1:
            drawn = points + points[:1] if self.outline else points
            flat = [v for p in drawn for v in project(*p)]
            self.create_line(flat, fill='#343434', width=9 if self.outline else 3, joinstyle='round')
        if self.outline and len(self.trail) > 1:
            flat = [v for p in self.trail for v in project(*p)]
            self.create_line(flat, fill='#7a7037', width=2)
        labels = []
        for car in sorted(cars, key=lambda c: c.car_id == observed_id):
            x, y = project(car.x, car.y)
            if not (-40 <= x <= w + 40 and -40 <= y <= h + 40):
                continue
            own, watched = car.car_id == state.selected_id, car.car_id == observed_id
            color = '#ffd700' if own else '#00d9ff' if car.in_pit else '#eeeeee'
            r = 7 if own or watched else 4
            self.create_oval(x-r, y-r, x+r, y+r, fill=color, outline='#0a0a0a')
            if watched and self.camera.follow:
                self.create_oval(x-13, y-13, x+13, y+13, outline='#00ff66', width=2)
            label = ('ВЫ' if state.player_id >= 0 else 'ФОКУС UDP') if own else (car.name[:20] if watched else str(car.position or car.car_id))
            labels.append((0 if own else 1 if watched else 2, x, y-19, label, color))
        placed = []
        for _, x, y, label, color in sorted(labels, key=lambda item: item[0]):
            item = self.create_text(x, y, text=label, fill=color, font=('Consolas', 9))
            box = self.bbox(item)
            if not box:
                continue
            a, b, c, d = box
            overlaps = any(a < r+3 and c > l-3 and b < bot+3 and d > top-3 for l, top, r, bot in placed)
            if overlaps or a < 2 or c > w-2 or b < 43 or d > h-24:
                self.delete(item)
            else:
                placed.append(box)
        subtitle = 'Контур трассы' if self.outline else 'Записанный след (не готовый контур)'
        mode = ('Слежение: ' + self.target_name if self.target_position else 'Ожидание выбранного пилота') if self.camera.follow else 'Обзор' if self.camera.overview else 'Свободная карта'
        # HUD has an opaque background so off-screen parts of a zoomed track cannot obscure it.
        self.create_rectangle(0, 0, w, 42, fill='#0a0a0a', outline='')
        self.create_rectangle(0, h-23, w, h, fill='#0a0a0a', outline='')
        self.create_text(10, 12, anchor='w', text=state.track, fill='#eeeeee', font=('Consolas', 11, 'bold'))
        self.create_text(10, 31, anchor='w', text=self.notice or mode, fill='#00ff66' if self.camera.follow else '#aaaaaa', font=('Segoe UI', 9))
        self.create_text(10, h-12, anchor='w', text=subtitle, fill='#aaaaaa', font=('Segoe UI', 9))
        self.create_text(w-10, 12, anchor='e', text=f'{self.zoom:.1f}x', fill='#aaaaaa')
