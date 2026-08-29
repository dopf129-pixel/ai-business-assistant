# Product Decision User Action Post-Decision Outcome v1

Classifies how a later Product Decision differs from the prior decision after a user-reported-complete checklist.

Supported observations include decision change, priority decrease, priority increase, and no change. The result is descriptive only.

Mandatory interpretation boundary:

- interpretation=`OBSERVED_AFTER_USER_REPORT`;
- causal_claim_allowed=False;
- executed=False.

The contract must never claim that the user's reported action caused the later Product Decision or business outcome.
