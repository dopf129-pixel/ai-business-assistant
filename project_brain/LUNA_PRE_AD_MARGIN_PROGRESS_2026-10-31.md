# Журнал: маржа SKU до рекламы

Дата подготовки: 31.10.2026. ТЗ: `LUNA_PRE_AD_MARGIN_TASK_2026-10-31.md`. Аудит: `PRE_AD_MARGIN_AUDIT_2026-10-31.md`.

База подготовки: `aad70b572b7f3bc37aaf79df302abe2eaa8b87d8`, проверенный PR #722. Ветка ТЗ: `codex/pre-ad-margin-spec-20261031`. Подготовка документации не является реализацией MA00–MA29.

## Resume

- MA00 DONE: PR #721/#722/#723 открыты, их базы/head сверены; создана отдельная `codex/pre-ad-margin-implementation-20261031` от точной головы ТЗ `34007a9b229092b6d54f6194d6037b50f23b2d1c`. До изменений дерево было чистым; `data/tasks.json` SHA-1 `7fcef9d518b4dd2be4b3bb6fd307b93474f6b215`, lock отсутствовал. См. `PRE_AD_MARGIN_MA00_BASELINE_2026-10-31.md`.
- MA01–MA04 DONE: зафиксированы current/historical/scenario consumers, исторический add-back boundary и versioned `pre_ad_margin` v1 contract. Исходный профиль **89 passed in 1.74s**; hashes owner data неизменны. Подробности в `PRE_AD_MARGIN_AUDIT_2026-10-31.md` и Decision 051.
- MA05 DONE: добавлена additive `pre_ad_margin` v1 canonical no-ad projection; при неизвестной рекламе before доступен, legacy after-ad result остаётся unavailable; internal no-ad zero не попадает во входы. Crossdock + extended guard сохранён, partial-проекция исключает crossdock и маркирует его unknown. Final linked profile **313 passed in 4.83s**; исходные данные чистые и hash совпадает. См. audit §MA05.
- MA06 DONE: добавлен `advertising_tax_bridge` v1 с T0/T1, рекламным расходом, эффектом `T0−T1` и проверкой равенства после рекламы. Покрыты `NONE`, USN income, USN income-minus-expenses и минимум; `calculate_components_only` не вызывает tax per SKU, SalesMix сохраняет aggregate единственный вызов. Linked profile **315 passed in 4.97s**; owner data hash unchanged.
- Продолжить MA07: seller revenue denominator до points, проценты/округление/zero/null, отрицательная прибыль и bounds.
- Подтверждено владельцем: before-ad после налога и прочих расходов, процент от общей выручки продавца до вычета баллов.
- Новый отдельный before-ad расчёт не требует известной рекламы; неизвестный after-ad остаётся неизвестным.
- Сценарий использует налог при нулевой рекламе; historical add-back сохраняет налог исходного периода. Основания не смешиваются.
- Сохранить canonical calculator/TaxService, legacy outputs/history, W42–W44 guards и crossdock denominator restriction.
- Реальные Ozon/Telegram запросы, запуск бота, merge и deploy запрещены. Итог исполнения — готовый PR с зелёным CI текущего SHA и независимым review packet.

## Этапы

| Этап | Зависимости | Статус | Фактические результаты |
|---|---|---|---|
| MA00 | — | DONE | PR #721/#722/#723 сверены; отдельная implementation branch создана от точного spec head; чистое исходное дерево; data/tasks.json SHA-1 `7fcef9d518b4dd2be4b3bb6fd307b93474f6b215`, lock отсутствовал. См. `PRE_AD_MARGIN_MA00_BASELINE_2026-10-31.md`. |
| MA01 | MA00 | DONE | Карта current/history: текущая модель уже без рекламы, но expense scope неполон; historical ads source не подключён. Профиль базы 89 passed. См. audit §MA01. |
| MA02 | MA00 | DONE | Зафиксированы canonical scenario inputs, ad requirement, TaxService, extended expense gate и grid/mix/experiment consumers. Профиль базы 89 passed. См. audit §MA02. |
| MA03 | MA01,MA02 | DONE | Exact-SKU financial-ad resolver существует, но не подключён к history query; Performance CPC reconciliation-only. Исторический add-back без доказанного inclusion недоступен. См. audit §MA03. |
| MA04 | MA01,MA02,MA03 | DONE | Аддитивный versioned `pre_ad_margin` v1 и backward compatibility закреплены Decision 051. N01–N20 остаются acceptance oracle. См. audit §MA04. |
| MA05 | MA04 | DONE | `UnitPriceScenarioService` добавил no-ad branch, не меняющий исходные inputs и legacy calculated profit/margin; extended unavailable branch выдаёт только partial subtotal; crossdock guard не ослаблен. Целевой профиль 47 passed; связанный профиль 313 passed. |
| MA06 | MA05 | DONE | `advertising_tax_bridge` фиксирует T0/T1 и `after = before − ad + (T0−T1)` с delta 0.00; N01/N04/min-tax/NONE. `calculate_components_only` оставлен без TaxService; SalesMix aggregate-tax-one-call тест зелёный. Linked profile 315 passed. |
| MA07 | MA06 | NOT_STARTED | — |
| MA08 | MA05 | NOT_STARTED | — |
| MA09 | MA06,MA08 | NOT_STARTED | — |
| MA10 | MA07,MA08,MA09 | NOT_STARTED | — |
| MA11 | MA10 | NOT_STARTED | — |
| MA12 | MA03,MA07,MA09 | NOT_STARTED | — |
| MA13 | MA11 | NOT_STARTED | — |
| MA14 | MA13 | NOT_STARTED | — |
| MA15 | MA10,MA11,MA12 | NOT_STARTED | — |
| MA16 | MA15 | NOT_STARTED | — |
| MA17 | MA16 | NOT_STARTED | — |
| MA18 | MA12,MA15 | NOT_STARTED | — |
| MA19 | MA13,MA17,MA18 | NOT_STARTED | — |
| MA20 | MA14,MA19 | NOT_STARTED | — |
| MA21 | MA20 | NOT_STARTED | — |
| MA22 | MA20,MA21 | NOT_STARTED | — |
| MA23 | MA17,MA22 | NOT_STARTED | — |
| MA24 | MA20,MA21,MA22 | NOT_STARTED | — |
| MA25 | MA06,MA07,MA08,MA09,MA12,MA14 | NOT_STARTED | — |
| MA26 | MA19,MA23,MA24,MA25 | NOT_STARTED | — |
| MA27 | MA26 | NOT_STARTED | — |
| MA28 | MA27 | NOT_STARTED | — |
| MA29 | MA28 | NOT_STARTED | — |

## Правила исполнения

1. По завершении этапа: дата, входной/выходной SHA, изменённые файлы, точный результат проверок и ограничения; обновить Resume.
2. Статусы: NOT_STARTED, IN_PROGRESS, DONE, VERIFIED_EXISTING, BLOCKED. VERIFIED_EXISTING требует доказательства приёмки; BLOCKED — внешнее условие, выполненные попытки и независимая работа, которую можно продолжить.
3. Неподтверждённый live источник не мешает доказать честное UNAVAILABLE поведение; он не превращается в полный результат. Owner acceptance остаётся отдельно.
4. Не переносить тестовый PASS между изменившимися версиями. Не скрывать сбои/пропуски. Сохранять исходные owner data hashes; восстанавливать только доказанные тестовые побочные файлы.
5. После сокращения контекста продолжить с первого незавершённого этапа с удовлетворёнными зависимостями.

## Проверки подготовки ТЗ

- Граф: **30 уникальных упорядоченных этапов**, все dependencies существуют и направлены назад, граф ацикличен. Task и journal полностью совпадают; все 30 статусов NOT_STARTED.
- **20 групп N01–N20**, 17 явно указанных repo-relative code/docs paths существуют; файлы task/journal/audit существуют.
- Числовые проверки через действующий UnitPriceScenarioService/TaxService: N01 до 33.50/после 21.50/налог 4.50; N03 after −86.50; N04 до 32.30/после 22.10, налог 5.70/3.90; N05 до 38.00/после 26.00. Отдельный legacy crossdock rate2 дал before 34.50, сочетание с incompatible extended scope осталось unavailable.
- Decimal-oracles historical add-back 645+360=1005; 33.50 ₽/шт. и 33.50%; historical tax basis N11 34.10 против no-ad 32.30; weighted aggregate 27.50% — PASS.
- Первый числовой запуск без Windows IANA database вернул EXTENDED_SCOPE_INVALID. Повтор с установленной локальной базой через PYTHONTZPATH прошёл; код/зависимости для этого не менялись.
- `git diff --check`: PASS. `data/tasks.json` hash `38637702206478ab3c08d7ae1c4ac87f1f1c6354` сохранён; lock отсутствует. Новые runtime tests не добавлены. Полный локальный pytest не повторялся для документационной подготовки; полный CI спецификации проверяется на её опубликованном SHA.

## Resume реализации MA05

- Код: текущая ветка `codex/pre-ad-margin-implementation-20261031`; текущий `pre_ad_margin` projection находится в `app/services/unit_price_scenario_service.py`.
- Регрессии: `tests/test_pre_ad_margin_projection.py`; сопутствующие numeric/tax assertions обновлены в `tests/test_unit_price_scenario_extended_contract.py`.
- Финальный профиль после последней правки **313 passed in 4.83s** охватил 15 существующих test modules. Первый вызов связанного профиля сослался на неверное имя Telegram test module и не запустил тесты; исправленный полный повтор с `test_unit_price_scenario_telegram_runtime.py` зелёный.
- `data/tasks.json` SHA-1: `7fcef9d518b4dd2be4b3bb6fd307b93474f6b215`; `data/tasks.json.lock` отсутствует.
- MA06 implementation: `app/services/unit_price_scenario_service.py`; numeric regressions в `tests/test_pre_ad_margin_projection.py` и `tests/test_unit_price_scenario_extended_contract.py`. Formula bridge additive; existing TaxService policy unchanged.
- Exact outputs: USN Income N01 T0=4.50/T1=4.50/pre=33.50/after=21.50; USN Income-minus-Expenses N04 T0=5.70/T1=3.90/pre=32.30/after=22.10/tax effect=1.80; minimum tax T0=T1=1.00; reconciliation delta=0.00. `NONE` remains zero tax.
- Final linked profile after MA06: **315 passed in 4.97s**; `data/tasks.json` SHA-1 remains `7fcef9d518b4dd2be4b3bb6fd307b93474f6b215`, lock absent.
- Next stage MA07: seller revenue denominator before points, zero/negative outputs, rounding and bounds.
