# Product Decision Learning Health Surface V1

Date: 2026-08-30  
Stages: v478-v487  
Architecture Review Required: Yes

## Goal

Expose the quality and volume of existing Product Decision learning evidence to the seller without inventing causality, success rates, profitability claims, or automatic rule changes.

This is a seller-facing read-only surface over the existing persisted Product Decision history summary.

## Why this feature

The repository already stores:

- decision snapshots;
- explicit user feedback;
- later decision-change observations.

The Telegram UI already shows a basic learning summary, but it does not tell the seller whether the available evidence is still sparse or broad enough for descriptive pattern review.

The newer canonical advisory chain cannot be wired directly yet because it requires explicit persisted/verified user-action checklist lineage that the current Telegram decision flow does not produce.

This package does not bypass that lineage.

## v478 — Canonical history-health input

The health contract consumes only the existing `ProductDecisionHistoryService.learning_summary()` aggregate.

It validates:

- product count;
- decision snapshot count;
- feedback totals;
- outcome totals;
- non-negative integer counts;
- consistency between totals and breakdowns.

Malformed aggregates fail closed.

## v479 — Feedback-only state

When explicit feedback exists but no later decision-change observation exists, the state is:

`FEEDBACK_ONLY`

The seller is told that later observations have not accumulated yet.

## v480 — Descriptive sample states

The contract uses four descriptive states:

- `NO_FEEDBACK_EVIDENCE`;
- `FEEDBACK_ONLY`;
- `EARLY_POST_FEEDBACK_SAMPLE`;
- `MULTI_PRODUCT_DESCRIPTIVE_SAMPLE`.

These are evidence-volume states only.

They are not statistical confidence levels and do not prove correctness.

## v481 — Malformed evidence rejection

Inconsistent totals or impossible relationships such as more products than snapshots fail closed.

The UI does not attempt to repair or infer missing counts.

## v482 — No success-rate claim

The health artifact deliberately does not expose a usefulness percentage or success rate.

Mandatory safety fields:

- `causal_claim_allowed=False`;
- `success_rate_claim_allowed=False`;
- `profitability_claim_allowed=False`;
- `decision_rule_update_allowed=False`;
- `automatic_execution_allowed=False`;
- `executed=False`.

## v483 — Backward-compatible handler DI

`AssistantButtonHandlerService` receives an optional final constructor argument:

`product_decision_learning_health_builder=None`.

Without the builder:

- the old Product Decisions menu is unchanged;
- the new callback returns unavailable;
- existing tests/consumers remain compatible.

## v484 — Seller navigation

Production Telegram explicitly injects the canonical builder.

When decision history and the builder are both available, the Product Decisions menu adds:

`🩺 Качество данных обучения`

callback:

`product_decision_learning_health`.

## v485 — Human-readable evidence health

The screen shows:

- products in history;
- decision snapshots;
- useful/not-relevant feedback counts;
- post-feedback observation counts;
- descriptive sample state;
- a safe next evidence-collection/review step.

It explicitly says that the statistics do not prove causality, decision correctness, or profitability.

## v486 — Forgery resistance

The handler rejects a builder result that violates safety flags, including any attempt to enable:

- causal claims;
- success-rate claims;
- profitability claims;
- decision-rule updates;
- automatic execution.

## v487 — Production wiring and safety

`create_telegram_assistant()` injects the canonical pure builder.

The feature does not:

- change Product Decision rules or thresholds;
- persist new feedback;
- create or execute tasks;
- mutate Ozon;
- change mapping authorization;
- change financial calculations;
- modify `data/users.json`.

## Important distinction

This screen is based on legacy persisted decision-history aggregates because those are the facts currently available in the production Telegram flow.

It does **not** claim to be the newer canonical user-action advisory evaluation chain.

That chain still requires its own exact checklist/completion/persistence lineage before production use.

## Verification

Focused regressions cover:

1. no-feedback state;
2. feedback-only state;
3. early/multi-product descriptive states;
4. malformed aggregate rejection;
5. no success-rate/execution claims;
6. backward-compatible optional DI;
7. conditional menu navigation;
8. seller-facing wording;
9. forged safety violation rejection;
10. production builder wiring.

Full GitHub Actions verification is required before merge.
