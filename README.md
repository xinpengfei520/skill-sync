# skill-sync

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-green.svg" alt="License: MIT"></a>
  <img src="https://img.shields.io/badge/python-3.9%2B-blue.svg" alt="Python 3.9+">
  <img src="https://img.shields.io/badge/platform-macOS%20%7C%20Linux%20%7C%20Windows-lightgrey.svg" alt="Platform">
  <img src="https://img.shields.io/badge/version-0.3.0-blue.svg" alt="Version">
  <img src="https://img.shields.io/badge/PRs-welcome-brightgreen.svg" alt="PRs welcome">
</p>

<p align="center">
  <b>English</b> ·
  <a href="README.zh-CN.md">简体中文</a> ·
  <a href="README.ja.md">日本語</a> ·
  <a href="README.ko.md">한국어</a>
</p>

**One Git-managed source of truth for the Skills used by all your local AI agents.**

Modern AI agents — Claude Code, Codex, Cursor, Gemini CLI, Copilot, Windsurf,
WorkBuddy, and more — all support [Skills](https://www.anthropic.com/news/skills)
(`SKILL.md` folders), but each stores them in a *different* directory. Install a
skill in one and the others don't have it; edit it in one and the copies drift.

`skill-sync` fixes that. It keeps a single canonical copy of every skill under
[`skills/`](skills/) and points every installed agent at it with **symlinks**.
Edit a skill once here and every agent sees the change. Install a skill into just
one agent and the next sync shares it with the rest.

```
             ┌─────────────────────────────┐
             │   skills/  (this repo, Git)  │   ← the one source of truth
             └──────────────┬──────────────┘
        ┌───────────┬───────┼───────┬───────────┐
     symlink     symlink  symlink symlink     symlink
        ▼           ▼        ▼       ▼           ▼
   ~/.claude/   ~/.codex/  ~/.cursor/ ~/.gemini/  … every installed agent
```

## Features

- **Collect + full-mirror** — pulls source-installed skills from every agent into
  the repo, then symlinks all skills into every agent so they stay identical.
- **Only touches installed agents** — auto-detects which agents exist on the
  machine; never creates folders for agents you don't have.
- **First-run selection** — `init` lets you pick which agents to manage (or all).
- **Auto-sync** — install a native OS timer (`schedule --interval 1h`) or run a
  foreground `watch` loop; syncs on a schedule with optional auto commit/push.
- **Cross-platform** — macOS, Linux, and Windows (Windows uses directory
  junctions when real symlinks aren't permitted).
- **Safe** — dry-run by default; never overwrites a real directory; content
  conflicts are reported, never silently resolved; removed duplicates are
  backed up; idempotent.

## Install

### Option A — via your AI agent (paste & go)

Copy this and paste it to any AI agent (Claude Code, Codex, Cursor, …). It clones
the repo, detects your installed agents, and syncs everything:

```text
Install "skill-sync" for me — it keeps all my AI agents' Skills in sync from one Git repo.

1. If ~/skill-sync doesn't exist, run:
   git clone https://github.com/xinpengfei520/skill-sync.git ~/skill-sync
2. Preview the sync (detects my installed agents, changes nothing):
   python3 ~/skill-sync/bin/skill-sync.py init --all
3. Show me the plan. If there are no conflicts, apply it:
   python3 ~/skill-sync/bin/skill-sync.py --apply
4. Tell me which agents were detected and how many skills are now shared.

Needs Python 3.9+. Never overwrite my existing skills — if a skill name conflicts
with different content, stop and show me.
```

> **Tip:** After installing, just tell any agent *"sync my skills"* to re-sync
> — the `skill-sync` skill is mirrored into every agent, so there are no commands
> to remember.

### Option B — manual

No dependencies beyond **Python 3.9+**. Just clone and run:

```bash
git clone https://github.com/xinpengfei520/skill-sync.git ~/skill-sync
cd ~/skill-sync
python3 bin/skill-sync.py --version
```

Optionally install the `skill-sync` command (`pip install -e .`). If you install
it and keep your skills repo elsewhere, point at it with
`export SKILL_SYNC_HOME=~/my-skills`.

## Quick start

```bash
# 1. Choose which installed agents to manage (interactive, or --all)
python3 bin/skill-sync.py init

# 2. Preview what a sync would do (nothing changes)
python3 bin/skill-sync.py

# 3. Apply
python3 bin/skill-sync.py --apply

# 4. Commit & push (this repo is the source of truth)
git add -A && git commit -m "sync skills" && git push
```

## Commands

| Command | What it does |
|---|---|
| `init [--all\|--agents a,b]` | Detect installed agents, pick which to manage, save config, sync |
| `sync [--apply]` | Collect + mirror. Dry-run unless `--apply` |
| `uninstall <skill> … [--apply]` | Remove skill(s) from the library and every agent. Dry-run unless `--apply` |
| `agent add <name> [--path DIR]` | Start syncing one agent (resolves its skills dir; preview unless `--apply`) |
| `agent remove <name> [--prune-links]` | Stop syncing one agent; optionally reclaim its symlinks |
| `status` | Platform, agent table, auto-sync state, and a dry-run summary |
| `list` | All known agents with installed / managed state |
| `watch --interval 10m` | Foreground loop; sync every interval |
| `schedule --interval 1h` | Install a native OS timer (launchd / Task Scheduler / systemd) |
| `unschedule` | Remove the timer |
| `update [--check]` | Update the tool to the latest version (git pull) |
| `backup [--set URL]` | Back up your skills to your own Git repo (off by default) |

Useful `sync` flags: `--adopt-external` (centralize skills currently symlinked to
an outside hub), `--agent NAME` (limit to specific agents), `--commit --push`
(git after applying), `--json`, `--no-backup`.

### Adding / removing an agent

```bash
# Start syncing an agent that's in the registry
python3 bin/skill-sync.py agent add cursor

# An agent not in the registry: give it the skills directory
python3 bin/skill-sync.py agent add dsh --path ~/.dsh/skills --display "DeepSeek Harness"

# Stop syncing it, and reclaim its links into the library
python3 bin/skill-sync.py agent remove dsh --prune-links --apply
```

`agent add` resolves the skills dir in this order: the registry
(`config/registry.json`) → your `custom` entries (`config/agents.json`) →
`--path` → a convention probe of `~/.<name>/skills` and
`~/.config/<name>/skills`. The probe only trusts paths that actually exist, and
it refuses to register a name whose directory already belongs to another agent
(same dir, two names → double sync). `agent add` previews a sync; add `--apply`
to perform it.

`agent remove` only changes the selection — existing symlinks stay until you pass
`--prune-links` (dry-run by default, `--apply` to delete). Only links pointing
into the library are reclaimed; real directories and links to outside hubs are
reported and left untouched.

### Auto-sync

```bash
# Sync every hour in the background, auto commit+push, survives reboot
python3 bin/skill-sync.py schedule --interval 1h

# Or a simple foreground loop
python3 bin/skill-sync.py watch --interval 10m
```

Intervals accept `s`/`m`/`h`/`d` (e.g. `90s`, `10m`, `1h`, `12h`, `24h`, `1d`);
a bare number is minutes. Minimum `30s`. Logs go to `~/.skill-sync/autosync.log`.

### Updating & backup

```bash
# Update skill-sync to the latest version
python3 bin/skill-sync.py update            # or: update --check

# Self-update on every scheduled run
python3 bin/skill-sync.py schedule --interval 1h --auto-update

# Back up your skills to your own Git repo (off by default)
python3 bin/skill-sync.py backup --set git@github.com:you/my-skills-backup.git
python3 bin/skill-sync.py backup            # push on demand; also runs after scheduled syncs
```

`update` fast-forwards, or rebases over your local skill commits. `backup` pushes
to a second Git remote you control — handy when you cloned this tool from upstream
and want your own skills stored separately.

## How syncing works

1. **Collect** — scan each managed agent's skills dir for *real* directories
   (symlinks are ignored) containing a `SKILL.md`:
   - a **new** skill is moved into `skills/` (becomes canonical),
   - an **identical duplicate** is backed up and removed (so it can be relinked),
   - a same-named skill with **different content** is a **conflict** — every copy
     is left untouched and reported for you to resolve.
2. **Mirror** — every skill in `skills/` is symlinked into every installed,
   managed agent. A pre-existing real directory is never overwritten (reported as
   *blocked*). With `--adopt-external`, skills symlinked to an outside hub are
   copied into the repo and repointed.

## Configuration

- **`config/registry.json`** — catalog of known agents and their per-OS skills
  paths. Add new agents here (with `paths.default` and optional `paths.windows` /
  `paths.macos` / `paths.linux`).
- **`config/agents.json`** — your machine's selection: `enabled` (a list of agent
  names, or `"all"`), `disabled` (names excluded even when `enabled` is `"all"`),
  `adopt_external`, `auto_commit`, `auto_push`, and any `custom` agents not in
  the registry. Written by `init` and `agent add/remove`.

An agent is only synced if it's enabled, not `disabled`, **and** its config
directory exists on this machine.

## Safety

- Dry-run by default; real changes need `--apply`.
- Never overwrites a real directory or a conflicting skill.
- Removed duplicates are backed up to `~/.skill-sync-backups/<timestamp>/`.
- Idempotent — re-running when everything is linked does nothing.

## License

MIT — see [LICENSE](LICENSE).
