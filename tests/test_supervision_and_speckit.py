#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "skills" / "codex-with-cc" / "scripts"
CCWATCH = SCRIPTS / "ccwatch.py"
CCSUPERVISE = SCRIPTS / "ccsupervise.py"
CCSPEC = SCRIPTS / "ccspec.py"
CCDOCTOR = SCRIPTS / "ccdoctor.py"
CCCLEAN = SCRIPTS / "ccclean.py"


def run_script(script: Path, *args: str, cwd: Path = REPO) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), *args],
        cwd=cwd,
        text=True,
        capture_output=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )


def write_running_run(root: Path, run_id: str = "run-supervisor-test") -> None:
    root.mkdir(parents=True, exist_ok=True)
    config_path = root / f"config_{run_id}.json"
    status_path = root / f"status_{run_id}.json"
    stream_path = root / f"stream_{run_id}.jsonl"
    output_path = root / f"claude_{run_id}.md"
    trace_path = root / f"trace_{run_id}.log"
    workflow_path = root / "workflow_wf-supervisor-test.json"
    config = {
        "artifactSchema": 3,
        "invocationContract": "codex_with_cc_workflow",
        "runId": run_id,
        "workflowId": "wf-supervisor-test",
        "taskId": "task-supervisor-test",
        "role": "implementer",
        "runnerType": "claude_code",
        "outputPath": str(output_path),
        "statusPath": str(status_path),
        "rawStreamPath": str(stream_path),
        "tracePath": str(trace_path),
    }
    status = {
        "artifactSchema": 3,
        "invocationContract": "codex_with_cc_workflow",
        "runId": run_id,
        "workflowId": "wf-supervisor-test",
        "taskId": "task-supervisor-test",
        "role": "implementer",
        "runnerType": "claude_code",
        "status": "running",
        "outputPath": str(output_path),
        "rawStreamPath": str(stream_path),
        "tracePath": str(trace_path),
    }
    workflow = {
        "artifactSchema": 3,
        "invocationContract": "codex_with_cc_workflow",
        "workflowId": "wf-supervisor-test",
        "tasks": {
            "task-supervisor-test": {
                "taskId": "task-supervisor-test",
                "role": "implementer",
                "runs": [run_id],
                "status": "running",
            }
        },
        "runs": {
            run_id: {
                "runId": run_id,
                "taskId": "task-supervisor-test",
                "role": "implementer",
                "runnerType": "claude_code",
                "status": "running",
                "configPath": str(config_path),
                "statusPath": str(status_path),
                "outputPath": str(output_path),
                "rawStreamPath": str(stream_path),
                "tracePath": str(trace_path),
            }
        },
    }
    config_path.write_text(json.dumps(config), encoding="utf-8")
    status_path.write_text(json.dumps(status), encoding="utf-8")
    stream_path.write_text('{"type":"assistant","model":"test-model"}\n', encoding="utf-8")
    trace_path.write_text("[running]\n", encoding="utf-8")
    workflow_path.write_text(json.dumps(workflow), encoding="utf-8")


def worker_report(final_result: str) -> str:
    return "\n".join(
        [
            "Status",
            final_result,
            "",
            "Role",
            "implementer",
            "",
            "Summary",
            f"Cleanup fixture finished with {final_result}.",
            "",
            "Changed Files",
            "None",
            "",
            "Verification",
            "- fixture verification recorded",
            "",
            "Findings",
            "None",
            "",
            "Final Result",
            final_result,
            "",
            "Risks Or Follow-ups",
            "None",
        ]
    )


def write_cleanup_workflow(root: Path, workflow_id: str, run_id: str, status: str, final_result: str, old_days: int) -> None:
    root.mkdir(parents=True, exist_ok=True)
    config_path = root / f"config_{run_id}.json"
    status_path = root / f"status_{run_id}.json"
    output_path = root / f"claude_{run_id}.md"
    prompt_path = root / f"prompt_{run_id}.md"
    stream_path = root / f"stream_{run_id}.jsonl"
    trace_path = root / f"trace_{run_id}.log"
    workflow_path = root / f"workflow_{workflow_id}.json"
    common = {
        "artifactSchema": 3,
        "invocationContract": "codex_with_cc_workflow",
        "runId": run_id,
        "workflowId": workflow_id,
        "taskId": f"task-{run_id}",
        "role": "implementer",
        "runnerType": "claude_code",
        "outputPath": str(output_path),
        "promptPath": str(prompt_path),
        "rawStreamPath": str(stream_path),
        "tracePath": str(trace_path),
    }
    config = {**common, "statusPath": str(status_path), "configPath": str(config_path)}
    status_obj = {**common, "status": status, "statusPath": str(status_path), "configPath": str(config_path)}
    workflow = {
        "artifactSchema": 3,
        "invocationContract": "codex_with_cc_workflow",
        "workflowId": workflow_id,
        "tasks": {
            f"task-{run_id}": {
                "taskId": f"task-{run_id}",
                "role": "implementer",
                "runs": [run_id],
                "status": status,
            }
        },
        "runs": {
            run_id: {
                "runId": run_id,
                "taskId": f"task-{run_id}",
                "role": "implementer",
                "runnerType": "claude_code",
                "status": status,
                "reportStatus": final_result,
                "reportFinalResult": final_result,
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
    status_path.write_text(json.dumps(status_obj), encoding="utf-8")
    output_path.write_text(worker_report(final_result), encoding="utf-8")
    prompt_path.write_text("# prompt\n", encoding="utf-8")
    stream_path.write_text('{"type":"result","subtype":"success"}\n', encoding="utf-8")
    trace_path.write_text("[fixture]\n", encoding="utf-8")
    workflow_path.write_text(json.dumps(workflow), encoding="utf-8")
    old = time.time() - old_days * 86400
    for path in (config_path, status_path, output_path, prompt_path, stream_path, trace_path, workflow_path):
        os.utime(path, (old, old))


def test_ccwatch_and_ccsupervise_report_artifact_grounded_run_state() -> None:
    with tempfile.TemporaryDirectory(prefix="codex_with_cc_supervision_") as tmp:
        root = Path(tmp)
        write_running_run(root)

        watched = run_script(
            CCWATCH,
            "-RunId",
            "run-supervisor-test",
            "-ArtifactRoot",
            str(root),
            "--json",
            cwd=REPO,
        )
        assert watched.returncode == 0, watched.stdout + watched.stderr
        watch_json = json.loads(watched.stdout)
        assert watch_json["supervisorType"] == "run-supervisor"
        assert watch_json["state"] == "RUNNING_ACTIVE"
        assert watch_json["deterministicVerifierResult"]["status"] == "not-run"
        assert watch_json["mayOverrideVerifier"] is False

        supervised = run_script(
            CCSUPERVISE,
            "-RunId",
            "run-supervisor-test",
            "-ArtifactRoot",
            str(root),
            "--json",
            cwd=REPO,
        )
        assert supervised.returncode == 0, supervised.stdout + supervised.stderr
        supervisor_json = root / "supervisor_run-supervisor-test.json"
        supervisor_md = root / "supervisor_run-supervisor-test.md"
        assert supervisor_json.exists()
        assert supervisor_md.exists()
        stored = json.loads(supervisor_json.read_text(encoding="utf-8"))
        assert stored["state"] == "RUNNING_ACTIVE"
        assert stored["recommendedAction"] == "continue_waiting_on_run_supervisor"
        assert "mayOverrideVerifier: false" in supervisor_md.read_text(encoding="utf-8")

        workflow = run_script(
            CCWATCH,
            "-WorkflowId",
            "wf-supervisor-test",
            "-ArtifactRoot",
            str(root),
            "--json",
            cwd=REPO,
        )
        assert workflow.returncode == 0, workflow.stdout + workflow.stderr
        workflow_json = json.loads(workflow.stdout)
        assert workflow_json["stateCounts"]["RUNNING_ACTIVE"] == 1


def test_ccspec_can_create_and_list_tracked_specs() -> None:
    with tempfile.TemporaryDirectory(prefix="codex_with_cc_speckit_") as tmp:
        root = Path(tmp) / "specs" / "codex-with-cc-plus"
        created = run_script(CCSPEC, "-SpecRoot", str(root), "new", "sample-flow", "-Title", "Sample Flow")
        assert created.returncode == 0, created.stdout + created.stderr
        path = Path(created.stdout.strip())
        assert path.exists()
        assert "# Sample Flow" in path.read_text(encoding="utf-8")

        listed = run_script(CCSPEC, "-SpecRoot", str(root), "list")
        assert listed.returncode == 0, listed.stdout + listed.stderr
        assert "sample-flow.md" in listed.stdout


def test_ccdoctor_reports_deterministic_preflight_state() -> None:
    with tempfile.TemporaryDirectory(prefix="codex_with_cc_doctor_") as tmp:
        root = Path(tmp) / "artifacts"
        result = run_script(CCDOCTOR, "-ArtifactRoot", str(root), "--json")

        assert result.returncode in (0, 1), result.stdout + result.stderr
        report = json.loads(result.stdout)
        assert report["doctorType"] == "codex-with-cc-preflight"
        assert report["recommendedAction"] in {
            "dispatch_allowed",
            "dispatch_allowed_but_review_warnings",
            "fix_local_environment_before_dispatch",
        }
        assert report["artifactRoot"] == str(root.resolve())
        check_names = {item["name"] for item in report["checks"]}
        assert "python_runtime" in check_names
        assert "workflow_contract" in check_names
        assert "artifact_root_writable" in check_names
        assert "claude_cli_available" in check_names


def test_ccclean_plans_and_applies_reversible_artifact_cleanup() -> None:
    with tempfile.TemporaryDirectory(prefix="codex_with_cc_clean_") as tmp:
        root = Path(tmp) / "artifacts"
        trash = Path(tmp) / "trash"
        write_cleanup_workflow(root, "wf-done", "run-done", "completed", "DONE", old_days=40)
        write_cleanup_workflow(root, "wf-fail", "run-fail", "failed", "FAIL", old_days=40)
        write_cleanup_workflow(root, "wf-recent", "run-recent", "completed", "DONE", old_days=1)

        planned = run_script(CCCLEAN, "plan", "-ArtifactRoot", str(root), "-TrashRoot", str(trash), "--json")
        assert planned.returncode == 0, planned.stdout + planned.stderr
        plan = json.loads(planned.stdout)
        assert plan["cleanupType"] == "codex-with-cc-artifact-cleanup"
        assert plan["dryRun"] is True
        by_workflow = {item["workflowId"]: item for item in plan["items"]}
        assert by_workflow["wf-done"]["eligible"] is True
        assert by_workflow["wf-done"]["plannedAction"] == "move-to-trash"
        assert by_workflow["wf-done"]["confidence"] == "high"
        assert by_workflow["wf-fail"]["eligible"] is False
        assert "require -IncludeFailures" in "; ".join(by_workflow["wf-fail"]["protectionReasons"])
        assert by_workflow["wf-recent"]["eligible"] is False
        assert "newer than cleanup cutoff" in "; ".join(by_workflow["wf-recent"]["protectionReasons"])

        without_confirm = run_script(CCCLEAN, "apply", "-ArtifactRoot", str(root), "-TrashRoot", str(trash), "--json")
        assert without_confirm.returncode != 0
        assert "requires -ConfirmDelete" in without_confirm.stderr

        applied = run_script(CCCLEAN, "apply", "-ArtifactRoot", str(root), "-TrashRoot", str(trash), "-ConfirmDelete", "--json")
        assert applied.returncode == 0, applied.stdout + applied.stderr
        result = json.loads(applied.stdout)
        assert result["status"] == "applied"
        assert result["dryRun"] is False
        assert result["movedFiles"]
        assert not (root / "workflow_wf-done.json").exists()
        assert not (root / "status_run-done.json").exists()
        assert (root / "workflow_wf-fail.json").exists()
        assert (root / "workflow_wf-recent.json").exists()
        manifest_path = Path(result["manifestPath"])
        assert manifest_path.exists()
        assert trash.resolve() in manifest_path.resolve().parents


def test_ccclean_filters_failures_only_when_user_opts_in() -> None:
    with tempfile.TemporaryDirectory(prefix="codex_with_cc_clean_filter_") as tmp:
        root = Path(tmp) / "artifacts"
        write_cleanup_workflow(root, "wf-fail", "run-fail", "failed", "FAIL", old_days=45)
        write_cleanup_workflow(root, "wf-done", "run-done", "completed", "DONE", old_days=45)

        planned = run_script(
            CCCLEAN,
            "plan",
            "-ArtifactRoot",
            str(root),
            "-Result",
            "FAIL",
            "-IncludeFailures",
            "--json",
        )
        assert planned.returncode == 0, planned.stdout + planned.stderr
        plan = json.loads(planned.stdout)
        assert [item["workflowId"] for item in plan["items"]] == ["wf-fail"]
        assert plan["items"][0]["eligible"] is True
