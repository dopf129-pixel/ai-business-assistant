# Product Decision User Action Learning Confidence v1

Adds minimum-sample descriptive confidence on top of v52 evidence quality.

Confidence levels:

- NONE: fewer than 3 observations;
- LOW: at least 3 observations but limited coverage;
- MEDIUM: at least 10 observations across at least 2 SKUs;
- HIGH: at least 30 observations across at least 3 SKUs.

Confidence is explicitly scoped to descriptive pattern stability only. It is not causal evidence and cannot update Product Decision rules automatically.

Safety remains:

- causal_inference_supported=False;
- decision_rule_update_allowed=False;
- automatic_execution_allowed=False;
- executed=False.
