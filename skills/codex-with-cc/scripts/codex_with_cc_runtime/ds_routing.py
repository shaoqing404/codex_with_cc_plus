from __future__ import annotations

from typing import Any

from .common import ARTIFACT_SCHEMA_VERSION, INVOCATION_CONTRACT, now_iso


DS_ADVISORY_CAPABILITIES = {
    "advisoryOnly": True,
    "mayOverrideValidator": False,
    "mayOverrideVerifier": False,
    "canEditBusinessFiles": False,
    "canRunShellTests": False,
    "canDispatchWorkerRuns": False,
    "canAcceptWorkflowResults": False,
}


def _base_plan(
    *,
    recommendation: str,
    trigger: str,
    role: str,
    model: str,
    reason: str,
    evidence_paths: dict[str, str] | None = None,
    confidence: str = "high",
) -> dict[str, Any]:
    should_route = recommendation == "recommended"
    return {
        "artifactSchema": ARTIFACT_SCHEMA_VERSION,
        "invocationContract": INVOCATION_CONTRACT,
        "routeType": "ds-advisory-routing-plan",
        "recommendation": recommendation,
        "shouldRoute": should_route,
        "automaticDispatch": False,
        "trigger": trigger,
        "role": role,
        "runnerType": "openai_compatible_report" if role else "",
        "model": model,
        "reason": reason,
        "nextCommandTemplate": _command_template(role) if role else "",
        "taskFileGuidance": _task_file_guidance(trigger),
        "evidencePaths": evidence_paths or {},
        "confidence": confidence,
        "provenance": {
            "sources": ["ccstatus audit", "deterministic verifier", "workflow artifacts"],
            "generatedReasoning": ["recommendation", "trigger", "reason", "taskFileGuidance"],
        },
        **DS_ADVISORY_CAPABILITIES,
        "updatedAt": now_iso(),
    }


def _command_template(role: str) -> str:
    if not role:
        return ""
    return (
        "delegate_to_openai_compatible_report -TaskFile <ds-report-task-file> "
        "-WorkflowId <workflow-id> -TaskId <ds-task-id> -Role researcher "
        "-SessionKey <workflow-id>-ds-report"
    )


def _task_file_guidance(trigger: str) -> str:
    if trigger == "execution_layer_failure":
        return "Create a report-only forensic TaskFile summarizing failureLayer, status/trace/stream paths, retry safety, and human recovery steps."
    if trigger == "deterministic_verifier_failed":
        return "Create a report-only forensic TaskFile summarizing verifier failure evidence and likely rework paths without changing verifier outcome."
    if trigger == "missing_or_invalid_report":
        return "Create a report-only normalization TaskFile asking DS to explain missing report evidence and next diagnostic steps."
    if trigger == "business_failure":
        return "Create a report-only forensic TaskFile summarizing worker claim, blocked business acceptance, and recommended main-thread decision points."
    if trigger == "workflow_failed_runs":
        return "Create a workflow-level report-only forensic TaskFile listing failed runs, evidence paths, and safe next actions."
    if trigger == "workflow_summary":
        return "Create a report-only workflow summary TaskFile if the human needs a compact narrative; deterministic verifiers still decide acceptance."
    return "No DS TaskFile is recommended; follow deterministic nextCommand first."


def run_audit_ds_routing(audit: dict[str, Any]) -> dict[str, Any]:
    evidence_paths = audit.get("evidencePaths") if isinstance(audit.get("evidencePaths"), dict) else {}
    worker_claim = str(audit.get("workerClaim") or "")
    if audit.get("acceptanceAllowed"):
        return _base_plan(
            recommendation="not_recommended",
            trigger="acceptance_allowed",
            role="",
            model="",
            reason="Workflow evidence is already accepted; DS cannot add acceptance authority.",
            evidence_paths=evidence_paths,
        )
    if audit.get("executionLayerFailure"):
        return _base_plan(
            recommendation="recommended",
            trigger="execution_layer_failure",
            role="forensic-analyst",
            model="deepseek-v4-pro",
            reason="Execution-layer failure needs a concise forensic explanation, retry safety, and human recovery steps.",
            evidence_paths=evidence_paths,
        )
    if not audit.get("reportValid"):
        return _base_plan(
            recommendation="recommended",
            trigger="missing_or_invalid_report",
            role="forensic-analyst",
            model="deepseek-v4-pro",
            reason="Worker report is missing or invalid, so DS may help summarize evidence without accepting the run.",
            evidence_paths=evidence_paths,
        )
    if audit.get("verifierPassed") is False:
        return _base_plan(
            recommendation="recommended",
            trigger="deterministic_verifier_failed",
            role="forensic-analyst",
            model="deepseek-v4-pro",
            reason="Deterministic verification failed; DS may explain failure evidence but cannot override the verifier.",
            evidence_paths=evidence_paths,
        )
    if audit.get("businessFailure") or worker_claim in {"FAIL", "BLOCKED", "NEEDS_CONTEXT", "DONE_WITH_CONCERNS"}:
        return _base_plan(
            recommendation="recommended",
            trigger="business_failure",
            role="forensic-analyst",
            model="deepseek-v4-pro",
            reason="Worker reported a business-level concern; DS may summarize risks and decision options for the main thread.",
            evidence_paths=evidence_paths,
        )
    if audit.get("canEnterReview") and audit.get("missingGates"):
        return _base_plan(
            recommendation="not_recommended",
            trigger="missing_review_gates",
            role="",
            model="",
            reason="The next action is deterministic review-gate dispatch, not DS analysis.",
            evidence_paths=evidence_paths,
        )
    return _base_plan(
        recommendation="optional",
        trigger="audit_summary",
        role="report-worker",
        model="deepseek-v4-flash",
        reason="DS may produce a compact report-only summary if the human asks, but no automatic route is needed.",
        evidence_paths=evidence_paths,
        confidence="medium",
    )


def workflow_audit_ds_routing(audit: dict[str, Any]) -> dict[str, Any]:
    evidence_paths = audit.get("evidencePaths") if isinstance(audit.get("evidencePaths"), dict) else {}
    if audit.get("acceptanceAllowed"):
        return _base_plan(
            recommendation="not_recommended",
            trigger="acceptance_allowed",
            role="",
            model="",
            reason="Workflow is already accepted; DS cannot add acceptance authority.",
            evidence_paths=evidence_paths,
        )
    if audit.get("runningStates"):
        return _base_plan(
            recommendation="not_recommended",
            trigger="workflow_running",
            role="",
            model="",
            reason="Runs are still active or stale; resolve run state before asking DS for a report.",
            evidence_paths=evidence_paths,
        )
    if audit.get("failedRuns"):
        return _base_plan(
            recommendation="recommended",
            trigger="workflow_failed_runs",
            role="forensic-analyst",
            model="deepseek-v4-pro",
            reason="Workflow contains failed or invalid runs; DS may produce a forensic summary for the main thread.",
            evidence_paths=evidence_paths,
        )
    if audit.get("missingGates"):
        return _base_plan(
            recommendation="not_recommended",
            trigger="missing_review_gates",
            role="",
            model="",
            reason="The next action is deterministic review/final-verifier gate dispatch, not DS analysis.",
            evidence_paths=evidence_paths,
        )
    return _base_plan(
        recommendation="optional",
        trigger="workflow_summary",
        role="report-worker",
        model="deepseek-v4-flash",
        reason="DS may summarize workflow evidence for a human, but deterministic workflow verification remains authoritative.",
        evidence_paths=evidence_paths,
        confidence="medium",
    )
