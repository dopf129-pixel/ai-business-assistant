# W39 — пакет независимого review

## Addendum: remediation review R1–R5, 30.10.2026

Пять подтверждённых замечаний исправлены и опубликованы в PR #722 коммитом `3dd56343ac29339e83d5fbcb4f8d563010876384`, на базе исходного code HEAD `762c5cd53359962a90fec6f8bdf512dc5dfdb246`. Exact-head Windows и full-verification CI успешно завершились в runs [41051047996](https://github.com/dopf129-pixel/ai-business-assistant/actions/runs/41051047996) и [41051054590](https://github.com/dopf129-pixel/ai-business-assistant/actions/runs/41051054590); full verification включает compile, полный suite, Docker build/smoke и SHA-bound report. Документирующий follow-up может обновить текущий PR SHA; перед повторным review проверить live CI на актуальной голове.

- **R1:** `COMPLETE` требует не только весь диапазон дат, но и complete evidence каждого сегмента/компонента.
- **R2:** история контрольных событий читается страницами максимум по 10, с проверкой offsets и общим пределом в 100 записей.
- **R3:** режим абсолютного расхода рекламы на единицу сохраняется в результате; не переинтерпретируется как процент.
- **R4:** при отсутствии полного снимка Telegram предлагает собрать 56 завершённых локальных дней; finance и FBO denominator сохраняются только при доказанной полноте. Partial/credit/unsupported данные не маркируются COMPLETE.
- **R5:** добавлен публичный Telegram маршрут от baseline к candidate: сбор, оценка, контрольные условия, завершение, сравнение и решение владельца. Сквозной синтетический тест подтверждает, что цена в Ozon не меняется.

Фактические проверки: связанный Windows профиль **127 passed in 6.60s**, полный Windows pytest **4,346 passed in 42.30s**. При первом полном запуске была задана неподходящая `AI_ASSISTANT_STORAGE_ROOT`, из-за чего падали 7 тестов относительных tenant-путей; штатный повтор без неё прошёл. Полный pytest создал временный `data/tasks.json.lock`; `data/tasks.json` восстановлен байт-в-байт из pre-run копии, lock удалён, итоговый `git diff -- data` пустой. `git diff --check` PASS.

Следующий шаг: проверить exact-head CI на последнем документирующем commit и пройти повторное независимое review. Live API, реальный бот, merge и deployment не запускались. Проверка владельцем на реальном SKU остаётся pending.

Дата: 30.10.2026
Статус: W39 engineering handoff завершён; remediation R1–R5 опубликована, code SHA `3dd56343ac29339e83d5fbcb4f8d563010876384` прошёл Windows/full-verification CI (runs `41051047996`, `41051054590`). Текущий PR HEAD мог обновиться последующим documentation-only commit; его checks нужно перепроверить live перед независимым review.
PR реализации: https://github.com/dopf129-pixel/ai-business-assistant/pull/722
Зависимость: PR #721, ветка `codex/full-unit-economics-experiments-spec-20261028`.
Ветка реализации: `codex/full-unit-economics-experiments-implementation-20261028`.
Base PR реализации: ветка спецификации PR #721.
Проверенный HEAD до текущего status-only docs-коммита: `b1b81592199348df40cdb6133b464f59fbe0768e`.

## Порядок интеграции

Это зависимый PR: сначала рассмотреть и включить спецификацию #721, затем реализацию #722. PR #722 не сливать отдельно в `main`, пока его base остаётся веткой спецификации. После разрешения зависимости проверить base/head и exact-head CI в GitHub заново. Этот этап не выполняет merge.

## Содержание и архитектурное влияние

Base-to-head diff относительно spec SHA `f76d2dd90e4298113c037278666532715974e4a8`: 126 файлов, 26,167 добавлений и 244 удаления; 57 коммитов. Классификация: **Architecture Review Required**.

Основные области:

- расширены planning-workspace contracts и репозиторий для versioned immutable expense snapshots, experiment/phase/result history, ownership guards, revisions, quotas и восстановления;
- добавлены нормализация расходов и доказательная проекция рекламных, возвратных и дополнительных расходов;
- сохранён единый canonical unit-economics forward path; режимы проходят через sensitivity, batch, mix и saved-plan consumers;
- добавлены bounded reference/window snapshots, readiness/maturity gates и консервативная candidate-price recommendation;
- добавлены state machine, owner confirmations, CAS/idempotency, experiment history и export;
- добавлены Telegram guided entry/history/export, owner runbook и numerical/concurrency/backup-restore acceptance.

Новая параллельная расчётная система не вводилась. Изменения расширяют существующий planning repository и price/unit-economics services; сохраняют TaxService, legacy сценарии и их result history. Подробные версии/переходы: `UNIT_ECONOMICS_W03_CONTRACTS_ARCHITECTURE_2026-10-28.md`, `UNIT_ECONOMICS_W17_EXPERIMENT_REPOSITORY_2026-10-29.md`, `UNIT_ECONOMICS_W21_STATE_MACHINE_ACTIVE_GUARD_2026-10-29.md` и migration/backup tests.

## Проверки

- Полный локальный Windows suite в disposable worktree, кодовый SHA `428e80cb9a3ada56af1b9aa21280f52d3dec3d64`, Python 3.12.10: **4,335 passed in 50.37s**, без skip/deselect.
- `python -m compileall -q app`: PASS.
- `python -c 'from database import create_tables; create_tables()'`: PASS.
- W35 N01–N18/cross-route profile: **667 passed in 16.53s**.
- W36 concurrency/resource profile: **64 passed in 4.36s**; четыре новые regressions **4 passed in 0.99s**.
- W37 backup/restore profile: **46 passed in 2.94s**.
- `git diff --check` относительно spec base после публикации: PASS.
- GitHub Verify exact HEAD `b1b81592199348df40cdb6133b464f59fbe0768e`: [run 40956765471](https://github.com/dopf129-pixel/ai-business-assistant/actions/runs/40956765471) — Windows full suite **success**, Linux full verification **success**, production Docker build и smoke **success**, SHA-bound report/artifacts generated. Для любого следующего commit проверять текущий SHA и checks live в PR #722.

Подробные команды, isolation environment и побочные эффекты: `UNIT_ECONOMICS_W38_FULL_VERIFICATION_2026-10-30.md`. Полный suite изменил `data/tasks.json`/lock только в disposable копии; данные source checkout не менялись. `.env`/секреты не читались; реальные Ozon/Telegram API и бот не вызывались.

## Контракты и ограничения источников

- Расходы сохраняют provenance, знаковость, coverage и различение missing/zero/credit/correction; CPC reconciliation не прибавляется к финансовому CPC повторно.
- Источники с неполной SKU-атрибуцией остаются account-level/unknown; они не распределяются на SKU молча. FBS и неподтверждённые поля явно unsupported/unverified.
- Возвратная/невыкупленная когорта и восстановленная себестоимость не объявляются фактом без evidence; pending disposition блокирует строгую оценку потери.
- Scenario/experiment/result/history используют scoped revisions; stale callbacks/decisions отклоняются; export проходит allowlist и bounded-size guards.
- Source audit документальный; live Ozon запросы не делались.

См. `UNIT_ECONOMICS_W02_OZON_API_CONTRACT_AUDIT_2026-10-28.md`, W05–W10 source evidence, W18–W29 evidence, privacy tests и W37 backup/restore acceptance.

## Известные ограничения и пользовательская приёмка

Два прежних инженерных блокера W31 (первый сбор полного 56-дневного reference snapshot и Telegram lifecycle candidate-фазы) исправлены и опубликованы в PR #722; детали и регрессии приведены в addendum выше и `UNIT_ECONOMICS_W40_REVIEW_REMEDIATION_2026-10-30.md`. Сбор сохраняет только snapshot с доказанной полнотой, а синтетический end-to-end путь не меняет цену в Ozon.

Исправления W40 имеют зелёный CI на code SHA `3dd56343ac29339e83d5fbcb4f8d563010876384`; перед повторным независимым review проверить, что документирующий commit на текущей голове PR также прошёл CI. Всё ещё требуется owner acceptance на настроенном магазине и реальном SKU. Проверка реального магазина, owner backup и runtime остаются pending и не заменяются synthetic tests. Не вводить вручную выкупы или неизвестные расходы. Owner guide: `UNIT_ECONOMICS_W34_OWNER_GUIDE_ACCEPTANCE_2026-10-29.md`.

Рекомендация сравнивает наблюдаемые сопоставимые условия и не доказывает причинность «цена вызвала рост конверсии/снижение ДРР». Maturity sample gate — инженерная защита, не статистическая гарантия.

## Независимый review checklist

На exact PR HEAD и с учётом #721 проверить:

1. **Схема и совместимость:** порядок миграций, старые plan/result readers, fail-closed future/corrupt payload, backup/restore; старые записи не пересчитываются и не теряются.
2. **Финансовая модель:** ownership компонентов, возвраты/невыкупы/корректировки, CPC overlap, missing против нуля, налог один раз, tariff boundary и единая canonical forward во всех consumers.
3. **Сопоставимость эксперимента:** confirmation timestamp/timezone, завершённые окна, maturity/quality, late evidence и correction revision, ties/incomparable results, отсутствие causal claims.
4. **Изоляция/конкурентность:** owner/store/SKU/schema guards, CAS, payload-hash idempotency, active experiment guard, rollback и stale callbacks.
5. **Ресурсы:** общий operation trace, retries/pages внутри лимитов, cancellation/429/retry, отсутствие обхода parent budget.
6. **Telegram/export/privacy:** UX недоступных источников, UTF-16 splitting, allowlist, pagination/quota, отсутствие секретов и идентификаторов.
7. **Проверки:** независимые numeric oracles N01–N18, cross-route/concurrency/restore suites, полный Verify всех платформ/контейнера на exact HEAD PR #722.
8. **Остаточные blockers:** W31 и owner/live acceptance показаны как ограничения, а не решённый функционал.

Авторский self-review, локальные проверки и exact-head CI зафиксированы; независимое review ожидает рецензента. Merge/deploy/live API/bot не выполнялись.
