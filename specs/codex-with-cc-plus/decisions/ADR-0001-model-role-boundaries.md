# ADR-0001 Model Role Boundaries

## Decision

Codex With CC Plus uses four separate roles:

- `Dispatch Planner`: DeepSeek V4-Pro, pre-dispatch planning only.
- `Run Supervisor`: Codex child-thread supervisor, artifact observation and verifier
  execution for one delegated run.
- `Report Worker`: DeepSeek V4-Flash, low-cost report-only support.
- `Forensic Analyst`: DeepSeek V4-Pro, failure explanation only.

## Rationale

DeepSeek Flash is useful for cheap repeated summaries, but dispatch planning and
failure forensics carry higher workflow risk. Those responsibilities need stronger
reasoning and more explicit provenance, so they default to V4-Pro.

The Run Supervisor is not a model-only role because it needs trusted access to local
artifacts and deterministic verifier commands. It should run as a Codex child thread
so the main thread receives a compact report instead of polling the filesystem.

## Invariants

- `validate_delegate_task.*` remains the local zero-token TaskFile hard gate.
- `verify_delegate_run.*` and `verify_delegate_workflow.*` remain deterministic hard
  gates.
- Model outputs may recommend, explain, normalize, or draft.
- Model outputs must not turn a deterministic failure into success.
- Forensic artifacts must state `mayOverrideVerifier=false`.
