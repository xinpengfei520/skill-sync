# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.4.2] — 2026-11-14

### Added
- **Consolidated layout** — skills, config, backups and logs now live under one
  directory: `~/.skill-sync/skills/` (the library), `~/.skill-sync/config/`,
  `~/.skill-sync/backups/`, `~/.skill-sync/logs/`, plus `~/.skill-sync/tool/`
  for one-line installs. The data repo still tracks `skills/` and `config/`
  (relative paths are unchanged); `backups/`, `logs/`, `tool/` and `home` are
  gitignored.
- **`migrate` command** — moves `~/my-skills`, `~/.skill-sync-backups` and
  `~/.skill-sync/autosync.log` into the consolidated layout, keeps the repo's
  `.git` and remotes, repoints the agent symlinks, and rewrites the auto-sync
  job so it no longer pins the old paths. Dry-run by default; a safe migration
  also runs automatically on the next command.
- **Local commits by default** — `sync` commits the data repo when git is
  available, pushes only when a remote is configured (`origin` or the backup
  remote), and skips committing entirely without git. `auto_commit` defaults
  to true; `auto_push: null` means "push when a remote exists".
- **Bundled skill stays current** — the tool's own `skills/skill-sync` is
  authoritative. It is seeded into the library on install and refreshed from the
  tool whenever the content differs (on install, after `update`, and on any
  command); the previous copy is moved under `backups/bundled-skill-<stamp>/`.
  This makes the "just tell your agent to sync my skills" workflow work on a
  fresh install and keeps its instructions in step with the CLI. Linked or
  missing sources are left alone.
- **Updated bundled skill** — the `skill-sync` skill now documents the
  consolidated `~/.skill-sync` layout, the global `skill-sync` command,
  `doctor`, `migrate`, `agent add/remove`, `uninstall`, `update`, `backup`, and
  the local-commit-by-default behavior.
- **One-line installer** — `curl -fsSL …/install.sh | sh` clones the tool to
  `~/.skill-sync/tool` (or reuses an existing checkout such as `~/skill-sync`),
  writes a `skill-sync` launcher into `~/.local/bin`, and adds that directory to
  PATH in `~/.zshrc` / `~/.bashrc` through an idempotent marker block. Re-running
  updates the checkout; an existing `~/.skill-sync/home`, `config/agents.json`,
  and the skills library are never touched, and `python3 bin/skill-sync.py`
  keeps working for manual clones.

## [0.4.1] — 2026-11-14

### Added
- **`doctor` command** — a read-only health check for the library and every
  managed agent: how many skills are installed, how large each one is, what the
  name + description block costs in context, and which agents are out of sync
  (missing, dangling, or blocked links). It validates frontmatter against the
  Agent Skills limits (name/description present, kebab-case name ≤ 64 chars,
  description ≤ 1024 chars without angle brackets, `SKILL.md` < 500 lines) and
  ends with concrete suggestions. `--json` for tooling, `--limit`/`--all` to
  control the size table and info findings, `--agent` to narrow the agent view,
  `--strict` to exit 1 when an error is found.

### Documentation
- **Product banner** at the top of all four READMEs — agents on the left, each
  linked to `skill-sync` in the middle, and `skills-repo` on the right.
- `doctor` is documented in all four language READMEs (command table and a
  health-check section).

## [0.4.0] — 2026-11-13

### Added
- **Antigravity agents** — `antigravity`, `antigravity-ide`, and
  `antigravity-cli` are now in the registry, pointing at
  `~/.gemini/{antigravity,antigravity-ide,antigravity-cli}/skills`. Note that
  `~/.gemini/antigravity/skills` is a symlink to the shared, cloud-managed
  `~/.gemini/config/skills` store — see the README before enabling it.
- **Grok** — `grok` (`~/.grok/skills`) is now in the registry, so it no longer
  needs a `custom` entry. A `custom` entry that duplicates a registry name is
  ignored (the registry wins), which prevents syncing the same directory twice.
- **`agent add` / `agent remove`** — manage one agent without re-running `init`.
  `agent add <name>` enables it, resolving the skills dir from the registry →
  `custom` → `--path` → a convention probe (`~/.<name>/skills`,
  `~/.config/<name>/skills`); it refuses a name that points at another agent's
  directory and previews the sync unless `--apply`. `agent remove <name>` stops
  syncing it and, with `--prune-links` (dry-run unless `--apply`), reclaims the
  symlinks it left in the library — real dirs and external links are left alone.
  New `disabled` key in `config/agents.json` makes exclusions work even when
  `enabled` is `"all"`; `init` clears it.
- **`uninstall` command** — `skill-sync uninstall <skill> [<skill> …]` removes a
  skill from the library and every installed agent in one pass: it deletes
  `skills/<name>` (backed up first unless `--no-backup`) and removes every
  mirrored symlink that points into the library, including dangling links left
  behind after a skill is gone (orphan cleanup). Dry-run by default; `--apply`
  executes. Honors the safety invariants: a real directory or a link to an
  outside hub is reported and left untouched, never deleted. `--commit`/`--push`
  optionally commit the removal to the DATA repo.

## [0.3.0] — 2026-07-07

### Added
- **Self-update** — `skill-sync update` pulls the latest tool code
  (`update --check` to only check). When `auto_update` is enabled, the scheduled
  auto-sync job updates the tool before each run (fast-forward, or rebase over
  local commits) and re-execs so the new code runs immediately.
- **Backup** — `skill-sync backup --set <git-url>` configures a second Git remote
  and pushes your skills to it; `backup` pushes on demand and (when enabled) after
  each scheduled sync; `backup --disable` turns it off. **Off by default.**
- `status` now reports the tool version, update availability, and backup state.
- `schedule --auto-update` toggles self-update on the scheduled job.

### Config
- New `config/agents.json` keys: `auto_update` (default `false`), `update_remote`
  (default `"origin"`), and `backup: { enabled, remote }` (default off).

## [0.2.0] — 2026-07-07

Turned the single-file script into an installable, open-source, cross-platform
tool.

### Added
- **`skillsync` package** — split into `agents` (registry + OS-aware path
  resolution + install detection + symlink/junction helpers), `engine`
  (collect + mirror), `runner` (orchestration + git), `scheduler`, and `cli`.
- **Agent registry** (`config/registry.json`) — catalog of known agents with
  per-OS skills paths; new agents are added here.
- **`init` command** — detects installed agents and lets you choose which to
  manage (interactive, `--all`, or `--agents a,b`).
- **Auto-sync** — `schedule --interval <1m|10m|1h|12h|24h|1d>` installs a native
  OS timer (launchd / Task Scheduler / systemd) with optional auto commit+push;
  `watch` runs the same loop in the foreground; `unschedule` removes the timer.
- **`status`** and **`list`** commands for an at-a-glance overview.
- **Cross-platform** support (macOS / Linux / Windows), with a Windows
  symlink→directory-junction fallback when real symlinks aren't permitted.
- `SKILL_SYNC_HOME` environment override, `pyproject.toml` (`skill-sync` console
  script), and an **MIT LICENSE**.

### Changed
- `config/agents.json` is now a selection file (`enabled` list, `adopt_external`,
  `auto_commit`, `auto_push`, `custom`) instead of a raw path list. The old
  list format is auto-migrated.
- Only installed agents are ever touched; enabled-but-absent agents are skipped.

### Compatibility
- Backward compatible: a bare invocation (or leading options) still runs `sync`.

### Managed agents
- Grew to 13: claude, codex, workbuddy, hermes, gemini, cursor, copilot,
  codebuddy, qoder, trae, windsurf, opencode, kiro. Library holds 92 skills.

## [0.1.0] — 2026-07-07

Initial release.

### Added
- Central Git-managed skills repository (`skills/`) as the single source of
  truth, with agents pointing at it via symlinks.
- **Collect + full-mirror engine**: moves source-installed skills into the repo,
  dedupes identical copies (with backups), reports content conflicts without
  overwriting, and mirrors every skill into every managed agent. Dry-run by
  default; idempotent.
- `--adopt-external` to centralize skills symlinked to an outside hub
  (e.g. `~/.agents`).
- Onboarded claude, codex, workbuddy, hermes; adopted skills from external hubs
  (lark-*, obsidian-*, wecomcli-*, agently-mail); added gemini, cursor, copilot,
  codebuddy, qoder, trae, windsurf.
- Resolved the `aihot` naming conflict (kept the Claude Code version).

[0.4.2]: https://github.com/xinpengfei520/skill-sync/releases/tag/v0.4.2
[0.4.1]: https://github.com/xinpengfei520/skill-sync/releases/tag/v0.4.1
[0.4.0]: https://github.com/xinpengfei520/skill-sync/releases/tag/v0.4.0
[0.3.0]: https://github.com/xinpengfei520/skill-sync/releases/tag/v0.3.0
[0.2.0]: https://github.com/xinpengfei520/skill-sync/releases/tag/v0.2.0
[0.1.0]: https://github.com/xinpengfei520/skill-sync/releases/tag/v0.1.0
