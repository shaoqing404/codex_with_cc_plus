# 0006 Command Taxonomy, Runtime Control, Index, And Dashboard

## Goal

Implement the deep-water command reorganization phase without expanding into a
Docker service or background API. The phase adds controlled runtime visibility,
machine-level workflow indexing, and a static local dashboard while preserving the
existing delegate, verifier, supervisor, and cleanup gates.

## Command Taxonomy

Public commands are grouped by governance object:

- Spec/Task: `ccspec`, `validate_delegate_task`
- Dispatch: `delegate_to_claude`, `delegate_to_openai_compatible_report`
- Verify: `verify_delegate_run/artifacts/workflow/chain`
- Observe: `ccwatch`, `ccsupervise`, `ccviz`
- Retention: `ccclean`
- Runtime: `ccdoctor`, `ccruntime`
- Machine Index: `ccindex`
- Dashboard: `ccdash`

`ccserver` and `ccapi` are intentionally left for a later framework phase.

## Runtime Control

`ccruntime` is a Transparent AI runtime surface:

```bash
ccruntime status --json
ccruntime doctor -ClaudeSmoke --json
ccruntime plan-switch -Model opus -PermissionMode acceptEdits --json
ccruntime apply-switch -Model opus -PermissionMode acceptEdits -ConfirmRuntimeChange
```

Rules:

- `status` reads Claude CLI, OpenClaw, runner defaults, redacted Claude settings,
  and read-only `ccswitchProvider` facts from ccwitch/ccswitch/cc-switch CLI
  discovery plus known desktop state paths.
- `plan-switch` is dry-run and records the next delegate `-Model` and
  `-PermissionMode` arguments.
- `apply-switch` requires `-ConfirmRuntimeChange`, changes only whitelisted Claude
  settings fields, writes `runtime_<timestamp>.json/.md`, and creates rollback
  backup evidence when settings change.
- Secrets are never written to runtime artifacts; token fields are reduced to
  presence booleans.
- Permission mode remains a delegate runner argument. It is not silently persisted
  as hidden global state.

## Machine Index And Dashboard

`ccindex` builds a machine-level view from project and user fallback artifact roots:

```bash
ccindex build --json
ccindex list --ProjectMatch pageindex
ccindex show <workflow-id>
ccindex export -Output .codex/codex_with_cc/index/index.json
```

Each record includes workflow/run ids, project root, state counts, final results,
requested and streamed model, permission mode, bypass flag, confidence, provenance,
parse gaps, and `mayOverrideVerifier=false`.

`ccdash` renders `ccindex` output into a local static dashboard:

```bash
ccdash build --json
ccdash open
```

The first dashboard is deliberately read-only and file-based. Docker, SQLite/API,
and Codex Sites deployment are deferred until the artifact interpretation contract
is stable.

## AI Design Lens

Interface pattern: Transparent AI with ambient monitoring.

Failure-first paths:

- Low confidence: show confidence and provenance instead of hiding parse gaps.
- Timeout/no response: surface stale and dead-process states from artifacts.
- Empty result: show scanned roots and an empty dashboard state.
- Unexpected result: show requested model versus streamed model mismatch.
- User rejection: runtime mutation stays impossible without explicit confirmation.

Automation is visible, reversible, and overridable only by the human/Codex main
thread. Indexes and dashboards never override deterministic verifiers.

## Field Feedback From PageIndex

The PageIndex Service workflow confirmed the product boundary: codex-with-cc-plus
is useful as a governed delegation framework because workers can be dispatched,
TaskFiles validated, artifacts written, and workflow evidence inspected. The
failure was not a business-task boundary failure; the weak point was execution
reliability when Claude Code reached an unavailable local/API socket.

Observed product lesson:

- The artifact and review shell is valuable: it preserved status, prompt, trace,
  stream, workflow, and report paths even during worker failure.
- A `status: running` artifact with missing output, stale process, or API error
  must remain non-terminal until supervisor/verifier evidence says otherwise.
- The framework needs health diagnosis and recovery guidance before and after
  dispatch, which this phase addresses through `ccruntime`, `ccindex`, `ccdash`,
  and the child-thread return protocol.
- Automatic recovery must remain conservative. A socket/API failure may generate
  forensic context, but it cannot be accepted as implementation success.

## Acceptance

- `delegate_to_claude.*` supports `-PermissionMode` while defaulting to
  `acceptEdits`.
- `ccruntime` reports Claude/OpenClaw/cc-switch provider/runtime settings without
  secrets and can apply confirmed whitelisted Claude settings changes with
  rollback evidence.
- `ccindex` emits a machine-level JSON index with confidence and provenance.
- `ccdash` renders a local static read-only HTML dashboard from the index.
- macOS and Windows wrappers are thin forwarding scripts.
- Tests cover runtime redaction/apply, permission mode forwarding, index, dashboard,
  child-thread waiting protocol, and wrapper registration.

## Verification

- `uvx pytest -q`
- `skills/codex-with-cc/macos_scripts/test_delegate_runtime.sh`
- `skills/codex-with-cc/macos_scripts/test_delegate_session_pool.sh`
- `skills/codex-with-cc/macos_scripts/ccruntime.sh status --json`
- `skills/codex-with-cc/macos_scripts/ccruntime.sh plan-switch -Model opus -PermissionMode acceptEdits --json`
- `skills/codex-with-cc/macos_scripts/ccindex.sh build --json`
- `skills/codex-with-cc/macos_scripts/ccdash.sh build --json`
- `git diff --check`
