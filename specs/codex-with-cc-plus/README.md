# Codex With CC Plus Speckit

This directory is the tracked source of truth for Codex With CC Plus workflow design.
Runtime artifacts still live under `.codex/codex_with_cc`; specs here record stable
decisions, task plans, model boundaries, and acceptance rules.

## Lifecycle

Every substantial workflow change should move through this state machine:

```text
INTAKE
-> SPEC_DRAFTED
-> TASKFILES_DRAFTED
-> TASKFILES_VALIDATED
-> DISPATCH_READY
-> RUN_SUPERVISED
-> REPORT_READY
-> DETERMINISTIC_VERIFIED
-> MAIN_ACCEPTED
```

Failure branches:

- `TASKFILE_INVALID`: return to Dispatch Planner, then rerun the local validator.
- `RUN_STALE`: Run Supervisor reports idle time and last artifact activity.
- `DETERMINISTIC_VERIFY_FAILED`: optional V4-Pro forensic analysis, never override.
- `HUMAN_OVERRIDE_REQUIRED`: Codex main thread or human keeps final judgment.

## Roles

- `Dispatch Planner`: DeepSeek V4-Pro pre-dispatch planner. It drafts workflow plans
  and TaskFiles, but does not execute shell commands, edit business files, or override
  `validate_delegate_task.*`.
- `Run Supervisor`: Codex child-thread orchestration role. It owns one delegated run,
  observes that run's artifacts, runs deterministic verification, and returns concise
  feedback to the main thread.
- `Report Worker`: DeepSeek V4-Flash report-only helper for cheap preflight,
  normalization, and routine summaries.
- `Forensic Analyst`: DeepSeek V4-Pro failure assistant. It explains verifier failures
  and recommends next actions with `mayOverrideVerifier=false`.

## Commands

- `ccspec path|list|new`: manage tracked specs.
- `ccwatch -RunId <id>` or `ccwatch -WorkflowId <id>`: read artifact-grounded status.
- `ccsupervise -RunId <id>`: write `supervisor_<RunId>.json/.md` after observation.

Specs are not success claims. Deterministic validators and verifiers remain the hard
gates.
