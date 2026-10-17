"""Tk dashboard panels. All panels receive one consistent main-thread snapshot."""
import math
import tkinter as tk
from tkinter import ttk

BG, FG, MUTED = '#0b0f15', '#d4dfeb', '#8295aa'


def value(number, suffix='', digits=1):
    return '--' if number is None else f'{number:.{digits}f}{suffix}'


class SpeedDial(tk.Canvas):
    def __init__(self, master, **kw):
        super().__init__(master, height=190, width=240, bg=BG, highlightthickness=0, **kw)

    def render(self, state):
        self.delete('all')
        w, h = self.winfo_width(), self.winfo_height()
        cx, cy, r = w / 2, h * .53, min(w * .38, h * .42)
        self.create_arc(cx-r, cy-r, cx+r, cy+r, start=-40, extent=260,
                        outline='#213348', style='arc', width=10)
        if state.rpm is not None:
            self.create_arc(cx-r, cy-r, cx+r, cy+r, start=220,
                            extent=-260 * min(1, state.rpm / 9000),
                            outline='#49b7ed', style='arc', width=10)
        self.create_text(cx, cy-18, text=value(state.speed, '', 0), fill=FG,
                         font=('Consolas', 30, 'bold'))
        self.create_text(cx, cy+12, text='km/h', fill=MUTED, font=('Consolas', 10))
        gear = '--' if state.gear is None else 'R' if state.gear < 0 else 'N' if state.gear == 0 else str(state.gear)
        self.create_text(cx, cy+40, text=gear, fill='#ffd24a', font=('Consolas', 22, 'bold'))
        self.create_text(cx, 12, text=value(state.rpm, ' RPM', 0), fill=MUTED, font=('Consolas', 11))


class TyrePanel(tk.Canvas):
    def __init__(self, master, **kw):
        super().__init__(master, width=270, height=220, bg=BG, highlightthickness=0, **kw)

    def render(self, state):
        self.delete('all')
        w, h = self.winfo_width(), self.winfo_height()
        for i, (name, fx, fy) in enumerate([('FL', .25, .28), ('FR', .75, .28),
                                          ('RL', .25, .72), ('RR', .75, .72)]):
            x, y = w * fx, h * fy
            half_h = min(35, h * .20)
            t, p = state.tyre_core[i], state.tyre_pressure[i]
            # Temperature colour is descriptive, not a setup recommendation.
            color = MUTED if t is None else '#eb735b' if t > 105 else '#67cfa0' if t >= 75 else '#57aee8'
            self.create_rectangle(x-47, y-half_h, x+47, y+half_h, outline=color, fill='#121c28')
            self.create_text(x, y-half_h*.67, text=name, fill=MUTED, font=('Consolas', 9))
            self.create_text(x, y-1, text=value(t, ' °C'), fill=color, font=('Consolas', 13, 'bold'))
            self.create_text(x, y+half_h*.65, text=value(p, ' psi'), fill=FG, font=('Consolas', 10))


class WindRose(tk.Canvas):
    def __init__(self, master, **kw):
        super().__init__(master, width=220, height=120, bg=BG, highlightthickness=0, **kw)

    def render(self, state):
        self.delete('all')
        w = self.winfo_width()
        self.create_text(w/2, 22, text=value(state.wind_speed, ' m/s'), fill='#63c9fa',
                         font=('Consolas', 18, 'bold'))
        self.create_text(w/2, 52, text=value(None if state.wind_speed is None else state.wind_speed * 3.6, ' km/h'),
                         fill=FG, font=('Consolas', 11))
        self.create_text(w/2, 82, text='Курс ACC (raw): ' + value(state.wind_direction),
                         fill=MUTED, font=('Consolas', 9))
        self.create_text(w/2, 103, text='Направление не калибровано', fill=MUTED, font=('Segoe UI', 8))


class PositionList(ttk.Frame):
    def __init__(self, master, on_select=None, **kw):
        super().__init__(master, **kw)
        self.on_select = on_select
        self.tree = ttk.Treeview(self, columns=('pos', 'name', 'model', 'gap', 'int'), show='headings',
                                 selectmode='browse', height=14)
        for name, title, width in [('pos', 'P', 40), ('name', 'Пилот / класс', 165),
                                   ('model', 'Машина', 160), ('gap', 'Лидер', 90), ('int', 'Интервал', 90)]:
            self.tree.heading(name, text=title)
            self.tree.column(name, width=width, minwidth=35, stretch=name in ('name', 'model'))
        self.tree.tag_configure('player', foreground='#ffd24a')
        self.tree.tag_configure('pit', foreground='#69c3f0')
        scroll = ttk.Scrollbar(self, orient='vertical', command=self.tree.yview)
        xscroll = ttk.Scrollbar(self, orient='horizontal', command=self.tree.xview)
        self.tree.configure(yscrollcommand=scroll.set, xscrollcommand=xscroll.set)
        scroll.pack(side='right', fill='y')
        xscroll.pack(side='bottom', fill='x')
        self.tree.pack(fill='both', expand=True)
        self.tree.bind('<<TreeviewSelect>>', self._select)

    def _select(self, event):
        selection = self.tree.selection()
        if selection and self.on_select:
            self.on_select(int(selection[0]))

    def render(self, state):
        cars = state.ordered_cars()
        expected = {str(c.car_id) for c in cars}
        for iid in self.tree.get_children():
            if iid not in expected:
                self.tree.delete(iid)
        for row, car in enumerate(cars):
            iid = str(car.car_id)
            vals = (car.position or '--', f'#{car.number} {car.name or "Car " + iid} [{car.cup}]' +
                    (' PIT' if car.in_pit else ''), car.model or '--', car.gap, car.interval)
            tags = ('player',) if car.car_id == state.player_id else ('pit',) if car.in_pit else ()
            if self.tree.exists(iid):
                self.tree.item(iid, values=vals, tags=tags)
                self.tree.move(iid, '', row)
            else:
                self.tree.insert('', row, iid=iid, values=vals, tags=tags)
