import math
import unittest
from acc_telemetry.camera import MapCamera


class MapCameraTests(unittest.TestCase):
    def setUp(self):
        self.camera = MapCamera()
        # A long world-space circuit, roughly the extent expected for a large map.
        self.bounds = (-10000, -5000, 10000, 5000)
        self.camera.update(self.bounds, 1000, 600)

    def assertPointAlmostEqual(self, actual, expected):
        for a, b in zip(actual, expected):
            self.assertAlmostEqual(a, b)

    def test_overview_and_coordinate_roundtrip(self):
        self.assertPointAlmostEqual(self.camera.project(0, 0), (500, 300))
        for point in [(100, 200), (-9999, 4999), (10000, -5000)]:
            self.assertPointAlmostEqual(self.camera.unproject(*self.camera.project(*point)), point)

    def test_drag_moves_map_by_exact_screen_pixels(self):
        before = self.camera.project(123, 456)
        self.camera.pan(120, -70)
        self.assertPointAlmostEqual(self.camera.project(123, 456), (before[0] + 120, before[1] - 70))
        self.assertFalse(self.camera.overview)

    def test_pan_survives_telemetry_and_bounds_updates(self):
        self.camera.pan(150, 80)
        center, scale = self.camera.center, self.camera.scale
        self.camera.update((-12000, -6000, 15000, 9000), 1000, 600)
        self.assertEqual(self.camera.center, center)
        self.assertEqual(self.camera.scale, scale)

    def test_cursor_zoom_keeps_world_point_under_pointer(self):
        anchor = self.camera.unproject(230, 180)
        self.camera.wheel(3, 230, 180)
        self.assertPointAlmostEqual(self.camera.unproject(230, 180), anchor)
        self.assertAlmostEqual(self.camera.zoom, 3)

    def test_large_map_zoom_limit_is_80_not_5(self):
        self.camera.wheel(1000)
        self.assertAlmostEqual(self.camera.zoom, 80)
        self.camera.wheel(.000001)
        self.assertAlmostEqual(self.camera.zoom, .4)

    def test_follow_tracks_moving_driver_in_center(self):
        self.camera.focus((1000, -2000))
        self.assertTrue(self.camera.follow)
        self.assertAlmostEqual(self.camera.zoom, 8)
        for position in [(1200, -1800), (5000, 4000), (-8000, 2000)]:
            self.camera.update(self.bounds, 1000, 600, position)
            self.assertPointAlmostEqual(self.camera.project(*position), (500, 300))

    def test_follow_zoom_does_not_pull_driver_from_center(self):
        self.camera.focus((200, 500))
        self.camera.wheel(2, 20, 20)
        self.assertPointAlmostEqual(self.camera.project(200, 500), (500, 300))
        self.assertTrue(self.camera.follow)

    def test_drag_disables_follow_without_resetting_zoom(self):
        self.camera.focus((1000, 2000))
        scale = self.camera.scale
        self.camera.pan(40, 50)
        center = self.camera.center
        self.camera.update(self.bounds, 1000, 600, (9000, 4000))
        self.assertFalse(self.camera.follow)
        self.assertEqual(self.camera.center, center)
        self.assertEqual(self.camera.scale, scale)

    def test_follow_waits_if_selected_driver_disappears(self):
        self.camera.focus((1000, 2000))
        self.camera.update(self.bounds, 1000, 600, None)
        self.assertTrue(self.camera.follow)
        self.assertEqual(self.camera.center, (1000, 2000))

    def test_fit_all_clears_manual_camera_and_follow(self):
        self.camera.focus((8000, 1000))
        self.camera.pan(80, 60)
        self.camera.fit_all()
        self.camera.update(self.bounds, 1000, 600)
        self.assertTrue(self.camera.overview)
        self.assertFalse(self.camera.follow)
        self.assertAlmostEqual(self.camera.zoom, 1)
        self.assertPointAlmostEqual(self.camera.project(0, 0), (500, 300))

    def test_resize_keeps_follow_centered(self):
        self.camera.focus((3000, 2000))
        self.camera.update(self.bounds, 400, 200, (3000, 2000))
        self.assertPointAlmostEqual(self.camera.project(3000, 2000), (200, 100))

    def test_tiny_window_and_invalid_wheel_are_safe(self):
        self.camera.update((0, 0, 0, 0), 1, 1)
        self.assertGreater(self.camera.scale, 0)
        for factor in (0, -1, float('nan'), float('inf')):
            self.camera.wheel(factor)
        self.assertTrue(all(math.isfinite(v) for v in self.camera.project(1, 1)))
