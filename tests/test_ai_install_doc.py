#!/usr/bin/env python3
from pathlib import Path

repo = Path(__file__).resolve().parents[1]


def test_ai_install_doc_contract() -> None:
    text = (repo / "AI_INSTALL.md").read_text(encoding="utf-8")

    assert "codex_with_cc_plus" in text
    assert "shaoqing404/codex_with_cc_plus" in text
    assert ".codex-plugin/plugin.json" in text
    assert ".agents/plugins/marketplace.json" in text
    assert "skills/codex-with-cc/manifest.json" not in text
    assert "command -v codex" in text
    assert "npm i -g @openai/codex" in text
    assert "codex plugin marketplace add shaoqing404/codex_with_cc_plus --ref master" in text
    assert "codex plugin add codex-with-cc-plus@codex-with-cc-plus" in text
    assert "aiskyhub/aiskyhub" in text
    assert "not required registration" in text
    assert "user-scope plugin install" in text
    assert "Do not mutate system Python" in text
    assert "Any mention of child-agent" in text
    assert "Codex main thread" in text
    assert "Codex child thread" in text
    assert "local deterministic zero-token hard gate" in text
    assert "`validate_delegate_task.*` is not a DeepSeek verifier" in text
    assert "DeepSeek Flash or compatible OpenAI API" in text
    assert "mayOverrideValidator=false" in text
    assert "Task file format check" in text
    assert "zero-token hard gate" in text
    assert "env CODEX_CLAUDE_CHILD_THREAD=1" in text
    assert "Do not keep the main agent busy with blind `sleep` loops" in text
    assert "-MaxTurns" in text
    assert "-IncludePartialMessages" in text
    assert "docs/codex_with_cc" in text
    assert "doc/codex_with_cc" in text
    assert ".codex/skills/codex-with-cc" in text
    assert "<!-- BEGIN CODEX_WITH_CC --> ... <!-- END CODEX_WITH_CC -->" in text
    assert "$HOME/.codex/skills/codex-with-cc" in text
    assert "$env:USERPROFILE\\.codex\\skills\\codex-with-cc" in text
    assert "codex_with_cc/scripts/delegate_to_claude.py" not in text
    assert "/plugin install codex-with-cc@aiskyhub --scope user" not in text
    assert "Codex plugin entry" in text
    assert "workflow/task/run" in text
    assert "artifact schema" in text
    assert "WorkflowId" in text
    assert "TaskId" in text
    assert "Role" in text
    assert "Status / Role / Summary / Changed Files / Verification / Findings / Final Result / Risks Or Follow-ups" in text
    assert "test_delegate_runtime.ps1" in text
    assert "test_delegate_session_pool.ps1" in text
    assert "dry-run install verification" in text.lower()
    assert "verify_delegate_run" in text
    assert "verify_delegate_workflow" in text
    assert "<installed-workflow-root>" in text
    assert "<installed-plugin-root>" not in text
    assert "marketplace-only" not in text
    assert ".claude-plugin/marketplace.json" not in text
    assert "/plugin marketplace list" not in text
    assert "claude plugin marketplace list" not in text
    assert "/plugin marketplace add aiskyhub/aiskyhub" not in text
    assert "/reload-plugins" not in text
    assert "## Final Report To User" in text
    assert "Only say the workflow is ready after verification" in text
    assert "install_codex_with_cc.ps1" not in text
    assert "install_codex_with_cc.sh" not in text
    assert "scripts/install_codex_with_cc.py" not in text
    assert "macOS 支持尚未实现" not in text
