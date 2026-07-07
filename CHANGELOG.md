# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

[0.3.0]: https://github.com/xinpengfei520/skill-sync/releases/tag/v0.3.0
[0.2.0]: https://github.com/xinpengfei520/skill-sync/releases/tag/v0.2.0
[0.1.0]: https://github.com/xinpengfei520/skill-sync/releases/tag/v0.1.0
