#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import plistlib
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
CCSTATUS = SCRIPTS / "ccstatus.py"
DELEGATE = SCRIPTS / "delegate_to_claude.py"
CONTRACT = REPO / "skills" / "codex-with-cc" / "contract.json"
sys.path.insert(0, str(SCRIPTS))

from codex_with_cc_runtime.artifacts import verify_artifacts
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


def write_running_fixture(root: Path) -> str:
    root.mkdir(parents=True, exist_ok=True)
    workflow_id = "wf-running"
    task_id = "task-running"
    run_id = "run-running"
    config_path = root / f"config_{run_id}.json"
    status_path = root / f"status_{run_id}.json"
    output_path = root / f"claude_{run_id}.md"
    prompt_path = root / f"prompt_{run_id}.md"
    stream_path = root / f"stream_{run_id}.jsonl"
    trace_path = root / f"trace_{run_id}.log"
    common = {
        "artifactSchema": 3,
        "invocationContract": "codex_with_cc_workflow",
        "childThreadMarkerName": "CODEX_CLAUDE_CHILD_THREAD",
        "childThreadMarkerValidated": True,
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
        "sessionMode": "PrimaryReuse",
        "sessionKey": "running-session",
    }
    status = {
        **common,
        "configPath": str(config_path),
        "statusPath": str(status_path),
        "status": "running",
        "pid": os.getpid(),
        "attempts": [{"attempt": 1, "pid": os.getpid()}],
    }
    workflow = {
        "artifactSchema": 3,
        "invocationContract": "codex_with_cc_workflow",
        "workflowId": workflow_id,
        "tasks": {task_id: {"taskId": task_id, "role": "implementer", "runs": [run_id], "status": "running"}},
        "runs": {run_id: {"runId": run_id, "taskId": task_id, "role": "implementer", "status": "running"}},
    }
    config_path.write_text(json.dumps(config), encoding="utf-8")
    status_path.write_text(json.dumps(status), encoding="utf-8")
    prompt_path.write_text("# prompt\n", encoding="utf-8")
    stream_path.write_text('{"type":"assistant","message":{"model":"MiniMax-M3","content":[]}}\n', encoding="utf-8")
    trace_path.write_text("[fixture]\n", encoding="utf-8")
    (root / f"workflow_{workflow_id}.json").write_text(json.dumps(workflow), encoding="utf-8")
    return run_id


def pageindex_api_failure_report() -> str:
    return "\n".join(
        [
            "Status",
            "FAIL",
            "",
            "Role",
            "implementer",
            "",
            "Summary",
            "Claude Code reached its API layer but could not complete the delegated PageIndex task.",
            "",
            "Changed Files",
            "None",
            "",
            "Verification",
            "- not run; Claude Code API connection failed before trustworthy worker execution",
            "",
            "Findings",
            "- Delegate runner startup, TaskFile metadata, and artifact writing reached Claude Code execution.",
            "- Claude Code returned an API error instead of a structured worker implementation report.",
            "- API error: API Error: Unable to connect to API (ConnectionRefused)",
            "",
            "Final Result",
            "FAIL",
            "",
            "Risks Or Follow-ups",
            "- Check Claude Code login, local OpenClaw/MiniMax backend, proxy, account quota, and selected backend/model before retrying.",
            "- Do not accept this delegated task as implemented; no trustworthy worker verification was produced.",
        ]
    )


def write_pageindex_socket_failure_fixture(root: Path) -> str:
    root.mkdir(parents=True, exist_ok=True)
    workflow_id = "pageindex-phase-5-3b-step2e-ui"
    task_id = "phase-5-3b-step2e1b-upload-delete-ux-hardening"
    run_id = "20260607_222729_937_b97208fd"
    output_path = root / f"claude_{run_id}.md"
    prompt_path = root / f"prompt_{run_id}.md"
    stream_path = root / f"stream_{run_id}.jsonl"
    trace_path = root / f"trace_{run_id}.log"
    status_path = root / f"status_{run_id}.json"
    config_path = root / f"config_{run_id}.json"
    output_path.write_text(pageindex_api_failure_report(), encoding="utf-8")
    prompt_path.write_text("# PageIndex Step 2E-1B TaskFile\n\nGoal\nRun bounded PageIndex upload/delete UX hardening.\n", encoding="utf-8")
    stream_path.write_text(
        json.dumps(
            {
                "type": "result",
                "subtype": "success",
                "is_error": True,
                "api_error_status": None,
                "result": "API Error: Unable to connect to API (ConnectionRefused)",
            },
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )
    trace_path.write_text("[result] API Error: Unable to connect to API (ConnectionRefused)\n", encoding="utf-8")
    failure = {
        "failureDisposition": "NEED_HUMAN_INTERVENTION",
        "failureSummary": "CLAUDE_API_ERROR: API Error: Unable to connect to API (ConnectionRefused)",
        "apiErrorStatus": None,
        "artifactContract": "structured_failure_report",
        "workerOutcome": "FAIL",
        "businessAcceptance": "blocked",
        "failureLayer": "claude_api_connection",
        "retryable": "maybe",
        "humanActionRequired": True,
        "safeToRetrySameTaskFile": True,
        "businessFilesChanged": False,
        "mayOverrideImplementation": False,
    }
    common = {
        "artifactSchema": 3,
        "invocationContract": "codex_with_cc_workflow",
        "childThreadMarkerName": "CODEX_CLAUDE_CHILD_THREAD",
        "childThreadMarkerValidated": True,
        "runId": run_id,
        "workflowId": workflow_id,
        "taskId": task_id,
        "role": "implementer",
        "runnerType": "claude_code",
        "outputPath": str(output_path),
        "promptPath": str(prompt_path),
        "rawStreamPath": str(stream_path),
        "tracePath": str(trace_path),
        "sessionMode": "PrimaryReuse",
        "sessionKey": "phase-5-3b-step2e1b-upload-delete-20260607-a",
        "initialSessionId": "fresh-session-a",
        "initialResume": False,
        "sessionId": "fresh-session-a",
        "resume": False,
        "attemptCount": 1,
        "retryCount": 0,
        "maxRetryCount": 0,
        "scope": ["frontend"],
        "tests": ["cd frontend && npm run build", "git diff --check"],
        **failure,
    }
    config = {**common, "configPath": str(config_path), "statusPath": str(status_path)}
    status = {
        **common,
        "configPath": str(config_path),
        "statusPath": str(status_path),
        "status": "failed",
        "exitCode": 1,
        "outputBytes": output_path.stat().st_size,
        "attempts": [
            {
                "attempt": 1,
                "sessionId": "fresh-session-a",
                "resume": False,
                "retryReason": None,
                "exitCode": 1,
                "sawAssistantText": False,
                "sawResultSuccess": False,
                "capturedFinalResult": True,
            }
        ],
    }
    workflow = {
        "artifactSchema": 3,
        "invocationContract": "codex_with_cc_workflow",
        "workflowId": workflow_id,
        "tasks": {
            task_id: {
                "taskId": task_id,
                "role": "implementer",
                "scope": ["frontend"],
                "verification": ["cd frontend && npm run build", "git diff --check"],
                "runs": [run_id],
                "status": "failed",
                "lastReportStatus": "FAIL",
                "lastReportFinalResult": "FAIL",
                "lastReportRole": "implementer",
                "reviewDecision": "failed",
                "reviews": {},
            }
        },
        "runs": {
            run_id: {
                "runId": run_id,
                "taskId": task_id,
                "role": "implementer",
                "runnerType": "claude_code",
                "status": "failed",
                "reportStatus": "FAIL",
                "reportFinalResult": "FAIL",
                "reportRole": "implementer",
                "reviewDecision": "failed",
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
    (root / f"workflow_{workflow_id}.json").write_text(json.dumps(workflow), encoding="utf-8")
    return run_id


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


def test_runtime_status_discovers_ccswitch_cli_and_desktop_state_without_secrets() -> None:
    with tempfile.TemporaryDirectory(prefix="codex_with_ccswitch_") as tmp:
        root = Path(tmp)
        home = root / "home"
        fake_bin = root / "bin"
        fake_bin.mkdir(parents=True)
        fake_cli = fake_bin / "cc-switch"
        fake_cli.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        fake_cli.chmod(0o755)

        settings_path = home / ".claude" / "settings.json"
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        settings_path.write_text(json.dumps({"model": "opus", "env": {"ANTHROPIC_BASE_URL": "http://127.0.0.1:15721"}}), encoding="utf-8")

        home_state = home / ".cc-switch"
        home_state.mkdir(parents=True)
        home_state.joinpath("config.json").write_text(
            json.dumps({"provider": "MiniMax", "model": "MiniMax-M3", "apiKey": "ccswitch-secret"}),
            encoding="utf-8",
        )
        app_state = home / "Library" / "Application Support" / "com.ccswitch.desktop"
        app_state.mkdir(parents=True)
        app_state.joinpath("state.json").write_text(json.dumps({"activeProfile": "local-minimax"}), encoding="utf-8")
        plist_path = home / "Library" / "Preferences" / "com.ccswitch.desktop.plist"
        plist_path.parent.mkdir(parents=True, exist_ok=True)
        with plist_path.open("wb") as handle:
            plistlib.dump({"selectedProvider": "MiniMax", "authToken": "plist-secret", "opaqueData": b"\x00\x01local"}, handle)

        env = {
            "HOME": str(home),
            "CODEX_HOME": str(root / "codex-home"),
            "PATH": f"{fake_bin}{os.pathsep}{os.environ.get('PATH', '')}",
        }
        status = run_script(CCRUNTIME, "status", "-ClaudeSettingsPath", str(settings_path), "--json", env=env)
        assert status.returncode == 0, status.stdout + status.stderr
        payload = json.loads(status.stdout)
        provider = payload["ccswitchProvider"]
        assert provider["available"] is True
        assert provider["path"] == str(fake_cli)
        assert provider["desktopStateAvailable"] is True
        assert provider["loadStatus"] == "cli_available"
        assert provider["mutability"] == "read_only"
        assert provider["mayRepairRuntime"] is False
        assert "ccswitch-secret" not in status.stdout
        assert "plist-secret" not in status.stdout
        assert '"redacted": true' in status.stdout


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
    assert "REFUSED" in protocol["delegateStatusValues"]
    assert contract["mainThreadHandoffSchema"]["recommendedWaitPolicy"]["RUNNING_ACTIVE"] == 60


def test_contract_declares_ccswitch_provider_schema_boundary() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    provider_schema = contract["runtimeProviderSchema"]["ccswitchProvider"]

    assert {"ccwitch", "ccswitch", "cc-switch"} <= set(provider_schema["cliNames"])
    assert {"home_state", "desktop_app_support", "desktop_preferences"} <= set(provider_schema["knownStateKinds"])
    assert "mutability" in provider_schema["requiredFields"]
    assert "mayRepairRuntime" in provider_schema["requiredFields"]
    assert "diagnostic evidence only" in provider_schema["acceptanceRule"]
    assert "cannot override deterministic workflow verifiers" in provider_schema["acceptanceRule"]


def test_contract_declares_ds_routing_schema_boundary() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    ds_schema = contract["dsRoutingSchema"]

    assert ds_schema["routeType"] == "ds-advisory-routing-plan"
    assert {"recommended", "optional", "not_recommended"} <= set(ds_schema["recommendationValues"])
    assert "automaticDispatch" in ds_schema["requiredFields"]
    assert "mayOverrideVerifier" in ds_schema["requiredFields"]
    assert "canAcceptWorkflowResults" in ds_schema["requiredFields"]
    assert "automaticDispatch=false" in ds_schema["automaticDispatchRule"]
    assert "cannot override" in ds_schema["acceptanceRule"]


def test_ccstatus_claude_blocks_when_local_backend_is_unreachable_and_redacts_token() -> None:
    with tempfile.TemporaryDirectory(prefix="codex_with_cc_status_") as tmp:
        home = Path(tmp) / "home"
        settings_path = home / ".claude" / "settings.json"
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        settings_path.write_text(
            json.dumps(
                {
                    "model": "opus",
                    "env": {
                        "ANTHROPIC_AUTH_TOKEN": "secret-token",
                        "ANTHROPIC_BASE_URL": "http://127.0.0.1:9",
                        "ANTHROPIC_DEFAULT_OPUS_MODEL_NAME": "MiniMax-M3",
                    },
                }
            ),
            encoding="utf-8",
        )
        empty_bin = Path(tmp) / "empty-bin"
        empty_bin.mkdir()
        env = {"HOME": str(home), "CODEX_HOME": str(Path(tmp) / "codex-home"), "PATH": str(empty_bin)}
        status = run_script(CCSTATUS, "claude", "-ClaudeSettingsPath", str(settings_path), "--json", env=env)
        assert status.returncode == 1
        payload = json.loads(status.stdout)
        assert payload["overall"] == "blocked"
        assert payload["dispatchAllowed"] is False
        assert payload["handoff"]["delegateStatus"] == "REFUSED"
        assert payload["handoff"]["childThreadAction"] == "do_not_call_delegate_to_claude"
        assert payload["backendReachable"] is False
        assert payload["ccswitchProvider"]["provider"] == "cc-switch"
        assert payload["ccswitchProvider"]["loadStatus"] == "not_found"
        assert "secret-token" not in status.stdout


def test_ccstatus_run_returns_wait_handoff_for_active_run() -> None:
    with tempfile.TemporaryDirectory(prefix="codex_with_cc_status_run_") as tmp:
        artifact_root = Path(tmp) / "artifacts"
        run_id = write_running_fixture(artifact_root)
        status = run_script(CCSTATUS, "run", "-RunId", run_id, "-ArtifactRoot", str(artifact_root), "--json")
        assert status.returncode == 0, status.stdout + status.stderr
        payload = json.loads(status.stdout)
        assert payload["overall"] == "running"
        assert payload["handoff"]["delegateStatus"] == "WAITING"
        assert payload["handoff"]["recommendedWaitSeconds"] == 60
        assert "ccsupervise" in payload["handoff"]["nextCommand"]
        assert payload["acceptanceAllowed"] is False


def test_ccstatus_audit_writes_canonical_package_for_reviewable_run() -> None:
    with tempfile.TemporaryDirectory(prefix="codex_with_cc_audit_") as tmp:
        root = Path(tmp)
        artifact_root = root / "artifacts"
        task = root / "task.md"
        task.write_text(compliant_task("audit reviewable dry run"), encoding="utf-8")
        delegated = run_script(
            DELEGATE,
            "-TaskFile",
            str(task),
            "-WorkflowId",
            "wf-audit",
            "-TaskId",
            "task-audit",
            "-Role",
            "implementer",
            "-ArtifactRoot",
            str(artifact_root),
            "-SessionKey",
            "audit-session",
            "-DryRun",
            env={"CODEX_CLAUDE_CHILD_THREAD": "1"},
        )
        assert delegated.returncode == 0, delegated.stdout + delegated.stderr
        run_id = run_id_from_output(delegated.stdout)

        audit = run_script(CCSTATUS, "audit", "-RunId", run_id, "-ArtifactRoot", str(artifact_root), "--json")

        assert audit.returncode == 0, audit.stdout + audit.stderr
        payload = json.loads(audit.stdout)
        assert payload["auditType"] == "codex-with-cc-run-audit"
        assert payload["workerClaim"] == "DONE"
        assert payload["verifierPassed"] is True
        assert payload["canEnterReview"] is True
        assert payload["acceptanceAllowed"] is False
        assert "spec_review" in payload["missingGates"]
        assert payload["mayOverrideVerifier"] is False
        assert payload["dsRouting"]["recommendation"] == "not_recommended"
        assert payload["dsRouting"]["trigger"] == "missing_review_gates"
        assert payload["dsRouting"]["automaticDispatch"] is False
        assert payload["dsRouting"]["mayOverrideVerifier"] is False
        assert Path(payload["auditPath"]).exists()
        assert Path(payload["auditMarkdownPath"]).exists()
        stored_audit = json.loads(Path(payload["auditPath"]).read_text(encoding="utf-8"))
        assert stored_audit["runId"] == run_id
        assert stored_audit["dsRouting"]["recommendation"] == "not_recommended"


def test_ccstatus_audit_writes_workflow_rollup_package() -> None:
    with tempfile.TemporaryDirectory(prefix="codex_with_cc_workflow_audit_") as tmp:
        root = Path(tmp)
        artifact_root = root / "artifacts"
        task = root / "task.md"
        task.write_text(compliant_task("workflow audit dry run"), encoding="utf-8")
        delegated = run_script(
            DELEGATE,
            "-TaskFile",
            str(task),
            "-WorkflowId",
            "wf-rollup",
            "-TaskId",
            "task-rollup",
            "-Role",
            "implementer",
            "-ArtifactRoot",
            str(artifact_root),
            "-SessionKey",
            "rollup-session",
            "-DryRun",
            env={"CODEX_CLAUDE_CHILD_THREAD": "1"},
        )
        assert delegated.returncode == 0, delegated.stdout + delegated.stderr

        audit = run_script(CCSTATUS, "audit", "-WorkflowId", "wf-rollup", "-ArtifactRoot", str(artifact_root), "--json")

        assert audit.returncode == 0, audit.stdout + audit.stderr
        payload = json.loads(audit.stdout)
        assert payload["auditType"] == "codex-with-cc-workflow-audit"
        assert payload["runCount"] == 1
        assert payload["acceptanceAllowed"] is False
        assert payload["mainThreadAction"] == "dispatch_missing_review_gates"
        assert "spec_review" in payload["missingGates"]
        assert "workflow_final_acceptance" in payload["missingGates"]
        assert payload["mayOverrideVerifier"] is False
        assert payload["dsRouting"]["recommendation"] == "not_recommended"
        assert payload["dsRouting"]["trigger"] == "missing_review_gates"
        assert payload["dsRouting"]["automaticDispatch"] is False
        assert payload["dsRouting"]["mayOverrideVerifier"] is False
        assert Path(payload["auditPath"]).exists()
        assert Path(payload["auditMarkdownPath"]).exists()
        stored_audit = json.loads(Path(payload["auditPath"]).read_text(encoding="utf-8"))
        assert stored_audit["workflowId"] == "wf-rollup"
        assert stored_audit["dsRouting"]["recommendation"] == "not_recommended"


def test_delegate_refuses_before_claude_when_preflight_fails() -> None:
    with tempfile.TemporaryDirectory(prefix="codex_with_cc_delegate_refusal_") as tmp:
        root = Path(tmp)
        home = root / "home"
        settings_path = home / ".claude" / "settings.json"
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        settings_path.write_text(
            json.dumps({"model": "opus", "env": {"ANTHROPIC_BASE_URL": "http://127.0.0.1:9"}}),
            encoding="utf-8",
        )
        artifact_root = root / "artifacts"
        task = root / "task.md"
        task.write_text(compliant_task("preflight refusal"), encoding="utf-8")
        result = run_script(
            DELEGATE,
            "-TaskFile",
            str(task),
            "-WorkflowId",
            "wf-refused",
            "-TaskId",
            "task-refused",
            "-Role",
            "implementer",
            "-ArtifactRoot",
            str(artifact_root),
            "-SessionKey",
            "refused-session",
            env={"CODEX_CLAUDE_CHILD_THREAD": "1", "HOME": str(home), "CODEX_HOME": str(root / "codex-home")},
        )
        assert result.returncode == 1
        assert "PreflightHandoff:" in result.stdout
        run_id = run_id_from_output(result.stdout)
        status_json = json.loads((artifact_root / f"status_{run_id}.json").read_text(encoding="utf-8"))
        config_json = json.loads((artifact_root / f"config_{run_id}.json").read_text(encoding="utf-8"))
        output = (artifact_root / f"claude_{run_id}.md").read_text(encoding="utf-8")
        assert status_json["status"] == "failed"
        assert status_json["failureDisposition"] == "NEED_HUMAN_INTERVENTION"
        assert status_json["handoff"]["delegateStatus"] == "REFUSED"
        assert config_json["businessAcceptance"] == "blocked"
        assert "Claude Code runtime preflight failed" in output
        assert (artifact_root / "workflow_wf-refused.json").exists()

        audit = run_script(CCSTATUS, "audit", "-RunId", run_id, "-ArtifactRoot", str(artifact_root), "--json")
        assert audit.returncode == 0, audit.stdout + audit.stderr
        audit_json = json.loads(audit.stdout)
        assert audit_json["executionLayerFailure"] is True
        assert audit_json["failureLayer"] == "claude_api_socket"
        assert audit_json["mainThreadAction"] == "run_runtime_diagnostics"
        assert audit_json["acceptanceAllowed"] is False
        assert audit_json["dsRouting"]["recommendation"] == "recommended"
        assert audit_json["dsRouting"]["trigger"] == "execution_layer_failure"
        assert audit_json["dsRouting"]["role"] == "forensic-analyst"
        assert audit_json["dsRouting"]["model"] == "deepseek-v4-pro"
        assert audit_json["dsRouting"]["automaticDispatch"] is False
        assert audit_json["dsRouting"]["mayOverrideVerifier"] is False


def test_pageindex_socket_failure_fixture_is_execution_layer_failure_not_acceptance() -> None:
    with tempfile.TemporaryDirectory(prefix="codex_with_cc_pageindex_failure_") as tmp:
        artifact_root = Path(tmp) / "artifacts"
        run_id = write_pageindex_socket_failure_fixture(artifact_root)
        verify_artifacts(run_id, str(artifact_root))

        run_status = run_script(CCSTATUS, "run", "-RunId", run_id, "-ArtifactRoot", str(artifact_root), "--json")
        assert run_status.returncode == 0, run_status.stdout + run_status.stderr
        run_payload = json.loads(run_status.stdout)
        handoff = run_payload["handoff"]
        assert run_payload["summary"]["state"] == "FAILED"
        assert run_payload["summary"]["deterministicVerifierResult"]["status"] == "passed"
        assert handoff["delegateStatus"] == "FAILED"
        assert handoff["acceptanceAllowed"] is False
        assert handoff["mainThreadAction"] == "run_runtime_diagnostics"
        assert handoff["failureLayer"] == "claude_api_connection"
        assert handoff["businessAcceptance"] == "blocked"
        assert handoff["businessFilesChanged"] is False
        assert handoff["safeToRetrySameTaskFile"] is True
        assert handoff["mayOverrideImplementation"] is False

        audit = run_script(CCSTATUS, "audit", "-RunId", run_id, "-ArtifactRoot", str(artifact_root), "--json")
        assert audit.returncode == 0, audit.stdout + audit.stderr
        audit_payload = json.loads(audit.stdout)
        assert audit_payload["executionLayerFailure"] is True
        assert audit_payload["businessFailure"] is False
        assert audit_payload["canEnterReview"] is False
        assert audit_payload["acceptanceAllowed"] is False
        assert audit_payload["workerOutcome"] == "FAIL"
        assert audit_payload["businessAcceptance"] == "blocked"
        assert audit_payload["businessFilesChanged"] is False
        assert audit_payload["safeToRetrySameTaskFile"] is True
        assert audit_payload["mainThreadAction"] == "run_runtime_diagnostics"
        assert audit_payload["dsRouting"]["recommendation"] == "recommended"
        assert audit_payload["dsRouting"]["trigger"] == "execution_layer_failure"
        assert audit_payload["dsRouting"]["role"] == "forensic-analyst"
        assert audit_payload["dsRouting"]["automaticDispatch"] is False
        assert audit_payload["dsRouting"]["canAcceptWorkflowResults"] is False
        assert Path(audit_payload["auditPath"]).exists()

        built = run_script(CCINDEX, "build", "-ArtifactRoot", str(artifact_root), "--json")
        assert built.returncode == 0, built.stdout + built.stderr
        index = json.loads(built.stdout)
        indexed_run = index["records"][0]["runSummaries"][0]
        assert indexed_run["failureLayer"] == "claude_api_connection"
        assert indexed_run["executionLayerFailure"] is True
        assert indexed_run["businessAcceptance"] == "blocked"
        assert indexed_run["businessFilesChanged"] is False

        dash_root = Path(tmp) / "dashboard"
        dash = run_script(CCDASH, "build", "-ArtifactRoot", str(artifact_root), "-OutputRoot", str(dash_root), "--json")
        assert dash.returncode == 0, dash.stdout + dash.stderr
        html = Path(json.loads(dash.stdout)["htmlPath"]).read_text(encoding="utf-8")
        assert "claude_api_connection" in html
        assert "blocked" in html
