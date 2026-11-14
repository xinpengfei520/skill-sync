"""Tool self-update (git pull the TOOL repo) and optional backup of the skills
library (push the DATA repo to a user-configured Git remote). These are two
different repositories once the tool and skills are split apart."""
from __future__ import annotations

import datetime as _dt
import hashlib
import re
import shutil
import subprocess

from . import __version__
from . import agents as A

BACKUP_REMOTE = "skillsync-backup"


def _git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args],
                          capture_output=True, text=True)


def git_available() -> bool:
    return shutil.which("git") is not None


def _is_repo(root) -> bool:
    return _git(root, "rev-parse", "--is-inside-work-tree").stdout.strip() == "true"


def ensure_data_repo() -> bool:
    """Make DATA_ROOT a git repo, and keep skill-sync's own state out of it.

    Only needed when the library is the consolidated ~/.skill-sync directory:
    tool/, backups/, logs/ and the `home` pointer live next to skills/ and must
    never be committed."""
    if not git_available():
        return False
    root = A.DATA_ROOT
    root.mkdir(parents=True, exist_ok=True)
    if not _is_repo(root):
        _git(root, "init", "-q")
    if root == A.SKILL_SYNC_DIR:
        ignore = root / ".gitignore"
        text = ignore.read_text(encoding="utf-8") if ignore.is_file() else ""
        lines = set(text.splitlines())
        missing = [x for x in A.STATE_IGNORE_LINES if x not in lines]
        if missing:
            if text and not text.endswith("\n"):
                text += "\n"
            text += ("\n# skill-sync managed state — never part of the skills repo\n"
                     + "\n".join(missing) + "\n")
            ignore.write_text(text, encoding="utf-8")
    return True


def commit_local(message: str) -> str:
    """Commit the data repo locally. Never pushes. No-op without git."""
    if not git_available():
        return "skipped (git not installed — files stay local)"
    if not ensure_data_repo():
        return "skipped (not a git repo)"
    root = A.DATA_ROOT
    _git(root, "add", "-A")
    if not _git(root, "status", "--porcelain").stdout.strip():
        return "nothing to commit"
    c = _git(root, "commit", "-m", message)
    if c.returncode != 0:
        first = (c.stderr.strip().splitlines() or ["unknown error"])[0]
        return f"commit failed: {first}"
    return "committed locally"


def has_push_remote() -> bool:
    if not git_available():
        return False
    b = backup_config()
    if b.get("enabled") and b.get("remote"):
        return True
    return _git(A.DATA_ROOT, "remote", "get-url", "origin").returncode == 0


def push_origin() -> str:
    """Push the data repo to origin, if there is one."""
    if not git_available():
        return "push skipped (git not installed)"
    if _git(A.DATA_ROOT, "remote", "get-url", "origin").returncode != 0:
        return "no origin remote (committed locally)"
    # `-u` also sets the upstream on the first push, so plain `git push` works
    # from then on.
    p = _git(A.DATA_ROOT, "push", "-u", "origin", "HEAD")
    if p.returncode != 0:
        first = (p.stderr.strip().splitlines() or ["unknown error"])[0]
        return f"push failed: {first}"
    return "pushed to origin"


def _branch(root) -> str:
    b = _git(root, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    return b if b and b != "HEAD" else "main"


def _hash_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def sync_bundled_skill() -> str | None:
    """Keep the library's `skill-sync` copy equal to the tool's bundled one.

    The tool version is authoritative: when the content differs, the old copy is
    moved to BACKUP_ROOT/bundled-skill-<stamp>/ first, so a customization is
    never lost silently. Symlinked or missing sources are left alone."""
    src = A.TOOL_ROOT / "skills" / "skill-sync"
    src_md = src / "SKILL.md"
    if not src_md.is_file():
        return None
    dst = A.skills_root() / "skill-sync"
    if A.is_link(dst):
        return None  # the user linked it somewhere; don't replace a link
    if not dst.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dst, ignore=shutil.ignore_patterns(".DS_Store"))
        return "installed the bundled skill-sync skill"
    dst_md = dst / "SKILL.md"
    if dst_md.is_file() and _hash_file(dst_md) == _hash_file(src_md):
        return None
    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = A.BACKUP_ROOT / f"bundled-skill-{stamp}" / "skill-sync"
    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(dst), str(backup))
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns(".DS_Store"))
    return f"refreshed the bundled skill-sync skill (previous copy: {backup})"


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
    if not git_available():
        return {"ok": False, "error": "git is not installed"}
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
