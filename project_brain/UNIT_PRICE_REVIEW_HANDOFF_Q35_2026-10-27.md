# Review handoff: калькулятор прибыли с единицы — Q35

Дата: 27.10.2026

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

- Полный изолированный Windows/Python 3.12 `pytest`: **3983 passed in 53.74s**.
- Повторный профиль шести Q30/UI модулей в реализации: **56 passed in 2.60s**.
- Q31 связанный профиль: **1374 passed across 175 modules**; bounded checks: **3 passed**.
- `python -m compileall -q app`, `git diff --check`: PASS; `data/` diff основной реализации пустой.
- Exact implementation-head GitHub Verify прошёл: run `40573748055`; финальный проверенный PR-head snapshot `483cd4d1` также прошёл Verify `40574423459`, Windows/Linux full verification и Docker build/runtime smoke. После текущего документирования статуса нужно сверить CI нового документационного HEAD.

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
