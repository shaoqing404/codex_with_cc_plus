---
name: codex-with-cc-dispatching
description: Dispatch codex-with-cc tasks through the required Codex child thread to delegate_to_claude.* to Claude Code CLI chain with WorkflowId, TaskId, Role, and Scope metadata.
---

# Codex with CC Dispatching

Read `../codex-with-cc/CODEX_WITH_CC.md` before dispatching. Use this skill after planning has produced task boundaries.

Dispatch rules:

- Every child thread uses `model: gpt-5.4-mini`, `reasoning_effort: medium`, and `fork_context: false`.
- Every worker command sets `CODEX_CLAUDE_CHILD_THREAD=1`.
- Every worker command passes `-TaskFile`, `-WorkflowId`, `-TaskId`, `-Role`, and `-SessionKey`.
- Run `validate_delegate_task.*` before dispatch when the task file was generated, contains reviewer metadata, or carries explicit `-Tests` commands.
- Never dispatch legacy inline `-Task`, legacy `-Mode`, or a command that relies on an implicit session key.
- Reviewer commands must pass `-ReviewForTaskId` and `-ReviewKind spec` or `-ReviewKind quality`.
- Parallel writable tasks require explicit non-overlapping `-Scope` values.
- Use `PrimaryAnchor` for a parallel batch anchor, `ParallelPool` for independent side work, and `PrimaryReuse` for serial follow-up.

Dispatch discipline:

- Dispatch the immediate blocking task locally only when no child-thread delegation is needed; otherwise create the Codex child thread and keep the main thread focused on review.
- Put all worker instructions in a TaskFile with `Goal`, `Allowed Scope`, `Forbidden Actions`, `Acceptance Criteria`, `Verification`, and `Report Requirements`; the runtime rejects old one-line prompts.
- Include the exact verification commands in the task file and pass them with `-Tests` when possible.
- Run `ccdoctor` before implementation dispatch when Claude Code/socket/login/proxy health is uncertain.
- The worker's final `Verification` report must include every command passed with `-Tests` and the observed outcome.
- Dispatch implementer, spec reviewer, and quality reviewer as separate task ids so the workflow artifact can prove acceptance.
- Dispatch a final-verifier task for any workflow with implementer tasks.
- Use parallel dispatch only after scope boundaries are explicit enough to avoid file conflicts.
- After a parallel batch, wait for the anchor and side tasks before serial review or follow-up implementation.
- A child thread must wait for terminal delegate evidence. Artifact paths, `status: running`, `RUNNING_ACTIVE`, or `STARTING` are not completion. If the worker report is missing or non-terminal, run `ccsupervise -Wait` and then deterministic verification before returning a worker result.

Required child-thread return shape:

```text
DelegateStatus: <DISPATCHED|WAITING|TERMINAL|FAILED>
RunId: <run-id>
WorkflowId: <workflow-id>
TaskId: <task-id>
ArtifactRoot: <artifact-root>
StatusPath: <status-path>
ReportPath: <claude/report path or missing>
TracePath: <trace-path>
RawStreamPath: <stream-path>
ObservedState: <STARTING|RUNNING_ACTIVE|RUNNING_QUIET|REPORT_READY|FAILED|STALE|RUNNING_DEAD_PROCESS>
Verifier: <not-run|passed|failed>
Supervisor: <not-run|passed|failed>
MainThreadAction: <wait-with-ccsupervise|verify-run|review-report|rerun-or-forensics>
```

If `ObservedState` is `STARTING`, `RUNNING_ACTIVE`, or `RUNNING_QUIET`, the child
thread must say `DelegateStatus: WAITING` and `MainThreadAction:
wait-with-ccsupervise`; it must not summarize implementation, review, or acceptance
as complete. A concise valid waiting response is:

```text
DelegateStatus: WAITING
RunId: <run-id>
ObservedState: RUNNING_ACTIVE
MainThreadAction: run ccsupervise -RunId <run-id> -ArtifactRoot <artifact-root> -Wait
No worker report is acceptable yet.
```

Main-thread instruction handoff:

- For `WAITING`, include the exact `ccsupervise -RunId ... -ArtifactRoot ... -Wait`
  command the main thread should run from the target project root.
- For `TERMINAL`, include the exact verifier command the main thread should run
  next and whether report review is allowed.
- For `FAILED`, list status, trace, stream, and report paths, then say whether
  this is an execution-layer failure or a worker-reported task failure.
- Never use natural-language success wording unless `Verifier: passed` and the
  worker report is present.

Do not dispatch default Codex workers outside the codex-with-cc chain.
