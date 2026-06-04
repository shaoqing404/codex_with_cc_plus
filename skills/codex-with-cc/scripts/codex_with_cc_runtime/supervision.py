from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from .artifacts import resolve_artifact_root, verify_artifacts
from .common import ARTIFACT_SCHEMA_VERSION, INVOCATION_CONTRACT, DelegateError, now_iso
from .io_utils import load_json, read_text, write_json, write_text
from .paths import repo_root
from .reports import parse_report_final_result, parse_report_role, parse_report_status, report_summary_line
from .workflow import workflow_path


RUN_SUPERVISOR_STATES = (
    "STARTING",
    "RUNNING_ACTIVE",
    "RUNNING_QUIET",
    "REPORT_READY",
    "RUN_VERIFIED",
    "STALE",
    "FAILED",
)


def _path_from_artifact(root: Path, data: dict[str, Any], key: str, fallback_name: str) -> Path:
    value = data.get(key)
    if value:
        path = Path(str(value))
        return path if path.is_absolute() else (root / path.name).resolve()
    return (root / fallback_name).resolve()


def _file_meta(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"path": str(path), "exists": False}
    stat = path.stat()
    return {
        "path": str(path),
        "exists": True,
        "sizeBytes": stat.st_size,
        "modifiedAt": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(stat.st_mtime)),
        "modifiedEpoch": stat.st_mtime,
    }


def _last_stream_event(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"path": str(path), "exists": False, "lastLine": ""}
    last_line = ""
    for line in read_text(path).splitlines():
        if line.strip():
            last_line = line.strip()
    event: dict[str, Any] = {"path": str(path), "exists": True, "lastLine": last_line}
    if last_line:
        try:
            parsed = json.loads(last_line)
            event["type"] = parsed.get("type")
            event["subtype"] = parsed.get("subtype")
            if isinstance(parsed.get("usage"), dict):
                event["usage"] = parsed["usage"]
            if parsed.get("model"):
                event["model"] = parsed.get("model")
        except json.JSONDecodeError:
            event["type"] = "unparsed"
    return event


def _verification_result(run_id: str, root: Path, should_verify: bool) -> dict[str, Any]:
    if not should_verify:
        return {"status": "not-run", "reason": "run is not in a terminal state"}
    try:
        verify_artifacts(run_id, str(root))
    except DelegateError as exc:
        return {"status": "failed", "error": str(exc), "mayOverrideVerifier": False}
    return {"status": "passed", "mayOverrideVerifier": False}


def build_run_supervisor_summary(
    run_id: str,
    artifact_root_value: str | None = None,
    stale_after_seconds: int = 600,
    verify: bool = True,
) -> dict[str, Any]:
    root = resolve_artifact_root(artifact_root_value, run_id=run_id)
    config_path = root / f"config_{run_id}.json"
    status_path = root / f"status_{run_id}.json"
    if not config_path.exists() and not status_path.exists():
        raise DelegateError(f"Run artifacts were not found for RunId: {run_id}")

    config = load_json(config_path) if config_path.exists() else {}
    status = load_json(status_path) if status_path.exists() else {}
    workflow_id = str(config.get("workflowId") or status.get("workflowId") or "")
    task_id = str(config.get("taskId") or status.get("taskId") or "")
    run_status = str(status.get("status") or "starting")
    output_name = "report_" + run_id + ".md" if str(config.get("runnerType")) == "openai_compatible_report" else "claude_" + run_id + ".md"
    output_path = _path_from_artifact(root, config, "outputPath", output_name)
    stream_path = _path_from_artifact(root, config, "rawStreamPath", f"stream_{run_id}.jsonl")
    trace_path = _path_from_artifact(root, config, "tracePath", f"trace_{run_id}.log")

    file_metas = [_file_meta(path) for path in (config_path, status_path, output_path, stream_path, trace_path)]
    newest = max((meta.get("modifiedEpoch", 0) for meta in file_metas if meta.get("exists")), default=0)
    idle_seconds = max(0, int(time.time() - newest)) if newest else None
    report_text = read_text(output_path) if output_path.exists() else ""
    report_status = parse_report_status(report_text) if report_text else ""
    report_final = parse_report_final_result(report_text) if report_text else ""
    report_role = parse_report_role(report_text) if report_text else ""
    terminal = run_status in ("completed", "failed")

    if terminal and output_path.exists():
        state = "REPORT_READY"
    elif run_status == "failed":
        state = "FAILED"
    elif run_status == "running":
        state = "STALE" if idle_seconds is not None and idle_seconds >= stale_after_seconds else "RUNNING_ACTIVE"
    elif run_status == "starting":
        state = "STARTING"
    else:
        state = "RUNNING_QUIET"

    verification = _verification_result(run_id, root, verify and terminal)
    if verification.get("status") == "passed":
        state = "RUN_VERIFIED"
    elif verification.get("status") == "failed":
        state = "FAILED"

    recommended_action = {
        "RUN_VERIFIED": "main_accept_or_review_report",
        "REPORT_READY": "run_deterministic_verifier",
        "FAILED": "inspect_failure_or_trigger_forensic_analyst",
        "STALE": "ask_run_supervisor_for_staleness_details_or_human_decision",
        "RUNNING_ACTIVE": "continue_waiting_on_run_supervisor",
        "RUNNING_QUIET": "continue_waiting_or_check_trace",
        "STARTING": "continue_waiting",
    }.get(state, "human_review_required")

    return {
        "artifactSchema": ARTIFACT_SCHEMA_VERSION,
        "invocationContract": INVOCATION_CONTRACT,
        "supervisorType": "run-supervisor",
        "runId": run_id,
        "workflowId": workflow_id,
        "taskId": task_id,
        "runnerType": config.get("runnerType") or status.get("runnerType") or "unknown",
        "role": config.get("role") or status.get("role") or "unknown",
        "state": state,
        "runStatus": run_status,
        "idleSeconds": idle_seconds,
        "staleAfterSeconds": stale_after_seconds,
        "lastStreamEvent": _last_stream_event(stream_path),
        "report": {
            "path": str(output_path),
            "exists": output_path.exists(),
            "status": report_status,
            "finalResult": report_final,
            "role": report_role,
            "summary": report_summary_line(report_text) if report_text else "",
        },
        "artifacts": {
            "root": str(root),
            "config": _file_meta(config_path),
            "status": _file_meta(status_path),
            "output": _file_meta(output_path),
            "stream": _file_meta(stream_path),
            "trace": _file_meta(trace_path),
        },
        "deterministicVerifierResult": verification,
        "mayOverrideVerifier": False,
        "recommendedAction": recommended_action,
        "updatedAt": now_iso(),
    }


def build_workflow_watch_summary(workflow_id: str, artifact_root_value: str | None = None) -> dict[str, Any]:
    root = resolve_artifact_root(artifact_root_value, workflow_id=workflow_id)
    path = workflow_path(root, workflow_id)
    if not path.exists():
        raise DelegateError(f"Workflow artifact was not found: {path}")
    workflow = load_json(path)
    runs = []
    for run_id in sorted((workflow.get("runs") or {}).keys()):
        try:
            runs.append(build_run_supervisor_summary(str(run_id), str(root), verify=False))
        except DelegateError as exc:
            runs.append({"runId": str(run_id), "state": "FAILED", "error": str(exc)})
    state_counts: dict[str, int] = {}
    for item in runs:
        state = str(item.get("state") or "UNKNOWN")
        state_counts[state] = state_counts.get(state, 0) + 1
    return {
        "artifactSchema": ARTIFACT_SCHEMA_VERSION,
        "invocationContract": INVOCATION_CONTRACT,
        "watchType": "workflow",
        "workflowId": workflow_id,
        "artifactRoot": str(root),
        "stateCounts": state_counts,
        "finalAcceptance": workflow.get("finalAcceptance", {}),
        "runs": runs,
        "updatedAt": now_iso(),
    }


def render_watch_text(summary: dict[str, Any]) -> str:
    if summary.get("watchType") == "workflow":
        lines = [
            f"Workflow: {summary.get('workflowId')}",
            f"ArtifactRoot: {summary.get('artifactRoot')}",
            "StateCounts: " + ", ".join(f"{key}={value}" for key, value in sorted((summary.get("stateCounts") or {}).items())),
        ]
        for run in summary.get("runs") or []:
            lines.append(f"- {run.get('runId')}: {run.get('state')} / {run.get('recommendedAction', 'n/a')}")
        return "\n".join(lines)
    return "\n".join(
        [
            f"Run: {summary.get('runId')}",
            f"Workflow: {summary.get('workflowId')}",
            f"State: {summary.get('state')}",
            f"RunStatus: {summary.get('runStatus')}",
            f"IdleSeconds: {summary.get('idleSeconds')}",
            f"Report: {(summary.get('report') or {}).get('path')}",
            f"Verifier: {(summary.get('deterministicVerifierResult') or {}).get('status')}",
            f"RecommendedAction: {summary.get('recommendedAction')}",
        ]
    )


def write_supervisor_artifacts(summary: dict[str, Any], artifact_root_value: str | None = None) -> tuple[Path, Path]:
    root = resolve_artifact_root(artifact_root_value, run_id=str(summary["runId"]))
    run_id = str(summary["runId"])
    json_path = root / f"supervisor_{run_id}.json"
    md_path = root / f"supervisor_{run_id}.md"
    write_json(json_path, summary)
    write_text(
        md_path,
        "\n".join(
            [
                "# Run Supervisor Report",
                "",
                f"RunId: {run_id}",
                f"WorkflowId: {summary.get('workflowId')}",
                f"State: {summary.get('state')}",
                f"RunStatus: {summary.get('runStatus')}",
                f"RecommendedAction: {summary.get('recommendedAction')}",
                f"mayOverrideVerifier: {str(summary.get('mayOverrideVerifier')).lower()}",
                "",
                "## Deterministic Verifier Result",
                "",
                json.dumps(summary.get("deterministicVerifierResult"), ensure_ascii=False, indent=2),
            ]
        )
        + "\n",
    )
    return json_path, md_path


def spec_root() -> Path:
    return repo_root() / "specs" / "codex-with-cc-plus"


def run_ccwatch(ns: argparse.Namespace) -> int:
    if ns.run_id:
        summary = build_run_supervisor_summary(ns.run_id, ns.artifact_root, ns.stale_after_seconds, verify=not ns.no_verify)
    else:
        summary = build_workflow_watch_summary(ns.workflow_id, ns.artifact_root)
    if ns.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(render_watch_text(summary))
    return 0


def run_ccsupervise(ns: argparse.Namespace) -> int:
    summary = build_run_supervisor_summary(ns.run_id, ns.artifact_root, ns.stale_after_seconds, verify=not ns.no_verify)
    json_path, md_path = write_supervisor_artifacts(summary, ns.artifact_root)
    if ns.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(render_watch_text(summary))
        print(f"SupervisorJson: {json_path}")
        print(f"SupervisorMarkdown: {md_path}")
    return 0 if summary["state"] in ("RUN_VERIFIED", "REPORT_READY", "RUNNING_ACTIVE", "STARTING") else 1


def run_ccspec(ns: argparse.Namespace) -> int:
    root = Path(ns.spec_root).resolve() if ns.spec_root else spec_root()
    if ns.ccspec_command == "path":
        print(root)
        return 0
    if ns.ccspec_command == "list":
        if not root.exists():
            print(f"No spec root found: {root}")
            return 0
        for path in sorted(root.rglob("*.md")):
            print(path.relative_to(root).as_posix())
        return 0
    if ns.ccspec_command == "new":
        slug = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in ns.slug.strip().lower()).strip("-") or "new-spec"
        path = root / f"{slug}.md"
        if path.exists() and not ns.force:
            raise DelegateError(f"Spec already exists: {path}")
        template = root / "templates" / "spec.md"
        if template.exists():
            content = read_text(template)
        else:
            content = DEFAULT_SPEC_TEMPLATE
        content = content.replace("{{SPEC_TITLE}}", ns.title or slug.replace("-", " ").title())
        write_text(path, content)
        print(path)
        return 0
    raise DelegateError(f"Unknown ccspec command: {ns.ccspec_command}")


DEFAULT_SPEC_TEMPLATE = """# {{SPEC_TITLE}}

## Goal

## Scope

## Task Plan

## Acceptance

## Verification

## Decision Log
"""
