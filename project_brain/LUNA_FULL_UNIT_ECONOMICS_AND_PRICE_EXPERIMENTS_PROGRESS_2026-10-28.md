# Журнал: расширенная экономика SKU и ценовые эксперименты

Дата: 28.10.2026.
ТЗ: LUNA_FULL_UNIT_ECONOMICS_AND_PRICE_EXPERIMENTS_TASK_2026-10-28.md.
Статус: NOT_STARTED. Реализация W00–W39 не начиналась.
База подготовки: main 9315046cf29c9e8c68da1cab027cb2568040f142 (PR #719 и #720 merged).
Ветка подготовки: codex/full-unit-economics-experiments-spec-20261028.
Аудит подготовки: FULL_UNIT_ECONOMICS_AND_PRICE_EXPERIMENTS_AUDIT_2026-10-28.md.

## Resume

- Следующий этап: W00.
- Implementation branch и её HEAD: ещё не созданы; при старте перепроверить фактический main и spec PR.
- Production bot, Ozon API, .env и owner database не использовались.
- Новые режимы экономики/эксперимента пока не реализованы; описанные схемы и acceptance — требования.
- Прежние Q00–Q35 и исправления R1–R8 находятся в main; не переоткрывать их как новую реализацию.
- Архитектурные решения новой программы принимаются на W03 и фиксируются как реализованные только после изменений.

## Этапы

| Этап | Зависимости | Статус | Фактический результат / проверки |
|---|---|---|---|
| W00 | — | NOT_STARTED | — |
| W01 | W00 | NOT_STARTED | — |
| W02 | W01 | NOT_STARTED | — |
| W03 | W01,W02 | NOT_STARTED | — |
| W04 | W03 | NOT_STARTED | — |
| W05 | W03,W04 | NOT_STARTED | — |
| W06 | W05 | NOT_STARTED | — |
| W07 | W05 | NOT_STARTED | — |
| W08 | W05 | NOT_STARTED | — |
| W09 | W06,W07,W08 | NOT_STARTED | — |
| W10 | W09 | NOT_STARTED | — |
| W11 | W03,W10 | NOT_STARTED | — |
| W12 | W07,W11 | NOT_STARTED | — |
| W13 | W11,W12 | NOT_STARTED | — |
| W14 | W06,W11 | NOT_STARTED | — |
| W15 | W13,W14 | NOT_STARTED | — |
| W16 | W15 | NOT_STARTED | — |
| W17 | W03,W10 | NOT_STARTED | — |
| W18 | W16,W17 | NOT_STARTED | — |
| W19 | W18 | NOT_STARTED | — |
| W20 | W19 | NOT_STARTED | — |
| W21 | W17,W19 | NOT_STARTED | — |
| W22 | W16,W21 | NOT_STARTED | — |
| W23 | W22 | NOT_STARTED | — |
| W24 | W22,W23 | NOT_STARTED | — |
| W25 | W24 | NOT_STARTED | — |
| W26 | W24,W25 | NOT_STARTED | — |
| W27 | W26 | NOT_STARTED | — |
| W28 | W20,W27 | NOT_STARTED | — |
| W29 | W28 | NOT_STARTED | — |
| W30 | W10,W18 | NOT_STARTED | — |
| W31 | W24,W25,W30 | NOT_STARTED | — |
| W32 | W29,W31 | NOT_STARTED | — |
| W33 | W20,W32 | NOT_STARTED | — |
| W34 | W33 | NOT_STARTED | — |
| W35 | W34 | NOT_STARTED | — |
| W36 | W35 | NOT_STARTED | — |
| W37 | W36 | NOT_STARTED | — |
| W38 | W37 | NOT_STARTED | — |
| W39 | W38 | NOT_STARTED | — |

## Правила записи результата этапа

Статусы: NOT_STARTED, IN_PROGRESS, VERIFIED_EXISTING, DONE, BLOCKED. BLOCKED содержит конкретное внешнее условие и независимую работу, которую можно продолжить. VERIFIED_EXISTING допустим только при доказательстве, что существующая реализация полностью удовлетворяет приёмке.

Для каждой записи:

1. Дата, этап, branch/base/code SHA, входной контракт.
2. Реальные изменения и paths, результат/изменённое поведение.
3. Новые regressions, точные команды и exit/result; старое зелёное CI не переносится.
4. Окружение и изоляция, owner data status.
5. Непроверенные источники и ограничения.
6. Следующий этап и необходимость business decision, если есть.

## Регистр источников и решений

| Вопрос | Текущее состояние | Где разрешается |
|---|---|---|
| Retained cohort / exact return-to-sale quantity | Не подтверждён для нового режима | W01–W03,W07,W12 |
| Вся реклама и SKU allocation | CPC и account totals нельзя складывать; новый coverage contract ещё не реализован | W02,W05,W06 |
| Дополнительные услуги против base fees | Требуется disjoint ownership | W05,W08 |
| TaxService и extra gross profit | Сохранить существующую политику; numeric oracle обязателен | W11,W13 |
| Единый active SKU guard | Observation guard существует; experiment integration ещё не реализована | W17,W21 |
| Maturity/30 units/7 days | Операционные ограничения модели, не статистическая гарантия | W22,W27,W28 |

## Подготовка ТЗ

- Прочитаны существующие roadmap, реестр возможностей, архитектурные решения, scenario/tax/returns/planning/observation contracts.
- Подготовлены 40 этапов с dependency graph и 18 групп acceptance.
- Offline проверки подготовки прошли: 40 уникальных упорядоченных стадий, ациклический граф, exact match зависимостей task/journal и 40 NOT_STARTED, 18 acceptance groups, 58 существующих опорных путей. Устаревшая ссылка period_profit_service.py заменена на действующий period_profit_query_service.py до публикации.
- Numeric oracles через существующий pure canonical calculator: base profit 46.00; USN income 40.00; income с points20 — 41.20; income-minus-expenses — 39.10; candidate95/ads7 — 46.50. Дополнительные расходы в этих проверках арифметически сведены к сумме затрат только как oracle, это не будущая реализация подмены поля cost. Loss pool=350, extra/unit=5 и weighted200/110=1.82 проверены Decimal.
- git diff --check прошёл; git diff -- data пустой. Новых code/tests нет; branch подготовки содержит только документацию. CI этой документационной ветки будет привязан к опубликованному SHA.
- Полный pytest не выполнялся для новой реализации: она не начиналась. Проверки подготовки не закрывают этапы W00–W39.
