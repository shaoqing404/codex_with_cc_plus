from __future__ import annotations

import argparse
import json
import plistlib
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
CCSWITCH_CLI_NAMES = ("ccwitch", "ccswitch", "cc-switch")
CCSWITCH_SECRET_HINTS = ("token", "secret", "password", "api_key", "apikey", "auth", "cookie", "session")
CCSWITCH_STATE_FILES = (
    "config.json",
    "settings.json",
    "state.json",
    "current.json",
    "profile.json",
)
MAX_CCSWITCH_STATE_BYTES = 128 * 1024


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


def _redact_ccswitch_value(key: str, value: Any) -> Any:
    lowered = key.lower()
    if any(hint in lowered for hint in CCSWITCH_SECRET_HINTS):
        return {"present": bool(value), "redacted": True}
    if isinstance(value, bytes):
        return {"present": bool(value), "redacted": True, "type": "bytes", "length": len(value)}
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(child_key): _redact_ccswitch_value(str(child_key), child_value) for child_key, child_value in value.items()}
    if isinstance(value, list):
        return [_redact_ccswitch_value(key, item) for item in value[:25]]
    if isinstance(value, str) and len(value) > 500:
        return f"{value[:500]}...<truncated>"
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return str(value)


def _load_ccswitch_json(path: Path) -> tuple[Any, str]:
    try:
        if path.stat().st_size > MAX_CCSWITCH_STATE_BYTES:
            return None, "skipped_too_large"
        return json.loads(path.read_text(encoding="utf-8")), "ok"
    except Exception as exc:
        return {"error": str(exc)}, "parse_error"


def _load_ccswitch_plist(path: Path) -> tuple[Any, str]:
    try:
        if path.stat().st_size > MAX_CCSWITCH_STATE_BYTES:
            return None, "skipped_too_large"
        with path.open("rb") as handle:
            return plistlib.load(handle), "ok"
    except Exception as exc:
        return {"error": str(exc)}, "parse_error"


def _ccswitch_path_probe(path: Path, kind: str) -> dict[str, Any]:
    exists = path.exists()
    probe: dict[str, Any] = {
        "kind": kind,
        "path": str(path),
        "exists": exists,
        "loadStatus": "missing",
        "confidence": "low",
        "provenance": {"source": str(path), "redacted": True},
    }
    if not exists:
        return probe
    if path.is_dir():
        names: list[str] = []
        try:
            names = sorted(item.name for item in path.iterdir())[:25]
        except Exception as exc:
            probe.update({"loadStatus": "list_error", "error": str(exc), "confidence": "medium"})
            return probe
        probe.update({"loadStatus": "directory", "entries": names, "confidence": "medium"})
        metadata: dict[str, Any] = {}
        for filename in CCSWITCH_STATE_FILES:
            candidate = path / filename
            if not candidate.exists() or not candidate.is_file():
                continue
            loaded, load_status = _load_ccswitch_json(candidate)
            metadata[filename] = {
                "path": str(candidate),
                "loadStatus": load_status,
                "value": _redact_ccswitch_value(filename, loaded) if load_status == "ok" else loaded,
                "provenance": {"source": str(candidate), "redacted": True},
            }
        if metadata:
            probe["metadata"] = metadata
            probe["confidence"] = "high"
        return probe
    if path.suffix == ".plist":
        loaded, load_status = _load_ccswitch_plist(path)
    elif path.suffix == ".json":
        loaded, load_status = _load_ccswitch_json(path)
    else:
        loaded, load_status = None, "file_present_unread"
    probe.update(
        {
            "loadStatus": load_status,
            "value": _redact_ccswitch_value(path.name, loaded) if load_status == "ok" else loaded,
            "confidence": "high" if load_status == "ok" else "medium",
        }
    )
    return probe


def _discover_ccswitch_provider() -> dict[str, Any]:
    cli_candidates = [{"name": name, "path": shutil.which(name) or ""} for name in CCSWITCH_CLI_NAMES]
    available_cli = next((item for item in cli_candidates if item["path"]), None)
    home = Path.home()
    state_paths = [
        _ccswitch_path_probe(home / ".cc-switch", "home_state"),
        _ccswitch_path_probe(home / "Library" / "Application Support" / "com.ccswitch.desktop", "desktop_app_support"),
        _ccswitch_path_probe(home / "Library" / "Preferences" / "com.ccswitch.desktop.plist", "desktop_preferences"),
    ]
    state_found = any(item.get("exists") for item in state_paths)
    load_status = "cli_available" if available_cli else "desktop_state_found" if state_found else "not_found"
    confidence = "high" if available_cli and state_found else "medium" if available_cli or state_found else "low"
    return {
        "provider": "cc-switch",
        "available": bool(available_cli),
        "path": str(available_cli.get("path")) if available_cli else "",
        "cliCandidates": cli_candidates,
        "desktopStateAvailable": state_found,
        "desktopState": state_paths,
        "loadStatus": load_status,
        "confidence": confidence,
        "mutability": "read_only",
        "mayRepairRuntime": False,
        "provenance": {
            "cliNames": list(CCSWITCH_CLI_NAMES),
            "statePaths": [item["path"] for item in state_paths],
            "redacted": True,
        },
    }


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
    ccswitch_provider = _discover_ccswitch_provider()
    ccwitch_path = ccswitch_provider.get("path") or ""
    claude_package = _find_package_version(claude_path, "@anthropic-ai/claude-code")
    openclaw_package = _find_package_version(openclaw_path, "openclaw")
    checks = []
    checks.append({"name": "claude_cli", "status": "pass" if claude_path else "fail", "path": claude_path or ""})
    checks.append({"name": "claude_settings", "status": "pass" if load_status == "ok" else "warn", "path": str(settings_path), "loadStatus": load_status})
    checks.append({"name": "openclaw", "status": "pass" if openclaw_path else "warn", "path": openclaw_path or ""})
    checks.append(
        {
            "name": "ccswitch_provider",
            "status": "pass" if ccswitch_provider.get("available") else "warn" if ccswitch_provider.get("desktopStateAvailable") else "warn",
            "path": ccwitch_path,
            "loadStatus": ccswitch_provider.get("loadStatus"),
        }
    )
    confidence = "high" if claude_path and load_status == "ok" else "medium" if claude_path or load_status == "ok" else "low"
    return {
        "artifactSchema": ARTIFACT_SCHEMA_VERSION,
        "invocationContract": INVOCATION_CONTRACT,
        "runtimeType": "codex-with-cc-runtime-status",
        "status": "pass" if claude_path and load_status == "ok" else "warn",
        "confidence": confidence,
        "claudeCli": {"path": claude_path or "", **claude_package},
        "openclaw": {"path": openclaw_path or "", **openclaw_package},
        "ccwitch": ccswitch_provider,
        "ccswitchProvider": ccswitch_provider,
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
            "ccswitchProviderLoadStatus": ccswitch_provider.get("loadStatus"),
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
        f"CcSwitch: {report.get('ccswitchProvider', report.get('ccwitch', {})).get('path') or '-'} loadStatus={report.get('ccswitchProvider', report.get('ccwitch', {})).get('loadStatus') or '-'}",
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
