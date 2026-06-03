# AI Install Contract

This file is for AI agents installing, updating, or operating Codex With CC Plus.

Current repository:

```text
https://github.com/shaoqing404/codex_with_cc_plus
```

Codex plugin manifest:

```text
.codex-plugin/plugin.json
```

This repository provides a Codex plugin entry, not a Claude host plugin.

Workflow root inside the plugin:

```text
skills/codex-with-cc
```

Do not use a nonexistent skill-level manifest path.

## Operating Policy

Default behavior:

1. Do the install/update directly when the user asks.
2. Prefer user-scope plugin install.
3. Use macOS as the primary supported path when the host is macOS.
4. Do not mutate system Python; use `uv`, `uvx`, or project-local environments for Python checks.
5. Do not print API keys.
6. Do not copy files into fallback skill paths unless marketplace install is unavailable or the user explicitly asks for local fallback.
7. Do not replace this workflow with default Codex subagents.

## Trigger Rule

Any mention of child-agent, subagent, sub-agent, child-thread, subthread, delegation, worker-execution, 子代理, 子线程, 多代理, 委派, 派工, or 执行层 triggers codex-with-cc routing.

Required chain:

```text
Codex main thread
-> Codex child thread
-> local delegate runner
-> Claude Code CLI or OpenAI-compatible report model
-> artifacts
-> Codex main thread / human final judgment
```

## Runner Separation

```text
Task file format check
-> validate_delegate_task.*
-> local deterministic zero-token hard gate

Implementation worker
-> delegate_to_claude.*
-> Claude Code CLI
-> can edit scoped files and run verification

Report / audit worker
-> delegate_to_openai_compatible_report.*
-> DeepSeek Flash or compatible OpenAI API
-> read-only judgment; no shell tests
```

`validate_delegate_task.*` is not a DeepSeek verifier. It only checks TaskFile sections, role metadata, reviewer metadata, declared `-Tests`, placeholders, and report headings.

Optional task-file assist may use `delegate_to_openai_compatible_report.*` to explain a validation failure or draft a corrected TaskFile. It must state `mayOverrideValidator=false`. The corrected TaskFile still must pass local validation.

## Marketplace Install

Ensure Codex CLI exists:

```bash
command -v codex || npm i -g @openai/codex
```

Add this repository itself as the Codex marketplace source:

```bash
codex plugin marketplace add shaoqing404/codex_with_cc_plus --ref master
```

Install the plugin from that marketplace:

```bash
codex plugin add codex-with-cc@codex-with-cc-plus
```

This works because the repository includes:

```text
.agents/plugins/marketplace.json
```

The plugin itself still uses:

```text
.codex-plugin/plugin.json
```

Do not fork or depend on `aiskyhub/aiskyhub` for the normal install path. A third-party public marketplace PR is optional distribution, not ownership and not required registration.

## Local Fallback Install

Use only when marketplace install is not available or the user asks for local skill binding.

```bash
git clone git@github.com:shaoqing404/codex_with_cc_plus.git
mkdir -p ~/.codex/skills
rm -rf ~/.codex/skills/codex-with-cc
cp -r codex_with_cc_plus/skills/codex-with-cc ~/.codex/skills/
```

Equivalent user skill path: `$HOME/.codex/skills/codex-with-cc`.

Windows equivalent user skill path: `$env:USERPROFILE\.codex\skills\codex-with-cc`.

Then tell Codex in the target project:

```text
请把本地 ~/.codex/skills/codex-with-cc 子代理工作流绑定并应用到我当前的项目中。
```

## Cleanup Before Install

Remove legacy project-local copies if present:

- `docs/codex_with_cc`
- `doc/codex_with_cc`
- `.codex/skills/codex-with-cc`
- managed `<!-- BEGIN CODEX_WITH_CC --> ... <!-- END CODEX_WITH_CC -->` block in `AGENTS.md`

If `AGENTS.md` becomes empty after removing the managed block, it may be deleted.

## Environment

For report-only workers:

```env
DEEPSEEK_API_KEY=sk-...
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash
OPENAI_COMPATIBLE_TIMEOUT_SECONDS=600
```

Accepted aliases:

- `OPENAI_API_KEY`
- `OPENAI_COMPATIBLE_API_KEY`
- `OPENAI_BASE_URL`
- `OPENAI_COMPATIBLE_BASE_URL`
- `OPENAI_MODEL`
- `OPENAI_COMPATIBLE_MODEL`

Never write secrets into artifacts, prompts, reports, logs, or final answers.

## Dispatch Contract

This workflow uses the `workflow/task/run` artifact schema.

Every worker command must pass:

- `-TaskFile`
- `-WorkflowId`
- `-TaskId`
- `-Role`
- `-SessionKey`

Implementation workers should normally include:

- `-Scope`
- `-SessionMode PrimaryReuse`
- `-BypassPermissions` when the user accepts local trusted execution

Parallel writable workers must include explicit non-overlapping `-Scope`.

Reviewer workers must include:

- `-ReviewForTaskId`
- `-ReviewKind spec` or `-ReviewKind quality`

Worker reports must use:

```text
Status / Role / Summary / Changed Files / Verification / Findings / Final Result / Risks Or Follow-ups
```

## Long-Run Policy

Implementation workers may run for a long time. That is expected.

Do not make Codex main thread use `sleep` to babysit a live implementation run. Instead:

Do not keep the main agent busy with blind `sleep` loops.

1. Record `RunId`, `statusPath`, `rawStreamPath`, `tracePath`, and `outputPath`.
2. Let Claude Code finish and produce the structured report.
3. Use `ccviz show <workflow-id>`, `ccviz audit <workflow-id>`, or status JSON checkpoints to reconnect.
4. If a run is truly stale, inspect PID/status/stream before deciding whether to rework or recover.

Optional explicit controls:

- `-MaxBudgetUsd <amount>`: cost brake.
- `-MaxTurns <n>`: turn-count brake.
- `-IncludePartialMessages`: more detailed stream events.

These are not defaults. Defaults favor full worker completion.

## macOS Commands

Validate a TaskFile:

```bash
/absolute/path/to/skills/codex-with-cc/macos_scripts/validate_delegate_task.sh \
  -TaskFile ./.codex/codex_with_cc/tasks/<task-file>.md \
  -Role implementer \
  -Tests "pytest -q"
```

Run implementation worker:

```bash
env CODEX_CLAUDE_CHILD_THREAD=1 \
  /absolute/path/to/skills/codex-with-cc/macos_scripts/delegate_to_claude.sh \
  -TaskFile ./.codex/codex_with_cc/tasks/<task-file>.md \
  -WorkflowId <workflow-id> \
  -TaskId <task-id> \
  -Role implementer \
  -SessionKey <session-key> \
  -Scope <path-or-module> \
  -SessionMode PrimaryReuse \
  -BypassPermissions
```

Run report-only worker:

```bash
env CODEX_CLAUDE_CHILD_THREAD=1 DEEPSEEK_MODEL=deepseek-v4-flash \
  /absolute/path/to/skills/codex-with-cc/macos_scripts/delegate_to_openai_compatible_report.sh \
  -TaskFile ./.codex/codex_with_cc/tasks/<task-file>.md \
  -WorkflowId <workflow-id> \
  -TaskId <task-id> \
  -Role researcher \
  -SessionKey <session-key> \
  -Scope <path-or-artifact> \
  -Tests "report-only; do not run shell commands"
```

Do not assign `WORKFLOW_ROOT=...` and expand `"$WORKFLOW_ROOT/..."` in the same zsh simple command. Use a prior exported variable or an absolute path.

## Verification

After install/update:

Use `<installed-workflow-root>` for the installed `skills/codex-with-cc` directory.

```bash
./skills/codex-with-cc/macos_scripts/test_delegate_runtime.sh
./skills/codex-with-cc/macos_scripts/test_delegate_session_pool.sh
uvx pytest -q
```

Windows wrapper parity checks:

```text
test_delegate_runtime.ps1
test_delegate_session_pool.ps1
```

Inspect workflow artifacts:

```bash
./skills/codex-with-cc/macos_scripts/verify_delegate_run.sh -RunId <run-id>
./skills/codex-with-cc/macos_scripts/verify_delegate_workflow.sh -WorkflowId <workflow-id>
./skills/codex-with-cc/macos_scripts/ccviz.sh list
./skills/codex-with-cc/macos_scripts/ccviz.sh show <workflow-id>
./skills/codex-with-cc/macos_scripts/ccviz.sh audit <workflow-id>
```

## Final Report To User

Only say the workflow is ready after verification.

When done, report:

- install/update status
- marketplace or local fallback used
- old files cleaned
- self-tests run
- dry-run install verification or real workflow verification result
- any remaining action for the user
- exact blocker if collaborator invitation or marketplace publication could not be completed
