"""Real Tk smoke tests: run on Windows or Linux under Xvfb; skip without Tk/display."""
import unittest


class DashboardSmokeTests(unittest.TestCase):
    def test_demo_switch_fullscreen_resize_and_close(self):
        try:
            import tkinter as tk
        except ImportError:
            self.skipTest('Tk is not installed')
        try:
            probe = tk.Tk()
            probe.withdraw()
            probe.update()
            probe.destroy()
        except tk.TclError:
            self.skipTest('No graphical display (use Xvfb)')
        from acc_telemetry.app import Dashboard
        from acc_telemetry.config import parse_args
        from acc_telemetry.demo_feed import DemoGenerator
        app = Dashboard(parse_args(['--demo']))
        try:
            app.withdraw()
            app.update()
            # Deterministic update; the in-process demo uses non-contiguous IDs.
            DemoGenerator(app.store).step(1)
            app.after_cancel(app.after_id)
            app._tick()
            app.update_idletasks()
            self.assertEqual(len(app.positions.tree.get_children()), 12)
            app.positions.tree.selection_set('10')
            app.update()
            self.assertEqual(app.rival.selected, 10)
            from types import SimpleNamespace
            from acc_telemetry.track_map import REFERENCE_TRACK
            # Map geometry is meaningful only after the test window is mapped.
            app.deiconify()
            app.update()
            app.update_idletasks()
            self.assertGreater(app.map.winfo_width(), 10)
            state = app.store.snapshot()
            app.map.render(state, REFERENCE_TRACK)
            player_id = state.player_id
            app.map.follow_player()
            app.map.render(state, REFERENCE_TRACK)
            own = state.cars[player_id]
            self.assertAlmostEqual(app.map.camera.project(own.x, own.y)[0], app.map.winfo_width()/2)
            self.assertTrue(app.follow_var.get())
            app.map._drag_start(SimpleNamespace(x=100, y=80))
            app.map._drag_move(SimpleNamespace(x=170, y=120))
            app.map._drag_end(SimpleNamespace(x=170, y=120))
            self.assertFalse(app.follow_var.get())
            self.assertFalse(app.map.camera.follow)
            panned = app.map.camera.center
            app.map.render(state, REFERENCE_TRACK)
            self.assertEqual(app.map.camera.center, panned)
            app.map.follow_car(10)
            state.cars[10].x += 2000
            app.map.render(state, REFERENCE_TRACK)
            self.assertEqual(app.map.camera.center, (state.cars[10].x, state.cars[10].y))
            self.assertEqual(state.player_id, player_id)  # observing never changes physical telemetry
            app.map.fit_all()
            self.assertFalse(app.follow_var.get())
            self.assertAlmostEqual(app.map.zoom, 1)
            app.map.follow_car(9999)
            app.map.render(state, REFERENCE_TRACK)
            self.assertIsNone(app.map.target_position)
            app.map.fit_all()
            app.toggle_fs()
            app.toggle_fs()
            # Every pit-wall panel must remain inside the root at both layouts.
            for geometry in ('1100x760', '1920x1080'):
                app.geometry(geometry)
                app.update()
                app.update_idletasks()
                for panel in (app.dial, app.pedals, app.tyres, app.fuel, app.wind,
                              app.extra, app.rival_canvas, app.map, app.positions):
                    self.assertGreater(panel.winfo_width(), 100)
                    self.assertGreater(panel.winfo_height(), 100)
                    self.assertGreaterEqual(panel.winfo_rootx(), app.winfo_rootx())
                    self.assertLessEqual(panel.winfo_rootx()+panel.winfo_width(),
                                         app.winfo_rootx()+app.winfo_width())
                    self.assertLessEqual(panel.winfo_rooty()+panel.winfo_height(),
                                         app.winfo_rooty()+app.winfo_height())
                # Windows runners may clamp the requested width to their monitor.
                self.assertEqual('model' in app.positions.tree.cget('displaycolumns'),
                                 app.positions.winfo_width() >= 660)
            # Exercise both layouts independently of the runner's display size.
            from unittest.mock import patch
            for width in (390, 700):
                with patch.object(app.positions, 'winfo_width', return_value=width):
                    app.positions._layout()
                self.assertEqual('model' in app.positions.tree.cget('displaycolumns'), width >= 660)
            app.positions._layout()
            app.geometry('1100x760')
            app._switch(True)
            app.update()
        finally:
            app._close()
        self.assertFalse(app.feeds.threads)
