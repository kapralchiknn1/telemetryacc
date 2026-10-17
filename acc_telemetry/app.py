"""ACC desktop dashboard. Works as a script, python -m package, or PyInstaller exe."""
from pathlib import Path
import json
import logging
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
from acc_telemetry.widgets.panels import SpeedDial, TyrePanel, WindRose, PositionList, PedalPanel, FuelPanel, TimingPanel, value

BG, PANEL, FG = '#000000', '#0a0a0a', '#eeeeee'


def resource_path(relative):
    base = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent.parent))
    return base / relative


class Dashboard(tk.Tk):
    def __init__(self, args):
        super().__init__()
        self.title('ACC PIT WALL — Telemetry')
        self.geometry('1440x920')
        self.minsize(1100, 760)
        self.configure(bg=BG)
        self.attributes('-fullscreen', args.fullscreen)
        self.bind('<Escape>', lambda e: self.attributes('-fullscreen', False))
        self.store = TelemetryStore()
        self.feeds = FeedController(self.store, args.host, args.port, args.password)
        self.startup_warning = args.startup_warning
        self.custom_outline = None
        self.outline_key = None
        self.outline = []
        self.outline_error = ''
        self.after_id = None
        self.callback_errors = []
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

    def report_callback_exception(self, exc_type, exc_value, traceback):
        self.callback_errors.append(str(exc_value))
        logging.error('Tk callback failed', exc_info=(exc_type, exc_value, traceback))
        # Tk's default reporter writes to stderr, which does not exist in a
        # --windowed exe. The launcher provides a persistent UTF-8 log instead.

    def _build_style(self):
        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure('.', font=('Consolas', 10), background=PANEL, foreground=FG)
        style.configure('TFrame', background=PANEL)
        style.configure('TButton', background='#161616', foreground=FG, padding=(8, 6), borderwidth=1, relief='flat')
        style.map('TButton', background=[('active', '#303030'), ('pressed', '#404040')], foreground=[('disabled', '#777777')])
        style.configure('TCheckbutton', background=PANEL, foreground=FG, padding=4)
        style.map('TCheckbutton', background=[('active', '#222222')])
        style.configure('Treeview', background=PANEL, fieldbackground=PANEL, foreground=FG,
                        rowheight=28, font=('Consolas', 10), borderwidth=0)
        style.configure('Treeview.Heading', background='#161616', foreground='#b0b0b0', font=('Consolas', 9), padding=(3, 6), relief='flat')
        style.map('Treeview', background=[('selected', '#15363c')], foreground=[('selected', '#ffffff')])
        style.map('Treeview.Heading', background=[('active', '#282828')])
        style.configure('TScrollbar', background='#303030', troughcolor='#0d0d0d', bordercolor='#1a1a1a', arrowcolor='#aaaaaa')

    def _panel(self, parent, title):
        shell = tk.Frame(parent, bg=PANEL, highlightbackground='#2a2a2a', highlightthickness=1)
        tk.Label(shell, text=title, bg='#161616', fg='#aaaaaa', font=('Consolas', 9), anchor='w', padx=10, pady=5).pack(fill='x')
        body = tk.Frame(shell, bg=PANEL)
        body.pack(fill='both', expand=True)
        body.shell = shell
        return body

    def _build_ui(self):
        self.rowconfigure(2, weight=1)
        self.columnconfigure(0, weight=1)
        top = tk.Frame(self, bg=PANEL, highlightbackground='#2a2a2a', highlightthickness=1)
        top.grid(row=0, column=0, sticky='ew', padx=2, pady=(2, 0))
        tk.Label(top, text='● ACC PIT WALL', bg=PANEL, fg='#ff4545', font=('Consolas', 13, 'bold'), padx=12).pack(side='left')
        self.status = tk.Label(top, bg=PANEL, fg=FG, font=('Consolas', 10, 'bold'))
        self.status.pack(side='left', padx=10)
        self.demo_button = ttk.Button(top, text='Демо', command=lambda: self._switch(not self.feeds.demo))
        self.demo_button.pack(side='right', padx=4, pady=4)
        ttk.Button(top, text='Переподключить', command=lambda: self._switch(self.feeds.demo)).pack(side='right', padx=2)
        ttk.Button(top, text='Полный экран', command=self.toggle_fs).pack(side='right', padx=2)
        self.weather = tk.Label(self, bg=BG, fg='#aaaaaa', font=('Consolas', 10), anchor='w', padx=12, pady=8)
        self.weather.grid(row=1, column=0, sticky='ew')
        main = tk.Frame(self, bg='#202020')
        main.grid(row=2, column=0, sticky='nsew', padx=2)
        main.rowconfigure(0, weight=1)
        columns = []
        for i, weight in enumerate((24, 20, 20, 36)):
            main.columnconfigure(i, weight=weight, uniform='pitwall')
            col = tk.Frame(main, bg=BG, width=1, height=1)
            col.grid(row=0, column=i, sticky='nsew', padx=(0, 2) if i<3 else 0)
            col.grid_propagate(False)
            col.columnconfigure(0, weight=1)
            columns.append(col)
        vital, center, timing, field = columns
        vital.rowconfigure(0, weight=4)
        vital.rowconfigure(1, weight=1, minsize=174)
        ps = self._panel(vital, 'ПЕРЕДАЧА // RPM // СКОРОСТЬ')
        ps.shell.grid(row=0, column=0, sticky='nsew', pady=(0, 2))
        self.dial = SpeedDial(ps)
        self.dial.pack(fill='both', expand=True)
        pi = self._panel(vital, 'ПЕДАЛИ · СВОЯ МАШИНА')
        pi.shell.grid(row=1, column=0, sticky='nsew')
        self.pedals = PedalPanel(pi)
        self.pedals.pack(fill='both', expand=True)
        center.rowconfigure(0, weight=3, minsize=290)
        center.rowconfigure(1, weight=1, minsize=153)
        center.rowconfigure(2, weight=0, minsize=150)
        pt = self._panel(center, 'ШИНЫ · CORE °C / PSI')
        pt.shell.grid(row=0, column=0, sticky='nsew', pady=(0, 2))
        self.tyres = TyrePanel(pt)
        self.tyres.pack(fill='both', expand=True)
        pf = self._panel(center, 'ТОПЛИВО')
        pf.shell.grid(row=1, column=0, sticky='nsew', pady=(0, 2))
        self.fuel = FuelPanel(pf)
        self.fuel.pack(fill='both', expand=True)
        pw = self._panel(center, 'ВЕТЕР')
        pw.shell.grid(row=2, column=0, sticky='nsew')
        self.wind = WindRose(pw)
        self.wind.pack(fill='both', expand=True)
        timing.rowconfigure(0, weight=3, minsize=340)
        timing.rowconfigure(1, weight=2, minsize=230)
        pe = self._panel(timing, 'ТАЙМИНГ · СВОЯ МАШИНА')
        pe.shell.grid(row=0, column=0, sticky='nsew', pady=(0, 2))
        self.extra = TimingPanel(pe)
        self.extra.pack(fill='both', expand=True)
        pr = self._panel(timing, 'ВЫБРАННЫЙ ПИЛОТ · 2D')
        pr.shell.grid(row=1, column=0, sticky='nsew')
        self.rival_canvas = tk.Canvas(pr, bg=PANEL, highlightthickness=0, width=1, height=1)
        self.rival_canvas.pack(fill='both', expand=True)
        self.rival = RivalModelPanel(self.rival_canvas)
        field.rowconfigure(0, weight=1)
        field.rowconfigure(1, weight=1)
        pp = self._panel(field, 'ПОЗИЦИИ · ЛИДЕР / ИНТЕРВАЛ')
        pp.shell.grid(row=0, column=0, sticky='nsew', pady=(0, 2))
        self.positions = PositionList(pp, on_select=self._select_rival)
        self.positions.pack(fill='both', expand=True)
        pm = self._panel(field, 'КАРТА · ПЕРЕМЕЩЕНИЕ И СЛЕЖЕНИЕ')
        pm.shell.grid(row=1, column=0, sticky='nsew')
        tools = ttk.Frame(pm)
        tools.pack(fill='x', padx=4, pady=4)
        self.follow_var = tk.BooleanVar(value=False)
        self.map = TrackMap(pm, on_view_change=self._map_view_changed)
        ttk.Button(tools, text='Вся трасса', command=self.map.fit_all).pack(side='left', padx=(0, 3))
        ttk.Button(tools, text='К своему', command=self.map.follow_player).pack(side='left', padx=(0, 3))
        ttk.Button(tools, text='За выбранным', command=lambda: self.map.follow_car(self.rival.selected)).pack(side='left')
        follow_tools = ttk.Frame(pm)
        follow_tools.pack(fill='x', padx=4)
        ttk.Checkbutton(follow_tools, text='Следить', variable=self.follow_var,
                        command=lambda: self.map.set_follow(self.follow_var.get())).pack(side='left')
        tk.Label(follow_tools, text='ЛКМ: сдвиг · колесо: масштаб', bg=PANEL, fg='#999999', font=('Consolas', 9)).pack(side='left', padx=4)
        self.map.pack(fill='both', expand=True)
        self.diagnostics = tk.Label(self, bg=PANEL, fg='#aaaaaa', font=('Consolas', 9), anchor='w', justify='left', padx=10, pady=7, wraplength=1380)
        self.diagnostics.grid(row=3, column=0, sticky='ew', padx=2, pady=2)
        self.bind('<Configure>', self._resize)

    def _resize(self, event):
        if event.widget is self:
            self.diagnostics.configure(wraplength=max(500, event.width - 24))

    def _map_view_changed(self, follow):
        self.follow_var.set(follow)

    def _select_rival(self, car_id):
        self.rival.selected = car_id

    def _switch(self, demo):
        try:
            self.feeds.start(demo)
        except RuntimeError as exc:
            messagebox.showerror('Источник данных', str(exc), parent=self)
            return
        if not demo and self.startup_warning:
            logging.warning(self.startup_warning)
            with self.store.lock:
                self.store.state.broadcast_error = self.startup_warning
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
        self.status.config(text=label, fg='#ffd700' if s.demo else '#00ff66' if udp or shared else '#ff4545')
        remaining = '--' if s.session_remaining_ms is None else f'{int(s.session_remaining_ms / 60000)} мин'
        self.weather.config(text=f'{s.track}   ·   Воздух {value(s.air, " °C")}   ·   Асфальт {value(s.road, " °C")}   ·   '
                                 f'Влажность {value(None if s.wetness is None else s.wetness * 100, "%", 0)}   ·   Осталось {remaining}')
        self.map.render(s, self._get_outline(s))
        self.positions.render(s)
        self.rival.render(s)
        self.dial.render(s)
        self.tyres.render(s)
        self.wind.render(s)
        self.pedals.render(s)
        self.fuel.render(s)
        self.extra.render(s)
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
    app = Dashboard(args)
    result = {'ok': not args.smoke_test, 'mode': 'demo' if args.demo else 'live'}
    if args.smoke_test:
        def verify_window():
            try:
                app.update_idletasks()
                if not app.winfo_viewable():
                    raise RuntimeError('Dashboard window was not mapped')
                if app.callback_errors:
                    raise RuntimeError('Tk callbacks failed: ' + '; '.join(app.callback_errors))
                if args.demo and len(app.positions.tree.get_children()) != 12:
                    raise RuntimeError('Demo car list was not rendered')
                result['ok'] = True
            except Exception as exc:
                result['ok'] = False
                result['error'] = str(exc)
                logging.exception('Frozen smoke test failed')
            finally:
                try:
                    app._close()
                except Exception as exc:
                    result['ok'] = False
                    result['error'] = str(exc)
                    logging.exception('Shutdown failed')
        app.after(1200, verify_window)
    app.mainloop()
    if args.smoke_report:
        args.smoke_report.write_text(json.dumps(result), encoding='utf-8')
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
