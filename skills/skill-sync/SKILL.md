---
name: skill-sync
description: >-
  Single source of truth for AI-agent Skills. Use when the user wants to sync,
  consolidate, or centralize skills across local agents (Claude Code, Codex,
  Cursor, Gemini, Copilot, Windsurf, WorkBuddy, Hermes, etc.); when a new skill
  was installed into only one agent and should be shared with the others; to
  choose which agents to manage; or to set up automatic/scheduled syncing. Also
  triggers on "同步 skills", "sync my skills", "把这个 skill 同步到所有 agent",
  "collect skills", "整理 skills", "定时同步 skills", "自动同步".
---

# skill-sync

Keep every local AI agent's Skills in sync from one Git-managed source
(`~/skill-sync`). Skills live under `skills/`; every managed agent points at them
with symlinks, so editing a skill once updates all agents.

## Commands

Run via the repo (no install needed). Always dry-run first, then apply.

```bash
# Detect installed agents and choose which to manage (first-time setup)
python3 ~/skill-sync/bin/skill-sync.py init            # interactive
python3 ~/skill-sync/bin/skill-sync.py init --all      # manage all installed

# Preview then apply a sync
python3 ~/skill-sync/bin/skill-sync.py                 # dry-run
python3 ~/skill-sync/bin/skill-sync.py --apply         # execute

# Overview / discovery
python3 ~/skill-sync/bin/skill-sync.py status          # platform, agents, dry-run
python3 ~/skill-sync/bin/skill-sync.py list            # all known agents + state

# Auto-sync
python3 ~/skill-sync/bin/skill-sync.py schedule --interval 1h   # native OS timer
python3 ~/skill-sync/bin/skill-sync.py unschedule              # remove timer
python3 ~/skill-sync/bin/skill-sync.py watch --interval 10m    # foreground loop
```

Common `sync` flags: `--adopt-external` (centralize skills symlinked to an
outside hub like `~/.agents`), `--agent NAME` (limit), `--commit --push` (git
after apply), `--json`, `--no-backup`.

## How it works

1. **Collect** — scans each managed agent's skills dir for real directories (not
   symlinks) with a `SKILL.md`: new → moved into the repo; identical duplicate →
   backed up + removed; same name but different content → **conflict**, left
   untouched and reported.
2. **Mirror** — every repo skill is symlinked into every installed managed agent.
   A pre-existing real dir is never overwritten (reported as blocked).

## Guidance

- **Never `--apply` without showing the dry-run first** and getting an OK —
  collection moves/removes real directories.
- Surface any **CONFLICT** entries (same name, different content); nothing is
  changed for those. The user picks which version wins (edit the repo copy, or
  delete the losing copy and re-sync).
- After applying, remind the user to commit & push:
  `git -C ~/skill-sync add -A && git -C ~/skill-sync commit -m "sync skills" && git -C ~/skill-sync push`
- Managed agents & their paths: `config/agents.json` (selection) +
  `config/registry.json` (known agents, per-OS paths).
- Removed duplicates are backed up under `~/.skill-sync-backups/`.
