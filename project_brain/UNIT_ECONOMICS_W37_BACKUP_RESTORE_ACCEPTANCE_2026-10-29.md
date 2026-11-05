# W37 — backup/restore и повторное открытие истории

Дата: 29.10.2026
Статус: DONE (synthetic backup, новый root; без внешних API).

## Проверка полного экспериментального набора

Добавлен `test_experiment_phases_results_and_event_history_survive_new_root_restore` в `tests/test_unit_price_backup_restore.py`. Он создаёт только синтетические данные: saved plan с cost input, 56-дневный expense snapshot, tariff profile, baseline experiment, owner-confirmed phase, collection и result через штатный collector seam, а также append-only control event.

Проверка сохраняет архив через `BotBackupService`, проверяет архив, восстанавливает его в новый временный каталог и создаёт новый экземпляр `PlanningWorkspaceRepository`, как после перезапуска. После повторного открытия сверяются точные структуры плана, cost snapshot, тарифа, эксперимента, фаз, collections, results и событий; восстановленная `planning_schema` совпадает с текущей версией репозитория.

Другой store после restore не может прочитать план, expense snapshot, тариф или эксперимент. В отдельной синтетической копии future schema versions в experiment и phase payload приводят к `PLANNING_PRICE_EXPERIMENT_CORRUPT` и `PLANNING_PRICE_EXPERIMENT_PHASE_CORRUPT`; запись не принимается как пустая или частично восстановленная.

Существующие связанные tests дополняют этот сценарий: schema migration и backfill active guard, история документа с corrupt/future revisions, корневой будущий schema version остаётся без изменений при отказе, и прежние unit-price observation results сохраняются по точным revision после backup/restore. Production-код backup/restore и форматы миграции не изменялись.

## Проверки

Изолированный Windows профиль:

```text
46 passed in 2.94s
```

Файлы: `tests/test_unit_price_backup_restore.py`, `tests/test_planning_workspace_unit_economics.py`, `tests/test_planning_workspace_repository.py`. Использовались проектный `.venv`, отключённая загрузка `.env`/pytest plugins и временный `AI_ASSISTANT_STORAGE_ROOT`; восстановление и повреждение ограничены `tmp_path`. Реальные данные и `data/` не изменялись. W38 отдельно запустит полный suite в disposable checkout.

## Ограничения

Это проверка целостности локальной копии и tenant scope, а не проверка реального рабочего архива владельца. Owner validation остаётся pending; W31 acquisition/candidate Telegram blockers сохраняются. Следующий этап — полный pytest, compileall, safety checks и CI нового commit SHA в W38.
