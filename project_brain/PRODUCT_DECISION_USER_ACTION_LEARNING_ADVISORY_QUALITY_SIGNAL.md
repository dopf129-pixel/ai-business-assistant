# Product Decision User Action Learning Advisory Quality Signal v1

Turns v56 human-reported usefulness metrics into a review signal:

- `INSUFFICIENT_REVIEWS` below five reviews;
- `HIGH_REPORTED_USEFULNESS` at 80% or higher;
- `MIXED_REPORTED_USEFULNESS` at 50-79%;
- `LOW_REPORTED_USEFULNESS` below 50%.

Mixed/low signals may recommend a human advisory-improvement review, but they never change advisory generation automatically.

`automatic_advisory_change_allowed=False`, `decision_rule_update_allowed=False`, and `automatic_execution_allowed=False` remain mandatory.
