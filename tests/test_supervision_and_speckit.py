#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "skills" / "codex-with-cc" / "scripts"
CCWATCH = SCRIPTS / "ccwatch.py"
CCSUPERVISE = SCRIPTS / "ccsupervise.py"
CCSPEC = SCRIPTS / "ccspec.py"


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
