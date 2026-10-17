"""ACC desktop dashboard. Works as a script, python -m package, or PyInstaller exe."""
from pathlib import Path
import sys
import time
import tkinter as tk
from tkinter import ttk, messagebox

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from acc_telemetry.config import parse_args
from acc_telemetry.model import TelemetryStore, fmt_ms
from acc_telemetry.feeds import FeedController
from acc_telemetry.track_map import REFERENCE_TRACK, load_track
from acc_telemetry.widgets.track_map import TrackMap
from acc_telemetry.widgets.car_model import RivalModelPanel
from acc_telemetry.widgets.panels import SpeedDial, TyrePanel, WindRose, PositionList, value

BG, PANEL, FG = '#0b0f15', '#101b28', '#d4dfeb'


def resource_path(relative):
    base = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent.parent))
    return base / relative


class Dashboard(tk.Tk):
    def __init__(self, args):
        super().__init__()
        self.title('ACC Telemetry Dashboard')
        self.geometry('1440x920')
        self.minsize(1100, 760)
        self.configure(bg=BG)
        self.attributes('-fullscreen', args.fullscreen)
        self.bind('<Escape>', lambda e: self.attributes('-fullscreen', False))
        self.store = TelemetryStore()
        self.feeds = FeedController(self.store, args.host, args.port, args.password)
        self.custom_outline = None
        self.outline_key = None
        self.outline = []
        self.outline_error = ''
        self.after_id = None
        if args.track_map:
            try:
                self.custom_outline = load_track(args.track_map)
            except (OSError, ValueError) as exc:
                messagebox.showerror('Контур трассы', str(exc), parent=self)
        self._build_style()
        self._build_ui()
        self.protocol('WM_DELETE_WINDOW', self._close)
        self._switch(args.demo)
        self._tick()

    def _build_style(self):
        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure('TFrame', background=PANEL)
        style.configure('TLabelframe', background=PANEL)
        style.configure('TLabelframe.Label', background=PANEL, foreground=FG, font=('Segoe UI', 10, 'bold'))
        style.configure('TButton', background='#24394f', foreground=FG, padding=6)
        style.map('TButton', background=[('active', '#355477')])
        style.configure('Treeview', background=BG, fieldbackground=BG, foreground=FG,
                        rowheight=28, font=('Segoe UI', 9))
        style.configure('Treeview.Heading', background='#24394f', foreground=FG)
        style.map('Treeview', background=[('selected', '#324863')])

    def _panel(self, parent, title):
        return ttk.LabelFrame(parent, text=title, padding=6)

    def _build_ui(self):
        top = tk.Frame(self, bg=PANEL)
        top.pack(fill='x', padx=8, pady=8)
        self.status = tk.Label(top, bg=PANEL, fg=FG, font=('Segoe UI', 11, 'bold'))
        self.status.pack(side='left', padx=8)
        self.demo_button = ttk.Button(top, text='Демо', command=lambda: self._switch(not self.feeds.demo))
        self.demo_button.pack(side='right', padx=4)
        ttk.Button(top, text='Переподключить', command=lambda: self._switch(self.feeds.demo)).pack(side='right', padx=4)
        ttk.Button(top, text='Полный экран', command=self.toggle_fs).pack(side='right', padx=4)
        self.weather = tk.Label(self, bg=BG, fg='#69c3f0', font=('Segoe UI', 11), anchor='w')
        self.weather.pack(fill='x', padx=16, pady=(0, 6))
        main = tk.Frame(self, bg=BG)
        main.pack(fill='both', expand=True, padx=8)
        main.columnconfigure(0, weight=3)
        main.columnconfigure(1, weight=4)
        main.rowconfigure(0, weight=3)
        main.rowconfigure(1, weight=2)
        pm = self._panel(main, 'КАРТА · МЕТРЫ · КОЛЕСО МЫШИ — МАСШТАБ')
        pm.grid(row=0, column=0, sticky='nsew', padx=4, pady=4)
        self.map = TrackMap(pm)
        self.map.pack(fill='both', expand=True)
        pp = self._panel(main, 'ПОЗИЦИИ · ОТСТАВАНИЕ / ИНТЕРВАЛ')
        pp.grid(row=0, column=1, rowspan=2, sticky='nsew', padx=4, pady=4)
        self.positions = PositionList(pp, on_select=self._select_rival)
        self.positions.pack(fill='both', expand=True)
        below = tk.Frame(main, bg=BG)
        below.grid(row=1, column=0, sticky='nsew', padx=4, pady=4)
        below.columnconfigure((0, 1), weight=1)
        below.rowconfigure(0, weight=1)
        pr = self._panel(below, 'СОПЕРНИК')
        pr.grid(row=0, column=0, sticky='nsew', padx=(0, 4))
        self.rival_canvas = tk.Canvas(pr, bg=BG, highlightthickness=0, width=260, height=240)
        self.rival_canvas.pack(fill='both', expand=True)
        self.rival = RivalModelPanel(self.rival_canvas)
        pt = self._panel(below, 'ШИНЫ · CORE °C / PSI')
        pt.grid(row=0, column=1, sticky='nsew')
        self.tyres = TyrePanel(pt)
        self.tyres.pack(fill='both', expand=True)
        bottom = tk.Frame(self, bg=BG)
        bottom.pack(fill='x', padx=12, pady=6)
        ps = self._panel(bottom, 'СВОЯ МАШИНА · SHARED MEMORY')
        ps.pack(side='left', padx=(0, 6))
        self.dial = SpeedDial(ps)
        self.dial.pack()
        pw = self._panel(bottom, 'ВЕТЕР')
        pw.pack(side='left', fill='y', padx=(0, 6))
        self.wind = WindRose(pw)
        self.wind.pack(fill='both', expand=True)
        pe = self._panel(bottom, 'СЕССИЯ / СВОЯ МАШИНА')
        pe.pack(side='left', fill='both', expand=True)
        self.extra = tk.Label(pe, bg=PANEL, fg=FG, font=('Consolas', 12), justify='left', anchor='nw')
        self.extra.pack(fill='both', expand=True, padx=8, pady=8)
        self.diagnostics = tk.Label(self, bg=BG, fg='#8295aa', font=('Segoe UI', 9), anchor='w', wraplength=1380)
        self.diagnostics.pack(side='bottom', fill='x', padx=12, pady=(0, 6))
        # Reserve the fixed bottom panels BEFORE giving the map/table remaining space.
        # Otherwise pack can clip the telemetry/footer on smaller desktop displays.
        bottom.pack_forget()
        main.pack_forget()
        bottom.pack(side='bottom', fill='x', padx=12, pady=6)
        main.pack(fill='both', expand=True, padx=8)
        self.bind('<Configure>', self._resize)

    def _resize(self, event):
        if event.widget is self:
            self.diagnostics.configure(wraplength=max(500, event.width - 24))

    def _select_rival(self, car_id):
        self.rival.selected = car_id

    def _switch(self, demo):
        try:
            self.feeds.start(demo)
        except RuntimeError as exc:
            messagebox.showerror('Источник данных', str(exc), parent=self)
            return
        self.map.reset()
        self.outline_key = None
        self.rival.selected = None
        self.demo_button.configure(text='Выйти из демо' if demo else 'Демо без игры')

    def _get_outline(self, state):
        key = state.track, state.demo
        if key != self.outline_key:
            self.outline_key, self.outline, self.outline_error = key, [], ''
            if state.demo:
                self.outline = REFERENCE_TRACK
            elif self.custom_outline is not None:
                self.outline = self.custom_outline
            else:
                slug = ''.join(ch if ch.isascii() and ch.isalnum() else '_' for ch in state.track.lower())
                path = resource_path('tracks') / (slug + '.json')
                if path.is_file():
                    try:
                        self.outline = load_track(path)
                    except (OSError, ValueError) as exc:
                        self.outline_error = f'Контур не загружен: {exc}'
        return self.outline

    def _tick(self):
        s = self.store.snapshot()
        now = time.monotonic()
        udp = now - s.broadcast_seen < 3
        shared = now - s.shared_seen < 3
        label = 'DEMO — ТЕСТОВЫЕ ДАННЫЕ' if s.demo else f'ACC: UDP {"ON" if udp else "OFF"} · MEMORY {"ON" if shared else "OFF"}'
        self.status.config(text=label, fg='#ffc34f' if s.demo else '#67cfa0' if udp or shared else '#eb735b')
        remaining = '--' if s.session_remaining_ms is None else f'{int(s.session_remaining_ms / 60000)} мин'
        self.weather.config(text=f'{s.track}   ·   Воздух {value(s.air, " °C")}   ·   Асфальт {value(s.road, " °C")}   ·   '
                                 f'Влажность {value(None if s.wetness is None else s.wetness * 100, "%", 0)}   ·   Осталось {remaining}')
        self.map.render(s, self._get_outline(s))
        self.positions.render(s)
        self.rival.render(s)
        self.dial.render(s)
        self.tyres.render(s)
        self.wind.render(s)
        laps = f'{s.current_lap}' + (f'/{s.total_laps}' if s.total_laps else '') if s.current_lap else '--'
        self.extra.config(text=f'Позиция: {s.position or "--"}     Круг: {laps}\n'
                               f'Текущий: {fmt_ms(s.lap_ms)}\nЛучший:  {fmt_ms(s.best_ms)}\n'
                               f'Топливо: {value(s.fuel, " л")}\n'
                               f'Газ: {value(None if s.gas is None else s.gas * 100, "%", 0)}   '
                               f'Тормоз: {value(None if s.brake is None else s.brake * 100, "%", 0)}')
        notes = [] if s.demo else [s.broadcast_error, s.shared_error]
        if not s.demo and not shared:
            notes.append('Для шин, оборотов, топлива и ветра запустите приложение на Windows-ПК с игрой')
        notes += [self.outline_error, '≈ — оценка по прохождению точек трассы; -- — данных пока нет. Схема машины условная.']
        self.diagnostics.config(text=' · '.join(filter(None, notes)))
        self.after_id = self.after(50, self._tick)

    def toggle_fs(self):
        self.attributes('-fullscreen', not bool(self.attributes('-fullscreen')))

    def _close(self):
        if self.after_id:
            self.after_cancel(self.after_id)
            self.after_id = None
        try:
            self.feeds.stop()
        finally:
            self.destroy()


def main():
    args = parse_args()
    Dashboard(args).mainloop()


if __name__ == '__main__':
    main()
