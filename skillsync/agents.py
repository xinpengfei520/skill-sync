"""Platform detection, agent registry, install detection, user selection,
and cross-platform symlink helpers."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

# --- Paths ------------------------------------------------------------------
# TOOL_ROOT: the tool's own checkout — its code, the known-agents registry, and
#   the repo that `update` pulls from.
# DATA_ROOT: your skills library — skills/, your config, and the repo that
#   `sync`/`backup` commit to.
# They coincide in a combined checkout. Point DATA_ROOT at a separate (private)
# skills repo by setting SKILL_SYNC_HOME.
TOOL_ROOT = Path(__file__).resolve().parent.parent
_HOME_FILE = Path.home() / ".skill-sync" / "home"  # remembers DATA_ROOT across runs
if os.environ.get("SKILL_SYNC_HOME"):
    DATA_ROOT = Path(os.path.expanduser(os.environ["SKILL_SYNC_HOME"])).resolve()
elif _HOME_FILE.is_file() and _HOME_FILE.read_text().strip():
    DATA_ROOT = Path(os.path.expanduser(_HOME_FILE.read_text().strip())).resolve()
else:
    DATA_ROOT = TOOL_ROOT
REGISTRY_FILE = TOOL_ROOT / "config" / "registry.json"
SELECTION_FILE = DATA_ROOT / "config" / "agents.json"
DEFAULT_SKILLS_ROOT = DATA_ROOT / "skills"
BACKUP_ROOT = Path.home() / ".skill-sync-backups"

# Entries never treated as skills (system/hidden). Anything starting with "."
# is also ignored by callers.
IGNORE_NAMES = {".DS_Store", ".git", ".system"}

# Fallback catalog used only if config/registry.json is missing/unreadable.
BUILTIN_REGISTRY = [
    {"name": "claude",    "display": "Claude Code",        "paths": {"default": "~/.claude/skills"}},
    {"name": "codex",     "display": "Codex CLI",          "paths": {"default": "~/.codex/skills"}},
    {"name": "workbuddy", "display": "WorkBuddy",          "paths": {"default": "~/.workbuddy/skills"}},
    {"name": "hermes",    "display": "Hermes",             "paths": {"default": "~/.hermes/skills"}},
    {"name": "gemini",    "display": "Gemini CLI",         "paths": {"default": "~/.gemini/skills"}},
    {"name": "cursor",    "display": "Cursor",             "paths": {"default": "~/.cursor/skills"}},
    {"name": "copilot",   "display": "GitHub Copilot CLI", "paths": {"default": "~/.copilot/skills"}},
    {"name": "codebuddy", "display": "CodeBuddy",          "paths": {"default": "~/.codebuddy/skills"}},
    {"name": "qoder",     "display": "Qoder",              "paths": {"default": "~/.qoder/skills"}},
    {"name": "trae",      "display": "Trae",               "paths": {"default": "~/.trae/skills"}},
    {"name": "windsurf",  "display": "Windsurf (Codeium)", "paths": {"default": "~/.codeium/windsurf/skills"}},
    {"name": "opencode",  "display": "OpenCode",           "paths": {"default": "~/.config/opencode/skills"}},
    {"name": "kiro",      "display": "Kiro",               "paths": {"default": "~/.kiro/skills"}},
    {"name": "openclaw",  "display": "OpenClaw",           "paths": {"default": "~/.openclaw/skills"}},
]


# --- Platform ---------------------------------------------------------------
def system_name() -> str:
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    return "linux"


def expand(p) -> Path:
    """Expand ~ and environment variables (incl. Windows %VAR%)."""
    s = os.path.expandvars(os.path.expanduser(str(p)))
    # normalize %VAR% that expandvars didn't catch on non-Windows
    return Path(s)


# --- Registry & resolution --------------------------------------------------
def load_registry() -> list[dict]:
    if REGISTRY_FILE.is_file():
        try:
            data = json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("agents"), list):
                return data["agents"]
            if isinstance(data, list):
                return data
        except (json.JSONDecodeError, OSError):
            pass
    return BUILTIN_REGISTRY


def _registry_path(entry: dict) -> Path | None:
    paths = entry.get("paths") or {}
    raw = paths.get(system_name()) or paths.get("default")
    if not raw and "skills_dir" in entry:  # legacy home-relative form
        raw = "~/" + str(entry["skills_dir"]).lstrip("/")
    return expand(raw) if raw else None


def resolve_agent(entry: dict, priority: int) -> dict:
    sd = _registry_path(entry)
    return {
        "name": entry["name"],
        "display": entry.get("display", entry["name"]),
        "skills_dir": sd,
        "base_dir": sd.parent if sd else None,
        "priority": priority,
        "installed": bool(sd and sd.parent.exists()),
    }


def all_agents() -> list[dict]:
    """Every known agent (registry + user custom), resolved for this OS."""
    reg = load_registry()
    custom = load_selection().get("custom") or []
    entries = list(reg) + list(custom)
    return [resolve_agent(e, i) for i, e in enumerate(entries)]


def is_managed(name: str, sel: dict | None = None) -> bool:
    """True when `name` is not disabled and is covered by `enabled`."""
    sel = sel if sel is not None else load_selection()
    if name in (sel.get("disabled") or []):
        return False
    enabled = sel.get("enabled", "all")
    return not isinstance(enabled, list) or name in enabled


def managed_agents(only: list[str] | None = None) -> list[dict]:
    """Resolved agents the user has enabled (and optionally filtered by name)."""
    sel = load_selection()
    enabled = sel.get("enabled", "all")
    disabled = set(sel.get("disabled") or [])
    agents = [a for a in all_agents() if a["name"] not in disabled]
    if isinstance(enabled, list):
        wanted = set(enabled)
        agents = [a for a in agents if a["name"] in wanted]
    if only:
        keep = set(only)
        agents = [a for a in agents if a["name"] in keep]
    return sorted(agents, key=lambda a: a["priority"])


def probe_skills_dir(name: str) -> list[Path]:
    """Best-effort guesses for an unknown agent's skills dir.

    Only returns paths that actually show evidence of the agent on this machine
    (the skills dir exists, or its parent — the agent's config dir — does).
    Never creates anything."""
    seen: set[str] = set()
    out: list[Path] = []
    for raw in (f"~/.{name}/skills", f"~/.config/{name}/skills"):
        p = expand(raw)
        if not (p.is_dir() or p.parent.is_dir()):
            continue
        key = os.path.realpath(p)
        if key not in seen:
            seen.add(key)
            out.append(p)
    return out


def find_agent_by_dir(path: Path, exclude: str | None = None) -> dict | None:
    """Return the agent already configured with this skills dir, if any.

    Guards `agent add` against registering a second name for the same directory
    (e.g. `dsh` vs. a custom `deepseek`), which would double-process it."""
    target = os.path.realpath(path)
    for a in all_agents():
        if a["name"] == exclude or not a["skills_dir"]:
            continue
        if os.path.realpath(a["skills_dir"]) == target:
            return a
    return None


def tilde_path(path: Path) -> str:
    """Render a path under the home dir as ~/… so config stays portable."""
    try:
        rel = Path(os.path.realpath(path)).relative_to(Path.home())
    except ValueError:
        return str(path)
    return "~/" + rel.as_posix()


# --- User selection (config/agents.json) ------------------------------------
def load_selection() -> dict:
    if SELECTION_FILE.is_file():
        try:
            data = json.loads(SELECTION_FILE.read_text(encoding="utf-8"))
            if isinstance(data, list):  # legacy: [{name, skills_dir, priority}, ...]
                return {"enabled": [a["name"] for a in data if "name" in a],
                        "disabled": [], "adopt_external": True,
                        "auto_commit": False, "auto_push": False, "custom": []}
            if isinstance(data, dict):
                data.setdefault("enabled", "all")
                data.setdefault("disabled", [])
                data.setdefault("adopt_external", True)
                data.setdefault("auto_commit", False)
                data.setdefault("auto_push", False)
                data.setdefault("auto_update", False)
                data.setdefault("update_remote", "origin")
                data.setdefault("backup", {"enabled": False, "remote": None})
                data.setdefault("custom", [])
                return data
        except (json.JSONDecodeError, OSError):
            pass
    return {"enabled": "all", "disabled": [], "adopt_external": True,
            "auto_commit": False, "auto_push": False, "auto_update": False,
            "update_remote": "origin", "backup": {"enabled": False, "remote": None},
            "custom": []}


def save_selection(sel: dict) -> None:
    SELECTION_FILE.parent.mkdir(parents=True, exist_ok=True)
    SELECTION_FILE.write_text(
        json.dumps(sel, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def skills_root() -> Path:
    root = load_selection().get("skills_root")
    return expand(root) if root else DEFAULT_SKILLS_ROOT


# --- Cross-platform symlink helpers -----------------------------------------
def is_link(path: Path) -> bool:
    """True for a POSIX symlink or a Windows junction/reparse point."""
    if path.is_symlink():
        return True
    if system_name() == "windows":
        try:
            os.readlink(str(path))
            return True
        except OSError:
            return False
    return False


def link_target(path: Path) -> str | None:
    try:
        return os.readlink(str(path))
    except OSError:
        return None


def make_link(target: Path, link: Path) -> None:
    """Create a directory symlink; fall back to a junction on Windows when
    real symlinks require privileges the user doesn't have."""
    target, link = Path(target), Path(link)
    try:
        os.symlink(str(target), str(link), target_is_directory=True)
    except (OSError, NotImplementedError, AttributeError):
        if system_name() == "windows":
            subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)],
                           check=True, capture_output=True, text=True)
        else:
            raise


def remove_link(path: Path) -> None:
    """Remove a symlink or junction without touching its target."""
    try:
        path.unlink()
    except (OSError, IsADirectoryError):
        # Windows junctions may need rmdir (removes the link, not the target)
        if system_name() == "windows":
            os.rmdir(str(path))
        else:
            raise
