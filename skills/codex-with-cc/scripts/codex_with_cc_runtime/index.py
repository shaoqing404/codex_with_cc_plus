from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .cleanup import _scan_artifact_root, _user_artifact_roots
from .common import ARTIFACT_SCHEMA_VERSION, INVOCATION_CONTRACT, DelegateError, now_iso
from .io_utils import load_json, write_json
from .paths import project_artifact_root, repo_root, user_artifact_root


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = load_json(path)
    except Exception as exc:
        return {"_parseError": str(exc)}
    return data if isinstance(data, dict) else {"_parseError": "not an object"}


def _stream_model(path: Path) -> str:
    if not path.exists():
        return ""
    model = ""
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            if isinstance(record, dict):
                if record.get("model"):
                    model = str(record.get("model"))
                message = record.get("message")
                if isinstance(message, dict) and message.get("model"):
                    model = str(message.get("model"))
    except Exception:
        return model
    return model


def _probable_project_root(artifact_root: Path) -> str:
    parts = artifact_root.parts
    suffix = (".codex", "codex_with_cc", "claude-delegate")
    if len(parts) >= 3 and tuple(parts[-3:]) == suffix:
        return str(Path(*parts[:-3]))
    return ""


def _discover_project_artifact_roots() -> list[Path]:
    roots: list[Path] = []
    current = repo_root()
    roots.append(project_artifact_root(current))
    roots.append(user_artifact_root(current))
    roots.extend(_user_artifact_roots())
    candidate_bases = [
        current.parent,
        Path.home() / "Developer",
        Path.home() / "Developer" / "element_workspace",
        Path.home() / "Projects",
        Path.home() / "Code",
    ]
    seen_bases: set[str] = set()
    for base in candidate_bases:
        try:
            base = base.expanduser().resolve()
        except Exception:
            continue
        if str(base) in seen_bases or not base.exists() or not base.is_dir():
            continue
        seen_bases.add(str(base))
        for depth_path in [base, *list(base.glob("*")), *list(base.glob("*/*"))]:
            artifact = depth_path / ".codex" / "codex_with_cc" / "claude-delegate"
            if artifact.exists() and artifact.is_dir():
                roots.append(artifact.resolve())
    return _dedupe_paths(roots)


def _selected_roots(ns: argparse.Namespace) -> list[Path]:
    roots: list[Path] = []
    for value in getattr(ns, "artifact_root", None) or []:
        roots.append(Path(value).expanduser().resolve())
    for value in getattr(ns, "project_root", None) or []:
        project = Path(value).expanduser().resolve()
        roots.append(project_artifact_root(project))
        roots.append(user_artifact_root(project))
    if getattr(ns, "all_projects", False):
        roots.extend(_discover_project_artifact_roots())
    if not roots:
        roots.extend(_discover_project_artifact_roots())
    return _dedupe_paths(roots)


def _dedupe_paths(paths: list[Path]) -> list[Path]:
    out: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = str(path.resolve())
        if key not in seen:
            seen.add(key)
            out.append(path.resolve())
    return out


def _matches_project(item: dict[str, Any], filters: list[str] | None) -> bool:
    if not filters:
        return True
    haystack = " ".join(
        [
            str(item.get("artifactRoot") or ""),
            str(item.get("projectKey") or ""),
            str(item.get("probableProjectRoot") or ""),
            str(item.get("workflowId") or ""),
            " ".join(item.get("runIds") or []),
        ]
    ).lower()
    return any(value.lower() in haystack for value in filters)


def _path_from_run(root: Path, run_id: str, run: dict[str, Any], key: str, prefix: str, ext: str) -> Path:
    explicit = run.get(key)
    if explicit:
        path = Path(str(explicit))
        if path.is_absolute():
            return path.resolve()
        return (root / path.name).resolve()
    return (root / f"{prefix}_{run_id}.{ext}").resolve()


def _enrich_run(root: Path, run: dict[str, Any]) -> dict[str, Any]:
    run_id = str(run.get("runId") or "")
    config_path = _path_from_run(root, run_id, run, "configPath", "config", "json")
    status_path = _path_from_run(root, run_id, run, "statusPath", "status", "json")
    stream_path = _path_from_run(root, run_id, run, "rawStreamPath", "stream", "jsonl")
    config = _read_json(config_path)
    status = _read_json(status_path)
    failure_layer = str(status.get("failureLayer") or config.get("failureLayer") or "")
    failure_disposition = str(status.get("failureDisposition") or config.get("failureDisposition") or "")
    execution_layer_failure = bool(failure_layer) or failure_disposition == "NEED_HUMAN_INTERVENTION"
    enriched = dict(run)
    enriched.update(
        {
            "configPath": str(config_path),
            "statusPath": str(status_path),
            "rawStreamPath": str(stream_path),
            "requestedModel": str(config.get("model") or ""),
            "streamedModel": _stream_model(stream_path),
            "permissionMode": str(config.get("permissionMode") or "acceptEdits"),
            "bypassPermissions": bool(config.get("bypassPermissions")),
            "sessionMode": str(config.get("sessionMode") or ""),
            "sessionKey": str(config.get("sessionKey") or ""),
            "failureLayer": failure_layer,
            "failureDisposition": failure_disposition,
            "failureSummary": str(status.get("failureSummary") or config.get("failureSummary") or ""),
            "executionLayerFailure": execution_layer_failure,
            "workerOutcome": str(status.get("workerOutcome") or config.get("workerOutcome") or ""),
            "businessAcceptance": str(status.get("businessAcceptance") or config.get("businessAcceptance") or ""),
            "businessFilesChanged": bool(status.get("businessFilesChanged") or config.get("businessFilesChanged")),
            "safeToRetrySameTaskFile": bool(status.get("safeToRetrySameTaskFile") or config.get("safeToRetrySameTaskFile")),
            "mayOverrideImplementation": bool(status.get("mayOverrideImplementation") or config.get("mayOverrideImplementation")),
            "tests": config.get("tests") if isinstance(config.get("tests"), list) else [],
            "provenance": {
                "config": str(config_path) if config_path.exists() else "",
                "status": str(status_path) if status_path.exists() else "",
                "stream": str(stream_path) if stream_path.exists() else "",
            },
        }
    )
    return enriched


def _enrich_item(item: dict[str, Any]) -> dict[str, Any]:
    root = Path(str(item.get("artifactRoot") or "")).resolve()
    enriched = dict(item)
    run_summaries = [_enrich_run(root, dict(run)) for run in item.get("runSummaries") or []]
    enriched["runSummaries"] = run_summaries
    enriched["probableProjectRoot"] = _probable_project_root(root)
    enriched["provenance"] = {
        "artifactRoot": str(root),
        "workflow": item.get("workflowPath") or "",
        "sources": item.get("sources") or {},
    }
    enriched["modelSummary"] = {
        "requested": sorted({run.get("requestedModel") for run in run_summaries if run.get("requestedModel")}),
        "streamed": sorted({run.get("streamedModel") for run in run_summaries if run.get("streamedModel")}),
    }
    enriched["permissionSummary"] = {
        "permissionModes": sorted({run.get("permissionMode") for run in run_summaries if run.get("permissionMode")}),
        "bypassPermissions": any(bool(run.get("bypassPermissions")) for run in run_summaries),
    }
    enriched["mayOverrideVerifier"] = False
    return enriched


def build_index(ns: argparse.Namespace) -> dict[str, Any]:
    roots = _selected_roots(ns)
    records: list[dict[str, Any]] = []
    for root in roots:
        for item in _scan_artifact_root(root, int(ns.stale_after_seconds)):
            enriched = _enrich_item(item)
            if _matches_project(enriched, getattr(ns, "project_match", None)):
                records.append(enriched)
    records.sort(key=lambda item: str(item.get("newestActivityAt") or ""), reverse=True)
    state_counts: dict[str, int] = {}
    confidence_counts: dict[str, int] = {}
    for item in records:
        confidence = str(item.get("confidence") or "unknown")
        confidence_counts[confidence] = confidence_counts.get(confidence, 0) + 1
        for state, count in (item.get("stateCounts") or {}).items():
            state_counts[str(state)] = state_counts.get(str(state), 0) + int(count)
    return {
        "artifactSchema": ARTIFACT_SCHEMA_VERSION,
        "invocationContract": INVOCATION_CONTRACT,
        "indexType": "codex-with-cc-machine-index",
        "status": "built",
        "selection": {
            "artifactRoots": [str(root) for root in roots],
            "projectMatch": getattr(ns, "project_match", None) or [],
            "allProjects": bool(getattr(ns, "all_projects", False)),
            "staleAfterSeconds": int(ns.stale_after_seconds),
        },
        "records": records,
        "totals": {
            "rootsScanned": len(roots),
            "records": len(records),
            "workflows": len([item for item in records if item.get("itemType") == "workflow"]),
            "orphanRuns": len([item for item in records if item.get("itemType") == "orphan-run"]),
            "stateCounts": state_counts,
            "confidenceCounts": confidence_counts,
        },
        "mayOverrideVerifier": False,
        "updatedAt": now_iso(),
    }


def _render_list(index: dict[str, Any]) -> str:
    lines = [
        "ccindex list",
        "Totals: " + ", ".join(f"{key}={value}" for key, value in (index.get("totals") or {}).items() if key != "stateCounts"),
    ]
    for item in index.get("records") or []:
        states = ",".join(f"{key}:{value}" for key, value in sorted((item.get("stateCounts") or {}).items()))
        models = ",".join((item.get("modelSummary") or {}).get("requested") or [])
        perms = ",".join((item.get("permissionSummary") or {}).get("permissionModes") or [])
        lines.append(
            f"- {item.get('itemType')} workflow={item.get('workflowId') or '-'} "
            f"runs={','.join(item.get('runIds') or []) or '-'} "
            f"project={item.get('probableProjectRoot') or item.get('projectKey')} "
            f"state={states or '-'} model={models or '-'} permission={perms or '-'} "
            f"confidence={item.get('confidence')}"
        )
    return "\n".join(lines)


def _render_show(record: dict[str, Any] | None, workflow_id: str) -> str:
    if not record:
        return f"Workflow not found: {workflow_id}"
    lines = [
        f"Workflow: {record.get('workflowId') or '-'}",
        f"ArtifactRoot: {record.get('artifactRoot')}",
        f"ProjectRoot: {record.get('probableProjectRoot') or '-'}",
        f"Confidence: {record.get('confidence')}",
        f"StateCounts: {record.get('stateCounts')}",
        "Runs:",
    ]
    for run in record.get("runSummaries") or []:
        lines.append(
            f"- {run.get('runId')} role={run.get('role')} state={run.get('state')} "
            f"result={run.get('finalResult') or '-'} model={run.get('requestedModel') or '-'} "
            f"streamed={run.get('streamedModel') or '-'} permission={run.get('permissionMode')}"
        )
    return "\n".join(lines)


def _write_output(path_value: str | None, data: dict[str, Any]) -> str:
    if not path_value:
        return ""
    path = Path(path_value).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, data)
    return str(path)


def run_ccindex(ns: argparse.Namespace) -> int:
    command = str(ns.ccindex_command)
    index = build_index(ns)
    if command == "show":
        workflow_id = str(ns.workflow_id)
        record = next((item for item in index["records"] if item.get("workflowId") == workflow_id), None)
        if ns.json:
            print(json.dumps(record or {"status": "not_found", "workflowId": workflow_id}, ensure_ascii=False, indent=2))
        else:
            print(_render_show(record, workflow_id))
        return 0 if record else 1
    if command == "export":
        if not ns.output:
            raise DelegateError("ccindex export requires -Output <path>.")
        index["outputPath"] = _write_output(ns.output, index)
    elif command == "build" and ns.output:
        index["outputPath"] = _write_output(ns.output, index)
    if ns.json:
        print(json.dumps(index, ensure_ascii=False, indent=2))
    else:
        print(_render_list(index))
    return 0
