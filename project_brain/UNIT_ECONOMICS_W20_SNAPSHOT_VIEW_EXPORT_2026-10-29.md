# W20 — единая snapshot-проекция и экспорт эксперимента

Дата: 29.10.2026
Branch: `codex/full-unit-economics-experiments-implementation-20261028`
Входной code HEAD: `0e2a71af`
Code commit: `68881def` (`Add frozen unit economics experiment snapshot view`)
ТЗ: `LUNA_FULL_UNIT_ECONOMICS_AND_PRICE_EXPERIMENTS_TASK_2026-10-28.md`

## Результат

Добавлен `UnitEconomicsExperimentSnapshotViewService`: он строит один bounded read model из `get_price_experiment_frozen_snapshot`, не загружает источники и не пересчитывает экономику. В проекцию входят сохранённые суммы/статусы экономики, применимость и полнота расходов, tariff/quantity evidence, cost basis и revisions.

Экспорт `AnalyticsExportService.export_unit_economics_experiment_snapshot` использует тот же read model в JSON/CSV serializer path. Экспорт хранит projection целиком одной JSON-ячейкой, сообщает `source_reads=false` и `recalculated_on_export=false`, не обновляя данные. JSON и CSV regressions декодируют запись и сверяют её с той же projection. Добавлен allowlisted export kind.

Проекция проверяет exact experiment/store/SKU/scheme, plan revision/schema/calculation version, expense snapshot reference, tariff revision и observation result revision. Несовпадающая ссылка expense snapshot помечает cost basis как `UNCONFIRMED` и добавляет model limit; старые планы без `tax_mode` сохраняются как unavailable/incomplete, а не отклоняются. Внутренние IDs, SKU/offer/product names, title эксперимента и исходные API данные в read model/export не передаются. Лимит view — 64 KiB без усечения.

Фактический Telegram detail экран пока не подключён: W20 создаёт общий contract для будущего W32 UI и текущего экспортного сервиса.

## Изменённые файлы

- `app/services/unit_economics_experiment_snapshot_view_service.py` — новый чистый projection service.
- `app/services/analytics_export_service.py` — snapshot export из того же projection.
- `app/services/analytics_export_serializer.py` — allowlisted export kind.
- `tests/test_unit_economics_experiment_snapshot_view_service.py` — coverage, exact versions, privacy, cost-basis mismatch, legacy tax mode, size gate и export parity.
- `tests/test_planning_workspace_unit_economics.py` — projection фактического frozen bundle, включая tariff и quantity revision.

## Проверки

Изолированный Windows/Python 3.12 профиль: **50 passed in 3.49s** по команде:

```powershell
$env:PYTHON_DOTENV_DISABLED = '1'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
$env:AI_ASSISTANT_DATA_DIR = Join-Path $env:TEMP ('unit-economics-w20-' + [guid]::NewGuid().ToString('N'))
$env:PYTHONPATH = (Join-Path (Get-Location).Path 'app') + ';C:\Users\gelashvilee\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\Lib\site-packages'
Remove-Item Env:OZON_CLIENT_ID -ErrorAction SilentlyContinue
Remove-Item Env:OZON_API_KEY -ErrorAction SilentlyContinue
Remove-Item Env:TELEGRAM_BOT_TOKEN -ErrorAction SilentlyContinue
& 'C:\Users\gelashvilee\Desktop\Ai ассистент\.venv\Scripts\python.exe' -m pytest -q tests/test_unit_economics_experiment_snapshot_view_service.py tests/test_planning_workspace_unit_economics.py tests/test_planning_workspace_repository.py tests/test_analytics_export_service.py tests/test_analytics_export_serializer.py tests/test_unit_price_owner_exports.py
```

Первый запуск не имел `app` в `PYTHONPATH`; второй использовал проектный Python без IANA базы и выявил локальное отсутствие timezone database. Финальный успешный профиль подключил уже установленную bundled `tzdata` без изменения окружения проекта. Ни один прогон не делал реальных Ozon/Telegram запросов и не запускал бота. Проверки синтаксиса, diff/data safety выполняются после документирования W20.

## Ограничения и следующий шаг

Исторические суммы читаются только из сохранённых версий и не доказывают фактический спрос или причинность. W20 не включает Telegram UI и сбор новых источников. Следующий этап — W21: чистая state machine, атомарные переходы и общий active-SKU guard с observation.
