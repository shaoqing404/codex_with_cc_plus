# 0005 Machine Observability, Browser Checks, And Runtime Control

## Goal

Define the next Codex With CC Plus phase for three adjacent needs:

1. browser-capable delegated verification,
2. explicit Claude Code runtime/model/permission visibility and control,
3. a machine-level dashboard over Codex With CC Plus workflows and artifacts.

The phase should make long-running AI delegation understandable at machine scope
without weakening the existing child-thread, artifact, verifier, and cleanup gates.

## Current Answers

### Can Codex With CC Plus delegate direct browser tests?

Partially.

Today an implementation worker can run shell-level browser tests when the target
project provides them, for example Playwright, Cypress, Vitest browser mode, or a
local app smoke command. Those commands can be declared in the TaskFile
`Verification` section and passed through `-Tests`, then recorded in the worker
report and artifacts.

Today a Claude Code worker cannot directly use Codex app tools such as the Browser
plugin or Chrome connector, because the worker is a Claude Code CLI process reached
through `delegate_to_claude.*`, not a Codex tool-owning thread. A Codex child thread
in this workflow is also constrained to invoke the delegate runner, so it should not
silently switch to direct Browser plugin operations.

Next phase should add an explicit Browser Verification lane instead of pretending
Claude Code already owns Codex browser tools.

### Can we query or modify the delegated Claude Code model and permission mode?

Partially.

Current per-run controls:

- `-Model <model>` is accepted by `delegate_to_claude.*` and passed to Claude Code as
  `--model <model>`.
- The model value is recorded in `config_<RunId>.json`.
- `ccviz` attempts to parse the actual streamed model from `stream_<RunId>.jsonl`
  when the backend emits it.
- `--permission-mode acceptEdits` is currently hard-coded by the runner.
- `-BypassPermissions` appends `--dangerously-skip-permissions` and records
  `bypassPermissions=true`.

Current gaps:

- There is no `ccruntime` or `ccmodel` command to query Claude Code / ccwitch backend
  state before dispatch.
- There is no supported command to switch ccwitch-managed model/provider from inside
  Codex With CC Plus.
- There is no arbitrary `-PermissionMode` option; only the hard-coded
  `acceptEdits` plus optional bypass flag exists.
- The Codex child-thread model is fixed by contract as `gpt-5.4-mini`; this should
  remain separate from the Claude Code worker model.

### Is a complete delegation recorded and readable?

Mostly, at artifact-root scope.

Current artifacts include:

- `workflow_<WorkflowId>.json`
- `config_<RunId>.json`
- `status_<RunId>.json`
- `prompt_<RunId>.md`
- `stream_<RunId>.jsonl`
- `trace_<RunId>.log`
- `claude_<RunId>.md` or `report_<RunId>.md`
- `session-pools/<SessionKey>.json`
- `supervisor_<RunId>.json/.md`
- `ccclean_<timestamp>.json/.md` and cleanup trash manifests when cleanup runs

Current readability tools:

- `ccwatch` for run/workflow state summaries.
- `ccsupervise` for run observation artifacts.
- `ccviz list|show|audit` for workflow inspection.
- `ccclean list|plan|apply` for reversible cleanup planning.

Current gap:

- These tools are still centered on the current project or explicit artifact root.
  There is no machine-level index that scans every project fallback root, no local
  web dashboard, and no Codex Sites view.

## AI Design Lens

Dominant interface pattern: Transparent AI with ambient monitoring.

Design requirements:

- Show provenance for every displayed state: workflow artifact, status artifact,
  stream line, report heading, or supervisor result.
- Show confidence for runtime state: high when all core artifacts parse, medium when
  a report is missing but status is terminal, low when references are broken.
- Separate retrieved facts from generated interpretation. The dashboard must label
  artifact-derived facts separately from any optional model-written summary.
- Keep automation reversible. Dashboard actions should default to plan/dry-run and
  link to `ccclean` manifests or retry TaskFiles.
- Expose latency and staleness. Running states must show last activity, PID alive,
  stale threshold, and recommended action.
- Parameterize thresholds: stale seconds, recent artifact window, cleanup retention,
  failure severity, and dashboard refresh interval.

## Product Surface

### 1. Browser Verification Lane

Add a first-class `browser-verifier` workflow lane with two supported execution
styles:

- Shell Browser Tests: Claude Code worker runs project-provided Playwright/Cypress
  commands through `-Tests`.
- Codex Browser Check: Codex main thread or a dedicated Codex browser verifier runs
  Browser/Chrome tool checks after implementation, then writes a browser evidence
  artifact into the same workflow.

Required artifacts:

- `browser_<RunId>.json`: URL, viewport, action log, screenshots, assertions,
  confidence, and failure classification.
- `browser_<RunId>.md`: human-readable acceptance report.

Rules:

- Claude Code workers must not claim they used Codex Browser plugin unless evidence
  is present in browser artifacts.
- Browser artifacts may support acceptance but must not override
  `verify_delegate_workflow.*`.
- Browser actions against logged-in user sessions require explicit user consent.

### 2. Runtime Doctor And Control

Add `ccruntime` with read-first behavior:

```bash
ccruntime status --json
ccruntime doctor -ClaudeSmoke --json
ccruntime plan-switch -Model <model> -PermissionMode <mode> --json
ccruntime apply-switch -Model <model> -PermissionMode <mode> -ConfirmRuntimeChange
```

Phase 1 should implement status and planning before any mutation:

- detect Claude CLI path and version,
- show configured per-run default model,
- show supported permission modes,
- show whether `ccwitch` is present,
- if possible, read ccwitch current provider/model without secrets,
- report whether the next delegate run can safely use the requested model.

Mutation rules:

- Never change ccwitch/global Claude config without `-ConfirmRuntimeChange`.
- Record changes in `runtime_<timestamp>.json/.md`.
- Store previous state when discoverable so rollback instructions can be shown.
- Do not write API keys or auth tokens to artifacts.

Recommended default:

- Keep `-Model` as the per-run override.
- Add `-PermissionMode` only after tests prove Claude CLI supports the selected
  values.
- Keep `-BypassPermissions` explicit and noisy.

### 3. Machine Workflow Index

Add `ccindex` as the machine-level indexer:

```bash
ccindex build --json
ccindex list --ProjectMatch pageindex
ccindex show <workflow-id>
ccindex export -Output .codex/codex_with_cc/index/index.json
```

Scan roots:

- each known project `.codex/codex_with_cc/claude-delegate`,
- `$CODEX_HOME/codex_with_cc/claude-delegate/<project-key>`,
- optional extra roots from config.

Index records:

- project key and probable project root,
- workflow id, task ids, run ids, role, scope, status, final result,
- model requested vs streamed model,
- permission mode and bypass flag,
- last activity, PID state, staleness,
- report path and summary,
- verification evidence and missing gates,
- cleanup eligibility/protection reason,
- artifact confidence and parse errors.

### 4. Dashboard

Add a local read-only dashboard fed by `ccindex`.

First implementation should be static or local-file friendly:

- generate `dashboard/index.html` plus `index.json`,
- or publish through Codex Sites only after local static output is stable.

Views:

- Machine Overview: active/stale/failed/accepted counts by project.
- Project View: workflows, tasks, run states, recent failures.
- Workflow View: state machine, artifacts, report excerpts, verifier gates.
- Run View: prompt/status/stream/trace/report links, model and permission metadata.
- Cleanup View: `ccclean plan` summary and protected evidence.
- Browser Evidence View: screenshots/actions/assertions when browser artifacts exist.

Actions should be staged:

- Open artifact path.
- Copy verifier command.
- Generate retry TaskFile suggestion.
- Run `ccclean plan`.
- Later: apply cleanup or runtime switch only with explicit confirmation outside the
  read-only dashboard.

## State Machines

Browser verification:

```text
IMPLEMENTATION_DONE
-> BROWSER_CHECK_PLANNED
-> APP_STARTED_OR_URL_CONFIRMED
-> BROWSER_ACTIONS_RUN
-> ASSERTIONS_CAPTURED
-> BROWSER_EVIDENCE_WRITTEN
-> WORKFLOW_VERIFIER_CONSUMES_EVIDENCE
```

Runtime control:

```text
STATUS_READ
-> SWITCH_PLAN_CREATED
-> USER_CONFIRMS_RUNTIME_CHANGE
-> RUNTIME_CHANGE_APPLIED
-> SMOKE_PROBE_RUN
-> NEXT_DELEGATE_RECORDS_EFFECTIVE_MODEL
```

Machine dashboard:

```text
SCAN_ROOTS
-> PARSE_ARTIFACTS
-> CLASSIFY_CONFIDENCE
-> BUILD_INDEX
-> RENDER_DASHBOARD
-> USER_TAKES_EXPLICIT_ACTION
```

## Failure-First Design

- Low confidence: show artifact parse errors and hide destructive actions.
- Timeout/no response: show stale seconds, PID status, stream tail, and supervisor
  recommendation.
- Empty result: show scanned roots and explain no workflows found.
- Unexpected result: show requested model vs streamed model mismatch.
- User rejection: runtime switch and cleanup remain plan-only unless explicitly
  confirmed.

## Technical Plan

1. Add `ccruntime status` without mutation.
2. Add `ccindex build/list/show` over project and user fallback artifact roots.
3. Extend `ccviz` or reuse `ccindex` parser so there is one artifact interpretation
   layer.
4. Add browser evidence schema and deterministic validator.
5. Add dashboard generator from index JSON.
6. Optional later: Codex Sites deployment for a richer local observability page.

## Acceptance

- Current capabilities and gaps above are reflected in docs and commands.
- `ccruntime status --json` reports model/permission/runtime information without
  secrets.
- `ccindex build --json` scans machine-level artifact roots and emits confidence.
- Dashboard can render from local JSON without a model call.
- Browser evidence artifacts can be validated and linked into workflow acceptance.
- Runtime mutation is impossible without explicit confirmation.
- Existing delegate, supervisor, cleanup, and verifier tests remain green.

## Verification

- `python -m pytest tests/test_supervision_and_speckit.py`
- `python -m pytest tests/test_workflow_contract.py`
- `./skills/codex-with-cc/macos_scripts/ccclean.sh plan --json`
- Future:
  - `./skills/codex-with-cc/macos_scripts/ccruntime.sh status --json`
  - `./skills/codex-with-cc/macos_scripts/ccindex.sh build --json`
  - Dashboard render snapshot test.

## Decision Log

- Keep direct Codex Browser plugin usage outside Claude Code worker claims until a
  dedicated browser evidence lane exists.
- Treat `-Model` as per-run Claude Code model selection; do not mix it with the
  Codex child-thread model.
- Treat permission bypass as a high-salience runtime risk.
- Prefer local static dashboard first; use Codex Sites after the data contract is
  stable.
