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
            app.toggle_fs()
            app.toggle_fs()
            app.geometry('1100x760')
            app.update_idletasks()
            app._switch(True)
            app.update()
        finally:
            app._close()
        self.assertFalse(app.feeds.threads)
