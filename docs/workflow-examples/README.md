# Шаблоны GitHub Actions (не активны)

GitHub принял исходники, но отклонил пакет, включавший `.github/workflows`.
Без этих файлов тот же пакет был успешно записан. Поэтому автоматизация не
включена через текущее подключение.

Чтобы включить её, владелец репозитория может вручную добавить файлы:

- `tests.yml` → `.github/workflows/tests.yml`
- `build-windows.yml` → `.github/workflows/build-windows.yml`

После коммита первого файла тесты запускаются на push/PR. После добавления
второго в default branch появится ручной workflow **Build Windows executable**.
Он собирает приложение на Windows и сохраняет exe как artifact, не публикуя релиз.
Эти шаблоны не запускались в GitHub Actions в рамках данной доработки.
