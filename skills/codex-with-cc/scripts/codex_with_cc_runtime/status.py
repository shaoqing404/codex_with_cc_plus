from __future__ import annotations

import argparse
import json
import socket
from types import SimpleNamespace
from typing import Any
from urllib.parse import urlparse

from .artifacts import resolve_artifact_root
from .common import ARTIFACT_SCHEMA_VERSION, INVOCATION_CONTRACT, DelegateError, now_iso
from .doctor import build_doctor_report
from .handoff import refusal_handoff, terminal_handoff, wait_handoff
from .index import build_index
from .runtime_control import build_runtime_status
from .supervision import build_run_supervisor_summary, build_workflow_watch_summary


UNAVAILABLE_MESSAGE = (
    "Claude Code is not ready. Install, configure, or restart Claude Code/OpenClaw/MiniMax "
    "before using this framework for implementation workers."
)


def _base_url(runtime: dict[str, Any]) -> str:
    settings = runtime.get("claudeSettings") if isinstance(runtime.get("claudeSettings"), dict) else {}
    safe_env = settings.get("safeEnv") if isinstance(settings.get("safeEnv"), dict) else {}
    return str(safe_env.get("ANTHROPIC_BASE_URL") or "")


def _reachable_base_url(base_url: str, timeout_seconds: float = 1.0) -> dict[str, Any]:
    if not base_url:
        return {"checked": False, "reachable": None, "reason": "no_base_url_configured"}
    parsed = urlparse(base_url)
    host = parsed.hostname
    if not host:
        return {"checked": True, "reachable": False, "reason": "base_url_missing_host"}
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        with socket.create_connection((host, port), timeout=timeout_seconds):
            return {"checked": True, "reachable": True, "host": host, "port": port}
    except OSError as exc:
        return {"checked": True, "reachable": False, "host": host, "port": port, "error": str(exc)}


def _runtime_configured(runtime: dict[str, Any]) -> bool:
    settings = runtime.get("claudeSettings") if isinstance(runtime.get("claudeSettings"), dict) else {}
    claude = runtime.get("claudeCli") if isinstance(runtime.get("claudeCli"), dict) else {}
    return bool(claude.get("path")) and settings.get("loadStatus") == "ok"


def _doctor_namespace(ns: argparse.Namespace) -> argparse.Namespace:
    artifact_root = getattr(ns, "artifact_root", None)
    if isinstance(artifact_root, list):
        artifact_root = artifact_root[0] if artifact_root else None
    return SimpleNamespace(
        artifact_root=artifact_root,
        claude_smoke=bool(getattr(ns, "claude_smoke", False)),
        timeout_seconds=int(getattr(ns, "timeout_seconds", 10)),
    )


def build_claude_status(ns: argparse.Namespace) -> dict[str, Any]:
    runtime = build_runtime_status(ns)
    doctor = build_doctor_report(_doctor_namespace(ns))
    base_url = _base_url(runtime)
    reachability = _reachable_base_url(base_url)
    runtime_configured = _runtime_configured(runtime)
    claude = runtime.get("claudeCli") if isinstance(runtime.get("claudeCli"), dict) else {}
    safe_to_dispatch = bool(doctor.get("safeToDispatch")) and runtime_configured
    if reachability.get("checked") and reachability.get("reachable") is False:
        safe_to_dispatch = False
    overall = "ready" if safe_to_dispatch else "blocked"
    failure_layer = "" if safe_to_dispatch else "claude_code_runtime_unavailable"
    if reachability.get("checked") and reachability.get("reachable") is False:
        failure_layer = "claude_api_socket"
    result = {
        "artifactSchema": ARTIFACT_SCHEMA_VERSION,
        "invocationContract": INVOCATION_CONTRACT,
        "command": "ccstatus claude",
        "overall": overall,
        "dispatchAllowed": safe_to_dispatch,
        "acceptanceAllowed": False,
        "runtimeConfigured": runtime_configured,
        "claudeCliAvailable": bool(claude.get("path")),
        "claudeCliPath": claude.get("path") or "",
        "claudeCliVersion": claude.get("version") or "",
        "openclaw": runtime.get("openclaw", {}),
        "ccwitch": runtime.get("ccwitch", {}),
        "backendBaseUrl": base_url,
        "backendReachable": reachability.get("reachable"),
        "backendReachability": reachability,
        "modelHandshake": "not_run",
        "artifactRootWritable": any(item.get("name") == "artifact_root_writable" and item.get("status") == "pass" for item in doctor.get("checks") or []),
        "failureLayer": failure_layer,
        "recommendedAction": "dispatch_allowed" if safe_to_dispatch else "check_local_claude_or_openclaw_backend",
        "nextCommand": "ccstatus preflight --json" if safe_to_dispatch else "ccruntime doctor -ClaudeSmoke --json",
        "confidence": "high" if runtime_configured else "medium",
        "runtimeStatus": runtime,
        "doctor": doctor,
        "updatedAt": now_iso(),
    }
    if not safe_to_dispatch:
        result["handoff"] = refusal_handoff(
            failure_layer=failure_layer,
            user_message=UNAVAILABLE_MESSAGE,
            next_command="ccstatus claude --json",
            confidence="high" if failure_layer == "claude_api_socket" else "medium",
        )
    return result


def build_preflight_status(ns: argparse.Namespace) -> dict[str, Any]:
    claude_status = build_claude_status(ns)
    dispatch_allowed = bool(claude_status.get("dispatchAllowed"))
    handoff = claude_status.get("handoff")
    if not handoff and dispatch_allowed:
        handoff = {
            "artifactSchema": ARTIFACT_SCHEMA_VERSION,
            "invocationContract": INVOCATION_CONTRACT,
            "handoffType": "preflight",
            "delegateStatus": "READY",
            "dispatchAllowed": True,
            "acceptanceAllowed": False,
            "mainThreadAction": "dispatch_worker",
            "childThreadAction": "may_call_delegate_to_claude",
            "recommendedWaitSeconds": 0,
            "nextCommand": "delegate_to_claude -TaskFile <task-file> ...",
            "confidence": "high",
            "mayOverrideValidator": False,
            "mayOverrideVerifier": False,
            "updatedAt": now_iso(),
        }
    return {
        "artifactSchema": ARTIFACT_SCHEMA_VERSION,
        "invocationContract": INVOCATION_CONTRACT,
        "command": "ccstatus preflight",
        "overall": "ready" if dispatch_allowed else "blocked",
        "dispatchAllowed": dispatch_allowed,
        "acceptanceAllowed": False,
        "failureLayer": "" if dispatch_allowed else claude_status.get("failureLayer") or "claude_code_runtime_unavailable",
        "humanInterventionRequired": not dispatch_allowed,
        "mainThreadAction": "dispatch_worker" if dispatch_allowed else "install_or_repair_claude_code",
        "childThreadAction": "may_call_delegate_to_claude" if dispatch_allowed else "do_not_call_delegate_to_claude",
        "nextCommand": "delegate_to_claude -TaskFile <task-file> ..." if dispatch_allowed else "ccstatus claude --json",
        "confidence": claude_status.get("confidence") or "medium",
        "claude": claude_status,
        "handoff": handoff,
        "updatedAt": now_iso(),
    }


def build_run_status(ns: argparse.Namespace) -> dict[str, Any]:
    summary = build_run_supervisor_summary(ns.run_id, ns.artifact_root, ns.stale_after_seconds, verify=not ns.no_verify)
    artifact_root = str((summary.get("artifacts") or {}).get("root") or resolve_artifact_root(ns.artifact_root, run_id=ns.run_id))
    state = str(summary.get("state") or "")
    if state in ("STARTING", "RUNNING_ACTIVE", "RUNNING_QUIET"):
        handoff = wait_handoff(summary, artifact_root=artifact_root, stale_after_seconds=ns.stale_after_seconds)
    else:
        handoff = terminal_handoff(summary, artifact_root=artifact_root)
    return {
        "artifactSchema": ARTIFACT_SCHEMA_VERSION,
        "invocationContract": INVOCATION_CONTRACT,
        "command": "ccstatus run",
        "overall": "running" if handoff.get("delegateStatus") == "WAITING" else "terminal",
        "runId": ns.run_id,
        "dispatchAllowed": False,
        "acceptanceAllowed": bool(handoff.get("acceptanceAllowed")),
        "summary": summary,
        "handoff": handoff,
        "updatedAt": now_iso(),
    }


def build_workflow_status(ns: argparse.Namespace) -> dict[str, Any]:
    summary = build_workflow_watch_summary(ns.workflow_id, ns.artifact_root)
    final_acceptance = summary.get("finalAcceptance") if isinstance(summary.get("finalAcceptance"), dict) else {}
    acceptance_allowed = final_acceptance.get("status") == "accepted"
    missing_gates = []
    if not acceptance_allowed:
        missing_gates.append("workflow_review_or_final_verifier")
    return {
        "artifactSchema": ARTIFACT_SCHEMA_VERSION,
        "invocationContract": INVOCATION_CONTRACT,
        "command": "ccstatus workflow",
        "overall": "accepted" if acceptance_allowed else "blocked",
        "workflowId": ns.workflow_id,
        "dispatchAllowed": False,
        "acceptanceAllowed": acceptance_allowed,
        "missingGates": missing_gates,
        "mainThreadAction": "accept_or_commit" if acceptance_allowed else "dispatch_missing_review_gates_or_inspect_failed_runs",
        "nextCommand": f"verify_delegate_workflow -WorkflowId {ns.workflow_id} -ArtifactRoot {summary.get('artifactRoot')}",
        "confidence": "high",
        "summary": summary,
        "mayOverrideVerifier": False,
        "updatedAt": now_iso(),
    }


def build_summary_status(ns: argparse.Namespace) -> dict[str, Any]:
    claude_status = build_claude_status(ns)
    index_report = build_index(ns)
    latest_failure_layer = ""
    for record in index_report.get("records") or []:
        for run in record.get("runSummaries") or []:
            if run.get("failureLayer"):
                latest_failure_layer = str(run.get("failureLayer"))
                break
        if latest_failure_layer:
            break
    overall = "blocked" if not claude_status.get("dispatchAllowed") else "ready"
    return {
        "artifactSchema": ARTIFACT_SCHEMA_VERSION,
        "invocationContract": INVOCATION_CONTRACT,
        "command": "ccstatus summary",
        "overall": overall,
        "dispatchAllowed": bool(claude_status.get("dispatchAllowed")),
        "acceptanceAllowed": False,
        "lastWorkerFailureLayer": latest_failure_layer,
        "recommendedAction": claude_status.get("recommendedAction"),
        "nextCommand": claude_status.get("nextCommand"),
        "confidence": claude_status.get("confidence") or "medium",
        "claude": claude_status,
        "machineIndex": index_report,
        "updatedAt": now_iso(),
    }


def render_status_text(report: dict[str, Any]) -> str:
    lines = [
        f"Command: {report.get('command')}",
        f"Overall: {report.get('overall')}",
        f"DispatchAllowed: {str(report.get('dispatchAllowed')).lower()}",
        f"AcceptanceAllowed: {str(report.get('acceptanceAllowed')).lower()}",
    ]
    if report.get("failureLayer"):
        lines.append(f"FailureLayer: {report.get('failureLayer')}")
    if report.get("recommendedAction"):
        lines.append(f"RecommendedAction: {report.get('recommendedAction')}")
    if report.get("nextCommand"):
        lines.append(f"NextCommand: {report.get('nextCommand')}")
    handoff = report.get("handoff")
    if isinstance(handoff, dict):
        lines.append(f"Handoff: {handoff.get('delegateStatus')} action={handoff.get('mainThreadAction')}")
    return "\n".join(lines)


def run_ccstatus(ns: argparse.Namespace) -> int:
    command = str(ns.ccstatus_command)
    if command == "summary":
        report = build_summary_status(ns)
    elif command == "claude":
        report = build_claude_status(ns)
    elif command == "preflight":
        report = build_preflight_status(ns)
    elif command == "run":
        report = build_run_status(ns)
    elif command == "workflow":
        report = build_workflow_status(ns)
    else:
        raise DelegateError(f"Unknown ccstatus command: {command}")
    if getattr(ns, "json", False):
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_status_text(report))
    return 0 if report.get("overall") not in {"blocked"} else 1
