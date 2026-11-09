# FIFO review blockers — журнал FR00–FR31

Подготовлено 08.11.2026, редакционная проверка 09.11.2026. Этапы FR00–FR12 выполнены; далее FR13.

ТЗ: [LUNA_FIFO_REVIEW_BLOCKERS_COMPLETION_TASK_2026-11-08.md](LUNA_FIFO_REVIEW_BLOCKERS_COMPLETION_TASK_2026-11-08.md).

## Resume

- Текущий этап FR13 NOT_STARTED: FR12 завершён. Для смешанного basis частичный возврат использует owner-approved latest-allocation-first convention; подробности записаны ниже. Следующий шаг — собственный CSV parser physical sales поверх durable evidence API.
- Worktree: C:\Users\gelashvilee\.codex\worktrees\daily-readiness-foundation\Ai ассистент.
- Ветка: codex/fifo-review-rate-replay-20261108 (создана от опубликованной головы #730 `8e6b528c462c322b78b0c5e1d82fb782f4bbeab4`).
- Current implementation HEAD after FR12: `7e0f44b4ac50c7144a2dc329afd256e63553b154` (`Add durable FIFO transition evidence API`).
- Базовый HEAD FR00: 0de5522d162b70c569d9272b8e217f524bd4ff67. Corrections checkpoint FR01: `49442244cbad9f679455562196c7b47b74790b6b`; отдельный task/progress documentation commit: `8e6b528c462c322b78b0c5e1d82fb782f4bbeab4`. FR02 red-test checkpoint: `461d8056b803f80244e757453163f9865757dd76`.
- PR #728 открыт: head 5b4f85881301b8d5b4a7977d67fa59e13d2647db, base main d8d4ba00c85acf14ba9a960f56a755fbe30b555c; PR #729 открыт: head 7abf5d79d608bf377f79df3b425b50d73de4d81c, base #728; PR #730 открыт: head 0de5522d162b70c569d9272b8e217f524bd4ff67, base #729. Проверено через GitHub metadata 2026-11-09.
- На FR00 baseline 17 tracked review-correction files были сохранены и зафиксированы отдельным FR01 checkpoint; первоначальный staged state был пуст. Реализация FR02–FR12 находится в отдельных проверенных commits. Существующий `.fl12-deps/` сохраняется вне Git.
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
| FR03 | DONE | Создан `FR03_CONTRACTS_2026-11-08.md`, добавлен узкий Decision 066 addendum и red-test map; Decimal MR01–MR15 + canonical TaxService checks PASS. |
| FR04 | DONE | Добавлены typed boundary DTOs и stable `TransitionReasonCode`; strict money/digest/nullable-balance/date/timezone/proof validation. Legacy allocation API unchanged. Linked pure suite: **70 passed, 2 replay cases excluded because FR05–FR06 are next**. |
| FR05 | DONE | Pure kernel: MR01–MR07 and linked allocator/replay profile: **77 passed, 2 replay-adapter cases deselected**; compileall and diff-check PASS. |
| FR06 | DONE | Store-local temporal ordering, exact/local-date boundaries, bounded ambiguity analysis, stable duplicate/permutation fingerprints; **86 passed in 1.39s** across temporal replay and legacy allocator/replay profiles. |
| FR07 | DONE | Schema v16; additive tables/indexes/FK/immutable guards/quotas; local migrations and replay profile 104 passed. |
| FR08 | DONE | Multi-rate repository adapter; linked FIFO profile **134 passed in 7.34s**, compileall/diff/data-manifest PASS; implementation checkpoint `c2b4ce2b7cc020a6ed9232d1e152289a5ab486f8` |
| FR09 | DONE | Public MR01–MR03; exact prefix replay; complete bridge for lower stock; atomic rate/reconciliation/allocation/projection; **136 passed in 7.79s** |
| FR10 | DONE | Owner latest-allocation-first policy; MR04–MR06 linked profile 142 passed; compile/diff/data manifest PASS; checkpoint `5534917c0f14dbed6610e084dd7d3d839862b13d` |
| FR11 | DONE | History/current/export/Period Profit сверены по полным replay revisions; FR11 profile **79 passed in 4.66s**; saved-plan restart regression PASS |
| FR12 | DONE | Typed bridge-evidence and confirmation APIs; **133 passed in 10.53s** on linked profile; exact data manifest preserved |
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

## FR12 — 2026-11-09

- Реализация добавлена поверх уже существующей схемы v16, без новой миграции: `TransitionBridgeEvidence`/`TransitionEvidenceConfirmation` задают allowlist по каждому виду доказательства, типы дат/digest/количеств, проверку полноты по пагинации и coverage, owner/source compatibility, предел event set 100,000 и лимиты размера.
- `FifoCostRepository.append_transition_bridge_evidence` вычисляет content fingerprint, шифрует весь sensitive payload существующим tenant Fernet provider и атомарно добавляет exact scoped evidence + новую case revision с CAS/idempotency. Нет ключа — нет записи. Лимиты одного физического документа, total ciphertext и версий проверяются до вставки и SQL append transaction; данные не обрезаются.
- `confirm_transition_evidence` связывает typed confirmation с точным evidence fingerprint, owner/scope, case revision и допустимым confirmation kind, проверяет decrypt/key, записывает immutable confirmation и case revision. Чтение evidence возвращает только allowlisted metadata и подтверждения; ciphertext не раскрывается. При недоступном ключе сохранённый факт остаётся с явным blocker и не подтверждается.
- `read_transition_preview` извлекает только заданный `preview_id` из точного tenant/store/SKU/case scope. Проверяет hash и binding preview row к сохранённым ревизиям/снимкам; расчёт не повторяет. Новое evidence переводит READY в AWAITING_EVIDENCE и оставляет прежний seal доступным как исторический, уже не-current.
- Тесты: `tests/test_fifo_cost_transition_bridge_evidence.py` и существующие v16/schema, transition store/service/atomic apply, multi-rate history/current/Period Profit/CSV and saved-plan restart regressions — **133 passed in 10.53s**. Изменённые Python modules `compileall` PASS; `git diff --check` PASS; `git diff --exit-code -- data` PASS. Пять user-data SHA-256 совпали с FR00; `.fl12-deps/` осталась неотслеживаемой и не stage.
- Использованы только synthetic `tmp_path` SQLite и временные Fernet keys. Владелец/его данные, реальные Ozon/Telegram, merge/deploy и запуск бота не затрагивались. Полный pytest и exact-head CI относятся к FR30.
- Code commit: `7e0f44b4ac50c7144a2dc329afd256e63553b154` (`Add durable FIFO transition evidence API`).
- Следующий этап FR13: фиксированный UTF-8 CSV physical-sales parser; не распознавать произвольный XLSX и не менять legacy cost CSV route.

## FR08 — 2026-11-09

- Реализация: `app/services/fifo_cost_repository.py` загружает ограниченную полную цепочку active rates, исключая отменённые ставки; проверяет последовательность, дату каждой границы, exact predecessor reconciliation, complete-through bridge/cutoff mapping и matching physical-sale rows. Неполные доказательства блокируют replay. `app/services/fifo_cost_replay_service.py` сохраняет derived rate lineage в формате allocation line. Репозиторий валидирует все active rate IDs, пишет schema-v16 остатки по каждой ставке и читает projection после нового экземпляра.
- Source fingerprint расширяет полный proof bundle только при multi-rate цепочке. Для no-rate/single-rate путь сохраняет старую форму и прежний fingerprint, чтобы не делать существующие allocation revisions stale после обновления.
- Добавлен `tests/test_fifo_cost_repository_multi_rate_replay.py`: положительный synthetic MR01–MR03 chain проверяет COGS 92.30 / 1614.20 / 166.00 ₽, остатки 0 / 0 / неизвестно, persisted linkage и готовность publication guard. Negative regressions: отсутствующая reconciliation, неполная cutoff mapping и новая mapping revision после preview (stale append не пишет строки).
- Проверка на изменённом коде: `tests/test_fifo_cost_repository_multi_rate_replay.py`, `test_fifo_cost_allocation_repository.py`, `test_fifo_cost_rate_service.py`, `test_fifo_cost_temporal_rate_replay.py`, `test_fifo_cost_replay_service.py`, `test_fifo_cost_transition_schema_v13.py`, `test_fifo_cost_late_entry_reconstruction_service.py`, `test_fifo_cost_transition_atomic_apply.py`, `test_fifo_cost_return_repository.py` — **134 passed in 7.34s**. `compileall` для двух изменённых сервисов — PASS; `git diff --check` — PASS.
- Data manifest до/после: history `520E8E1F25B2BB5C7F2A9E48B8CD6B0F8DCF9B0EA021CE622366F88BDE44E08C`; profiles `8F9E51A4545AC897A5F0324200BEAC5281428A6B248CA60A7049AD44BF5F0D51`; tasks `6D852D707927A617DFE3B23CB32AA580EC558272D40FB346B57ABF030868142F`; tax `F8EB3295F353060EAE6568A60F43E5B06DE66432AE64B8711C3F9E2BC42004BD`; users `2D289F298EB3E66EB0E65FE5A20E7F1A7A520A0845A4FD6F27FB15017BC51BE2`. `git diff -- data` пустой. `.fl12-deps/` не изменялась и не добавлялась.
- Ограничение: synthetic repository fixture создаёт rate/reconciliation/mapping rows напрямую для изоляции adapter boundary; создание новых ставок через публичные application methods — критерий FR09. Реальные данные владельца и внешние API не использовались. Следующий шаг — FR09.
- Итоговый code/docs checkpoint FR08: `c2b4ce2b7cc020a6ed9232d1e152289a5ab486f8` (`Connect FIFO repository multi-rate replay`). Рабочее дерево чистое, кроме заранее существующей неотслеживаемой `.fl12-deps/`; она не включена в commit.

## FR09 — 2026-11-09

- Реализация: `preview_cost_rate_change` выполняет prefix replay по выбранной store-local effective date для каждого изменения после первой ставки. Prefix replay требует полного exact-SKU cutoff mapping, фильтрует продажи, возвраты и non-sale outflows по локальной дате и отсекает будущие rate boundaries. Полный end-of-period остаток больше не используется для утверждения прошлой границы.
- Снимок с меньшим количеством допускается только при объяснении полного мостового интервала подтверждёнными продажами, non-sale outflows и saleable returns. Неподтверждённая/неполная причина или временная метка блокирует изменение; необъяснённое уменьшение возвращает `FIFO_RATE_STOCK_DISCREPANCY`.
- Public regression `test_fr09_replays_three_rates_from_prefix_and_publishes_atomically` проходит MR01–MR03 через `FifoCostRateService.preview_new_cost/confirm_new_cost` без SQL-вставки новых ставок. Инъекция ошибки после записи allocation rows доказывает rollback rate/reconciliation/allocation/projection; успешное повторное подтверждение читает текущую полную ревизию из нового repository instance. Финальный COGS по дням: 92.30 / 1614.20 / 166.00 ₽, сумма 1872.50 ₽. Проверка отдельно отвергает необъяснённое падение остатков.
- Временная проекция при транзакции ставит только новую ревизию/fingerprint/неполный флаг; она не публикует остаток из другого горизонта. После полного candidate replay в той же транзакции вычисляются и публикуются exact finite balances, известная стоимость/количество и следующий FIFO unit cost. До commit все записи атомарны.
- Проверка после последней правки: связанный профиль FR04–FR09, 9 файлов — **136 passed in 7.79s**. `compileall` трёх изменённых Python-файлов — PASS; `git diff --check` — PASS; `git diff --exit-code -- data` — PASS. Пять файлов `data/` совпадают с FR00 hashes. `.fl12-deps/` оставлена существующей, не изменена и не включена.
- Использованы только synthetic SQLite в `tmp_path`; реальные данные владельца, Ozon/Telegram, deployment и запуск бота не трогались. Изменение ещё не опубликовано; exact-head CI не запускался. Следующий шаг — FR10: разрешить temporal replay возвратов из rate-derived sales и подтвердить точное lineage, outflow и Return COGS isolation.

## FR10 — initial implementation checkpoint, 2026-11-09

- Реализация в `fifo_cost_repository.py`, `fifo_cost_return_restock_service.py` и `fifo_cost_allocation_service.py`: исходная стоимость возврата теперь читается из обычных layer allocation lines и rate-derived allocation lines; mixed-basis полный возврат восстанавливает каждую базу точно; rate-derived basis сохраняется при последующей продаже. Частичный возврат допускается, если у продажи одна точная исходная база. Превышение остатка возврата отклоняется. Непродажный outflow остаётся отдельным от sales COGS.
- Первоначальный безопасный вариант поддерживал полный mixed-basis return и однозначный single-basis partial return; неоднозначный mixed-basis partial возврат был закрыт fail-closed. На этом промежуточном checkpoint связанный профиль дал **141 passed**.
- Владелец позднее выбрал автоматическое правило «последние списанные FIFO-единицы возвращаются первыми». Это решение сняло blocker и зафиксировано в [FIFO contract](FIFO_COST_CONTRACTS_2026-11-06.md), [FR03 contracts](FR03_CONTRACTS_2026-11-08.md) и FR10 requirement.

## FR10 — завершение по owner-approved политике, 2026-11-09

- Реализация в `fifo_cost_repository.py`, `fifo_cost_return_restock_service.py` и `fifo_cost_allocation_service.py`: исходная стоимость возврата читается из обычных layer allocation lines и rate-derived allocation lines; при mixed-basis partial return назначаются последние оригинальные allocation lines первыми. Ранее возвращённые количества вычитаются из этой же обратной очереди по стабильному layer/rate basis identity. Полный return сохраняет исходный порядок allocation lines. Rate-derived basis сохраняется при последующей продаже.
- Регрессии: MR04 возвращает 1 из двух R2 units продажи MR02 по 16 ₽; MR05 продаёт восстановленную единицу за COGS 16 ₽ без изменения COGS предыдущих продаж. Повторные partial returns исчерпывают R2, затем переходят к R1. Полный return через разные ставки сохраняет 7×16 ₽ + 3×18 ₽. Over-return блокируется. Non-sale outflow остаётся вне sales COGS. Обновлён прежний тест, закреплявший блокировку mixed-basis partial return.
- Связанный профиль из 10 FIFO suites: **142 passed in 9.07s**. `compileall` всех затронутых Python-файлов, `git diff --check`, `git diff --exit-code -- data` и five-file FR00 SHA-256 manifest — PASS.
- Checkpoint `5534917c0f14dbed6610e084dd7d3d839862b13d` (`Apply latest FIFO basis to partial returns`).
- Это synthetic local verification, не full-suite/current-head CI. Owner case remains `SOURCE_BLOCKED`; реальные данные владельца, Ozon/Telegram запросы, бот, deploy и merge не использовались. Следующий этап — FR11.

## FR11 — потребители нескольких ставок, 2026-11-09

- `FifoCostHistoryService` теперь читает finite-layer и per-rate balances только из одной полной, актуальной allocation revision с совпадающим stream revision и cutoff. После движений статический `prior_rate_units` отображается как исторический остаток на границе, а текущая стоимость выбирается по пересчитанному FIFO остатку; open rate сохраняет неизвестное количество. Неполная/устаревшая rate-balance часть блокирует current-unit значение.
- Нулевой доказанный residual ставки сохраняется и показывается как `0`, но не становится next-unit layer. Regression проверяет, что следующей остаётся последняя open rate.
- Экран истории явно различает подтверждённое количество на границе ставки и остаток после полного replay. CSV добавляет отдельный столбец replay-остатка и помечает подтверждённые rate transitions как `RATE_BOUNDARY`, а не как покупку. Неизвестный остаток открытой ставки остаётся пустым.
- `tests/test_fifo_cost_repository_multi_rate_replay.py::test_fr11_history_current_cost_export_and_period_profit_use_replayed_rates` сверяет после fresh repository instance историю, текущую цену, экспорт и Period Profit: rate остатки `0, 0`, open rate `18.00 ₽` с unknown quantity, allocation revision одна и та же, COGS `1872.50 ₽`. MR04/MR05 повторно проверяют историю после возврата и перепродажи; возвратная единица 16 ₽ расходуется раньше открытой ставки 18 ₽.
- Старые adapter fixtures без доказанного cutoff bridge больше не ожидают материализации статической ставки: они проверяют `FIFO_RATE_REPLAY_REQUIRED` и отсутствие второй сохранённой ставки. Это сохраняет strict cutoff контракт; production replay guard не ослаблялся.
- Связанный профиль из history/current adapter/multi-rate repository/Period Profit/Telegram CSV и frozen-plan restart suites: **79 passed in 4.66s**. `compileall`, `git diff --check` и `git diff --exit-code -- data` прошли. SHA-256 до/после совпал с FR00: `history.json=520E8E1F25B2BB5C7F2A9E48B8CD6B0F8DCF9B0EA021CE622366F88BDE44E08C`; `profiles.json=8F9E51A4545AC897A5F0324200BEAC5281428A6B248CA60A7049AD44BF5F0D51`; `tasks.json=6D852D707927A617DFE3B23CB32AA580EC558272D40FB346B57ABF030868142F`; `tax_configuration.json=F8EB3295F353060EAE6568A60F43E5B06DE66432AE64B8711C3F9E2BC42004BD`; `users.json=2D289F298EB3E66EB0E65FE5A20E7F1A7A520A0845A4FD6F27FB15017BC51BE2`.
- Код/docs checkpoint: `0baae8ce` (`Use replayed balances in FIFO readers`). Все тестовые базы находятся в `tmp_path`; `.fl12-deps/` сохранена как исходная untracked папка и не включена. Owner-case remains `SOURCE_BLOCKED`; live Ozon/Telegram, бот, deployment, merge и exact-head CI не использовались. Следующий этап — FR12.

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

## FR03 — 2026-11-09

- Создан `project_brain/FR03_CONTRACTS_2026-11-08.md`: typed boundary DTOs, date/timezone rules, stable failure codes, one-kernel replay invariants, repository schema v16, N/N+1 application contract, public service relationships, privacy/quota bounds, independent arithmetic and verification gates.
- `project_brain/DECISIONS_066.md` получил узкий append-only addendum: temporal boundaries materialize only proven predecessor residual; source/cutoff gate and owner blocking remain unchanged. `TEST_MAP.md` lists FR02 red-baseline cases without representing them as passing CI. `CURRENT_STATE.md` now records execution and branch state.
- Independent `Decimal` arithmetic passed for MR01–MR07/MR12–MR15; direct existing canonical `TaxService.calculate` passed NONE, USN income, USN income-minus-expenses and minimum-tax checks. TaxService unchanged. No pytest run in FR03; it is a contracts/doc stage.
- Existing `data/` manifest from FR00 remains the baseline; no task mutated owner data. No real APIs, DBs, or bot run.

## FR04 — 2026-11-09

- `app/services/fifo_cost_allocation_service.py`: immutable `FifoRateBoundaryEvent` validates IDs, Decimal money, digest and first-vs-later residual/finite balance nullability. `app/services/fifo_cost_replay_service.py`: immutable `FifoDatedRateBoundaryEvent` validates exact timestamp offset or date-only local-end boundary, valid IANA zone and matching evidence fingerprint.
- `TransitionReasonCode` now includes the fixed stable replay/evidence failure codes. No replay algorithm, DB schema, production wiring, or source gate changed in FR04.
- Tests: pure allocation+temporal DTO and existing replay profiles **70 passed, 2 deselected** (only MR02/MR03 behavior awaiting FR05/FR06); `compileall` on changed modules PASS. Test fixtures are pure/in-memory, no SQLite or live source.
- Follow-up: integrate `rate_boundaries` into the pure kernel in FR05, then temporal sorting in FR06. Existing single-rate callers must remain green.

## FR05 — 2026-11-09

- `FifoCostAllocationService.allocate` now accepts typed rate boundaries in its already-proven event order. A later boundary must name the exact active predecessor and reconcile the finite queue; only the independently confirmed predecessor residual becomes a derived finite balance at the queue tail. No synthetic receipt/arrival event is emitted, and the new active rate remains quantity-unknown.
- Sale/outflow allocation now carries `basis_kind` and `rate_change_id` internally. Closed-rate returns restore an exact finite unit at the return position with original cost and origin-sale lineage, before the currently open rate. Outflows still consume finite layers only. Per-rate balances expose `None` for the current open rate.
- `tests/test_fifo_cost_temporal_rate_replay.py` adds pure MR01–MR07 controls, chain/finite-balance conflicts, rate-return/re-sale lineage, outflow separation, and unknown-open-quantity behavior.
- Linked pure kernel + existing allocator/replay tests: **77 passed, 2 deselected in 1.30s** (only FR06 chronological adapter tests). `compileall` and `git diff --check` PASS. No SQLite, owner data, live API or bot used.
- FR05 does not claim temporal ordering: caller event order must already be proven. Next: FR06 integrates dated boundaries into the bounded event-order analysis.

## FR06 — 2026-11-09

- `FifoCostReplayService.preview` now accepts bounded dated rate boundaries, a store IANA timezone and `complete_through`; no rate boundaries means the existing input/output contract remains unchanged. Exact timestamps are converted to store-local dates before cutoff/horizon comparisons. `END_OF_LOCAL_DATE` boundaries sort after every event on that local day and before the next local day.
- Rate boundaries and sale/return/outflow events now share one proof-ordered stream passed into the FR05 pure allocator. Exact same-instant ties and mixed date-only/timestamp days use the existing bounded ambiguity analysis; different boundary proofs at the same position conflict. Identical duplicate pages collapse, conflicting duplicate event IDs and repeated distinct sale identities fail closed.
- The preview fingerprint seals timezone, complete-through and canonical rate-boundary set; output exposes per-rate remaining balances, basis kind and rate IDs. No creation timestamps or host timezone participate in ordering.
- Added FR06 checks for MR08–MR10: same-local-day sale, UTC/local date crossing with `America/Los_Angeles`, ambiguous exact-instant sale/boundary, duplicate/permutation stability, and incomplete source horizon.
- Temporal + legacy allocator/replay suites: **86 passed in 1.39s**. `compileall`, `git diff --check`, `git diff --exit-code -- data` PASS; all five tracked user-data hashes match FR00. No SQLite, live API or bot process used.
- FR07 schema migration follows as the next dependent stage.

## FR07 — 2026-11-09

- FIFO schema moved from v15 to v16 in the existing `FifoCostRepository`; `PRAGMA user_version` and Planning schema remain untouched. Added append-only transition evidence, exact evidence confirmations, and allocation rate-balance tables with scoped foreign keys, idempotency/uniqueness, query indexes, and generated update/delete guards.
- Database constraints enforce the task allowlists and data bounds: metadata ≤256 KiB, confirmation JSON ≤64 KiB, physical documents ≤50,000 rows/16 MiB ciphertext, per-case evidence ≤100 versions/64 MiB encrypted payload. Composite foreign keys bind evidence to owner/tenant/store/case and each confirmation to the exact evidence/hash/owner/scope; no plaintext evidence fallback is possible because ciphertext is required. New table columns are included in repository schema validation.
- Historical migration tests now assert schema v16. The v12 fixture removes objects introduced after v12; the v15→v16 regression removes only new tables, seeds and snapshots a v15 confirmation, then verifies successful migration. An injected index failure proves all new DDL and version updates roll back.
- Schema/migration tests and prior FR04–FR06 replay suite: **104 passed in 2.78s** on implementation commit `43e6d5e5`; touched-file `compileall`, `git diff --check`, and `git diff --exit-code -- data` passed; five owner-data SHA-256 values still match FR00. Test databases use `tmp_path`; no owner DB/files, live API or bot were used.
- Implementation commit: `43e6d5e5` (`Add FIFO transition evidence schema v16`). `.fl12-deps/` remains untracked/unstaged.
- Next: FR08 repository adapter for the existing proven multi-rate replay kernel.
