from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from .common import CHILD_MARKER_NAME, CHILD_MARKER_VALUE, INVOCATION_CONTRACT, now_iso
from .io_utils import test_path_writable
from .paths import project_artifact_root, repo_root, workflow_root


def _check(name: str, status: str, message: str, **extra: Any) -> dict[str, Any]:
    return {"name": name, "status": status, "message": message, **extra}


def _status_from_checks(checks: list[dict[str, Any]]) -> str:
    if any(item.get("status") == "fail" for item in checks):
        return "fail"
    if any(item.get("status") == "warn" for item in checks):
        return "warn"
    return "pass"


def _artifact_root(ns: argparse.Namespace) -> Path:
    return Path(ns.artifact_root).resolve() if ns.artifact_root else project_artifact_root(repo_root())


def build_doctor_report(ns: argparse.Namespace) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    root = repo_root()
    artifact_root = _artifact_root(ns)
    workflow = workflow_root()

    checks.append(_check("python_runtime", "pass", f"Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}", executable=sys.executable))

    if workflow.exists() and (workflow / "CODEX_WITH_CC.md").exists():
        checks.append(_check("workflow_contract", "pass", "Workflow contract is available.", path=str(workflow / "CODEX_WITH_CC.md")))
    else:
        checks.append(_check("workflow_contract", "fail", "Workflow contract is missing.", path=str(workflow / "CODEX_WITH_CC.md")))

    try:
        artifact_root.mkdir(parents=True, exist_ok=True)
        test_path_writable(artifact_root / ".doctor_write_probe")
        checks.append(_check("artifact_root_writable", "pass", "Artifact root is writable.", path=str(artifact_root)))
    except Exception as exc:
        checks.append(_check("artifact_root_writable", "fail", f"Artifact root is not writable: {exc}", path=str(artifact_root)))

    child_marker = f"{CHILD_MARKER_NAME}={CHILD_MARKER_VALUE}"
    checks.append(_check("child_thread_marker_contract", "pass", f"Delegate runners require {child_marker}.", markerName=CHILD_MARKER_NAME, markerValue=CHILD_MARKER_VALUE))

    hook_path = workflow.parent.parent / "hooks" / "subagent-gate-hook.mjs"
    if hook_path.exists():
        checks.append(_check("hook_contract", "pass", "Platform hook script is available.", path=str(hook_path)))
    else:
        checks.append(_check("hook_contract", "warn", "Platform hook script was not found beside this workflow.", path=str(hook_path)))

    cli_path = shutil.which("claude")
    if cli_path:
        checks.append(_check("claude_cli_available", "pass", "Claude Code CLI is on PATH.", path=cli_path))
    else:
        checks.append(_check("claude_cli_available", "fail", "Claude Code CLI is not on PATH. Implementation delegates cannot start."))

    if ns.claude_smoke:
        if not cli_path:
            checks.append(_check("claude_cli_smoke", "fail", "Skipped smoke probe because Claude Code CLI is unavailable."))
        else:
            try:
                result = subprocess.run(
                    [cli_path, "--version"],
                    cwd=str(root),
                    capture_output=True,
                    text=True,
                    timeout=max(1, int(ns.timeout_seconds)),
                )
                status = "pass" if result.returncode == 0 else "fail"
                checks.append(
                    _check(
                        "claude_cli_smoke",
                        status,
                        "Claude CLI --version completed." if status == "pass" else "Claude CLI --version failed.",
                        exitCode=result.returncode,
                        stdout=result.stdout.strip()[:400],
                        stderr=result.stderr.strip()[:400],
                    )
                )
            except Exception as exc:
                checks.append(_check("claude_cli_smoke", "fail", f"Claude CLI smoke probe failed: {exc}"))
    else:
        checks.append(_check("claude_cli_smoke", "warn", "Claude CLI smoke probe not run. Pass -ClaudeSmoke to run a local no-model CLI probe."))

    overall = _status_from_checks(checks)
    safe_to_dispatch = overall == "pass" or (overall == "warn" and bool(cli_path))
    if not safe_to_dispatch:
        action = "fix_local_environment_before_dispatch"
    elif overall == "warn":
        action = "dispatch_allowed_but_review_warnings"
    else:
        action = "dispatch_allowed"

    return {
        "invocationContract": INVOCATION_CONTRACT,
        "doctorType": "codex-with-cc-preflight",
        "status": overall,
        "safeToDispatch": safe_to_dispatch,
        "recommendedAction": action,
        "repoRoot": str(root),
        "artifactRoot": str(artifact_root),
        "checks": checks,
        "updatedAt": now_iso(),
    }


def render_doctor_text(report: dict[str, Any]) -> str:
    lines = [
        f"DoctorStatus: {report.get('status')}",
        f"SafeToDispatch: {str(report.get('safeToDispatch')).lower()}",
        f"RecommendedAction: {report.get('recommendedAction')}",
        f"ArtifactRoot: {report.get('artifactRoot')}",
        "Checks:",
    ]
    for check in report.get("checks") or []:
        lines.append(f"- {check.get('name')}: {check.get('status')} - {check.get('message')}")
    return "\n".join(lines)


def run_doctor(ns: argparse.Namespace) -> int:
    report = build_doctor_report(ns)
    if ns.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_doctor_text(report))
    return 0 if report["safeToDispatch"] else 1
