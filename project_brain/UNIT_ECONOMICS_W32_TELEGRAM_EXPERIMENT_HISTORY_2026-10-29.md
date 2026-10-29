# W32 — Telegram-история, карточки и результаты ценовых экспериментов

Дата: 29.10.2026
Ветка: `codex/full-unit-economics-experiments-implementation-20261028`
Входной code HEAD: W31 runtime implementation; W32 adds Telegram read-only UI.
Статус: DONE.

## Реализовано

- Список экспериментов доступен из меню, имеет bounded pagination и открывает записи из Planning Workspace. После перезапуска runtime пользователь открывает меню заново; сохранённые записи и история остаются доступными, а старые process-local callback tokens безопасно отклоняются.
- Добавлены карточки эксперимента/фазы, история experiment/phase/result revisions и exact snapshot reopen. Все screen data перечитываются только из owner/store-scoped repository; frozen snapshot проходит через существующую W20 read-only projection.
- Экраны показывают сохранённые суммы, даты, хэши и версии; результат объясняется существующим recommendation service, включая ограниченные причины gates. UI не пересчитывает экономику, не опрашивает Ozon и не выдаёт модель за доказательство причинности.
- При позднем сохранении результата владелец нажимает «Обновить карточку» и получает свежую запись. От подтверждённой фазы можно открыть связанное наблюдение и существующий процесс сбора.
- История ограничена repository page size и числом фаз; сообщения компактны, а транспорт отправляет длинные ответы через общий Telegram splitter на 3 800 UTF-16 единиц. Callback tokens остаются короче лимита Telegram 64 bytes.

## Изменённые файлы

- `app/services/telegram_unit_economics_experiment_runtime_service.py` — список, read-only detail/history/revision/result screens и export-ready navigation points.
- `app/telegram_assistant_factory.py` — передаёт существующий observation runtime experiment runtime для ссылки на активный сбор.
- `tests/test_telegram_unit_economics_experiment_runtime.py` — добавлены restart/reopen, stale callback, phase→observation navigation, late-result refresh, reason rendering и exact frozen-snapshot reopen regressions.
- `CHANGELOG.md`, `project_brain/CURRENT_STATE.md`, `project_brain/TEST_MAP.md`, `project_brain/LUNA_FULL_UNIT_ECONOMICS_AND_PRICE_EXPERIMENTS_PROGRESS_2026-10-28.md` — отражены результаты и следующий этап.

## Проверки

Команда профиля (Windows, Python 3.14; отдельный временный data root, dotenv/plugin autoload отключены):

```powershell
$env:PYTHON_DOTENV_DISABLED='1'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
$env:PYTHONPATH='app;tests'
$env:PYTHONTZPATH='C:\Users\gelashvilee\AppData\Local\Programs\Python\Python314\Lib\site-packages\tzdata\zoneinfo'
$env:AI_ASSISTANT_DATA_DIR = Join-Path $env:TEMP ('w32-target-' + [guid]::NewGuid().ToString('N'))
& 'C:\Users\gelashvilee\Desktop\Ai ассистент\.venv\Scripts\python.exe' -m pytest -q --tb=short tests/test_telegram_unit_economics_experiment_runtime.py tests/test_unit_economics_experiment_recommendation_service.py tests/test_unit_economics_experiment_snapshot_view_service.py
```

- Целевой W32 profile (experiment runtime + recommendation + frozen view): **24 passed in 1.19s**.
- Linked W31/W32 public menu/runtime, scenario, observation, repository, recommendation and frozen-view profile: **111 passed in 4.43s**.
- Замороженный snapshot screen успешно открывается из тестового Planning Workspace; тест проверяет обязательное сообщение, что Ozon не опрашивался.
- Проверены stale transient callback после runtime restart, recovery из persistent history, переход в связанное observation и поздний result refresh.
- `py_compile` changed Python modules: PASS; `git diff --check`: PASS; `git diff -- data`: empty.
- Тесты используют синтетическую БД во временной директории. Данные владельца не читались/не изменялись; реальные API/бот не запускались.

## Ограничения и следующий этап

W31 остаётся BLOCKED для первого пользовательского запуска: production source adapter не создаёт полный 56-дневный snapshot через приложение. W32 не снижает этот gate. Следующий этап W33 добавит выгрузку сохранённых snapshot/history без повторного чтения источников.

Архитектурное влияние W32: minor extension существующего Telegram runtime/repository routing; база данных, бизнес-математика и контракты сохранения не менялись.
