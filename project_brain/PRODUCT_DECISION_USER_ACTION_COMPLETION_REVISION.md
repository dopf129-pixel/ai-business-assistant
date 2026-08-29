# Product Decision User Action Completion Revision v1

Allows a later user report to supersede an earlier persisted completion report without mutating or deleting history.

A revision is built only from a successfully persisted `USER_REPORT`. The root evidence ID is preserved and each later report receives an immutable `:revision:N` ID. This allows a user to report `NOT_COMPLETED` first and later `CONFIRM_COMPLETED` without an ID conflict.

The revision deliberately returns the existing v45 completion status (`...CONFIRMED` or `...DECLINED`) with `persistent=False`, so the existing v46 persistence service can store it without a new write path.

Safety remains unchanged: `externally_verified=False`, `checklist_mutated=False`, `ozon_mutation_called=False`, `execution_allowed=False`, `execution_ready=False`, `executed=False`.
