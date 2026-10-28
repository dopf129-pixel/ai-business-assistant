# Журнал: помощник выбора цены по прибыли с единицы

Дата подготовки: 26.10.2026.
Задание: `LUNA_PRICE_PROFIT_PER_UNIT_TASK_2026-10-26.md`.
Статус: SPEC_PREPARED; реализация Q00–Q35 не начата.

## Исходная точка

- Main после PR #718: `07a84b5d7a9ffa7d0007947e0d8d4e9032052e01`.
- ТЗ подготовлено в отдельном чистом worktree, ветка `codex/price-profit-per-unit-spec-20261026`.
- Основной Desktop checkout с существующими изменениями/данными не редактировался.
- Выполнена предметная сверка существующих price/tariff/source/plan/observation contracts; runtime-код не изменялся.
- Принятые решения: цель ₽/шт. после учтённых расходов; seller price; тарифы по диапазонам с обязательным ручным fallback; гипотеза изменения ДРР отделена от наблюдений.
- Текущие ставки конкретного SKU не подтверждены. 14%/20% из старой публикации не использовать как defaults.
- Обнаруженное ограничение факта: существующий SKU-report/CPC attribution не доказывает полный учёт всех расходов. ТЗ разделяет сценарий, модель по наблюдавшимся входам и сопоставимый canonical факт.
- Зафиксировано canonical ROUND_HALF_UP: в synthetic N01 при цене 95 ₽ и ДРР 16,5% реклама 15,68 ₽, прибыль 12,27 ₽; пороги равенства и строгого улучшения различаются.

## Карта этапов

| Этап | Статус | Результат / проверки |
|---|---|---|
| Q00 | NOT_STARTED | — |
| Q01 | NOT_STARTED | — |
| Q02 | NOT_STARTED | — |
| Q03 | NOT_STARTED | — |
| Q04 | NOT_STARTED | — |
| Q05 | NOT_STARTED | — |
| Q06 | NOT_STARTED | — |
| Q07 | NOT_STARTED | — |
| Q08 | NOT_STARTED | — |
| Q09 | NOT_STARTED | — |
| Q10 | NOT_STARTED | — |
| Q11 | NOT_STARTED | — |
| Q12 | NOT_STARTED | — |
| Q13 | NOT_STARTED | — |
| Q14 | NOT_STARTED | — |
| Q15 | NOT_STARTED | — |
| Q16 | NOT_STARTED | — |
| Q17 | NOT_STARTED | — |
| Q18 | NOT_STARTED | — |
| Q19 | NOT_STARTED | — |
| Q20 | NOT_STARTED | — |
| Q21 | NOT_STARTED | — |
| Q22 | NOT_STARTED | — |
| Q23 | NOT_STARTED | — |
| Q24 | NOT_STARTED | — |
| Q25 | NOT_STARTED | — |
| Q26 | NOT_STARTED | — |
| Q27 | NOT_STARTED | — |
| Q28 | NOT_STARTED | — |
| Q29 | NOT_STARTED | — |
| Q30 | NOT_STARTED | — |
| Q31 | NOT_STARTED | — |
| Q32 | NOT_STARTED | — |
| Q33 | NOT_STARTED | — |
| Q34 | NOT_STARTED | — |
| Q35 | NOT_STARTED | — |

## Проверки подготовки документа

Реализация и pytest для неё не запускались: изменяется только документация.

- Однократная read-only проверка структуры: 36 уникальных упорядоченных этапов Q00–Q35, полная ациклическая dependency table, все 36 строк NOT_STARTED в журнале, 13 групп приёмки N01–N13 — PASS.
- Проверено существование 25 перечисленных source/document paths — PASS.
- Шесть примеров прибыли/рекламы и три примера комиссии пересчитаны прямым вызовом существующих чистых `UnitPriceScenarioService` и `TaxService` с `tax_mode=NONE` — PASS. Примеры взвешенной агрегации и разных баз ДРР проверены Decimal-арифметикой — PASS.
- Проверка выполнялась Python 3.12 из ранее изолированного venv с `-B`, без запуска приложения, записи storage и сетевых запросов. Новый тестовый файл не добавлялся.
- Проверки `git diff --check` и полного `git diff --cached --check` прошли; staged diff содержит только шесть Markdown-файлов задания/журнала/указателей.
- `DECISIONS.md` не менялся: архитектурная реализация ещё не начата. CHANGELOG/CURRENT_STATE/ROADMAP/TEST_MAP ссылаются на новый план, не объявляя его готовым функционалом.
- Старый exact-head CI PR #718 является доказательством базы, не проверкой будущей реализации. CI документального PR отслеживается отдельно.

## Следующее действие / resume

1. Прочитать ТЗ, AGENTS и актуальные project-brain contracts.
2. Начать Q00: проверить фактический main/HEAD, выбрать безопасный implementation worktree/ветку и записать базу.
3. Перейти к Q01/Q02, затем двигаться по dependency table.
4. После каждого этапа обновлять эту таблицу и дописывать точные команды/результаты ниже.

## Записи исполнения

Пока отсутствуют.
