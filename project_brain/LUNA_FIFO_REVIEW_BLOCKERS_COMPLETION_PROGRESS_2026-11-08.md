# FIFO review blockers — журнал FR00–FR31

Подготовлено 08.11.2026, редакционная проверка 09.11.2026. Выполнение задания ещё не начато.

ТЗ: [LUNA_FIFO_REVIEW_BLOCKERS_COMPLETION_TASK_2026-11-08.md](LUNA_FIFO_REVIEW_BLOCKERS_COMPLETION_TASK_2026-11-08.md).

## Resume

- Следующий этап FR03: оформить стабильные DTO/error/revision/migration contracts и addendum к Decision 066; затем идти FR04–FR11 на ветке PR A.
- Worktree: C:\Users\gelashvilee\.codex\worktrees\daily-readiness-foundation\Ai ассистент.
- Ветка: codex/fifo-review-rate-replay-20261108 (создана от опубликованной головы #730 `8e6b528c462c322b78b0c5e1d82fb782f4bbeab4`).
- Базовый HEAD FR00: 0de5522d162b70c569d9272b8e217f524bd4ff67. Corrections checkpoint FR01: `49442244cbad9f679455562196c7b47b74790b6b` (`Preserve FIFO review corrections checkpoint`); отдельный task/progress documentation commit: `8e6b528c462c322b78b0c5e1d82fb782f4bbeab4`.
- PR #728 открыт: head 5b4f85881301b8d5b4a7977d67fa59e13d2647db, base main d8d4ba00c85acf14ba9a960f56a755fbe30b555c; PR #729 открыт: head 7abf5d79d608bf377f79df3b425b50d73de4d81c, base #728; PR #730 открыт: head 0de5522d162b70c569d9272b8e217f524bd4ff67, base #729. Проверено через GitHub metadata 2026-11-09.
- Существуют 17 modified tracked-файлов review corrections без commit. Сохранить весь исходный diff. Staged state на входе FR00 был пуст.
- .fl12-deps/ — существующие untracked dependencies, не stage.
- Manifest data/ до и после целевых тестов (SHA-256): history.json `520E8E1F25B2BB5C7F2A9E48B8CD6B0F8DCF9B0EA021CE622366F88BDE44E08C`; profiles.json `8F9E51A4545AC897A5F0324200BEAC5281428A6B248CA60A7049AD44BF5F0D51`; tasks.json `6D852D707927A617DFE3B23CB32AA580EC558272D40FB346B57ABF030868142F`; tax_configuration.json `F8EB3295F353060EAE6568A60F43E5B06DE66432AE64B8711C3F9E2BC42004BD`; users.json `2D289F298EB3E66EB0E65FE5A20E7F1A7A520A0845A4FD6F27FB15017BC51BE2`. `git diff -- data` пустой, data status пустой. Не восстанавливать будущие пользовательские изменения из Git.
- Старый CI #730 на 0de5522d PASS; новые corrections им не покрыты. NOT READY TO MERGE.
- R-A production bridge/preview/apply и R-B multi-rate replay открыты.
- IMPLEMENTATION_VERIFIED=false; OWNER_CASE_VERIFIED=false.

## Этапы

| Этап | Статус | Проверка / SHA / результат |
|---|---|---|
| FR00 | DONE | 2026-11-09; ветка и SHA сверены; #728–#730 подтверждены открытыми через GitHub; полный исходный diff — 17 tracked files; исходно staged state пуст; manifest data снят. |
| FR01 | DONE | 2026-11-09; отдельный checkpoint `49442244cbad9f679455562196c7b47b74790b6b`; 7 FIFO/Telegram модулей существующих исправлений: **86 passed in 7.14s** с Python проекта и локальными зависимостями; manifest data до/после совпал. |
| FR02 | DONE | Добавлены temporal replay и production-workflow red regressions; baseline на старом коде: **6 failed in 1.28s** с ожидаемыми причинами — отсутствие rate-boundary DTO, evidence service injection и общей production factory/apply wiring. Тесты не помечены skip/xfail. |
| FR03 | IN_PROGRESS | Создать FR03_CONTRACTS_2026-11-08.md и узкий addendum к Decision 066, сохраняя существующий gate. |
| FR04 | NOT_STARTED | Typed boundaries |
| FR05 | NOT_STARTED | Allocation kernel |
| FR06 | NOT_STARTED | Temporal replay |
| FR07 | NOT_STARTED | Migration |
| FR08 | NOT_STARTED | Repository adapter |
| FR09 | NOT_STARTED | Rate commit/replay |
| FR10 | NOT_STARTED | Returns/non-sale |
| FR11 | NOT_STARTED | Readers/gateB |
| FR12 | NOT_STARTED | Typed evidence |
| FR13 | NOT_STARTED | Physical CSV |
| FR14 | NOT_STARTED | Durable confirmation |
| FR15 | NOT_STARTED | Telegram routing |
| FR16 | NOT_STARTED | Source snapshots |
| FR17 | NOT_STARTED | Cutoff/opening |
| FR18 | NOT_STARTED | Assembler/bridge |
| FR19 | NOT_STARTED | Reconstruction |
| FR20 | NOT_STARTED | Financial baseline |
| FR21 | NOT_STARTED | Impact |
| FR22 | NOT_STARTED | Prepare seal |
| FR23 | NOT_STARTED | Apply/restart |
| FR24 | NOT_STARTED | Production builder |
| FR25 | NOT_STARTED | Exact confirm UI |
| FR26 | NOT_STARTED | Consumers |
| FR27 | NOT_STARTED | Production E2E |
| FR28 | NOT_STARTED | Backup/fault/concurrency |
| FR29 | NOT_STARTED | Documentation |
| FR30 | NOT_STARTED | Full tests/current CI |
| FR31 | NOT_STARTED | Review package |

## Формат записи

Дата; этап; base/head SHA; изменённые функции; контракты; команда и среда проверки; фактический результат; original data manifest before/after; ссылки PR/CI; ограничения; следующий этап.

Старые результаты 110/5115 tests не являются проверкой нового кода. При подготовке этого ТЗ pytest и live API не запускались.

## Проверка подготовки ТЗ — 09.11.2026

- Статически проверены 32 уникальных этапа FR00–FR31, порядок зависимостей без циклов, 22 строки MR01–MR22 и локальные Markdown-ссылки.
- Независимые Decimal-контроли FIFO и налоговые примеры сверены с существующим чистым TaxService: NONE, USN_INCOME 6%, USN_INCOME_MINUS_EXPENSES 15% и minimum tax — PASS. Это проверка примеров документа, не тест новой реализации.
- Изменены только документы задания и указатели на них; реализация FR00–FR31 не начиналась. Code fixes предыдущего review остаются в исходном dirty состоянии.

## FR00–FR01 — 2026-11-09

- FR00: проверены AGENTS.md, CURRENT_STATE.md, DECISIONS.md, TEST_MAP.md, Decision 066, FL-task/progress, review packet, новое ТЗ; повторно сверены branch/HEAD и GitHub PR refs #728–#730. Полный tracked diff содержит ровно 17 заранее указанных исправленных файлов; `.fl12-deps/` оставлена нетронутой и unstaged; staged state пуст.
- FR00 data manifest SHA-256 до тестов: `history.json=520E8E1F25B2BB5C7F2A9E48B8CD6B0F8DCF9B0EA021CE622366F88BDE44E08C`, `profiles.json=8F9E51A4545AC897A5F0324200BEAC5281428A6B248CA60A7049AD44BF5F0D51`, `tasks.json=6D852D707927A617DFE3B23CB32AA580EC558272D40FB346B57ABF030868142F`, `tax_configuration.json=F8EB3295F353060EAE6568A60F43E5B06DE66432AE64B8711C3F9E2BC42004BD`, `users.json=2D289F298EB3E66EB0E65FE5A20E7F1A7A520A0845A4FD6F27FB15017BC51BE2`.
- FR01 целевые regression suites: `tests/test_fifo_cost_cutoff_bridge_service.py`, `tests/test_fifo_cost_transition_atomic_apply.py`, `tests/test_fifo_cost_transition_schema_v13.py`, `tests/test_fifo_cost_transition_service.py`, `tests/test_fifo_cost_transition_store.py`, `tests/test_telegram_fifo_cost_report_import_service.py`, `tests/test_telegram_fifo_cost_transition_runtime_service.py` — **86 passed in 7.14s**. Запуск использовал установленный проектный Python и `.fl12-deps`; каждый затронутый persistent-store test строит БД в `tmp_path`.
- Установка зависимостей не выполнялась. Первые два диагностических запуска выявили отсутствие pytest в глобальном Python и необходимость явно добавить `app`/`.fl12-deps` в sys.path; корректный повтор прошёл. SHA-256 всех файлов `data/` после тестов совпал побайтно с исходным manifest; `git diff -- data` пустой.
- Реальные owner DB/отчёты, Ozon, Telegram и запуск бота не использовались. Следующий шаг — отдельный commit ровно 17 corrections paths, после него отдельный commit новых TASK/PROGRESS документов.

## FR02 — 2026-11-09

- Добавлены `tests/test_fifo_cost_temporal_rate_replay.py` и `tests/test_fifo_cost_transition_production_workflow.py`. Они фиксируют требуемый public multi-rate replay для MR02–MR03, обзор exact durable evidence и отсутствие единой apply-capable factory/physical-document path.
- Baseline запуск: 6 tests failed in 1.28s по ожидаемым недостающим контрактам на исходном коде: нет typed rate-boundary event; `FifoCostTransitionReviewService` не принимает evidence service; `create_fifo_cost_transition_workflow` не существует. Это red-baseline этапа, не текущий passing CI.
- Положительный E2E и настоящие saved-document/confirmed-preview проверки будут доведены на FR12–FR27 без постоянных skip/xfail. FR02 tests пока не публиковались; для зелёного PR A production-only tests будут перенесены в PR B scope, а temporal tests останутся в PR A.
- Тестовые SQLite использовали только `tmp_path`; owner data manifest остался тем же. Live APIs и bot не использовались.
