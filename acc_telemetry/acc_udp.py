"""ACC Broadcasting SDK protocol v4 client. Read-only registration; no camera commands."""
import math
import socket
import struct
import threading
import time

try:
    from .model import Car, PassageTiming
except ImportError:
    from model import Car, PassageTiming

# SDK model IDs; unknown/new models are explicitly displayed by ID.
CAR_MODELS = {
    0: 'Porsche 991 GT3 R', 1: 'Mercedes-AMG GT3', 2: 'Ferrari 488 GT3',
    3: 'Audi R8 LMS', 4: 'Lamborghini Huracán GT3', 5: 'McLaren 650S GT3',
    6: 'Nissan GT-R Nismo GT3 2018', 7: 'BMW M6 GT3', 8: 'Bentley Continental GT3 2018',
    9: 'Porsche 991II GT3 Cup', 10: 'Nissan GT-R Nismo GT3 2017',
    11: 'Bentley Continental GT3 2016', 12: 'Aston Martin V12 Vantage GT3',
    13: 'Lamborghini Gallardo R-EX', 14: 'Jaguar G3', 15: 'Lexus RC F GT3',
    16: 'Lamborghini Huracán Evo ST', 17: 'Honda NSX GT3',
    18: 'Lamborghini Huracán GT3 Evo', 19: 'Audi R8 LMS Evo',
    20: 'AMR V8 Vantage GT3', 21: 'Honda NSX GT3 Evo', 22: 'McLaren 720S GT3',
    23: 'Porsche 991II GT3 R', 24: 'Ferrari 488 GT3 Evo', 25: 'Mercedes-AMG GT3 Evo',
    26: 'Ferrari 488 Challenge Evo', 27: 'BMW M2 CS Racing', 28: 'Porsche 992 GT3 Cup',
    29: 'Lamborghini Huracán Super Trofeo Evo2', 30: 'BMW M4 GT3',
    31: 'Audi R8 LMS GT3 Evo II', 32: 'Ferrari 296 GT3',
    33: 'Lamborghini Huracán GT3 Evo2', 34: 'Porsche 992 GT3 R',
    35: 'McLaren 720S GT3 Evo', 36: 'Ford Mustang GT3',
    50: 'Alpine A110 GT4', 51: 'AMR V8 Vantage GT4', 52: 'Audi R8 LMS GT4',
    53: 'BMW M4 GT4', 55: 'Chevrolet Camaro GT4', 56: 'Ginetta G55 GT4',
    57: 'KTM X-Bow GT4', 58: 'Maserati MC GT4', 59: 'McLaren 570S GT4',
    60: 'Mercedes-AMG GT4', 61: 'Porsche 718 Cayman GT4',
    80: 'Audi R8 LMS GT2', 82: 'KTM X-Bow GT2', 83: 'Maserati MC20 GT2',
    84: 'Mercedes-AMG GT2', 85: 'Porsche 911 GT2 RS CS Evo',
    86: 'Porsche 935',
}
CUPS = {0: 'Pro', 1: 'Pro-Am', 2: 'Am', 3: 'Silver', 4: 'National'}


class PacketError(ValueError):
    pass


class Reader:
    def __init__(self, data):
        self.data = data
        self.offset = 0

    def read(self, fmt):
        size = struct.calcsize('<' + fmt)
        if self.offset + size > len(self.data):
            raise PacketError('truncated packet')
        result = struct.unpack_from('<' + fmt, self.data, self.offset)
        self.offset += size
        if any(isinstance(x, float) and not math.isfinite(x) for x in result):
            raise PacketError('non-finite number')
        return result[0] if len(result) == 1 else result

    def string(self):
        size = self.read('H')
        if self.offset + size > len(self.data):
            raise PacketError('truncated string')
        value = self.data[self.offset:self.offset + size].decode('utf-8', errors='replace')
        self.offset += size
        return value

    def lap(self):
        result = self.read('i')
        self.read('HH')
        splits = self.read('B')
        if splits > 16:
            raise PacketError('too many lap splits')
        for _ in range(splits):
            self.read('i')
        self.read('BBBB')
        return result if 0 < result < 2_147_483_647 else 0


def encode_string(text):
    data = text.encode('utf-8')
    if len(data) > 65535:
        raise ValueError('ACC string too long')
    return struct.pack('<H', len(data)) + data


def registration(password, interval=100):
    return (bytes((1, 4)) + encode_string('ACC Telemetry Dashboard') + encode_string(password)
            + struct.pack('<i', interval) + encode_string(''))


class ACCUDPReader(threading.Thread):
    def __init__(self, store, host='127.0.0.1', port=9000, password='', interval=100):
        super().__init__(daemon=True)
        self.store = store
        self.address = (host, port)
        self.password = password
        self.interval = interval
        self.stop_event = threading.Event()
        self.sock = None
        self.connection_id = None
        self.timing = PassageTiming()
        self.context = None
        self.last_entry_request = 0.0
        self.last_timing_update = 0.0

    def stop(self):
        self.stop_event.set()
        # recv is bounded by a 0.5 s timeout; run() owns socket cleanup.

    def _send(self, kind):
        if self.sock is not None and self.connection_id is not None:
            self.sock.send(bytes((kind,)) + struct.pack('<i', self.connection_id))

    def run(self):
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.connect(self.address)  # ephemeral LOCAL port; 9000 belongs to ACC
            self.sock.settimeout(0.5)
            last_register = -10.0
            last_received = 0.0
            while not self.stop_event.is_set():
                now = time.monotonic()
                if now - last_received > 5 and now - last_register > 5:
                    self.sock.send(registration(self.password, self.interval))
                    last_register = now
                    self.connection_id = None
                try:
                    data = self.sock.recv(65535)
                except (socket.timeout, ConnectionResetError, ConnectionRefusedError):
                    continue
                try:
                    if self.dispatch(data):
                        last_received = time.monotonic()
                except PacketError:
                    # Ignore bad datagrams without killing the receiver or logging passwords.
                    continue
        except OSError as exc:
            with self.store.lock:
                self.store.state.broadcast_error = f'UDP: {exc}'
        finally:
            if self.sock:
                try:
                    self._send(9)
                except OSError:
                    pass
                self.sock.close()
                self.sock = None

    def dispatch(self, data):
        r = Reader(data)
        kind = r.read('B')
        now = time.monotonic()
        # Fully parse into locals BEFORE mutating the store.
        if kind == 1:
            cid, success, _readonly = r.read('iBB')
            error = r.string()
            self.connection_id = cid if success else None
            with self.store.lock:
                self.store.state.broadcast_error = '' if success else f'ACC отклонил подключение: {error}'
            if success:
                self._send(10)
                self._send(11)
            return bool(success)
        if kind == 2:
            event, session, session_type, phase, elapsed, end, focused = r.read('HHBBffi')
            r.string(); r.string(); r.string()
            if r.read('B'):
                r.read('ff')
            r.read('f')  # time of day
            air, road, clouds, rain, wet = r.read('BBBBB')
            r.lap()
            context = (event, session, session_type)
            with self.store.lock:
                s = self.store.state
                if self.context is not None and self.context != context:
                    s.cars.clear()
                    self.timing = PassageTiming()
                    self._send(10)
                self.context = context
                s.focus_id = focused
                s.session_type = session_type
                s.session_remaining_ms = max(0, end - elapsed)
                s.air, s.road, s.wetness = float(air), float(road), min(1.0, wet / 10)
        elif kind == 3:
            cid, driver, count, gear = r.read('HHBb')
            x, y, yaw, location, speed, pos, cup_pos, track_pos, spline, laps, delta = r.read('fffBHHHHfHi')
            best, last, current = r.lap(), r.lap(), r.lap()
            with self.store.lock:
                s = self.store.state
                car = s.cars.setdefault(cid, Car(cid))
                car.driver_index = driver
                if driver < len(car.drivers):
                    car.name = car.drivers[driver]
                car.x, car.y, car.yaw = x, y, yaw
                car.speed, car.gear, car.position = speed, gear - 1, pos
                car.laps, car.spline = laps, max(0.0, min(1.0, spline))
                car.best_ms, car.last_ms, car.lap_ms = best, last, current
                car.in_pit = location in (2, 3, 4)
                car.located, car.updated = True, now
                self.timing.observe(car, now)
                if now - self.last_timing_update >= 0.2:
                    self.timing.apply(s)
                    self.last_timing_update = now
                if not car.model and now - self.last_entry_request > 5:
                    self._send(10)
                    self.last_entry_request = now
        elif kind == 4:
            r.read('i')
            n = r.read('H')
            if n > 1024:
                raise PacketError('too many cars')
            ids = [r.read('H') for _ in range(n)]
            with self.store.lock:
                self.store.state.cars = {cid: self.store.state.cars.get(cid, Car(cid)) for cid in ids}
        elif kind == 5:
            r.read('i')
            name = r.string()
            track_id, metres = r.read('ii')
            for _ in range(r.read('B')):
                r.string()
                for _ in range(r.read('B')):
                    r.string()
            for _ in range(r.read('B')):
                r.string()
            with self.store.lock:
                s = self.store.state
                if s.track not in ('--', name):
                    s.cars.clear()
                    self.timing = PassageTiming()
                s.track, s.track_length = name, max(0, metres)
        elif kind == 6:
            cid, model = r.read('HB')
            team = r.string()
            number, cup, driver, nationality, n = r.read('iBBHB')
            drivers = []
            for _ in range(n):
                first, last, short = r.string(), r.string(), r.string()
                r.read('BH')
                drivers.append(f'{first} {last}'.strip() or short)
            with self.store.lock:
                car = self.store.state.cars.setdefault(cid, Car(cid))
                car.model = CAR_MODELS.get(model, f'Модель ID {model}')
                car.cup = CUPS.get(cup, f'Cup {cup}')
                car.number, car.drivers = number, drivers
                car.name = drivers[driver] if driver < len(drivers) else team
        elif kind == 7:
            r.read('B'); r.string(); r.read('ii')
        else:
            return False
        with self.store.lock:
            s = self.store.state
            s.broadcast_seen = now
            s.broadcast_error = ''
            s.packets += 1
        return True
