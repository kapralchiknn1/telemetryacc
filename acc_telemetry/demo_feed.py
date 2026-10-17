"""Deterministic in-process demo. Never opens sockets or impersonates an ACC protocol."""
import math
import random
import threading
import time

try:
    from .model import Car, PassageTiming
    from .track_map import REFERENCE_TRACK
    from .acc_udp import CAR_MODELS
except ImportError:
    from model import Car, PassageTiming
    from track_map import REFERENCE_TRACK
    from acc_udp import CAR_MODELS


class DemoGenerator(threading.Thread):
    def __init__(self, store, n_cars=12, seed=42):
        super().__init__(daemon=True)
        if not 1 <= n_cars <= 60:
            raise ValueError('n_cars must be 1..60')
        self.store = store
        self.n = n_cars
        self.random = random.Random(seed)
        self.stop_event = threading.Event()
        self.progress = [1.0 + (n_cars - i) * 0.015 for i in range(n_cars)]
        self.elapsed = 0.0
        self.track = REFERENCE_TRACK
        self.lengths = [math.dist(a, self.track[(i + 1) % len(self.track)])
                        for i, a in enumerate(self.track)]
        self.total_len = sum(self.lengths)
        self.timing = PassageTiming()
        self.lap_start = [0.0] * n_cars
        self.best = [0] * n_cars
        self.last = [0] * n_cars
        self.initial_laps = [int(v) for v in self.progress]

    def position(self, fraction):
        remaining = (fraction % 1) * self.total_len
        for i, length in enumerate(self.lengths):
            if remaining <= length and length > 0:
                a, b = self.track[i], self.track[(i + 1) % len(self.track)]
                t = remaining / length
                return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t,
                        math.atan2(b[1] - a[1], b[0] - a[0]))
            remaining -= length
        return (*self.track[0], 0.0)

    def step(self, dt):
        self.elapsed += dt
        now = time.monotonic()
        with self.store.lock:
            s = self.store.state
            s.demo, s.player_id, s.focus_id = True, 7, 7
            s.track, s.track_length, s.session_type = 'Demo circuit', self.total_len, 10
            s.session_remaining_ms = max(0, (1800 - self.elapsed) * 1000)
            for i in range(self.n):
                # Non-contiguous car IDs are deliberate: ID != list offset.
                cid = 7 + i * 3
                car = s.cars.setdefault(cid, Car(cid))
                speed = 170 + 30 * math.sin(self.progress[i] * 8 + i * 0.3)
                before = int(self.progress[i])
                self.progress[i] += speed / 3.6 * dt / self.total_len
                if int(self.progress[i]) > before:
                    # First crossing starts a full lap; don't count the initial partial lap.
                    if before > self.initial_laps[i]:
                        self.last[i] = int((self.elapsed - self.lap_start[i]) * 1000)
                        self.best[i] = min(self.best[i] or self.last[i], self.last[i])
                    self.lap_start[i] = self.elapsed
                car.name, car.number = f'Demo Driver {i + 1}', 10 + i
                car.cup = ['Pro', 'Silver', 'Pro-Am', 'Am'][i % 4]
                car.model = CAR_MODELS[[30, 32, 34, 35][i % 4]]
                car.x, car.y, car.yaw = self.position(self.progress[i])
                car.speed, car.gear = speed, min(6, max(1, int(speed / 40) + 1))
                car.spline, car.laps = self.progress[i] % 1, int(self.progress[i])
                car.located, car.updated = True, now
                car.lap_ms = int((self.elapsed - self.lap_start[i]) * 1000)
                car.best_ms, car.last_ms = self.best[i], self.last[i]
                self.timing.observe(car, self.elapsed)
            order = sorted(range(self.n), key=lambda i: self.progress[i], reverse=True)
            for pos, idx in enumerate(order, 1):
                s.cars[7 + idx * 3].position = pos
            self.timing.apply(s)
            me = s.cars[7]
            s.speed, s.gear, s.rpm = me.speed, me.gear, int(4400 + me.speed * 12)
            s.fuel = max(0, 80 - self.elapsed * 0.025)
            s.gas, s.brake = 0.7 + 0.3 * math.sin(self.elapsed), max(0, 0.2 * math.sin(self.elapsed * 2))
            s.tyre_core = [85 + 4 * math.sin(self.elapsed / 8 + i) for i in range(4)]
            s.tyre_pressure = [26.5 + 0.2 * math.sin(self.elapsed / 10 + i) for i in range(4)]
            s.air, s.road, s.wetness = 24.0, 32.0, 0.0
            s.wind_speed, s.wind_direction = 3 + math.sin(self.elapsed / 8), self.elapsed % 360
            s.position, s.current_lap, s.total_laps = me.position, me.laps + 1, 25
            s.best_ms, s.lap_ms = me.best_ms, me.lap_ms
            s.shared_seen = s.broadcast_seen = now

    def run(self):
        last = time.monotonic()
        while not self.stop_event.is_set():
            now = time.monotonic()
            self.step(min(0.1, max(0, now - last)))
            last = now
            self.stop_event.wait(1 / 30)

    def stop(self):
        self.stop_event.set()
