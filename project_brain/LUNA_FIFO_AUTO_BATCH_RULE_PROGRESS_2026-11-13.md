# Журнал Luna: автоматическая принадлежность поставок партии

Дата создания: 13.11.2026. Журнал исполнения; продолжать по Resume после сокращения контекста.

## Resume

- ТЗ: LUNA_FIFO_AUTO_BATCH_RULE_TASK_2026-11-13.md.
- Spec branch: codex/fifo-auto-batch-rule-spec-20261113.
- Product baseline: main 7965dcddffa50bd4e0f175cd18c32929b6a845d0.
- Implementation branch/head checkpoint: `codex/fifo-auto-batch-foundation-20261113` at `930ef296` (`Integrate automatic supply manifest readiness`, FB09 implementation commit); documentation checkpoint follows. FB08: `f99b8096`; FB07: `9ff94a4f04f14e6a9c91d2e55c26d93f56bfb35a`; FB06: `12014e9600085eaa0739708a025ca317705bb736`. Product base remains `7965dcddffa50bd4e0f175cd18c32929b6a845d0`.
- Следующий этап: FB10 (PR A checkpoint). FB00–FB09 closed; former FB01 unknown-total baseline is green. The separate untracked `.fl12-deps/` stays preserved and excluded.
- Прежняя untracked .fl12-deps/ сохранена, не добавлять в Git.
- Рабочая копия: изолированный Codex worktree; Desktop-папка с работающим ботом не открывалась для разработки.
- Исходный `git status`: только `?? .fl12-deps/`; staged и tracked diff отсутствовали. Каталог .fl12-deps содержит 6 элементов, сохранён и исключён из изменений.
- Исходные SHA-256 tracked data (без чтения/вывода содержимого): `data/history.json` 520E8E1F25B2BB5C7F2A9E48B8CD6B0F8DCF9B0EA021CE622366F88BDE44E08C; `data/profiles.json` 8F9E51A4545AC897A5F0324200BEAC5281428A6B248CA60A7049AD44BF5F0D51; `data/tasks.json` 6D852D707927A617DFE3B23CB32AA580EC558272D40FB346B57ABF030868142F; `data/tax_configuration.json` F8EB3295F353060EAE65632A4E64B8711C3F9E2BC42004BD; `data/users.json` 2D289F298EB3E66EB0E65FE5A20E7F1A7A520A0845A4FD6F27FB15017BC51BE2.
- Spec branch and origin/main were fetched and verified: spec HEAD 0fa8b783; its merge-base with main is exactly 7965dcdd. PR A is based on the published spec branch.
- Existing architecture reviewed: Decision 066, current state, test map, FR/FL progress, transition runtime/contracts/store/reconciliation/readiness and v16 migration tests. No code changed at FB00 start.
- No contents of owner data were read or printed. R1 remains independent and unverified.
- R1: полного поддержанного журнала движений пока нет; owner case не верифицирован.
- Source: bundle для состава SKU подтверждён официальным гайдом. Полная JSON schema, raw states и фактическая dispatch date подлежат проверке FB02.
- CI спецификации указывается в описании spec PR и не является implementation CI.

## Этапы

| Этап | Статус | Коммит / файлы | Проверки и фактический результат |
|---|---|---|---|
| FB00 | DONE | `56c7c24a`; progress journal | `git status` подтвердил отсутствие tracked/staged edits на старте; `.fl12-deps/` сохранён; пять tracked data hashes записаны; base/main=7965dcdd; Desktop bot не открывался. `git diff --check` PASS. |
| FB01 | DONE | `c47c63c2`; `tests/test_fifo_cost_batch_rule_regressions.py` | B01/B02 baseline red зафиксирован в Windows Python 3.12: **1 failed** на точной причине — `не знаю` отклоняется как неверное количество; saved case сохраняет `declared_shipped_units=None`, revision 6, FIFO queue не инициализируется. Краснота ожидаема до FB08. B23 будет покрыт после реализации typed controls/manifest в FB07/FB17. |
| FB02 | DONE | `project_brain/FIFO_BATCH_SUPPLY_SOURCE_CONTRACT_2026-11-13.md`; два synthetic fixtures | Проверены официальные страницы Ozon и текущие локальные wrappers. Подтверждено только bundle concept `supply_id`+`bundle_id` и наличие SKU/quantity, list/get v3 и crossdock `arrival_date=null`; точная raw schema/states/pagination/bundle response/dispatch date не раскрыты и оставлены NOT_VERIFIED. Fixtures проходят JSON parsing/маркер проверки; `git diff --check` PASS. Реальных запросов нет. |
| FB03 | DONE | `1d7e275f`; immutable contracts and eight new tests | New contract tests: **8 passed**; with existing FIFO transition contracts: **21 passed**. `compileall`, `git diff --check`, and `git diff --exit-code -- data` PASS. Covers strict booleans, immutable scoped contracts, encrypted lookup, unknown versus explicit zero, independent coverage flags, timestamp-independent manifest fingerprint, and separate aggregate quantity ceiling. No I/O/persistence introduced. |
| FB04 | DONE | `cac9e676b5490ba76262b3f5be75370d11d64713` — `Add FIFO batch rule v17 storage`; repository/schema, batch store, transition case mode readers/writers, tests, CHANGELOG/CURRENT_STATE/TEST_MAP/DECISIONS | Additive schema v17 and scoped SQL helpers. `supply_total_mode` defaults to LEGACY_OWNER_TOTAL in DB and old payload readers; explicit mode round-trips. Rules, SKU observations, decisions/decision references and controls are append-only; scans use revision CAS and encrypted continuation bytes. Fresh/v12–v16 migration, injected rollback, future-version rejection, no Planning user_version change. Final linked profile: **121 passed** across repository, transition store/service/atomic apply, schema migrations and contracts; `compileall`, `git diff --check`, `git diff --exit-code -- data` PASS. Original five data hashes match FB00. No owner data/credentials/API used. |
| FB05 | DONE | `99b95e85` — `Add FIFO batch rule preview and confirmation`; contracts, batch store, new rule service and tests, CHANGELOG/CURRENT_STATE/TEST_MAP/DECISIONS | Added frozen preview tickets and exact owner/store/product/offer/SKU + case revision + rule-head CAS. Explicit old-home/transit zero and first-boundary date are required; same-day successor is review-only. Confirmation atomically appends immutable rule event(s), closes predecessor interval when needed, and changes only `supply_total_mode`; no rates/layers/events/allocations/COGS are written. Identical retry works after service restart via durable receipt; reused key with changed payload conflicts. Linked Windows/Python 3.12 profile across batch contracts/service/store, transition contracts/store/service/apply, v13/v16 migration: **91 passed in 10.18s**; latest FB05 service-only: **10 passed in 1.18s**. `compileall`, `git diff --check`, and `git diff --exit-code -- data` PASS. All SQLite data was synthetic and temporary. Architecture review required (>300 lines/new service). Full suite and exact-head CI remain pending FB10. |
| FB06 | DONE | `12014e9600085eaa0739708a025ca317705bb736` — `Add FIFO supply membership classifier`; pure classifier, membership result contract, stable rule binding, timezone chain regression, docs | `classify_supply` selects only by proven local dispatch date and validated `[start, next_start)` rule history. Explicit first-day selection is respected; unknown dates, same-day boundaries, malformed histories, timezone changes, scope mismatch, and owner/source contradictions fail closed. Ordinary status/quantity refresh preserves membership only while scope, supply, rule revision/fingerprint and dispatch binding are unchanged; full source fingerprint remains historical audit evidence. A later stale decision cannot revive a superseded one. Cancellation does not erase a proven dispatch. No FIFO event/rate/layer/allocation/COGS writes. FB05–FB06 profile: **39 passed in 2.02s**; modified modules compile; `git diff --check` and `git diff --exit-code -- data` PASS. Synthetic fixtures only. Architecture review required because a new service and >300-line change were introduced. Exact-SHA hosted CI remains pending at PR A checkpoint FB10. |
| FB07 | DONE | `9ff94a4f04f14e6a9c91d2e55c26d93f56bfb35a` — `Add dated FIFO owner quantity controls`; contract/store tests and docs | Added typed `BatchTotalControl` with inclusive local-date window, quantity kind/status, exact scope/case and separate source/owner confirmation fingerprints. Store appends idempotently in caller transaction, validates exact scope and sequential control revisions, supports owner-confirmed then superseded/revoked status records, enforces the 100-control read boundary, and reads controls under exact tenant/store/SKU scope. Separate control rows do not mutate case revision, legacy total/mode, declarations, or FIFO tables; later dated controls do not rewrite earlier ones. Legacy `declared_shipped_units=None`/`UnknownValue` support and `LEGACY_OWNER_TOTAL` default remain unchanged. Combined controls + FB05–FB06 + legacy transition contract/service profile: **65 passed in 5.46s**; changed modules compile; `git diff --check` and tracked `data/` equality PASS. UI selection is FB08; manifest/window comparison is FB17; no lifetime auto cap is introduced. |
| FB08 | DONE | `f99b8096` — `Add FIFO batch rule Telegram choices`; batch Telegram adapter, runtime/factory wiring, B01/B02/B31 regressions, production workflow assertion | Wizard with production composition offers auto Ozon supply mode, dated control, and return instead of mandatory lifetime quantity. Existing unknown and legacy-total drafts resume at choice with values preserved. “Не знаю” opens first-day policy question only; separate all-dispatches choice creates read-only preview and separate confirm stores rule under exact case revision. NO/UNKNOWN first-day path stays unresolved without source selection; no unsafe include-all fallback. Manual values are typed controls bound to explicit inclusive date window/kind and are never treated as Ozon facts. UI tickets carry flow revision and stale mode buttons fail closed. Test profile across FB08, existing runtime, batch contracts/service/store/classifier and production assembly: **71 passed**; compileall, `git diff --check`, and `git diff --exit-code -- data` PASS. Auto-rule/control confirmation does not initialize FIFO or change profit. No Ozon/Telegram/live bot calls. |
| FB09 | DONE | `930ef296` — `Integrate automatic supply manifest readiness`; readiness service and regressions | `AUTO_FROM_SUPPLIES` now has typed exact scope/case/scan/rule checks. Missing manifest yields `AUTO_SUPPLY_MANIFEST_UNAVAILABLE`; incomplete coverage yields `AUTO_SUPPLY_MANIFEST_INCOMPLETE` with subtotal clearly non-final. Empty list, unresolved membership, unknown quantities, stale source, absent source-as-of/window or unsupported source profile block. Exact current manifest can remove only supply-manifest gap; physical receipt timing and R1/cutoff remain independent. `LEGACY_OWNER_TOTAL` keeps prior gate; `OWNER_CONTROL` cannot fall through it. Linked readiness/review/transition/apply/cutoff bridge/batch contracts: **81 passed**. Both changed Python files compile; `git diff --check` and tracked `data/` equality PASS. First run exposed invalid test fixture (`None` total lacked typed UnknownValue); fixture corrected, rerun passed. No live calls. Architecture review required (>300 lines changed and readiness dependency on batch contracts). |
| FB10 | NOT_STARTED | — | — |
| FB11 | NOT_STARTED | — | — |
| FB12 | NOT_STARTED | — | — |
| FB13 | NOT_STARTED | — | — |
| FB14 | NOT_STARTED | — | — |
| FB15 | NOT_STARTED | — | — |
| FB16 | NOT_STARTED | — | — |
| FB17 | NOT_STARTED | — | — |
| FB18 | NOT_STARTED | — | — |
| FB19 | NOT_STARTED | — | — |
| FB20 | NOT_STARTED | — | — |
| FB21 | NOT_STARTED | — | — |
| FB22 | NOT_STARTED | — | — |
| FB23 | NOT_STARTED | — | — |
| FB24 | NOT_STARTED | — | — |
| FB25 | NOT_STARTED | — | — |
| FB26 | NOT_STARTED | — | — |
| FB27 | NOT_STARTED | — | — |
| FB28 | NOT_STARTED | — | — |
| FB29 | NOT_STARTED | — | — |
| FB30 | NOT_STARTED | — | — |
| FB31 | NOT_STARTED | — | — |

## Содержание каждой записи

Дата, branch/HEAD/base, изменённые функции/контракты, команды и результаты проверок,
Bxx→test mapping, source gaps, data integrity, PR/CI URL, следующий этап.
Не писать DONE для непроверенной функции.

### FB06 verification detail

- B05/B06/B07/B26: `tests/test_fifo_cost_batch_rule_classifier.py` covers start-day policies, later interval selection, unknown dispatch evidence, successor rule boundaries, and same-day/history conflicts.
- B28/B43: classifier preserves a cancelled supply's previously proven dispatch and fails closed on cancelled/malformed rule history; post-APPLIED correction/replay remains owned by later integration stages and is not claimed here.
- B38: buyer returns remain outside this supply-only API; classification accepts only `SupplySkuObservation` and does not create FIFO movements or reassign return COGS.
- B42: the status/quantity-refresh regression proves a stable membership binding reuses the owner decision; a changed dispatch proof and a stale latest decision cannot resurrect an earlier selection.
- Command: `PYTHONPATH=app python -m pytest tests/test_fifo_cost_batch_rule_classifier.py tests/test_fifo_cost_batch_rule_service.py tests/test_fifo_cost_batch_rule_contracts.py tests/test_fifo_cost_batch_supply_store.py -q` — **39 passed in 2.02s**. `python -m compileall -q` on the three changed service modules, `git diff --check`, and unchanged tracked `data/` all PASS.
- Exact code SHA: `12014e9600085eaa0739708a025ca317705bb736`. No real API, bot, owner data, merge, or deployment.

### FB07 verification detail

- B23/B24/B25 foundation: dated controls preserve their exact kind/window and coexist without replacing earlier controls; automatic-manifest comparison and factual apply gate are still future FB17/FB25. Legacy unbounded values stay in the original transition payload; no date is inferred from `updated_at`.
- Tests: `test_fifo_cost_batch_rule_contracts.py` and `test_fifo_cost_batch_supply_store.py`, plus `test_fifo_cost_batch_rule_service.py`, `test_fifo_cost_batch_rule_classifier.py`, `test_fifo_cost_transition_contracts.py`, and `test_fifo_cost_transition_service.py` — **65 passed in 5.46s**. `compileall`, `git diff --check`, and `git diff --exit-code -- data` PASS. Synthetic DB only.
- `append_total_control` does not switch `supply_total_mode`; it is a repository evidence operation. The later owner flow must bind the selected control to its explicit confirmation and intended mode without changing legacy declarations.

## Отдельные ограничения

- Ошибка резервирования assistant_session.json (list против ожидаемого dict) вне scope FB.
- RULE_CONFIRMED не означает SUPPLY_COVERAGE_COMPLETE или FIFO_READY.
- Не выполнять merge/deploy/live Ozon/Telegram/startbot.
