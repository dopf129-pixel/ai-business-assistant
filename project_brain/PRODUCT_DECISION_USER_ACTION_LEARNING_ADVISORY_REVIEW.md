# Product Decision User Action Learning Advisory Review v1

Captures an explicit human evaluation of v54 advisory insights.

Allowed decisions:

- `ACCEPT_USEFUL`;
- `REJECT_NOT_USEFUL`.

Acceptance means only that the user reported the advisory as useful. It does not validate causality and does not authorize a Product Decision rule update.

Mandatory boundary remains:

- `persistent=False`;
- `advisory_only=True`;
- `causal_claim_allowed=False`;
- `decision_rule_update_allowed=False`;
- `automatic_execution_allowed=False`;
- `executed=False`.
