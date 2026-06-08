from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .claude_cli import PERMISSION_MODES
from .common import ARTIFACT_SCHEMA_VERSION, INVOCATION_CONTRACT, DelegateError, now_iso
from .doctor import build_doctor_report, render_doctor_text
from .io_utils import load_json, write_json, write_text
from .paths import project_artifact_root, repo_root


SAFE_ENV_KEYS = (
    "ANTHROPIC_BASE_URL",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL_NAME",
    "ANTHROPIC_DEFAULT_OPUS_MODEL",
    "ANTHROPIC_DEFAULT_OPUS_MODEL_NAME",
    "ANTHROPIC_DEFAULT_SONNET_MODEL",
    "ANTHROPIC_DEFAULT_SONNET_MODEL_NAME",
    "API_TIMEOUT_MS",
    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC",
    "CLAUDE_CODE_EFFORT_LEVEL",
    "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS",
    "ENABLE_TOOL_SEARCH",
)
SECRET_ENV_KEYS = ("ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "DEEPSEEK_API_KEY")
MODEL_ENV_KEYS = {
    "opus": ("ANTHROPIC_DEFAULT_OPUS_MODEL", "ANTHROPIC_DEFAULT_OPUS_MODEL_NAME"),
    "sonnet": ("ANTHROPIC_DEFAULT_SONNET_MODEL", "ANTHROPIC_DEFAULT_SONNET_MODEL_NAME"),
    "haiku": ("ANTHROPIC_DEFAULT_HAIKU_MODEL", "ANTHROPIC_DEFAULT_HAIKU_MODEL_NAME"),
}


def _settings_path(ns: argparse.Namespace | None = None) -> Path:
    explicit = getattr(ns, "claude_settings_path", None) if ns is not None else None
    if explicit:
        return Path(str(explicit)).expanduser().resolve()
    return (Path.home() / ".claude" / "settings.json").resolve()


def _artifact_root(ns: argparse.Namespace) -> Path:
    value = getattr(ns, "artifact_root", None)
    return Path(value).expanduser().resolve() if value else project_artifact_root(repo_root())


def _load_settings(path: Path) -> tuple[dict[str, Any], str]:
    if not path.exists():
        return {}, "missing"
    try:
        data = load_json(path)
    except Exception as exc:
        return {"_parseError": str(exc)}, "parse_error"
    return data if isinstance(data, dict) else {"_parseError": "settings root is not an object"}, "ok"


def _find_package_version(command_path: str | None, package_name: str) -> dict[str, Any]:
    if not command_path:
        return {"packageName": package_name, "version": "", "packagePath": "", "confidence": "low"}
    resolved = Path(command_path).expanduser().resolve()
    for parent in [resolved.parent, *resolved.parents]:
        package_path = parent / "package.json"
        if not package_path.exists():
            continue
        try:
            package = json.loads(package_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if package.get("name") == package_name:
            return {
                "packageName": package_name,
                "version": str(package.get("version") or ""),
                "packagePath": str(package_path),
                "confidence": "high",
            }
    return {"packageName": package_name, "version": "", "packagePath": "", "confidence": "medium"}


def _redacted_settings(data: dict[str, Any], path: Path, load_status: str) -> dict[str, Any]:
    env = data.get("env") if isinstance(data.get("env"), dict) else {}
    safe_env = {key: env.get(key) for key in SAFE_ENV_KEYS if key in env}
    secret_presence = {key: key in env and bool(env.get(key)) for key in SECRET_ENV_KEYS}
    return {
        "path": str(path),
        "exists": path.exists(),
        "loadStatus": load_status,
        "model": data.get("model") if load_status == "ok" else None,
        "safeEnv": safe_env,
        "secretPresence": secret_presence,
        "hasToken": bool(secret_presence.get("ANTHROPIC_AUTH_TOKEN")),
        "provenance": {"source": str(path), "redacted": True},
    }


def build_runtime_status(ns: argparse.Namespace | None = None) -> dict[str, Any]:
    settings_path = _settings_path(ns)
    settings, load_status = _load_settings(settings_path)
    claude_path = shutil.which("claude")
    openclaw_path = shutil.which("openclaw")
    ccwitch_path = shutil.which("ccwitch")
    claude_package = _find_package_version(claude_path, "@anthropic-ai/claude-code")
    openclaw_package = _find_package_version(openclaw_path, "openclaw")
    checks = []
    checks.append({"name": "claude_cli", "status": "pass" if claude_path else "fail", "path": claude_path or ""})
    checks.append({"name": "claude_settings", "status": "pass" if load_status == "ok" else "warn", "path": str(settings_path), "loadStatus": load_status})
    checks.append({"name": "openclaw", "status": "pass" if openclaw_path else "warn", "path": openclaw_path or ""})
    checks.append({"name": "ccwitch", "status": "pass" if ccwitch_path else "warn", "path": ccwitch_path or ""})
    confidence = "high" if claude_path and load_status == "ok" else "medium" if claude_path or load_status == "ok" else "low"
    return {
        "artifactSchema": ARTIFACT_SCHEMA_VERSION,
        "invocationContract": INVOCATION_CONTRACT,
        "runtimeType": "codex-with-cc-runtime-status",
        "status": "pass" if claude_path and load_status == "ok" else "warn",
        "confidence": confidence,
        "claudeCli": {"path": claude_path or "", **claude_package},
        "openclaw": {"path": openclaw_path or "", **openclaw_package},
        "ccwitch": {"path": ccwitch_path or "", "available": bool(ccwitch_path)},
        "claudeSettings": _redacted_settings(settings, settings_path, load_status),
        "runnerDefaults": {
            "model": "sonnet",
            "permissionMode": "acceptEdits",
            "supportedPermissionModes": list(PERMISSION_MODES),
            "bypassPermissionsRequiresExplicitFlag": True,
        },
        "toolkitAudit": {
            "claudeCodeCliPackageVersion": claude_package.get("version") or "",
            "openclawVersion": openclaw_package.get("version") or "",
            "minimaxDetected": "MiniMax" in json.dumps(_redacted_settings(settings, settings_path, load_status), ensure_ascii=False),
            "directClaudeCliExecution": "forbidden-outside-delegate-runner",
        },
        "checks": checks,
        "updatedAt": now_iso(),
    }


def _requested_settings(ns: argparse.Namespace) -> dict[str, Any]:
    requested: dict[str, Any] = {}
    if ns.model:
        requested["model"] = ns.model
    requested_env: dict[str, str] = {}
    if ns.base_url:
        requested_env["ANTHROPIC_BASE_URL"] = str(ns.base_url)
    if ns.effort_level:
        requested_env["CLAUDE_CODE_EFFORT_LEVEL"] = str(ns.effort_level)
    if ns.api_timeout_ms:
        requested_env["API_TIMEOUT_MS"] = str(ns.api_timeout_ms)
    for model_key, env_keys in MODEL_ENV_KEYS.items():
        model_attr = getattr(ns, f"{model_key}_model", None)
        name_attr = getattr(ns, f"{model_key}_model_name", None)
        if model_attr:
            requested_env[env_keys[0]] = str(model_attr)
        if name_attr:
            requested_env[env_keys[1]] = str(name_attr)
    if requested_env:
        requested["env"] = requested_env
    return requested


def _change(key: str, before: Any, after: Any, target: str) -> dict[str, Any]:
    return {
        "target": target,
        "key": key,
        "before": before,
        "after": after,
        "action": "no-op" if before == after else "set" if before is None else "update",
        "secret": False,
    }


def build_switch_plan(ns: argparse.Namespace) -> dict[str, Any]:
    status = build_runtime_status(ns)
    settings_path = _settings_path(ns)
    settings, load_status = _load_settings(settings_path)
    if load_status == "missing":
        settings = {}
    if "_parseError" in settings:
        raise DelegateError(f"Cannot plan runtime switch because Claude settings could not be parsed: {settings.get('_parseError')}")
    requested = _requested_settings(ns)
    changes: list[dict[str, Any]] = []
    if "model" in requested:
        changes.append(_change("model", settings.get("model"), requested["model"], "claude_settings"))
    current_env = settings.get("env") if isinstance(settings.get("env"), dict) else {}
    for key, after in sorted((requested.get("env") or {}).items()):
        if key not in SAFE_ENV_KEYS:
            raise DelegateError(f"Unsupported runtime setting key: {key}")
        changes.append(_change(key, current_env.get(key), after, "claude_settings.env"))
    permission_mode = getattr(ns, "permission_mode", "acceptEdits") or "acceptEdits"
    return {
        "artifactSchema": ARTIFACT_SCHEMA_VERSION,
        "invocationContract": INVOCATION_CONTRACT,
        "runtimeChangeType": "codex-with-cc-runtime-switch",
        "status": "no_change" if all(item["action"] == "no-op" for item in changes) else "planned",
        "dryRun": True,
        "settingsPath": str(settings_path),
        "requested": {
            "model": requested.get("model"),
            "permissionMode": permission_mode,
            "env": requested.get("env") or {},
        },
        "current": status["claudeSettings"],
        "changes": changes,
        "nextDelegateArgs": {
            "Model": requested.get("model") or status["claudeSettings"].get("model") or "sonnet",
            "PermissionMode": permission_mode,
            "permissionModeAppliedToSettings": False,
        },
        "supportedPermissionModes": list(PERMISSION_MODES),
        "requiresConfirmation": True,
        "reversible": True,
        "mayOverrideVerifier": False,
        "updatedAt": now_iso(),
    }


def _runtime_artifact_paths(ns: argparse.Namespace) -> tuple[Path, Path]:
    stamp = datetime.now(timezone.utc).astimezone().strftime("%Y%m%d_%H%M%S")
    root = _artifact_root(ns)
    root.mkdir(parents=True, exist_ok=True)
    return root / f"runtime_{stamp}.json", root / f"runtime_{stamp}.md"


def _apply_switch(ns: argparse.Namespace) -> dict[str, Any]:
    if not ns.confirm_runtime_change:
        raise DelegateError("ccruntime apply-switch requires -ConfirmRuntimeChange. Run ccruntime plan-switch first.")
    plan = build_switch_plan(ns)
    settings_path = _settings_path(ns)
    settings, load_status = _load_settings(settings_path)
    if load_status == "missing":
        settings = {}
    settings.setdefault("env", {})
    if not isinstance(settings.get("env"), dict):
        settings["env"] = {}
    changed = [item for item in plan["changes"] if item["action"] != "no-op"]
    backup_path = ""
    if changed and settings_path.exists():
        stamp = datetime.now(timezone.utc).astimezone().strftime("%Y%m%d_%H%M%S")
        backup_dir = settings_path.parent / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup = backup_dir / f"settings.json.codex-with-cc.{stamp}.bak"
        shutil.copy2(settings_path, backup)
        backup_path = str(backup)
    for item in changed:
        if item["target"] == "claude_settings":
            settings[item["key"]] = item["after"]
        elif item["target"] == "claude_settings.env":
            settings["env"][item["key"]] = item["after"]
    if changed:
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        settings_path.write_text(json.dumps(settings, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    artifact_json, artifact_md = _runtime_artifact_paths(ns)
    result = dict(plan)
    result.update(
        {
            "status": "applied" if changed else "no_change",
            "dryRun": False,
            "appliedChanges": changed,
            "backupPath": backup_path,
            "artifactPath": str(artifact_json),
            "reportPath": str(artifact_md),
            "rollback": "restore backupPath over settingsPath" if backup_path else "no rollback needed; no settings changed",
            "updatedAt": now_iso(),
        }
    )
    write_json(artifact_json, result)
    write_text(
        artifact_md,
        "\n".join(
            [
                "# ccruntime Runtime Change Audit",
                "",
                f"Status: {result['status']}",
                f"SettingsPath: {settings_path}",
                f"BackupPath: {backup_path or '-'}",
                f"AppliedChanges: {len(changed)}",
                "PermissionModeAppliedToSettings: false",
                "mayOverrideVerifier: false",
                "",
            ]
        ),
    )
    return result


def render_runtime_text(report: dict[str, Any]) -> str:
    if report.get("runtimeChangeType"):
        lines = [
            f"RuntimeSwitch: {report.get('status')}",
            f"SettingsPath: {report.get('settingsPath')}",
            f"DryRun: {str(report.get('dryRun')).lower()}",
            f"NextDelegateArgs: -Model {report.get('nextDelegateArgs', {}).get('Model')} -PermissionMode {report.get('nextDelegateArgs', {}).get('PermissionMode')}",
            "Changes:",
        ]
        for item in report.get("changes") or []:
            lines.append(f"- {item.get('target')}.{item.get('key')}: {item.get('action')} {item.get('before')!r} -> {item.get('after')!r}")
        if report.get("artifactPath"):
            lines.append(f"Artifact: {report.get('artifactPath')}")
        return "\n".join(lines)
    lines = [
        f"RuntimeStatus: {report.get('status')}",
        f"Confidence: {report.get('confidence')}",
        f"ClaudeCli: {report.get('claudeCli', {}).get('path') or '-'} version={report.get('claudeCli', {}).get('version') or '-'}",
        f"OpenClaw: {report.get('openclaw', {}).get('path') or '-'} version={report.get('openclaw', {}).get('version') or '-'}",
        f"Ccwitch: {report.get('ccwitch', {}).get('path') or '-'}",
        f"ClaudeSettings: {report.get('claudeSettings', {}).get('path')} model={report.get('claudeSettings', {}).get('model')}",
        f"RunnerDefault: -Model {report.get('runnerDefaults', {}).get('model')} -PermissionMode {report.get('runnerDefaults', {}).get('permissionMode')}",
    ]
    return "\n".join(lines)


def run_ccruntime(ns: argparse.Namespace) -> int:
    command = str(ns.ccruntime_command)
    if command == "status":
        report = build_runtime_status(ns)
    elif command == "doctor":
        doctor_report = build_doctor_report(ns)
        report = {**doctor_report, "runtimeStatus": build_runtime_status(ns)}
        if not ns.json:
            print(render_doctor_text(doctor_report))
            print("")
            print(render_runtime_text(report["runtimeStatus"]))
            return 0 if doctor_report["safeToDispatch"] else 1
    elif command == "plan-switch":
        report = build_switch_plan(ns)
    elif command == "apply-switch":
        report = _apply_switch(ns)
    else:
        raise DelegateError(f"Unknown ccruntime command: {command}")
    if getattr(ns, "json", False):
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_runtime_text(report))
    return 0
