# Review handoff: калькулятор прибыли с единицы — Q35

Дата: 27.10.2026

## Статус независимого review — 2026-10-28

Независимый review выявил пять воспроизведённых замечаний. Исправления внесены в PR #720; предыдущие CI ссылки относятся к старым SHA и не подтверждают новую версию. Свежие локальные regressions прошли (**149 passed across eight modules**); полный изолированный suite — **3,990 passed in 49.21s**, `compileall` и `git diff --check` — PASS, `data/` основного checkout не изменён. Review-fix head прошёл GitHub Verify.

- R1: observation commission is resolved against its observed price using the frozen tariff snapshot; legacy point-only commission is not carried to a changed price, and completeness reports provenance.
- R2: Returns receives UTC instants corresponding to inclusive local calendar dates.
- R3: session-only tariff selection remains effective after freezing without overriding ambiguity among persisted profiles.
- R4: tariff target search accounts for rounded canonical profit, verifies candidate cents, and fails closed on its evaluation budget.
- R5: batch planning passes remaining shared calculation budget into each solver call and stops before additional source/solver calls once exhausted.

## Повторный review — исправления R6–R7 (2026-10-28)

- R6: одиночное редактирование, применение одной ставки рекламы к нескольким SKU и пересчёт целевой маржи теперь ограничивают поиск до вызова solver. Для multi-row действия остаток общего бюджета передаётся по строкам; неуспех из-за этого лимита отражается как `BUDGET_EXHAUSTED`.
- R7: подтверждённый тариф из result service теперь принимается качественным gate наравне с ручным тарифом. Проверка остаётся модельной (`verified=False`), а `UNKNOWN` продолжает давать `MODEL_TARIFF_BASIS_UNCONFIRMED`.
- Регрессии закрывают R6 edit/target/bulk paths и R7 подтверждённый/неизвестный provenance end-to-end. Связанный Windows/Python 3.12 профиль: **164 passed in 4.53s**. Изолированный полный pytest, публикация фикса в PR #720 и exact-head CI ещё не выполнены.

Проверенный review-fix commit: `bb0a8aea` (`Fix unit price review findings R1-R5`). Head `40a23315d74958cb7b7e427b785f730ea886ac79` включает документацию результатов и прошёл [Verify run 40654624761](https://github.com/dopf129-pixel/ai-business-assistant/actions/runs/40654624761): `success`, включая Windows/Python 3.12 и Linux full verification. Этот run относится к review-fix code head; предыдущие ссылки ниже относятся к первоначальной реализации.

## PR и порядок проверки

- Реализационный PR: [#720](https://github.com/dopf129-pixel/ai-business-assistant/pull/720).
- PR с утверждённым заданием: [#719](https://github.com/dopf129-pixel/ai-business-assistant/pull/719).
- #720 намеренно stacked на `codex/price-profit-per-unit-spec-20261026`; проверять и интегрировать нужно по порядку: сначала задание #719, затем реализацию #720. PR #720 не слит.
- Проверенный implementation head: `0154f857cd2600ad9879acf2084604ca4735449c`.
- GitHub Verify: [run 40573748055](https://github.com/dopf129-pixel/ai-business-assistant/actions/runs/40573748055) — `success` на этом exact head. Windows/Python 3.12, Linux full verification, Docker build/runtime smoke и SHA-bound report прошли. Verification artifact: [verification report](https://api.github.com/repos/dopf129-pixel/ai-business-assistant/actions/artifacts/12767520722).
- После этого опубликован documentation-only handoff commit. PR head `483cd4d1f4724e68a140a4b94aa4d6355a1e3ae6` прошёл [Verify run 40574423459](https://github.com/dopf129-pixel/ai-business-assistant/actions/runs/40574423459): all jobs SUCCESS, включая Windows, Linux full verification и Docker. Код/тесты после `0154f857` не изменялись.

## Что реализовано

- Конечный путь планирования цены по прибыли на единицу: ручной тариф комиссии с диапазонами, сравнение цены, целевая маржа/безубыточность, рекламная компенсация, сохранённые планы, наблюдения, качество и сравнение результатов, экспорты и Telegram-поток.
- Buyout estimate для конкретного FBO SKU берётся из FBO postings и Returns API. Модель принимает его только для полной выборки, финальных статусов, нуля неоднозначных отмен и согласованных количеств.
- Формула: `delivered / (delivered + confirmed customer non-buyout)`. Это наблюдаемая оценка за окно, а не показатель Ozon Analytics и не причинный эффект цены.
- Возвраты показываются отдельным числом. Расходы возвратов не вычитаются из модельной прибыли на единицу; CPC и FBO cohort имеют разные основания дат. В UI/результате эти ограничения видны.

## Проверки

- Полный изолированный Windows/Python 3.12 `pytest` на review-fix commit: **3,990 passed in 49.21s**.
- Повторный профиль шести Q30/UI модулей в реализации: **56 passed in 2.60s**.
- Q31 связанный профиль: **1374 passed across 175 modules**; bounded checks: **3 passed**.
- `python -m compileall -q app`, `git diff --check`: PASS; `data/` diff основной реализации пустой.
- Review-fix exact-head GitHub Verify `40654624761` passed on `40a23315`; Windows/Python 3.12 and Linux full verification succeeded. Initial implementation-head runs `40573748055` and `40574423459` predate review fixes.

## Основные review входы

- Требования и зависимости: `LUNA_PRICE_PROFIT_PER_UNIT_TASK_2026-10-26.md`.
- Исполнение/resume: `LUNA_PRICE_PROFIT_PER_UNIT_PROGRESS_2026-10-26.md`.
- Самопроверка и известные ограничения: `UNIT_PRICE_SELF_REVIEW_Q34_2026-10-27.md`.
- Финальный локальный прогон: `UNIT_PRICE_FINAL_VERIFICATION_Q33_2026-10-27.md`.
- Архитектурная политика расчёта выкупа: `DECISIONS_062.md`.
- Практическое описание владельцу: `UNIT_PRICE_PROFIT_PER_UNIT_USER_GUIDE_2026-10-27.md`.
- Regression inventory: `TEST_MAP.md` и Q30/Q31 acceptance.

## Review focus

1. Убедиться, что неполные/двусмысленные Returns и не финальные статусы блокируют buyout denominator.
2. Проверить сохранение owner/store/SKU boundaries и отсутствие raw Ozon IDs/rows в persisted/exported results.
3. Проверить explicit model-only labeling и то, что CPC/return cost не попадают в итог как подтверждённые суммы.
4. Проверить backward compatibility тарифов/планов, миграции и публичные Telegram callbacks.
5. Сверить exact-head CI artifact/report с PR head; локальные результаты не заменяют CI.

## Архитектурная классификация

`Architecture Review Required`: изменение связывает несколько сервисных слоёв, Telegram UI, planning persistence, source completeness/quality gates и экспорты; локальный финальный commit изменил 25 файлов. Архитектура расширена добавочно, существующие финансовые расчёты и shared Ozon client переиспользуются. Слияние, развёртывание и запуск реального бота не выполнялись.
