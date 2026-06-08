from __future__ import annotations

import argparse
import html
import json
import webbrowser
from pathlib import Path
from typing import Any

from .common import ARTIFACT_SCHEMA_VERSION, INVOCATION_CONTRACT, now_iso
from .index import build_index
from .io_utils import write_json, write_text
from .paths import repo_root


def _output_root(ns: argparse.Namespace) -> Path:
    if ns.output_root:
        return Path(ns.output_root).expanduser().resolve()
    return (repo_root() / ".codex" / "codex_with_cc" / "dashboard").resolve()


def _state_badge_class(state: str) -> str:
    upper = state.upper()
    if upper in {"REPORT_READY"}:
        return "ok"
    if upper in {"FAILED", "RUNNING_DEAD_PROCESS", "STALE"}:
        return "bad"
    if upper.startswith("RUNNING") or upper == "STARTING":
        return "warn"
    return "muted"


def _render_badges(counts: dict[str, Any]) -> str:
    if not counts:
        return '<span class="badge muted">none</span>'
    parts = []
    for key, value in sorted(counts.items()):
        parts.append(f'<span class="badge {_state_badge_class(str(key))}">{html.escape(str(key))}: {html.escape(str(value))}</span>')
    return " ".join(parts)


def _render_html(index: dict[str, Any]) -> str:
    rows = []
    for record in index.get("records") or []:
        run_rows = []
        for run in record.get("runSummaries") or []:
            run_rows.append(
                "<tr>"
                f"<td>{html.escape(str(run.get('runId') or ''))}</td>"
                f"<td>{html.escape(str(run.get('role') or ''))}</td>"
                f"<td>{html.escape(str(run.get('state') or ''))}</td>"
                f"<td>{html.escape(str(run.get('finalResult') or ''))}</td>"
                f"<td>{html.escape(str(run.get('requestedModel') or ''))}</td>"
                f"<td>{html.escape(str(run.get('streamedModel') or ''))}</td>"
                f"<td>{html.escape(str(run.get('permissionMode') or ''))}</td>"
                f"<td>{'yes' if run.get('bypassPermissions') else 'no'}</td>"
                f"<td>{html.escape(str(run.get('failureLayer') or ''))}</td>"
                f"<td>{html.escape(str(run.get('businessAcceptance') or ''))}</td>"
                "</tr>"
            )
        run_table = (
            '<table class="runs"><thead><tr><th>Run</th><th>Role</th><th>State</th><th>Result</th>'
            "<th>Requested</th><th>Streamed</th><th>Permission</th><th>Bypass</th><th>Failure Layer</th><th>Acceptance</th></tr></thead><tbody>"
            + "".join(run_rows)
            + "</tbody></table>"
        )
        rows.append(
            '<section class="workflow">'
            f"<div><h2>{html.escape(str(record.get('workflowId') or '(orphan)'))}</h2>"
            f"<p>{html.escape(str(record.get('probableProjectRoot') or record.get('projectKey') or ''))}</p></div>"
            f"<div class=\"states\">{_render_badges(record.get('stateCounts') or {})}</div>"
            f"<div class=\"meta\"><span>confidence: {html.escape(str(record.get('confidence') or ''))}</span>"
            f"<span>updated: {html.escape(str(record.get('newestActivityAt') or ''))}</span>"
            f"<span>artifact: {html.escape(str(record.get('artifactRoot') or ''))}</span></div>"
            f"{run_table}"
            "</section>"
        )
    totals = index.get("totals") or {}
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Codex With CC Plus Dashboard</title>
  <style>
    :root { color-scheme: light dark; --bg: #f7f7f3; --fg: #171717; --line: #d8d8cf; --panel: #ffffff; --ok: #137a53; --warn: #9a6500; --bad: #b3261e; --muted: #60646c; }
    @media (prefers-color-scheme: dark) { :root { --bg: #141512; --fg: #f2f2ec; --line: #363831; --panel: #1f211d; --muted: #a8aca3; } }
    body { margin: 0; font: 14px/1.45 ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: var(--bg); color: var(--fg); }
    header { padding: 20px 24px 12px; border-bottom: 1px solid var(--line); }
    h1 { margin: 0 0 8px; font-size: 22px; letter-spacing: 0; }
    h2 { margin: 0; font-size: 15px; letter-spacing: 0; }
    p { margin: 4px 0 0; color: var(--muted); overflow-wrap: anywhere; }
    .summary { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
    .badge { display: inline-flex; align-items: center; min-height: 24px; padding: 0 8px; border: 1px solid var(--line); border-radius: 6px; font-size: 12px; white-space: nowrap; }
    .ok { color: var(--ok); } .warn { color: var(--warn); } .bad { color: var(--bad); } .muted { color: var(--muted); }
    main { padding: 16px 24px 32px; display: grid; gap: 12px; }
    .workflow { border: 1px solid var(--line); border-radius: 8px; background: var(--panel); padding: 14px; display: grid; gap: 10px; }
    .states, .meta { display: flex; flex-wrap: wrap; gap: 8px; }
    .meta span { color: var(--muted); overflow-wrap: anywhere; }
    table { width: 100%; border-collapse: collapse; table-layout: fixed; }
    th, td { text-align: left; border-top: 1px solid var(--line); padding: 7px 6px; overflow-wrap: anywhere; vertical-align: top; }
    th { color: var(--muted); font-weight: 600; font-size: 12px; }
    @media (max-width: 760px) { header, main { padding-left: 12px; padding-right: 12px; } table { font-size: 12px; } th, td { padding: 6px 4px; } }
  </style>
</head>
<body>
  <header>
    <h1>Codex With CC Plus Dashboard</h1>
    <p>Read-only machine artifact view. Facts are derived from workflow, status, config, stream, and report artifacts.</p>
    <div class="summary">
      <span class="badge">records: """ + html.escape(str(totals.get("records", 0))) + """</span>
      <span class="badge">workflows: """ + html.escape(str(totals.get("workflows", 0))) + """</span>
      <span class="badge">orphan runs: """ + html.escape(str(totals.get("orphanRuns", 0))) + """</span>
      """ + _render_badges(totals.get("stateCounts") or {}) + """
    </div>
  </header>
  <main>
    """ + "\n".join(rows or ['<p class="muted">No workflows found for the selected roots.</p>']) + """
  </main>
</body>
</html>
"""


def build_dashboard(ns: argparse.Namespace) -> dict[str, Any]:
    output_root = _output_root(ns)
    output_root.mkdir(parents=True, exist_ok=True)
    index = build_index(ns)
    index_path = output_root / "index.json"
    html_path = output_root / "index.html"
    write_json(index_path, index)
    write_text(html_path, _render_html(index))
    return {
        "artifactSchema": ARTIFACT_SCHEMA_VERSION,
        "invocationContract": INVOCATION_CONTRACT,
        "dashboardType": "codex-with-cc-static-dashboard",
        "status": "built",
        "outputRoot": str(output_root),
        "indexPath": str(index_path),
        "htmlPath": str(html_path),
        "records": len(index.get("records") or []),
        "readOnly": True,
        "mayOverrideVerifier": False,
        "updatedAt": now_iso(),
    }


def _render_text(report: dict[str, Any]) -> str:
    return "\n".join(
        [
            f"ccdash {report.get('status')}",
            f"OutputRoot: {report.get('outputRoot')}",
            f"Index: {report.get('indexPath')}",
            f"HTML: {report.get('htmlPath')}",
            f"Records: {report.get('records')}",
            "ReadOnly: true",
        ]
    )


def run_ccdash(ns: argparse.Namespace) -> int:
    report = build_dashboard(ns)
    if str(ns.ccdash_command) == "open" and not getattr(ns, "no_open", False):
        webbrowser.open(Path(report["htmlPath"]).as_uri())
        report["opened"] = True
    if ns.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(_render_text(report))
    return 0
