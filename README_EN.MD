# Codex With CC Plus

[中文](README.md) | English

Codex With CC Plus is an auditable multi-worker workflow for Codex. Codex stays the planner, dispatcher, reviewer, acceptance owner, and final judge. Expensive, long-running implementation work that changes code is delegated to Claude Code, while low-cost, high-frequency, read-only report and audit work can run through DeepSeek, MiniMax, MiMo, or another OpenAI-compatible API.

If you are Codex and the user asks you to install or update this workflow, read [AI_INSTALL.md](AI_INSTALL.md) first.

## Token Price Snapshot

Prices change. This table is a routing reference as of 2026-06-03 only. Use the official pricing pages as the source of truth for final billing and exact API model ids.

| Provider | Model / Tier | Context note | Input cache hit / 1M tokens | Input cache miss / 1M tokens | Output / 1M tokens | Official link |
| --- | --- | --- | ---: | ---: | ---: | --- |
| DeepSeek | `deepseek-chat` | 64K context, 8K max output | $0.07 | $0.27 | $1.10 | [DeepSeek pricing](https://api-docs.deepseek.com/quick_start/pricing-details-usd) |
| DeepSeek | `deepseek-reasoner` | 64K context, 32K max CoT, 8K max output | $0.14 | $0.55 | $2.19 | [DeepSeek pricing](https://api-docs.deepseek.com/quick_start/pricing-details-usd) |
| MiniMax | `MiniMax-M3` standard, <=512K input | listed 7-day 50% off price | $0.06 prompt cache read | $0.30 input | $1.20 | [MiniMax Token Plan](https://platform.minimaxi.com/subscribe/token-plan?code=8Qv3X7oLng&source=link) |
| MiniMax | `MiniMax-M2.7` | standard LLM tier | $0.06 prompt cache read | $0.30 input | $1.20 | [MiniMax Token Plan](https://platform.minimaxi.com/subscribe/token-plan?code=8Qv3X7oLng&source=link) |
| MiMo | MiMo 2.5 Pro overseas PAYG | 1M context, 128K max output | $0.0036 | $0.435 | $0.87 | [MiMo Pay-as-you-go](https://platform.xiaomimimo.com/docs/en-US/price/pay-as-you-go) |
| MiMo | MiMo 2.5 overseas PAYG | 1M context, 128K max output | $0.0028 | $0.14 | $0.28 | [MiMo Pay-as-you-go](https://platform.xiaomimimo.com/docs/en-US/price/pay-as-you-go) |
| MiMo | MiMo Flash overseas PAYG | 256K context, 64K max output | $0.01 | $0.10 | $0.30 | [MiMo Pay-as-you-go](https://platform.xiaomimimo.com/docs/en-US/price/pay-as-you-go) |

This is the fun part: the workflow does not burn the most expensive model on every tiny judgment. Cheap models can handle preflight, normalization, report review, and failure forensics. Claude Code focuses on real implementation. Codex main thread stays clear-headed, reviews evidence, and owns acceptance. The whole thing feels less like waiting in a fog and more like running a small, accountable engineering room.

![Codex With CC Plus execution chain](docs/assets/codex-with-cc-plus-chain.svg)

![Codex With CC Plus state machine](docs/assets/codex-with-cc-plus-state-machine.svg)

## What It Does

Codex With CC Plus turns a vague “use subagents” request into a controlled workflow with state, boundaries, and evidence:

- Codex main thread plans the task graph, defines scope, reviews evidence, and decides final acceptance.
- Task files make worker intent explicit: `Goal`, `Allowed Scope`, `Forbidden Actions`, `Acceptance Criteria`, `Verification`, and `Report Requirements`.
- `validate_delegate_task.*` is a local deterministic zero-token hard gate before dispatch.
- Implementation workers run through `delegate_to_claude.* -> Claude Code CLI`.
- Report-only workers run through `delegate_to_openai_compatible_report.* -> DeepSeek Flash / OpenAI-compatible API`.
- Every run writes artifacts: `config`, `status`, `prompt`, `stream`, `trace`, `report`, and workflow aggregate JSON.
- `ccviz` lets you inspect workflow status, topology, cost, stale runs, and review/audit gates.

The big idea is simple: let workers do the noisy work, but keep accountability with Codex main thread and the human.

## Why It Exists

Large AI coding tasks often fail in boring ways: the main agent gets buried in logs, worker context is implicit, parallel writes overlap, reviews trust summaries too much, and long implementation runs make the main thread wait while nothing useful happens.

Codex With CC Plus gives that process a state machine. It is not a magic prompt. It is a small protocol for task files, child-thread dispatch, deterministic validation, artifacts, review gates, and final acceptance.

## Learning Relationship

This project learns from and references the original `codex-with-cc` / Codex with CC workflow idea: Codex as leader, Claude Code as execution worker, and a cheaper model layer for high-volume reasoning. Codex With CC Plus is an independent continuation focused on stricter artifacts, OpenAI-compatible report runners, `ccviz` observability, and Codex plugin / marketplace distribution.

If you reuse this work, preserve the attribution and the MIT license.

## Platform Recommendation

Use macOS first.

The main development path, real long-running worker path, shell wrappers, and runtime self-tests are maintained primarily on macOS. Windows wrappers are kept as thin compatibility entrypoints and are tested, but they are not the recommended first-line operating environment.

## Mental Model

```text
Dispatch planning
-> DeepSeek V4-Pro Dispatch Planner
-> spec / workflow / TaskFile draft
-> local validation still decides

Task file format check
-> local validate_delegate_task.*
-> zero-token deterministic hard gate

Implementation task
-> Codex child thread
-> delegate_to_claude.*
-> Claude Code CLI
-> structured report

Report / audit task
-> Codex child thread
-> delegate_to_openai_compatible_report.*
-> DeepSeek Flash or compatible OpenAI API
-> structured report

Run observation
-> Codex child thread Run Supervisor
-> ccwatch / ccsupervise
-> supervisor_<RunId>.json/.md

Final judgment
-> Codex main thread + human
-> verify artifacts, review diffs, accept or rework
```

Long implementation tasks should be allowed to finish. Do not make Codex main thread sleep and babysit, and do not keep hand-writing `find/git status/ls` polling commands. Record `RunId`, `statusPath`, `rawStreamPath`, and `tracePath`, prefer a Run Supervisor with `ccwatch` / `ccsupervise` for a specific run, then reconnect at workflow level through `ccviz show` or `ccviz audit`.

Do not let the main thread burn cycles idling.

Optional controls such as `-MaxBudgetUsd`, `-MaxTurns`, and `-IncludePartialMessages` are explicit observability or emergency brake tools. They are not default limits.

## State Machine

1. **Intent**: the user asks for child-agent / subagent / delegation / multi-agent work.
2. **Plan**: Codex main thread creates scoped TaskFiles.
3. **Validate**: local `validate_delegate_task.*` checks structure and metadata.
4. **Dispatch**: Codex creates a child thread with `model: gpt-5.4-mini`, `reasoning_effort: medium`, and `fork_context: false`.
5. **Run**: child thread calls exactly one delegate runner with `CODEX_CLAUDE_CHILD_THREAD=1`.
6. **Artifact**: runner writes config/status/prompt/stream/trace/report/workflow artifacts.
7. **Review**: reviewers verify spec and quality; final verifier checks aggregate evidence.
8. **Accept or Rework**: Codex main thread and human decide.

## Dispatch Planner / Run Supervisor

Codex With CC Plus now splits startup planning and long-run observation into clearer roles:

- **Dispatch Planner**: default `deepseek-v4-pro`. It turns user goals into specs, workflow plans, TaskFile drafts, and risk notes. It cannot execute shell commands, edit business files, or bypass `validate_delegate_task.*`.
- **Report Worker**: default `deepseek-v4-flash`. It handles cheap preflight, report normalization, audit summaries, and lightweight validator explanations.
- **Run Supervisor**: owned by a Codex child thread. It observes one delegated run's artifacts, runs deterministic verification, and writes `supervisor_<RunId>.json/.md` so the main thread receives structured feedback.
- **Forensic Analyst**: default `deepseek-v4-pro`. It only runs after a deterministic verifier failure or explicit human request, explains failure and risk, and must write `mayOverrideVerifier=false`.

Common observation commands:

```bash
./skills/codex-with-cc/macos_scripts/ccwatch.sh -RunId <run-id>
./skills/codex-with-cc/macos_scripts/ccwatch.sh -WorkflowId <workflow-id> --json
./skills/codex-with-cc/macos_scripts/ccsupervise.sh -RunId <run-id>
./skills/codex-with-cc/macos_scripts/ccspec.sh list
```

## Install

### Software Versions

The software actually used for installation and the recommended versions are:

**Required At Runtime**

| Software | Actual Local Version | Recommended Version | Purpose |
|---|---:|---:|---|
| Codex CLI | `0.137.0` | `>= 0.137.0` | `plugin marketplace/list/add/remove` |
| Node.js | `v24.15.0` | `>= 20 LTS` | Runs plugin hooks; `hooks.json` directly calls `node --input-type=module` |
| zsh | `5.9` | `>= 5.9` | macOS wrapper scripts |
| Python | `3.14.5` | Runtime `>= 3.9`; testing recommended `>= 3.11` | delegate/runtime/ccviz/verify scripts |
| Claude Code CLI | `2.1.141` | `>= 2.1.141` or latest | Real `delegate_to_claude` worker execution |

**Used For Installation / Verification**

| Software | Actual Local Version | Recommended Version | Purpose |
|---|---:|---:|---|
| Git | `2.48.1` | `>= 2.40` | Marketplace fetches the GitHub repository |
| curl | `8.7.1` | `>= 8.0` | Used here to read remote manifests/install docs |
| jq | `1.7.1` | `>= 1.7` | JSON manifest/status checks |
| ripgrep / `rg` | `15.1.0` | `>= 14` | Search configuration and source |
| uv / uvx | `0.10.9` | `>= 0.10` | Temporarily run pytest without mutating system Python |
| pytest | `9.0.3` | `>= 8.4` | Repository self-tests |
| npm | `11.12.1` | `>= 10` | Only needed to install/update Codex CLI |

**Optional / Scenario-Dependent**

| Software / Config | Recommendation | Purpose |
|---|---|---|
| PowerShell / `pwsh` | `>= 7.4` | Only needed for Windows wrappers or cross-platform parity tests |
| DeepSeek/OpenAI-compatible API Key | `DEEPSEEK_API_KEY`, `OPENAI_API_KEY`, etc. | Only needed by `delegate_to_openai_compatible_report` report workers |
| Network access | Can reach GitHub, Claude Code, and optional OpenAI-compatible APIs | Installation, real delegation, report workers |

Bottom line: runtime mainly depends on `Codex CLI + Node.js + zsh + Python + Claude Code CLI`. The Python runtime mostly uses the standard library, so the plugin itself does not need extra Python packages; `pytest` is only for installation verification.

### Codex Plugin Marketplace

This repository is self-indexed for Codex. Add this repository itself as a marketplace source:

```bash
codex plugin marketplace add shaoqing404/codex_with_cc_plus --ref master
```

Then install the plugin from that marketplace:

```bash
codex plugin add codex-with-cc-plus@codex-with-cc-plus
```

The marketplace manifest lives at:

```text
.agents/plugins/marketplace.json
```

The plugin manifest lives at:

```text
.codex-plugin/plugin.json
```

Optional public index registration is only for discovery. A PR to a third-party public marketplace such as `aiskyhub/aiskyhub` is not required for this repository to install in Codex, and `shaoqing404/aiskyhub` must not be treated as the project home.

The project home is always `https://github.com/shaoqing404/codex_with_cc_plus`.

### Local Fallback

```bash
git clone git@github.com:shaoqing404/codex_with_cc_plus.git
mkdir -p ~/.codex/skills
cp -r codex_with_cc_plus/skills/codex-with-cc ~/.codex/skills/
```

Then ask Codex inside your target project:

```text
Bind and apply the local ~/.codex/skills/codex-with-cc subagent workflow to my current project.
```

Repository install/update prompt:

```text
Install or update the https://github.com/shaoqing404/codex_with_cc_plus subagent workflow in the current Codex environment.
```

## Environment

For report-only workers and task-file assist:

```env
DEEPSEEK_API_KEY=sk-...
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash
OPENAI_COMPATIBLE_TIMEOUT_SECONDS=600
```

Supported API key aliases include `OPENAI_API_KEY` and `OPENAI_COMPATIBLE_API_KEY`. API keys must never be written to artifacts.

## Start Prompts

Use these prompts to trigger the workflow:

```text
You are responsible for decomposition, dispatch, review, and final delivery. Split this task into multiple codex-with-cc subagent tasks. Each task must include a TaskFile, Allowed Scope, Forbidden Actions, Verification, and Report Requirements. Send implementation tasks to Claude Code and report/audit tasks to DeepSeek Flash. You own final acceptance; do not let workers expand their own scope.
```

```text
Use the codex-with-cc multi-child-thread workflow to audit this project: one researcher reviews architecture, one researcher reviews testing risk, one planner proposes the migration plan, and one reviewer attacks weaknesses in the plan. All reports must be traceable to artifacts. Finally, summarize the conclusion and the next implementation prompt.
```

```text
Schedule one implementer subagent to make the smallest viable change, then schedule a spec reviewer and quality reviewer to review it separately. If review fails, send it back for rework. Finally run verify_delegate_workflow and the project tests before delivery.
```

```text
This task may be long. Split it into non-conflicting worker scopes. Allow the Claude Code worker to run long enough to produce a formal report. The main thread should not sleep and babysit; it should only record RunId/status/stream/trace and use ccviz for checkpoint handoff.
```

## Common Commands

Validate a TaskFile:

```bash
./skills/codex-with-cc/macos_scripts/validate_delegate_task.sh \
  -TaskFile ./.codex/codex_with_cc/tasks/<task-file>.md \
  -Role implementer \
  -Tests "pytest -q"
```

Run an implementation worker from a trusted fallback terminal:

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

Run a report-only worker:

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

Inspect workflows:

```bash
./skills/codex-with-cc/macos_scripts/ccviz.sh list
./skills/codex-with-cc/macos_scripts/ccviz.sh show <workflow-id>
./skills/codex-with-cc/macos_scripts/ccviz.sh audit <workflow-id>
```

## What You Can Imagine Building With It

- Parallel implementation with bounded write scopes.
- Independent architecture, security, testing, and migration researchers.
- Deterministic artifact verification plus optional LLM forensic assistance.
- Long-running implementation workers that do not bury the main thread.
- Review pipelines where spec, quality, and final acceptance are separate gates.
- Low-cost report/audit flows using DeepSeek Flash while keeping implementation with Claude Code.
- A reusable protocol for human-AI software delivery under uncertainty.

## Maintainers

See [MAINTAINERS.md](MAINTAINERS.md).

## License

MIT. See [LICENSE](LICENSE).
