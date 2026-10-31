# W36 — конкурентность и ограниченные ресурсы

Дата: 29.10.2026
Статус: DONE (синтетическая инженерная приёмка; внешние API не вызывались).

## Область и доказательства

W36 проверяет конкурирующие записи, атомарность, ограниченный рост журнала, пагинацию, квоты, privacy и общие бюджеты запросов. Производственная логика не менялась; добавлен отдельный acceptance-модуль `tests/test_unit_economics_experiment_concurrency_acceptance.py`.

| Сценарий | Фактический результат |
|---|---|
| Одновременное подтверждение одной baseline-фазы | Два потока используют одинаковые ожидаемые ревизии и разные idempotency keys; ровно один подтверждает фазу и создаёт наблюдение. Второй получает state conflict. Сохранена одна связь ACTIVE-фазы с единственным observation. |
| Одновременный сбор одной фазы | Барьер синхронизирует оба источника перед записью; ровно один вызов создаёт collection revision 1 и result revision 1. Второй завершается конфликтом state/result. Суммы комиссии `-70.00` и CPC `12.50` сохранены ровно один раз. |
| Конкурентное изменение DRAFT и архивация | При одинаковом expected state revision ровно одна операция побеждает. Итоговый статус DRAFT или ARCHIVED имеет state revision 2; обе ревизии остаются читаемыми и согласованными. |
| Фиксированный finite soak | Seed `20261029`, 64 последовательных допустимых CONTROL_UPDATE. Каждая запись увеличивает state revision ровно на один; 64 события доступны как 7 страниц по максимум 10, revisions идут от 64 к 1 в порядке API. Нет прямых owner/store/product/offer/SKU/API-secret полей. Это ограниченный soak, не стресс-тест по пропускной способности. |
| Ошибка/отмена/поздний ответ/shared budget | Существующие проверки `tests/test_unit_economics_experiment_phase_collection_service.py` покрывают rollback коллекции и результата, cooperative cancellation, отбрасывание позднего ответа после паузы/исчерпания времени и передачу дочернему сборщику остатка HTTP-бюджета без его сброса. |
| Quotas, tenant/privacy и размер | Существующие проверки `tests/test_planning_workspace_unit_economics.py`, `tests/test_unit_economics_experiment_snapshot_view_service.py`, `tests/test_analytics_export_serializer.py` и `tests/test_telegram_unit_economics_experiment_runtime.py` покрывают event/snapshot/result/export quota с fail-closed/rollback, store scope, allowlist приватности и отказ для oversized projection/export без усечения. |

## Проверки

Новые конкурентные/soak regressions:

```text
4 passed in 0.99s
```

Связанный W36 Windows profile (6 модулей: новые гонки, phase collection, repository quotas/concurrency, snapshot projection, serializer, Telegram history/export):

```text
64 passed in 4.36s
```

Запускался проектным `.venv` с `PYTHON_DOTENV_DISABLED=1`, `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`, временным `AI_ASSISTANT_STORAGE_ROOT` и установленной локальной IANA timezone database. Реальные Ozon-запросы, Telegram API и production bot не использовались. Данные `data/` не затрагивались. Архитектурных решений не добавлено.

## Ограничения и продолжение

Это bounded acceptance для ожидаемых конфликтов и сохранённых лимитов, а не нагрузочный тест/измерение пикового RSS. W31 blockers остаются: приложению не подключён автоматический сбор полного 56-дневного reference snapshot и в Telegram нет завершённого candidate-phase setup. W37 продолжает проверку резервного копирования/восстановления, миграций, повреждённых записей и tenant isolation.
