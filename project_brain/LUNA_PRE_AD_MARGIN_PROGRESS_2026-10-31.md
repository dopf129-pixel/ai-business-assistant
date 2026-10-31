# Журнал: маржа SKU до рекламы

Дата подготовки: 31.10.2026. ТЗ: `LUNA_PRE_AD_MARGIN_TASK_2026-10-31.md`. Аудит: `PRE_AD_MARGIN_AUDIT_2026-10-31.md`.

База подготовки: `aad70b572b7f3bc37aaf79df302abe2eaa8b87d8`, проверенный PR #722. Ветка ТЗ: `codex/pre-ad-margin-spec-20261031`. Подготовка документации не является реализацией MA00–MA29.

## Resume

- MA00 DONE: PR #721/#722/#723 открыты, их базы/head сверены; создана отдельная `codex/pre-ad-margin-implementation-20261031` от точной головы ТЗ `34007a9b229092b6d54f6194d6037b50f23b2d1c`. До изменений дерево было чистым; `data/tasks.json` SHA-1 `7fcef9d518b4dd2be4b3bb6fd307b93474f6b215`, lock отсутствовал. См. `PRE_AD_MARGIN_MA00_BASELINE_2026-10-31.md`.
- MA01–MA04 DONE: зафиксированы current/historical/scenario consumers, исторический add-back boundary и versioned `pre_ad_margin` v1 contract. Исходный профиль **89 passed in 1.74s**; hashes owner data неизменны. Подробности в `PRE_AD_MARGIN_AUDIT_2026-10-31.md` и Decision 051.
- MA05 DONE: добавлена additive `pre_ad_margin` v1 canonical no-ad projection; при неизвестной рекламе before доступен, legacy after-ad result остаётся unavailable; internal no-ad zero не попадает во входы. Crossdock + extended guard сохранён, partial-проекция исключает crossdock и маркирует его unknown. Final linked profile **313 passed in 4.83s**; исходные данные чистые и hash совпадает. См. audit §MA05.
- MA06 DONE: добавлен `advertising_tax_bridge` v1 с T0/T1, рекламным расходом, эффектом `T0−T1` и проверкой равенства после рекламы. Покрыты `NONE`, USN income, USN income-minus-expenses и минимум; `calculate_components_only` не вызывает tax per SKU, SalesMix сохраняет aggregate единственный вызов. Linked profile **315 passed in 4.97s**; owner data hash unchanged.
- MA07 VERIFIED_EXISTING: закреплены seller-price denominator до points, отдельное налоговое влияние баллов, нулевая и out-of-range цена, подтверждённые нулевые расходы, отрицательная прибыль и каноническое округление. Точечный Windows профиль: **56 passed in 0.81s**; `data/tasks.json` hash сохранён, lock отсутствует. Подробности: audit §MA07.
- MA08 DONE: `expense_scope` явно разделяет включённые, исключённые и неизвестные расходы; постоянные общие расходы явно вне SKU contribution, source-confirmed zero storage больше не отображается как UNKNOWN, loss pool возврата показан отдельной категорией, а base-owned, рекламные и window-return компоненты нельзя второй раз подать как generic additional. Старый guard cross-docking supplied-unit + sales-unit extension сохранён. Linked Windows профиль: **359 passed in 5.12s** на 17 модулях; пользовательские данные не изменились. См. audit §MA08.
- MA09 DONE: percent/absolute/unknown/zero/above-price, конфликтующие payloads, CPC reconciliation и credit semantics проверены. Регрессия нашла падение при отрицательном абсолютном расходе; canonical scenario и components-only теперь fail closed для after-ad, сохраняя доступную независимую before-ad проекцию. Linked Windows profile: **378 passed in 5.34s** across 18 modules; commit `b2d4a043`. User data hash unchanged.
- MA10 DONE: current provider/query expose additive `pre_ad_margin` v1 without changing legacy current profit/margin. Partial unknown expense scope and actual-ad UNKNOWN are explicit; seller-price/current-finance/cross-dock periods are separately labeled. Linked Windows profile after metadata allowlist regression: **401 passed in 6.09s** across 21 modules; `py_compile` and `git diff --check` passed; user data hash unchanged.
- MA12 DONE: historical reconciliation adds back only complete CPC/CPO/OTHER amounts proven already included in an exact-SKU net for the same owner/store/product/offer/SKU/schema and accrual window. Tax from the existing historical query is preserved without a second calculation; Performance CPC, cohort/account/window amounts, additional ownership, incomplete ads and net credits are not added. The normal production source does not attach this evidence and remains UNAVAILABLE with a specific reason. Linked profile **156 passed**; owner-data hash unchanged. See Resume MA12.
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
| MA07 | MA06 | VERIFIED_EXISTING | Current calculator already uses seller price before discount points as margin denominator and canonical money rounding; tests prove the tax-basis point effect, zero/negative/out-of-range price handling, confirmed zero expense, negative profit, and half-cent rounding. Targeted Windows profile: 56 passed in 0.81s. Owner data hash unchanged; lock absent. |
| MA08 | MA05 | DONE | `expense_scope` now distinguishes included/excluded/unknown; fixed store overhead is explicitly outside SKU contribution; exact zero storage is represented as confirmed zero; strict cohort loss is labeled as return loss; base-owned, advertising and window-return components cannot be re-added as generic extras. The supplied-unit cross-docking incompatibility guard remains unchanged. Linked Windows profile: 359 passed in 5.12s across 17 modules; owner data hash unchanged and lock absent. |
| MA09 | MA06,MA08 | DONE | Percent/absolute/unknown/zero/above-price and mixed payloads covered; before-ad is invariant to the ad input. Fixed a confirmed crash for invalid negative absolute ad in canonical and components-only calculation; after-ad fails closed while before-ad remains available. CPC remains reconciliation-only and net credit remains REVIEW_REQUIRED. Linked Windows profile: 378 passed in 5.34s across 18 modules; commit `b2d4a043`; `data/tasks.json` unchanged. |
| MA10 | MA07,MA08,MA09 | DONE | Current query/provider attach additive `pre_ad_margin` v1 from existing current calculation values. Legacy profit/margin remain unchanged. Partial unknown scope, unknown advertising, required-input UNAVAILABLE and separate exact finance/cross-dock periods are tested. Linked Windows profile: 401 passed in 6.09s across 21 modules; compile/diff checks passed; owner data hash unchanged. |
| MA11 | MA10 | VERIFIED_EXISTING | Точный тариф применяется к каждой кандидатной цене из frozen bands; current-price rate не переносится на кандидат без покрытия. Если тарифа нет, кандидат остаётся недоступным до ручного ввода комиссии с provenance `manual_seller_assumption`. После ввода сохраняются цена, себестоимость и рекламный override. Linked Windows profile: 61 passed in 1.53s; output checkpoint `ca7f9183`. |
| MA12 | MA03,MA07,MA09 | DONE | Historical projection and strict evidence/ownership checks; N09–N12/N16, exact-SKU versus cohort, credit and query integration covered. Linked Windows profile: 156 passed in 2.83s; data/tasks.json hash unchanged. Production historical source remains unconnected, so normal projection stays UNAVAILABLE. |
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
- MA07 status: VERIFIED_EXISTING; see the next Resume section for numerical test evidence.

## Resume реализации MA07

- MA07 changed no production code: the existing canonical scenario already divides post-tax no-ad profit by seller price before discount points and preserves canonical Decimal money rounding.
- Added independent regressions for: seller-price denominator; points reducing the USN income tax base while remaining outside the margin denominator; zero, negative and out-of-range price handling; confirmed zero expenses; negative profit without clipping; and the half-cent money-rounding boundary.
- Verification: Windows focused profile `tests/test_pre_ad_margin_projection.py`, `tests/test_unit_price_scenario_extended_contract.py`, `tests/test_unit_price_scenario_service.py` — **56 passed in 0.81s**. `data/tasks.json` SHA-1 remains `7fcef9d518b4dd2be4b3bb6fd307b93474f6b215`; lock absent.
- MA08 completed with explicitly modeled exclusions and unknowns; storage, returns/cancellations, placement and unmapped categories remain unknown until confirmed by evidence. Next: MA09 advertising modes and incompleteness.

## Resume реализации MA08

- `UnitPriceScenarioService` now publishes disjoint `included_expense_keys`, `excluded_expense_keys` with reasons, `confirmed_zero_expense_keys`, and `unknown_non_ad_expense_keys`; numerical availability remains separate from scope completeness.
- Fixed store overhead is explicitly excluded from SKU contribution scope. Storage/placement/returns and unmapped expenses stay unknown unless the extended evidence names them. An explicit zero storage component is available as `STORAGE: 0.00` and is not mislabeled as missing. Strict return cohort loss is labeled once under `RETURN_LOSS_STRICT_COHORT`; it is not also shown in the generic additional pool.
- Extended components that repeat known base-owned keys (COGS, commission, logistics, last mile, acquiring), advertising, or return types reserved for the strict cohort model fail closed. The existing supplied-unit cross-docking + sales-unit extended guard remains. A linked consumer test showed an existing standalone cross-docking extension is supported; that path was preserved rather than over-rejected.
- Windows linked profile: **359 passed in 5.12s** across 17 modules including canonical scenario, return/additional evidence, pricing, mix/batch, observation, current economics and Telegram consumers. `data/tasks.json` SHA-1 remains `7fcef9d518b4dd2be4b3bb6fd307b93474f6b215`; lock absent.
- Next stage: MA09 advertising mode and incompleteness semantics.

## Resume реализации MA09

- MA09 input SHA: `90432fe6`; output commit: `b2d4a043`.
- `UnitPriceScenarioService._calculate_components` now preserves `advertising=None` for invalid absolute input rather than passing `None` to Decimal quantization. Both `calculate` and `calculate_components_only` leave after-ad unavailable, retain invalid-input diagnostics, and keep pre-ad independently available.
- `tests/test_pre_ad_margin_projection.py` proves before-ad profit/margin/tax invariant across percentage zero/nonzero, absolute zero/above-price, unknown, and invalid negative ad. Components-only path also stays fail-closed. `tests/test_unit_price_scenario_extended_contract.py` confirms mixed ad payload rejection does not suppress pre-ad.
- Existing `UnitEconomicsAdvertisingEvidenceService` remains unchanged: CPC is reconciliation-only; net negative ad credit remains preserved and marked `REVIEW_REQUIRED`.
- Verification: four-module targeted profile **78 passed in 1.08s**; final linked 18-module profile **378 passed in 5.34s**; `py_compile` and `git diff --check` passed. `data/tasks.json` SHA-1 remains `7fcef9d518b4dd2be4b3bb6fd307b93474f6b215`; lock absent. No live source requests.
- Next stage: MA10, current SKU card/provider/query integration. No live source requests.

## Resume реализации MA10

- MA10 input SHA: `b2d4a043` (MA09 complete). The additive current projection is built from the existing provider's already-calculated current values; no extra tax calculation or source request was introduced.
- `pre_ad_margin` v1 uses `basis=CURRENT_MODEL`, `tax_basis=CURRENT_TAX_POLICY`, seller revenue before points as denominator, and exactly the current result's per-unit profit/tax/margin. Advertising remains UNKNOWN/null. Expense scope names known per-unit COGS/commission/logistics/last-mile/acquiring and applicable cross-dock; storage, placement, return losses, unmapped expenses and unavailable cross-dock remain UNKNOWN; fixed store overhead is explicitly excluded. Numeric availability is independent of PARTIAL scope.
- The query carries exact requested accrual date bounds and observed-sales-day count, price observation timestamp, and whitelisted cross-dock period/coverage/denominator. The current response now renders its existing note, distinguishing the recent accrual window from the 56-completed-day supplied-unit cross-dock average and warning that storage/returns/other expenses are not confirmed.
- `tests/test_current_unit_economics_integration.py` proves exact parity with existing values (96 ₽ price, 33.45 ₽ profit, 34.84%, tax 5.76 ₽), seller-price denominator under buyer-price tax policy, partial scope, unknown advertising, zero/unknown cross-dock and separate periods, missing price UNAVAILABLE, and visible mixed-period/incompleteness note.
- Linked Windows profile: **401 passed in 6.09s** across 21 modules including current provider/query, current source/production wiring, Telegram UI/runtime, expense evidence, scenario/grid/solver/mix. `py_compile` and `git diff --check` passed. `data/tasks.json` SHA-1 unchanged at `7fcef9d518b4dd2be4b3bb6fd307b93474f6b215`; lock absent.
- Next: MA11 — arbitrary planned price with candidate-specific tariff and current overrides. Keep current verified commission from carrying to a different price; use existing manual fallback only as an explicit assumption.

## Resume реализации MA11

- Input SHA: `7b21710ca99a6f9266f6d2f00c748350954d0f9d` (MA10 complete). MA11 uses existing `_prepare_tariff`/frozen-profile resolution and canonical scenario calculation; no tariff lookup or calculation path was replaced.
- MA11 output code/docs checkpoint: `ca7f9183` (`Verify pre-ad margin at planned prices`).
- Existing comparison regression proves candidate prices 99.99/100.00/100.01 ₽ resolve to 11/11/22% respectively from a frozen profile, use one snapshot and one tariff-profile read, and applying 100.01 ₽ retains its matching 22% commission, 120 ₽ COGS and explicit 0% ad override.
- Added `test_manual_commission_at_candidate_price_preserves_price_cost_and_advertising`: an existing current-price commission becomes unavailable at 100.01 ₽ when no candidate tariff is known; before-ad margin is unavailable until manual commission is entered. Manual 22% is tagged `manual_seller_assumption`; chosen price 100.01 ₽, manually edited COGS 25 ₽ and 8% advertising remain intact. Canonical outputs: before-ad −6.79 ₽/−6.79%, after-ad −14.79 ₽/unit.
- Extended the frozen-range test to assert selected-candidate before-ad projection and its own commission expense: 100.01 ₽ candidate, 22% fee, −101.79 ₽/−101.78% before-ad, with prior cost and advertising inputs retained.
- Verification command: `pytest -q tests/test_unit_price_scenario_telegram_runtime.py tests/test_unit_price_tariff_snapshot_adapter.py tests/test_telegram_unit_price_tariff_profile_runtime.py` — **61 passed in 1.53s** on Windows. One initial numeric assertion used an incorrect hand sum; canonical output showed −101.79 ₽/−101.78%, assertion was corrected and the complete profile rerun green.
- No production code changed in MA11; no live source calls. The data/tasks.json hash was rechecked during MA12 and remains unchanged. MA11 code/docs commit `ca7f9183`; checkpoint follow-up `6604dd0b`. Next: MA13 candidate-price grid and comparison.

## Resume реализации MA12

- Input SHA: `6604dd0be30995f9ab4d102f308efa751b99690c` (MA11 checkpoint complete).
- Added `ProductUnitEconomicsHistoricalPreAdMarginService`, a separate projection service. It preserves historical net and tax and adds back only complete, exact-SKU CPC/CPO/OTHER financial ads proven as `BASE_ALREADY_INCLUDED` in that same net. The check requires the same owner/store/product/offer/SKU/schema and exact accrual dates; an additional, account, cohort, window-allocation or reconciliation-only amount cannot be used. Corrections are consumed from the normalized financial group once. A net advertising credit requires review. Performance CPC is never read by this calculation.
- The existing advertising resolver now reports `financial.exact_sku_attribution_complete`; a complete cohort snapshot is explicitly not exact evidence for one SKU. Current production historical source does not attach the full evidence/identity envelope, so the normal query returns `UNAVAILABLE` with `HISTORICAL_ADVERTISING_EVIDENCE_NOT_CONNECTED`; legacy historical fields and current/model route are unchanged.
- N09 synthetic result: revenue 3,000 ₽; source net after tax 645 ₽; already-included financial ads 360 ₽ after a 40 ₽ correction; tax 135 ₽ copied from the existing historical query result and marked with explicit provenance; historical before-ad 1,005 ₽ / 33.50 ₽ per unit / 33.50%; after-ad 645 ₽ / 21.50 ₽ per unit / 21.50%. Separate Performance CPC of 359.98 ₽ is not added.
- Added regressions for N10 incomplete CPO, N11 recorded-tax versus scenario tax basis (34.10 ₽ remains tied to 3.90 ₽), N12 zero/unknown denominators, N16 additional ownership/correction double count, negative net ad credit, cohort versus exact SKU, store/window mismatches, public historical query integration and ordinary production-source unavailable behavior.
- Linked Windows profile: **156 passed in 2.83s** across 9 related modules. `py_compile` and `git diff --check` passed. `data/tasks.json` SHA-1 before/after: `7fcef9d518b4dd2be4b3bb6fd307b93474f6b215`; no lock was created. No live Ozon/Telegram requests.
- Changed code/tests/docs: historical projection service, query integration, exact-SKU flag in ad resolver, 2 test modules, changelog/current state/test map/Decision 051/audit/journal. Code/docs checkpoint: `57595c440f0a0e1146671caf022d23de4c63db0f` (`Add strict historical pre-ad margin projection`). Final related profile, `py_compile`, `git diff --check` and data hash are recorded above.
- Next: MA13. Do not relax evidence requirements to make a historical value appear available.
