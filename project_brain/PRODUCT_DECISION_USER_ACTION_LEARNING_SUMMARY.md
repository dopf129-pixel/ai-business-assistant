# Product Decision User Action Learning Summary v1

Aggregates non-causal post-decision outcome observations across SKUs.

The summary counts outcome types, priority changes, and observations per SKU. It excludes blocked, causal, or executed rows.

The summary is descriptive only:

- learning_scope=`DESCRIPTIVE_OBSERVATIONS_ONLY`;
- causal_claim_allowed=False;
- decision_rule_update_allowed=False;
- automatic_execution_allowed=False;
- executed=False.

This stage does not modify Product Decision rules, thresholds, persistence, or execution behavior.
