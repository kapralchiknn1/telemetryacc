import ctypes
import json
import math
import os
from pathlib import Path
import socket
import struct
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from acc_telemetry.acc_udp import ACCUDPReader, Reader, PacketError, registration, encode_string
from acc_telemetry.config import parse_args
from acc_telemetry.demo_feed import DemoGenerator
from acc_telemetry.feeds import FeedController
from acc_telemetry.model import Car, PassageTiming, TelemetryStore, fmt_ms
from acc_telemetry.shared_memory import Physics, Graphics, Static, SharedMemoryReader, Mapping, text
from acc_telemetry.track_map import load_track


def lap(ms=0, cid=7):
    # Independent wire fixture from the SDK field layout, not from production encoder.
    return struct.pack('<iHHBiiiBBBB', ms, cid, 0, 3, 30000, 30000, 30000, 0, 1, 0, 0)


def car_packet(cid=7, pos=2, gear=0, x=10.5):
    return (bytes([3]) + struct.pack('<HHBbfffBHHHHfHi', cid, 0, 1, gear,
            x, -42.25, 1.5, 1, 180, pos, pos, pos, .45, 3, 100)
            + lap(90000, cid) + lap(91000, cid) + lap(12345, cid))


def entry_packet(cid=7, model=32):
    return (bytes([6]) + struct.pack('<HB', cid, model) + encode_string('Team')
            + struct.pack('<iBBHB', 42, 3, 0, 0, 1)
            + encode_string('Иван') + encode_string('Иванов') + encode_string('IVA')
            + struct.pack('<BH', 2, 0))


def session_packet(index=1, replay=False):
    return (bytes([2]) + struct.pack('<HHBBffi', 1, index, 10, 5, 10000., 60000., 7)
            + encode_string('set') + encode_string('cam') + encode_string('hud')
            + bytes([int(replay)]) + (struct.pack('<ff', 10., 20.) if replay else b'')
            + struct.pack('<fBBBBB', 123., 24, 32, 0, 5, 7) + lap(90000))


def write_text(array, content):
    values = struct.unpack('<' + 'H' * (len(content.encode('utf-16-le')) // 2), content.encode('utf-16-le'))
    for i, val in enumerate(values):
        array[i] = val


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.store = TelemetryStore()
        self.reader = ACCUDPReader(self.store)

    def test_registration_wire(self):
        r = Reader(registration('пароль', 100))
        self.assertEqual(r.read('BB'), (1, 4))
        self.assertEqual(r.string(), 'ACC Telemetry Dashboard')
        self.assertEqual(r.string(), 'пароль')
        self.assertEqual(r.read('i'), 100)
        self.assertEqual(r.string(), '')  # never request a command password
        self.assertEqual(r.offset, len(r.data))

    def test_registration_denied(self):
        self.assertFalse(self.reader.dispatch(b'\x01' + struct.pack('<iBB', -1, 0, 1) + encode_string('denied')))
        self.assertIsNone(self.reader.connection_id)
        self.assertIn('denied', self.store.snapshot().broadcast_error)

    def test_real_car_packet_and_noncontiguous_ids(self):
        self.reader.dispatch(car_packet())
        c = self.store.snapshot().cars[7]
        self.assertEqual((c.x, c.y, c.position, c.laps, c.gear), (10.5, -42.25, 2, 3, -1))
        self.assertEqual((c.best_ms, c.last_ms, c.lap_ms), (90000, 91000, 12345))
        self.assertAlmostEqual(c.spline, .45, places=6)
        self.assertEqual(self.store.snapshot().player_id, -1)  # focused is not necessarily player

    def test_neutral_and_forward_gears(self):
        for wire, expected in [(0, -1), (1, 0), (2, 1), (7, 6)]:
            self.reader.dispatch(car_packet(gear=wire))
            self.assertEqual(self.store.snapshot().cars[7].gear, expected)

    def test_entry_list_and_driver_unicode(self):
        self.reader.dispatch(entry_packet())
        self.reader.dispatch(car_packet())
        c = self.store.snapshot().cars[7]
        self.assertEqual(c.name, 'Иван Иванов')
        self.assertEqual(c.model, 'Ferrari 296 GT3')
        self.assertEqual(c.cup, 'Silver')
        self.reader.dispatch(b'\x04' + struct.pack('<iHHH', 99, 2, 7, 101))
        self.assertEqual(set(self.store.state.cars), {7, 101})

    def test_unknown_model_is_not_invented(self):
        self.reader.dispatch(entry_packet(model=255))
        self.assertEqual(self.store.state.cars[7].model, 'Модель ID 255')

    def test_session_and_replay(self):
        self.reader.dispatch(session_packet(replay=True))
        s = self.store.snapshot()
        self.assertEqual(s.focus_id, 7)
        self.assertEqual(s.session_remaining_ms, 50000)
        self.assertAlmostEqual(s.wetness, .7)
        self.reader.dispatch(car_packet())
        self.reader.dispatch(session_packet(index=2))
        self.assertEqual(self.store.snapshot().cars, {})

    def test_track_packet(self):
        p = (b'\x05' + struct.pack('<i', 5) + encode_string('spa') + struct.pack('<iiB', 9, 7004, 1)
             + encode_string('set') + b'\x01' + encode_string('cam') + b'\x01' + encode_string('hud'))
        self.reader.dispatch(p)
        self.assertEqual((self.store.state.track, self.store.state.track_length), ('spa', 7004))

    def test_all_truncated_packets_fail_atomically(self):
        fixtures = [car_packet(), entry_packet(), session_packet(),
                    b'\x04' + struct.pack('<iHHH', 1, 2, 7, 99)]
        for packet in fixtures:
            for length in range(len(packet)):
                store = TelemetryStore()
                reader = ACCUDPReader(store)
                before = store.snapshot()
                with self.assertRaises(PacketError, msg=(packet[0], length)):
                    reader.dispatch(packet[:length])
                self.assertEqual(store.snapshot(), before)

    def test_nonfinite_rejected(self):
        with self.assertRaises(PacketError):
            self.reader.dispatch(car_packet(x=float('nan')))
        self.assertFalse(self.store.state.cars)

    def test_unknown_packet_ignored(self):
        self.assertFalse(self.reader.dispatch(b'\xff\x00'))
        self.assertEqual(self.store.state.packets, 0)


class ModelTests(unittest.TestCase):
    def test_stale_physics_and_positions_hidden(self):
        store = TelemetryStore()
        store.state.speed = 200
        store.state.player_id = 7
        store.state.tyre_pressure = [26] * 4
        store.state.cars[7] = Car(7, updated=time.monotonic() - 10)
        s = store.snapshot()
        self.assertIsNone(s.speed)
        self.assertEqual(s.player_id, -1)
        self.assertEqual(s.tyre_pressure, [None] * 4)
        self.assertFalse(s.cars)

    def test_snapshot_is_independent(self):
        store = TelemetryStore()
        store.state.demo = True
        store.state.cars[7] = Car(7)
        s = store.snapshot()
        s.cars[7].name = 'changed'
        self.assertEqual(store.state.cars[7].name, '')

    def test_gap_from_crossing_time_not_spatial_distance(self):
        timing = PassageTiming()
        a, b = Car(7), Car(99)
        a.spline, b.spline = .10, .10
        timing.observe(a, 10)
        timing.observe(b, 12)
        a.spline = b.spline = .115
        timing.observe(a, 11)
        timing.observe(b, 13)
        self.assertEqual(timing.gap(b, a), '≈+2.0s')
        b.spline = .8
        self.assertEqual(timing.gap(b, a), '--')

    def test_fmt(self):
        for ms, expected in [(0, '--:--.---'), (-1, '--:--.---'), (91234, '1:31.234'),
                             (2147483647, '--:--.---')]:
            self.assertEqual(fmt_ms(ms), expected)


class SharedMemoryTests(unittest.TestCase):
    def test_layout_matches_windows_sdk_offsets(self):
        self.assertEqual(Physics.speedKmh.offset, 28)
        self.assertEqual(Physics.wheelsPressure.offset, 88)
        self.assertEqual(Physics.tyreCoreTemperature.offset, 152)
        self.assertEqual(Physics.airTemp.offset, 288)
        self.assertEqual(Physics.roadTemp.offset, 292)
        self.assertEqual(Graphics.completedLaps.offset, 132)
        self.assertEqual(Graphics.tyreCompound.offset, 176)
        self.assertEqual(Graphics.carCoordinates.offset, 256)
        self.assertEqual(Graphics.playerCarID.offset, 1216)
        self.assertEqual(Graphics.windSpeed.offset, 1248)
        self.assertEqual(Static.track.offset, 134)
        self.assertEqual(ctypes.sizeof(Graphics), 1256)

    def test_apply_binary_fields_and_units(self):
        p, g, st = Physics(), Graphics(), Static()
        p.packetId, g.packetId, g.status = 1, 1, 2
        p.speedKmh, p.fuel, p.gear, p.rpms = 200., 63.2, 0, 7100
        p.wheelsPressure[:] = [26.1, 26.2, 26.3, 26.4]
        p.tyreCoreTemperature[:] = [80, 81, 82, 83]
        g.activeCars, g.playerCarID, g.carID[0] = 1, 101, 101
        g.carCoordinates[0][:] = [10, 999, 30]
        g.windSpeed, g.windDirection = 18, 2.4
        write_text(st.track, 'spa')
        write_text(st.playerName, 'Иван')
        write_text(st.playerSurname, 'Петров')
        write_text(st.carModel, 'bmw_m4_gt3')
        store = TelemetryStore()
        reader = SharedMemoryReader(store)
        self.assertTrue(reader.apply(p, g, st))
        s = store.snapshot()
        self.assertEqual((s.player_id, s.cars[101].x, s.cars[101].y), (101, 10, 30))
        self.assertEqual(s.cars[101].name, 'Иван Петров')
        self.assertEqual(s.gear, -1)
        self.assertAlmostEqual(s.wind_speed, 5)
        self.assertEqual(s.tyre_core, [80, 81, 82, 83])
        self.assertAlmostEqual(s.tyre_pressure[0], 26.1, places=4)

    def test_off_game_does_not_appear_connected(self):
        store = TelemetryStore()
        self.assertFalse(SharedMemoryReader(store).apply(Physics(), Graphics(), Static()))
        self.assertEqual(store.state.shared_seen, 0)

    @unittest.skipIf(os.name == 'nt', 'Windows mapping tested by game acceptance test')
    def test_mapping_not_available_on_linux(self):
        with self.assertRaises(OSError):
            Mapping('Local\\acpmf_physics', Physics)


class DemoAndConfigTests(unittest.TestCase):
    def test_demo_thousands_of_ticks_without_packets_or_overflows(self):
        store = TelemetryStore()
        demo = DemoGenerator(store, n_cars=60)
        with patch('socket.socket', side_effect=AssertionError('demo must not open sockets')):
            for _ in range(2200):
                demo.step(.05)
        s = store.snapshot()
        self.assertEqual(len(s.cars), 60)
        self.assertEqual(sorted(c.position for c in s.cars.values()), list(range(1, 61)))
        self.assertGreater(s.best_ms, 0)
        self.assertGreater(s.fuel, 0)
        self.assertEqual(s.player_id, 7)
        self.assertTrue(all(math.isfinite(c.x) and math.isfinite(c.y) for c in s.cars.values()))

    def test_feed_switching_stops_threads(self):
        store = TelemetryStore()
        feeds = FeedController(store)
        try:
            for _ in range(5):
                feeds.start(True)
                time.sleep(.04)
                old = list(feeds.threads)
                feeds.start(True)
                self.assertTrue(all(not t.is_alive() for t in old))
        finally:
            feeds.stop()
        self.assertFalse(feeds.threads)

    def test_remote_host_does_not_mix_local_memory(self):
        store = TelemetryStore()
        feeds = FeedController(store, host='192.0.2.1')
        with patch.object(ACCUDPReader, 'start'):
            feeds.start(False)
            self.assertEqual(len(feeds.threads), 1)
            self.assertIn('Удалённый', store.state.shared_error)
        # The mocked thread has not been started, so no join is required.
        feeds.threads.clear()

    def test_live_demo_live_lifecycle(self):
        store = TelemetryStore()
        server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        server.bind(('127.0.0.1', 0))
        feeds = FeedController(store, port=server.getsockname()[1])
        try:
            feeds.start(False)
            old = list(feeds.threads)
            feeds.start(True)
            self.assertTrue(all(not t.is_alive() for t in old))
            feeds.start(False)
            self.assertFalse(store.state.demo)
        finally:
            feeds.stop()
            server.close()

    def test_config_and_unicode_password(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'config.json'
            p.write_text(json.dumps({'updListenerPort': 9010, 'connectionPassword': 'пароль'}), encoding='utf-8-sig')
            with patch.dict(os.environ, {}, clear=True):
                args = parse_args(['--config', str(p)])
                self.assertEqual((args.port, args.password), (9010, 'пароль'))
                demo = parse_args(['--demo', '--config', str(p)])
                self.assertEqual((demo.port, demo.password), (9010, 'пароль'))
                self.assertEqual(parse_args(['--config', str(p), '--port', '9020']).port, 9020)
            with patch.dict(os.environ, {'ACC_CONNECTION_PASSWORD': 'override'}):
                self.assertEqual(parse_args(['--config', str(p)]).password, 'override')

    def test_explicit_config_without_home_directory(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'broadcasting.json'
            path.write_text(json.dumps({'updListenerPort': 9011, 'connectionPassword': 'local-test'}), encoding='utf-8')
            with patch('acc_telemetry.config.Path.home', side_effect=RuntimeError('No home')) as home:
                with patch.dict(os.environ, {}, clear=True):
                    args = parse_args(['--config', str(path)])
                    self.assertEqual((args.port, args.password), (9011, 'local-test'))
                home.assert_not_called()

    def test_no_home_uses_cli_and_environment(self):
        with patch('acc_telemetry.config.Path.home', side_effect=RuntimeError('No home')):
            with patch.dict(os.environ, {'ACC_CONNECTION_PASSWORD': 'local-test'}, clear=True):
                args = parse_args(['--port', '9012'])
                self.assertEqual((args.port, args.password), (9012, 'local-test'))

    def test_invalid_config_does_not_leak_secrets(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'config.json'
            p.write_text('{"connectionPassword": "SECRET" invalid}', encoding='utf-8')
            from io import StringIO
            with patch('sys.stderr', new_callable=StringIO) as output:
                with self.assertRaises(SystemExit):
                    parse_args(['--config', str(p)])
                self.assertNotIn('SECRET', output.getvalue())

    def test_track_validation(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'track.json'
            p.write_text('{"points": [[0,0],[10,0],[0,10]]}')
            self.assertEqual(load_track(p), [(0., 0.), (10., 0.), (0., 10.)])
            for bad in ['[]', '[[0,0],[0,0],[0,0]]', '[[true,0],[10,0],[0,10]]',
                        '[[NaN,0],[10,0],[0,10]]', '[[0,0,0],[10,0],[0,10]]']:
                p.write_text(bad)
                with self.assertRaises(ValueError):
                    load_track(p)


class UDPIntegrationTests(unittest.TestCase):
    def test_local_acc_mock_registration_requests_and_disconnect(self):
        server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        server.bind(('127.0.0.1', 0))
        server.settimeout(3)
        store = TelemetryStore()
        client = ACCUDPReader(store, port=server.getsockname()[1], password='test')
        try:
            client.start()
            packet, peer = server.recvfrom(65535)
            self.assertEqual(packet, registration('test'))
            self.assertNotEqual(peer[1], server.getsockname()[1])  # don't bind the game's port
            server.sendto(b'\x01' + struct.pack('<iBBH', 42, 1, 1, 0), peer)
            requests = {server.recvfrom(100)[0], server.recvfrom(100)[0]}
            self.assertEqual(requests, {b'\x0a'+struct.pack('<i',42), b'\x0b'+struct.pack('<i',42)})
            # A corrupt datagram must not kill the receiver.
            server.sendto(b'\x03\x01', peer)
            server.sendto(entry_packet(), peer)
            server.sendto(car_packet(), peer)
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                s = store.snapshot()
                if 7 in s.cars and s.cars[7].located:
                    break
                time.sleep(.01)
            self.assertEqual(s.cars[7].position, 2)
            self.assertEqual(s.cars[7].name, 'Иван Иванов')
            client.stop()
            client.join(2)
            self.assertFalse(client.is_alive())
            self.assertEqual(server.recvfrom(100)[0], b'\x09' + struct.pack('<i', 42))
        finally:
            client.stop()
            if client.ident:
                client.join(2)
            server.close()


if __name__ == '__main__':
    unittest.main()
