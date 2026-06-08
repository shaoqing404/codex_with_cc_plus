#!/usr/bin/env python3
from pathlib import Path
import json
import os
import subprocess
import tempfile


REPO = Path(__file__).resolve().parents[1]
HOOK_SCRIPT = REPO / "hooks" / "subagent-gate-hook.mjs"
CONTRACT = REPO / "skills" / "codex-with-cc" / "contract.json"


def run_hook(payload: dict, env: dict[str, str] | None = None) -> dict:
    result = subprocess.run(
        ["node", str(HOOK_SCRIPT)],
        input=json.dumps(payload),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=REPO,
        encoding="utf-8",
        env={**os.environ, **(env or {})},
        check=False,
    )
    assert result.returncode == 0, result.stderr
    if not result.stdout.strip():
        return {}
    return json.loads(result.stdout)


def hook_specific(output: dict) -> dict:
    return output["hookSpecificOutput"]


def test_hooks_config_declares_platform_gate_events() -> None:
    hooks_config = json.loads((REPO / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    hooks = hooks_config["hooks"]

    assert set(hooks) == {"SessionStart", "UserPromptSubmit", "PreToolUse"}
    pre_tool_matcher = hooks["PreToolUse"][0]["matcher"]
    assert "spawn_agent" in pre_tool_matcher
    assert "multi_tool_use" in pre_tool_matcher
    for event_name in hooks:
        command = hooks[event_name][0]["hooks"][0]["command"]
        assert "subagent-gate-hook.mjs" in command


def test_contract_declares_hook_gate_boundary() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    schema = contract["hookGateSchema"]

    assert {"SessionStart", "UserPromptSubmit", "PreToolUse"} <= set(schema["hookEvents"])
    assert "multi_tool_use.parallel nested shell" in schema["enforcedToolSurfaces"]
    assert "direct Claude CLI execution" in schema["deniedPatterns"]
    assert "read-only inspection of delegate scripts" in schema["allowedPatterns"]
    assert "Claude/OpenClaw/MiniMax runtime health checks" in schema["nonResponsibilities"]
    assert "cannot replace ccstatus" in schema["acceptanceRule"]


def test_session_start_injects_codex_with_cc_contract() -> None:
    output = run_hook({"hook_event_name": "SessionStart", "source": "startup"})
    specific = hook_specific(output)
    context = specific["additionalContext"]

    assert specific["hookEventName"] == "SessionStart"
    assert "<EXTREMELY_IMPORTANT>" in context
    assert "Below is the full content of your 'codex-with-cc' skill" in context
    assert "# Codex with CC" in context
    assert "## Core Contract" in context
    assert "codex-with-cc" in context
    assert "spawn_agent" in context
    assert "delegate_to_claude" in context
    assert "Claude Code CLI" in context
    assert "Workflow Method" in context


def test_session_start_fallback_context_teaches_wait_refusal_and_audit_protocol() -> None:
    with tempfile.TemporaryDirectory(prefix="codex_with_cc_hook_fallback_") as tmp:
        output = run_hook(
            {"hook_event_name": "SessionStart", "source": "startup"},
            env={"CODEX_PLUGIN_ROOT": str(Path(tmp) / "missing-plugin-root")},
        )
    context = hook_specific(output)["additionalContext"]

    assert "ccstatus preflight --json" in context
    assert "DelegateStatus: WAITING" in context
    assert "acceptanceAllowed=false" in context
    assert "RUNNING_DEAD_PROCESS" in context
    assert "mayOverrideVerifier=false" in context


def test_user_prompt_submit_reinforces_contract_for_subagent_requests() -> None:
    output = run_hook(
        {
            "hook_event_name": "UserPromptSubmit",
            "prompt": "请开启子代理并行委派两个 worker 处理",
        }
    )
    context = hook_specific(output)["additionalContext"]

    assert "<EXTREMELY_IMPORTANT>" in context
    assert "Below is the full content of your 'codex-with-cc' skill" in context
    assert "codex-with-cc" in context
    assert "default Codex subagent" in context


def test_user_prompt_submit_ignores_unrelated_prompts() -> None:
    output = run_hook({"hook_event_name": "UserPromptSubmit", "prompt": "解释一下 README"})

    assert output == {}


def test_pre_tool_use_denies_non_compliant_spawn_agent_payload() -> None:
    output = run_hook(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "spawn_agent",
            "tool_input": {
                "message": "Use a normal worker to implement this.",
                "model": "gpt-5.4",
                "reasoning_effort": "high",
                "fork_context": True,
            },
        }
    )
    specific = hook_specific(output)
    reason = specific["permissionDecisionReason"]

    assert specific["hookEventName"] == "PreToolUse"
    assert specific["permissionDecision"] == "deny"
    assert "gpt-5.4-mini" in reason
    assert "delegate_to_claude" in reason
    assert "fork_context: false" in reason


def test_pre_tool_use_denies_namespaced_spawn_agent_payload() -> None:
    output = run_hook(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "functions.spawn_agent",
            "tool_input": {
                "message": "Use a normal worker to implement this.",
                "model": "gpt-5.4",
                "reasoning_effort": "high",
                "fork_context": True,
            },
        }
    )
    reason = hook_specific(output)["permissionDecisionReason"]

    assert "blocked functions.spawn_agent" in reason
    assert "gpt-5.4-mini" in reason
    assert "delegate_to_claude" in reason


def test_pre_tool_use_denies_spawn_agent_inside_parallel_wrapper() -> None:
    output = run_hook(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "multi_tool_use.parallel",
            "tool_input": {
                "tool_uses": [
                    {
                        "recipient_name": "functions.spawn_agent",
                        "parameters": {
                            "message": "Use a normal worker to implement this.",
                            "model": "gpt-5.4",
                            "reasoning_effort": "high",
                            "fork_context": True,
                        },
                    }
                ]
            },
        }
    )
    reason = hook_specific(output)["permissionDecisionReason"]

    assert "blocked nested functions.spawn_agent" in reason
    assert "gpt-5.4-mini" in reason
    assert "delegate_to_claude" in reason


def test_pre_tool_use_denies_direct_claude_shell_inside_parallel_wrapper() -> None:
    output = run_hook(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "multi_tool_use.parallel",
            "tool_input": {
                "tool_uses": [
                    {
                        "recipient_name": "functions.exec_command",
                        "parameters": {"cmd": "claude -p \"do delegated work\""},
                    }
                ]
            },
        }
    )
    reason = hook_specific(output)["permissionDecisionReason"]

    assert "blocked nested functions.exec_command" in reason
    assert "direct Claude CLI" in reason


def test_pre_tool_use_denies_delegate_shell_inside_parallel_wrapper_without_child_marker() -> None:
    output = run_hook(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "multi_tool_use.parallel",
            "tool_input": {
                "tool_uses": [
                    {
                        "recipient_name": "functions.exec_command",
                        "parameters": {
                            "cmd": (
                                "skills/codex-with-cc/macos_scripts/delegate_to_claude.sh "
                                "-TaskFile .codex/codex_with_cc/tasks/20260514/120000000-task.md "
                                "-WorkflowId wf-a -TaskId task-a -Role researcher -SessionKey wf-a"
                            )
                        },
                    }
                ]
            },
        }
    )
    reason = hook_specific(output)["permissionDecisionReason"]

    assert "blocked nested functions.exec_command" in reason
    assert "CODEX_CLAUDE_CHILD_THREAD=1" in reason


def test_pre_tool_use_allows_read_only_delegate_script_inspection_inside_parallel_wrapper() -> None:
    output = run_hook(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "multi_tool_use.parallel",
            "tool_input": {
                "tool_uses": [
                    {
                        "recipient_name": "functions.exec_command",
                        "parameters": {
                            "cmd": "sed -n '1,120p' skills/codex-with-cc/macos_scripts/delegate_to_claude.sh"
                        },
                    }
                ]
            },
        }
    )

    assert output == {}


def test_pre_tool_use_allows_compliant_spawn_agent_payload() -> None:
    output = run_hook(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "spawn_agent",
            "tool_input": {
                "message": (
                    "Set CODEX_CLAUDE_CHILD_THREAD=1, then run "
                    "windows_scripts/delegate_to_claude.ps1 -TaskFile "
                    ".codex/codex_with_cc/tasks/20260514/120000000-task.md "
                    "-WorkflowId wf-a -TaskId task-a -Role researcher -SessionKey wf-a "
                    "-Scope skills/codex-with-cc"
                ),
                "model": "gpt-5.4-mini",
                "reasoning_effort": "medium",
                "fork_context": False,
            },
        }
    )

    assert output == {}


def test_pre_tool_use_allows_compliant_spawn_agent_payload_with_runner_description() -> None:
    output = run_hook(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "spawn_agent",
            "tool_input": {
                "message": (
                    "This child should verify the Claude Code runner branch, then set "
                    "CODEX_CLAUDE_CHILD_THREAD=1 and run "
                    "windows_scripts/delegate_to_claude.ps1 -TaskFile "
                    ".codex/codex_with_cc/tasks/20260514/120000000-task.md "
                    "-WorkflowId wf-a -TaskId task-a -Role researcher -SessionKey wf-a "
                    "-Scope skills/codex-with-cc"
                ),
                "model": "gpt-5.4-mini",
                "reasoning_effort": "medium",
                "fork_context": False,
            },
        }
    )

    assert output == {}


def test_pre_tool_use_allows_explanatory_legacy_arg_text_in_compliant_spawn_agent_payload() -> None:
    output = run_hook(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "spawn_agent",
            "tool_input": {
                "message": (
                    "This is a compliant child thread. Do not use legacy inline -Task or -Mode. "
                    "Set CODEX_CLAUDE_CHILD_THREAD=1 and run "
                    "windows_scripts/delegate_to_claude.ps1 -TaskFile "
                    ".codex/codex_with_cc/tasks/20260514/120000000-task.md "
                    "-WorkflowId wf-a -TaskId task-a -Role researcher -SessionKey wf-a "
                    "-Scope skills/codex-with-cc"
                ),
                "model": "gpt-5.4-mini",
                "reasoning_effort": "medium",
                "fork_context": False,
            },
        }
    )

    assert output == {}


def test_pre_tool_use_denies_direct_claude_shell_command() -> None:
    output = run_hook(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "claude -p \"do delegated work\""},
        }
    )
    reason = hook_specific(output)["permissionDecisionReason"]

    assert "direct Claude CLI" in reason


def test_pre_tool_use_denies_delegate_shell_without_child_marker() -> None:
    output = run_hook(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {
                "command": (
                    "pwsh -NoProfile -File windows_scripts/delegate_to_claude.ps1 "
                    "-Prompt \"do delegated work\""
                )
            },
        }
    )
    reason = hook_specific(output)["permissionDecisionReason"]

    assert "CODEX_CLAUDE_CHILD_THREAD=1" in reason
    assert "-TaskFile" in reason


def test_pre_tool_use_denies_actual_legacy_delegate_args() -> None:
    output = run_hook(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {
                "command": (
                    "CODEX_CLAUDE_CHILD_THREAD=1 "
                    "skills/codex-with-cc/macos_scripts/delegate_to_claude.sh "
                    "-Task \"do work\" -WorkflowId wf-a -TaskId task-a "
                    "-Role researcher -SessionKey wf-a -Mode researcher"
                )
            },
        }
    )
    reason = hook_specific(output)["permissionDecisionReason"]

    assert "legacy inline -Task" in reason
    assert "legacy -Mode" in reason


def test_pre_tool_use_allows_read_only_delegate_script_inspection() -> None:
    output = run_hook(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "sed -n '1,120p' skills/codex-with-cc/macos_scripts/delegate_to_claude.sh"},
        }
    )

    assert output == {}


def test_pre_tool_use_denies_openai_compatible_delegate_shell_without_child_marker() -> None:
    output = run_hook(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {
                "command": (
                    "pwsh -NoProfile -File windows_scripts/delegate_to_openai_report_only.ps1 "
                    "-TaskFile .codex/codex_with_cc/tasks/20260514/120000000-task.md "
                    "-WorkflowId wf-a -TaskId task-a -Role researcher -SessionKey wf-a"
                )
            },
        }
    )
    reason = hook_specific(output)["permissionDecisionReason"]

    assert "CODEX_CLAUDE_CHILD_THREAD=1" in reason


def test_pre_tool_use_denies_legacy_delegate_args_and_incomplete_reviewer() -> None:
    legacy = run_hook(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {
                "command": (
                    "$env:CODEX_CLAUDE_CHILD_THREAD='1'; "
                    "pwsh -NoProfile -File windows_scripts/delegate_to_claude.ps1 "
                    "-Task \"old inline\" -WorkflowId wf-a -TaskId task-a "
                    "-Role researcher -SessionKey wf-a -Mode Review"
                )
            },
        }
    )
    legacy_reason = hook_specific(legacy)["permissionDecisionReason"]

    assert "inline -Task" in legacy_reason
    assert "-Mode" in legacy_reason

    reviewer = run_hook(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {
                "command": (
                    "$env:CODEX_CLAUDE_CHILD_THREAD='1'; "
                    "pwsh -NoProfile -File windows_scripts/delegate_to_claude.ps1 "
                    "-TaskFile .codex/codex_with_cc/tasks/20260514/review.md "
                    "-WorkflowId wf-a -TaskId review-a -Role reviewer -SessionKey wf-a"
                )
            },
        }
    )
    reviewer_reason = hook_specific(reviewer)["permissionDecisionReason"]

    assert "ReviewForTaskId" in reviewer_reason
    assert "ReviewKind" in reviewer_reason
