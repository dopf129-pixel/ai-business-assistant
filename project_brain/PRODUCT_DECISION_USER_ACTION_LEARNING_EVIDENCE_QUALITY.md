# Product Decision User Action Learning Evidence Quality v1

Grades the descriptive learning summary by observation count and SKU coverage.

Quality levels:

- NO_EVIDENCE;
- VERY_LIMITED;
- LIMITED;
- DESCRIPTIVE_BASELINE.

Even DESCRIPTIVE_BASELINE is not causal evidence and cannot update Product Decision rules automatically.

Mandatory safety:

- causal_inference_supported=False;
- decision_rule_update_allowed=False;
- automatic_execution_allowed=False;
- executed=False.
