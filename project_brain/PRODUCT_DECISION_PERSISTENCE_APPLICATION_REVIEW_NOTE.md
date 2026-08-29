# Review Note — Product Decision Persistence Application v1

Classification: Architecture Review Required. This stage introduces a new service and the first intentional Product Decision history mutation in the recompute pipeline.

Review focus: exact v40 readiness lineage; full-preview-to-authorized-preview matching; preservation of the existing history signature semantics; fail-closed read/write handling; no Ozon mutation; no legacy Action Executor; no automatic execution.

The service writes only through injected Product Decision history and leaves `execution_allowed=False`, `execution_ready=False`, and `executed=False`.
