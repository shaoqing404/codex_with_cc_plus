from __future__ import annotations

import argparse
import json
import socket
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.parse import urlparse

from .artifacts import resolve_artifact_root
from .common import ARTIFACT_SCHEMA_VERSION, INVOCATION_CONTRACT, DelegateError, now_iso
from .doctor import build_doctor_report
from .handoff import refusal_handoff, terminal_handoff, wait_handoff
from .index import build_index
from .io_utils import load_json, read_text, write_json, write_text
from .reports import report_section
from .runtime_control import build_runtime_status
from .supervision import build_run_supervisor_summary, build_workflow_watch_summary
from .workflow import REQUIRED_IMPLEMENTER_REVIEWS, workflow_path


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


def _path_from_meta(summary: dict[str, Any], key: str) -> Path | None:
    artifacts = summary.get("artifacts") if isinstance(summary.get("artifacts"), dict) else {}
    meta = artifacts.get(key) if isinstance(artifacts.get(key), dict) else {}
    path = meta.get("path")
    return Path(str(path)).resolve() if path else None


def _load_json_path(path: Path | None) -> dict[str, Any]:
    if path and path.exists():
        try:
            data = load_json(path)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}
    return {}


def _missing_workflow_gates(workflow: dict[str, Any], task_id: str, role: str) -> list[str]:
    if not workflow:
        return ["workflow_artifact"]
    final_acceptance = workflow.get("finalAcceptance") if isinstance(workflow.get("finalAcceptance"), dict) else {}
    missing: list[str] = []
    task = (workflow.get("tasks") or {}).get(task_id) if isinstance(workflow.get("tasks"), dict) else None
    if role == "implementer":
        reviews = task.get("reviews") if isinstance(task, dict) and isinstance(task.get("reviews"), dict) else {}
        missing.extend(f"{kind}_review" for kind in REQUIRED_IMPLEMENTER_REVIEWS if not isinstance(reviews.get(kind), dict))
    if final_acceptance.get("status") != "accepted":
        missing.append("workflow_final_acceptance")
    return missing


def _tests_observed(report_text: str, declared_tests: list[str]) -> bool:
    verification = report_section(report_text, "Verification")
    if not declared_tests:
        return False
    lowered = verification.lower()
    return all(test.lower() in lowered for test in declared_tests)


def _changed_files_in_scope(report_text: str, scope: list[str]) -> bool:
    changed = report_section(report_text, "Changed Files")
    if not changed.strip():
        return False
    lowered = changed.lower()
    if "none" in lowered:
        return True
    if not scope:
        return False
    return all(any(item.strip() and item.strip() in line for item in scope) for line in changed.splitlines() if line.strip() and not line.strip().startswith("- none"))


def build_audit_package(ns: argparse.Namespace) -> dict[str, Any]:
    summary = build_run_supervisor_summary(ns.run_id, ns.artifact_root, ns.stale_after_seconds, verify=not ns.no_verify)
    artifact_root = Path(str((summary.get("artifacts") or {}).get("root") or resolve_artifact_root(ns.artifact_root, run_id=ns.run_id))).resolve()
    config_path = _path_from_meta(summary, "config")
    status_path = _path_from_meta(summary, "status")
    output_path = _path_from_meta(summary, "output")
    config = _load_json_path(config_path)
    status = _load_json_path(status_path)
    report_text = read_text(output_path) if output_path and output_path.exists() else ""
    workflow_id = str(summary.get("workflowId") or config.get("workflowId") or status.get("workflowId") or "")
    task_id = str(summary.get("taskId") or config.get("taskId") or status.get("taskId") or "")
    role = str(summary.get("role") or config.get("role") or status.get("role") or "")
    workflow_file = workflow_path(artifact_root, workflow_id) if workflow_id else artifact_root / "workflow_missing.json"
    workflow = _load_json_path(workflow_file)
    report = summary.get("report") if isinstance(summary.get("report"), dict) else {}
    verifier = summary.get("deterministicVerifierResult") if isinstance(summary.get("deterministicVerifierResult"), dict) else {}
    declared_tests = config.get("tests") if isinstance(config.get("tests"), list) else []
    scope = config.get("scope") if isinstance(config.get("scope"), list) else []
    missing_gates = _missing_workflow_gates(workflow, task_id, role)
    worker_claim = str(report.get("status") or "")
    failure_layer = str(status.get("failureLayer") or config.get("failureLayer") or "")
    execution_layer_failure = bool(failure_layer) or str(status.get("failureDisposition") or "") == "NEED_HUMAN_INTERVENTION"
    worker_outcome = str(status.get("workerOutcome") or config.get("workerOutcome") or "")
    business_acceptance = str(status.get("businessAcceptance") or config.get("businessAcceptance") or "")
    business_files_changed = bool(status.get("businessFilesChanged") or config.get("businessFilesChanged"))
    safe_to_retry_same_task_file = bool(status.get("safeToRetrySameTaskFile") or config.get("safeToRetrySameTaskFile"))
    may_override_implementation = bool(status.get("mayOverrideImplementation") or config.get("mayOverrideImplementation"))
    verifier_passed = verifier.get("status") == "passed"
    report_valid = bool(report.get("exists")) and bool(worker_claim)
    can_enter_review = report_valid and verifier_passed and worker_claim == "DONE" and not execution_layer_failure
    acceptance_allowed = can_enter_review and not missing_gates and (workflow.get("finalAcceptance") or {}).get("status") == "accepted"
    main_action = "accept_or_commit" if acceptance_allowed else "dispatch_missing_review_gates" if can_enter_review and missing_gates else "run_runtime_diagnostics" if execution_layer_failure else "rerun_or_forensics" if not verifier_passed else "review_worker_report"
    audit = {
        "artifactSchema": ARTIFACT_SCHEMA_VERSION,
        "invocationContract": INVOCATION_CONTRACT,
        "command": "ccstatus audit",
        "auditType": "codex-with-cc-run-audit",
        "runId": ns.run_id,
        "workflowId": workflow_id,
        "taskId": task_id,
        "role": role,
        "observedState": summary.get("state"),
        "runStatus": summary.get("runStatus"),
        "workerClaim": worker_claim,
        "workerOutcome": worker_outcome,
        "businessAcceptance": business_acceptance,
        "businessFilesChanged": business_files_changed,
        "safeToRetrySameTaskFile": safe_to_retry_same_task_file,
        "mayOverrideImplementation": may_override_implementation,
        "reportValid": report_valid,
        "changedFilesInScope": _changed_files_in_scope(report_text, scope),
        "testsDeclared": bool(declared_tests),
        "declaredTests": declared_tests,
        "testsObserved": _tests_observed(report_text, declared_tests),
        "verifierPassed": verifier_passed,
        "deterministicVerifierResult": verifier,
        "missingGates": missing_gates,
        "canEnterReview": can_enter_review,
        "acceptanceAllowed": acceptance_allowed,
        "failureLayer": failure_layer,
        "executionLayerFailure": execution_layer_failure,
        "businessFailure": worker_claim in {"FAIL", "BLOCKED", "NEEDS_CONTEXT", "DONE_WITH_CONCERNS"} and not execution_layer_failure,
        "mainThreadAction": main_action,
        "nextCommand": "ccstatus claude --json" if execution_layer_failure else f"verify_delegate_workflow -WorkflowId {workflow_id} -ArtifactRoot {artifact_root}",
        "confidence": "high" if report_valid and verifier.get("status") in {"passed", "failed"} else "medium",
        "evidencePaths": {
            "config": str(config_path or ""),
            "status": str(status_path or ""),
            "report": str(output_path or ""),
            "workflow": str(workflow_file),
            "trace": str(_path_from_meta(summary, "trace") or ""),
            "stream": str(_path_from_meta(summary, "stream") or ""),
        },
        "provenance": {
            "sources": ["config", "status", "report", "workflow", "supervisor"],
            "generatedReasoning": ["mainThreadAction", "missingGates", "canEnterReview", "acceptanceAllowed"],
        },
        "mayOverrideValidator": False,
        "mayOverrideVerifier": False,
        "updatedAt": now_iso(),
    }
    return audit


def write_audit_artifacts(audit: dict[str, Any], artifact_root_value: str | None = None) -> tuple[Path, Path]:
    root = resolve_artifact_root(artifact_root_value, run_id=str(audit["runId"]))
    run_id = str(audit["runId"])
    json_path = root / f"audit_{run_id}.json"
    md_path = root / f"audit_{run_id}.md"
    audit["auditPath"] = str(json_path)
    audit["auditMarkdownPath"] = str(md_path)
    write_json(json_path, audit)
    write_text(
        md_path,
        "\n".join(
            [
                "# Codex With CC Run Audit",
                "",
                f"RunId: {run_id}",
                f"WorkflowId: {audit.get('workflowId')}",
                f"ObservedState: {audit.get('observedState')}",
                f"WorkerClaim: {audit.get('workerClaim')}",
                f"WorkerOutcome: {audit.get('workerOutcome') or '-'}",
                f"BusinessAcceptance: {audit.get('businessAcceptance') or '-'}",
                f"BusinessFilesChanged: {str(audit.get('businessFilesChanged')).lower()}",
                f"SafeToRetrySameTaskFile: {str(audit.get('safeToRetrySameTaskFile')).lower()}",
                f"CanEnterReview: {str(audit.get('canEnterReview')).lower()}",
                f"AcceptanceAllowed: {str(audit.get('acceptanceAllowed')).lower()}",
                f"FailureLayer: {audit.get('failureLayer') or '-'}",
                f"MainThreadAction: {audit.get('mainThreadAction')}",
                f"mayOverrideVerifier: {str(audit.get('mayOverrideVerifier')).lower()}",
                "",
                "## Missing Gates",
                "",
                "\n".join(f"- {item}" for item in audit.get("missingGates") or []) or "- none",
                "",
                "## Evidence Paths",
                "",
                "\n".join(f"- {key}: {value}" for key, value in (audit.get("evidencePaths") or {}).items()),
                "",
            ]
        )
        + "\n",
    )
    return json_path, md_path


def build_workflow_audit_package(ns: argparse.Namespace) -> dict[str, Any]:
    summary = build_workflow_watch_summary(ns.workflow_id, ns.artifact_root)
    artifact_root = Path(str(summary.get("artifactRoot") or resolve_artifact_root(ns.artifact_root, workflow_id=ns.workflow_id))).resolve()
    workflow_file = workflow_path(artifact_root, ns.workflow_id)
    workflow = _load_json_path(workflow_file)
    run_audits: list[dict[str, Any]] = []
    for run in summary.get("runs") or []:
        run_id = str(run.get("runId") or "")
        if not run_id:
            continue
        try:
            run_audits.append(
                build_audit_package(
                    SimpleNamespace(
                        run_id=run_id,
                        artifact_root=str(artifact_root),
                        stale_after_seconds=ns.stale_after_seconds,
                        no_verify=ns.no_verify,
                    )
                )
            )
        except DelegateError as exc:
            run_audits.append(
                {
                    "artifactSchema": ARTIFACT_SCHEMA_VERSION,
                    "invocationContract": INVOCATION_CONTRACT,
                    "auditType": "codex-with-cc-run-audit",
                    "runId": run_id,
                    "workflowId": ns.workflow_id,
                    "reportValid": False,
                    "verifierPassed": False,
                    "canEnterReview": False,
                    "acceptanceAllowed": False,
                    "failureLayer": "audit_generation_failed",
                    "executionLayerFailure": True,
                    "mainThreadAction": "inspect_missing_or_invalid_run_artifacts",
                    "error": str(exc),
                    "mayOverrideVerifier": False,
                }
            )
    final_acceptance = workflow.get("finalAcceptance") if isinstance(workflow.get("finalAcceptance"), dict) else {}
    failed_runs = [item.get("runId") for item in run_audits if item.get("executionLayerFailure") or item.get("businessFailure") or not item.get("reportValid")]
    missing_gates = sorted({gate for item in run_audits for gate in item.get("missingGates") or []})
    state_counts = summary.get("stateCounts") if isinstance(summary.get("stateCounts"), dict) else {}
    running_states = {key: value for key, value in state_counts.items() if key in {"STARTING", "RUNNING_ACTIVE", "RUNNING_QUIET", "STALE", "RUNNING_DEAD_PROCESS"} and int(value) > 0}
    acceptance_allowed = final_acceptance.get("status") == "accepted" and not failed_runs and not running_states
    if acceptance_allowed:
        main_action = "accept_or_commit"
    elif running_states:
        main_action = "wait_or_resolve_running_runs"
    elif failed_runs:
        main_action = "inspect_failed_runs_or_trigger_forensics"
    elif missing_gates:
        main_action = "dispatch_missing_review_gates"
    else:
        main_action = "run_workflow_verifier"
    return {
        "artifactSchema": ARTIFACT_SCHEMA_VERSION,
        "invocationContract": INVOCATION_CONTRACT,
        "command": "ccstatus audit",
        "auditType": "codex-with-cc-workflow-audit",
        "workflowId": ns.workflow_id,
        "artifactRoot": str(artifact_root),
        "runCount": len(run_audits),
        "runAudits": run_audits,
        "stateCounts": state_counts,
        "failedRuns": failed_runs,
        "runningStates": running_states,
        "missingGates": missing_gates,
        "workflowFinalAcceptance": final_acceptance,
        "acceptanceAllowed": acceptance_allowed,
        "mainThreadAction": main_action,
        "nextCommand": f"verify_delegate_workflow -WorkflowId {ns.workflow_id} -ArtifactRoot {artifact_root}",
        "confidence": "high" if run_audits else "medium",
        "evidencePaths": {
            "workflow": str(workflow_file),
            "artifactRoot": str(artifact_root),
        },
        "provenance": {
            "sources": ["workflow", "run_audits", "supervisor"],
            "generatedReasoning": ["failedRuns", "missingGates", "acceptanceAllowed", "mainThreadAction"],
        },
        "mayOverrideValidator": False,
        "mayOverrideVerifier": False,
        "updatedAt": now_iso(),
    }


def write_workflow_audit_artifacts(audit: dict[str, Any], artifact_root_value: str | None = None) -> tuple[Path, Path]:
    root = resolve_artifact_root(artifact_root_value, workflow_id=str(audit["workflowId"]))
    workflow_id = str(audit["workflowId"])
    json_path = root / f"audit_{workflow_id}.json"
    md_path = root / f"audit_{workflow_id}.md"
    audit["auditPath"] = str(json_path)
    audit["auditMarkdownPath"] = str(md_path)
    write_json(json_path, audit)
    write_text(
        md_path,
        "\n".join(
            [
                "# Codex With CC Workflow Audit",
                "",
                f"WorkflowId: {workflow_id}",
                f"RunCount: {audit.get('runCount')}",
                f"AcceptanceAllowed: {str(audit.get('acceptanceAllowed')).lower()}",
                f"MainThreadAction: {audit.get('mainThreadAction')}",
                f"mayOverrideVerifier: {str(audit.get('mayOverrideVerifier')).lower()}",
                "",
                "## Failed Runs",
                "",
                "\n".join(f"- {item}" for item in audit.get("failedRuns") or []) or "- none",
                "",
                "## Missing Gates",
                "",
                "\n".join(f"- {item}" for item in audit.get("missingGates") or []) or "- none",
                "",
                "## Evidence Paths",
                "",
                "\n".join(f"- {key}: {value}" for key, value in (audit.get("evidencePaths") or {}).items()),
                "",
            ]
        )
        + "\n",
    )
    return json_path, md_path


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
    elif command == "audit":
        if getattr(ns, "workflow_id", None):
            report = build_workflow_audit_package(ns)
            write_workflow_audit_artifacts(report, ns.artifact_root)
        else:
            report = build_audit_package(ns)
            write_audit_artifacts(report, ns.artifact_root)
    elif command == "workflow":
        report = build_workflow_status(ns)
    else:
        raise DelegateError(f"Unknown ccstatus command: {command}")
    if getattr(ns, "json", False):
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_status_text(report))
    return 0 if report.get("overall") not in {"blocked"} else 1
