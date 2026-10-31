# W38 — полная проверка и защита данных

Дата: 30.10.2026
Статус: Локальная Windows проверка DONE; GitHub Verify текущего PR HEAD ожидает публикации W39.

## Точный локальный результат

Проверенный кодовый SHA: `428e80cb9a3ada56af1b9aa21280f52d3dec3d64` (`Use current schema version in migration tests`). Проверка проведена в отдельном disposable worktree `ai-assistant-w38-428e80cb`, Python 3.12.10, не в checkout с рабочей веткой и не в каталоге владельца.

Команды, соответствующие `.github/workflows/verify.yml`:

```powershell
python -m compileall -q app
python -c 'from database import create_tables; create_tables()'
python -m pytest -q
```

Результаты:

```text
compileall: PASS
full pytest: 4335 passed in 50.37s
```

Среда: `PYTHONPATH=app`, `PYTHON_DOTENV_DISABLED=1`, пустые `OZON_CLIENT_ID`/`OZON_API_KEY`, `AI_ASSISTANT_STORAGE_ROOT` не задан. Для Windows тестовой среды явно использована локально установленная IANA база через `PYTHONTZPATH`; это компенсирует отсутствие системной zoneinfo database в локальном Windows образе и не меняет продуктовый код.

## Исправления, найденные полным прогоном

1. Старый `_Keyboard` test double не принимал новый опциональный `experiment_callback`; он обновлён, один узкий regression test прошёл.
2. Два migration tests в `tests/test_unit_price_observation_repository.py` ожидали прежнюю schema version `11`; assertions теперь ссылаются на `PlanningWorkspaceRepository.DATABASE_SCHEMA_VERSION` (12). Миграции и production code не изменялись; оба теста прошли отдельно.

Первые два полных запуска не засчитывались: один использовал storage root, отсутствующий в CI, второй — без IANA timezone data. Финальный прогон выполнен после устранения обоих факторов; в нём не было skip/deselect.

## Данные и безопасность

Full pytest запускался только в disposable worktree на точном commit. Legacy suite изменила `data/tasks.json` и создала `data/tasks.json.lock` **в disposable копии**; эти тестовые побочные эффекты не переносились и не копировались в source checkout. Исходная рабочая ветка осталась чистой; её `git diff -- data` пуст. Тестовые `.env` и live credentials не читались; Ozon/Telegram API и реальный бот не вызывались.

## Оставшиеся проверки

Этот локальный прогон подтверждает Windows Python suite. Linux Verify, production Docker build/smoke и SHA-bound отчёт должны пройти на final PR HEAD в GitHub Actions; их результат будет указан в самом PR, чтобы связать ссылку с неизменяемым проверенным commit SHA. До этого нельзя заявлять, что remote CI зелёный.
