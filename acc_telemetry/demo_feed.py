# -*- coding: utf-8 -*-
"""
Генератор пакетов ACC UDP для демо-режима.

Собирает корректные бинарные пакеты (magic 0x4571234F) и отправляет их
на указанный UDP-порт, чтобы приложение можно было тестировать без запущенной игры.
Машины едут по эталонной трассе (тот же сплайн, что используется в карте).
"""

import math
import struct
import threading
import time
import socket
import random

MAGIC = 0x4571234F


def make_header(ptype, payload_len):
    total = 5 + payload_len
    return struct.pack("<BIBBH", total & 0xFFFF, MAGIC, 1, ptype, 0)


class DemoGenerator(threading.Thread):
    def __init__(self, port=9000, n_cars=12, track_points=None, host="127.0.0.1"):
        super().__init__(daemon=True)
        self.port = port
        self.host = host
        self.n = n_cars
        self.running = True
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # трасса: замкнутый сплайн (тот же, что в assets/track_map.py)
        from track_map import REFERENCE_TRACK
        self.track = REFERENCE_TRACK
        self._resample()
        # стартовые позиции вдоль трассы (нормализованные 0..1)
        self.s_frac = [i * 0.011 for i in range(n_cars)]
        self.speeds = [random.uniform(160, 200) for _ in range(n_cars)]  # km/h
        self.lap = [0] * n_cars
        self.local_idx = 0
        self.names = [f"#{i+1} {n}" for i, n in enumerate(
            ["Rossi", "Vermeulen", "Bortolotti", "Catsburg", "Engel", "Ferrari",
             "Girardot", "Haase", "Iltsov", "Jaminet", "Klingmann", "Lauda Jr",
             "Mapelli", "Nato", "Pera"])]
        self.classes = ["Pro"] * n_cars
        self.t = time.time()
        self.tick = 0

    def _resample(self):
        pts = self.track
        self.cum = [0.0]
        for i in range(len(pts)):
            x1, y1 = pts[i]
            x2, y2 = pts[(i + 1) % len(pts)]
            self.cum.append(self.cum[-1] + math.hypot(x2 - x1, y2 - y1))
        self.total_len = self.cum[-1]

    def pos_at(self, frac):
        d = (frac % 1.0) * self.total_len
        # бинарный поиск сегмента
        lo, hi = 0, len(self.cum) - 1
        while lo < hi:
            mid = (lo + hi) // 2
            if self.cum[mid + 1] < d:
                lo = mid + 1
            else:
                hi = mid
        seg_len = self.cum[lo + 1] - self.cum[lo] or 1e-6
        t = (d - self.cum[lo]) / seg_len
        x1, y1 = self.track[lo]
        x2, y2 = self.track[(lo + 1) % len(self.track)]
        x = x1 + (x2 - x1) * t
        y = y1 + (y2 - y1) * t
        ang = math.atan2(y2 - y1, x2 - x1)
        return x, y, ang

    def run(self):
        dt = 1.0 / 60.0
        while self.running:
            start = time.time()
            self._step(dt)
            self._send_all()
            elapsed = time.time() - start
            time.sleep(max(0.0, dt - elapsed))

    def stop(self):
        self.running = False
        try:
            self.sock.close()
        except Exception:
            pass

    def _step(self, dt):
        self.tick += 1
        for i in range(self.n):
            # скорость слегка гуляет
            target = 170 + 40 * math.sin((self.s_frac[i] * 6) + self.tick * 0.008)
            self.speeds[i] += (target - self.speeds[i]) * 0.05
            v_ms = self.speeds[i] / 3.6
            self.s_frac[i] += v_ms * dt / self.total_len
            if self.s_frac[i] >= 1.0:
                self.s_frac[i] -= 1.0
                self.lap[i] += 1

    def _payload_basic(self):
        i = self.local_idx
        speed_ms = self.speeds[i] / 3.6
        rpm = 4500 + int(speed_ms * 40 + random.uniform(-100, 100))
        gear = max(1, min(6, int(speed_ms / 45) + 1))
        fuel = 80.0 - (self.tick % 7200) * 0.002
        temps_out = [random.uniform(80, 105) for _ in range(4)]
        temps_in = [t - random.uniform(10, 20) for t in temps_out]
        pressures = [random.uniform(1.6, 2.1) for _ in range(4)]
        grip = [random.uniform(0.8, 1.0) for _ in range(4)]
        # заголовок пакета BYTES: 7 целых + 6 float + 4 целых = 17 полей
        head_fmt = "<HBBhBBBBffffffBBBB"
        body = struct.pack(head_fmt,
                           i, 1, 1, int(time.time() * 1000) & 0x7FFF, self.tick & 0xFF,
                           45, gear + 1,
                           speed_ms, float(rpm), 0.0, 400.0, fuel, 0.0,
                           0, 6, 0, 0)
        assert struct.calcsize(head_fmt) == len(body)
        tyres = struct.pack("<" + "f" * 16,
                            *pressures, *grip, *temps_out, *temps_in)
        return body + tyres

    def _payload_quant(self):
        n = self.n
        o, la, lb = [], [], []
        vx, vy = [], []
        gb, st = [], []
        for i in range(n):
            x, y, ang = self.pos_at(self.s_frac[i])
            o.append(int(x * 1000))
            la.append(int(y * 1000))
            lb.append(0)
            v = self.speeds[i] / 3.6
            vx.append(int(v * math.cos(ang) * 100))
            vy.append(int(v * math.sin(ang) * 100))
            gas = int(random.uniform(0.6, 1.0) * 255)
            brk = int(random.uniform(0.0, 0.2) * 255)
            gb.append(gas); gb.append(brk)
            st.append(int(random.uniform(-0.3, 0.3) * 65535))
        ti = int((self.tick % 9000) / 60 * 1000)
        fmt = "<BBHHHhhhHhh"          # 11 полей
        body = struct.pack(fmt, n, 13, self.tick & 0xFFFF, 0, 0,
                           0, 0, 0, ti, 0, int(self.total_len))
        body += struct.pack("<" + "i" * (n * 3), *(o + la + lb))
        body += struct.pack("<" + "h" * n, *vx)
        body += struct.pack("<" + "h" * n, *vy)
        body += struct.pack("<" + "BB" * n, *gb)
        body += struct.pack("<" + "h" * n, *st)
        return body

    def _payload_rounds(self):
        i = self.local_idx
        fmt = "<BBHBBBBBIf"           # 10 полей: localIdx, numCars, lapPos, curLap,
                                     # totalLaps, lapsAhead, lapsBehind, classId, dist, time
        ahead = sum(1 for j in range(self.n)
                    if (self.lap[j], self.s_frac[j]) > (self.lap[i], self.s_frac[i]))
        pos = self.n - ahead
        laptime = (self.tick % 9000) / 60.0
        return struct.pack(fmt, i, self.n, pos, self.lap[i] + 1, 25,
                           ahead, self.n - 1 - ahead, 0, 0, laptime)

    def _payload_labels(self):
        out = struct.pack("<BB", self.n, 13)
        for i in range(self.n):
            name = self.names[i].encode("utf-8")[:47].ljust(48, b"\x00")
            cls = self.classes[i][:3].encode("utf-8").ljust(4, b"\x00")
            out += name + cls + b"\x00"
        return out

    def _payload_hotlap(self):
        best = 90000 + (self.tick // 60) % 5000
        cur = int((self.tick % 9000) / 60 * 1000)
        return struct.pack("<II", best, cur)

    def _payload_setup(self):
        return struct.pack("<BBBBI", 6, 12, 9, 3, 5)

    def _payload_fuel(self):
        fuel = 80.0 - (self.tick % 7200) * 0.002
        return struct.pack("<ffff", fuel, 0.0, self.total_len / 1000.0, 0.0)

    def _payload_rain(self):
        wet = 0
        clouds = 0x20 | 0x40  # clear + partly cloudy
        wind_dir = (self.tick * 0.02) % 360.0
        wind_spd = 3.0 + 2.0 * math.sin(self.tick * 0.01)
        pad = 32.0 + 3.0 * math.sin(self.tick * 0.003)
        air = 24.0
        return struct.pack("<BfBBhh", wet, wind_dir, int(wind_spd * 100),
                           clouds, int(pad * 10), int(air * 10))

    def _payload_test(self):
        return struct.pack("<I", self.tick)

    def _send_all(self):
        addr = (self.host, self.port)
        parts = [(1, self._payload_basic()), (2, self._payload_quant()),
                 (3, self._payload_rounds()), (4, self._payload_labels()),
                 (5, self._payload_hotlap()), (6, self._payload_setup()),
                 (8, self._payload_fuel()), (9, self._payload_rain())]
        for ptype, payload in parts:
            pkt = make_header(ptype, len(payload)) + payload
            try:
                self.sock.sendto(pkt, addr)
            except OSError:
                return
