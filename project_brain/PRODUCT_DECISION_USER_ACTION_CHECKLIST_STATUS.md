# Product Decision User Action Checklist Status v1

Builds a read-only aggregate status from a v44 checklist plus persisted v46/v47 user completion reports.

For each checklist item, only the highest `completion_revision` is considered. Reports from another checklist/SKU, non-persisted records, execution-marked records, or non-`USER_REPORT` evidence are ignored.

Statuses are deliberately explicit:

- `NO_USER_REPORTS` — no valid report exists;
- `USER_REPORTED_PARTIAL` — at least one item has a report but not all latest reports are completed;
- `USER_REPORTED_COMPLETE` — every checklist item is reported completed by the user.

`USER_REPORTED_COMPLETE` is not external proof of execution. The result always keeps `externally_verified=False`, `executed=False`, and performs no persistence or mutation.
