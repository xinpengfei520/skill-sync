"""One-time, idempotent migration to the consolidated ~/.skill-sync layout.

Before:
    ~/my-skills/            (DATA_ROOT: skills/ + config/)
    ~/.skill-sync-backups/  (backups)
    ~/.skill-sync/autosync.log

After:
    ~/.skill-sync/
    ├── skills/             the library (all skills live here)
    ├── config/             agents.json
    ├── tool/               the tool checkout (ignored by git)
    ├── backups/            ignored by git
    └── logs/               ignored by git

The data repo keeps its .git and remotes: relative paths inside the repo do not
change (skills/…, config/…), only the repo root moves up one level. Agent
symlinks that still point at the old root are repointed, and an installed
auto-sync job is rewritten so it no longer pins the old SKILL_SYNC_HOME or log
path.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from . import agents as A
from . import engine as E

OLD_BACKUPS = Path.home() / ".skill-sync-backups"
OLD_LOG = A.SKILL_SYNC_DIR / "autosync.log"
RESCHEDULE_MARKER = A.SKILL_SYNC_DIR / ".reschedule"


def _same(a, b) -> bool:
    return os.path.realpath(str(a)) == os.path.realpath(str(b))


def _conflicts(src: Path, dst: Path) -> list[str]:
    """Reasons the source tree cannot be merged into dst. Empty = safe."""
    out: list[str] = []
    if not dst.exists():
        return out
    for child in sorted(src.iterdir()):
        if child.name == ".DS_Store":
            continue
        target = dst / child.name
        if not target.exists():
            continue
        if child.name == ".git":
            out.append(f"{target} and {child} both contain a .git directory")
        elif child.is_dir() and target.is_dir() and child.name in ("skills", "config"):
            for sub in sorted(child.iterdir()):
                t = target / sub.name
                if not t.exists():
                    continue
                if sub.is_dir() and t.is_dir():
                    if E.hash_dir(sub) != E.hash_dir(t):
                        out.append(f"conflicting {child.name}/{sub.name}")
                elif sub.is_file() and t.is_file():
                    if sub.read_bytes() != t.read_bytes():
                        out.append(f"conflicting {child.name}/{sub.name}")
                else:
                    out.append(f"conflicting {child.name}/{sub.name}")
        elif child.is_file() and target.is_file():
            if child.read_bytes() != target.read_bytes():
                out.append(f"{target} exists with different content")
        else:
            out.append(f"{target} already exists")
    return out


def _links_into(old_root: Path) -> list[tuple[Path, Path]]:
    """(agent link, its current absolute target) pairs pointing into old_root."""
    found: list[tuple[Path, Path]] = []
    root = Path(os.path.realpath(old_root))
    for agent in A.all_agents():
        sd = agent["skills_dir"]
        if not agent["installed"] or not sd or not sd.is_dir():
            continue
        for entry in sd.iterdir():
            if not A.is_link(entry):
                continue
            raw = A.link_target(entry)
            if not raw:
                continue
            target = Path(os.path.realpath(entry))
            try:
                target.relative_to(root)
            except ValueError:
                continue
            found.append((entry, target))
    return found


def plan() -> dict:
    target = A.SKILL_SYNC_DIR
    current = A.DATA_ROOT
    p = {
        "target": str(target),
        "current": str(current),
        "data": None,
        "backups": None,
        "log": None,
        "scheduler": None,
        "home": None,
        "relink": [],
        "blockers": [],
        "warnings": [],
        "changes": False,
    }

    # --- data root ----------------------------------------------------------
    if os.environ.get("SKILL_SYNC_HOME"):
        p["warnings"].append(
            "SKILL_SYNC_HOME is set; leaving the data root where it points")
    elif _same(current, target):
        pass
    elif _same(current, A.TOOL_ROOT):
        p["warnings"].append(
            "combined checkout detected; keeping it (set SKILL_SYNC_HOME to split)")
    elif str(target).startswith(str(current) + os.sep):
        p["blockers"].append(
            f"{target} is inside the current data root {current}; move it manually")
    elif not current.is_dir():
        p["warnings"].append(f"data root {current} does not exist; nothing to move")
    else:
        conflicts = _conflicts(current, target)
        if conflicts:
            p["blockers"].extend(conflicts)
        else:
            p["data"] = {"src": str(current), "dst": str(target)}
            p["changes"] = True

    # --- backups ------------------------------------------------------------
    if OLD_BACKUPS.is_dir():
        p["backups"] = {"src": str(OLD_BACKUPS), "dst": str(A.BACKUP_ROOT)}
        p["changes"] = True

    # --- log ----------------------------------------------------------------
    new_log = A.LOG_DIR / "autosync.log"
    if OLD_LOG.is_file() and not new_log.exists():
        p["log"] = {"src": str(OLD_LOG), "dst": str(new_log)}
        p["changes"] = True

    # --- symlinks -----------------------------------------------------------
    if p["data"]:
        p["relink"] = _links_into(current)
        if p["relink"]:
            p["changes"] = True

    # --- scheduler ----------------------------------------------------------
    from . import scheduler
    sched = scheduler.read_installed()
    if sched:
        # Only rewrite the job when it still pins an old path. Otherwise every
        # command would look like "there is work to do" forever.
        stale = False
        if sched.get("home") and not _same(sched["home"], target):
            stale = True
        if sched.get("log") and not _same(sched["log"], new_log):
            stale = True
        if stale:
            p["scheduler"] = sched
            p["changes"] = True

    return p


def _move(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))


def _repoint_data_root(new_root: Path) -> None:
    """Update the in-process constants and the saved pointer."""
    A.DATA_ROOT = new_root
    A.SELECTION_FILE = new_root / "config" / "agents.json"
    A.DEFAULT_SKILLS_ROOT = new_root / "skills"
    if not os.environ.get("SKILL_SYNC_HOME"):
        A.SKILL_SYNC_DIR.mkdir(parents=True, exist_ok=True)
        A._HOME_FILE.write_text(str(new_root) + "\n", encoding="utf-8")


def _apply_data(src: Path, dst: Path) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    items = sorted(src.iterdir(), key=lambda x: (x.name != ".git", x.name))
    for child in items:
        if child.name == ".DS_Store":
            continue
        target = dst / child.name
        if not target.exists():
            _move(child, target)
        elif child.is_dir() and child.name in ("skills", "config"):
            # Conflicts were ruled out in plan(); identical duplicates are
            # parked under backups/pre-migration rather than deleted.
            for sub in sorted(child.iterdir()):
                t = target / sub.name
                if not t.exists():
                    _move(sub, t)
                else:
                    park = (A.BACKUP_ROOT / "pre-migration" / child.name
                            / sub.name)
                    _move(sub, park)
            try:
                child.rmdir()
            except OSError:
                pass
        else:
            park = A.BACKUP_ROOT / "pre-migration" / child.name
            _move(child, park)
    try:
        src.rmdir()
    except OSError:
        pass


def _apply_backups(src: Path, dst: Path) -> tuple[int, list[str]]:
    dst.mkdir(parents=True, exist_ok=True)
    moved, skipped = 0, []
    for child in sorted(src.iterdir()):
        t = dst / child.name
        if t.exists():
            skipped.append(child.name)
            continue
        _move(child, t)
        moved += 1
    try:
        src.rmdir()
    except OSError:
        pass
    return moved, skipped


def apply(p: dict, set_auto_commit: bool = False) -> dict:
    if p["blockers"]:
        return {"ok": False, "blockers": p["blockers"]}

    res = {"data": None, "backups": None, "log": False, "relinked": 0,
           "scheduler": None, "auto_commit": False, "warnings": []}

    if p["data"]:
        src, dst = Path(p["data"]["src"]), Path(p["data"]["dst"])
        _apply_data(src, dst)
        _repoint_data_root(dst)
        res["data"] = {"src": str(src), "dst": str(dst)}

    if p["backups"]:
        moved, skipped = _apply_backups(Path(p["backups"]["src"]),
                                        Path(p["backups"]["dst"]))
        res["backups"] = {"moved": moved, "skipped": skipped}

    if p["log"]:
        _move(Path(p["log"]["src"]), Path(p["log"]["dst"]))
        res["log"] = True

    old_root = Path(os.path.realpath(p["current"]))
    new_root = Path(os.path.realpath(p["target"]))
    for entry, target in p["relink"]:
        rel = target.relative_to(old_root)
        new_target = new_root / rel
        if not new_target.exists():
            if not target.exists():
                # The skill was already gone, so this link was dangling before
                # the migration; drop it instead of stranding it on the old path.
                if A.is_link(entry):
                    A.remove_link(entry)
                res["removed"] = res.get("removed", 0) + 1
            else:
                res["warnings"].append(f"no target for {entry} -> {new_target}")
            continue
        if A.is_link(entry):
            A.remove_link(entry)
        A.make_link(new_target, entry)
        res["relinked"] += 1

    if p["scheduler"]:
        from . import scheduler
        if scheduler.running_under_job():
            RESCHEDULE_MARKER.parent.mkdir(parents=True, exist_ok=True)
            RESCHEDULE_MARKER.write_text("pending\n", encoding="utf-8")
            res["scheduler"] = "deferred (running inside the job)"
        else:
            try:
                info = scheduler.refresh_from_installed()
                res["scheduler"] = info["interval"] if info else "not installed"
            except Exception as e:  # scheduler failure must not undo a migration
                res["scheduler"] = f"failed: {e}"

    if p["data"]:
        from . import maintenance
        maintenance.ensure_data_repo()

    if set_auto_commit:
        sel = A.load_selection()
        if sel.get("auto_commit") is not True:
            sel["auto_commit"] = True
            A.save_selection(sel)
            res["auto_commit"] = True

    return {"ok": True, **res}


def auto() -> dict | None:
    """Apply a safe migration at startup. Never runs with blockers."""
    if os.environ.get("SKILL_SYNC_NO_MIGRATE") == "1":
        return None
    if RESCHEDULE_MARKER.exists():
        try:
            from . import scheduler
            if not scheduler.running_under_job():
                scheduler.refresh_from_installed()
                RESCHEDULE_MARKER.unlink()
        except Exception:
            pass
    p = plan()
    if p["blockers"] or not p["changes"]:
        return None
    if p["data"]:
        print(f"skill-sync: migrating the library to {p['target']} …")
    res = apply(p, set_auto_commit=False)
    if res.get("ok"):
        if res.get("data"):
            extra = (f", {res['removed']} dangling link(s) removed"
                     if res.get("removed") else "")
            print(f"skill-sync: library moved to {res['data']['dst']} "
                  f"({res['relinked']} agent link(s) repointed{extra})")
        if res.get("backups"):
            print(f"skill-sync: backups moved to {A.BACKUP_ROOT}")
        if res.get("log"):
            print(f"skill-sync: logs moved to {A.LOG_DIR}")
        if res.get("scheduler"):
            print(f"skill-sync: auto-sync job refreshed ({res['scheduler']})")
    return res


# --- reporting --------------------------------------------------------------
def print_report(p: dict, apply: bool, result: dict | None = None) -> None:
    print(f"\nskill-sync migrate — {'APPLY' if apply else 'DRY-RUN'}")
    print(f"  target: {p['target']}")
    if p["data"]:
        print(f"  data root: {p['data']['src']} -> {p['data']['dst']}")
        if p["relink"]:
            print(f"  relink: {len(p['relink'])} agent symlink(s)")
    if p["backups"]:
        print(f"  backups: {p['backups']['src']} -> {p['backups']['dst']}")
    if p["log"]:
        print(f"  logs: {p['log']['src']} -> {p['log']['dst']}")
    if p["scheduler"]:
        print(f"  auto-sync: rewrite job ({p['scheduler']['seconds']}s, "
              f"commit={p['scheduler']['commit']}, push={p['scheduler']['push']})")
    for w in p["warnings"]:
        print(f"  note: {w}")
    for b in p["blockers"]:
        print(f"  BLOCKED: {b}")
    if result and result.get("ok"):
        print("\nDone.")
        if result.get("relinked"):
            print(f"  repointed {result['relinked']} agent link(s)")
        if result.get("removed"):
            print(f"  removed {result['removed']} already-dangling link(s)")
        if result.get("backups") and result["backups"]["skipped"]:
            print(f"  skipped existing backups: {', '.join(result['backups']['skipped'])}")
        if result.get("scheduler"):
            print(f"  scheduler: {result['scheduler']}")
        if result.get("auto_commit"):
            print("  auto_commit: true")
        for w in result.get("warnings", []):
            print(f"  warning: {w}")
    elif p["blockers"]:
        print("\nBlocked; nothing was changed.")
    elif not apply:
        if p["changes"]:
            print("\nNothing changed. Re-run with --apply to execute.")
        else:
            print("\nAlready on the consolidated layout — nothing to do.")
    else:
        print("\nAborted; nothing was changed.")
