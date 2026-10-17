# ACC Telemetry Dashboard

Приложение телеметрии для **Assetto Corsa Competizione**: читает пакет
`local telemetry` из встроенного UDP-стрима ACC и показывает:

- позицию пилота относительно соперников (P, отставание/интервал);
- список всех машин с моделями соперников;
- карту трассы с точками машины игрока и всех соперников в реальном времени;
- скорость машины, обороты двигателя и передачу;
- температуры и давления четырёх шин;
- скорость и направление ветра, температуру асфальта и воздуха.

## Структура

```
acc_telemetry/
  app.py            - главное окно (Tkinter)
  acc_udp.py        - UDP-приёмник и парсер пакета local telemetry ACC
  track_map.py      - загрузка контуров трасс (traced outlines)
  demo_feed.py      - генератор тестовой телеметрии (для проверки без игры)
  widgets/          - виджеты: карта, спидометр, шины, ветер, позиции, модель авто
tracks/             - JSON-контуры трасс (можно добавить свои)
```

## Настройка ACC

В `assetto_corsa_competizione/userconfig/app/system.config.json`:

```json
"LOCAL_TELEMETRY": { "ENABLE": true, "IP": "127.0.0.1", "PORT": 9000 }
```

(или через внутриигровое меню: Content Manager → Settings → Custom Apps → UDP).

## Запуск из исходников

```bash
pip install -r requirements.txt
python acc_telemetry/app.py                 # подключение к UDP 127.0.0.1:9000
python acc_telemetry/app.py --demo          # демо-режим без игры
```

## Сборка .exe (Windows)

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name acc_telemetry ^
    --add-data "tracks;tracks" acc_telemetry/app.py
```

Готовый файл появится в `dist/acc_telemetry.exe`.
