"""Tool self-update (git pull the TOOL repo) and optional backup of the skills
library (push the DATA repo to a user-configured Git remote). These are two
different repositories once the tool and skills are split apart."""
from __future__ import annotations

import re
import subprocess

from . import __version__
from . import agents as A

BACKUP_REMOTE = "skillsync-backup"


def _git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args],
                          capture_output=True, text=True)


def _branch(root) -> str:
    b = _git(root, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    return b if b and b != "HEAD" else "main"


def disk_version() -> str:
    """Version as written on disk (may differ from the loaded __version__ right
    after a self-update)."""
    try:
        txt = (A.TOOL_ROOT / "skillsync" / "__init__.py").read_text(encoding="utf-8")
        m = re.search(r'__version__\s*=\s*"([^"]+)"', txt)
        return m.group(1) if m else __version__
    except OSError:
        return __version__


# --- self-update (operates on TOOL_ROOT) ------------------------------------
def update_remote() -> str:
    return A.load_selection().get("update_remote", "origin")


def check_update(fetch: bool = True) -> dict:
    root = A.TOOL_ROOT
    remote, branch = update_remote(), _branch(root)
    if fetch:
        f = _git(root, "fetch", "--quiet", remote, branch)
        if f.returncode != 0:
            return {"ok": False, "error": f.stderr.strip() or "git fetch failed"}
    rl = _git(root, "rev-list", "--left-right", "--count", f"HEAD...{remote}/{branch}")
    ahead = behind = 0
    parts = rl.stdout.split()
    if rl.returncode == 0 and len(parts) == 2:
        ahead, behind = int(parts[0]), int(parts[1])
    return {"ok": True, "remote": remote, "branch": branch,
            "ahead": ahead, "behind": behind, "version": disk_version()}


def apply_update() -> dict:
    root = A.TOOL_ROOT
    info = check_update(fetch=True)
    if not info.get("ok"):
        return {"updated": False, "error": info.get("error")}
    if info["behind"] == 0:
        return {"updated": False, "message": "already up to date",
                "version": disk_version()}
    remote, branch = info["remote"], info["branch"]
    ff = _git(root, "merge", "--ff-only", f"{remote}/{branch}")
    if ff.returncode == 0:
        return {"updated": True, "behind": info["behind"],
                "version": disk_version(), "how": "fast-forward"}
    rb = _git(root, "pull", "--rebase", remote, branch)
    if rb.returncode == 0:
        return {"updated": True, "behind": info["behind"],
                "version": disk_version(), "how": "rebase"}
    _git(root, "rebase", "--abort")
    return {"updated": False,
            "error": "local history diverged; couldn't fast-forward or rebase "
                     "(resolve manually, e.g. `git pull --rebase`).",
            "detail": (rb.stderr or ff.stderr).strip()}


# --- backup (operates on DATA_ROOT) -----------------------------------------
def backup_config() -> dict:
    return A.load_selection().get("backup") or {}


def _ensure_remote(url: str):
    root = A.DATA_ROOT
    if _git(root, "remote", "get-url", BACKUP_REMOTE).returncode == 0:
        _git(root, "remote", "set-url", BACKUP_REMOTE, url)
    else:
        _git(root, "remote", "add", BACKUP_REMOTE, url)


def set_backup(url: str, branch: str | None = None) -> dict:
    sel = A.load_selection()
    b = sel.get("backup") or {}
    b.update({"enabled": True, "remote": url})
    if branch:
        b["branch"] = branch
    sel["backup"] = b
    A.save_selection(sel)
    _ensure_remote(url)
    return b


def disable_backup() -> None:
    sel = A.load_selection()
    b = sel.get("backup") or {}
    b["enabled"] = False
    sel["backup"] = b
    A.save_selection(sel)


def push_backup(commit_first: bool = True) -> dict:
    root = A.DATA_ROOT
    b = backup_config()
    url = b.get("remote")
    if not url:
        return {"ok": False,
                "error": "no backup repo set (skill-sync backup --set <git-url>)"}
    _ensure_remote(url)
    branch = b.get("branch") or _branch(root)
    if commit_first and _git(root, "status", "--porcelain").stdout.strip():
        _git(root, "add", "-A")
        _git(root, "commit", "-m", "skill-sync: backup")
    p = _git(root, "push", BACKUP_REMOTE, f"HEAD:{branch}")
    if p.returncode != 0:
        return {"ok": False, "error": p.stderr.strip(), "remote": url}
    return {"ok": True, "remote": url, "branch": branch}
