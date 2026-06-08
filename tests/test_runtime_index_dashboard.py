#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from tests.task_helpers import compliant_task


REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "skills" / "codex-with-cc" / "scripts"
CCRUNTIME = SCRIPTS / "ccruntime.py"
CCINDEX = SCRIPTS / "ccindex.py"
CCDASH = SCRIPTS / "ccdash.py"
DELEGATE = SCRIPTS / "delegate_to_claude.py"
CONTRACT = REPO / "skills" / "codex-with-cc" / "contract.json"
sys.path.insert(0, str(SCRIPTS))

from codex_with_cc_runtime.claude_cli import new_claude_cli_args


def run_script(script: Path, *args: str, cwd: Path = REPO, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    merged_env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    if env:
        merged_env.update(env)
    return subprocess.run([sys.executable, str(script), *args], cwd=cwd, text=True, capture_output=True, env=merged_env)


def run_id_from_output(output: str) -> str:
    for line in output.splitlines():
        if line.startswith("RunId:"):
            return line.split(":", 1)[1].strip()
    raise AssertionError(f"RunId line missing from output:\n{output}")


def worker_report() -> str:
    return "\n".join(
        [
            "Status",
            "DONE",
            "",
            "Role",
            "implementer",
            "",
            "Summary",
            "Index fixture completed.",
            "",
            "Changed Files",
            "None",
            "",
            "Verification",
            "- fixture verification passed",
            "",
            "Findings",
            "None",
            "",
            "Final Result",
            "DONE",
            "",
            "Risks Or Follow-ups",
            "None",
        ]
    )


def write_index_fixture(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    workflow_id = "wf-index"
    task_id = "task-index"
    run_id = "run-index"
    config_path = root / f"config_{run_id}.json"
    status_path = root / f"status_{run_id}.json"
    output_path = root / f"claude_{run_id}.md"
    prompt_path = root / f"prompt_{run_id}.md"
    stream_path = root / f"stream_{run_id}.jsonl"
    trace_path = root / f"trace_{run_id}.log"
    common = {
        "artifactSchema": 3,
        "invocationContract": "codex_with_cc_workflow",
        "runId": run_id,
        "workflowId": workflow_id,
        "taskId": task_id,
        "role": "implementer",
        "runnerType": "claude_code",
        "outputPath": str(output_path),
        "promptPath": str(prompt_path),
        "rawStreamPath": str(stream_path),
        "tracePath": str(trace_path),
    }
    config = {
        **common,
        "configPath": str(config_path),
        "statusPath": str(status_path),
        "model": "opus",
        "permissionMode": "plan",
        "bypassPermissions": True,
        "sessionMode": "PrimaryReuse",
        "sessionKey": "index-session",
        "tests": ["pytest -q"],
    }
    status = {**common, "configPath": str(config_path), "statusPath": str(status_path), "status": "completed", "exitCode": 0}
    workflow = {
        "artifactSchema": 3,
        "invocationContract": "codex_with_cc_workflow",
        "workflowId": workflow_id,
        "tasks": {task_id: {"taskId": task_id, "role": "implementer", "runs": [run_id], "status": "completed"}},
        "runs": {
            run_id: {
                "runId": run_id,
                "taskId": task_id,
                "role": "implementer",
                "runnerType": "claude_code",
                "status": "completed",
                "configPath": str(config_path),
                "statusPath": str(status_path),
                "outputPath": str(output_path),
                "promptPath": str(prompt_path),
                "rawStreamPath": str(stream_path),
                "tracePath": str(trace_path),
            }
        },
    }
    config_path.write_text(json.dumps(config), encoding="utf-8")
    status_path.write_text(json.dumps(status), encoding="utf-8")
    output_path.write_text(worker_report(), encoding="utf-8")
    prompt_path.write_text("# prompt\n", encoding="utf-8")
    stream_path.write_text('{"type":"assistant","message":{"model":"MiniMax-M3","content":[]}}\n', encoding="utf-8")
    trace_path.write_text("[fixture]\n", encoding="utf-8")
    (root / f"workflow_{workflow_id}.json").write_text(json.dumps(workflow), encoding="utf-8")


def test_runtime_status_and_apply_switch_are_redacted_and_reversible() -> None:
    with tempfile.TemporaryDirectory(prefix="codex_with_cc_runtime_") as tmp:
        home = Path(tmp) / "home"
        settings_path = home / ".claude" / "settings.json"
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        settings_path.write_text(
            json.dumps(
                {
                    "model": "sonnet",
                    "env": {
                        "ANTHROPIC_AUTH_TOKEN": "secret-token",
                        "ANTHROPIC_BASE_URL": "http://127.0.0.1:15721",
                        "ANTHROPIC_DEFAULT_SONNET_MODEL_NAME": "MiniMax-M3",
                    },
                }
            ),
            encoding="utf-8",
        )
        env = {"HOME": str(home), "CODEX_HOME": str(Path(tmp) / "codex-home")}
        status = run_script(CCRUNTIME, "status", "-ClaudeSettingsPath", str(settings_path), "--json", env=env)
        assert status.returncode == 0, status.stdout + status.stderr
        status_json = json.loads(status.stdout)
        assert status_json["claudeSettings"]["model"] == "sonnet"
        assert status_json["claudeSettings"]["hasToken"] is True
        assert "secret-token" not in status.stdout

        plan = run_script(
            CCRUNTIME,
            "plan-switch",
            "-ClaudeSettingsPath",
            str(settings_path),
            "-Model",
            "opus",
            "-PermissionMode",
            "acceptEdits",
            "-OpusModelName",
            "MiniMax-M3",
            "--json",
            env=env,
        )
        assert plan.returncode == 0, plan.stdout + plan.stderr
        plan_json = json.loads(plan.stdout)
        assert plan_json["dryRun"] is True
        assert plan_json["nextDelegateArgs"]["PermissionMode"] == "acceptEdits"
        assert plan_json["nextDelegateArgs"]["permissionModeAppliedToSettings"] is False

        artifact_root = Path(tmp) / "artifacts"
        applied = run_script(
            CCRUNTIME,
            "apply-switch",
            "-ClaudeSettingsPath",
            str(settings_path),
            "-ArtifactRoot",
            str(artifact_root),
            "-Model",
            "opus",
            "-PermissionMode",
            "acceptEdits",
            "-OpusModelName",
            "MiniMax-M3",
            "-ConfirmRuntimeChange",
            "--json",
            env=env,
        )
        assert applied.returncode == 0, applied.stdout + applied.stderr
        applied_json = json.loads(applied.stdout)
        assert applied_json["status"] == "applied"
        assert Path(applied_json["backupPath"]).exists()
        assert Path(applied_json["artifactPath"]).exists()
        assert "secret-token" not in Path(applied_json["artifactPath"]).read_text(encoding="utf-8")
        updated = json.loads(settings_path.read_text(encoding="utf-8"))
        assert updated["model"] == "opus"
        assert updated["env"]["ANTHROPIC_DEFAULT_OPUS_MODEL_NAME"] == "MiniMax-M3"


def test_delegate_permission_mode_is_recorded_and_forwarded() -> None:
    args = new_claude_cli_args("opus", "session-name", "session-id", False, None, False, permission_mode="plan")
    assert args[args.index("--permission-mode") + 1] == "plan"
    with tempfile.TemporaryDirectory(prefix="codex_with_cc_permission_") as tmp:
        root = Path(tmp)
        artifact_root = root / "artifacts"
        task = root / "task.md"
        task.write_text(compliant_task("permission mode dry run"), encoding="utf-8")
        result = run_script(
            DELEGATE,
            "-TaskFile",
            str(task),
            "-WorkflowId",
            "wf-permission",
            "-TaskId",
            "task-permission",
            "-Role",
            "researcher",
            "-ArtifactRoot",
            str(artifact_root),
            "-SessionKey",
            "permission-session",
            "-PermissionMode",
            "plan",
            "-DryRun",
            env={"CODEX_CLAUDE_CHILD_THREAD": "1"},
        )
        assert result.returncode == 0, result.stdout + result.stderr
        run_id = run_id_from_output(result.stdout)
        config = json.loads((artifact_root / f"config_{run_id}.json").read_text(encoding="utf-8"))
        assert config["permissionMode"] == "plan"


def test_ccindex_and_ccdash_render_machine_artifact_view() -> None:
    with tempfile.TemporaryDirectory(prefix="codex_with_cc_index_") as tmp:
        artifact_root = Path(tmp) / "artifacts"
        write_index_fixture(artifact_root)
        built = run_script(CCINDEX, "build", "-ArtifactRoot", str(artifact_root), "--json")
        assert built.returncode == 0, built.stdout + built.stderr
        index = json.loads(built.stdout)
        assert index["indexType"] == "codex-with-cc-machine-index"
        record = index["records"][0]
        assert record["workflowId"] == "wf-index"
        assert record["runSummaries"][0]["requestedModel"] == "opus"
        assert record["runSummaries"][0]["streamedModel"] == "MiniMax-M3"
        assert record["runSummaries"][0]["permissionMode"] == "plan"
        assert record["permissionSummary"]["bypassPermissions"] is True

        shown = run_script(CCINDEX, "show", "wf-index", "-ArtifactRoot", str(artifact_root), "--json")
        assert shown.returncode == 0, shown.stdout + shown.stderr
        assert json.loads(shown.stdout)["workflowId"] == "wf-index"

        dash_root = Path(tmp) / "dashboard"
        dash = run_script(CCDASH, "build", "-ArtifactRoot", str(artifact_root), "-OutputRoot", str(dash_root), "--json")
        assert dash.returncode == 0, dash.stdout + dash.stderr
        dash_json = json.loads(dash.stdout)
        assert Path(dash_json["indexPath"]).exists()
        html = Path(dash_json["htmlPath"]).read_text(encoding="utf-8")
        assert "Codex With CC Plus Dashboard" in html
        assert "wf-index" in html
        assert "MiniMax-M3" in html


def test_child_thread_return_protocol_keeps_waiting_runs_non_terminal() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    protocol = contract["childThreadReturnProtocol"]
    assert {"STARTING", "RUNNING_ACTIVE", "RUNNING_QUIET"} <= set(protocol["waitingStates"])
    assert "RUN_VERIFIED" in protocol["terminalStates"]
    assert "RUNNING_DEAD_PROCESS" in protocol["terminalStates"]
    assert "ArtifactRoot" in protocol["requiredFields"]
    assert "MainThreadAction" in protocol["requiredFields"]
    assert "ccsupervise" in protocol["mainThreadActions"]["RUNNING_ACTIVE"]
    assert "-Wait" in protocol["mainThreadActions"]["RUNNING_ACTIVE"]
    assert "not worker completion" in protocol["completionRule"]
