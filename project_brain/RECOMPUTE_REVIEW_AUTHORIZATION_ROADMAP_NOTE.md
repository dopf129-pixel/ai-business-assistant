# Roadmap Note — Product Decision Recompute Review Authorization v1

Completed after v33 recompute-review eligibility.

An explicit `AUTHORIZE` decision can now grant permission for a separate Product Decision recompute step, while `REJECT` keeps recompute disallowed.

This stage does not start recomputation, mutate Product Decisions, call Ozon, or enable execution.
