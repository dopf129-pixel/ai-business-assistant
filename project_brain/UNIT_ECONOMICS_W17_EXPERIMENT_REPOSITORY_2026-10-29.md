# W17 — хранилище снимков экономики и экспериментов

Дата: 29.10.2026
Кодовый коммит: `b249bcab` — `Add durable unit economics experiment storage`
Этап: W17 (`W03`, `W10`) — DONE.

## Изменение

- Схема SQLite `PlanningWorkspaceRepository` аддитивно переведена с версии 5 на 6. Старые планы, тарифные профили, наблюдения, сравнения и payload schema 1–4 не пересчитываются и не переписываются.
- Добавлено content-addressed хранение allowlisted снимков готовности дополнительных расходов. JSON нормализуется до записи, ограничен 64 KiB, защищён от UPDATE/DELETE и читается без обращения к источникам.
- Добавлено сохранение эксперимента с точными ссылками на ревизию плана, снимок, опциональные ревизии тарифа и observation result. Все ссылки проверяются в транзакции на owner/store/SKU/sale schema.
- Добавлены фазы и append-only ревизии состояний/результатов. CAS и idempotency с hash тела не допускают stale write или повторное создание; частичный unique index резервирует не более одного активного эксперимента на точный SKU/scheme.
- Архивация не удаляет историю. Пагинация ограничена существующим максимумом 10; хранилище ограничивает 1 000 снимков, 100 экспериментов на store, 10 фаз и 20 результатов на фазу. Лимиты покрыты регрессиями.
- Future/corrupt версии, неверные ссылки, неправильная арифметика результата, перекрёстный scope и незавершённая транзакция отказываются fail-closed.

## Новые таблицы

`planning_unit_economics_snapshots`, `planning_price_experiments`, `planning_price_experiment_revisions`, `planning_price_experiment_phases`, `planning_price_experiment_phase_revisions`, `planning_price_experiment_results`, `planning_price_experiment_idempotency`.

Таблицы добавляются в существующем `BEGIN IMMEDIATE`; foreign keys связывают записи с точной tenant scope и исходными immutable revisions. Raw Ozon rows, credentials и свободный текст не сохраняются. W17 не добавляет API-клиент, Telegram-flow или фоновый сборщик.

## Проверки

- Связанный профиль: **89 passed in 3.58s** — W17 snapshots/experiments, базовый repository, tariff profiles, observation repository, plan comparison и saved-plan Telegram reopen.
- Полный изолированный `pytest`: **4,166 passed in 36.99s**.
- `py_compile`: PASS; `git diff --check`: PASS; `git diff -- data`: пустой после возврата тестового `data/tasks.json` и удаления созданного пустого lock.
- Полный тест использовал синтетическую изолированную директорию. Реальные Ozon/API, credentials, owner database и бот не запускались.

## Архитектурная оценка

Минорное расширение существующего persistence слоя. Новый конкурентный repository/service pipeline не вводился; транзакции остаются во владении `PlanningWorkspaceRepository`. Database schema выросла до v6, старые payload readers и schema 1–4 сохранены. Поскольку добавлена durable storage schema и несколько новых контрактов, требуется независимый архитектурный review до PR merge.

## Следующий этап

W18: сохранять/открывать exact calculation, cost, tariff и quantity версии без источникового I/O; refresh должен создавать новую ревизию.
