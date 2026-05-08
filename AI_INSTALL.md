# AI 安装说明

## 默认交互策略

只要用户是在让你“安装 / 集成 / 更新这套工作流”，默认进入零打扰安装模式：

1. 直接执行，不要先把安装过程变成问答游戏。
2. 默认把当前工作目录视为目标项目根目录，除非上下文无法判断。
3. 默认安装或更新全局 skill：`$CODEX_HOME/skills/codex-with-cc`；`CODEX_HOME` 未设置时使用 `~/.codex`。
4. 默认运行当前平台可用的本地验证。
5. 默认不再写入 `AGENTS.md`；如果旧版本写过托管块，安装或更新时移除它。
6. 只有源仓库缺失、目标根目录无法判断、写入失败或当前平台没有可用执行路径时，才停下来询问用户。

安装或更新 skill 时必须清理旧安装产物：`docs/codex_with_cc`、`doc/codex_with_cc` 和 `AGENTS.md` 中的托管块。

保留目标项目 `.codex/codex_with_cc` 下的任务、审计和 delegate artifacts；这些是运行历史，不是安装产物。全局 skill 运行时以当前工作目录作为目标项目根目录，因此多个项目可以共用同一套全局脚本，但必须从各自项目根目录执行。

## 目标

把本仓库的 `Codex -> Codex 子代理 -> Claude Code CLI` 委派工作流安装成全局 Codex skill，使后续凡是涉及子代理、子线程、多代理、委派、派工或执行层的任务，都强制触发 `$codex-with-cc`。

Any user mention of child-agent, subagent, sub-agent, child-thread, subthread, delegation, worker-execution, or Chinese equivalents such as 子代理、子线程、多代理、委派、派工、执行层 is a workflow trigger.

触发后必须走：

```text
Codex 主线程 -> Codex spawn_agent 子线程 -> $CODEX_HOME/skills/codex-with-cc/<platform_scripts>/delegate_to_claude.* -> scripts/*.py -> Claude Code CLI
```

不要把 Codex 默认子代理工作流、宿主环境内置代理流程、直接运行 `claude`、或主线程直接执行 `delegate_to_claude.*` 当作等价替代。

## 必需源文件

安装前确认源仓库存在：

```text
install_codex_with_cc.ps1
install_codex_with_cc.sh
skills/codex-with-cc/SKILL.md
skills/codex-with-cc/agents/openai.yaml
skills/codex-with-cc/CODEX_WITH_CC.md
skills/codex-with-cc/scripts/delegate_to_claude.py
skills/codex-with-cc/scripts/runtime.py
skills/codex-with-cc/windows_scripts/delegate_to_claude.ps1
skills/codex-with-cc/macos_scripts/delegate_to_claude.sh
```

`skills/codex-with-cc` 是完整 skill 分发包和仓库唯一工作流源，必须直接包含 `CODEX_WITH_CC.md`、`scripts/`、`windows_scripts/` 和 `macos_scripts/`。安装器只从这个 skill 目录复制到全局 skill 目录，根安装脚本也从这个 skill 目录启动共享 Python 入口。

Windows 全局 skill 不要安装 `macos_scripts`；macOS 全局 skill 不要安装 `windows_scripts`。两个平台都必须安装共享的 `scripts/*.py`。

## 安装行为

安装器应执行这些动作：

1. 删除目标项目旧目录 `docs/codex_with_cc` 和 `doc/codex_with_cc`。
2. 删除目标项目 `AGENTS.md` 中的 `<!-- BEGIN CODEX_WITH_CC --> ... <!-- END CODEX_WITH_CC -->` 托管块；保留其他内容，若文件变空则删除文件。
3. 删除目标项目旧的 `.codex/skills/codex-with-cc`，避免 local skill 和全局 skill 竞争触发。
4. 删除旧的 `$CODEX_HOME/skills/codex-with-cc` 后重新复制当前 skill 和运行时文件。
5. 创建目标项目 `.codex/codex_with_cc/tasks`，任务文件继续放在 `.codex/codex_with_cc/tasks/<yyyyMMdd>/<HHmmssfff>-<short-id>-<task-file>.md`。
6. 确保目标项目 `.gitignore` 包含 `.codex/codex_with_cc`，不要忽略全局 skill。
7. 输出全局 skill 路径、旧安装产物清理结果，以及下一步提示：重启 Codex 后使用 `$codex-with-cc` 或子代理/委派触发词。

## Windows 安装

在源仓库根目录执行：

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File .\install_codex_with_cc.ps1 -TargetRoot <target-project>
```

如果用户明确要求兼容旧参数，`-SkipAgentEntrypoints` 仍可接受，但不再阻止旧托管块清理：

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File .\install_codex_with_cc.ps1 -TargetRoot <target-project> -SkipAgentEntrypoints
```

Windows 验证命令，在目标项目根目录执行：

```powershell
pwsh -NoProfile -File "$env:CODEX_HOME\skills\codex-with-cc\windows_scripts\test_delegate_runtime.ps1"
pwsh -NoProfile -File "$env:CODEX_HOME\skills\codex-with-cc\windows_scripts\test_delegate_session_pool.ps1"
pwsh -NoProfile -File "$env:CODEX_HOME\skills\codex-with-cc\windows_scripts\run_real_delegate_chain_validation.ps1"
```

## macOS 安装

在源仓库根目录执行：

```bash
./install_codex_with_cc.sh --target-root <target-project> --platform macOS
```

如果用户明确要求兼容旧参数，`--skip-agent-entrypoints` 仍可接受，但不再阻止旧托管块清理：

```bash
./install_codex_with_cc.sh --target-root <target-project> --platform macOS --skip-agent-entrypoints
```

macOS 验证命令，在目标项目根目录执行：

```bash
"${CODEX_HOME:-$HOME/.codex}/skills/codex-with-cc/macos_scripts/test_delegate_runtime.sh"
"${CODEX_HOME:-$HOME/.codex}/skills/codex-with-cc/macos_scripts/test_delegate_session_pool.sh"
"${CODEX_HOME:-$HOME/.codex}/skills/codex-with-cc/macos_scripts/run_real_delegate_chain_validation.sh"
```

## 委派规则

Windows 子线程标准调用形态：

```powershell
$env:CODEX_CLAUDE_CHILD_THREAD = '1'
pwsh -NoProfile -File "$env:CODEX_HOME\skills\codex-with-cc\windows_scripts\delegate_to_claude.ps1" `
  -TaskFile .\.codex\codex_with_cc\tasks\<yyyyMMdd>\<HHmmssfff>-<short-id>-<task-file>.md `
  -SessionMode PrimaryReuse `
  -SessionKey <stable-session-key> `
  -BypassPermissions
```

macOS 子线程标准调用形态：

```bash
export CODEX_CLAUDE_CHILD_THREAD=1
"${CODEX_HOME:-$HOME/.codex}/skills/codex-with-cc/macos_scripts/delegate_to_claude.sh" \
  -TaskFile ./.codex/codex_with_cc/tasks/<yyyyMMdd>/<HHmmssfff>-<short-id>-<task-file>.md \
  -SessionMode PrimaryReuse \
  -SessionKey <stable-session-key> \
  -BypassPermissions
```

并行任务按场景使用：

- `PrimaryAnchor -AllowParallel`：并行批次的主线锚点。
- `ParallelPool -AllowParallel`：独立支线任务池。

只有任务范围互不冲突时才允许并行。多个子代理同时修改同一批文件时，必须拆分写入边界或改为串行。

## 验证与产物

委派运行产物默认写在目标项目：

```text
.codex/codex_with_cc/claude-delegate
```

常见文件包括：

- `claude_<RunId>.md`
- `status_<RunId>.json`
- `config_<RunId>.json`
- `prompt_<RunId>.md`
- `stream_<RunId>.jsonl`
- `trace_<RunId>.log`
- `session-pools/<SessionKey>.json`

检查单次委派产物：

```powershell
pwsh -NoProfile -File "$env:CODEX_HOME\skills\codex-with-cc\windows_scripts\verify_delegate_artifacts.ps1"
```

```bash
"${CODEX_HOME:-$HOME/.codex}/skills/codex-with-cc/macos_scripts/verify_delegate_artifacts.sh"
```

检查多轮链路连续性：

```powershell
pwsh -NoProfile -File "$env:CODEX_HOME\skills\codex-with-cc\windows_scripts\verify_delegate_chain.ps1"
```

```bash
"${CODEX_HOME:-$HOME/.codex}/skills/codex-with-cc/macos_scripts/verify_delegate_chain.sh"
```
