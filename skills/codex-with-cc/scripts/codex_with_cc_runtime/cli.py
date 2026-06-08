from __future__ import annotations

import argparse
import sys
from typing import Callable

from .artifacts import run_verify_artifacts, run_verify_chain, run_verify_workflow
from .claude_cli import PERMISSION_MODES
from .common import DelegateError, WORKER_ROLES
from .cleanup import run_ccclean
from .dashboard import run_ccdash
from .delegate import run_delegate
from .doctor import run_doctor
from .index import run_ccindex
from .openai_compatible_report import run_openai_compatible_report_delegate
from .real_chain import run_real_chain_validation
from .selftests import run_test_runtime, run_test_session_pool
from .supervision import run_ccspec, run_ccsupervise, run_ccwatch
from .task_contract import run_validate_task
from .runtime_control import run_ccruntime
from .status import run_ccstatus
from .ccviz_parser import list_workflows, get_workflow_details
from .ccviz_renderer import render_list, render_show, render_audit



def choice_arg(choices: list[str]) -> Callable[[str], str]:
    lookup = {choice.lower(): choice for choice in choices}

    def parse(value: str) -> str:
        selected = lookup.get(value.lower())
        if selected is None:
            expected = ", ".join(choices)
            raise argparse.ArgumentTypeError(f"invalid choice: {value!r} (choose from {expected})")
        return selected

    return parse



def int_range_arg(name: str, minimum: int, maximum: int) -> Callable[[str], int]:
    def parse(value: str) -> int:
        try:
            parsed = int(value)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(f"{name} must be an integer") from exc
        if parsed < minimum or parsed > maximum:
            raise argparse.ArgumentTypeError(f"{name} must be between {minimum} and {maximum}")
        return parsed

    return parse



def add_delegate_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("-TaskFile", dest="task_file", required=True)
    parser.add_argument("-Scope", dest="scope", action="append", default=[])
    parser.add_argument("-Tests", dest="tests", action="append", default=[])
    parser.add_argument("-WorkflowId", dest="workflow_id", required=True)
    parser.add_argument("-TaskId", dest="task_id", required=True)
    parser.add_argument("-Role", dest="role", type=choice_arg(list(WORKER_ROLES)), required=True)
    parser.add_argument("-ReviewForTaskId", dest="review_for_task_id")
    parser.add_argument("-ReviewKind", dest="review_kind", type=choice_arg(["spec", "quality"]))
    parser.add_argument("-DependsOn", dest="depends_on", action="append", default=[])
    parser.add_argument("-Model", dest="model", default="sonnet")
    parser.add_argument("-PermissionMode", dest="permission_mode", type=choice_arg(list(PERMISSION_MODES)), default="acceptEdits")
    parser.add_argument("-Name", dest="name")
    parser.add_argument("-NamePrefix", dest="name_prefix", default="codex-delegate")
    parser.add_argument("-MaxBudgetUsd", dest="max_budget_usd")
    parser.add_argument("-MaxTurns", dest="max_turns", type=int_range_arg("MaxTurns", 1, 1000))
    parser.add_argument("-IncludePartialMessages", dest="include_partial_messages", action="store_true")
    parser.add_argument("-ArtifactRoot", dest="artifact_root")
    parser.add_argument("-OutputPath", dest="output_path")
    parser.add_argument("-AllowParallel", dest="allow_parallel", action="store_true")
    parser.add_argument("-SessionMode", dest="session_mode", type=choice_arg(["PrimaryReuse", "PrimaryAnchor", "ParallelPool"]), default="PrimaryReuse")
    parser.add_argument("-SessionKey", dest="session_key", required=True)
    parser.add_argument("-SessionLeaseTimeoutSeconds", dest="session_lease_timeout_seconds", type=int, default=21600)
    parser.add_argument("-SessionLeaseWaitSeconds", dest="session_lease_wait_seconds", type=int, default=120)
    parser.add_argument("-ResetPrimarySession", dest="reset_primary_session", action="store_true")
    parser.add_argument("-ResetParallelPool", dest="reset_parallel_pool", action="store_true")
    parser.add_argument("-LockTimeoutSeconds", dest="lock_timeout_seconds", type=int, default=120)
    parser.add_argument("-LockPollMilliseconds", dest="lock_poll_milliseconds", type=int, default=500)
    parser.add_argument("-MaxRetryCount", dest="max_retry_count", type=int_range_arg("MaxRetryCount", 0, 100), default=5)
    parser.add_argument("-BypassPermissions", dest="bypass_permissions", action="store_true")
    parser.add_argument("-DryRun", dest="dry_run", action="store_true")


def add_validate_task_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("-TaskFile", dest="task_file", required=True)
    parser.add_argument("-Role", dest="role", type=choice_arg(list(WORKER_ROLES)), required=True)
    parser.add_argument("-ReviewForTaskId", dest="review_for_task_id")
    parser.add_argument("-ReviewKind", dest="review_kind", type=choice_arg(["spec", "quality"]))
    parser.add_argument("-Tests", dest="tests", action="append", default=[])



def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="codex_with_cc scripts", allow_abbrev=False)
    sub = parser.add_subparsers(dest="command", required=True)
    delegate = sub.add_parser("delegate", allow_abbrev=False)
    add_delegate_args(delegate)
    delegate.set_defaults(func=run_delegate)

    report = sub.add_parser("openai-compatible-report", allow_abbrev=False)
    add_delegate_args(report)
    report.set_defaults(func=run_openai_compatible_report_delegate, model="deepseek-v4-flash")

    validate_task = sub.add_parser("validate-task", allow_abbrev=False)
    add_validate_task_args(validate_task)
    validate_task.set_defaults(func=run_validate_task)

    verify = sub.add_parser("verify-artifacts", allow_abbrev=False)
    verify.add_argument("-RunId", dest="run_id", required=True)
    verify.add_argument("-ArtifactRoot", dest="artifact_root")
    verify.set_defaults(func=run_verify_artifacts)

    verify_run = sub.add_parser("verify-run", allow_abbrev=False)
    verify_run.add_argument("-RunId", dest="run_id", required=True)
    verify_run.add_argument("-ArtifactRoot", dest="artifact_root")
    verify_run.set_defaults(func=run_verify_artifacts)

    workflow = sub.add_parser("verify-workflow", allow_abbrev=False)
    workflow.add_argument("-WorkflowId", dest="workflow_id", required=True)
    workflow.add_argument("-ArtifactRoot", dest="artifact_root")
    workflow.set_defaults(func=run_verify_workflow)

    chain = sub.add_parser("verify-chain", allow_abbrev=False)
    chain.add_argument("-ArtifactRoot", dest="artifact_root", required=True)
    chain.add_argument("-SessionKey", dest="session_key", required=True)
    chain.add_argument("-AnchorRunId", dest="anchor_run_id", required=True)
    chain.add_argument("-ParallelRunIds", dest="parallel_run_ids", nargs="+", required=True)
    chain.add_argument("-ReuseRunIds", dest="reuse_run_ids", nargs="+", required=True)
    chain.set_defaults(func=run_verify_chain)

    validation = sub.add_parser("run-real-chain-validation", allow_abbrev=False)
    validation.add_argument("-ValidationRoot", dest="validation_root")
    validation.add_argument("-Name", dest="name")
    validation.add_argument("-SessionKey", dest="session_key")
    validation.set_defaults(func=run_real_chain_validation)

    sub.add_parser("test-runtime").set_defaults(func=run_test_runtime)
    sub.add_parser("test-session-pool").set_defaults(func=run_test_session_pool)

    doctor = sub.add_parser("doctor", allow_abbrev=False)
    doctor.add_argument("-ArtifactRoot", dest="artifact_root")
    doctor.add_argument("-ClaudeSmoke", dest="claude_smoke", action="store_true")
    doctor.add_argument("-TimeoutSeconds", dest="timeout_seconds", type=int, default=10)
    doctor.add_argument("--json", dest="json", action="store_true")
    doctor.set_defaults(func=run_doctor)

    ccruntime = sub.add_parser("ccruntime", allow_abbrev=False)
    ccruntime_sub = ccruntime.add_subparsers(dest="ccruntime_command", required=True)
    runtime_status = ccruntime_sub.add_parser("status", allow_abbrev=False)
    runtime_status.add_argument("-ClaudeSettingsPath", dest="claude_settings_path")
    runtime_status.add_argument("--json", dest="json", action="store_true")
    runtime_status.set_defaults(func=run_ccruntime)
    runtime_doctor = ccruntime_sub.add_parser("doctor", allow_abbrev=False)
    runtime_doctor.add_argument("-ArtifactRoot", dest="artifact_root")
    runtime_doctor.add_argument("-ClaudeSettingsPath", dest="claude_settings_path")
    runtime_doctor.add_argument("-ClaudeSmoke", dest="claude_smoke", action="store_true")
    runtime_doctor.add_argument("-TimeoutSeconds", dest="timeout_seconds", type=int, default=10)
    runtime_doctor.add_argument("--json", dest="json", action="store_true")
    runtime_doctor.set_defaults(func=run_ccruntime)
    for runtime_command_name in ("plan-switch", "apply-switch"):
        runtime_command = ccruntime_sub.add_parser(runtime_command_name, allow_abbrev=False)
        runtime_command.add_argument("-Model", dest="model", type=choice_arg(["opus", "sonnet", "haiku"]))
        runtime_command.add_argument("-PermissionMode", dest="permission_mode", type=choice_arg(list(PERMISSION_MODES)), default="acceptEdits")
        runtime_command.add_argument("-BaseUrl", dest="base_url")
        runtime_command.add_argument("-OpusModel", dest="opus_model")
        runtime_command.add_argument("-OpusModelName", dest="opus_model_name")
        runtime_command.add_argument("-SonnetModel", dest="sonnet_model")
        runtime_command.add_argument("-SonnetModelName", dest="sonnet_model_name")
        runtime_command.add_argument("-HaikuModel", dest="haiku_model")
        runtime_command.add_argument("-HaikuModelName", dest="haiku_model_name")
        runtime_command.add_argument("-EffortLevel", dest="effort_level")
        runtime_command.add_argument("-ApiTimeoutMs", dest="api_timeout_ms")
        runtime_command.add_argument("-ArtifactRoot", dest="artifact_root")
        runtime_command.add_argument("-ClaudeSettingsPath", dest="claude_settings_path")
        runtime_command.add_argument("-ConfirmRuntimeChange", dest="confirm_runtime_change", action="store_true")
        runtime_command.add_argument("--json", dest="json", action="store_true")
        runtime_command.set_defaults(func=run_ccruntime)

    ccstatus = sub.add_parser("ccstatus", allow_abbrev=False)
    ccstatus_sub = ccstatus.add_subparsers(dest="ccstatus_command", required=True)
    for command_name in ("summary", "claude", "preflight"):
        command = ccstatus_sub.add_parser(command_name, allow_abbrev=False)
        command.add_argument("-ArtifactRoot", dest="artifact_root", action="append", default=[])
        command.add_argument("-ProjectRoot", dest="project_root", action="append", default=[])
        command.add_argument("-AllProjects", dest="all_projects", action="store_true")
        command.add_argument("-ProjectMatch", dest="project_match", action="append", default=[])
        command.add_argument("-ClaudeSettingsPath", dest="claude_settings_path")
        command.add_argument("-ClaudeSmoke", dest="claude_smoke", action="store_true")
        command.add_argument("-TimeoutSeconds", dest="timeout_seconds", type=int, default=10)
        command.add_argument("-StaleAfterSeconds", dest="stale_after_seconds", type=int, default=600)
        command.add_argument("--json", dest="json", action="store_true")
        command.set_defaults(func=run_ccstatus)
    for command_name in ("run", "audit"):
        ccstatus_run = ccstatus_sub.add_parser(command_name, allow_abbrev=False)
        ccstatus_run.add_argument("-RunId", dest="run_id", required=True)
        ccstatus_run.add_argument("-ArtifactRoot", dest="artifact_root")
        ccstatus_run.add_argument("-StaleAfterSeconds", dest="stale_after_seconds", type=int, default=600)
        ccstatus_run.add_argument("--json", dest="json", action="store_true")
        ccstatus_run.add_argument("--no-verify", dest="no_verify", action="store_true")
        ccstatus_run.set_defaults(func=run_ccstatus)
    ccstatus_workflow = ccstatus_sub.add_parser("workflow", allow_abbrev=False)
    ccstatus_workflow.add_argument("-WorkflowId", dest="workflow_id", required=True)
    ccstatus_workflow.add_argument("-ArtifactRoot", dest="artifact_root")
    ccstatus_workflow.add_argument("--json", dest="json", action="store_true")
    ccstatus_workflow.set_defaults(func=run_ccstatus)

    # ccviz subcommands
    ccviz = sub.add_parser("ccviz", allow_abbrev=False)
    ccviz_sub = ccviz.add_subparsers(dest="ccviz_command", required=True)
    
    ccviz_list = ccviz_sub.add_parser("list", allow_abbrev=False)
    ccviz_list.add_argument("-ArtifactRoot", dest="artifact_root")
    ccviz_list.set_defaults(func=run_ccviz_list)
    
    ccviz_show = ccviz_sub.add_parser("show", allow_abbrev=False)
    ccviz_show.add_argument("workflow_id")
    ccviz_show.add_argument("-ArtifactRoot", dest="artifact_root")
    ccviz_show.set_defaults(func=run_ccviz_show)
    
    ccviz_audit = ccviz_sub.add_parser("audit", allow_abbrev=False)
    ccviz_audit.add_argument("workflow_id")
    ccviz_audit.add_argument("-ArtifactRoot", dest="artifact_root")
    ccviz_audit.set_defaults(func=run_ccviz_audit)

    ccwatch = sub.add_parser("ccwatch", allow_abbrev=False)
    watch_target = ccwatch.add_mutually_exclusive_group(required=True)
    watch_target.add_argument("-RunId", dest="run_id")
    watch_target.add_argument("-WorkflowId", dest="workflow_id")
    ccwatch.add_argument("-ArtifactRoot", dest="artifact_root")
    ccwatch.add_argument("-StaleAfterSeconds", dest="stale_after_seconds", type=int, default=600)
    ccwatch.add_argument("--json", dest="json", action="store_true")
    ccwatch.add_argument("--no-verify", dest="no_verify", action="store_true")
    ccwatch.set_defaults(func=run_ccwatch)

    ccsupervise = sub.add_parser("ccsupervise", allow_abbrev=False)
    ccsupervise.add_argument("-RunId", dest="run_id", required=True)
    ccsupervise.add_argument("-ArtifactRoot", dest="artifact_root")
    ccsupervise.add_argument("-StaleAfterSeconds", dest="stale_after_seconds", type=int, default=600)
    ccsupervise.add_argument("-Wait", dest="wait", action="store_true")
    ccsupervise.add_argument("-TimeoutSeconds", dest="timeout_seconds", type=int, default=600)
    ccsupervise.add_argument("-PollSeconds", dest="poll_seconds", type=float, default=5.0)
    ccsupervise.add_argument("--json", dest="json", action="store_true")
    ccsupervise.add_argument("--no-verify", dest="no_verify", action="store_true")
    ccsupervise.set_defaults(func=run_ccsupervise)

    ccspec = sub.add_parser("ccspec", allow_abbrev=False)
    ccspec.add_argument("-SpecRoot", dest="spec_root")
    ccspec_sub = ccspec.add_subparsers(dest="ccspec_command", required=True)
    ccspec_sub.add_parser("path", allow_abbrev=False).set_defaults(func=run_ccspec)
    ccspec_sub.add_parser("list", allow_abbrev=False).set_defaults(func=run_ccspec)
    ccspec_new = ccspec_sub.add_parser("new", allow_abbrev=False)
    ccspec_new.add_argument("slug")
    ccspec_new.add_argument("-Title", dest="title")
    ccspec_new.add_argument("--force", dest="force", action="store_true")
    ccspec_new.set_defaults(func=run_ccspec)

    ccclean = sub.add_parser("ccclean", allow_abbrev=False)
    ccclean_sub = ccclean.add_subparsers(dest="ccclean_command", required=True)
    for command_name in ("list", "plan", "apply"):
        command = ccclean_sub.add_parser(command_name, allow_abbrev=False)
        command.add_argument("-ArtifactRoot", dest="artifact_root", action="append", default=[])
        command.add_argument("-ProjectRoot", dest="project_root", action="append", default=[])
        command.add_argument("-AllProjects", dest="all_projects", action="store_true")
        command.add_argument("-ProjectMatch", dest="project_match", action="append", default=[])
        command.add_argument("-WorkflowId", dest="workflow_id", action="append", default=[])
        command.add_argument("-RunId", dest="run_id", action="append", default=[])
        command.add_argument("-State", dest="state", action="append", default=[])
        command.add_argument("-Result", dest="result", action="append", default=[])
        command.add_argument("-Role", dest="role", action="append", default=[])
        command.add_argument("-RunnerType", dest="runner_type", action="append", default=[])
        command.add_argument("-OlderThanDays", dest="older_than_days", type=float)
        command.add_argument("-OlderThanHours", dest="older_than_hours", type=float)
        command.add_argument("-Before", dest="before")
        command.add_argument("-IgnoreAge", dest="ignore_age", action="store_true")
        command.add_argument("-IncludeFailures", dest="include_failures", action="store_true")
        command.add_argument("-IncludeRunning", dest="include_running", action="store_true")
        command.add_argument("-IncludeOrphans", dest="include_orphans", action="store_true")
        command.add_argument("-StaleAfterSeconds", dest="stale_after_seconds", type=int, default=600)
        command.add_argument("-TrashRoot", dest="trash_root")
        command.add_argument("-Limit", dest="limit", type=int)
        command.add_argument("-ConfirmDelete", dest="confirm_delete", action="store_true")
        command.add_argument("--json", dest="json", action="store_true")
        command.set_defaults(func=run_ccclean)

    ccindex = sub.add_parser("ccindex", allow_abbrev=False)
    ccindex_sub = ccindex.add_subparsers(dest="ccindex_command", required=True)
    for command_name in ("build", "list", "export"):
        command = ccindex_sub.add_parser(command_name, allow_abbrev=False)
        command.add_argument("-ArtifactRoot", dest="artifact_root", action="append", default=[])
        command.add_argument("-ProjectRoot", dest="project_root", action="append", default=[])
        command.add_argument("-AllProjects", dest="all_projects", action="store_true")
        command.add_argument("-ProjectMatch", dest="project_match", action="append", default=[])
        command.add_argument("-Output", dest="output")
        command.add_argument("-StaleAfterSeconds", dest="stale_after_seconds", type=int, default=600)
        command.add_argument("--json", dest="json", action="store_true")
        command.set_defaults(func=run_ccindex)
    ccindex_show = ccindex_sub.add_parser("show", allow_abbrev=False)
    ccindex_show.add_argument("workflow_id")
    ccindex_show.add_argument("-ArtifactRoot", dest="artifact_root", action="append", default=[])
    ccindex_show.add_argument("-ProjectRoot", dest="project_root", action="append", default=[])
    ccindex_show.add_argument("-AllProjects", dest="all_projects", action="store_true")
    ccindex_show.add_argument("-ProjectMatch", dest="project_match", action="append", default=[])
    ccindex_show.add_argument("-StaleAfterSeconds", dest="stale_after_seconds", type=int, default=600)
    ccindex_show.add_argument("--json", dest="json", action="store_true")
    ccindex_show.set_defaults(func=run_ccindex)

    ccdash = sub.add_parser("ccdash", allow_abbrev=False)
    ccdash_sub = ccdash.add_subparsers(dest="ccdash_command", required=True)
    for command_name in ("build", "open"):
        command = ccdash_sub.add_parser(command_name, allow_abbrev=False)
        command.add_argument("-ArtifactRoot", dest="artifact_root", action="append", default=[])
        command.add_argument("-ProjectRoot", dest="project_root", action="append", default=[])
        command.add_argument("-AllProjects", dest="all_projects", action="store_true")
        command.add_argument("-ProjectMatch", dest="project_match", action="append", default=[])
        command.add_argument("-OutputRoot", dest="output_root")
        command.add_argument("-StaleAfterSeconds", dest="stale_after_seconds", type=int, default=600)
        command.add_argument("--json", dest="json", action="store_true")
        command.add_argument("--no-open", dest="no_open", action="store_true")
        command.set_defaults(func=run_ccdash)

    return parser


def run_ccviz_list(ns: argparse.Namespace) -> int:
    workflows = list_workflows(ns.artifact_root)
    render_list(workflows)
    return 0


def run_ccviz_show(ns: argparse.Namespace) -> int:
    wf = get_workflow_details(ns.workflow_id, ns.artifact_root)
    if not wf:
        print(f"\033[91mError: Workflow '{ns.workflow_id}' not found.\033[0m", file=sys.stderr)
        return 1
    render_show(wf)
    return 0


def run_ccviz_audit(ns: argparse.Namespace) -> int:
    wf = get_workflow_details(ns.workflow_id, ns.artifact_root)
    if not wf:
        print(f"\033[91mError: Workflow '{ns.workflow_id}' not found.\033[0m", file=sys.stderr)
        return 1
    render_audit(wf)
    return 0



def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    ns = parser.parse_args(argv)
    try:
        return int(ns.func(ns))
    except DelegateError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Interrupted", file=sys.stderr)
        return 130
