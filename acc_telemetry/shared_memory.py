"""Read-only Windows ACC shared memory. Never creates a missing named mapping.

Layouts follow the Kunos SDK, #pragma pack(4), UTF-16LE (not platform wchar_t).
Only stable prefixes used by this dashboard are mapped.
"""
import ctypes as C
import math
import os
import threading
import time

try:
    from .model import Car
except ImportError:
    from model import Car

I, F, W = C.c_int32, C.c_float, C.c_uint16


class Physics(C.LittleEndianStructure):
    _pack_ = 4
    _fields_ = [
        ('packetId', I), ('gas', F), ('brake', F), ('fuel', F), ('gear', I),
        ('rpms', I), ('steerAngle', F), ('speedKmh', F), ('velocity', F * 3),
        ('accG', F * 3), ('wheelSlip', F * 4), ('wheelLoad', F * 4),
        ('wheelsPressure', F * 4), ('wheelAngularSpeed', F * 4),
        ('tyreWear', F * 4), ('tyreDirtyLevel', F * 4), ('tyreCoreTemperature', F * 4),
        ('camberRAD', F * 4), ('suspensionTravel', F * 4), ('drs', F), ('tc', F),
        ('heading', F), ('pitch', F), ('roll', F), ('cgHeight', F),
        ('carDamage', F * 5), ('numberOfTyresOut', I), ('pitLimiterOn', I),
        ('abs', F), ('kersCharge', F), ('kersInput', F), ('autoShifterOn', I),
        ('rideHeight', F * 2), ('turboBoost', F), ('ballast', F), ('airDensity', F),
        ('airTemp', F), ('roadTemp', F),
    ]


class Graphics(C.LittleEndianStructure):
    _pack_ = 4
    _fields_ = [
        ('packetId', I), ('status', I), ('session', I),
        ('currentTime', W * 15), ('lastTime', W * 15), ('bestTime', W * 15), ('split', W * 15),
        ('completedLaps', I), ('position', I), ('iCurrentTime', I), ('iLastTime', I),
        ('iBestTime', I), ('sessionTimeLeft', F), ('distanceTraveled', F),
        ('isInPit', I), ('currentSectorIndex', I), ('lastSectorTime', I), ('numberOfLaps', I),
        ('tyreCompound', W * 33), ('replayTimeMultiplier', F), ('normalizedCarPosition', F),
        ('activeCars', I), ('carCoordinates', (F * 3) * 60), ('carID', I * 60),
        ('playerCarID', I), ('penaltyTime', F), ('flag', I), ('penalty', I),
        ('idealLineOn', I), ('isInPitLane', I), ('surfaceGrip', F), ('mandatoryPitDone', I),
        ('windSpeed', F), ('windDirection', F),
    ]


class Static(C.LittleEndianStructure):
    _pack_ = 4
    _fields_ = [('smVersion', W * 15), ('acVersion', W * 15),
                ('numberOfSessions', I), ('numCars', I), ('carModel', W * 33),
                ('track', W * 33), ('playerName', W * 33),
                ('playerSurname', W * 33), ('playerNick', W * 33)]


def text(value):
    return bytes(value).decode('utf-16-le', errors='replace').split('\0', 1)[0]


def finite(value):
    return float(value) if math.isfinite(value) else None


class Mapping:
    def __init__(self, name, structure):
        if os.name != 'nt':
            raise OSError('ACC shared memory доступна только в Windows')
        from ctypes import wintypes
        self.kernel = C.WinDLL('kernel32', use_last_error=True)
        self.kernel.OpenFileMappingW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
        self.kernel.OpenFileMappingW.restype = wintypes.HANDLE
        self.kernel.MapViewOfFile.argtypes = [wintypes.HANDLE, wintypes.DWORD,
                                             wintypes.DWORD, wintypes.DWORD, C.c_size_t]
        self.kernel.MapViewOfFile.restype = C.c_void_p
        self.kernel.UnmapViewOfFile.argtypes = [C.c_void_p]
        self.kernel.UnmapViewOfFile.restype = wintypes.BOOL
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel.CloseHandle.restype = wintypes.BOOL
        self.structure = structure
        self.size = C.sizeof(structure)
        self.handle = self.kernel.OpenFileMappingW(4, False, name)  # FILE_MAP_READ
        if not self.handle:
            raise OSError(C.get_last_error(), 'Ожидание запущенной ACC')
        self.pointer = self.kernel.MapViewOfFile(self.handle, 4, 0, 0, self.size)
        if not self.pointer:
            self.kernel.CloseHandle(self.handle)
            self.handle = None
            raise OSError(C.get_last_error(), 'Не удалось прочитать память ACC')

    def read(self):
        for _ in range(3):
            first = C.string_at(self.pointer, self.size)
            second = C.string_at(self.pointer, self.size)
            if first == second:
                return self.structure.from_buffer_copy(first)
        raise OSError('Телеметрия обновляется, повтор чтения')

    def close(self):
        if self.pointer:
            self.kernel.UnmapViewOfFile(self.pointer)
            self.pointer = None
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


class SharedMemoryReader(threading.Thread):
    def __init__(self, store):
        super().__init__(daemon=True)
        self.store = store
        self.stop_event = threading.Event()

    def stop(self):
        self.stop_event.set()

    def apply(self, physics, graphics, static):
        p, g = physics, graphics
        if g.status not in (1, 2, 3):
            return False
        now = time.monotonic()
        if not (0 <= g.activeCars <= 60):
            return False
        with self.store.lock:
            s = self.store.state
            s.player_id = g.playerCarID
            s.speed, s.rpm, s.gear = finite(p.speedKmh), max(0, p.rpms), p.gear - 1
            s.fuel, s.gas, s.brake = finite(p.fuel), finite(p.gas), finite(p.brake)
            s.tyre_pressure = [finite(v) for v in p.wheelsPressure]
            s.tyre_core = [finite(v) for v in p.tyreCoreTemperature]
            s.air, s.road = finite(p.airTemp), finite(p.roadTemp)
            # Actual ACC windSpeed is km/h. Keep the direction raw: SDK docs and
            # observed values disagree; do not pretend it is a calibrated compass.
            s.wind_speed = finite(g.windSpeed / 3.6)
            s.wind_direction = finite(g.windDirection)
            s.position, s.current_lap = g.position, g.completedLaps + 1
            s.total_laps = max(0, g.numberOfLaps)
            s.lap_ms, s.best_ms = max(0, g.iCurrentTime), max(0, g.iBestTime)
            if now - s.broadcast_seen > 3:
                s.track = text(static.track) or '--'
                s.session_remaining_ms = max(0, g.sessionTimeLeft)
            for i in range(g.activeCars):
                cid = g.carID[i]
                xyz = g.carCoordinates[i]
                if not all(math.isfinite(v) for v in xyz):
                    continue
                car = s.cars.setdefault(cid, Car(cid))
                if now - car.updated > 0.5 or cid == g.playerCarID:
                    car.x, car.y = xyz[0], xyz[2]  # vertical axis is y in shared memory
                    car.located, car.updated = True, now
                if cid == g.playerCarID:
                    car.name = (text(static.playerName) + ' ' + text(static.playerSurname)).strip()
                    car.model = text(static.carModel) or car.model
                    car.position, car.laps = g.position, g.completedLaps
                    car.spline, car.yaw = max(0, min(1, g.normalizedCarPosition)), p.heading
                    car.speed, car.gear = s.speed or 0, s.gear
                    car.in_pit = bool(g.isInPitLane or g.isInPit)
                    car.best_ms, car.lap_ms = s.best_ms, s.lap_ms
            s.shared_seen = now
            s.shared_error = ''
        return True

    def run(self):
        if os.name != 'nt':
            with self.store.lock:
                self.store.state.shared_error = 'Shared memory: нужен Windows-ПК с ACC'
            return
        previous = None
        last_change = time.monotonic()
        while not self.stop_event.is_set():
            maps = []
            try:
                for name, structure in [('Local\\acpmf_physics', Physics),
                                        ('Local\\acpmf_graphics', Graphics),
                                        ('Local\\acpmf_static', Static)]:
                    maps.append(Mapping(name, structure))
                while not self.stop_event.is_set():
                    p, g, st = [m.read() for m in maps]
                    signature = (p.packetId, g.packetId)
                    if signature != previous:
                        last_change = time.monotonic()
                        previous = signature
                    if time.monotonic() - last_change > 3 or not self.apply(p, g, st):
                        break  # close stale mappings and wait for a new game process
                    self.stop_event.wait(1 / 30)
            except OSError as exc:
                with self.store.lock:
                    self.store.state.shared_error = str(exc)
            finally:
                for mapping in maps:
                    mapping.close()
            self.stop_event.wait(1)
