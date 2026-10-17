"""Frozen-app entry point: initialize diagnostics before importing Tk or the app."""
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import sys
import tempfile
import threading


class LogStream:
    encoding = 'utf-8'

    def write(self, text):
        if text and text.strip():
            logging.getLogger('stderr').error(text.rstrip())
        return len(text or '')

    def flush(self):
        pass

    def isatty(self):
        return False


def configure_logging():
    bases = [Path(os.environ.get('LOCALAPPDATA') or tempfile.gettempdir()), Path(tempfile.gettempdir())]
    for base in bases:
        try:
            path = base / 'ACCTelemetry' / 'logs' / 'startup.log'
            path.parent.mkdir(parents=True, exist_ok=True)
            handler = RotatingFileHandler(path, maxBytes=1_000_000, backupCount=2, encoding='utf-8')
            handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(threadName)s %(message)s'))
            logger = logging.getLogger()
            logger.setLevel(logging.INFO)
            logger.addHandler(handler)
            if sys.stderr is None:
                sys.stderr = LogStream()
            return path
        except OSError:
            continue
    return None


def run():
    log_path = configure_logging()
    logging.info('Starting ACC Telemetry; Python %s; frozen=%s', sys.version.split()[0], getattr(sys, 'frozen', False))

    def thread_failure(args):
        logging.error('Background thread failed', exc_info=(args.exc_type, args.exc_value, args.exc_traceback))

    threading.excepthook = thread_failure
    try:
        from acc_telemetry.app import main
        result = main()
        logging.info('Application closed, exit=%s', result or 0)
        return result or 0
    except BaseException as exc:
        if isinstance(exc, SystemExit) and exc.code in (None, 0):
            return 0
        logging.exception('Startup/application failed')
        # The frozen windowed app has no console. Show a native error even if Tk
        # itself failed to load. Never show a blocking dialog during CI smoke tests.
        if os.name == 'nt' and '--smoke-test' not in sys.argv:
            try:
                import ctypes
                message = ('Не удалось открыть ACC Telemetry.\n\n'
                           f'Журнал ошибки:\n{log_path or "не удалось создать"}\n\n'
                           'Отправьте журнал разработчику. Отключать защиту Windows не нужно.')
                ctypes.windll.user32.MessageBoxW(None, message, 'ACC Telemetry — ошибка запуска', 0x10)
            except Exception:
                pass
        return 1


if __name__ == '__main__':
    raise SystemExit(run())
