"""CLI/config loading independent of Tk. Password is never printed or saved."""
import argparse
import json
import os
from pathlib import Path


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description='ACC Telemetry Dashboard')
    parser.add_argument('--demo', action='store_true', help='демо без игры и сетевых подключений')
    parser.add_argument('--host', default='127.0.0.1', help='IP/имя ПК с ACC (по умолчанию localhost)')
    parser.add_argument('--port', type=int, help='порт Broadcasting API ACC, по умолчанию 9000')
    parser.add_argument('--config', type=Path, help='путь к broadcasting.json ACC; пароль не сохраняется')
    parser.add_argument('--track-map', type=Path, help='JSON-контур трассы в мировых метрах x/y')
    parser.add_argument('--fullscreen', action='store_true')
    parser.add_argument('--smoke-test', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--smoke-report', type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    config = {}
    args.startup_warning = ''
    # An explicit config must not depend on HOME/USERPROFILE. Headless Windows
    # runners and deliberately isolated tests may have neither variable.
    path = args.config
    if path is None:
        try:
            path = Path.home() / 'Documents' / 'Assetto Corsa Competizione' / 'Config' / 'broadcasting.json'
        except RuntimeError:
            path = None  # no home directory: use CLI/environment/default values
    if path is not None and (args.config or path.is_file()):
        try:
            config = json.loads(path.read_text(encoding='utf-8-sig'))
            if not isinstance(config, dict):
                raise ValueError('expected JSON object')
        except (OSError, ValueError):
            if not args.config:
                config = {}
                args.startup_warning = 'Не удалось прочитать стандартный broadcasting.json ACC. Проверьте настройки подключения.'
            else:
                parser.error('Не удалось прочитать broadcasting.json; проверьте путь и JSON (содержимое не выводится)')
    configured_port = config.get('updListenerPort', 9000)
    valid_port = (isinstance(configured_port, int) and not isinstance(configured_port, bool)
                  and 1 <= configured_port <= 65535)
    if args.port is None and not args.config and not valid_port:
        # A disabled/default ACC configuration must not prevent opening the UI.
        args.startup_warning = 'Broadcasting ACC не настроен: проверьте updListenerPort (обычно 9000).'
        configured_port = 9000
    args.port = args.port if args.port is not None else configured_port
    if isinstance(args.port, bool) or not isinstance(args.port, int) or not 1 <= args.port <= 65535:
        parser.error('порт должен быть целым числом 1..65535')
    args.password = os.environ.get('ACC_CONNECTION_PASSWORD', config.get('connectionPassword', ''))
    if not isinstance(args.password, str) or len(args.password.encode('utf-8')) > 65535:
        if args.config or 'ACC_CONNECTION_PASSWORD' in os.environ:
            parser.error('некорректный пароль Broadcasting API')
        args.password = ''
        args.startup_warning = 'Некорректный пароль в стандартном broadcasting.json ACC. Проверьте настройки.'
    return args
