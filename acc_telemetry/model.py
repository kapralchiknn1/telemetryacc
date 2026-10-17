"""Thread-safe telemetry model. Coordinates: horizontal x/y in metres; pressure: psi."""
from dataclasses import dataclass, field
import copy
import threading
import time


@dataclass
class Car:
    car_id: int
    name: str = ""
    model: str = ""
    cup: str = ""
    number: int = 0
    x: float = 0.0
    y: float = 0.0
    yaw: float = 0.0
    speed: float = 0.0
    gear: int = 0
    position: int = 0
    laps: int = 0
    spline: float = 0.0
    in_pit: bool = False
    located: bool = False
    best_ms: int = 0
    last_ms: int = 0
    lap_ms: int = 0
    driver_index: int = 0
    drivers: list = field(default_factory=list)
    updated: float = 0.0
    gap: str = "--"
    interval: str = "--"


@dataclass
class State:
    cars: dict = field(default_factory=dict)
    player_id: int = -1
    focus_id: int = -1
    track: str = "--"
    track_length: float = 0.0
    session_type: int = -1
    session_remaining_ms: float | None = None
    speed: float | None = None
    rpm: int | None = None
    gear: int | None = None
    fuel: float | None = None
    gas: float | None = None
    brake: float | None = None
    tyre_core: list = field(default_factory=lambda: [None] * 4)
    tyre_pressure: list = field(default_factory=lambda: [None] * 4)
    air: float | None = None
    road: float | None = None
    wind_speed: float | None = None
    wind_direction: float | None = None
    wetness: float | None = None
    best_ms: int = 0
    lap_ms: int = 0
    current_lap: int = 0
    total_laps: int = 0
    position: int = 0
    demo: bool = False
    broadcast_seen: float = 0.0
    shared_seen: float = 0.0
    broadcast_error: str = ""
    shared_error: str = ""
    packets: int = 0

    @property
    def selected_id(self):
        return self.player_id if self.player_id >= 0 else self.focus_id

    def ordered_cars(self):
        return sorted(self.cars.values(), key=lambda c: (c.position <= 0, c.position, c.car_id))


class TelemetryStore:
    def __init__(self):
        self.lock = threading.RLock()
        self.state = State()

    def snapshot(self):
        with self.lock:
            s = copy.deepcopy(self.state)
        now = time.monotonic()
        # No stale physical telemetry when the game/memory feed goes away.
        if not s.demo and now - s.shared_seen > 3:
            for name in ('speed', 'rpm', 'gear', 'fuel', 'gas', 'brake',
                         'wind_speed', 'wind_direction'):
                setattr(s, name, None)
            s.tyre_core = [None] * 4
            s.tyre_pressure = [None] * 4
            s.player_id = -1
            s.lap_ms = s.best_ms = s.position = s.current_lap = s.total_laps = 0
            if now - s.broadcast_seen > 3:
                s.air = s.road = s.wetness = None
                s.session_remaining_ms = None
        if not s.demo:
            s.cars = {k: v for k, v in s.cars.items() if now - v.updated <= 5}
        return s

    def reset(self, demo=False):
        with self.lock:
            self.state = State(demo=demo)


def fmt_ms(ms):
    if ms is None or ms <= 0 or ms >= 2_147_483_647:
        return '--:--.---'
    ms = int(ms)
    return f'{ms // 60000}:{ms // 1000 % 60:02d}.{ms % 1000:03d}'


class PassageTiming:
    """Estimate race gaps from observed crossings of 200 spline gates, not metres/speed."""
    def __init__(self):
        self.history = {}
        self.previous = {}

    def observe(self, car, now):
        progress = car.laps * 200 + max(0.0, min(car.spline, 0.999999)) * 200
        before = self.previous.get(car.car_id)
        times = self.history.setdefault(car.car_id, {})
        if before and 0 < progress - before[0] <= 30:
            old, stamp = before
            for gate in range(int(old) + 1, int(progress) + 1):
                times[gate] = stamp + (now - stamp) * (gate - old) / (progress - old)
        elif before and progress < before[0] - 1:
            times.clear()  # teleport, session reset or replay seek
        self.previous[car.car_id] = (progress, now)
        for gate in list(times):
            if gate < int(progress) - 600:
                del times[gate]

    def gap(self, car, reference):
        if car.car_id == reference.car_id:
            return 'LEADER'
        mine = self.history.get(car.car_id, {})
        theirs = self.history.get(reference.car_id, {})
        common = mine.keys() & theirs.keys()
        if not common:
            return '--'
        gate = max(common)
        # Old crossings cannot describe the current gap after stops/teleports.
        if int(car.laps * 200 + car.spline * 200) - gate > 2:
            return '--'
        if self.previous.get(car.car_id, (0, 0))[1] - mine[gate] > 5:
            return '--'
        delta = mine[gate] - theirs[gate]
        return f'≈+{delta:.1f}s' if delta >= 0 else '--'

    def apply(self, state):
        ordered = state.ordered_cars()
        if not ordered:
            return
        leader = ordered[0]
        for i, car in enumerate(ordered):
            if car.position <= 0:
                car.gap = car.interval = '--'
            elif state.session_type == 10:  # race, not qualifying order on track
                car.gap = self.gap(car, leader)
                car.interval = self.gap(car, ordered[i - 1]) if i else '--'
            else:
                car.gap = ('LEADER' if i == 0 else
                           f'+{(car.best_ms - leader.best_ms) / 1000:.3f}s'
                           if car.best_ms > 0 and leader.best_ms > 0 and car.best_ms >= leader.best_ms
                           else '--')
                previous = ordered[i - 1] if i else None
                car.interval = (f'+{(car.best_ms - previous.best_ms) / 1000:.3f}s'
                                if previous and car.best_ms > 0 and previous.best_ms > 0
                                and car.best_ms >= previous.best_ms else '--')
