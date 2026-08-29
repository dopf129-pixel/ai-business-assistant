# Period Profit Mapping Review Incident Audit v1 — v159–v163

Date: 2026-08-29

Architecture Review Required: **Yes** — this batch adds a safety-critical read-only incident/audit layer on top of the long-lived mapping review monitoring lifecycle.

## Goal

After v154–v158, a closed mapping review can be monitored and reopened when current catalog evidence changes. This batch makes that monitoring transition auditable without introducing any new write path.

Workflow:

`v154 checkpoint + v155 refresh + v156/v157 evaluation → v159 observation → v160 exact delta → v161 incident classification → v162 human escalation handoff → v163 audit receipt`

## v159 — monitoring observation

A monitoring observation binds checkpoint, refreshed quality, and evaluation to one exact:

- scope;
- revision ID;
- mapping ID.

It freezes only already-observed evidence: catalog availability, freshness, missing type IDs, renamed operations, drift flag, review-required flag, quality score, reopen state, and explicit reopen reasons.

The observation does not blindly trust supplied reopen state. It deterministically recomputes the expected reopen reasons from refreshed evidence and requires exact equality with the v156/v157 evaluation. A forged clean evaluation cannot hide drift, and a forged reason cannot alter later incident classification.

Missing type IDs and renamed-operation type IDs are normalized only through exact integer IDs. Malformed IDs, malformed booleans, malformed lists, or inconsistent reopen state fail closed.

## v160 — exact evidence delta

Two monitoring observations can be compared only when their scope/revision/mapping lineage is identical.

The delta records changed evidence fields with explicit `before` and `after` values. It does not infer operation meaning and does not classify by names, substrings, fuzzy matching, or semantic similarity.

## v161 — incident classification

Incident classification is derived only from explicit reopen reasons already validated against refreshed evidence:

- `CATALOG_UNAVAILABLE` → `CATALOG_EVIDENCE_UNAVAILABLE`;
- `MISSING_TYPE_IDS`, `RENAMED_OPERATIONS`, `CATALOG_DRIFT` → `CATALOG_DRIFT`;
- `FRESHNESS_NOT_FRESH` → `FRESHNESS`;
- `REVIEW_REQUIRED` / `REVIEW_STILL_REQUIRED` → `REVIEW_REQUIREMENT`.

If a review is reopened with another explicit validated reason, the artifact uses `REOPENED_OTHER_EXPLICIT_REASON`; it still does not invent mapping semantics.

A still-closed observation produces no incident.

## v162 — human escalation handoff

A handoff can be built only for a real reopened incident bound to the same exact lineage and exact reopen reasons as the reopen evaluation.

The handoff explicitly keeps all mutation permissions disabled:

- `mapping_build_allowed=False`;
- `registry_save_allowed=False`;
- `activation_allowed=False`;
- `automatic_remap_allowed=False`;
- `automatic_activation_allowed=False`.

It indicates only that human re-review is required. The actual re-review remains the existing v134+ workflow.

## v163 — audit receipt

The audit receipt aggregates the current observation, exact delta, incident classification, and—when an incident exists—the human escalation handoff.

An incident audit cannot be considered ready without the corresponding handoff. Observation, incident, and handoff must retain the same lineage and reopen reasons. Clean monitoring observations do not require a handoff.

The audit is deterministic, read-only, and has `executed=False`.

## Safety invariants

Unchanged:

- exact type-ID/name evidence only;
- no fuzzy or substring classification;
- no automatic operation semantics;
- no automatic remap;
- no automatic mapping build;
- no registry save;
- no automatic activation;
- no Ozon mutation;
- no profit adjustment or fee double counting;
- return evidence still does not imply full returns economics;
- Product Decisions execution remains manual.

## Tests

Primary coverage:

`tests/test_period_profit_mapping_review_incident_audit_batch_v159_v163.py`

Fail-closed regressions:

`tests/test_period_profit_mapping_review_incident_audit_fail_closed.py`

Coverage includes exact lineage binding, deterministic evidence ordering, exact observation delta, clean/no-incident state, explicit incident categorization, human-only handoff permissions, audit handoff requirement, clean audit path, forged evaluation rejection, malformed ID rejection, and malformed schema fail-closed behavior.
