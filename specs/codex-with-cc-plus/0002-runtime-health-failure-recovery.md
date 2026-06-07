# 0002 Runtime Health And Failure Recovery

## Goal

Make interrupted delegation runs self-explanatory, recoverable, and impossible to
mistake for business success. Codex With CC Plus should tell the main thread where
the chain failed, whether implementation work was trustworthy, and which recovery
path is safe before another worker run is attempted.

This spec applies the AI Design Kernel as a Transparent AI and Ambient Intelligence
surface: uncertainty, provenance, latency, and reversibility must be visible in the
artifact layer, not only in stderr.

## Scope

- Add a deterministic local `doctor` command for pre-dispatch health checks.
- Add structured failure taxonomy to delegate status/config artifacts.
- Make workflow verification prioritize upstream implementer failure before missing
  review gates.
- Reduce hook false positives caused by explanatory text that mentions forbidden
  legacy arguments.
- Preserve existing delegate, report-only, review, and final-verifier contracts.
- Keep runtime artifacts under `.codex/codex_with_cc`.

Explicit exclusions:

- Do not turn report-only forensics into implementation acceptance.
- Do not hide or auto-resolve Claude Code API failures.
- Do not expand this phase into a full framework roadmap.
- Leave a placeholder for a later framework phase only.

## Task Plan

1. Speckit update
   - Record this failure-recovery model as a tracked spec.
   - Add a framework-phase placeholder without design detail.

2. Doctor/preflight
   - Add `doctor` / `ccdoctor` CLI entrypoints.
   - Check repo/artifact root writability, Python runtime, child-thread marker
     expectation, Claude CLI availability, optional Claude CLI smoke probe, and hook
     contract availability.
   - Return JSON with `status`, `checks[]`, `safeToDispatch`, and `recommendedAction`.

3. Failure taxonomy
   - For Claude API failures, write structured fields:
     `artifactContract`, `workerOutcome`, `businessAcceptance`, `failureLayer`,
     `retryable`, `humanActionRequired`, `safeToRetrySameTaskFile`,
     `businessFilesChanged`, and `mayOverrideImplementation`.
   - Preserve the existing human-readable `failureSummary`.

4. Workflow verifier priority
   - If an implementer task has a terminal failed report, fail the workflow with
     "implementer failed before implementation; review gates are not applicable yet"
     before checking missing spec/quality/final-verifier gates.

5. Hook false-positive reduction
   - For spawn-agent prompts, require actual delegate command intent before checking
     command-like forbidden arguments.
   - Explanatory text such as "do not use -Task" must not be blocked by itself.

6. Tests
   - Unit-test doctor output.
   - Unit-test structured failure taxonomy.
   - Unit-test workflow verifier priority on failed implementer artifacts.
   - Unit-test hook explanatory text allowance while keeping actual legacy command
     denial intact.

## Acceptance

- `ccdoctor` can run before dispatch and returns actionable JSON without model calls.
- A Claude API/socket failure is represented as artifact-valid worker failure and
  business acceptance blockage, not a vague implementation result.
- Failed implementer workflows surface the implementer failure first; review gates are
  reported as not applicable yet.
- Hook still blocks actual non-compliant delegate commands, but does not block
  explanatory safety text.
- `mayOverrideImplementation=false` is present on structured execution failures.
- Existing runtime/session-pool selftests continue to pass.

## Verification

- `python -m pytest tests/test_contract_source.py tests/test_platform_hooks.py tests/test_workflow_contract.py tests/test_supervision_and_speckit.py`
- `python -m pytest tests/test_delegate_runtime_selftest.py`
- `./skills/codex-with-cc/macos_scripts/test_delegate_runtime.sh`
- `./skills/codex-with-cc/macos_scripts/test_delegate_session_pool.sh`
- `./skills/codex-with-cc/macos_scripts/ccdoctor.sh --json`

## Decision Log

- Treat "flow interruption" as a first-class outcome, not an exception outside the
  protocol.
- Use deterministic preflight for environment readiness. Model reports may explain
  failures but cannot override doctor/verifier results.
- Keep old `failureSummary` for compatibility while adding structured fields.
- Keep the later "Codex With CC Plus as a framework" phase as a placeholder:
  `0003-framework-roadmap-placeholder.md`. Do not scope it in this phase.
