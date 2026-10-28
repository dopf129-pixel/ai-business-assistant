# W03 — контракты и архитектура расширенной экономики SKU

Дата: 28.10.2026
Ветка: `codex/full-unit-economics-experiments-implementation-20261028`
Входной HEAD: `80395612` (после W02)
База архитектуры: `main` `9315046cf29c9e8c68da1cab027cb2568040f142`, с уже существующими planning migrations до DB schema v5.
Статус: архитектурное решение принято для последовательной реализации W04–W37; runtime изменения этим этапом не заявляются.

## 1. Решения, которые ограничивают реализацию

1. `UnitPriceScenarioService` остаётся единственной моделью forward profit, а текущий `TaxService` — единственным исполнителем политики налога. Telegram, ranking, target search, batch и experiment не имеют своего расчётного дубля.
2. `PlanningWorkspaceRepository` остаётся единственным владельцем tenant SQLite schema, миграций, транзакций, CAS, idempotency, архивации и backup/restore. Запрещено создавать вторую БД/репозиторий под экономику или эксперимент.
3. Snapshot расходов — плановое evidence, не бухгалтерская запись. Источники, даты, полнота, область и ownership сохраняются отдельно; неустановленное значение не превращается в подтверждённый 0.
4. Эксперимент read-only к Ozon: бот никогда не устанавливает цену, не запускает сбор автоматически и не делает фоновые повторы. Владелец сам меняет цену и подтверждает фактическую цену/время.
5. Уникальность активного эксперимента использует существующую защиту активного наблюдения на `(owner, store, product, offer, SKU, sale_schema)`. В момент переключения baseline → candidate закрытие предыдущей активной фазы и запуск новой выполняются атомарно.
6. Два режима расходов сравниваются только внутри одинаковых моделей и совместимых scope: `WINDOW_COST_ALLOCATION` — расходы периода на выбранную явно базу единиц; `STRICT_RETAINED_COHORT` — только расходы и возвраты с доказанной связью с соответствующей когортой. Они не взаимозаменяемы и не входят в общий ranking.
7. `LEGACY` при отсутствующем extension contract сохраняет прежний результат байт-в-байт по смыслу. Он не получает автоматически статус расширенной полной модели.

Основания — существующие `DECISIONS_061.md`, `DECISIONS_062.md`, `DECISIONS_063.md` и решение 064. Новое решение уточняет контракт, но не отменяет утверждённые там price/tax/buyout/persistence semantics.

## 2. Versioned value contracts

Имена типов ниже нормативны для реализации, но это не готовые runtime classes. W05–W18 должны использовать строгую нормализацию; наружу нельзя передавать произвольные provider dictionaries.

### 2.1 `ExpenseSnapshotV1`

Один immutable агрегат одного точного owner/store/product/offer/SKU/sale-schema scope и одного source window.

```text
ExpenseSnapshotV1 {
  schema_version: 1,
  identity: { owner_id, store_id, product_id, offer_id, sku, sale_schema },
  source_window: { from_date, to_date, date_basis, timezone },
  received_at: ISO-8601 UTC timestamp,
  as_of: ISO-8601 timestamp or UNKNOWN,
  components: list[ExpenseComponentV1],
  coverage: { requested_days, observed_days, page_count, complete, stop_reason },
  source_revision: bounded opaque fingerprint,
  completeness: COMPLETE | PARTIAL | UNKNOWN | CONFLICT,
  model_scope: WINDOW_COST_ALLOCATION | STRICT_RETAINED_COHORT
}
```

Identity is exact: a missing dimension never matches another store/SKU/schema. Use current repository owner/store guards, not chat text alone. `timezone` is a valid IANA name or explicit `UNKNOWN`; never silently label UTC dates Moscow local dates.

### 2.2 `ExpenseComponentV1`

```text
ExpenseComponentV1 {
  schema_version: 1,
  component_key: bounded stable enum/string,
  category: COMMISSION | ACQUIRING | LOGISTICS | ADVERTISING_CPC |
            ADVERTISING_CPO | ADVERTISING_OTHER | STORAGE | PLACEMENT | CROSS_DOCKING |
            RETURN_NONBUYOUT | RETURN_INVENTORY_LOSS | OTHER_SERVICE,
  source: SELLER_FINANCE | PERFORMANCE | SUPPLY_ACT | DERIVED | OWNER_INPUT,
  source_method: bounded endpoint/version identifier,
  source_contract_version: bounded string or UNKNOWN,
  source_window: exact dates + date_basis + timezone,
  status: PRESENT | CONFIRMED_ZERO | MISSING | UNAVAILABLE | PARTIAL |
          CONFLICT | UNSUPPORTED | EXCLUDED | RECONCILIATION_ONLY,
  signed_source_amount_rub: Decimal string or null,
  normalized_expense_rub: non-negative Decimal string or null,
  numerator_amount_rub: Decimal string or null,
  denominator_units: non-negative integer or null,
  denominator_kind: RETAINED_UNITS_EXACT_COHORT | DELIVERED_UNITS_EXACT_COHORT |
                   ORDERED_UNITS_WINDOW | SOLD_UNITS_WINDOW | SUPPLIED_UNITS_CROSS_DOCKING |
                   POSTINGS | NONE | UNKNOWN,
  unit_amount_rub: Decimal string or null,
  attribution: EXACT_SKU | EXACT_COHORT | WINDOW_ALLOCATION | UNATTRIBUTED,
  ownership: BASE_INCLUDED | ADDITIONAL | RECONCILIATION_ONLY | UNKNOWN,
  origin: OFFICIAL_SOURCE | DETERMINISTIC_DERIVATION | OWNER_ASSUMPTION | UNVERIFIED_SOURCE,
  recurrence: RECURRING | ONE_OFF | UNKNOWN,
  correction_state: FINAL_AS_OF | CORRECTED_AS_OF | OPEN | UNKNOWN,
  dedup_policy: stable bounded policy key,
  included_reason: bounded enum/string or null,
  excluded_reason: bounded enum/string or null
}
```

All arithmetic uses finite `Decimal`, currency is RUB, and parsing rejects bool, NaN, Infinity, negative quantities, oversized values, malformed dates, duplicate JSON keys and unknown future schema. Normalized expense is a positive deduction magnitude; original Ozon signed amount remains unchanged for audit. Credits/reversals preserve signed source amount and are normalized by a deterministic, documented component rule. No amount or rate is computed when its required numerator/denominator is absent or the denominator is zero.

`CONFIRMED_ZERO` is legal only when the exact source query completed successfully, all pages/windows were read, identity and mapping were exact, and the relevant rows explicitly sum to zero. Otherwise use MISSING, PARTIAL, UNAVAILABLE, CONFLICT, or UNSUPPORTED with a reason. Duplicate identity is `(owner, store, source, transient operation id, stable subcomponent key)` during one collection. Same operation with two distinct service keys counts both. Same service key repeated with equal canonical values counts once. Same service key with conflicting amount/identity invalidates that component and snapshot completeness. Raw operation IDs are transient only.

### 2.3 `QuantityEvidenceV1`

```text
QuantityEvidenceV1 {
  schema_version: 1,
  identity: exact owner/store/product/offer/SKU/sale_schema,
  window: from/to/date_basis/timezone,
  ordered_units: integer|null,
  cancelled_units: integer|null,
  delivered_units: integer|null,
  confirmed_returned_units_from_deliveries: integer|null,
  retained_units: integer|null,
  supplied_units: integer|null,
  posting_count: integer|null,
  api_row_count: integer|null,
  source_coverage: per-source complete/partial/unavailable + cursor termination,
  attribution: exact enum,
  status: COMPLETE | PARTIAL | UNKNOWN | CONFLICT | UNSUPPORTED,
  source_revision: bounded opaque fingerprint
}
```

`posting_count` and `api_row_count` are diagnostics only, never unit denominators. The strict retained equation is `delivered_units - confirmed_returned_units_from_deliveries`, where the returns are proven to originate in those exact delivered posting/SKU units. Cancellation is not added to or subtracted from delivered units a second time. `retained_units <= 0`, returns greater than delivered, mismatched units, missing page completion, unknown return classification, or non-exact cohort yields no strict per-unit profit. `supplied_units` is exclusively the cross-docking denominator and is never relabelled as sold/retained units.

### 2.4 `ExtendedScenarioV1`

```text
ExtendedScenarioV1 {
  schema_version: 1,
  calculation_mode: LEGACY | WINDOW_COST_ALLOCATION | STRICT_RETAINED_COHORT,
  expense_snapshot_ref: safe revision/fingerprint or null,
  quantity_evidence_ref: safe revision/fingerprint or null,
  expense_policy_revision: bounded string,
  included_component_keys: sorted unique bounded list,
  excluded_component_statuses: bounded projection,
  numerator_and_denominator_basis: explicit enum pair,
  source_completeness: COMPLETE | PARTIAL | UNKNOWN | CONFLICT,
  assumed_inputs: explicit allowlisted metadata
}
```

`UnitPriceScenarioService.calculate(...)` gets only an optional versioned contract. Absent contract → unchanged legacy behavior. New modes feed gross expenses into the existing tax calculation before tax; they do not subtract extra expense after an already-calculated tax or profit. An unsupported tax rule returns an explicit incompatible result, not a second tax formula. Existing seller price/tariff/cost assumptions retain their frozen revisions.

### 2.5 Experiment, phase, result contracts

`PriceExperimentV1` exact identity includes owner/store/product/offer/SKU/schema and current experiment schema version. It stores metric `MAX_RUB_PER_UNIT`, selected calculation mode, frozen scenario/tax/cost/tariff/reference-snapshot revisions, 2–10 bounded candidate prices, positive threshold (default technical 0.01 RUB), planned phase duration (3–28 full local days; default 7), currency, control flags, `state`, independent `state_revision`, and creation/update timestamps. It does not store seller credentials, raw API objects, product names, raw posting/return ids, or every financial row.

`ExperimentPhaseV1` is immutable once activated and has a phase id/revision, kind BASELINE/CANDIDATE, segment number, confirmed seller price, owner-confirmed timestamp, first complete local date, exact frozen input refs, planned dates/duration, coverage and condition flags. Pause/restart creates a new segment with its own price/time confirmation; nonconsecutive segments are never joined into one evidence window.

`ExperimentResultV1` is append-only with independent `result_revision`, exact source as-of and snapshot refs, baseline/candidate profit RUB/unit, absolute delta, eligible candidate ids, quantity/window basis, quality gate matrix, limitations and model outcome. Result `status` is one of READY, WAITING_FOR_DATA, INSUFFICIENT_DATA, INCOMPARABLE, NO_CLEAR_DIFFERENCE, BETTER, WORSE, or TIE. These are outcome statuses, not experiment lifecycle states. The experiment lifecycle state stays at the review state until the owner selects a valid next step.

Every public object is allowlisted and size-bounded. JSON decimal values serialize as normalized finite decimal strings; identity and revision checks execute before any read or mutation.

## 3. Expense ownership and gate matrix

| Input | Source/status contract | Ownership / allowed use | Blocks strict mode when |
|---|---|---|---|
| Commission, acquiring, base delivery/logistics | Existing frozen scenario components and explicit finance evidence | `BASE_INCLUDED`; included exactly once by the canonical scenario | required tariff/source missing or conflicting |
| Financial CPC | Exact SKU/subcomponent accrual evidence when available | `BASE_INCLUDED` if canonical base already includes it; otherwise `ADDITIONAL` only under one frozen policy | posting is multi-SKU/ambiguous, coverage partial, or overlap unresolved |
| Performance CPC | Exact promoted SKU and report window only | `RECONCILIATION_ONLY` when finance CPC overlaps; becomes additive only after mutually exclusive scope is proven | SKU/campaign mapping, date scope, or overlap unknown |
| CPO/CPM/other ads | Explicit current report category and exact SKU mapping required | Additional only with confirmed mapping; otherwise `UNSUPPORTED/UNATTRIBUTED` | never silently zero-filled |
| Return/non-buyout financial operations | Exact source amount/subcomponent; matched posting and SKU for cohort use | Additional loss only once; status/return amount alone is not proof of delivered cohort linkage | unresolved posting, partial pagination, quantity conflict or unknown disposition |
| Return stock/COGS disposition | Existing owner-confirmed recovery/COGS evidence | Inventory loss/recovery is separate from return logistics; pending disposition stays pending | pending COGS is not zero; no speculative deduction |
| Storage/placement/other service | Exact SKU source and explicit operation map required | Additional only if no base overlap; account-level remainder remains unattributed | account-only or residual-only evidence |
| Cross-docking | Accepted-act/SKU quantity and net signed financial corrections in one compatible reference window | Existing cost per supplied unit only; separate `SUPPLIED_UNITS_CROSS_DOCKING` | no exact supply-to-SKU mapping, incomplete corrections, or zero denominator |
| Discount points | Existing exact-SKU weighted 28 completed local-day ratio/source contract | Frozen explicit assumption/reference used in scenario; preserve existing tax policy | partial window or invalid point/sale relationship |
| Analytics counts | Current seller entitlement and requested metric status | ordered units only if available; never substitute count of rows | absent no-Premium cancellations/returns/delivered do not imply zero/fact |
| Current seller price | Current product price response | Current snapshot/starting prompt only | never used as historical per-order price proof |

Strict expense applicability additionally requires complete pages, known date basis, exact identity, a valid numerator and denominator, stable duplicate handling, no conflict, and `ownership` that does not overlap another included component. A row excluded from profit remains visible as excluded/unknown with reason in detail projection. The displayed total contains included disjoint components only; do not include a reconciliation-only row or residual twice.

## 4. Experiment state transitions

State and outcome are separate. Every mutation requires exact owner/store/SKU/schema, `expected_state_revision`, action-specific allowlisted payload, and idempotency key/hash. Stale revision returns conflict without writes; exact replay returns the original outcome; same key with a different payload is rejected. An accepted transition increments `state_revision`; changed evidence/metadata appends a `result_revision` and never overwrites an older result.

| From | Action / gate | To | Atomic effects / failure rule |
|---|---|---|---|
| DRAFT | validate exact identity, frozen scenario, selected mode, candidates, plan window and finite quotas | READY | No source collection or active guard. Missing required inputs leave DRAFT with validation reasons. |
| DRAFT or READY | owner cancels | CANCELLED | Preserve the draft/history; terminal, no active guard. |
| READY | owner confirms actual baseline seller price and effective timestamp | BASELINE_ACTIVE | Freeze exact plan/tariff/cost/tax/input revisions, create first segment and link its active observation; take existing SKU guard in the same transaction. |
| BASELINE_ACTIVE | finish due/explicit collection | BASELINE_REVIEW | Freeze evidence snapshot/as-of and append outcome. Stop collection; this is not settlement finality. |
| BASELINE_ACTIVE | owner pauses | PAUSED | Close current segment/observation without erasing rows; persist resume target. Release active guard. |
| BASELINE_REVIEW | baseline gates pass and owner chooses a candidate | CANDIDATE_READY | Candidate must be among saved 2–10 options; retain baseline result/revision. Failed gates keep state and append WAITING/INSUFFICIENT result. |
| CANDIDATE_READY | owner confirms actual candidate price/time | CANDIDATE_ACTIVE | Freeze candidate revisions and atomically start one new observation/segment under same guard. No price mutation. |
| CANDIDATE_ACTIVE | finish due/explicit collection | CANDIDATE_REVIEW | Freeze independent candidate window and append result revision. |
| CANDIDATE_ACTIVE | owner pauses | PAUSED | Same as baseline pause; close segment and release guard. |
| CANDIDATE_REVIEW | evaluate more saved candidate | CANDIDATE_READY | Allowed only with comparable frozen reference/baseline and remaining phase quota. |
| CANDIDATE_REVIEW | owner completes decision | COMPLETED | Requires a recorded decision (choose/keep current/no clear decision); preserve results, release guard. |
| PAUSED | owner resumes with new actual confirmation | stored READY/CANDIDATE_READY resume target | Old segment remains immutable; create a new segment and reacquire guard atomically. Missing fresh confirmation leaves PAUSED. |
| any nonterminal non-active state | owner cancels | CANCELLED | Preserve all evidence; release guard defensively. |
| DRAFT, READY, REVIEW, PAUSED, CANCELLED, COMPLETED | archive action | ARCHIVED | Preserve all revisions; active states must first finish or pause; archive never starts collection. |

`COMPLETED`, `CANCELLED`, and `ARCHIVED` cannot be reactivated. A new run is a new experiment. Late data only appends a result revision and source `as_of`; it cannot re-open a phase or overwrite a previous conclusion. If a late correction changes eligibility, the new projection may change outcome, while old revision remains inspectable.

## 5. Gate evaluation order

1. **Identity/version gate:** exact owner/store/product/offer/SKU/scheme, supported schema, valid references and current CAS revision.
2. **Source-completeness gate:** all required source pages/windows end normally; record the cursor terminal marker, dates, observed/requested day counts, source method/version and explicit stop reason.
3. **Numeric gate:** finite Decimal money; integer nonnegative quantities; explicit zero vs missing; signed corrections reconciled once; no conflicting duplicate.
4. **Ownership gate:** base/additional/reconciliation-only assignment is disjoint; CPC overlap and tax ownership are explicit; no residual allocation.
5. **Scope gate:** same exact SKU/schema and compatible date basis/windows. No mixed aggregate/seller/report/return dates relabelled as one cohort.
6. **Quantity gate:** `WINDOW_COST_ALLOCATION` labels its declared denominator; `STRICT_RETAINED_COHORT` additionally requires exact delivered→return unit linkage and `Q_retained > 0`. Counts of API rows/postings do not satisfy this gate.
7. **Maturity/control gate:** full local days, minimum elapsed delay, inventory/price/tariff/cost/ads/promotions/unknown control flags; changes become new segment or warning/incomparable as appropriate.
8. **Scenario/tax gate:** invoke the canonical forward calculator and active-store TaxService; all selected expenses are in the correct pre-tax base; tax minimum and group tax-once semantics stay intact.
9. **Comparison gate:** same mode, denominator, date grain, policy, and reference snapshot; apply saved RUB/unit threshold after rounding. Otherwise `INCOMPARABLE`; percentage is withheld for zero/negative base.
10. **Recommendation gate:** recommend only among evaluated candidate prices. Never claim a causal price→conversion/DRR effect or mutate Ozon price.

If a gate fails, later gates must not convert it into success. Preserve available money totals when quantity eligibility fails, but omit RUB/unit and ranking. Result details name the first blocking reason and any independent warnings.

## 6. Target signatures and extension points

Illustrative Python protocol signatures (exact module/class names may change only if journaled; no second engine):

```python
normalize_expense_snapshot(
    identity: ExactSkuIdentity,
    source_rows: Iterable[NormalizedSourceRow],  # transient raw IDs, never persisted
    source_coverage: SourceCoverage,
    window: SourceWindow,
) -> ExpenseSnapshotV1 | EvidenceError

validate_quantity_evidence(
    identity: ExactSkuIdentity,
    posting_evidence: PostingWindowEvidence,
    returns_evidence: ReturnWindowEvidence,
    *, mode: Literal["WINDOW_COST_ALLOCATION", "STRICT_RETAINED_COHORT"],
) -> QuantityEvidenceV1

UnitPriceScenarioService.calculate(
    legacy_inputs: ExistingUnitScenarioInputs,
    *, extended: ExtendedScenarioV1 | None = None,
) -> ExistingScenarioResult

transition_experiment(
    repository: PlanningWorkspaceRepository,
    exact_scope: ExperimentIdentity,
    experiment_id: str,
    *, expected_state_revision: int,
    action: ExperimentAction,
    idempotency_key: str,
    payload: AllowlistedActionPayload,
) -> TransitionOutcome

append_phase_result(
    repository: PlanningWorkspaceRepository,
    exact_scope: ExperimentIdentity,
    experiment_id: str,
    phase_id: str,
    *, expected_state_revision: int,
    evidence_snapshot: ExpenseSnapshotRef,
    quantity_snapshot: QuantityEvidenceRef,
    as_of: Timestamp,
) -> ExperimentResultV1 | ControlledError
```

Collectors only orchestrate existing API clients plus one shared `PeriodProfitOperationTrace`; normalizers/services remain deterministic and pure where possible; repository is the sole transaction owner. The starting upper ceiling is 120 seconds and 128 actual HTTP attempts **for the complete user-triggered operation**, retries and pages included. A stricter existing parent trace wins. A repeated active button does not start a second collection; retry after 429/timeout is a separate explicit bounded action.

## 7. Persistence and migration plan for W17

- Recheck the actual branch revision before DDL. At W03, `PlanningWorkspaceRepository.DATABASE_SCHEMA_VERSION == 5`, payload `SCHEMA_VERSION == 3`, per-record payload cap is 64 KiB, repository list page max is 10. The additive target is DB schema v6; keep plan payload readers v1/v2/v3 frozen and use a dedicated contract version for new snapshots/results.
- Extend the existing repository only. Proposed additive tables: `planning_unit_economics_snapshots` (immutable allowlisted normalized projections), `planning_price_experiments` (exact scope/lifecycle CAS), `planning_price_experiment_phases` (immutable confirmed segments and snapshot refs), `planning_price_experiment_results` (append-only result revisions). Final table names/indexes follow W17 review; no migration is performed in W03.
- Put owner/store/product/offer/SKU/schema columns in unique/query guards. All mutations run in existing immediate transaction discipline. Parent/phase/result links are scoped and validated inside the same transaction; future/corrupt versions fail closed.
- Migration from v5 adds only new tables/indexes and version metadata; preserve every existing document, revision, tariff, observation, comparison and credential. Exercise supported older starting versions by the existing ordered migration path; never rewrite old payloads or recalculate old results. Reject a future DB version without modifying it.
- Per store: max 100 experiments; per experiment: max 10 phases; per phase: max 20 result revisions. Existing global document/observation/storage caps take precedence. At quota return explicit `*_QUOTA_REACHED`; do not silently delete/archive old history.
- Reuse 64 KiB serialized UTF-8 limit for each new snapshot/experiment/phase/result payload unless W17 proves an existing stricter cap; reject oversized before transaction. Keep repository page max 10 unless existing shared constant allows the requested operation.
- Idempotency key and payload hash are stored only as bounded mutation metadata under exact tenant scope. Strict allowlists deny raw posting/return ids, whole API responses, API keys, names/barcodes, unbounded source columns and free-form control text.
- Existing backup/verify/dry-run/restore must include new tables automatically through the existing SQLite snapshot mechanism; W37 proves it in a separate synthetic root before ready PR.

## 8. Synthetic fixture seeds for later stages

These are contract cases, not Ozon observations. W04 calculates numeric N01–N18; W05–W37 implement and assert these cases in their respective isolated tests.

| Fixture | Synthetic input shape | Expected contract result |
|---|---|---|
| F03-A repeated page | same owner/store/op/service and same signed 1.00 RUB on page boundary | one component counted; page cursor must advance and complete |
| F03-B multi-service | one operation id; service keys `LOGISTICS` and `STORAGE`, signed -2.00 and -0.50 RUB | two distinct components; never collapse by operation id only |
| F03-C duplicate conflict | same dedup key, first -2.00 then -2.01 RUB | component/snapshot `CONFLICT`; no unit amount |
| F03-D tenant identity | same raw transient operation id in two different stores | independently scoped rows; never cross-store merge |
| F03-E missing vs zero | complete exact source has no mapped operations versus complete exact source has explicit mapped rows totaling 0 | first MISSING/UNAVAILABLE; second CONFIRMED_ZERO |
| F03-F account residual | account total without exact SKU evidence or explicit allocation model | `UNATTRIBUTED`; excluded from SKU profit, never split by order count |
| F03-G ad reconciliation | financial CPC exact SKU -8.00 RUB and Performance same period/SKU 8.00 RUB | one cost source plus reconciliation link; no -16.00 double deduction |
| F03-H no-Premium metrics | Analytics returns ordered_units; cancellations/returns absent | ordered units may be retained; absent metrics `UNAVAILABLE`, strict retained gate blocked |
| F03-I cohort mismatch | delivered 10 units, two returns lack posting/SKU lineage | return counts shown as unmatched; strict retained units unavailable, not 8 |
| F03-J cross-dock units | signed net charge -40.00 RUB; accepted exact SKU supply denominator 20 units | 2.00 RUB/supplied unit only; no conversion to per sold unit |
| F03-K one-off expense | one-time -5 RUB handling charge in 56-day window | one-off status shown; not automatically repeated for every future sale |
| F03-L state replay | same confirm key and same body twice, then same key/new body; stale expected revision | first accepted once, exact replay stable, modified payload rejected, stale transition makes no write |

## 9. Planned verification ownership

No tests/services are introduced in W03. Implementation should extend existing suites before creating competing structures. Candidate target files (verify exact ownership during each stage):

- `tests/test_unit_economics_expense_contracts.py`: W05–W10 normalization/source coverage.
- `tests/test_unit_economics_quantity_contract.py`: W07/W12 strict cohort and separate supplied units.
- Existing `tests/test_unit_price_scenario_service.py`, target planning, batch, sensitivity, saved-plan, mix and observation result suites: W11–W16 parity and one-tax-call rules.
- Existing `tests/test_planning_workspace_repository.py` plus new `tests/test_planning_workspace_unit_economics.py`: W17–W20 migration, allowlists, CAS, idempotency, quotas and rollback.
- `tests/test_price_experiment_state_machine.py` and `tests/test_telegram_price_experiment_runtime.py`: W21–W34 domain/public flow.
- Existing backup/restore test profile: W37 new synthetic root and tenant isolation.

Current W03 verification is design consistency only: DB constants/source limit constants checked against repository; W02 support boundaries carried into gates; fixture ids unique and state chart has explicit terminal, active and pause paths. No pytest, compile, Ozon request, bot launch or data read is claimed for W03.

## 10. Open limitations carried forward

- Analytics no-Premium does not provide a dependable retained-sale denominator; exact terminal posting + return linkage must prove it or strict mode stays unavailable.
- Official Seller API docs SPA did not provide a readable schema through this audit. Do not promote community examples or local client request assumptions to API guarantees.
- Performance SKU reports / source CSV columns, storage SKU attribution, supply act confirmation/date semantics, and historical seller price remain unsupported until a verified contract or safe owner evidence appears.
- No business decision is required by W03: objective remains maximum positive RUB/unit among only the comparable evaluated candidates; active tax policy and all previous owner rules remain unchanged.
