# C01: компактный отчёт и scoped детализация — 25.10.2026

## Результат

C01 выполнен локально. Короткий отчёт прибыли форматирует суммы с копейками и разделителями тысяч, показывает долю денежной строки от общей выручки, сохраняет знак отрицательного результата и не вычисляет процент при нулевой или отрицательной базе. Итог подписан как прибыль после себестоимости; при подтверждённом полном учёте внешних расходов в названии указывается и этот компонент.

Кнопка `📋 Подробности` ведёт к исходной подробной строке того же периода, пользователя и магазина в существующем 10-минутном scoped report cache. Она не запускает новый запрос. Экран деталей возвращает к тому же отчёту и к полноте данных. Стандартный финансовый экран показывает одну приоритетную причину и количество дополнительных; полнота и диагностика показывают все доступные canonical причины.

В экспериментальном отчёте магазина проверены бюджеты короткого ответа и подробных частей. Telegram transport привязывает клавиатуру к последней части; длинный текст делится по существующему алгоритму с пределом в 3 800 UTF-16 units на отправляемое сообщение.

## Проверки

Команда в рабочей ветке (PowerShell; storage отдельный, production DB не открывалась):

```powershell
Set-Location -LiteralPath 'C:\Users\gelashvilee\.codex\worktrees\daily-readiness-foundation\Ai ассистент'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
$env:PYTHONPATH = Join-Path (Get-Location).Path 'app'
$env:AI_ASSISTANT_STORAGE_ROOT = Join-Path $env:TEMP 'ai-assistant-daily-readiness-c01'
$env:AI_ASSISTANT_MASTER_KEY = ''
$env:AI_ASSISTANT_CACHE_ENABLED = 'false'
& 'C:\Users\gelashvilee\Desktop\Ai ассистент\.venv\Scripts\python.exe' -m pytest tests/test_period_profit_compact_report_v1431_v1440.py tests/test_period_profit_analytics_runtime.py tests/test_experimental_store_economics.py tests/test_telegram_loading_feedback_v1451_v1460.py tests/test_period_profit_response.py -p no:cacheprovider -q -k 'not production_factory'
```

Результат: **74 passed, 1 deselected in 3.24s**. Исключён только `test_production_factory_routes_period_analytics_without_requery`: его `tmp_path` setup заблокирован Windows ACL в локальной среде. Полный pytest локально не запускался; тест требует exact-head CI.

Форматные измерения на фикстурах: короткий согласованный отчёт — **695 chars / 697 UTF-16 units**; пример runtime-сводки с неполнотой — **557 / 558**. Длинная синтетическая детализация — **7 350 chars / 7 700 UTF-16 units**, разделена на 3 сообщения; максимальная часть — **3 799 UTF-16 units**. Это локальный транспортный тест, не live Telegram вызов.

Проверенная детализация callback дополнительно подтверждает неизменный `report_view_id`, единственный query-service call, отказ для другого владельца, callback не длиннее 64 UTF-8 bytes и keyboard на том же snapshot. Финансовые источники и формулы не запрашивались повторно и не менялись.

In-memory compile всех 7 изменённых Python modules: **passed**; `git diff --check`: **passed**. Обычный `compileall -q app tests` не может записывать в существующие `__pycache__` из-за Windows ACL (`PermissionError: WinError 5`), поэтому не засчитан. Exact-head Windows/Linux CI и полный CI suite ожидают последующих этапов интеграции; PR для этой программы ещё не создан. Слияние, развёртывание и реальный запуск бота не выполнялись.

## Изменённые файлы

- `app/period_profit_compact_response.py` — формат сумм/долей, корректная подпись прибыли и поведение с нулевой выручкой.
- `app/services/assistant_period_profit_runtime_service.py` — кэш подробного текста и scoped callback, компактная причина и полный список причин на экране полноты.
- `app/services/assistant_keyboard_service.py`, `app/services/assistant_button_handler_service.py` — кнопки и маршрутизация деталей.
- `tests/test_period_profit_compact_report_v1431_v1440.py`, `tests/test_period_profit_analytics_runtime.py`, `tests/test_experimental_store_economics.py` — регрессии формата, бюджета, scope и повторного запроса.
- `docs/telegram-user-guide.md`, `CHANGELOG.md`, `project_brain/CURRENT_STATE.md`, `project_brain/ROADMAP.md`, `project_brain/TEST_MAP.md`, `project_brain/DAILY_USE_COMPLETENESS_ACCEPTANCE_B05_2026-10-25.md` — пользовательская инструкция, текущий статус и уточнение детализации причин.
