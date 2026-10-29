# W39 — пакет независимого review

Дата: 30.10.2026
Статус: W39 приёмка выполнена; Verify зелёный на exact HEAD `dd9a5f26b35d61e18cb7a61de1f65e99afc124eb`. Этот статусный docs-коммит потребует повторного Verify на новом HEAD.
PR реализации: https://github.com/dopf129-pixel/ai-business-assistant/pull/722
Зависимость: PR #721, ветка `codex/full-unit-economics-experiments-spec-20261028`.
Ветка реализации: `codex/full-unit-economics-experiments-implementation-20261028`.
Base PR реализации: ветка спецификации PR #721.
Проверенный HEAD до этого статусного docs-коммита: `dd9a5f26b35d61e18cb7a61de1f65e99afc124eb`.

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
- GitHub Verify exact HEAD `dd9a5f26b35d61e18cb7a61de1f65e99afc124eb`: [run 40955833551](https://github.com/dopf129-pixel/ai-business-assistant/actions/runs/40955833551) — Windows full suite **success**, Linux full verification **success**, production Docker build и smoke **success**, SHA-bound report/artifacts generated. Следующее обновление статуса/evidence — docs-only и потребует ещё одного exact-head Verify после публикации.

Подробные команды, isolation environment и побочные эффекты: `UNIT_ECONOMICS_W38_FULL_VERIFICATION_2026-10-30.md`. Полный suite изменил `data/tasks.json`/lock только в disposable копии; данные source checkout не менялись. `.env`/секреты не читались; реальные Ozon/Telegram API и бот не вызывались.

## Контракты и ограничения источников

- Расходы сохраняют provenance, знаковость, coverage и различение missing/zero/credit/correction; CPC reconciliation не прибавляется к финансовому CPC повторно.
- Источники с неполной SKU-атрибуцией остаются account-level/unknown; они не распределяются на SKU молча. FBS и неподтверждённые поля явно unsupported/unverified.
- Возвратная/невыкупленная когорта и восстановленная себестоимость не объявляются фактом без evidence; pending disposition блокирует строгую оценку потери.
- Scenario/experiment/result/history используют scoped revisions; stale callbacks/decisions отклоняются; export проходит allowlist и bounded-size guards.
- Source audit документальный; live Ozon запросы не делались.

См. `UNIT_ECONOMICS_W02_OZON_API_CONTRACT_AUDIT_2026-10-28.md`, W05–W10 source evidence, W18–W29 evidence, privacy tests и W37 backup/restore acceptance.

## Известные ограничения и пользовательская приёмка

W31 guided flow реализован условно и проверен синтетически, но не даёт владельцу полного производственного первого запуска:

1. Приложение не собирает автоматически полный snapshot расходов за `56` завершённых дней.
2. В Telegram нет полного owner-пути создания и подтверждения candidate phase.

До закрытия ограничений не использовать мастер для реального решения об изменении цены. Не вводить вручную выкупы или неизвестные расходы. Owner guide: `UNIT_ECONOMICS_W34_OWNER_GUIDE_ACCEPTANCE_2026-10-29.md`. Проверка одного реального SKU, настроенного магазина, owner backup и runtime остаются pending, не заменяются synthetic tests.

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
