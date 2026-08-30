# Task Load Observability v1

Date: 2026-08-30

Stages: v303-v312

## Goal

Make task persistence startup state observable without exposing file contents, exception details, user identifiers or creating a restart-time write.

## Source states

`TerminalSafeAssistantTaskService` now distinguishes:

- `ABSENT` — the task file does not exist;
- `UNREADABLE` — the file exists but cannot be read/decoded as JSON;
- `INVALID_ROOT` — JSON is readable but the root is not a dictionary;
- `LOADED` — a dictionary root was loaded and record-level validation ran.

## Issue codes

Source-level failures use stable non-sensitive codes:

- `TASK_FILE_READ_ERROR`;
- `INVALID_TASK_FILE_ROOT`.

Record-level issue codes from persisted-state validation remain available after a `LOADED` source state.

Diagnostics never include raw exception strings, file contents, file paths or user identifiers.

## Restart boundary

Initialization remains read-only.

A corrupt or invalid-root file is left unchanged during startup. The in-memory task store is empty and no recovered action is executed.

If a later explicit task mutation occurs through the normal task API, the existing atomic save path may replace the bad file with valid state. That write is caused by the explicit mutation, not by recovery itself.

## Backward compatibility

A missing file remains a normal empty store with no issue code.

An empty dictionary is a valid loaded store.

A valid dictionary continues through v293-v302 record validation and v283-v292 terminal reconciliation.

## Safety boundary

This work does not:

- auto-recover or execute malformed persisted intent;
- connect Product Decisions or Product Task Drafts to execution;
- call mutating Ozon APIs;
- change finance or mapping rules;
- modify `data/users.json`.

## Verification

Focused regressions:

`tests/test_task_load_observability_v303_v312.py`

The full repository `Verify` workflow must pass on the PR merge revision before merge.

Architecture Review Required: Yes, because production task startup/recovery behavior changes.
