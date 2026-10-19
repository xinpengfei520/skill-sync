"""Collect + full-mirror engine.

Given a list of resolved agents, collect their source-installed skills into the
central library and mirror every library skill back into every installed agent
via symlinks. Dry-run unless executed. Idempotent. Never overwrites a real
directory or a conflicting skill.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import os
import shutil
import sys
from pathlib import Path

from . import agents as A


# --- content hashing --------------------------------------------------------
def hash_dir(path: Path) -> str:
    h = hashlib.sha256()
    entries: list[tuple[str, Path]] = []
    for root, dirs, files in os.walk(path):
        dirs.sort()
        for fn in files:
            if fn == ".DS_Store":
                continue
            fp = Path(root) / fn
            entries.append((fp.relative_to(path).as_posix(), fp))
    for rel, fp in sorted(entries):
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        try:
            if fp.is_symlink():
                h.update(b"L:" + os.readlink(fp).encode("utf-8"))
            else:
                with open(fp, "rb") as f:
                    for chunk in iter(lambda: f.read(1 << 16), b""):
                        h.update(chunk)
        except OSError:
            h.update(b"<unreadable>")
        h.update(b"\0")
    return h.hexdigest()


def is_skill_dir(path: Path) -> bool:
    return path.is_dir() and (path / "SKILL.md").is_file()


def _points_into(link: Path, root: Path) -> bool:
    try:
        real = Path(os.path.realpath(link))
    except OSError:
        return False
    try:
        return real.is_relative_to(root)
    except AttributeError:
        return str(real).startswith(str(root) + os.sep)


def library_skills(library: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not library.is_dir():
        return out
    for child in sorted(library.iterdir()):
        if child.name in A.IGNORE_NAMES or child.name.startswith("."):
            continue
        if is_skill_dir(child):
            out[child.name] = hash_dir(child)
    return out


# --- planning ---------------------------------------------------------------
def build_plan(agent_list: list[dict], adopt_external: bool,
               library: Path | None = None) -> dict:
    library = library or A.skills_root()
    lib = library_skills(library)
    planned_from: dict[str, str] = {}

    collect, dedupe, adopt = [], [], []
    conflicts, external, non_skill = [], [], []
    will_empty: set[tuple[str, str]] = set()

    installed = [a for a in agent_list if a["installed"]]

    # Phase A: collect
    for agent in installed:
        sd = agent["skills_dir"]
        if not sd or not sd.is_dir():
            continue
        for entry in sorted(sd.iterdir()):
            name = entry.name
            if name in A.IGNORE_NAMES or name.startswith("."):
                continue
            if A.is_link(entry):
                if _points_into(entry, library):
                    continue
                target = Path(os.path.realpath(entry))
                if adopt_external and is_skill_dir(target) and name not in lib:
                    adopt.append({"agent": agent["name"], "name": name, "target": target})
                    lib[name] = hash_dir(target)
                    planned_from[name] = agent["name"]
                    # NOT will_empty: the source symlink still points at the hub
                    # and must be *repointed* (relink) in the mirror phase.
                else:
                    external.append({"agent": agent["name"], "name": name,
                                     "target": A.link_target(entry) or str(target)})
                continue
            if not entry.is_dir():
                continue
            if not is_skill_dir(entry):
                non_skill.append({"agent": agent["name"], "name": name})
                continue
            h = hash_dir(entry)
            if name not in lib:
                collect.append({"agent": agent["name"], "name": name, "src": entry})
                lib[name] = h
                planned_from[name] = agent["name"]
                will_empty.add((agent["name"], name))
            elif h == lib[name]:
                dedupe.append({"agent": agent["name"], "name": name, "src": entry})
                will_empty.add((agent["name"], name))
            else:
                conflicts.append({
                    "agent": agent["name"], "name": name, "src": entry,
                    "agent_hash": h, "canonical_hash": lib[name],
                    "canonical_from": planned_from.get(name, "library")})

    # Phase B: mirror
    links, relinks, already, blocked, ensure_dirs = [], [], [], [], []
    final_names = sorted(lib.keys())
    for agent in installed:
        sd = agent["skills_dir"]
        if not sd:
            continue
        if not sd.exists():
            ensure_dirs.append({"agent": agent["name"], "path": sd})
        for name in final_names:
            dst = sd / name
            desired = library / name
            if (agent["name"], name) in will_empty:
                links.append({"agent": agent["name"], "name": name, "dst": dst})
                continue
            if A.is_link(dst):
                if os.path.realpath(dst) == str(desired.resolve()) or (
                        _points_into(dst, library)
                        and Path(os.path.realpath(dst)).name == name):
                    already.append({"agent": agent["name"], "name": name})
                elif adopt_external and name in lib:
                    relinks.append({"agent": agent["name"], "name": name,
                                    "dst": dst, "old": A.link_target(dst)})
                else:
                    already.append({"agent": agent["name"], "name": name, "note": "external"})
            elif dst.exists():
                blocked.append({"agent": agent["name"], "name": name, "dst": dst})
            else:
                links.append({"agent": agent["name"], "name": name, "dst": dst})

    return {
        "library": library,
        "collect": collect, "dedupe": dedupe, "adopt": adopt,
        "conflicts": conflicts, "external": external, "non_skill": non_skill,
        "links": links, "relinks": relinks, "already": already,
        "blocked": blocked, "ensure_dirs": ensure_dirs,
        "final_names": final_names, "installed": installed,
        "not_installed": [a for a in agent_list if not a["installed"]],
    }


# --- execution --------------------------------------------------------------
def execute(plan: dict, do_backup: bool) -> None:
    library = plan["library"]
    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_dir = A.BACKUP_ROOT / stamp
    library.mkdir(parents=True, exist_ok=True)

    for item in plan["ensure_dirs"]:
        item["path"].mkdir(parents=True, exist_ok=True)
    for item in plan["collect"]:
        shutil.move(str(item["src"]), str(library / item["name"]))
    for item in plan["adopt"]:
        shutil.copytree(item["target"], library / item["name"],
                        symlinks=True, dirs_exist_ok=False)
    for item in plan["dedupe"]:
        if do_backup:
            bdst = backup_dir / item["agent"] / item["name"]
            bdst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(item["src"], bdst, symlinks=True)
        shutil.rmtree(item["src"])
    for item in plan["relinks"]:
        dst = item["dst"]
        if A.is_link(dst) or dst.exists():
            A.remove_link(dst) if A.is_link(dst) else dst.unlink()
        A.make_link(library / item["name"], dst)
    for item in plan["links"]:
        dst = item["dst"]
        dst.parent.mkdir(parents=True, exist_ok=True)
        if A.is_link(dst) and not dst.exists():   # stale/broken link
            A.remove_link(dst)
        if not dst.exists() and not A.is_link(dst):
            A.make_link(library / item["name"], dst)


# --- reporting --------------------------------------------------------------
class _C:
    _on = sys.stdout.isatty()
    RESET = "\033[0m" if _on else ""
    BOLD = "\033[1m" if _on else ""
    DIM = "\033[2m" if _on else ""
    RED = "\033[31m" if _on else ""
    GREEN = "\033[32m" if _on else ""
    YELLOW = "\033[33m" if _on else ""
    BLUE = "\033[34m" if _on else ""
    CYAN = "\033[36m" if _on else ""


def report(plan: dict, apply: bool, do_backup: bool, quiet: bool = False) -> None:
    C = _C
    n = {k: len(plan[k]) for k in
         ("collect", "dedupe", "adopt", "conflicts", "external",
          "non_skill", "links", "relinks", "blocked")}
    if quiet:
        changed = n["collect"] + n["adopt"] + n["dedupe"] + n["links"] + n["relinks"]
        print(f"skill-sync: {'applied' if apply else 'dry-run'} — "
              f"{len(plan['final_names'])} skills, {changed} changes, "
              f"{n['conflicts']} conflicts")
        return

    verb = "" if apply else "would "
    print(f"\n{C.BOLD}skill-sync — {'APPLY' if apply else 'DRY-RUN'}{C.RESET}")
    print(f"{C.DIM}library: {plan['library']}{C.RESET}")
    ins = ", ".join(a["name"] for a in plan["installed"])
    print(f"{C.DIM}managed & installed: {ins or '(none)'}{C.RESET}")
    if plan["not_installed"]:
        ni = ", ".join(a["name"] for a in plan["not_installed"])
        print(f"{C.DIM}enabled but not installed (skipped): {ni}{C.RESET}")

    def section(title, items, color, fmt):
        if not items:
            return
        print(f"\n{color}{C.BOLD}{title} ({len(items)}){C.RESET}")
        for it in items:
            print("  " + fmt(it))

    section(f"COLLECT — {verb}move into library", plan["collect"], C.GREEN,
            lambda i: f"{i['name']:<28} {C.DIM}from {i['agent']}{C.RESET}")
    section(f"ADOPT — {verb}centralize external symlink", plan["adopt"], C.GREEN,
            lambda i: f"{i['name']:<28} {C.DIM}from {i['agent']}{C.RESET}")
    section(f"DEDUPE — {verb}remove identical copy"
            + ("" if not do_backup else " (backed up)"), plan["dedupe"], C.CYAN,
            lambda i: f"{i['name']:<28} {C.DIM}in {i['agent']}{C.RESET}")
    section(f"LINK — {verb}create symlink", plan["links"], C.BLUE,
            lambda i: f"{i['agent']}/{i['name']}")
    section(f"RELINK — {verb}repoint to library", plan["relinks"], C.BLUE,
            lambda i: f"{i['agent']}/{i['name']} {C.DIM}(was {i['old']}){C.RESET}")
    section("CONFLICT — different content, LEFT UNTOUCHED", plan["conflicts"], C.RED,
            lambda i: f"{i['name']:<28} {C.DIM}{i['agent']} differs from "
                      f"{i['canonical_from']}; {i['agent_hash'][:8]} vs "
                      f"{i['canonical_hash'][:8]}{C.RESET}")
    section("BLOCKED — real dir in the way, not overwritten", plan["blocked"],
            C.YELLOW, lambda i: f"{i['agent']}/{i['name']}")
    section("EXTERNAL — symlink to outside hub, left as-is "
            "(use --adopt-external)", plan["external"], C.YELLOW,
            lambda i: f"{i['agent']}/{i['name']} {C.DIM}-> {i['target']}{C.RESET}")
    section("NOT A SKILL — dir without SKILL.md, skipped", plan["non_skill"],
            C.DIM, lambda i: f"{i['agent']}/{i['name']}")

    print(f"\n{C.BOLD}Summary{C.RESET}")
    print(f"  library skills after sync : {len(plan['final_names'])}")
    print(f"  collect {n['collect']}  adopt {n['adopt']}  dedupe {n['dedupe']}  "
          f"link {n['links']}  relink {n['relinks']}")
    print(f"  {C.RED}conflicts {n['conflicts']}{C.RESET}  "
          f"{C.YELLOW}blocked {n['blocked']}  external {n['external']}{C.RESET}  "
          f"already-ok {len(plan['already'])}")
    if not apply:
        print(f"\n{C.BOLD}Nothing changed.{C.RESET} Re-run with "
              f"{C.BOLD}--apply{C.RESET} to execute.")
    else:
        print(f"\n{C.GREEN}{C.BOLD}Done.{C.RESET}")
    if plan["conflicts"]:
        print(f"\n{C.RED}⚠ {len(plan['conflicts'])} conflict(s) need manual "
              f"review — those copies were left exactly as they were.{C.RESET}")


def has_conflicts(plan: dict) -> bool:
    return bool(plan["conflicts"])


# --- uninstall --------------------------------------------------------------
def build_uninstall_plan(agent_list: list[dict], names: list[str],
                         library: Path | None = None) -> dict:
    """Plan removal of one or more skills: delete each from the library and
    remove every mirrored symlink that points into the library. Real
    directories and links to outside hubs are reported and left untouched.
    Also reclaims dangling links left behind by a skill already gone from the
    library (orphan cleanup for a specific name)."""
    library = library or A.skills_root()
    lib = library_skills(library)
    installed = [a for a in agent_list if a["installed"]]

    remove_lib, remove_links, skipped, not_found = [], [], [], []
    seen: list[str] = []
    for name in names:
        if name in seen:
            continue
        seen.append(name)
        if name in lib:
            remove_lib.append({"name": name, "src": library / name})
        else:
            not_found.append({"name": name})
        desired = str((library / name).resolve())
        for agent in installed:
            sd = agent["skills_dir"]
            if not sd or not sd.is_dir():
                continue
            dst = sd / name
            if A.is_link(dst):
                real = os.path.realpath(dst)
                if real == desired or (_points_into(dst, library)
                                       and Path(real).name == name):
                    remove_links.append({"agent": agent["name"], "name": name,
                                         "dst": dst})
                elif _points_into(dst, library):
                    skipped.append({"agent": agent["name"], "name": name,
                                    "why": "link into library, different target"})
                else:
                    skipped.append({"agent": agent["name"], "name": name,
                                    "why": "external -> "
                                           + (A.link_target(dst) or real)})
            elif dst.exists():
                skipped.append({"agent": agent["name"], "name": name,
                                "why": "real directory"})

    return {"library": library, "remove_lib": remove_lib,
            "remove_links": remove_links, "skipped": skipped,
            "not_found": not_found, "installed": installed}


def execute_uninstall(plan: dict, do_backup: bool) -> None:
    library = plan["library"]
    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_dir = A.BACKUP_ROOT / ("uninstall-" + stamp)

    # Remove mirrored links first so deleting the library copy can't strand them.
    for item in plan["remove_links"]:
        dst = item["dst"]
        if A.is_link(dst):
            A.remove_link(dst)
    for item in plan["remove_lib"]:
        src = item["src"]
        if do_backup and src.is_dir() and not A.is_link(src):
            bdst = backup_dir / item["name"]
            bdst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(src, bdst, symlinks=True)
        if A.is_link(src):
            A.remove_link(src)
        elif src.is_dir():
            shutil.rmtree(src)


def report_uninstall(plan: dict, apply: bool, do_backup: bool,
                     quiet: bool = False) -> None:
    C = _C
    lib, links = plan["remove_lib"], plan["remove_links"]
    skipped, missing = plan["skipped"], plan["not_found"]
    if quiet:
        print(f"skill-sync uninstall: {'applied' if apply else 'dry-run'} — "
              f"{len(lib)} library skill(s), {len(links)} link(s), "
              f"{len(skipped)} skipped")
        return

    verb = "" if apply else "would "
    print(f"\n{C.BOLD}skill-sync uninstall — {'APPLY' if apply else 'DRY-RUN'}"
          f"{C.RESET}")
    print(f"{C.DIM}library: {plan['library']}{C.RESET}")

    def section(title, items, color, fmt):
        if not items:
            return
        print(f"\n{color}{C.BOLD}{title} ({len(items)}){C.RESET}")
        for it in items:
            print("  " + fmt(it))

    section(f"REMOVE — {verb}delete from library"
            + ("" if not do_backup else " (backed up)"), lib, C.RED,
            lambda i: f"{i['name']:<28} {C.DIM}{i['src']}{C.RESET}")
    section(f"UNLINK — {verb}remove mirrored symlink", links, C.BLUE,
            lambda i: f"{i['agent']}/{i['name']}")
    section("SKIPPED — real dir / external link, LEFT UNTOUCHED", skipped,
            C.YELLOW, lambda i: f"{i['agent']}/{i['name']} "
                                f"{C.DIM}({i['why']}){C.RESET}")
    section("NOT IN LIBRARY — no central copy to remove", missing, C.DIM,
            lambda i: f"{i['name']}")

    print(f"\n{C.BOLD}Summary{C.RESET}")
    print(f"  remove {len(lib)}  unlink {len(links)}  "
          f"skipped {len(skipped)}  not-in-library {len(missing)}")
    if not apply:
        print(f"\n{C.BOLD}Nothing changed.{C.RESET} Re-run with "
              f"{C.BOLD}--apply{C.RESET} to execute.")
    else:
        print(f"\n{C.GREEN}{C.BOLD}Done.{C.RESET}")


# --- prune one agent --------------------------------------------------------
def build_prune_agent_plan(agent: dict, library: Path | None = None) -> dict:
    """Plan removal of one agent's symlinks that point into the library.

    Used when an agent stops being managed: its mirrored links otherwise stay
    behind as orphans. Real directories and links to outside hubs are reported
    and left untouched — only library-pointing symlinks are reclaimed."""
    library = library or A.skills_root()
    sd = agent["skills_dir"]
    remove, skipped = [], []
    if sd and sd.is_dir():
        for entry in sorted(sd.iterdir()):
            if entry.name in A.IGNORE_NAMES or entry.name.startswith("."):
                continue
            if A.is_link(entry):
                if _points_into(entry, library):
                    remove.append({"agent": agent["name"], "name": entry.name,
                                   "dst": entry})
                else:
                    skipped.append({
                        "agent": agent["name"], "name": entry.name,
                        "why": "external -> "
                               + (A.link_target(entry) or os.path.realpath(entry))})
            elif entry.is_dir():
                skipped.append({"agent": agent["name"], "name": entry.name,
                                "why": "real directory"})
    return {"library": library, "agent": agent, "remove": remove,
            "skipped": skipped}


def execute_prune(plan: dict) -> None:
    for item in plan["remove"]:
        if A.is_link(item["dst"]):
            A.remove_link(item["dst"])


def report_prune(plan: dict, apply: bool, quiet: bool = False) -> None:
    C = _C
    rem, skipped = plan["remove"], plan["skipped"]
    agent = plan["agent"]
    if quiet:
        print(f"skill-sync agent prune: {'applied' if apply else 'dry-run'} — "
              f"{len(rem)} link(s), {len(skipped)} skipped")
        return

    verb = "" if apply else "would "
    print(f"\n{C.BOLD}skill-sync agent prune — {'APPLY' if apply else 'DRY-RUN'}"
          f"{C.RESET}")
    print(f"{C.DIM}agent: {agent['name']}  dir: {agent['skills_dir']}{C.RESET}")

    def section(title, items, color, fmt):
        if not items:
            return
        print(f"\n{color}{C.BOLD}{title} ({len(items)}){C.RESET}")
        for it in items:
            print("  " + fmt(it))

    section(f"UNLINK — {verb}remove link into library", rem, C.BLUE,
            lambda i: f"{i['name']}")
    section("SKIPPED — real dir / external link, LEFT UNTOUCHED", skipped,
            C.YELLOW,
            lambda i: f"{i['name']} {C.DIM}({i['why']}){C.RESET}")

    print(f"\n{C.BOLD}Summary{C.RESET}")
    print(f"  unlink {len(rem)}  skipped {len(skipped)}")
    if not apply:
        print(f"\n{C.BOLD}Nothing changed.{C.RESET} Re-run with "
              f"{C.BOLD}--apply{C.RESET} to execute.")
    else:
        print(f"\n{C.GREEN}{C.BOLD}Done.{C.RESET}")
