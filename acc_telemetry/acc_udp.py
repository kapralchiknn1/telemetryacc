# -*- coding: utf-8 -*-
"""
Чтение и разбор телеметрии Assetto Corsa Competizione по UDP.

ACC отдаёт UDP-пакеты с magic 0x4571234F. Разбираются пакеты:
  1 BYTES     - базовая телеметрия (скорость, обороты, передача, топливо, шины)
  2 QUITTLY   - квантованная телеметрия (позиции машин на трассе, газ/тормоз/руль)
  3 ROUNDS    - круги / позиция / отставание
  4 LABELS    - имена машин и классов
  5 HOTLAP    - лучшее время круга
  6 CARSETUP  - настройки машины
  7 TESTCASE  - тестовый пакет
  8 FUEL      - топливо / дистанция
  9 RAIN      - погода: ветер, температура асфальта/воздуха, влажность
"""

import socket
import struct
import threading
import time

ACC_MAGIC = 0x4571234F

FLAG_CAUCTION = 0x01
FLAG_WET = 0x02
FLAG_FOG = 0x04
FLAG_STORM = 0x08
FLAG_LIGHTNING = 0x10
FLAG_CLEAR = 0x20
FLAG_PARTLY_CLOUDY = 0x40
FLAG_MOSTLY_CLOUDY = 0x80
FLAG_OVERCAST = 0x100
FLAG_RAIN_LIGHT = 0x200
FLAG_RAIN_MEDIUM = 0x400
FLAG_RAIN_HEAVY = 0x800
FLAG_RAIN_STORM = 0x1000


class TelemetryStore:
    """Хранилище последнего состояния телеметрии (потокобезопасно)."""

    def __init__(self):
        self._lock = threading.Lock()
        self.status = "DISCONNECTED"      # CONNECTED / DISCONNECTED / DEMO
        self.last_packet_time = 0.0
        self.packets_per_sec = 0.0
        self.local_idx = 0
        self.num_cars = 0
        self.track_name = "-"
        self.graphics_id = -1
        self.wetness = 0.0
        self.clouds = 0
        # basic
        self.speed_kmh = 0.0
        self.rpm = 0
        self.gear = 0
        self.driving = False
        self.boost = 0.0
        self.fuel = 0.0
        self.steam = 0.0
        self.drs = 0
        self.n_gear = 6
        # weather
        self.weather_label = "-"
        self.wind_speed_ms = 0.0
        self.wind_dir_deg = 0.0
        self.wind_dir_label = "N"
        self.pad_temp = 0.0
        self.air_temp = 0.0
        # setup
        self.front_splitter = 0
        self.rear_wing = 0
        self.cargo_load = 0
        self.flow_restrictor = 0
        # hot lap
        self.best_lap_ms = 0
        self.lap_ms = 0
        # rounds
        self.pos = 0
        self.current_lap = 0
        self.total_laps = 0
        self.lap_time_s = 0.0
        self.dist_m = 0.0
        self.completed = False
        # quantized
        self.car_coordinates = []   # [(x,y,z), ...] мировые координаты машин
        self.car_vel_x = []
        self.car_vel_y = []
        self.gas = []
        self.brake = []
        self.steer = []
        # labels
        self.car_names = []
        self.car_classes = []
        self.car_pitlane = []
        # tyres: FL FR RL RR
        self.tyres_out = [0.0] * 4
        self.tyres_in = [0.0] * 4
        self.tyres_w = [0.0] * 4
        self.tyres_g = [0.0] * 4
        # track map points (заполняется из python api или демо)
        self.map_points = None
        # внутреннее для подсчёта частоты пакетов
        self._pkt_count = 0
        self._rate_window_start = time.time()


class ACCUDPReader(threading.Thread):
    """Фоновый поток, слушающий UDP-порт ACC и разбирающий пакеты в store."""

    def __init__(self, store, host="0.0.0.0", port=9000):
        super().__init__(daemon=True)
        self.store = store
        self.host = host
        self.port = port
        self.running = True

    def run(self):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((self.host, self.port))
            sock.settimeout(1.0)
        except OSError as e:
            print(f"[UDP] Не удалось занять порт {self.port}: {e}")
            return
        while self.running:
            try:
                data, _ = sock.recvfrom(65535)
            except socket.timeout:
                if time.time() - self.store.last_packet_time > 3.0 and \
                        self.store.status not in ("DEMO",):
                    self.store.status = "DISCONNECTED"
                continue
            except OSError:
                break
            self._dispatch(data)
        sock.close()

    def stop(self):
        self.running = False

    # ---------- разбор пакетов ----------
    def _dispatch(self, data):
        s = self.store
        fmt = "<BIBBH"
        size = struct.calcsize(fmt)
        if len(data) < size:
            return
        _, magic, protocol, packet_type, _ = struct.unpack_from(fmt, data)
        if magic != ACC_MAGIC:
            return
        with s._lock:
            s.last_packet_time = time.time()
            s._pkt_count += 1
            now = time.time()
            dt = now - s._rate_window_start
            if dt >= 1.0:
                s.packets_per_sec = s._pkt_count / dt
                s._pkt_count = 0
                s._rate_window_start = now
            if s.status != "DEMO":
                s.status = "CONNECTED"
        try:
            if packet_type == 1:
                self._parse_basic(data, size)
            elif packet_type == 2:
                self._parse_quant(data, size)
            elif packet_type == 3:
                self._parse_rounds(data, size)
            elif packet_type == 4:
                self._parse_labels(data, size)
            elif packet_type == 5:
                self._parse_hotlap(data, size)
            elif packet_type == 6:
                self._parse_setup(data, size)
            elif packet_type == 8:
                self._parse_fuel(data, size)
            elif packet_type == 9:
                self._parse_rain(data, size)
        except Exception as e:
            print(f"[UDP] Ошибка разбора пакета типа {packet_type}: {e}")

    def _parse_basic(self, data, off):
        s = self.store
        # Спецификация ACC (packet type 1 BYTES), little-endian:
        # uint16 carIdx; uint8 status; uint8 info; int16 timestamp; uint8 frame;
        # uint8 engine(bcd); uint8 gear(bcd); float speed(m/s); float rpm;
        # float turboBoost; float exhaustTemp; float fuel; float steam;
        # uint8 drs; uint8 nGears; ... ; далее 16 float шинных данных.
        fmt = "<HBBhBBBBffffffBBBB"   # 18 полей: 7 int + 7 float + 4 int
        size = struct.calcsize(fmt)
        if len(data) < off + size:
            return
        vals = struct.unpack_from(fmt, data, off)
        (cid, status, info, ts, frame, eng_bcd, g_bcd,
         speed, rpm, turbo, exhuast, fuel, steam, _f14, drs, ng, nb, vol) = vals
        s.local_idx = cid
        s.speed_kmh = max(0.0, speed) * 3.6
        s.rpm = int(rpm)
        s.gear = max(0, g_bcd - 1)
        s.fuel = fuel
        s.steam = steam
        s.drs = drs
        s.n_gear = ng if ng else 6
        s.driving = bool(info & 0x01)
        s.boost = turbo
        # шины идут сразу после
        fmt2 = "<" + "f" * 16
        size2 = struct.calcsize(fmt2)
        if len(data) >= off + size + size2:
            t = struct.unpack_from(fmt2, data, off + size)
            s.tyres_w = list(t[0:4])
            s.tyres_g = list(t[4:8])
            s.tyres_out = list(t[8:12])
            s.tyres_in = list(t[12:16])

    def _parse_quant(self, data, off):
        s = self.store
        fmt = "<BBHHHhhhHhh"
        size = struct.calcsize(fmt)
        if len(data) < off + size:
            return
        n, tc, f, q, v, o, la, lb, ti, co, di = struct.unpack_from(fmt, data, off)
        s.num_cars = n
        if tc in TRACK_NAMES:
            s.track_name = TRACK_NAMES[tc]
        s.lap_time_s = ti / 1000.0
        s.completed = bool(co & 0x01)
        s.dist_m = di * 10.0
        base = off + size
        fmt_pos = "<" + "i" * (n * 3)
        psize = struct.calcsize(fmt_pos)
        if len(data) >= base + psize:
            pos = struct.unpack_from(fmt_pos, data, base)
            s.car_coordinates = [(pos[i*3], pos[i*3+1], pos[i*3+2]) for i in range(n)]
            base += psize
        fmt_vx = "<" + "h" * n
        fmt_vy = "<" + "h" * n
        fmt_gb = "<" + "BB" * n
        fmt_st = "<" + "h" * n
        need = (struct.calcsize(fmt_vx) + struct.calcsize(fmt_vy) +
                struct.calcsize(fmt_gb) + struct.calcsize(fmt_st))
        if len(data) >= base + need:
            vx = struct.unpack_from(fmt_vx, data, base); base += struct.calcsize(fmt_vx)
            vy = struct.unpack_from(fmt_vy, data, base); base += struct.calcsize(fmt_vy)
            gb = struct.unpack_from(fmt_gb, data, base); base += struct.calcsize(fmt_gb)
            stv = struct.unpack_from(fmt_st, data, base)
            s.car_vel_x = list(vx)
            s.car_vel_y = list(vy)
            s.gas = [x / 255.0 for x in gb[0::2]]
            s.brake = [x / 255.0 for x in gb[1::2]]
            s.steer = [x / 65535.0 for x in stv]

    def _parse_rounds(self, data, off):
        s = self.store
        fmt = "<BBHBBBBIIf"
        size = struct.calcsize(fmt)
        if len(data) < off + size:
            return
        lidx, n, li, ci, tl, ta, tb, ps, dt = struct.unpack_from(fmt, data, off)
        s.local_idx = lidx
        s.num_cars = n
        s.pos = li
        s.current_lap = ci
        s.total_laps = tl
        s.dist_m = ps

    def _parse_labels(self, data, off):
        s = self.store
        fmt = "<BB"
        size = struct.calcsize(fmt)
        if len(data) < off + size:
            return
        n, tc = struct.unpack_from(fmt, data, off)
        names, classes, pit = [], [], []
        base = off + size
        NAMESZ, CLSZ, PSZ = 48, 4, 1
        stride = NAMESZ + CLSZ + PSZ
        if len(data) < base + n * stride:
            return
        for i in range(n):
            o = base + i * stride
            raw = data[o:o+NAMESZ]
            names.append(raw.split(b"\x00")[0].decode("utf-8", "ignore"))
            c = data[o+NAMESZ:o+NAMESZ+CLSZ]
            classes.append(c.split(b"\x00")[0].decode("utf-8", "ignore"))
            pt = data[o+NAMESZ+CLSZ]
            pit.append(bool(pt))
        s.car_names = names
        s.car_classes = classes
        s.car_pitlane = pit

    def _parse_hotlap(self, data, off):
        s = self.store
        fmt = "<II"
        size = struct.calcsize(fmt)
        if len(data) < off + size:
            return
        bl, cl = struct.unpack_from(fmt, data, off)
        s.best_lap_ms = bl
        s.lap_ms = cl

    def _parse_setup(self, data, off):
        s = self.store
        fmt = "<BBBBI"
        size = struct.calcsize(fmt)
        if len(data) < off + size:
            return
        n, w, sp, rw, cf = struct.unpack_from(fmt, data, off)
        s.n_gear = n
        s.front_splitter = w
        s.rear_wing = sp
        s.cargo_load = rw
        s.flow_restrictor = cf

    def _parse_fuel(self, data, off):
        s = self.store
        fmt = "<ffff"
        size = struct.calcsize(fmt)
        if len(data) < off + size:
            return
        fuel, steam, dist, _ = struct.unpack_from(fmt, data, off)
        s.fuel = fuel
        s.steam = steam

    def _parse_rain(self, data, off):
        s = self.store
        fmt = "<BfBBhh"
        size = struct.calcsize(fmt)
        if len(data) < off + size:
            return
        wd, wdir, wspd, clouds, tp, atp = struct.unpack_from(fmt, data, off)
        s.wetness = wd / 100.0
        s.wind_dir_deg = wdir / 100.0
        s.wind_speed_ms = wspd / 100.0
        s.clouds = clouds
        s.pad_temp = tp / 10.0
        s.air_temp = atp / 10.0
        labels = []
        if s.wetness < 0.5:
            labels.append("Dry")
        elif s.wetness < 0.8:
            labels.append("Damp")
        else:
            labels.append("Wet")
        if clouds & FLAG_CLEAR:
            labels.append("Clear")
        elif clouds & FLAG_PARTLY_CLOUDY:
            labels.append("Partly cloudy")
        elif clouds & FLAG_MOSTLY_CLOUDY:
            labels.append("Mostly cloudy")
        elif clouds & FLAG_OVERCAST:
            labels.append("Overcast")
        if clouds & FLAG_RAIN_LIGHT:
            labels.append("Light rain")
        elif clouds & FLAG_RAIN_MEDIUM:
            labels.append("Rain")
        elif clouds & FLAG_RAIN_HEAVY:
            labels.append("Heavy rain")
        elif clouds & FLAG_RAIN_STORM:
            labels.append("Storm")
        if clouds & FLAG_FOG:
            labels.append("Fog")
        if clouds & FLAG_LIGHTNING:
            labels.append("Lightning")
        s.weather_label = ", ".join(labels) if labels else "Unknown"
        dirs = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
        s.wind_dir_label = dirs[int(((s.wind_dir_deg + 22.5) % 360) // 45)]


TRACK_NAMES = {
    0: "No Track", 1: "Barcelona", 2: "Donington Test", 3: "Zolder", 4: "Misano",
    5: "Monza", 6: "Red Bull Ring", 7: "Silverstone", 8: "Hungaroring", 9: "Nurburgring",
    10: "Algarve", 11: "Magny-Cours", 12: "Bahrain", 13: "Spa-Francorchamps",
    14: "Paul Ricard", 15: "Tokyo Expressway", 16: "Imola", 17: "Brands Hatch",
    18: "Laguna Seca", 19: "Snetterton", 20: "Oulton Park", 21: "Kyalami",
    22: "Brno", 23: "Goodwood", 24: "COTA", 25: "Willow Springs", 26: "Mount Panorama",
    27: "Laguna Seca Short", 28: "Suzuka", 29: "Russell Hill", 30: "Nordschleife",
    31: "Oschersleben", 32: "Silverstone Intl", 33: "Donington GP", 34: "Brno Test",
    35: "Mugello", 36: "Vallelunga", 37: "Indianapolis",
}
