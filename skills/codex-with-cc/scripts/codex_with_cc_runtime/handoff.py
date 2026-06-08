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
    return {
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
    return {
        "artifactSchema": ARTIFACT_SCHEMA_VERSION,
        "invocationContract": INVOCATION_CONTRACT,
        "handoffType": "run",
        "delegateStatus": "WAITING",
        "observedState": state,
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


def terminal_handoff(run_summary: dict[str, Any], *, artifact_root: str) -> dict[str, Any]:
    state = str(run_summary.get("state") or "UNKNOWN")
    run_id = str(run_summary.get("runId") or "")
    verifier = run_summary.get("deterministicVerifierResult") if isinstance(run_summary.get("deterministicVerifierResult"), dict) else {}
    report = run_summary.get("report") if isinstance(run_summary.get("report"), dict) else {}
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
    else:
        delegate_status = "FAILED"
        action = "inspect_failure_or_run_runtime_diagnostics"
        acceptance_allowed = False
        next_command = "ccstatus claude --json"
    return {
        "artifactSchema": ARTIFACT_SCHEMA_VERSION,
        "invocationContract": INVOCATION_CONTRACT,
        "handoffType": "run",
        "delegateStatus": delegate_status,
        "observedState": state,
        "workerClaim": report.get("status") or "",
        "reportValid": bool(report.get("exists")),
        "verifierPassed": verifier.get("status") == "passed",
        "acceptanceAllowed": acceptance_allowed,
        "mainThreadAction": action,
        "recommendedWaitSeconds": 0,
        "nextCommand": next_command,
        "confidence": "high" if state in {"RUN_VERIFIED", "REPORT_READY", "RUNNING_DEAD_PROCESS", "FAILED"} else "medium",
        "evidencePaths": _evidence_paths(run_summary),
        "mayOverrideValidator": False,
        "mayOverrideVerifier": False,
        "updatedAt": now_iso(),
    }


def _evidence_paths(run_summary: dict[str, Any]) -> dict[str, str]:
    artifacts = run_summary.get("artifacts") if isinstance(run_summary.get("artifacts"), dict) else {}
    return {
        key: str(meta.get("path"))
        for key, meta in artifacts.items()
        if isinstance(meta, dict) and meta.get("path")
    }
