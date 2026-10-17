# -*- coding: utf-8 -*-
"""
ACC Telemetry Dashboard — мониторинг телеметрии Assetto Corsa Competizione.

Отображает: позицию пилота и соперников, модели машин, карту трассы с точками
позиций, скорость ветра, температуру асфальта, скорость машины, температуры
шин, обороты двигателя, передачу, топливо, круги и лучшее время круга.

Данные читаются из UDP-потока ACC (настраивается в игре:
Settings -> Custom -> UDP Telemetry: IP 127.0.0.1, порт 9000, все пакеты).

Режимы:
  • Реальный — слушает UDP-порт и ждёт данные от запущенной игры.
  • Демо     — встроенный генератор пакетов ACC для проверки интерфейса.

Запуск: acc_telemetry.exe [--demo] [--port 9000] [--fullscreen]
"""

import argparse
import os
import sys
import time
import tkinter as tk
from tkinter import ttk

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from acc_udp import TelemetryStore, ACCUDPReader          # noqa: E402
from widgets.track_map import TrackMap                    # noqa: E402
from widgets.car_model import RivalModelPanel             # noqa: E402
from widgets.panels import SpeedDial, TyrePanel, WindRose, PositionList, WeatherBar  # noqa: E402

APP_TITLE = "ACC Telemetry Dashboard"
BG = "#0b0f15"
PANEL = "#10151c"
BORDER = "#2a3644"


def resource_path(rel):
    """Путь к ресурсу внутри PyInstaller bundle."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)


class Dashboard(tk.Tk):
    def __init__(self, port=9000, demo=False, fullscreen=False):
        super().__init__()
        self.title(APP_TITLE)
        self.configure(bg=BG)
        self.geometry("1280x800")
        self.minsize(1024, 680)
        self.store = TelemetryStore()
        self.port = port
        self.demo = demo
        self.reader = None
        self.demo_gen = None

        if fullscreen:
            self.attributes("-fullscreen", True)
        try:
            icon = resource_path(os.path.join("assets", "app_icon.ico"))
            if os.path.exists(icon):
                self.iconbitmap(icon)
        except Exception:
            pass

        self._build_style()
        self._build_ui()
        self._start_feed()

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(30, self._tick)

    # ---------- стиль ----------
    def _build_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(".", background=PANEL, foreground="#cfd8e3")
        style.configure("TFrame", background=PANEL)
        style.configure("TLabelframe", background=PANEL, bordercolor=BORDER)
        style.configure("TLabelframe.Label", background=PANEL, foreground="#8fa3b8",
                        font=("Consolas", 9, "bold"))
        style.configure("TButton", background="#1d2836", foreground="#cfd8e3",
                        bordercolor=BORDER, focuscolor="#1d2836", font=("Consolas", 9))
        style.map("TButton", background=[("active", "#2a3a4e")])

    def _panel(self, parent, text):
        return ttk.Labelframe(parent, text=text, padding=6)

    # ---------- UI ----------
    def _build_ui(self):
        # верхняя строка: статус + погода + управление
        top = tk.Frame(self, bg=PANEL)
        top.pack(fill="x", padx=8, pady=(8, 4))

        self.lbl_status = tk.Label(top, text="● OFFLINE", bg=PANEL, fg="#e74c3c",
                                   font=("Consolas", 12, "bold"))
        self.lbl_status.pack(side="left", padx=8)

        self.lbl_rate = tk.Label(top, text="", bg=PANEL, fg="#4a5c70",
                                 font=("Consolas", 9))
        self.lbl_rate.pack(side="left", padx=6)

        self.weather = WeatherBar(top, self.store)
        self.weather.pack(side="left", padx=18)

        btns = tk.Frame(top, bg=PANEL)
        btns.pack(side="right")
        self.btn_demo = ttk.Button(btns, text="▶ Демо-режим", command=self.toggle_demo)
        self.btn_demo.pack(side="right", padx=4)
        ttk.Button(btns, text="⟳ Переподключить", command=self.reconnect).pack(side="right", padx=4)
        ttk.Button(btns, text="⛶ Полный экран", command=self.toggle_fs).pack(side="right", padx=4)

        # основная сетка
        main = tk.Frame(self, bg=BG)
        main.pack(fill="both", expand=True, padx=8, pady=4)
        main.columnconfigure(0, weight=3)
        main.columnconfigure(1, weight=2)
        main.columnconfigure(2, weight=2)
        main.rowconfigure(0, weight=3)
        main.rowconfigure(1, weight=2)

        # карта трассы
        p_map = self._panel(main, "КАРТА ТРАССЫ · ПОЗИЦИИ НА СЕССИИ")
        p_map.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
        self.map = TrackMap(p_map, self.store, width=520, height=380)
        self.map.pack(fill="both", expand=True)

        # список позиций
        p_pos = self._panel(main, "ПОЗИЦИИ ПИЛОТОВ")
        p_pos.grid(row=0, column=1, rowspan=2, sticky="nsew", padx=4, pady=4)
        self.plist = PositionList(p_pos, self.store, width=280, height=560)
        self.plist.pack(fill="both", expand=True)

        # правая колонка: модель соперника + шины
        p_riv = self._panel(main, "МОДЕЛЬ СОПЕРНИКА")
        p_riv.grid(row=0, column=2, sticky="nsew", padx=4, pady=4)
        self.riv_canvas = tk.Canvas(p_riv, bg="#0b0f15", highlightthickness=0, height=200)
        self.riv_canvas.pack(fill="both", expand=True)
        self.rival = RivalModelPanel(self.riv_canvas, self.store)

        p_tyres = self._panel(main, "ШИНЫ · ТЕМПЕРАТУРА")
        p_tyres.grid(row=1, column=2, sticky="nsew", padx=4, pady=4)
        self.tyres = TyrePanel(p_tyres, self.store, width=260, height=210)
        self.tyres.pack(fill="both", expand=True)

        # нижний ряд: спидометр + ветер + доп. параметры
        bottom = tk.Frame(self, bg=BG)
        bottom.pack(fill="x", padx=8, pady=4)

        p_speed = self._panel(bottom, "СКОРОСТЬ / ОБОРОТЫ")
        p_speed.pack(side="left", padx=4)
        self.dial = SpeedDial(p_speed, self.store, size=210)
        self.dial.pack()

        p_wind = self._panel(bottom, "ВЕТЕР")
        p_wind.pack(side="left", padx=4)
        self.wind = WindRose(p_wind, self.store, size=150)
        self.wind.pack()

        p_extra = self._panel(bottom, "МАШИНА")
        p_extra.pack(side="left", fill="y", padx=4)
        self.extra_grid = tk.Frame(p_extra, bg=PANEL)
        self.extra_grid.pack(fill="both", expand=True, padx=6, pady=4)
        self.extra_labels = {}
        specs = [("КРУГ", "lap"), ("КРУГОВОЕ ВРЕМЯ", "cur"), ("ЛУЧШИЙ КРУГ", "best"),
                 ("ТОПЛИВО", "fuel"), ("ПЕРЕДАЧА", "gear"), ("FASTER THAN", "delta"),
                 ("DRS", "drs"), ("GAS / BRAKE", "gb")]
        for i, (label, key) in enumerate(specs):
            r, c = divmod(i, 2)
            tk.Label(self.extra_grid, text=label, bg=PANEL, fg="#4a5c70",
                     font=("Consolas", 8)).grid(row=r*2, column=c, sticky="w", padx=10)
            v = tk.Label(self.extra_grid, text="--", bg=PANEL, fg="#cfd8e3",
                         font=("Consolas", 13, "bold"))
            v.grid(row=r*2+1, column=c, sticky="w", padx=10)
            self.extra_labels[key] = v

    # ---------- форматирование времени ----------
    @staticmethod
    def fmt_ms(ms):
        if ms <= 0:
            return "--:--.---"
        m = ms // 60000
        s = (ms % 60000) / 1000.0
        return f"{m}:{int(s):02d}.{(s % 1):06.3f}"[0:-1] if False else f"{m}:{int(s):02d}.{ms % 1000:03d}"

    # ---------- цикл обновления ----------
    def _tick(self):
        s = self.store
        # статус
        st = s.status
        if st == "CONNECTED":
            self.lbl_status.config(text="● LIVE (ACC)", fg="#2ecc71")
        elif st == "DEMO":
            self.lbl_status.config(text="● DEMO FEED", fg="#f39c12")
        else:
            self.lbl_status.config(text="● OFFLINE", fg="#e74c3c")
        self.lbl_rate.config(text=f"{s.packets_per_sec:.0f} pkt/s" if s.packets_per_sec else "")

        self.weather.redraw()
        self.dial.redraw()
        self.tyres.redraw()
        self.wind.redraw()
        self.plist.redraw()
        self.riv_canvas.update_idletasks()
        self.rival.redraw()
        self.map.redraw()

        # доп. поля
        lap = f"{s.current_lap}/{s.total_laps}" if s.total_laps else "--"
        self.extra_labels["lap"].config(text=lap)
        self.extra_labels["cur"].config(text=self.fmt_ms(int(s.lap_time_s * 1000)))
        self.extra_labels["best"].config(text=self.fmt_ms(s.best_lap_ms))
        self.extra_labels["fuel"].config(text=f"{s.fuel:.1f} kg")
        gear = "R" if s.gear < 0 else ("N" if s.gear == 0 else str(s.gear))
        self.extra_labels["gear"].config(text=gear)
        pos_txt = f"P{s.pos}/{s.num_cars}" if s.pos else "--"
        self.extra_labels["delta"].config(text=pos_txt)
        self.extra_labels["drs"].config(text="ON" if s.drs else "OFF")
        gi = min(s.local_idx, len(s.gas) - 1) if s.gas else -1
        bi = min(s.local_idx, len(s.brake) - 1) if s.brake else -1
        gb = ""
        if gi >= 0 and bi >= 0:
            gb = f"{s.gas[gi]*100:.0f}% / {s.brake[bi]*100:.0f}%"
        self.extra_labels["gb"].config(text=gb or "--")

        self.after(33, self._tick)

    # ---------- управление потоком ----------
    def _start_feed(self):
        if self.demo:
            from demo_feed import DemoGenerator
            self.demo_gen = DemoGenerator(port=self.port, n_cars=12)
            self.demo_gen.start()
            self.store.status = "DEMO"
            self.btn_demo.config(text="⏹ Стоп демо")
        else:
            self.store.status = "DISCONNECTED"
            self.btn_demo.config(text="▶ Демо-режим")
        self.reader = ACCUDPReader(self.store, host="0.0.0.0", port=self.port)
        self.reader.start()

    def toggle_demo(self):
        if self.demo:
            self.demo = False
            if self.demo_gen:
                self.demo_gen.stop()
                self.demo_gen = None
            self.store.status = "DISCONNECTED"
            self.reader = ACCUDPReader(self.store, host="0.0.0.0", port=self.port)
            self.reader.start()
            self.btn_demo.config(text="▶ Демо-режим")
        else:
            if self.reader:
                self.reader.stop()
            self.demo = True
            self._start_feed()

    def reconnect(self):
        if self.reader:
            self.reader.stop()
        self.reader = ACCUDPReader(self.store, host="0.0.0.0", port=self.port)
        self.reader.start()

    def toggle_fs(self):
        fs = not bool(self.attributes("-fullscreen")[1]) if self.attributes("-fullscreen") else True
        self.attributes("-fullscreen", fs)

    def _on_close(self):
        try:
            if self.reader:
                self.reader.stop()
            if self.demo_gen:
                self.demo_gen.stop()
        finally:
            self.destroy()


def parse_args():
    ap = argparse.ArgumentParser(description=APP_TITLE)
    ap.add_argument("--demo", action="store_true", help="запустить с внутренним симулятором ACC")
    ap.add_argument("--port", type=int, default=9000, help="UDP порт телеметрии (по умолчанию 9000)")
    ap.add_argument("--fullscreen", action="store_true", help="полноэкранный режим")
    return ap.parse_args()


def main():
    args = parse_args()
    app = Dashboard(port=args.port, demo=args.demo, fullscreen=args.fullscreen)
    app.mainloop()


if __name__ == "__main__":
    main()
