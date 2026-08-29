# Product Decision User Action Completion Evidence v1

Creates a non-persistent evidence artifact when the user explicitly reports whether one checklist item was completed.

`CONFIRM_COMPLETED` means only `user_reported_completed=True`. It does not prove that an external action occurred, so `completion_evidence_source=USER_REPORT` and `externally_verified=False` are mandatory.

`NOT_COMPLETED` records the opposite statement in the returned artifact.

This stage does not mutate or persist the checklist and does not mark the system execution state:

- persistent=False;
- checklist_mutated=False;
- ozon_mutation_called=False;
- execution_allowed=False;
- execution_ready=False;
- executed=False.

The purpose is to distinguish user-reported manual completion from automatic or externally verified execution.
