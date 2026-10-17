import logging
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import launcher


class LauncherTests(unittest.TestCase):
    def test_windowed_stderr_can_be_logged(self):
        with self.assertLogs('stderr', level='ERROR') as log:
            self.assertEqual(launcher.LogStream().write('startup problem\n'), 16)
        self.assertIn('startup problem', log.output[0])
        self.assertFalse(launcher.LogStream().isatty())

    def test_log_path_is_writable_and_utf8(self):
        root = logging.getLogger()
        before = list(root.handlers)
        level = root.level
        try:
            with tempfile.TemporaryDirectory() as d:
                with patch.dict(os.environ, {'LOCALAPPDATA': d}):
                    path = launcher.configure_logging()
                    self.assertEqual(path, Path(d) / 'ACCTelemetry' / 'logs' / 'startup.log')
                    logging.info('Диагностика запуска')
                    for handler in root.handlers:
                        handler.flush()
                    self.assertIn('Диагностика', path.read_text(encoding='utf-8'))
                    # Close handles before deleting the temporary folder on Windows.
                    for handler in list(root.handlers):
                        if handler not in before:
                            root.removeHandler(handler)
                            handler.close()
        finally:
            root.setLevel(level)


if __name__ == '__main__':
    unittest.main()
