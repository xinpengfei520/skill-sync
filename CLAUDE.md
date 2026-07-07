# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

`skill-sync` — a cross-platform CLI that keeps the Skills used by many local AI
agents (Claude Code, Codex, Cursor, …) in sync from one source: it collects
source-installed skills into a library directory and mirrors them into every
installed agent via symlinks.

This repo is the **tool**. A user's actual skills library is a **separate**
directory (their own, often private). The two are decoupled by path:

- **`TOOL_ROOT`** — this checkout: the code, the known-agents registry
  (`config/registry.json`), and the repo that `update` pulls from.
- **`DATA_ROOT`** — the skills library: `skills/`, the user's `config/agents.json`,
  and the repo that `sync`/`backup` commit to. Defaults to `TOOL_ROOT` (combined
  checkout) unless `SKILL_SYNC_HOME` points elsewhere.

Both resolve in `skillsync/agents.py`; use `A.TOOL_ROOT` vs `A.DATA_ROOT`
deliberately (e.g. `update` → TOOL, `backup`/commit → DATA).

- `bin/skill-sync.py` — entry point (adds repo root to `sys.path`, calls `skillsync.cli`).
- `skillsync/` — `agents` (registry + per-OS paths + install detection + symlink/
  junction helpers), `engine` (collect + mirror), `runner` (orchestration + git),
  `maintenance` (self-update + backup), `scheduler` (launchd/schtasks/systemd +
  watch), `cli`.

## Working on the tool

- No third-party dependencies. Target **Python 3.9+**; keep code cross-platform
  (macOS/Linux/Windows) — don't hardcode POSIX-only symlink calls or platform
  paths; use the helpers in `skillsync/agents.py`.
- There is no test suite. Verify a change by confirming a dry-run is idempotent
  and that modules compile:
  - `python3 bin/skill-sync.py` → expect `0 changes` when already synced
  - `python3 -m py_compile skillsync/*.py bin/skill-sync.py`
- `sync` is **dry-run by default**; only `--apply` mutates the filesystem.
  Preserve the engine's safety invariants: never overwrite a real directory, skip
  **and report** content conflicts (never auto-resolve), back up removed
  duplicates, and stay idempotent.

## Gotchas

- `config/agents.json` (a user's machine selection) and `skills/` beyond the
  bundled `skill-sync` skill are gitignored — they belong to a user's DATA_ROOT,
  not this tool repo. Don't commit them.
