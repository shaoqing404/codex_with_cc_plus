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
DELEGATE = SCRIPTS / "delegate_to_claude.py"
VERIFY_RUN = SCRIPTS / "verify_delegate_run.py"
VERIFY_WORKFLOW = SCRIPTS / "verify_delegate_workflow.py"
HOOK_SCRIPT = REPO / "hooks" / "subagent-gate-hook.mjs"
sys.path.insert(0, str(SCRIPTS))

from codex_with_cc_runtime.common import ARTIFACT_SCHEMA_VERSION, REPORT_STATUS_VALUES, WORKER_ROLES
from codex_with_cc_runtime.reports import parse_report_final_result, parse_report_role, parse_report_status, text_has_required_report_headings
from codex_with_cc_runtime.workflow import workflow_path


def workflow_report(status: str = "DONE", role: str = "researcher", final_result: str | None = None) -> str:
    final_result = final_result or status
    return "\n".join(
        (
            "Status",
            status,
            "",
            "Role",
            role,
            "",
            "Summary",
            "Completed the delegated workflow task.",
            "",
            "Changed Files",
            "None",
            "",
            "Verification",
            "- dry run artifact generation passed",
            "",
            "Findings",
            "None",
            "",
            "Final Result",
            final_result,
            "",
            "Risks Or Follow-ups",
            "None",
        )
    )


def run_hook(payload: dict) -> dict:
    result = subprocess.run(
        ["node", str(HOOK_SCRIPT)],
        input=json.dumps(payload),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=REPO,
        encoding="utf-8",
        check=False,
    )
    assert result.returncode == 0, result.stderr
    if not result.stdout.strip():
        return {}
    return json.loads(result.stdout)


def run_python(script: Path, *args: str, cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), *args],
        cwd=str(cwd),
        text=True,
        capture_output=True,
        env=env,
    )


def run_id_from_output(output: str) -> str:
    for line in output.splitlines():
        if line.startswith("RunId:"):
            return line.split(":", 1)[1].strip()
    raise AssertionError(f"RunId line missing from output:\n{output}")


def write_failed_implementer_artifacts(root: Path) -> str:
    run_id = "failed-implementer-run"
    workflow_id = "wf-failed-implementer"
    task_id = "failed-implementer-task"
    output_path = root / f"claude_{run_id}.md"
    prompt_path = root / f"prompt_{run_id}.md"
    stream_path = root / f"stream_{run_id}.jsonl"
    trace_path = root / f"trace_{run_id}.log"
    status_path = root / f"status_{run_id}.json"
    config_path = root / f"config_{run_id}.json"
    root.mkdir(parents=True, exist_ok=True)
    output_path.write_text(workflow_report(status="FAIL", role="implementer"), encoding="utf-8")
    prompt_path.write_text("# prompt", encoding="utf-8")
    stream_path.write_text('{"type":"result","subtype":"error_during_execution","is_error":true}\n', encoding="utf-8")
    trace_path.write_text("[result] error_during_execution\n", encoding="utf-8")
    common = {
        "artifactSchema": ARTIFACT_SCHEMA_VERSION,
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
        "sessionKey": "failed-implementer",
        "sessionMode": "PrimaryReuse",
        "initialSessionId": "session-a",
        "initialResume": False,
        "sessionId": "session-a",
        "resume": False,
        "attemptCount": 1,
        "retryCount": 0,
        "maxRetryCount": 0,
        "failureDisposition": "NEED_HUMAN_INTERVENTION",
        "failureSummary": "CLAUDE_API_ERROR: API Error: Unable to connect to API (ConnectionRefused)",
    }
    config = {**common, "statusPath": str(status_path)}
    status = {
        **common,
        "status": "failed",
        "exitCode": 1,
        "outputBytes": output_path.stat().st_size,
        "attempts": [
            {
                "attempt": 1,
                "sessionId": "session-a",
                "resume": False,
                "retryReason": None,
                "exitCode": 1,
                "sawAssistantText": False,
                "sawResultSuccess": False,
                "capturedFinalResult": True,
            }
        ],
    }
    config_path.write_text(json.dumps(config), encoding="utf-8")
    status_path.write_text(json.dumps(status), encoding="utf-8")
    workflow_path(root, workflow_id).write_text(
        json.dumps(
            {
                "artifactSchema": ARTIFACT_SCHEMA_VERSION,
                "invocationContract": "codex_with_cc_workflow",
                "workflowId": workflow_id,
                "tasks": {
                    task_id: {
                        "taskId": task_id,
                        "role": "implementer",
                        "scope": [],
                        "verification": [],
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
        ),
        encoding="utf-8",
    )
    return workflow_id


def test_readme_install_prompt_remains_available() -> None:
    current = (REPO / "README.md").read_text(encoding="utf-8")
    assert "请把 https://github.com/shaoqing404/codex_with_cc_plus 子代理工作流安装或更新到当前 Codex 环境。" in current
    assert ".codex-plugin/plugin.json" in current
    assert "skills/codex-with-cc/manifest.json" not in current


def test_report_contract_accepts_statuses_and_roles() -> None:
    assert ARTIFACT_SCHEMA_VERSION == 3
    assert REPORT_STATUS_VALUES == ("DONE", "DONE_WITH_CONCERNS", "NEEDS_CONTEXT", "BLOCKED", "FAIL")
    assert WORKER_ROLES == ("planner", "implementer", "researcher", "reviewer", "final-verifier")

    for status in REPORT_STATUS_VALUES:
        report = workflow_report(status=status)
        assert text_has_required_report_headings(report)
        assert parse_report_status(report) == status
        assert parse_report_final_result(report) == status
        assert parse_report_role(report) == "researcher"

    mismatched = workflow_report(status="DONE", role="reviewer", final_result="FAIL")
    assert parse_report_status(mismatched) == "DONE"
    assert parse_report_final_result(mismatched) == "FAIL"
    assert parse_report_role(mismatched) == "reviewer"


def test_delegate_dry_run_writes_workflow_artifacts_and_verifies_them() -> None:
    with tempfile.TemporaryDirectory(prefix="codex_with_cc_workflow_") as tmp:
        root = Path(tmp)
        artifact_root = root / "artifacts"
        env = {
            **os.environ,
            "CODEX_CLAUDE_CHILD_THREAD": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        task_file = root / "workflow-dry-run-task.md"
        task_file.write_text(compliant_task("workflow dry run task"), encoding="utf-8")
        result = run_python(
            DELEGATE,
            "-TaskFile",
            str(task_file),
            "-WorkflowId",
            "wf-contract",
            "-TaskId",
            "task-contract",
            "-Role",
            "researcher",
            "-Scope",
            "skills/codex-with-cc",
            "-Tests",
            "python -m pytest",
            "-DependsOn",
            "task-prereq",
            "-ArtifactRoot",
            str(artifact_root),
            "-SessionKey",
            "workflow-contract",
            "-DryRun",
            cwd=REPO,
            env=env,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        run_id = run_id_from_output(result.stdout)

        config = json.loads((artifact_root / f"config_{run_id}.json").read_text(encoding="utf-8"))
        status = json.loads((artifact_root / f"status_{run_id}.json").read_text(encoding="utf-8"))
        report = (artifact_root / f"claude_{run_id}.md").read_text(encoding="utf-8")
        workflow = json.loads(workflow_path(artifact_root, "wf-contract").read_text(encoding="utf-8"))

        assert config["artifactSchema"] == 3
        assert status["artifactSchema"] == 3
        assert config["workflowId"] == "wf-contract"
        assert config["taskId"] == "task-contract"
        assert config["role"] == "researcher"
        assert config["runnerType"] == "claude_code"
        assert status["workflowId"] == "wf-contract"
        assert status["taskId"] == "task-contract"
        assert status["role"] == "researcher"
        assert status["runnerType"] == "claude_code"
        assert text_has_required_report_headings(report)
        assert workflow["artifactSchema"] == 3
        assert workflow["workflowId"] == "wf-contract"
        assert workflow["tasks"]["task-contract"]["role"] == "researcher"
        assert workflow["tasks"]["task-contract"]["lastReportStatus"] == "DONE"
        assert workflow["tasks"]["task-contract"]["lastReportFinalResult"] == "DONE"
        assert workflow["tasks"]["task-contract"]["reviewDecision"] == "accepted"
        assert workflow["tasks"]["task-contract"]["dependsOn"] == ["task-prereq"]
        assert workflow["runs"][run_id]["taskId"] == "task-contract"
        assert workflow["runs"][run_id]["reportStatus"] == "DONE"
        assert workflow["runs"][run_id]["reportFinalResult"] == "DONE"
        assert workflow["runs"][run_id]["reportRole"] == "researcher"
        assert workflow["runs"][run_id]["reviewDecision"] == "accepted"
        assert workflow["runs"][run_id]["runnerType"] == "claude_code"

        verify_run = run_python(VERIFY_RUN, "-RunId", run_id, "-ArtifactRoot", str(artifact_root), cwd=REPO, env=env)
        verify_workflow = run_python(VERIFY_WORKFLOW, "-WorkflowId", "wf-contract", "-ArtifactRoot", str(artifact_root), cwd=REPO, env=env)

        assert verify_run.returncode == 0, verify_run.stdout + verify_run.stderr
        assert verify_workflow.returncode == 0, verify_workflow.stdout + verify_workflow.stderr
        verifier_audit_path = artifact_root / "verifier_audit_wf-contract.json"
        verifier_audit_md_path = artifact_root / "verifier_audit_wf-contract.md"
        assert verifier_audit_path.exists()
        assert verifier_audit_md_path.exists()
        verifier_audit = json.loads(verifier_audit_path.read_text(encoding="utf-8"))
        assert verifier_audit["auditType"] == "codex-with-cc-workflow-verifier-audit"
        assert verifier_audit["verifierPassed"] is True
        assert verifier_audit["acceptanceAllowed"] is True
        assert verifier_audit["mainThreadAction"] == "accept_or_commit"
        assert verifier_audit["mayOverrideVerifier"] is False
        assert {item["gate"] for item in verifier_audit["gateResults"]} >= {
            "workflow_artifact",
            "run_artifacts",
            "review_gates",
            "final_verifier_gate",
            "declared_tests",
            "parallel_scope",
        }
        assert "VerifierAudit:" in verify_workflow.stdout


def test_verify_workflow_prioritizes_failed_implementer_before_missing_reviews() -> None:
    with tempfile.TemporaryDirectory(prefix="codex_with_cc_failed_workflow_") as tmp:
        root = Path(tmp)
        artifact_root = root / "artifacts"
        workflow_id = write_failed_implementer_artifacts(artifact_root)
        env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}

        verify_workflow = run_python(VERIFY_WORKFLOW, "-WorkflowId", workflow_id, "-ArtifactRoot", str(artifact_root), cwd=REPO, env=env)

        assert verify_workflow.returncode != 0
        assert "Workflow implementer gate failed" in verify_workflow.stderr
        assert "review gates are not applicable yet" in verify_workflow.stderr
        assert "missing spec" not in verify_workflow.stderr
        verifier_audit_path = artifact_root / f"verifier_audit_{workflow_id}.json"
        verifier_audit_md_path = artifact_root / f"verifier_audit_{workflow_id}.md"
        assert verifier_audit_path.exists()
        assert verifier_audit_md_path.exists()
        verifier_audit = json.loads(verifier_audit_path.read_text(encoding="utf-8"))
        assert verifier_audit["auditType"] == "codex-with-cc-workflow-verifier-audit"
        assert verifier_audit["verifierPassed"] is False
        assert verifier_audit["acceptanceAllowed"] is False
        assert verifier_audit["failedGate"]["gate"] == "implementer_gate"
        assert verifier_audit["mainThreadAction"] == "inspect_failed_runs_or_trigger_forensics"
        assert verifier_audit["mayOverrideVerifier"] is False


def test_hook_gate_requires_workflow_payload_fields_and_write_scope_for_parallel() -> None:
    missing_workflow = run_hook(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {
                "command": (
                    "$env:CODEX_CLAUDE_CHILD_THREAD = '1'; "
                    "pwsh -NoProfile -File windows_scripts/delegate_to_claude.ps1 "
                    "-TaskFile .codex/codex_with_cc/tasks/20260514/120000000-task.md "
                    "-TaskId task-a -Role implementer"
                )
            },
        }
    )
    assert missing_workflow["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "WorkflowId" in missing_workflow["hookSpecificOutput"]["permissionDecisionReason"]

    parallel_without_scope = run_hook(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {
                "command": (
                    "$env:CODEX_CLAUDE_CHILD_THREAD = '1'; "
                    "pwsh -NoProfile -File windows_scripts/delegate_to_claude.ps1 "
                    "-TaskFile .codex/codex_with_cc/tasks/20260514/120000000-task.md "
                    "-WorkflowId wf-a -TaskId task-a -Role implementer -AllowParallel"
                )
            },
        }
    )
    assert parallel_without_scope["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "Scope" in parallel_without_scope["hookSpecificOutput"]["permissionDecisionReason"]

    compliant = run_hook(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {
                "command": (
                    "$env:CODEX_CLAUDE_CHILD_THREAD = '1'; "
                    "pwsh -NoProfile -File windows_scripts/delegate_to_claude.ps1 "
                    "-TaskFile .codex/codex_with_cc/tasks/20260514/120000000-task.md "
                    "-WorkflowId wf-a -TaskId task-a -Role researcher "
                    "-SessionKey wf-a "
                    "-Scope skills/codex-with-cc -SessionMode ParallelPool -AllowParallel"
                )
            },
        }
    )
    assert compliant == {}
