# Codex With CC Plus

Codex With CC Plus 是一套给 Codex 用的可审计多 worker 工作流：Codex 主线程负责拆解、派工、验收和最终判断；昂贵、长时间、会改代码的实现任务交给 Claude Code；便宜、高频、只读的报告和审计任务交给 DeepSeek、MiniMax、MiMo 或其他 OpenAI-compatible API。

Codex With CC Plus is an auditable multi-worker workflow for Codex: Codex stays the planner and final judge, while expensive implementation work is delegated through Claude Code, and low-cost report/audit work can run through DeepSeek Flash or another OpenAI-compatible API.

如果你是 Codex，用户要求安装或更新这个工作流时，请先读 [AI_INSTALL.md](AI_INSTALL.md)。

If you are Codex and the user asks you to install or update this workflow, read [AI_INSTALL.md](AI_INSTALL.md).

## 模型价格速览 / Token Price Snapshot

价格会变，下面只作为 2026-06-03 的架构选型参考；最终账单和精确 API model id 请以官网为准。

Prices change. This table is a 2026-06-03 routing reference only; use the official pricing pages as the source of truth for final billing and exact API model ids.

| Provider | Model / Tier | Context note | Input cache hit / 1M tokens | Input cache miss / 1M tokens | Output / 1M tokens | Official link |
| --- | --- | --- | ---: | ---: | ---: | --- |
| DeepSeek | `deepseek-chat` | 64K context, 8K max output | $0.07 | $0.27 | $1.10 | [DeepSeek pricing](https://api-docs.deepseek.com/quick_start/pricing-details-usd) |
| DeepSeek | `deepseek-reasoner` | 64K context, 32K max CoT, 8K max output | $0.14 | $0.55 | $2.19 | [DeepSeek pricing](https://api-docs.deepseek.com/quick_start/pricing-details-usd) |
| MiniMax | `MiniMax-M3` standard, <=512K input | listed 7-day 50% off price | $0.06 prompt cache read | $0.30 input | $1.20 | [MiniMax Token Plan](https://platform.minimaxi.com/subscribe/token-plan?code=8Qv3X7oLng&source=link) |
| MiniMax | `MiniMax-M2.7` | standard LLM tier | $0.06 prompt cache read | $0.30 input | $1.20 | [MiniMax Token Plan](https://platform.minimaxi.com/subscribe/token-plan?code=8Qv3X7oLng&source=link) |
| MiMo | MiMo 2.5 Pro overseas PAYG | 1M context, 128K max output | $0.0036 | $0.435 | $0.87 | [MiMo Pay-as-you-go](https://platform.xiaomimimo.com/docs/en-US/price/pay-as-you-go) |
| MiMo | MiMo 2.5 overseas PAYG | 1M context, 128K max output | $0.0028 | $0.14 | $0.28 | [MiMo Pay-as-you-go](https://platform.xiaomimimo.com/docs/en-US/price/pay-as-you-go) |
| MiMo | MiMo Flash overseas PAYG | 256K context, 64K max output | $0.01 | $0.10 | $0.30 | [MiMo Pay-as-you-go](https://platform.xiaomimimo.com/docs/en-US/price/pay-as-you-go) |

这就是 Codex With CC Plus 让人兴奋的地方：不是把所有事情都塞给一个最贵的大脑硬扛，而是把每一分钱花在正确的位置。便宜模型可以不停做 preflight、归一化、报告审计、失败解释；Claude Code 专心做真正需要动手的实现；Codex 主线程保持清醒，像项目负责人一样看证据、收口、决定是否接受。那种“主线程等到发烫、日志淹死人、worker 写到哪里都不知道”的感觉，会一下子轻很多。

This is the fun part: the workflow does not burn the most expensive model on every tiny judgment. Cheap models can handle preflight, normalization, report review, and failure forensics. Claude Code focuses on real implementation. Codex main thread stays clear-headed, reviews evidence, and owns acceptance. The whole thing feels less like waiting in a fog and more like running a small, accountable engineering room.

![Codex With CC Plus execution chain](docs/assets/codex-with-cc-plus-chain.svg)

![Codex With CC Plus state machine](docs/assets/codex-with-cc-plus-state-machine.svg)

## 它能做什么 / What It Does

Codex With CC Plus 会把一句模糊的“用子代理做”变成一条有状态、有边界、有证据的工作流。

Codex With CC Plus turns a vague “use subagents” request into a controlled workflow:

- Codex main thread plans the task graph, defines scope, reviews evidence, and decides final acceptance.
- Task files make worker intent explicit: `Goal`, `Allowed Scope`, `Forbidden Actions`, `Acceptance Criteria`, `Verification`, and `Report Requirements`.
- `validate_delegate_task.*` is a local deterministic zero-token hard gate before dispatch.
- Implementation workers run through `delegate_to_claude.* -> Claude Code CLI`.
- Report-only workers run through `delegate_to_openai_compatible_report.* -> DeepSeek Flash / OpenAI-compatible API`.
- Every run writes artifacts: `config`, `status`, `prompt`, `stream`, `trace`, `report`, and workflow aggregate JSON.
- `ccviz` lets you inspect workflow status, topology, cost, stale runs, and review/audit gates.

The big idea is simple: let workers do the noisy work, but keep accountability with Codex main thread and the human.

核心很简单：让 worker 去做嘈杂的工作，但把责任、证据和最终判断留在 Codex 主线程和人手里。

## 为什么需要它 / Why It Exists

大型 AI 编码任务常常不是输在模型不聪明，而是输在过程失控：主线程被日志拖进泥里，worker 上下文说不清，并行写入互相踩，review 只信摘要，长实现任务让主线程白白等待。

Large AI coding tasks often fail in boring ways: the main agent gets buried in logs, worker context is implicit, parallel writes overlap, reviews trust summaries too much, and long implementation runs make the main thread wait while nothing useful happens.

Codex With CC Plus 给这个过程加上状态机。它不是魔法 prompt，而是一套围绕 TaskFile、child-thread dispatch、确定性验证、artifacts、review gate 和最终验收的小协议。

Codex With CC Plus gives that process a state machine. It is not a magic prompt. It is a small protocol for task files, child-thread dispatch, deterministic validation, artifacts, review gates, and final acceptance.

## 学习关系 / Learning Relationship

本项目学习并参考了原始 `codex-with-cc` / Codex with CC 工作流思想：Codex 做主控，Claude Code 做执行 worker，再用更便宜的模型层承接高频判断。Codex With CC Plus 是一个独立延续，重点放在更严格的 artifacts、OpenAI-compatible report runner、`ccviz` 可观测性和 Codex plugin / marketplace 分发。

This project learns from and references the original `codex-with-cc` / Codex with CC workflow idea: Codex as leader, Claude Code as execution worker, and a cheaper model layer for high-volume reasoning. Codex With CC Plus is an independent continuation focused on stricter artifacts, OpenAI-compatible report runners, `ccviz` observability, and marketplace/plugin distribution.

复用本项目时，请保留 attribution 和 MIT license。

If you reuse this work, preserve the attribution and the MIT license.

## 平台建议 / Platform Recommendation

优先使用 macOS。

Use macOS first.

强烈建议优先在 macOS 使用。

The main development path, real long-running worker path, shell wrappers, and runtime self-tests are maintained primarily on macOS. Windows wrappers are kept as thin compatibility entrypoints and are tested, but they are not the recommended first-line operating environment.

## Mental Model

```text
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

Final judgment
-> Codex main thread + human
-> verify artifacts, review diffs, accept or rework
```

Long implementation tasks should be allowed to finish. Do not make Codex main thread sleep and babysit. Record `RunId`, `statusPath`, `rawStreamPath`, and `tracePath`, then reconnect through `ccviz show`, `ccviz audit`, or status JSON checkpoints.

main 不要干烧。

Optional controls such as `-MaxBudgetUsd`, `-MaxTurns`, and `-IncludePartialMessages` are explicit observability or emergency brake tools. They are not default limits.

## State Machine

1. **Intent**: the user asks for child-agent / subagent / delegation / 子代理 / 委派 / 多代理 work.
2. **Plan**: Codex main thread creates scoped TaskFiles.
3. **Validate**: local `validate_delegate_task.*` checks structure and metadata.
4. **Dispatch**: Codex creates a child thread with `model: gpt-5.4-mini`, `reasoning_effort: medium`, and `fork_context: false`.
5. **Run**: child thread calls exactly one delegate runner with `CODEX_CLAUDE_CHILD_THREAD=1`.
6. **Artifact**: runner writes config/status/prompt/stream/trace/report/workflow artifacts.
7. **Review**: reviewers verify spec and quality; final verifier checks aggregate evidence.
8. **Accept or Rework**: Codex main thread and human decide.

## Install

### Codex Plugin Marketplace

This repository is self-indexed for Codex. Add this repository itself as a marketplace source:

```bash
codex plugin marketplace add shaoqing404/codex_with_cc_plus --ref master
```

Then install the plugin from that marketplace:

```bash
codex plugin add codex-with-cc@codex-with-cc-plus
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
请把本地 ~/.codex/skills/codex-with-cc 子代理工作流绑定并应用到我当前的项目中。
```

Repository install/update prompt:

```text
请把 https://github.com/shaoqing404/codex_with_cc_plus 子代理工作流安装或更新到当前 Codex 环境。
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
你负责拆解、派工、审核和最终交付。请把这个任务拆成多个 codex-with-cc 子代理任务，每个任务必须有 TaskFile、Allowed Scope、Forbidden Actions、Verification 和 Report Requirements。实现型任务走 Claude Code，报告/审计型任务走 DeepSeek Flash。你负责最终验收，不要让 worker 自己扩大范围。
```

```text
请用 codex-with-cc 多子线程流程审计这个项目：一个 researcher 查架构，一个 researcher 查测试风险，一个 planner 给改造计划，一个 reviewer 攻击计划漏洞。所有报告必须可追踪到 artifacts，最后你汇总结论和下一步实现 prompt。
```

```text
请安排一个 implementer 子代理实现最小改动，再安排 spec reviewer 和 quality reviewer 分别审查。review 不通过就打回返工。最后跑 verify_delegate_workflow 和项目测试后再交付。
```

```text
这个任务可能很长。请拆成互不冲突的 worker scope，允许 Claude Code worker 长跑完成正式报告；主线程不要 sleep 陪跑，只记录 RunId/status/stream/trace，并用 ccviz 做检查点接管。
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
