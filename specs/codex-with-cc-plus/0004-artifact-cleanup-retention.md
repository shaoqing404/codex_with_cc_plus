# 0004 Artifact Cleanup And Retention

## Goal

Add `ccclean` as a deterministic artifact cleanup command that keeps delegation
evidence inspectable while giving users a safe way to reduce old runtime clutter.

This is a Transparent AI maintenance surface. Cleanup decisions must show
provenance, confidence, uncertainty, time cutoff, result filters, and reversibility
before any file is moved.

## Scope

- Add `ccclean list|plan|apply` for delegate artifact roots.
- Prefer workflow-group cleanup over per-file cleanup, so workflow references do not
  point at missing run artifacts.
- Support project/root matching, workflow/run matching, time cutoffs, state filters,
  result filters, role filters, and runner-type filters.
- Move eligible files to a trash root by default instead of permanent deletion.
- Write machine-readable cleanup manifests and local audit artifacts.
- Protect failure, interrupted, running, recent, and orphan artifacts unless the user
  explicitly opts in.

Explicit exclusions:

- Do not silently schedule background cleanup.
- Do not delete task files or session-pool state in this phase.
- Do not turn cleanup into verification or acceptance.
- Do not permanently delete artifacts in the default path.

## Interface Pattern

`ccclean` is a Transparent AI and AI-augmented operations command:

- transparent because it exposes artifact sources, confidence, and protection reasons;
- AI-augmented because it cleans evidence produced by model delegation workflows, but
  the cleanup decision itself stays deterministic and user-controlled.

## Failure-First Design

- Low confidence: mark the item `confidence=low` and protect unsafe referenced paths.
- Timeout/no response: not applicable; command is local and deterministic.
- Empty result: return zero items with selected roots and filters still visible.
- Unexpected result: `apply` requires `-ConfirmDelete` and writes a manifest.
- User rejection: `plan` is non-destructive, and `apply` moves to trash for recovery.

## State Model

```text
SCAN_ROOTS
-> GROUP_WORKFLOWS
-> CLASSIFY_RUNS
-> FILTER_SELECTION
-> PLAN_PROTECTIONS
-> USER_CONFIRMS
-> MOVE_TO_TRASH
-> WRITE_CLEANUP_MANIFEST
```

Protected branches:

- `RECENT_ACTIVITY`: newer than cutoff.
- `FAILURE_EVIDENCE`: failed, blocked, needs-context, interrupted, or concerning run.
- `RUNNING_EVIDENCE`: active or starting run.
- `ORPHAN_EVIDENCE`: run files without workflow provenance.
- `UNSAFE_REFERENCE`: artifact points outside the artifact root.

## Commands

Examples:

```bash
./skills/codex-with-cc/macos_scripts/ccclean.sh list --json
./skills/codex-with-cc/macos_scripts/ccclean.sh plan -OlderThanDays 30
./skills/codex-with-cc/macos_scripts/ccclean.sh plan -ProjectMatch pageindex -Result DONE
./skills/codex-with-cc/macos_scripts/ccclean.sh apply -OlderThanDays 45 -ConfirmDelete
```

Important flags:

- `-ArtifactRoot <dir>`: inspect a specific delegate artifact root.
- `-ProjectRoot <dir>`: inspect that project's local and user fallback roots.
- `-AllProjects`: include user-level fallback artifact roots.
- `-ProjectMatch <text>`: match artifact root, project key, workflow id, or run id.
- `-WorkflowId <id>` / `-RunId <id>`: narrow by workflow or run.
- `-State <state>` / `-Result <result>`: narrow by computed state or report result.
- `-OlderThanDays <n>` / `-OlderThanHours <n>` / `-Before <date>`: choose cutoff.
- `-IncludeFailures`, `-IncludeRunning`, `-IncludeOrphans`: opt into protected classes.
- `-TrashRoot <dir>`: choose the reversible trash destination.
- `-ConfirmDelete`: required for `apply`.

## Acceptance

- `ccclean list` shows matched artifact groups without moving files.
- `ccclean plan` defaults to a 30-day cutoff and dry-run output.
- `ccclean apply` fails unless `-ConfirmDelete` is present.
- Success-only old workflow groups can be moved to trash.
- Failed, interrupted, running, recent, and orphan evidence is protected by default.
- JSON output includes `cleanupType`, filters, totals, confidence, protection reasons,
  `mayOverrideVerifier=false`, and trash manifest paths.
- Existing runtime, supervision, workflow, and wrapper tests continue to pass.

## Verification

- `python -m py_compile skills/codex-with-cc/scripts/ccclean.py skills/codex-with-cc/scripts/codex_with_cc_runtime/cleanup.py`
- `python -m pytest tests/test_supervision_and_speckit.py`
- `python -m pytest tests/test_windows_wrapper_forwarding.py`
- `./skills/codex-with-cc/macos_scripts/ccclean.sh list --json`
- `git diff --check`

## Decision Log

- Use workflow groups as the primary cleanup unit to avoid dangling workflow/run
  references.
- Move files to trash instead of deleting them to preserve reversibility.
- Keep failed and interrupted artifacts by default because they are the highest-value
  forensic samples.
- Leave scheduled cleanup for a later phase after retention policy, UI/reporting, and
  user consent are designed.
