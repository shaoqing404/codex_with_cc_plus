from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Iterable

from .common import ARTIFACT_SCHEMA_VERSION, CHILD_MARKER_NAME, INVOCATION_CONTRACT, REPORT_STATUS_VALUES, WORKER_ROLES, DelegateError, boolish, now_iso, same_path
from .io_utils import load_json, write_json, write_text
from .locks import pid_alive
from .paths import project_artifact_root, user_artifact_root
from .reports import parse_report_final_result, parse_report_role, parse_report_status, path_has_required_report_headings, report_section
from .workflow import REQUIRED_IMPLEMENTER_REVIEWS, workflow_path



def resolve_artifact_root(artifact_root_value: str | None, run_id: str | None = None, workflow_id: str | None = None) -> Path:
    if artifact_root_value:
        return Path(artifact_root_value).resolve()
    candidates = [project_artifact_root(), user_artifact_root()]
    if run_id:
        for root in candidates:
            if (root / f"config_{run_id}.json").exists():
                return root
    if workflow_id:
        for root in candidates:
            if workflow_path(root, workflow_id).exists():
                return root
    return candidates[0]


def recorded_delegate_pid(status: dict[str, Any]) -> int | None:
    pid = status.get("pid")
    if pid in (None, ""):
        attempts = list(status.get("attempts") or [])
        if attempts and isinstance(attempts[-1], dict):
            pid = attempts[-1].get("pid")
    try:
        pid_int = int(pid)
    except (TypeError, ValueError):
        return None
    return pid_int if pid_int > 0 else None


def running_dead_process_message(status: dict[str, Any]) -> str | None:
    if str(status.get("status") or "") != "running":
        return None
    pid = recorded_delegate_pid(status)
    if pid is None or pid_alive(pid):
        return None
    run_id = str(status.get("runId") or "<unknown>")
    output_path = str(status.get("outputPath") or "")
    suffix = f" Output was expected at: {output_path}." if output_path else ""
    return (
        f"Delegate status is still running for RunId {run_id}, but recorded PID {pid} is not alive."
        f"{suffix} Treat this run as interrupted/stale; rerun or trigger failure forensics instead of accepting it."
    )


def verify_artifacts(run_id: str, artifact_root_value: str | None) -> dict[str, Any]:
    root = resolve_artifact_root(artifact_root_value, run_id=run_id)
    config_path = root / f"config_{run_id}.json"
    status_path = root / f"status_{run_id}.json"
    for label, path in (("config", config_path), ("status", status_path)):
        if not path.exists():
            raise DelegateError(f"Missing delegate {label}: {path}")
    config = load_json(config_path)
    status = load_json(status_path)
    output_path = Path(str(config.get("outputPath") or (root / f"claude_{run_id}.md"))).resolve()
    status_value = str(status.get("status"))
    if status_value not in ("starting", "running", "completed", "failed"):
        raise DelegateError(f"Unexpected delegate status value: {status_value}")
    dead_process_message = running_dead_process_message(status)
    if dead_process_message:
        raise DelegateError(dead_process_message)
    if not output_path.exists():
        raise DelegateError(f"Missing delegate output: {output_path}")
    for obj in (config, status):
        if "artifactSchema" not in obj or "invocationContract" not in obj:
            raise DelegateError("Legacy delegate artifact is unsupported; rerun with current spawn_agent-based flow.")
    if int(config["artifactSchema"]) != ARTIFACT_SCHEMA_VERSION or int(status["artifactSchema"]) != ARTIFACT_SCHEMA_VERSION:
        raise DelegateError(f"Unexpected delegate artifact schema. Expected {ARTIFACT_SCHEMA_VERSION}.")
    if config.get("invocationContract") != INVOCATION_CONTRACT or status.get("invocationContract") != INVOCATION_CONTRACT:
        raise DelegateError(f"Unexpected delegate invocation contract. Expected '{INVOCATION_CONTRACT}'.")
    if config.get("childThreadMarkerName") != CHILD_MARKER_NAME or status.get("childThreadMarkerName") != CHILD_MARKER_NAME:
        raise DelegateError(f"Unexpected child-thread marker name. Expected '{CHILD_MARKER_NAME}'.")
    if not boolish(config.get("childThreadMarkerValidated")) or not boolish(status.get("childThreadMarkerValidated")):
        raise DelegateError("Delegate artifact indicates the child-thread marker was not validated.")
    if not same_path(str(config.get("outputPath")), output_path):
        raise DelegateError(f"Config outputPath mismatch. Expected: {output_path} ; Actual: {config.get('outputPath')}")
    if not same_path(str(status.get("outputPath")), output_path):
        raise DelegateError(f"Status outputPath mismatch. Expected: {output_path} ; Actual: {status.get('outputPath')}")
    completed = status_value == "completed"
    structured_failure = status_value == "failed"
    if not completed and not structured_failure:
        raise DelegateError(f"Delegate status is neither completed nor failed: {status_value}")
    if not path_has_required_report_headings(output_path):
        raise DelegateError(f"Delegate output does not contain the required report headings in order: {output_path}")
    report_text = output_path.read_text(encoding="utf-8")
    report_status = parse_report_status(report_text)
    if report_status not in REPORT_STATUS_VALUES:
        raise DelegateError(f"Delegate output has an invalid report status: {report_status}")
    report_final_result = parse_report_final_result(report_text)
    if report_final_result not in REPORT_STATUS_VALUES:
        raise DelegateError(f"Delegate output has an invalid Final Result: {report_final_result}")
    if report_final_result != report_status:
        raise DelegateError(f"Delegate output Status and Final Result mismatch. Status={report_status}; Final Result={report_final_result}.")
    report_role = parse_report_role(report_text)
    if report_role not in WORKER_ROLES:
        raise DelegateError(f"Delegate output has an invalid report role: {report_role}")
    if report_role != str(config.get("role")):
        raise DelegateError(f"Delegate output role mismatch. Config role={config.get('role')}; report role={report_role}.")
    verification_text = report_section(report_text, "Verification").strip()
    if report_status == "DONE" and not report_has_verification_evidence(verification_text):
        raise DelegateError("Delegate output is missing concrete verification evidence.")
    if report_role == "reviewer":
        if not str(config.get("reviewForTaskId") or "").strip():
            raise DelegateError("Reviewer delegate config is missing reviewForTaskId.")
        if str(config.get("reviewKind") or "") not in REQUIRED_IMPLEMENTER_REVIEWS:
            raise DelegateError(f"Reviewer delegate config has invalid reviewKind: {config.get('reviewKind')}")
    for prop in ("workflowId", "taskId", "role"):
        if not str(config.get(prop) or "").strip():
            raise DelegateError(f"Delegate config is missing {prop}.")
        if not str(status.get(prop) or "").strip():
            raise DelegateError(f"Delegate status is missing {prop}.")
        if str(config.get(prop)) != str(status.get(prop)):
            raise DelegateError(f"Delegate config/status {prop} mismatch.")
    if str(config.get("role")) not in WORKER_ROLES:
        raise DelegateError(f"Delegate config has invalid role: {config.get('role')}")
    workflow_id = str(config.get("workflowId"))
    workflow_file = workflow_path(root, workflow_id)
    if not workflow_file.exists():
        raise DelegateError(f"Missing workflow artifact: {workflow_file}")
    workflow = load_json(workflow_file)
    if int(workflow.get("artifactSchema", -1)) != ARTIFACT_SCHEMA_VERSION:
        raise DelegateError(f"Unexpected workflow artifact schema. Expected {ARTIFACT_SCHEMA_VERSION}.")
    if workflow.get("invocationContract") != INVOCATION_CONTRACT:
        raise DelegateError(f"Unexpected workflow invocation contract. Expected '{INVOCATION_CONTRACT}'.")
    if workflow.get("workflowId") != workflow_id:
        raise DelegateError("Workflow artifact workflowId mismatch.")
    if run_id not in (workflow.get("runs") or {}):
        raise DelegateError(f"Workflow artifact does not reference run {run_id}.")
    task_id = str(config.get("taskId"))
    task = (workflow.get("tasks") or {}).get(task_id)
    if not isinstance(task, dict):
        raise DelegateError(f"Workflow artifact does not reference task {task_id}.")
    if run_id not in list(task.get("runs") or []):
        raise DelegateError(f"Workflow task {task_id} does not reference run {run_id}.")
    if completed and status.get("exitCode") is not None and int(status["exitCode"]) != 0:
        raise DelegateError(f"Delegate exitCode is not zero: {status['exitCode']}")
    if structured_failure and status.get("exitCode") is not None and int(status["exitCode"]) == 0:
        raise DelegateError("Structured failed delegate must record a non-zero exitCode.")
    if "attempts" not in status:
        raise DelegateError("Delegate status is missing attempts[] audit data.")
    if "sessionMode" not in config:
        raise DelegateError("Delegate config is missing sessionMode.")
    if "sessionKey" not in config:
        raise DelegateError("Delegate config is missing sessionKey.")
    attempts = list(status.get("attempts") or [])
    status_attempt_count = int(status.get("attemptCount", len(attempts)))
    status_retry_count = int(status.get("retryCount", 0))
    config_attempt_count = int(config.get("attemptCount", status_attempt_count))
    config_retry_count = int(config.get("retryCount", status_retry_count))
    if len(attempts) != status_attempt_count:
        raise DelegateError(f"Delegate attempts[] count mismatch. attempts={len(attempts)} status.attemptCount={status_attempt_count}")
    if status_attempt_count < 1:
        raise DelegateError("Delegate status must record at least one attempt.")
    if config_attempt_count != status_attempt_count:
        raise DelegateError(f"Config/status attemptCount mismatch. config={config_attempt_count} status={status_attempt_count}")
    if config_retry_count != status_retry_count:
        raise DelegateError(f"Config/status retryCount mismatch. config={config_retry_count} status={status_retry_count}")
    if structured_failure:
        for prop in ("failureDisposition", "failureSummary", "maxRetryCount"):
            if prop not in status:
                raise DelegateError(f"Structured failed delegate status is missing '{prop}'.")
            if prop not in config:
                raise DelegateError(f"Structured failed delegate config is missing '{prop}'.")
        if status.get("failureDisposition") != "NEED_HUMAN_INTERVENTION":
            raise DelegateError(f"Structured failed delegate must set failureDisposition to 'NEED_HUMAN_INTERVENTION'. Actual: {status.get('failureDisposition')}")
        if config.get("failureDisposition") != status.get("failureDisposition"):
            raise DelegateError("Structured failed delegate failureDisposition must match between config and status.")
        if not str(status.get("failureSummary", "")).strip():
            raise DelegateError("Structured failed delegate must record a non-empty failureSummary.")
        if config.get("failureSummary") != status.get("failureSummary"):
            raise DelegateError("Structured failed delegate failureSummary must match between config and status.")
        if int(config.get("maxRetryCount")) != int(status.get("maxRetryCount")):
            raise DelegateError("Structured failed delegate maxRetryCount must match between config and status.")
    recorded_retry_reasons = 0
    for index, attempt in enumerate(attempts):
        for prop in ("attempt", "sessionId", "resume", "retryReason", "exitCode", "sawAssistantText", "sawResultSuccess", "capturedFinalResult"):
            if prop not in attempt:
                raise DelegateError(f"Delegate attempt[{index}] is missing '{prop}'.")
        if int(attempt["attempt"]) != index + 1:
            raise DelegateError(f"Delegate attempt numbering is not sequential at index {index}. Expected {index + 1} but found {attempt['attempt']}.")
        if str(attempt.get("retryReason") or "").strip():
            recorded_retry_reasons += 1
    if recorded_retry_reasons != status_retry_count:
        raise DelegateError(f"Delegate retry count mismatch. attempts-with-retryReason={recorded_retry_reasons} status.retryCount={status_retry_count}")
    first_attempt = attempts[0]
    final_attempt = attempts[-1]
    if "initialSessionId" not in config:
        raise DelegateError("Delegate config is missing initialSessionId.")
    if "initialResume" not in config:
        raise DelegateError("Delegate config is missing initialResume.")
    if str(config.get("initialSessionId")) != str(first_attempt.get("sessionId")):
        raise DelegateError(f"Config initialSessionId mismatch. Expected first attempt session {first_attempt.get('sessionId')} but found {config.get('initialSessionId')}")
    if boolish(config.get("initialResume")) != boolish(first_attempt.get("resume")):
        raise DelegateError(f"Config initialResume mismatch. Expected first attempt resume {boolish(first_attempt.get('resume'))} but found {boolish(config.get('initialResume'))}")
    if "sessionId" in config and str(config.get("sessionId")) != str(final_attempt.get("sessionId")):
        raise DelegateError(f"Config final sessionId mismatch. Expected final attempt session {final_attempt.get('sessionId')} but found {config.get('sessionId')}")
    if "resume" in config and boolish(config.get("resume")) != boolish(final_attempt.get("resume")):
        raise DelegateError(f"Config final resume mismatch. Expected final attempt resume {boolish(final_attempt.get('resume'))} but found {boolish(config.get('resume'))}")
    if int(final_attempt.get("exitCode")) != int(status.get("exitCode")):
        raise DelegateError(f"Final attempt exitCode mismatch. Expected {status.get('exitCode')} but found {final_attempt.get('exitCode')}")
    if completed:
        if not boolish(final_attempt.get("sawResultSuccess")):
            raise DelegateError("Completed delegate must record sawResultSuccess=true on the final attempt.")
        if not boolish(final_attempt.get("capturedFinalResult")):
            raise DelegateError("Completed delegate must record capturedFinalResult=true on the final attempt.")
    if structured_failure and not boolish(final_attempt.get("capturedFinalResult")):
        raise DelegateError("Structured failed delegate must record capturedFinalResult=true on the final attempt.")
    optional_paths: set[str] = set()
    for prop in ("rawStreamPath", "tracePath", "promptPath"):
        for obj in (config, status):
            if obj.get(prop):
                optional_paths.add(str(obj[prop]))
    for path_text in optional_paths:
        if not Path(path_text).exists():
            raise DelegateError(f"Referenced artifact path is missing: {path_text}")
    state_path = config.get("sessionStatePath")
    if state_path and Path(str(state_path)).exists():
        state = load_json(Path(str(state_path)))
        primary = state.get("primary") if isinstance(state.get("primary"), dict) else {}
        if str(primary.get("leaseRunId")) == run_id:
            raise DelegateError(f"Primary session lease is still held by run {run_id}.")
        for slot in state.get("parallelPool") or []:
            if str(slot.get("leaseRunId")) == run_id:
                raise DelegateError(f"Parallel session lease is still held by run {run_id}.")
    return {"config": config, "status": status, "workflow": workflow, "artifactRoot": root}



def run_verify_artifacts(ns: argparse.Namespace) -> int:
    verify_artifacts(ns.run_id, ns.artifact_root)
    print(f"Artifact verification passed for RunId: {ns.run_id}")
    return 0


def workflow_verifier_audit_paths(root: Path, workflow_id: str) -> tuple[Path, Path]:
    safe_id = workflow_path(root, workflow_id).stem.removeprefix("workflow_")
    return root / f"verifier_audit_{safe_id}.json", root / f"verifier_audit_{safe_id}.md"


def main_thread_action_for_failed_gate(gate_name: str) -> str:
    return {
        "workflow_artifact": "inspect_workflow_artifact",
        "run_artifacts": "inspect_missing_or_invalid_run_artifacts",
        "implementer_gate": "inspect_failed_runs_or_trigger_forensics",
        "review_gates": "dispatch_missing_review_gates",
        "final_verifier_gate": "dispatch_final_verifier",
        "declared_tests": "rerun_or_correct_verification_evidence",
        "parallel_scope": "resolve_parallel_scope_conflict",
    }.get(gate_name, "inspect_workflow_verifier_failure")


def build_workflow_verifier_audit(
    *,
    root: Path,
    workflow_id: str,
    workflow_file: Path,
    workflow: dict[str, Any],
    verified_runs: dict[str, dict[str, Any]],
    gate_results: list[dict[str, Any]],
    verifier_passed: bool,
    error: str = "",
) -> dict[str, Any]:
    failed_gate = next((item for item in gate_results if not item.get("passed")), None)
    final_acceptance = workflow.get("finalAcceptance") if isinstance(workflow.get("finalAcceptance"), dict) else {}
    acceptance_allowed = bool(verifier_passed and final_acceptance.get("status") == "accepted")
    main_action = "accept_or_commit" if acceptance_allowed else main_thread_action_for_failed_gate(str((failed_gate or {}).get("gate") or "workflow_verifier"))
    run_summaries = []
    for run_id, record in sorted(verified_runs.items()):
        config = record.get("config") if isinstance(record.get("config"), dict) else {}
        status = record.get("status") if isinstance(record.get("status"), dict) else {}
        run_summaries.append(
            {
                "runId": run_id,
                "taskId": str(config.get("taskId") or status.get("taskId") or ""),
                "role": str(config.get("role") or status.get("role") or ""),
                "runStatus": str(status.get("status") or ""),
                "workerOutcome": str(status.get("workerOutcome") or config.get("workerOutcome") or ""),
                "failureLayer": str(status.get("failureLayer") or config.get("failureLayer") or ""),
                "businessAcceptance": str(status.get("businessAcceptance") or config.get("businessAcceptance") or ""),
                "outputPath": str(config.get("outputPath") or ""),
                "statusPath": str(config.get("statusPath") or status.get("statusPath") or ""),
                "configPath": str(config.get("configPath") or ""),
            }
        )
    return {
        "artifactSchema": ARTIFACT_SCHEMA_VERSION,
        "invocationContract": INVOCATION_CONTRACT,
        "command": "verify_delegate_workflow",
        "auditType": "codex-with-cc-workflow-verifier-audit",
        "workflowId": workflow_id,
        "artifactRoot": str(root),
        "workflowPath": str(workflow_file),
        "verifierPassed": verifier_passed,
        "acceptanceAllowed": acceptance_allowed,
        "workflowFinalAcceptance": final_acceptance,
        "gateResults": gate_results,
        "failedGate": failed_gate or {},
        "missingGates": [str(item.get("gate")) for item in gate_results if not item.get("passed")],
        "verifiedRunCount": len(verified_runs),
        "verifiedRuns": run_summaries,
        "mainThreadAction": main_action,
        "nextCommand": "accept_or_commit" if acceptance_allowed else f"ccstatus audit -WorkflowId {workflow_id} -ArtifactRoot {root} --json",
        "confidence": "high" if gate_results else "medium",
        "error": error,
        "evidencePaths": {
            "workflow": str(workflow_file),
        },
        "provenance": {
            "sources": ["workflow", "verified_run_artifacts", "workflow_verifier_gates"],
            "generatedReasoning": ["acceptanceAllowed", "mainThreadAction", "missingGates"],
        },
        "mayOverrideValidator": False,
        "mayOverrideVerifier": False,
        "updatedAt": now_iso(),
    }


def write_workflow_verifier_audit(audit: dict[str, Any]) -> tuple[Path, Path]:
    root = Path(str(audit["artifactRoot"])).resolve()
    workflow_id = str(audit["workflowId"])
    json_path, md_path = workflow_verifier_audit_paths(root, workflow_id)
    audit["auditPath"] = str(json_path)
    audit["auditMarkdownPath"] = str(md_path)
    audit.setdefault("evidencePaths", {})["verifierAudit"] = str(json_path)
    audit["evidencePaths"]["verifierAuditMarkdown"] = str(md_path)
    write_json(json_path, audit)
    write_text(
        md_path,
        "\n".join(
            [
                "# Codex With CC Workflow Verifier Audit",
                "",
                f"WorkflowId: {workflow_id}",
                f"VerifierPassed: {str(audit.get('verifierPassed')).lower()}",
                f"AcceptanceAllowed: {str(audit.get('acceptanceAllowed')).lower()}",
                f"MainThreadAction: {audit.get('mainThreadAction')}",
                f"FailedGate: {(audit.get('failedGate') or {}).get('gate') or '-'}",
                f"mayOverrideVerifier: {str(audit.get('mayOverrideVerifier')).lower()}",
                "",
                "## Gate Results",
                "",
                "\n".join(
                    f"- {item.get('gate')}: {'passed' if item.get('passed') else 'failed'}"
                    + (f" - {item.get('message')}" if item.get("message") else "")
                    for item in audit.get("gateResults") or []
                )
                or "- none",
                "",
                "## Verified Runs",
                "",
                "\n".join(
                    f"- {item.get('runId')}: role={item.get('role') or '-'} status={item.get('runStatus') or '-'} failureLayer={item.get('failureLayer') or '-'}"
                    for item in audit.get("verifiedRuns") or []
                )
                or "- none",
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


def _gate_pass(gate_results: list[dict[str, Any]], gate: str, message: str = "") -> None:
    gate_results.append({"gate": gate, "passed": True, "message": message})


def _gate_fail(gate_results: list[dict[str, Any]], gate: str, message: str) -> None:
    gate_results.append({"gate": gate, "passed": False, "message": message})


def run_verify_workflow(ns: argparse.Namespace) -> int:
    root = resolve_artifact_root(ns.artifact_root, workflow_id=ns.workflow_id)
    path = workflow_path(root, ns.workflow_id)
    if not path.exists():
        raise DelegateError(f"Missing workflow artifact: {path}")
    workflow = load_json(path)
    verified_runs: dict[str, dict[str, Any]] = {}
    gate_results: list[dict[str, Any]] = []

    def write_failure(exc: DelegateError, gate: str) -> None:
        if not gate_results or gate_results[-1].get("gate") != gate or gate_results[-1].get("passed"):
            _gate_fail(gate_results, gate, str(exc))
        audit = build_workflow_verifier_audit(
            root=root,
            workflow_id=ns.workflow_id,
            workflow_file=path,
            workflow=workflow if isinstance(workflow, dict) else {},
            verified_runs=verified_runs,
            gate_results=gate_results,
            verifier_passed=False,
            error=str(exc),
        )
        write_workflow_verifier_audit(audit)

    try:
        if int(workflow.get("artifactSchema", -1)) != ARTIFACT_SCHEMA_VERSION:
            raise DelegateError(f"Unexpected workflow artifact schema. Expected {ARTIFACT_SCHEMA_VERSION}.")
        if workflow.get("invocationContract") != INVOCATION_CONTRACT:
            raise DelegateError(f"Unexpected workflow invocation contract. Expected '{INVOCATION_CONTRACT}'.")
        if workflow.get("workflowId") != ns.workflow_id:
            raise DelegateError("Workflow artifact workflowId mismatch.")
        _gate_pass(gate_results, "workflow_artifact", "workflow artifact schema and identity passed")

        try:
            for run_id in (workflow.get("runs") or {}).keys():
                verified_runs[str(run_id)] = verify_artifacts(str(run_id), str(root))
        except DelegateError as exc:
            _gate_fail(gate_results, "run_artifacts", str(exc))
            raise
        _gate_pass(gate_results, "run_artifacts", f"verified {len(verified_runs)} run artifact set(s)")

        gate_steps = [
            ("implementer_gate", lambda: enforce_no_failed_implementers_before_review_gates(workflow)),
            ("review_gates", lambda: enforce_workflow_review_gates(workflow)),
            ("final_verifier_gate", lambda: enforce_workflow_final_verifier_gate(workflow)),
            ("declared_tests", lambda: enforce_declared_tests_are_reported(workflow, verified_runs)),
            ("parallel_scope", lambda: enforce_parallel_implementer_scope(workflow, verified_runs)),
        ]
        for gate, func in gate_steps:
            try:
                func()
            except DelegateError as exc:
                _gate_fail(gate_results, gate, str(exc))
                raise
            _gate_pass(gate_results, gate)
    except DelegateError as exc:
        failed_gate = str((gate_results[-1] if gate_results else {}).get("gate") or "workflow_artifact")
        write_failure(exc, failed_gate)
        raise

    audit = build_workflow_verifier_audit(
        root=root,
        workflow_id=ns.workflow_id,
        workflow_file=path,
        workflow=workflow,
        verified_runs=verified_runs,
        gate_results=gate_results,
        verifier_passed=True,
    )
    audit_path, audit_md_path = write_workflow_verifier_audit(audit)
    print(f"Workflow verification passed for WorkflowId: {ns.workflow_id}")
    print(f"VerifierAudit: {audit_path}")
    print(f"VerifierAuditMarkdown: {audit_md_path}")
    return 0


def report_has_verification_evidence(text: str) -> bool:
    normalized = " ".join(line.strip().lower() for line in text.splitlines() if line.strip())
    if not normalized:
        return False
    return normalized not in {"none", "- none", "not run", "- not run", "unknown", "- unknown"}


def declared_test_variants(test: str, run_id: str, task_id: str) -> set[str]:
    return {
        test,
        test.replace(f"<{task_id}-run-id>", run_id),
        test.replace("<run-id>", run_id),
    }


def enforce_workflow_review_gates(workflow: dict[str, Any]) -> None:
    tasks = workflow.get("tasks") if isinstance(workflow.get("tasks"), dict) else {}
    problems: list[str] = []
    for task_id, task in tasks.items():
        if not isinstance(task, dict) or task.get("role") != "implementer":
            continue
        reviews = task.get("reviews") if isinstance(task.get("reviews"), dict) else {}
        missing = [kind for kind in REQUIRED_IMPLEMENTER_REVIEWS if not isinstance(reviews.get(kind), dict)]
        rejected = [
            kind
            for kind in REQUIRED_IMPLEMENTER_REVIEWS
            if isinstance(reviews.get(kind), dict) and reviews[kind].get("reviewDecision") != "accepted"
        ]
        if missing:
            problems.append(f"implementer task {task_id} is missing {', '.join(missing)} review")
        if rejected:
            problems.append(f"implementer task {task_id} has non-accepted {', '.join(rejected)} review")
    if problems:
        raise DelegateError("Workflow review gates failed: " + "; ".join(problems))


def enforce_no_failed_implementers_before_review_gates(workflow: dict[str, Any]) -> None:
    tasks = workflow.get("tasks") if isinstance(workflow.get("tasks"), dict) else {}
    problems: list[str] = []
    blocking_statuses = {"FAIL", "BLOCKED", "NEEDS_CONTEXT"}
    for task_id, task in tasks.items():
        if not isinstance(task, dict) or task.get("role") != "implementer":
            continue
        report_status = str(task.get("lastReportStatus") or "")
        report_final = str(task.get("lastReportFinalResult") or "")
        task_status = str(task.get("status") or "")
        if task_status == "failed" or report_status in blocking_statuses or report_final in blocking_statuses:
            status_text = report_status or report_final or task_status
            problems.append(
                f"implementer task {task_id} ended as {status_text} before implementation acceptance; "
                "spec/quality review gates are not applicable yet"
            )
    if problems:
        raise DelegateError("Workflow implementer gate failed: " + "; ".join(problems))


def enforce_workflow_final_verifier_gate(workflow: dict[str, Any]) -> None:
    tasks = workflow.get("tasks") if isinstance(workflow.get("tasks"), dict) else {}
    if not any(isinstance(task, dict) and task.get("role") == "implementer" for task in tasks.values()):
        return
    accepted = [
        task_id
        for task_id, task in tasks.items()
        if isinstance(task, dict)
        and task.get("role") == "final-verifier"
        and task.get("status") == "completed"
        and task.get("lastReportStatus") == "DONE"
        and task.get("lastReportFinalResult") == "DONE"
        and task.get("reviewDecision") == "accepted"
    ]
    if not accepted:
        raise DelegateError("Workflow final-verifier gate failed: implementer workflows require an accepted final-verifier run.")


def enforce_declared_tests_are_reported(workflow: dict[str, Any], verified_runs: dict[str, dict[str, Any]]) -> None:
    problems: list[str] = []
    for run_id, run in (workflow.get("runs") or {}).items():
        record = verified_runs.get(str(run_id))
        if not record:
            continue
        config = record["config"]
        status = record["status"]
        if any(boolish(attempt.get("dryRun")) for attempt in status.get("attempts") or []):
            continue
        tests = [str(item).strip() for item in config.get("tests") or [] if str(item).strip()]
        if not tests:
            continue
        output_path = Path(str(config.get("outputPath")))
        report_text = output_path.read_text(encoding="utf-8")
        verification_text = report_section(report_text, "Verification")
        if parse_report_status(report_text) != "DONE":
            continue
        task_id = str(config.get("taskId") or (run or {}).get("taskId") or run_id)
        missing = [
            item
            for item in tests
            if not any(variant in verification_text for variant in declared_test_variants(item, str(run_id), task_id))
        ]
        if missing:
            problems.append(f"task {task_id} missing declared verification evidence: {'; '.join(missing)}")
    if problems:
        raise DelegateError("Workflow declared verification failed: " + "; ".join(problems))


def normalize_scope_item(value: str) -> str:
    normalized = value.strip().replace("\\", "/").strip("/")
    if len(normalized) >= 2 and normalized[1] == ":":
        normalized = normalized[0].lower() + normalized[1:]
    return normalized.lower()


def scopes_overlap(left: list[str], right: list[str]) -> bool:
    left_items = [normalize_scope_item(item) for item in left if normalize_scope_item(item)]
    right_items = [normalize_scope_item(item) for item in right if normalize_scope_item(item)]
    for left_item in left_items:
        for right_item in right_items:
            if left_item == right_item or left_item.startswith(right_item + "/") or right_item.startswith(left_item + "/"):
                return True
    return False


def enforce_parallel_implementer_scope(workflow: dict[str, Any], verified_runs: dict[str, dict[str, Any]]) -> None:
    parallel: list[tuple[str, str, list[str]]] = []
    problems: list[str] = []
    for run_id, record in verified_runs.items():
        config = record["config"]
        if config.get("role") != "implementer" or not boolish(config.get("allowParallel")):
            continue
        scope = [str(item) for item in config.get("scope") or [] if str(item).strip()]
        task_id = str(config.get("taskId") or run_id)
        if not scope:
            problems.append(f"parallel implementer task {task_id} is missing scope")
            continue
        parallel.append((task_id, run_id, scope))
    for index, (left_task, _left_run, left_scope) in enumerate(parallel):
        for right_task, _right_run, right_scope in parallel[index + 1 :]:
            if scopes_overlap(left_scope, right_scope):
                problems.append(f"overlapping parallel implementer scope between {left_task} and {right_task}")
    if problems:
        raise DelegateError("Workflow parallel scope gate failed: " + "; ".join(problems))



def normalize_run_ids(values: Iterable[str]) -> list[str]:
    out: list[str] = []
    for value in values:
        for part in re.split(r"[\s,]+", str(value)):
            clean = part.strip().strip("'\"")
            if clean:
                out.append(clean)
    return out



def load_artifact_record(root: Path, run_id: str) -> dict[str, Any]:
    verify_artifacts(run_id, str(root))
    return {
        "runId": run_id,
        "config": load_json(root / f"config_{run_id}.json"),
        "status": load_json(root / f"status_{run_id}.json"),
    }



def run_verify_chain(ns: argparse.Namespace) -> int:
    root = Path(ns.artifact_root).resolve()
    parallel_ids = normalize_run_ids(ns.parallel_run_ids)
    reuse_ids = normalize_run_ids(ns.reuse_run_ids)
    anchor = load_artifact_record(root, ns.anchor_run_id)
    parallels = [load_artifact_record(root, run_id) for run_id in parallel_ids]
    reuses = [load_artifact_record(root, run_id) for run_id in reuse_ids]
    if anchor["config"].get("sessionMode") != "PrimaryAnchor":
        raise DelegateError("Anchor run must use PrimaryAnchor.")
    if anchor["config"].get("sessionKey") != ns.session_key:
        raise DelegateError("Anchor run sessionKey mismatch.")
    session_state_path = str(anchor["config"].get("sessionStatePath") or "")
    if not session_state_path:
        raise DelegateError("Anchor run is missing sessionStatePath.")
    if not Path(session_state_path).exists():
        raise DelegateError(f"Missing session state path: {session_state_path}")
    expected_main_session_id = str(anchor["config"].get("sessionId"))
    parallel_pool_reuse = False
    stale_reset_occurred = False
    for record in parallels:
        if record["config"].get("sessionMode") != "ParallelPool":
            raise DelegateError(f"Parallel run '{record['runId']}' must use ParallelPool.")
        if record["config"].get("sessionKey") != ns.session_key:
            raise DelegateError(f"Parallel run '{record['runId']}' sessionKey mismatch.")
        if boolish(record["config"].get("initialResume")):
            parallel_pool_reuse = True
    for record in reuses:
        config = record["config"]
        if config.get("sessionMode") != "PrimaryReuse":
            raise DelegateError(f"Reuse run '{record['runId']}' must use PrimaryReuse.")
        if config.get("sessionKey") != ns.session_key:
            raise DelegateError(f"Reuse run '{record['runId']}' sessionKey mismatch.")
        if not boolish(config.get("initialResume")):
            raise DelegateError(f"Reuse run '{record['runId']}' must start by attempting resume=true.")
        if str(config.get("initialSessionId")) != expected_main_session_id:
            raise DelegateError(f"Reuse run '{record['runId']}' did not start from the expected main session.")
        attempts = list(record["status"].get("attempts") or [])
        first = attempts[0]
        final = attempts[-1]
        if not boolish(first.get("resume")):
            raise DelegateError(f"Reuse run '{record['runId']}' first attempt must be resume=true.")
        if str(final.get("sessionId")) != expected_main_session_id:
            stale_reset_occurred = True
            if int(record["status"].get("retryCount", 0)) < 1:
                raise DelegateError(f"Reuse run '{record['runId']}' changed primary session without recording a retry.")
            if record["status"].get("lastRetryReason") != "stale_claude_session":
                raise DelegateError(f"Reuse run '{record['runId']}' must record stale_claude_session when changing primary session.")
            if boolish(final.get("resume")):
                raise DelegateError(f"Reuse run '{record['runId']}' fresh recovery attempt must be resume=false.")
            expected_main_session_id = str(final.get("sessionId"))
    state = load_json(Path(session_state_path))
    if state.get("sessionKey") != ns.session_key:
        raise DelegateError("Session pool sessionKey mismatch.")
    primary = state.get("primary") or {}
    if primary.get("status") != "available":
        raise DelegateError("Primary session slot must be available after chain completion.")
    if str(primary.get("sessionId")) != expected_main_session_id:
        raise DelegateError("Final primary session ID does not match the expected chain head.")
    if stale_reset_occurred:
        if not primary.get("lastResetAt"):
            raise DelegateError("Primary session reset is missing lastResetAt.")
        if primary.get("lastResetReason") != "stale_claude_session":
            raise DelegateError("Primary session reset reason must be stale_claude_session.")
        if not primary.get("lastResetFromSessionId"):
            raise DelegateError("Primary session reset is missing lastResetFromSessionId.")
        if not primary.get("lastResetFromRunId"):
            raise DelegateError("Primary session reset is missing lastResetFromRunId.")
    for record in parallels:
        session_id = str(record["config"].get("sessionId"))
        slot = next((slot for slot in state.get("parallelPool") or [] if str(slot.get("sessionId")) == session_id), None)
        if slot is None:
            raise DelegateError(f"Parallel pool slot for run '{record['runId']}' was not found.")
        if slot.get("status") != "available":
            raise DelegateError(f"Parallel pool slot for run '{record['runId']}' must be available after chain completion.")
        if not slot.get("lastTaskFingerprint"):
            raise DelegateError(f"Parallel pool slot for run '{record['runId']}' is missing lastTaskFingerprint.")
    orphan = primary.get("status") == "leased" or any(slot.get("status") == "leased" for slot in state.get("parallelPool") or [])
    summary = {
        "primaryCacheHit": True,
        "parallelPoolReuse": parallel_pool_reuse,
        "staleResetOccurred": stale_reset_occurred,
        "orphanLeaseDetected": orphan,
        "artifactContractValid": True,
        "chainPassed": not orphan,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if orphan:
        raise DelegateError("Delegate chain verification failed because a session lease is still active.")
    return 0
