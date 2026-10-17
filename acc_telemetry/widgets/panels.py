"""Tk dashboard panels. All panels receive one consistent main-thread snapshot."""
import math
import tkinter as tk
from tkinter import ttk

BG, FG, MUTED = '#0a0a0a', '#eeeeee', '#999999'
CYAN, GREEN, RED, YELLOW = '#00d9ff', '#00ff66', '#ff4545', '#ffd700'
FONT = 'Consolas'


def value(number, suffix='', digits=1):
    return '--' if number is None else f'{number:.{digits}f}{suffix}'


class SpeedDial(tk.Canvas):
    """Digital gear display; RPM strip uses a labelled visual scale, not a rev limit."""
    def __init__(self, master, **kw):
        super().__init__(master, height=300, width=1, bg=BG, highlightthickness=0, **kw)

    def render(self, state):
        self.delete('all')
        w, h = max(10, self.winfo_width()), max(10, self.winfo_height())
        gear = '--' if state.gear is None else 'R' if state.gear < 0 else 'N' if state.gear == 0 else str(state.gear)
        self.create_text(14, 18, anchor='w', text=f'КРУГ  {state.current_lap or "--"}', fill=MUTED, font=(FONT, 10))
        self.create_text(w/2, max(50, (h-105)*.50), text=gear, fill=FG,
                         font=(FONT, -max(36, int(min(w*.69, (h-130)*.82))), 'bold'))
        self.create_text(14, h-111, anchor='w', text='СКОРОСТЬ', fill=MUTED, font=(FONT, 9))
        self.create_text(w-14, h-76, anchor='se', text=value(state.speed, '', 0), fill=CYAN,
                         font=(FONT, -max(24, int(min(w*.22, 66))), 'bold'))
        self.create_text(w-14, h-65, anchor='e', text='KM/H', fill=MUTED, font=(FONT, 9))
        self.create_line(0, h-53, w, h-53, fill='#2a2a2a')
        for i in range(20):
            on = state.rpm is not None and state.rpm / 9000 >= (i+1)/20
            color = GREEN if i < 12 else YELLOW if i < 17 else RED
            x = 12 + i*(w-24)/20
            self.create_rectangle(x, h-43, x+(w-24)/20-3, h-30,
                                  fill=color if on else '#1b1b1b', outline='')
        self.create_text(12, h-14, anchor='w', text=value(state.rpm, ' RPM', 0), fill=FG, font=(FONT, 10, 'bold'))
        self.create_text(w-12, h-14, anchor='e', text='/ 9000', fill=MUTED, font=(FONT, 9))


class PedalPanel(tk.Canvas):
    def __init__(self, master, **kw):
        super().__init__(master, width=1, height=140, bg=BG, highlightthickness=0, **kw)

    def render(self, state):
        self.delete('all')
        w, h = self.winfo_width(), self.winfo_height()
        for i, (label, val, color) in enumerate([('ГАЗ', state.gas, GREEN), ('ТОРМОЗ', state.brake, RED)]):
            x1, x2 = 12+i*w/2, (i+1)*w/2-12
            self.create_text((x1+x2)/2, 18, text=label, fill=MUTED, font=(FONT, 10))
            self.create_rectangle(x1, 36, x2, h-34, fill='#151515', outline='#303030')
            if val is not None:
                y = h-34-max(0, min(1, val))*(h-70)
                self.create_rectangle(x1+1, y, x2-1, h-35, fill=color, outline='')
            self.create_text((x1+x2)/2, h-16, text=value(None if val is None else val*100, '%', 0),
                             fill=color if val is not None else MUTED, font=(FONT, 12, 'bold'))


class TyrePanel(tk.Canvas):
    def __init__(self, master, **kw):
        super().__init__(master, width=1, height=260, bg=BG, highlightthickness=0, **kw)

    def render(self, state):
        self.delete('all')
        w, h = self.winfo_width(), self.winfo_height()
        for i, name in enumerate(('FL', 'FR', 'RL', 'RR')):
            x1, y1 = 8+(i%2)*w/2, 8+(i//2)*h/2
            x2, y2 = (i%2+1)*w/2-8, (i//2+1)*h/2-8
            cx, cy = (x1+x2)/2, (y1+y2)/2
            t, p = state.tyre_core[i], state.tyre_pressure[i]
            color = MUTED if t is None else RED if t > 105 else GREEN if t >= 75 else CYAN
            self.create_rectangle(x1, y1, x2, y2, outline='#303030', fill='#0d0d0d')
            self.create_text(x1+8, y1+14, anchor='w', text=name, fill=MUTED, font=(FONT, 10))
            # One core temperature only; no invented inner/middle/outer tread values.
            ty1, ty2 = y1+33, max(y1+41, cy-2)
            tw = min(46, (x2-x1)*.46)
            self.create_rectangle(cx-tw/2, ty1, cx+tw/2, ty2, fill='#17261d' if t is not None else '#191919', outline=color)
            self.create_line(cx-tw/2+5, ty1, cx-tw/2+5, ty2, fill=color)
            self.create_line(cx+tw/2-5, ty1, cx+tw/2-5, ty2, fill=color)
            self.create_text(cx, cy+24, text=value(t, '°C'), fill=color, font=(FONT, -max(14, int(min(25, (x2-x1)/5.2))), 'bold'))
            self.create_text(cx, y2-18, text=value(p, ' PSI'), fill=FG, font=(FONT, 10))


class WindRose(tk.Canvas):
    def __init__(self, master, **kw):
        super().__init__(master, width=1, height=108, bg=BG, highlightthickness=0, **kw)

    def render(self, state):
        self.delete('all')
        w, h = self.winfo_width(), self.winfo_height()
        self.create_text(12, 25, anchor='w', text=value(state.wind_speed, ' m/s'), fill=CYAN, font=(FONT, 20, 'bold'))
        self.create_text(12, 56, anchor='w', text=value(None if state.wind_speed is None else state.wind_speed*3.6, ' km/h'), fill=FG, font=(FONT, 11))
        self.create_text(12, 82, anchor='w', text='Курс raw: '+value(state.wind_direction), fill=MUTED, font=(FONT, 10))
        self.create_text(12, 103, anchor='w', text='Без калибровки компаса', fill=MUTED, font=(FONT, 9))


class FuelPanel(tk.Canvas):
    def __init__(self, master, **kw):
        super().__init__(master, width=1, height=160, bg=BG, highlightthickness=0, **kw)

    def render(self, state):
        self.delete('all')
        w, h = self.winfo_width(), self.winfo_height()
        self.create_text(w/2, h*.40, text=value(state.fuel), fill=YELLOW,
                         font=(FONT, -max(24, int(min(60, w*.23))), 'bold'))
        self.create_text(w/2, h*.40+40, text='ЛИТРЫ / СВОЯ МАШИНА', fill=MUTED, font=(FONT, 9))
        self.create_line(12, h-36, w-12, h-36, fill='#2a2a2a')
        self.create_text(w/2, h-18, text='ACC SHARED MEMORY', fill=MUTED, font=(FONT, 9))


class TimingPanel(tk.Canvas):
    def __init__(self, master, **kw):
        super().__init__(master, width=1, height=300, bg=BG, highlightthickness=0, **kw)

    def render(self, state):
        from acc_telemetry.model import fmt_ms
        self.delete('all')
        w, h = self.winfo_width(), self.winfo_height()
        tile_h = min(125, h*.32)
        self.create_line(w/2, 0, w/2, tile_h, fill='#2a2a2a')
        self.create_line(0, tile_h, w, tile_h, fill='#2a2a2a')
        for i, (label, text) in enumerate([('ПОЗИЦИЯ', str(state.position or '--')), ('КРУГ', str(state.current_lap or '--'))]):
            self.create_text(w*(i*.5+.25), 20, text=label, fill=MUTED, font=(FONT, 9))
            self.create_text(w*(i*.5+.25), tile_h*.60, text=text, fill=FG, font=(FONT, -max(26,int(min(55,w*.23))), 'bold'))
        own = state.cars.get(state.selected_id)
        times = [('ТЕКУЩИЙ', state.lap_ms, CYAN), ('ПОСЛЕДНИЙ', own.last_ms if own else 0, FG), ('ЛУЧШИЙ', state.best_ms, '#e75bff')]
        step = min(94, (h-tile_h-24)/3)
        for i, (label, ms, color) in enumerate(times):
            y = tile_h+12+i*step
            self.create_text(12, y+8, anchor='w', text=label, fill=MUTED, font=(FONT, 9))
            self.create_text(w-12, y+step*.60, anchor='e', text=fmt_ms(ms), fill=color,
                             font=(FONT, -max(17,int(min(29,w/8))), 'bold'))
            if i<2:
                self.create_line(12, y+step-3, w-12, y+step-3, fill='#1c1c1c')


class PositionList(ttk.Frame):
    def __init__(self, master, on_select=None, **kw):
        super().__init__(master, **kw)
        self.on_select = on_select
        self.tree = ttk.Treeview(self, columns=('pos', 'name', 'model', 'gap', 'int'), show='headings',
                                 selectmode='browse', height=14)
        for name, title, width in [('pos', 'P', 32), ('name', 'Пилот / класс', 220),
                                   ('model', 'Машина', 145), ('gap', 'Лидер', 76), ('int', 'Инт.', 76)]:
            self.tree.heading(name, text=title)
            self.tree.column(name, width=width, minwidth=width, stretch=name == 'name')
        self.tree.tag_configure('player', foreground=YELLOW)
        self.tree.tag_configure('pit', foreground=CYAN)
        scroll = ttk.Scrollbar(self, orient='vertical', command=self.tree.yview)
        xscroll = ttk.Scrollbar(self, orient='horizontal', command=self.tree.xview)
        self.tree.configure(yscrollcommand=scroll.set, xscrollcommand=xscroll.set)
        scroll.pack(side='right', fill='y')
        xscroll.pack(side='bottom', fill='x')
        self.tree.pack(fill='both', expand=True)
        self.tree.bind('<<TreeviewSelect>>', self._select)
        self.bind('<Configure>', self._layout)
        self._layout()

    def _layout(self, event=None):
        # Keep readable pilot names and both timing columns on compact screens.
        # The selected car's model remains visible in the dedicated pilot panel.
        wide = self.winfo_width() >= 660
        self.tree.configure(displaycolumns=('pos', 'name', 'model', 'gap', 'int') if wide else ('pos', 'name', 'gap', 'int'))
        self.tree.column('name', minwidth=180 if not wide else 220, width=220, stretch=True)
        for name in ('gap', 'int'):
            self.tree.column(name, minwidth=68, width=68, stretch=False)

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
