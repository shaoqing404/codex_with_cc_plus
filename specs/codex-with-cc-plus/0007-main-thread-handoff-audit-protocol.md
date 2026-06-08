# 0007 Main Thread Handoff And Audit Protocol

## Goal

Define the next framework phase around the real primary user: the Codex main
thread. Human-facing commands remain useful, but the framework must first serve
Codex as a delegation owner that has limited context, limited quota, and final
responsibility for user-facing acceptance.

This spec records product direction and the current P0 implementation state.
P0 main-thread handoff, `ccstatus`, bounded wait guidance, audit/refusal schema,
and first-use Claude Code reliability refusal are implemented. P1/P2 items remain
tracked below.

## Implementation Status

Implemented in this phase:

- `ccstatus summary|claude|preflight|run|audit|workflow`;
- shared main-thread handoff helpers for `REFUSED`, `WAITING`, and terminal run
  summaries;
- delegate preflight refusal before Claude Code startup when runtime readiness is
  blocked;
- structured failed artifacts for preflight refusal, including
  `businessAcceptance=blocked`, `workerOutcome=FAIL`, `failureLayer`, and
  machine-readable handoff;
- child-thread contract updates for `READY`, `REPORT_READY`, and `REFUSED`;
- canonical `audit_<RunId>.json/.md` artifacts through `ccstatus audit`;
- tests for unreachable local backend, active-run wait guidance, preflight
  refusal artifacts, and wrapper forwarding.

Not yet implemented:

- workflow-verifier-owned audit rollups across multiple runs;
- automatic post-execution DS routing;
- PageIndex socket/API failure fixture;
- full provider adapter support for cc-switch desktop state.

## Role Personas

### Codex Main Thread

Primary user: Delegation Owner and Acceptance Judge.

Needs:

- decide whether to delegate or keep work local;
- compress intent into a TaskFile without spending excessive context;
- avoid active polling while a worker is running;
- know whether to wait 60 seconds, wait 300 seconds, verify, review, diagnose,
  retry, or report back to the human;
- distinguish worker claims from artifact-grounded evidence;
- keep final acceptance authority even when DS or worker reports are available.

Anxiety source:

- quota and context pressure;
- uncertainty about live worker state;
- risk of accepting a false success;
- risk of spending too many tokens manually reading logs and artifacts.

### Codex Child Thread

Secondary user: Execution Courier and Run Observer.

Needs:

- know exactly which runner it is allowed to invoke;
- know whether it should wait, return a waiting handoff, or return a terminal
  handoff;
- avoid making final acceptance claims;
- return concise, machine-readable status to the main thread;
- know which local constraints and framework specs to read when execution becomes
  abnormal.

The child thread is not a product owner, reviewer of record, or acceptance
authority unless the task role explicitly says `reviewer` or `final-verifier` and
the workflow verifier later accepts that gate.

## Main Thread User Stories

### Scenario 1: Delegating To Reduce Quota And Context Pressure

Story:

> As Codex main thread, I want to delegate bounded implementation or audit work to
> a worker so I can preserve context and quota while keeping acceptance control.

Required response shape:

```json
{
  "handoffType": "dispatch",
  "delegateStatus": "DISPATCHED",
  "acceptanceAllowed": false,
  "mainThreadAction": "wait_with_supervisor",
  "recommendedWaitSeconds": 60,
  "nextCommand": "ccsupervise -RunId <run-id> -ArtifactRoot <artifact-root> -Wait -TimeoutSeconds 60",
  "confidence": "high",
  "evidencePaths": {
    "status": "<status-path>",
    "trace": "<trace-path>",
    "stream": "<stream-path>"
  }
}
```

Acceptance rule: dispatch evidence alone never allows review or final acceptance.

### Scenario 2: Waiting Without Taking Over

Story:

> As Codex main thread, I want the framework to recommend a bounded sleep/wait
> interval so I do not waste quota polling logs or prematurely interrupt a live
> worker.

Default wait policy:

- `STARTING`: recommend 60 seconds.
- `RUNNING_ACTIVE`: recommend 60 seconds.
- `RUNNING_QUIET` below stale threshold: recommend 300 seconds.
- `RUNNING_QUIET` over stale threshold: stop passive waiting and classify risk.
- `RUNNING_DEAD_PROCESS`: stop waiting; diagnose or rerun.

Required fields:

```json
{
  "observedState": "RUNNING_ACTIVE",
  "acceptanceAllowed": false,
  "recommendedWaitSeconds": 60,
  "mainThreadAction": "wait_with_supervisor",
  "nextCommand": "ccsupervise -RunId <run-id> -ArtifactRoot <artifact-root> -Wait -TimeoutSeconds 60",
  "reason": "worker process appears alive and stream activity is recent"
}
```

Thresholds must be configurable. Recommended defaults are product defaults, not
hidden hard-coded truths.

### Scenario 3: Reviewing Or Auditing A Finished Worker

Story:

> As Codex main thread, I want a compact audit package that tells me whether the
> worker result can enter review, needs missing gates, must be rerun, or is
> blocked by execution failure.

Audit package minimum:

```json
{
  "handoffType": "audit",
  "workerClaim": "DONE",
  "reportValid": true,
  "changedFilesInScope": true,
  "testsDeclared": true,
  "testsObserved": true,
  "verifierPassed": true,
  "missingGates": ["spec_review", "quality_review"],
  "acceptanceAllowed": false,
  "mainThreadAction": "dispatch_missing_review_gates",
  "confidence": "high"
}
```

`acceptanceAllowed` is the key field. It is the framework's direct service to the
main thread's decision burden.

## Child Thread Stories And Open Questions

### Story A: Child Thread As Waiting Courier

> As Codex child thread, I need to know whether I should wait internally or return
> a waiting handoff to the main thread.

Initial direction:

- Child thread may wait only when the wait budget is short and explicit.
- For longer waits, the child thread should return `DelegateStatus: WAITING` with
  `recommendedWaitSeconds` and `nextCommand` so the main thread can decide whether
  to sleep, continue, or report progress.
- A child thread must not keep an unbounded silent wait.

Open design point:

- Whether the child thread itself should run one 60-second supervisor wait before
  returning, or always return immediately with a suggested wait command.

### Story B: Child Thread As Review Or Audit Reporter

> As Codex child thread, I may be assigned a reviewer or final-verifier role, but I
> need to know whether I am reporting to the main thread or directly producing a
> customer-facing review/audit summary.

Initial direction:

- Default: child thread reports to main thread only.
- Customer-facing review/audit text is allowed only when the TaskFile role and
  report requirements explicitly request it.
- Even when a child thread produces customer-facing text, it must also emit a
  machine-readable handoff with `acceptanceAllowed`, `confidence`, `evidencePaths`,
  and missing gates.

Open design point:

- Whether reviewer/final-verifier child threads should write a separate
  `audit_<run-id>.json/.md` artifact, or whether workflow verifier should generate
  the canonical audit package after collecting reviewer reports.

### Story C: Child Thread Handling Abnormal Framework Feedback

> As Codex child thread, when the framework returns API errors, missing reports, or
> stale/dead process states, I need to know which constraints and specs to read
> before responding.

Initial direction:

- The child thread should read the framework contract and the current spec summary
  when abnormal states appear.
- The main thread should be able to inspect the same contract/spec and understand
  why the child thread returned `WAITING`, `FAILED`, or `TERMINAL`.
- Abnormal feedback must be classified as framework/execution state before the
  child thread makes any business-task statement.

Required output:

```json
{
  "delegateStatus": "FAILED",
  "failureLayer": "claude_api_socket",
  "businessFilesChanged": false,
  "workerReportTrustworthy": false,
  "acceptanceAllowed": false,
  "mainThreadAction": "run_runtime_diagnostics",
  "nextCommand": "ccruntime doctor -ClaudeSmoke --json"
}
```

## DS Roles In The Framework

DS means the built-in DeepSeek report/planning helpers used before dispatch and
after execution.

### Pre-Dispatch DS

Purpose:

- lower hard friction for TaskFile drafting;
- identify missing scope, missing verification, unclear acceptance, or unsafe
  parallelism;
- help the main thread plan delegation without consuming the main thread's deeper
  reasoning budget.

Boundaries:

- advisory only;
- cannot override `validate_delegate_task`;
- cannot edit business files;
- cannot dispatch worker runs;
- must output `mayOverrideValidator=false`.

Current assessment:

- DS is directionally useful for reducing framework friction, but its value should
  be measured by whether it reduces invalid TaskFiles and main-thread rework, not
  by whether it produces long planning prose.

### Post-Execution DS

Purpose:

- normalize reports;
- explain deterministic verifier failures;
- classify failure layer and retry safety;
- draft human-readable forensic summaries when the main thread asks.

Boundaries:

- cannot convert failed deterministic verification into success;
- cannot make final acceptance claims;
- cannot replace spec/quality/final-verifier gates;
- must output `mayOverrideVerifier=false`.

Current assessment:

- DS can reduce hard friction after failures, especially for socket/API errors and
  stale/dead process cases, if its output is constrained to failure layer,
  evidence, retry safety, and next action.

### Can Child Threads Talk To DS?

Initial policy:

- Allowed only through framework-sanctioned report-only runners.
- Allowed for TaskFile assist, report normalization, forensic explanation, and
  audit drafting.
- Not allowed for implementation, direct shell execution, business-file editing,
  or overriding deterministic gates.

Recommended routing:

- Main thread may request DS before dispatch for planning.
- Child thread may request DS only when its TaskFile or role explicitly assigns a
  report-only helper task.
- End-of-run DS should be triggered by verifier/supervisor state, not by an
  unconstrained child-thread improvisation.

This keeps DS useful as a friction reducer while preventing a second uncontrolled
agent layer from making acceptance decisions.

## Implemented `ccstatus`

The framework needs a main-thread-facing status command that answers a different
question from `ccruntime`.

`ccruntime` answers:

> What is configured on this machine?

`ccstatus` answers:

> Can Codex safely dispatch or trust a Claude Code worker right now, and if not,
> where exactly is the chain broken?

Motivating failure message:

```text
Phase 5.3.x product implementation is ready for main-control review/commit, but
strictly speaking the whole phase cannot be accepted as completed by
codex-with-cc-plus Claude Code workers under the current Claude API connection
state.
```

That message is directionally honest but not actionable enough for the main
thread. It should be replaced or accompanied by structured status:

```json
{
  "command": "ccstatus",
  "overall": "blocked",
  "dispatchAllowed": false,
  "acceptanceAllowed": false,
  "runtimeConfigured": true,
  "claudeCliAvailable": true,
  "claudeCliVersion": "2.1.165",
  "backendBaseUrl": "http://127.0.0.1:15721",
  "backendReachable": false,
  "modelHandshake": "not_run_or_failed",
  "lastWorkerFailureLayer": "claude_api_socket",
  "lastKnownGoodWorkerRun": "<run-id-or-empty>",
  "artifactRootWritable": true,
  "recommendedAction": "check_local_claude_or_openclaw_backend",
  "nextCommand": "ccruntime doctor -ClaudeSmoke --json",
  "confidence": "high",
  "evidencePaths": {
    "status": "<latest-status-path>",
    "trace": "<latest-trace-path>",
    "stream": "<latest-stream-path>"
  }
}
```

Implemented subcommands:

- `ccstatus summary --json`: compact main-thread status across runtime, latest
  worker failures, artifact writability, and active runs.
- `ccstatus claude --json`: Claude Code CLI, configured base URL, backend
  reachability, model handshake, and safe redacted settings.
- `ccstatus run -RunId <id> --json`: one run's current state, worker liveness,
  failure layer, report validity, acceptance allowance, and next action.
- `ccstatus audit -RunId <id> --json`: write `audit_<RunId>.json/.md` with
  worker claim, verifier state, missing gates, failure layer, evidence paths, and
  main-thread action.
- `ccstatus workflow -WorkflowId <id> --json`: workflow-level gate state and
  missing review/audit requirements.
- `ccstatus preflight --json`: first-use gate that refuses framework dispatch when
  the Claude Code worker chain is not reliable enough to run.

Relationship to existing commands:

- `ccruntime status`: static runtime inventory.
- `ccruntime doctor`: preflight checks.
- `ccwatch` / `ccsupervise`: run observation.
- `ccindex`: machine memory over artifacts.
- `ccstatus`: main-thread decision summary that can call or compose the above
  evidence sources.

The command should be optimized for Codex consumption first. Human-readable text
is useful, but the primary output is the structured handoff/action object.

### First-Use Claude Code Reliability Gate

Before the first implementation dispatch in a project or after a runtime change,
the framework should run a Claude Code reliability preflight. This may be exposed
as `ccstatus preflight --json` and may also be called by higher-level dispatch
flows.

Preflight must check:

- Claude Code CLI presence and version;
- safe redacted Claude settings;
- configured base URL;
- artifact root writability;
- child-thread marker contract;
- backend reachability;
- minimal model handshake when safe and explicitly supported;
- latest known worker failure layer from local artifacts.

If preflight fails, the framework must refuse implementation dispatch and return
the same refusal semantics to both Codex main thread and child thread:

```json
{
  "delegateStatus": "REFUSED",
  "dispatchAllowed": false,
  "acceptanceAllowed": false,
  "failureLayer": "claude_code_runtime_unavailable",
  "humanInterventionRequired": true,
  "mainThreadAction": "install_or_repair_claude_code",
  "childThreadAction": "do_not_call_delegate_to_claude",
  "userMessage": "Claude Code is not ready. Install, configure, or restart Claude Code/OpenClaw/MiniMax before using this framework for implementation workers.",
  "nextCommand": "ccstatus claude --json",
  "confidence": "high"
}
```

The child thread must treat this refusal as a terminal framework precondition
failure, not as a worker failure and not as business-task failure. It should not
attempt to start Claude Code when `dispatchAllowed=false`.

Human guidance should be direct and non-alarming:

- install or reinstall Claude Code;
- ensure OpenClaw/MiniMax backend is running if the base URL points to localhost;
- verify login/token configuration;
- rerun `ccstatus preflight --json`;
- rerun the same TaskFile only after runtime health is restored.

## Claude Code Instance Boundary

The local Claude Code/OpenClaw/MiniMax instance is an external runtime dependency,
not framework-owned state. The framework should not silently reinstall, mutate,
or repair a user's Claude Code installation.

Framework responsibilities:

- detect whether Claude CLI is present;
- detect configured safe settings and base URL without exposing secrets;
- run safe smoke checks such as CLI version and, in a future phase, a minimal
  model/backend handshake;
- distinguish local runtime failure from TaskFile, runner, worker-report, and
  business-implementation failure;
- produce next actions for the Codex main thread, such as `reinstall Claude Code`,
  `restart local backend`, `check OpenClaw/MiniMax listener`, or `rerun same
  TaskFile after runtime recovery`;
- keep evidence paths and redacted runtime facts for audit.

Non-responsibilities:

- no automatic Claude Code reinstall;
- no automatic token or secret rewriting;
- no direct repair of ccwitch/OpenClaw/MiniMax beyond reporting facts and suggested
  commands;
- no acceptance of worker tasks while runtime health is unknown or failing.

After a human repairs or reinstalls Claude Code, the expected reentry sequence is:

```bash
ccruntime status --json
ccruntime doctor -ClaudeSmoke -ArtifactRoot <writable-root> --json
ccstatus claude --json
ccstatus summary --json
```

`ccruntime status` and `ccruntime doctor` remain lower-level runtime probes, while
run/workflow conclusions still come from `ccwatch`, `ccsupervise`, `ccindex`, and
deterministic verifiers. `ccstatus` composes these facts into the main-thread
decision surface.

## Local Runtime Tooling Discovery

Current local discovery notes from this machine:

- `claude` CLI is on PATH and reports Claude Code `2.1.168`.
- `openclaw` CLI is on PATH and reports OpenClaw `2026.5.27`.
- `cc-switch`, `ccswitch`, and `ccwitch` are not on PATH.
- A cc-switch desktop/app state appears to exist under `~/.cc-switch`,
  `~/Library/Application Support/com.ccswitch.desktop`, and
  `~/Library/Preferences/com.ccswitch.desktop.plist`.

Design implication:

- `ccstatus` and `ccruntime` should report both CLI availability and discovered
  non-PATH app state as separate facts.
- The framework should not assume the desktop tool is operable simply because app
  state exists.
- Future provider adapters may inspect cc-switch metadata in a redacted,
  read-only way, but must not mutate it without explicit confirmation.

## Requirement Queue

### P0: First-Use Claude Code Reliability Gate

Status: implemented.

Before implementation dispatch, verify Claude Code worker readiness. If the gate
fails, return a refusal handoff to both Codex main thread and child thread, guide
the human to install/configure/restart Claude Code/OpenClaw/MiniMax, and prevent
`delegate_to_claude` from starting.

### P0: Main-Thread Handoff Schema

Status: implemented for `REFUSED`, `WAITING`, terminal run summaries, and
canonical run audit artifacts.

Deliver a shared schema used by delegate, supervisor, verifier, DS report workers,
and future dashboard/status tools.

Required fields:

- `delegateStatus`
- `observedState`
- `acceptanceAllowed`
- `mainThreadAction`
- `recommendedWaitSeconds`
- `nextCommand`
- `confidence`
- `failureLayer`
- `humanInterventionRequired`
- `evidencePaths`
- `mayOverrideValidator`
- `mayOverrideVerifier`

### P0: Recommended Wait Policy

Status: implemented in `ccstatus run`.

Implement bounded wait guidance for the main thread and child thread.

Defaults:

- 60 seconds for `STARTING`;
- 60 seconds for `RUNNING_ACTIVE`;
- 300 seconds for quiet-but-not-stale states;
- stop waiting for stale or dead-process states.

All thresholds must be configurable.

### P0: Audit Package

Status: implemented for individual runs through `ccstatus audit`; workflow-level
rollup audits remain a future refinement.

Generate a compact audit package after worker completion or failure.

The audit package must answer:

- can the main thread review this result?
- can the main thread accept this result?
- which gates are missing?
- were declared tests observed?
- were changed files inside scope?
- is this a business failure or an execution-layer failure?
- what should the main thread do next?

### P0: `ccstatus`

Status: implemented.

Implement `ccstatus` as the main-thread decision surface for runtime readiness,
live run state, workflow gates, and failure-layer explanation.

### P1: Child-Thread Contract Enforcement

Status: partially implemented through `ccstatus audit`, contract schema updates,
and child-thread refusal protocol. Additional hook guidance remains open.

Make the child-thread return protocol harder to violate.

Candidate implementation:

- runner-generated handoff artifact;
- child-thread response template;
- tests for `WAITING`, `FAILED`, `REPORT_READY`, and `RUNNING_DEAD_PROCESS`;
- hook guidance that tells child threads to read contract/spec on abnormal states.

### P1: DS Boundary And Routing

Standardize DS as an advisory friction reducer.

Required behavior:

- pre-dispatch DS outputs `mayOverrideValidator=false`;
- post-execution DS outputs `mayOverrideVerifier=false`;
- DS may produce explanations, TaskFile critiques, and forensic summaries;
- DS may not dispatch, implement, edit business files, or accept workflow results.

### P2: PageIndex Failure Fixture

Preserve a representative socket/API failure fixture with:

- valid TaskFile;
- runner/artifact success;
- worker report missing or failed;
- Claude API/socket failure;
- no business acceptance;
- recommended runtime recovery action.

This fixture should prevent regressions where a running/dead/missing-output state
is accidentally treated as success.

## Product Focus

The next phase should optimize the framework around:

1. main-thread handoff schema;
2. recommended wait policy;
3. audit package schema;
4. child-thread waiting and audit responsibilities;
5. DS advisory boundaries and trigger points;
6. `ccstatus` as a main-thread decision surface for Claude Code worker readiness,
   live run state, and failure-layer explanation.

Human CLI and dashboard surfaces should consume these schemas as secondary
interfaces. The primary interface is the structured feedback Codex main thread
receives after dispatch, waiting, failure, review, and verification.
