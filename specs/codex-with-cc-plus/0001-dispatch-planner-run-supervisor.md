# 0001 Dispatch Planner And Run Supervisor

## Goal

Reduce startup and long-running workflow friction by moving planning and observation
into explicit roles while preserving deterministic hard gates.

## Model Boundary

- DeepSeek V4-Pro powers `Dispatch Planner` and `Forensic Analyst`.
- DeepSeek V4-Flash powers cheap `Report Worker` tasks.
- Claude Code remains the expensive implementation executor.
- Codex main thread remains the final judge.

## Dispatch Planner

The Dispatch Planner receives user intent, repository context, and tracked specs. It
produces dispatch plans, TaskFile drafts, and risk notes. It must record:

- `runnerType=openai_compatible_report`
- `model=deepseek-v4-pro`
- `mayOverrideValidator=false`
- `mayOverrideVerifier=false`

It cannot execute shell commands, edit business files, dispatch implementation work,
or treat model judgment as a hard gate.

## Run Supervisor

The Run Supervisor is a Codex child-thread role for one delegated run. It can observe
the artifacts of the run it supervises, but it must not observe its own live artifacts
or recursively create unassigned delegate runs.

It reports:

- run state and idle time
- last stream event
- report path and parsed status
- deterministic verifier result
- main-thread recommended action
- `mayOverrideVerifier=false`

## State Machine

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

`RUN_STALE` is a reporting state, not an automatic kill decision. The main thread or
human decides whether to wait, request rework, or inspect partial artifacts.

## Acceptance

- The contract records all orchestration roles without adding them to Claude worker
  roles.
- `ccwatch` can summarize run and workflow artifacts without noisy shell polling.
- `ccsupervise` writes supervisor artifacts with `mayOverrideVerifier=false`.
- `ccspec` can list and create tracked specs.
- Existing `ccviz` and delegate verification commands continue to work.

## Verification

- `python -m pytest tests/test_contract_source.py tests/test_supervision_and_speckit.py`
- `python -m pytest tests/test_delegate_runtime_selftest.py`
- `./skills/codex-with-cc/macos_scripts/test_delegate_runtime.sh`

## Decision Log

- Use repo-tracked `specs/codex-with-cc-plus/` as the stable speckit layer.
- Keep `.codex/codex_with_cc` for runtime task files and generated artifacts.
- Keep DeepSeek Flash as cheap report support, not dispatch owner.
- Use DeepSeek V4-Pro for high-uncertainty planning and forensic analysis.
