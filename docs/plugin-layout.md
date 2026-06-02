# Codex Plugin Layout

This repository ships as a Codex plugin from the independent repository `shaoqing404/codex_with_cc_plus`. It can be installed from a Codex marketplace once that marketplace indexes `.codex-plugin/plugin.json`, or copied locally as a user skill while marketplace registration is pending.

## Structure

- `.codex-plugin/plugin.json`: Codex plugin manifest and UI metadata.
- `skills/`: Shared plugin content root for the Codex plugin.
- `skills/codex-with-cc/`: The real workflow implementation, runtime scripts, `contract.json`, and contract docs.

## Why the runtime stays under `skills/codex-with-cc/`

The delegated runtime, hook gate, and contract tests assume that `skills/codex-with-cc/` is the canonical workflow root. Keeping that directory stable avoids breaking:

- platform-specific packaging of `windows_scripts/` and `macos_scripts/`
- verification scripts and path-sensitive tests
- the shared `contract.json` read by both Python runtime code and the platform hook

## Installation paths

- Source layout: this repository exposes `.codex-plugin/plugin.json` so it can be recognized as a Codex plugin source.
- Public marketplace path: register `codex-with-cc` in `aiskyhub/aiskyhub` with repository `https://github.com/shaoqing404/codex_with_cc_plus.git` and manifest `.codex-plugin/plugin.json`.
- Personal marketplace path: register an alias such as `codex-with-cc-plus@shaoqing404` in `shaoqing404/marketplace`, also pointing at `.codex-plugin/plugin.json`.
- Local fallback path: clone this repository and copy `skills/codex-with-cc` to `$HOME/.codex/skills/codex-with-cc`.
