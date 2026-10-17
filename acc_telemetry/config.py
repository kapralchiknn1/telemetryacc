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
    args = parser.parse_args(argv)
    config = {}
    default = Path.home() / 'Documents' / 'Assetto Corsa Competizione' / 'Config' / 'broadcasting.json'
    path = args.config or default
    if args.config or path.is_file():
        try:
            config = json.loads(path.read_text(encoding='utf-8-sig'))
            if not isinstance(config, dict):
                raise ValueError('expected JSON object')
        except (OSError, ValueError):
            if args.demo and not args.config:
                config = {}  # demo is usable even if the game's default config is broken
            else:
                parser.error('Не удалось прочитать broadcasting.json; проверьте путь и JSON (содержимое не выводится)')
    args.port = args.port if args.port is not None else config.get('updListenerPort', 9000)
    if isinstance(args.port, bool) or not isinstance(args.port, int) or not 1 <= args.port <= 65535:
        parser.error('порт должен быть целым числом 1..65535')
    args.password = os.environ.get('ACC_CONNECTION_PASSWORD', config.get('connectionPassword', ''))
    if not isinstance(args.password, str) or len(args.password.encode('utf-8')) > 65535:
        parser.error('некорректный пароль Broadcasting API')
    return args
