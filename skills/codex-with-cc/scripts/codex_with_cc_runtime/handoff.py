from __future__ import annotations

from typing import Any

from .common import ARTIFACT_SCHEMA_VERSION, INVOCATION_CONTRACT, now_iso


WAIT_POLICY_DEFAULTS = {
    "startingSeconds": 60,
    "runningActiveSeconds": 60,
    "runningQuietSeconds": 300,
}


def refusal_handoff(
    *,
    failure_layer: str,
    user_message: str,
    next_command: str,
    evidence_paths: dict[str, str] | None = None,
    confidence: str = "high",
) -> dict[str, Any]:
    result = {
        "artifactSchema": ARTIFACT_SCHEMA_VERSION,
        "invocationContract": INVOCATION_CONTRACT,
        "handoffType": "preflight",
        "delegateStatus": "REFUSED",
        "dispatchAllowed": False,
        "acceptanceAllowed": False,
        "failureLayer": failure_layer,
        "humanInterventionRequired": True,
        "mainThreadAction": "install_or_repair_claude_code",
        "childThreadAction": "do_not_call_delegate_to_claude",
        "userMessage": user_message,
        "nextCommand": next_command,
        "confidence": confidence,
        "evidencePaths": evidence_paths or {},
        "mayOverrideValidator": False,
        "mayOverrideVerifier": False,
        "updatedAt": now_iso(),
    }
    result["childThreadResponseTemplate"] = child_thread_response_template(result)
    return result


def wait_handoff(run_summary: dict[str, Any], *, artifact_root: str, stale_after_seconds: int) -> dict[str, Any]:
    state = str(run_summary.get("state") or "UNKNOWN")
    run_id = str(run_summary.get("runId") or "")
    if state == "STARTING":
        wait_seconds = WAIT_POLICY_DEFAULTS["startingSeconds"]
    elif state == "RUNNING_ACTIVE":
        wait_seconds = WAIT_POLICY_DEFAULTS["runningActiveSeconds"]
    else:
        wait_seconds = WAIT_POLICY_DEFAULTS["runningQuietSeconds"]
    next_command = (
        f"ccsupervise -RunId {run_id} -ArtifactRoot {artifact_root} "
        f"-Wait -TimeoutSeconds {wait_seconds} -StaleAfterSeconds {stale_after_seconds} --json"
    )
    result = {
        "artifactSchema": ARTIFACT_SCHEMA_VERSION,
        "invocationContract": INVOCATION_CONTRACT,
        "handoffType": "run",
        "delegateStatus": "WAITING",
        "observedState": state,
        "artifactRoot": artifact_root,
        "acceptanceAllowed": False,
        "mainThreadAction": "wait_with_supervisor",
        "recommendedWaitSeconds": wait_seconds,
        "nextCommand": next_command,
        "confidence": "high",
        "reason": "worker process appears active or not yet stale; bounded supervisor wait is recommended",
        "thresholds": {**WAIT_POLICY_DEFAULTS, "staleAfterSeconds": stale_after_seconds},
        "evidencePaths": _evidence_paths(run_summary),
        "mayOverrideValidator": False,
        "mayOverrideVerifier": False,
        "updatedAt": now_iso(),
    }
    result["childThreadResponseTemplate"] = child_thread_response_template(result, run_summary)
    return result


def terminal_handoff(run_summary: dict[str, Any], *, artifact_root: str) -> dict[str, Any]:
    state = str(run_summary.get("state") or "UNKNOWN")
    run_id = str(run_summary.get("runId") or "")
    verifier = run_summary.get("deterministicVerifierResult") if isinstance(run_summary.get("deterministicVerifierResult"), dict) else {}
    report = run_summary.get("report") if isinstance(run_summary.get("report"), dict) else {}
    failure_layer = str(run_summary.get("failureLayer") or "")
    execution_layer_failure = bool(run_summary.get("executionLayerFailure"))
    if state == "RUN_VERIFIED":
        delegate_status = "REPORT_READY"
        action = "review_worker_report_and_workflow_gates"
        acceptance_allowed = False
        next_command = f"verify_delegate_workflow -WorkflowId {run_summary.get('workflowId')} -ArtifactRoot {artifact_root}"
    elif state == "REPORT_READY":
        delegate_status = "REPORT_READY"
        action = "run_deterministic_verifier"
        acceptance_allowed = False
        next_command = f"verify_delegate_run -RunId {run_id} -ArtifactRoot {artifact_root}"
    elif state == "RUNNING_DEAD_PROCESS":
        delegate_status = "FAILED"
        action = "rerun_or_trigger_failure_forensics"
        acceptance_allowed = False
        next_command = f"ccstatus run -RunId {run_id} -ArtifactRoot {artifact_root} --json"
    elif execution_layer_failure:
        delegate_status = "FAILED"
        action = "run_runtime_diagnostics"
        acceptance_allowed = False
        next_command = "ccstatus claude --json"
    else:
        delegate_status = "FAILED"
        action = "inspect_failure_or_run_runtime_diagnostics"
        acceptance_allowed = False
        next_command = "ccstatus claude --json"
    result = {
        "artifactSchema": ARTIFACT_SCHEMA_VERSION,
        "invocationContract": INVOCATION_CONTRACT,
        "handoffType": "run",
        "delegateStatus": delegate_status,
        "observedState": state,
        "artifactRoot": artifact_root,
        "workerClaim": report.get("status") or "",
        "reportValid": bool(report.get("exists")),
        "verifierPassed": verifier.get("status") == "passed",
        "acceptanceAllowed": acceptance_allowed,
        "failureLayer": failure_layer,
        "failureSummary": str(run_summary.get("failureSummary") or ""),
        "workerOutcome": str(run_summary.get("workerOutcome") or ""),
        "businessAcceptance": str(run_summary.get("businessAcceptance") or ""),
        "executionLayerFailure": execution_layer_failure,
        "businessFilesChanged": bool(run_summary.get("businessFilesChanged")),
        "safeToRetrySameTaskFile": bool(run_summary.get("safeToRetrySameTaskFile")),
        "mayOverrideImplementation": bool(run_summary.get("mayOverrideImplementation")),
        "humanInterventionRequired": bool(execution_layer_failure or state in {"FAILED", "RUNNING_DEAD_PROCESS", "STALE"}),
        "mainThreadAction": action,
        "recommendedWaitSeconds": 0,
        "nextCommand": next_command,
        "confidence": "high" if state in {"RUN_VERIFIED", "REPORT_READY", "RUNNING_DEAD_PROCESS", "FAILED"} else "medium",
        "evidencePaths": _evidence_paths(run_summary),
        "mayOverrideValidator": False,
        "mayOverrideVerifier": False,
        "updatedAt": now_iso(),
    }
    result["childThreadResponseTemplate"] = child_thread_response_template(result, run_summary)
    return result


def child_thread_response_template(handoff: dict[str, Any], run_summary: dict[str, Any] | None = None) -> str:
    summary = run_summary or {}
    evidence = handoff.get("evidencePaths") if isinstance(handoff.get("evidencePaths"), dict) else {}
    run_id = str(summary.get("runId") or "")
    workflow_id = str(summary.get("workflowId") or "")
    task_id = str(summary.get("taskId") or "")
    status_path = str(evidence.get("status") or "")
    report_path = str(evidence.get("output") or evidence.get("report") or "")
    trace_path = str(evidence.get("trace") or "")
    stream_path = str(evidence.get("stream") or "")
    lines = [
        f"DelegateStatus: {handoff.get('delegateStatus') or ''}",
        f"RunId: {run_id}",
        f"WorkflowId: {workflow_id}",
        f"TaskId: {task_id}",
        f"ArtifactRoot: {handoff.get('artifactRoot') or evidence.get('root') or ''}",
        f"HandoffPath: {handoff.get('handoffPath') or ''}",
        f"HandoffMarkdownPath: {handoff.get('handoffMarkdownPath') or ''}",
        f"StatusPath: {status_path}",
        f"ReportPath: {report_path}",
        f"TracePath: {trace_path}",
        f"RawStreamPath: {stream_path}",
        f"ObservedState: {handoff.get('observedState') or ''}",
        f"Verifier: {'passed' if handoff.get('verifierPassed') else 'not-run-or-failed'}",
        "Supervisor: passed",
        f"MainThreadAction: {handoff.get('mainThreadAction') or ''}",
        f"AcceptanceAllowed: {str(bool(handoff.get('acceptanceAllowed'))).lower()}",
        f"RecommendedWaitSeconds: {handoff.get('recommendedWaitSeconds') if handoff.get('recommendedWaitSeconds') is not None else 0}",
        f"NextCommand: {handoff.get('nextCommand') or ''}",
        f"Confidence: {handoff.get('confidence') or 'medium'}",
    ]
    if handoff.get("delegateStatus") == "WAITING":
        lines.append("Note: no worker report is acceptable yet; return this waiting handoff instead of claiming completion.")
    elif handoff.get("delegateStatus") == "REFUSED":
        lines.append("Note: no worker implementation was attempted; report this framework precondition failure to the main thread.")
    elif handoff.get("acceptanceAllowed") is False:
        lines.append("Note: acceptanceAllowed=false; do not present delegated work as accepted.")
    return "\n".join(lines)


def _evidence_paths(run_summary: dict[str, Any]) -> dict[str, str]:
    artifacts = run_summary.get("artifacts") if isinstance(run_summary.get("artifacts"), dict) else {}
    return {
        key: str(meta.get("path"))
        for key, meta in artifacts.items()
        if isinstance(meta, dict) and meta.get("path")
    }
