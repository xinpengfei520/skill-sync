---
name: skill-sync
description: >-
  Single source of truth for AI-agent Skills. Use when the user wants to sync,
  consolidate, or centralize skills across local agents (Claude Code, Codex,
  Cursor, Gemini, Copilot, Windsurf, WorkBuddy, Hermes, etc.); when a new skill
  was installed into only one agent and should be shared with the others; to
  choose which agents to manage; to check skill health (count, size, frontmatter,
  context cost); or to migrate an older on-disk layout. Also triggers on
  "同步 skills", "sync my skills", "把这个 skill 同步到所有 agent",
  "collect skills", "整理 skills", "定时同步 skills", "自动同步",
  "体检 skills", "迁移 skills".
---

# skill-sync

One Git-managed library for every local agent's Skills. The library is
`~/.skill-sync/skills/` (one directory per skill); every managed agent points at
it with symlinks, so editing a skill once updates all agents. `~/.skill-sync/`
also holds `config/agents.json` (which agents are managed), `backups/` and
`logs/`.

If `skill-sync` is not on PATH, run `python3 <checkout>/bin/skill-sync.py`
instead of `skill-sync` in every command below.

## Commands

Always dry-run first, then apply.

```bash
skill-sync init                  # detect agents, choose which to manage
skill-sync                       # preview a sync
skill-sync --apply               # execute

skill-sync status                # platform, library, agents, dry-run summary
skill-sync list                  # every known agent + installed/managed state
skill-sync doctor                # read-only health: count, size, frontmatter
skill-sync doctor --json         # machine-readable

skill-sync agent add cursor      # start managing one agent
skill-sync agent remove cursor --prune-links --apply
skill-sync uninstall <skill> --apply   # remove from the library + every agent

skill-sync migrate               # preview moving an older layout (dry-run)
skill-sync migrate --apply       # move ~/my-skills etc. into ~/.skill-sync

skill-sync schedule --interval 1h   # native OS timer
skill-sync unschedule
skill-sync watch --interval 10m     # foreground loop
skill-sync update [--check]         # update the tool itself
skill-sync backup [--set URL]       # optional backup remote
```

## How it works

1. **Collect** — scan each managed agent's skills dir for real directories (not
   symlinks) with a `SKILL.md`: new → moved into the library; identical duplicate
   → backed up and removed; same name with different content → **conflict**, left
   untouched and reported.
2. **Mirror** — every library skill is symlinked into every installed managed
   agent. An existing real directory is never overwritten (reported as blocked).

Sync commits the library locally when git is available, and pushes only when a
remote is configured; without git it just keeps syncing files.

## Guidance

- **Never `--apply` without showing the dry-run first** and getting an OK —
  collection moves and removes real directories.
- Surface any **CONFLICT** entries; nothing is changed for those. The user picks
  which version wins (edit the library copy, or delete the losing copy and
  re-sync).
- This skill's own bundled copy is refreshed from the tool on install/update
  when the content differs; the replaced copy is kept under `backups/`.
- Removed duplicates and replaced files are backed up under
  `~/.skill-sync/backups/`.
- Managed agents live in `config/agents.json`; known agents and their per-OS
  paths live in the tool's `config/registry.json`.
