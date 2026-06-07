from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .artifacts import recorded_delegate_pid
from .common import ARTIFACT_SCHEMA_VERSION, INVOCATION_CONTRACT, DelegateError, now_iso
from .io_utils import load_json, read_text, write_json, write_text
from .locks import pid_alive
from .paths import codex_home, project_artifact_root, project_artifact_key, repo_root, user_artifact_root
from .reports import parse_report_final_result, parse_report_status


FAILURE_RESULTS = {"FAIL", "BLOCKED", "NEEDS_CONTEXT", "DONE_WITH_CONCERNS"}
FAILURE_STATES = {"FAILED", "RUNNING_DEAD_PROCESS", "STALE"}
ACTIVE_STATES = {"STARTING", "RUNNING_ACTIVE", "RUNNING_QUIET"}
TERMINAL_SUCCESS_STATES = {"REPORT_READY"}
RUN_FILE_PREFIXES = ("config", "status", "prompt", "stream", "trace", "claude", "report", "supervisor")
RUN_FILE_EXTENSIONS = ("json", "md", "jsonl", "log")


def _path_inside(root: Path, candidate: Path) -> bool:
    try:
        candidate.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def _file_meta(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "path": str(path),
        "sizeBytes": stat.st_size,
        "modifiedEpoch": stat.st_mtime,
        "modifiedAt": _format_epoch(stat.st_mtime),
    }


def _format_epoch(value: float | None) -> str:
    if value is None:
        return ""
    return datetime.fromtimestamp(value, timezone.utc).astimezone().isoformat()


def _load_json_if_exists(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return load_json(path)
    except Exception:
        return {"_parseError": True, "_path": str(path)}


def _safe_add_path(root: Path, files: set[Path], unsafe: list[str], value: Any) -> None:
    if not value:
        return
    path = Path(str(value)).expanduser()
    if not path.is_absolute():
        path = root / path.name
    path = path.resolve()
    if not _path_inside(root, path):
        unsafe.append(str(path))
        return
    if path.exists() and path.is_file():
        files.add(path)


def _known_run_files(root: Path, run_id: str) -> set[Path]:
    paths: set[Path] = set()
    for prefix in RUN_FILE_PREFIXES:
        for ext in RUN_FILE_EXTENSIONS:
            path = root / f"{prefix}_{run_id}.{ext}"
            if path.exists() and path.is_file():
                paths.add(path.resolve())
    return paths


def _output_path_for(root: Path, run_id: str, config: dict[str, Any], workflow_run: dict[str, Any]) -> Path:
    explicit = config.get("outputPath") or workflow_run.get("outputPath")
    if explicit:
        path = Path(str(explicit))
        if path.is_absolute():
            return path.resolve()
        return (root / path.name).resolve()
    if str(config.get("runnerType") or workflow_run.get("runnerType")) == "openai_compatible_report":
        return (root / f"report_{run_id}.md").resolve()
    return (root / f"claude_{run_id}.md").resolve()


def _run_status_state(status_value: str, status: dict[str, Any], newest_activity: float | None, stale_after_seconds: int) -> str:
    if status_value == "completed":
        return "REPORT_READY"
    if status_value == "failed":
        return "FAILED"
    if status_value == "starting":
        return "STARTING"
    if status_value == "running":
        pid = recorded_delegate_pid(status)
        if pid is not None and not pid_alive(pid):
            return "RUNNING_DEAD_PROCESS"
        if newest_activity is not None and time.time() - newest_activity >= stale_after_seconds:
            return "STALE"
        return "RUNNING_ACTIVE"
    return "RUNNING_QUIET"


def _run_summary(root: Path, run_id: str, workflow_run: dict[str, Any], stale_after_seconds: int) -> dict[str, Any]:
    config_path = Path(str(workflow_run.get("configPath") or root / f"config_{run_id}.json"))
    status_path = Path(str(workflow_run.get("statusPath") or root / f"status_{run_id}.json"))
    if not config_path.is_absolute():
        config_path = root / config_path.name
    if not status_path.is_absolute():
        status_path = root / status_path.name
    config_path = config_path.resolve()
    status_path = status_path.resolve()
    config = _load_json_if_exists(config_path)
    status = _load_json_if_exists(status_path)
    output_path = _output_path_for(root, run_id, config, workflow_run)
    files = _known_run_files(root, run_id)
    unsafe_paths: list[str] = []
    for obj in (config, status, workflow_run):
        for key in ("configPath", "statusPath", "outputPath", "promptPath", "rawStreamPath", "tracePath"):
            _safe_add_path(root, files, unsafe_paths, obj.get(key))
    _safe_add_path(root, files, unsafe_paths, config_path)
    _safe_add_path(root, files, unsafe_paths, status_path)
    _safe_add_path(root, files, unsafe_paths, output_path)

    newest = max((path.stat().st_mtime for path in files if path.exists()), default=None)
    status_value = str(status.get("status") or workflow_run.get("status") or config.get("status") or "unknown")
    state = _run_status_state(status_value, status, newest, stale_after_seconds)
    report_text = read_text(output_path) if output_path.exists() else ""
    report_status = parse_report_status(report_text) if report_text else str(workflow_run.get("reportStatus") or "")
    final_result = parse_report_final_result(report_text) if report_text else str(workflow_run.get("reportFinalResult") or "")
    role = str(config.get("role") or status.get("role") or workflow_run.get("role") or "")
    runner_type = str(config.get("runnerType") or status.get("runnerType") or workflow_run.get("runnerType") or "")
    return {
        "runId": run_id,
        "workflowId": str(config.get("workflowId") or status.get("workflowId") or ""),
        "taskId": str(config.get("taskId") or status.get("taskId") or workflow_run.get("taskId") or ""),
        "role": role,
        "runnerType": runner_type,
        "status": status_value,
        "state": state,
        "reportStatus": report_status,
        "finalResult": final_result,
        "newestActivityEpoch": newest,
        "newestActivityAt": _format_epoch(newest),
        "files": sorted(str(path) for path in files),
        "missingCoreArtifacts": [
            label for label, path in (("config", config_path), ("status", status_path), ("output", output_path)) if not path.exists()
        ],
        "unsafeReferencedPaths": unsafe_paths,
    }


def _item_confidence(kind: str, runs: list[dict[str, Any]], unsafe_paths: list[str], parse_error: bool) -> str:
    if parse_error or unsafe_paths:
        return "low"
    if kind == "orphan-run":
        return "medium"
    if any(run.get("missingCoreArtifacts") for run in runs):
        return "medium"
    return "high"


def _aggregate_item(root: Path, kind: str, workflow_id: str, workflow_file: Path | None, runs: list[dict[str, Any]], extra_files: set[Path], parse_error: bool = False) -> dict[str, Any]:
    files: set[Path] = {path.resolve() for path in extra_files if path.exists() and path.is_file()}
    unsafe_paths: list[str] = []
    for run in runs:
        files.update(Path(path).resolve() for path in run.get("files") or [] if Path(path).exists())
        unsafe_paths.extend(run.get("unsafeReferencedPaths") or [])
    if workflow_file and workflow_file.exists():
        files.add(workflow_file.resolve())
    newest = max((path.stat().st_mtime for path in files), default=None)
    oldest = min((path.stat().st_mtime for path in files), default=None)
    state_counts: dict[str, int] = {}
    results: dict[str, int] = {}
    roles: dict[str, int] = {}
    runner_types: dict[str, int] = {}
    for run in runs:
        state_counts[str(run.get("state") or "UNKNOWN")] = state_counts.get(str(run.get("state") or "UNKNOWN"), 0) + 1
        result = str(run.get("finalResult") or "unknown")
        results[result] = results.get(result, 0) + 1
        role = str(run.get("role") or "unknown")
        roles[role] = roles.get(role, 0) + 1
        runner_type = str(run.get("runnerType") or "unknown")
        runner_types[runner_type] = runner_types.get(runner_type, 0) + 1
    size_bytes = sum(path.stat().st_size for path in files)
    item_id = f"{kind}:{workflow_id or ','.join(run.get('runId', '') for run in runs)}:{_hash_text(str(root))}"
    return {
        "itemId": item_id,
        "itemType": kind,
        "artifactRoot": str(root),
        "projectKey": root.name,
        "workflowId": workflow_id,
        "workflowPath": str(workflow_file) if workflow_file else "",
        "runIds": [str(run.get("runId")) for run in runs],
        "stateCounts": state_counts,
        "results": results,
        "roles": roles,
        "runnerTypes": runner_types,
        "runSummaries": runs,
        "fileCount": len(files),
        "sizeBytes": size_bytes,
        "newestActivityEpoch": newest,
        "newestActivityAt": _format_epoch(newest),
        "oldestActivityEpoch": oldest,
        "oldestActivityAt": _format_epoch(oldest),
        "files": sorted(str(path) for path in files),
        "unsafeReferencedPaths": sorted(set(unsafe_paths)),
        "confidence": _item_confidence(kind, runs, unsafe_paths, parse_error),
        "sources": {
            "workflow": str(workflow_file) if workflow_file else "",
            "statuses": [path for run in runs for path in run.get("files", []) if Path(path).name.startswith("status_")],
        },
    }


def _scan_workflow(root: Path, workflow_file: Path, stale_after_seconds: int) -> tuple[dict[str, Any], set[str]]:
    parse_error = False
    try:
        workflow = load_json(workflow_file)
    except Exception:
        parse_error = True
        workflow = {"workflowId": workflow_file.stem.removeprefix("workflow_"), "runs": {}}
    workflow_id = str(workflow.get("workflowId") or workflow_file.stem.removeprefix("workflow_"))
    runs_obj = workflow.get("runs") if isinstance(workflow.get("runs"), dict) else {}
    runs: list[dict[str, Any]] = []
    referenced_run_ids: set[str] = set()
    for run_id, workflow_run in sorted(runs_obj.items()):
        run_id_text = str(run_id)
        referenced_run_ids.add(run_id_text)
        run_dict = workflow_run if isinstance(workflow_run, dict) else {}
        runs.append(_run_summary(root, run_id_text, run_dict, stale_after_seconds))
    item = _aggregate_item(root, "workflow", workflow_id, workflow_file.resolve(), runs, set(), parse_error=parse_error)
    return item, referenced_run_ids


def _discover_run_ids(root: Path) -> set[str]:
    ids: set[str] = set()
    for path in root.glob("config_*.json"):
        ids.add(path.stem.removeprefix("config_"))
    for path in root.glob("status_*.json"):
        ids.add(path.stem.removeprefix("status_"))
    return ids


def _scan_artifact_root(root: Path, stale_after_seconds: int) -> list[dict[str, Any]]:
    root = root.resolve()
    if not root.exists() or not root.is_dir():
        return []
    items: list[dict[str, Any]] = []
    referenced: set[str] = set()
    for workflow_file in sorted(root.glob("workflow_*.json")):
        item, run_ids = _scan_workflow(root, workflow_file, stale_after_seconds)
        items.append(item)
        referenced.update(run_ids)
    for run_id in sorted(_discover_run_ids(root) - referenced):
        run = _run_summary(root, run_id, {}, stale_after_seconds)
        item = _aggregate_item(root, "orphan-run", run.get("workflowId") or "", None, [run], set())
        items.append(item)
    return items


def _user_artifact_roots() -> list[Path]:
    base = codex_home() / "codex_with_cc" / "claude-delegate"
    if not base.exists():
        return []
    return [path.resolve() for path in sorted(base.iterdir()) if path.is_dir()]


def _selected_roots(ns: argparse.Namespace) -> list[Path]:
    roots: list[Path] = []
    if ns.artifact_root:
        roots.extend(Path(value).expanduser().resolve() for value in ns.artifact_root)
    project_roots = [Path(value).expanduser().resolve() for value in (ns.project_root or [])]
    if not roots and not project_roots and not ns.all_projects:
        project_roots.append(repo_root())
    for project in project_roots:
        roots.append(project_artifact_root(project))
        roots.append(user_artifact_root(project))
    if ns.all_projects:
        roots.append(project_artifact_root(repo_root()))
        roots.extend(_user_artifact_roots())
    deduped: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        key = str(root.resolve())
        if key not in seen:
            seen.add(key)
            deduped.append(root.resolve())
    return deduped


def _parse_before(value: str | None) -> float | None:
    if not value:
        return None
    text = value.strip()
    if not text:
        return None
    if len(text) == 10 and text[4] == "-" and text[7] == "-":
        dt = datetime.fromisoformat(text).replace(tzinfo=timezone.utc)
    else:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def _cutoff_epoch(ns: argparse.Namespace, command: str) -> float | None:
    cutoffs: list[float] = []
    if ns.before:
        before = _parse_before(ns.before)
        if before is not None:
            cutoffs.append(before)
    if ns.older_than_days is not None:
        cutoffs.append(time.time() - float(ns.older_than_days) * 86400)
    if ns.older_than_hours is not None:
        cutoffs.append(time.time() - float(ns.older_than_hours) * 3600)
    if command in ("plan", "apply") and not cutoffs and not ns.ignore_age:
        cutoffs.append(time.time() - 30 * 86400)
    return min(cutoffs) if cutoffs else None


def _matches_any_filter(values: set[str], selected: list[str] | None) -> bool:
    if not selected:
        return True
    wanted = {value.lower() for value in selected}
    return any(value.lower() in wanted for value in values)


def _project_matches(item: dict[str, Any], filters: list[str] | None) -> bool:
    if not filters:
        return True
    haystack = " ".join(
        [
            str(item.get("artifactRoot") or ""),
            str(item.get("projectKey") or ""),
            str(item.get("workflowId") or ""),
            " ".join(item.get("runIds") or []),
        ]
    ).lower()
    return any(value.lower() in haystack for value in filters)


def _matches_selection(item: dict[str, Any], ns: argparse.Namespace) -> bool:
    if not _project_matches(item, ns.project_match):
        return False
    workflow_ids = {str(item.get("workflowId") or "")}
    if ns.workflow_id and not _matches_any_filter(workflow_ids, ns.workflow_id):
        return False
    run_ids = {str(value) for value in item.get("runIds") or []}
    if ns.run_id and not _matches_any_filter(run_ids, ns.run_id):
        return False
    states = set((item.get("stateCounts") or {}).keys())
    if ns.state and not _matches_any_filter(states, ns.state):
        return False
    results = set((item.get("results") or {}).keys())
    if ns.result and not _matches_any_filter(results, ns.result):
        return False
    roles = set((item.get("roles") or {}).keys())
    if ns.role and not _matches_any_filter(roles, ns.role):
        return False
    runner_types = set((item.get("runnerTypes") or {}).keys())
    if ns.runner_type and not _matches_any_filter(runner_types, ns.runner_type):
        return False
    return True


def _protection_reasons(item: dict[str, Any], ns: argparse.Namespace, cutoff: float | None) -> list[str]:
    reasons: list[str] = []
    states = set((item.get("stateCounts") or {}).keys())
    results = set((item.get("results") or {}).keys())
    if item.get("itemType") == "orphan-run" and not ns.include_orphans:
        reasons.append("orphan run artifacts require -IncludeOrphans")
    if states & ACTIVE_STATES and not ns.include_running:
        reasons.append("running or starting artifacts require -IncludeRunning")
    if states & FAILURE_STATES and not ns.include_failures:
        reasons.append("failure or interrupted artifacts require -IncludeFailures")
    if results & FAILURE_RESULTS and not ns.include_failures:
        reasons.append("non-success report results require -IncludeFailures")
    newest = item.get("newestActivityEpoch")
    if cutoff is not None and (newest is None or float(newest) > cutoff):
        reasons.append("newer than cleanup cutoff")
    if item.get("unsafeReferencedPaths"):
        reasons.append("referenced paths outside artifact root are never moved")
    if not item.get("files"):
        reasons.append("no movable files found")
    return reasons


def _annotate_item(item: dict[str, Any], ns: argparse.Namespace, command: str, cutoff: float | None) -> dict[str, Any]:
    matched = _matches_selection(item, ns)
    reasons = [] if matched else ["does not match selection filters"]
    if matched:
        reasons.extend(_protection_reasons(item, ns, cutoff))
    eligible = matched and not reasons
    action = "move-to-trash" if eligible else "keep"
    annotated = dict(item)
    annotated.update(
        {
            "matched": matched,
            "eligible": eligible,
            "plannedAction": action if command in ("plan", "apply") else "inspect",
            "protectionReasons": reasons,
            "cutoffEpoch": cutoff,
            "cutoffAt": _format_epoch(cutoff),
            "reversible": True,
            "mayOverrideVerifier": False,
        }
    )
    return annotated


def _scan_and_plan(ns: argparse.Namespace, command: str) -> dict[str, Any]:
    roots = _selected_roots(ns)
    cutoff = _cutoff_epoch(ns, command)
    scanned_items: list[dict[str, Any]] = []
    for root in roots:
        for item in _scan_artifact_root(root, ns.stale_after_seconds):
            scanned_items.append(_annotate_item(item, ns, command, cutoff))
    items = [item for item in scanned_items if item.get("matched")]
    if ns.limit is not None:
        items = items[: max(0, int(ns.limit))]
    eligible = [item for item in items if item.get("eligible")]
    protected = [item for item in items if item.get("matched") and not item.get("eligible")]
    return {
        "artifactSchema": ARTIFACT_SCHEMA_VERSION,
        "invocationContract": INVOCATION_CONTRACT,
        "cleanupType": "codex-with-cc-artifact-cleanup",
        "command": command,
        "status": "planned" if command != "list" else "listed",
        "selection": {
            "artifactRoots": [str(root) for root in roots],
            "projectMatch": ns.project_match or [],
            "workflowId": ns.workflow_id or [],
            "runId": ns.run_id or [],
            "state": ns.state or [],
            "result": ns.result or [],
            "role": ns.role or [],
            "runnerType": ns.runner_type or [],
            "includeFailures": bool(ns.include_failures),
            "includeRunning": bool(ns.include_running),
            "includeOrphans": bool(ns.include_orphans),
            "cutoffAt": _format_epoch(cutoff),
            "ignoreAge": bool(ns.ignore_age),
        },
        "items": items,
        "totals": {
            "scanned": len(scanned_items),
            "displayed": len(items),
            "matched": len([item for item in items if item.get("matched")]),
            "eligible": len(eligible),
            "protected": len(protected),
            "eligibleBytes": sum(int(item.get("sizeBytes") or 0) for item in eligible),
            "protectedBytes": sum(int(item.get("sizeBytes") or 0) for item in protected),
        },
        "dryRun": command != "apply",
        "trashRoot": str(_trash_root(ns).resolve()),
        "mayOverrideVerifier": False,
        "updatedAt": now_iso(),
    }


def _trash_root(ns: argparse.Namespace) -> Path:
    if ns.trash_root:
        return Path(ns.trash_root).expanduser().resolve()
    return (codex_home() / "codex_with_cc" / "cleanup-trash").resolve()


def _root_label(root: Path) -> str:
    return f"{root.name}-{_hash_text(str(root.resolve()))}"


def _move_file_to_trash(path: Path, artifact_root: Path, trash_run_root: Path) -> dict[str, Any]:
    relative = path.resolve().relative_to(artifact_root.resolve())
    destination = trash_run_root / _root_label(artifact_root) / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        destination = destination.with_name(f"{destination.name}.{_hash_text(str(time.time()))}")
    shutil.move(str(path), str(destination))
    return {
        "from": str(path),
        "to": str(destination),
        "sizeBytes": destination.stat().st_size if destination.exists() else 0,
    }


def _apply_plan(ns: argparse.Namespace, plan: dict[str, Any]) -> dict[str, Any]:
    if not ns.confirm_delete:
        raise DelegateError("ccclean apply requires -ConfirmDelete. Run ccclean plan first and inspect protected reasons.")
    stamp = datetime.now(timezone.utc).astimezone().strftime("%Y%m%d_%H%M%S")
    trash_run_root = _trash_root(ns) / stamp
    moved: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    eligible = [item for item in plan.get("items") or [] if item.get("eligible")]
    for item in eligible:
        root = Path(str(item["artifactRoot"])).resolve()
        for path_text in item.get("files") or []:
            path = Path(str(path_text)).resolve()
            if not path.exists():
                continue
            if not _path_inside(root, path):
                errors.append({"path": str(path), "error": "outside artifact root"})
                continue
            try:
                moved.append(_move_file_to_trash(path, root, trash_run_root))
            except Exception as exc:
                errors.append({"path": str(path), "error": str(exc)})
    manifest = dict(plan)
    manifest["status"] = "applied_with_errors" if errors else "applied"
    manifest["dryRun"] = False
    manifest["movedFiles"] = moved
    manifest["errors"] = errors
    manifest["trashRoot"] = str(trash_run_root)
    manifest["updatedAt"] = now_iso()
    trash_run_root.mkdir(parents=True, exist_ok=True)
    manifest_path = trash_run_root / "ccclean_manifest.json"
    write_json(manifest_path, manifest)
    manifest["manifestPath"] = str(manifest_path)
    for root_text in sorted({str(item.get("artifactRoot")) for item in eligible}):
        root = Path(root_text)
        if root.exists():
            audit_path = root / f"ccclean_{stamp}.json"
            write_json(audit_path, manifest)
            write_text(
                root / f"ccclean_{stamp}.md",
                "\n".join(
                    [
                        "# ccclean Cleanup Audit",
                        "",
                        f"Status: {manifest['status']}",
                        f"MovedFiles: {len(moved)}",
                        f"TrashRoot: {trash_run_root}",
                        f"Manifest: {manifest_path}",
                        "mayOverrideVerifier: false",
                        "",
                    ]
                ),
            )
    return manifest


def _render_table(report: dict[str, Any]) -> str:
    lines = [
        f"ccclean {report.get('command')} - {report.get('status')}",
        f"DryRun: {str(report.get('dryRun')).lower()}",
        f"TrashRoot: {report.get('trashRoot')}",
        "Totals: "
        + ", ".join(f"{key}={value}" for key, value in (report.get("totals") or {}).items()),
    ]
    for item in report.get("items") or []:
        state = ",".join(f"{key}:{value}" for key, value in sorted((item.get("stateCounts") or {}).items()))
        results = ",".join(f"{key}:{value}" for key, value in sorted((item.get("results") or {}).items()))
        reasons = "; ".join(item.get("protectionReasons") or [])
        lines.append(
            " - "
            + f"{item.get('plannedAction')} "
            + f"{item.get('itemType')} "
            + f"workflow={item.get('workflowId') or '-'} "
            + f"runs={','.join(item.get('runIds') or []) or '-'} "
            + f"state={state or '-'} "
            + f"result={results or '-'} "
            + f"ageSource={item.get('newestActivityAt') or '-'} "
            + f"bytes={item.get('sizeBytes')} "
            + f"confidence={item.get('confidence')}"
            + (f" protected=({reasons})" if reasons else "")
        )
    if report.get("manifestPath"):
        lines.append(f"Manifest: {report.get('manifestPath')}")
    return "\n".join(lines)


def run_ccclean(ns: argparse.Namespace) -> int:
    command = str(ns.ccclean_command)
    plan = _scan_and_plan(ns, command)
    result = _apply_plan(ns, plan) if command == "apply" else plan
    if ns.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(_render_table(result))
    if command == "apply" and result.get("errors"):
        return 1
    return 0
