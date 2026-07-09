"""Command-line interface: init / sync / uninstall / status / list / watch /
schedule / unschedule. Backward compatible: no subcommand (or a leading option)
means sync."""
from __future__ import annotations

import argparse
import sys

from . import __version__
from . import agents as A
from . import engine, runner, scheduler

KNOWN = {"init", "sync", "uninstall", "status", "list", "watch", "schedule",
         "unschedule", "update", "backup"}


class _C:
    _on = sys.stdout.isatty()
    B = "\033[1m" if _on else ""
    D = "\033[2m" if _on else ""
    G = "\033[32m" if _on else ""
    Y = "\033[33m" if _on else ""
    R = "\033[0m" if _on else ""


def _print_agents_table(only_installed: bool = False):
    sel = A.load_selection()
    enabled = sel.get("enabled", "all")
    enabled_set = None if enabled == "all" else set(enabled)
    print(f"{_C.B}{'AGENT':<12} {'INSTALLED':<10} {'MANAGED':<8} PATH{_C.R}")
    for a in A.all_agents():
        if only_installed and not a["installed"]:
            continue
        man = (enabled_set is None) or (a["name"] in enabled_set)
        ci, cm = (_C.G if a["installed"] else _C.D), (_C.G if man else _C.D)
        inst = ci + ("yes" if a["installed"] else "no").ljust(10) + _C.R
        mflag = cm + ("yes" if man else "no").ljust(8) + _C.R
        print(f"{a['name']:<12} {inst} {mflag} {_C.D}{a['skills_dir']}{_C.R}")


# --- commands ---------------------------------------------------------------
def cmd_list(args):
    print(f"{_C.B}Platform:{_C.R} {A.system_name()}   "
          f"{_C.B}Library:{_C.R} {A.skills_root()}\n")
    _print_agents_table()
    return 0


def cmd_status(args):
    from . import maintenance as M
    sel = A.load_selection()
    print(f"{_C.B}skill-sync v{M.disk_version()}{_C.R}")
    print(f"{_C.B}Platform:{_C.R} {A.system_name()}   "
          f"{_C.B}Library:{_C.R} {A.skills_root()}")
    st = scheduler.status()
    state = (f"{_C.G}active{_C.R}" if st.get("loaded")
             else (f"{_C.Y}installed (not loaded){_C.R}" if st.get("installed")
                   else f"{_C.D}off{_C.R}"))
    print(f"{_C.B}Auto-sync:{_C.R} {state}")
    info = M.check_update(fetch=False)  # offline: uses the last fetch
    behind = info.get("behind", 0)
    upd = (f"{_C.Y}{behind} behind (run: skill-sync update){_C.R}" if behind
           else f"{_C.G}up to date{_C.R}")
    print(f"{_C.B}Auto-update:{_C.R} {'on' if sel.get('auto_update') else 'off'}"
          f"  ({upd})")
    b = sel.get("backup") or {}
    bstate = (f"{_C.G}on{_C.R} -> {b.get('remote')}" if b.get("enabled") and
              b.get("remote") else f"{_C.D}off{_C.R}")
    print(f"{_C.B}Backup:{_C.R} {bstate}")
    print()
    _print_agents_table()
    print()
    runner.run_sync(apply=False, quiet=True)
    return 0


def cmd_update(args):
    from . import maintenance as M
    if args.check:
        info = M.check_update(fetch=True)
        if not info.get("ok"):
            print(f"{_C.Y}Update check failed:{_C.R} {info.get('error')}")
            return 2
        if info["behind"] == 0:
            print(f"{_C.G}Up to date{_C.R} (v{info['version']}).")
        else:
            print(f"{_C.Y}Update available:{_C.R} {info['behind']} commit(s) behind "
                  f"{info['remote']}/{info['branch']} — run `skill-sync update`.")
        return 0
    res = M.apply_update()
    if res.get("updated"):
        print(f"{_C.G}Updated to v{res['version']}{_C.R} "
              f"({res['how']}, {res['behind']} commit(s)).")
    elif res.get("error"):
        print(f"{_C.Y}Update failed:{_C.R} {res['error']}")
        return 2
    else:
        print(f"{_C.G}{res.get('message', 'already up to date')}{_C.R} "
              f"(v{res.get('version', __version__)}).")
    return 0


def cmd_backup(args):
    from . import maintenance as M
    if args.disable:
        M.disable_backup()
        print("Backup disabled.")
        return 0
    if args.set:
        M.set_backup(args.set, branch=args.branch)
        print(f"{_C.G}Backup repo set:{_C.R} {args.set}")
        res = M.push_backup()
        print(f"  {'pushed ✓' if res.get('ok') else 'push failed: ' + str(res.get('error'))}")
        return 0 if res.get("ok") else 2
    b = M.backup_config()
    if not b.get("remote"):
        print("No backup repo configured. Set one: "
              "skill-sync backup --set <git-url>")
        return 1
    res = M.push_backup()
    if res.get("ok"):
        print(f"{_C.G}Backed up{_C.R} to {res['remote']} ({res['branch']}).")
        return 0
    print(f"{_C.Y}Backup failed:{_C.R} {res.get('error')}")
    return 2


def cmd_init(args):
    installed = [a for a in A.all_agents() if a["installed"]]
    if not installed:
        print("No known agents detected on this machine.")
        return 1

    chosen: list[str]
    if args.all:
        chosen = [a["name"] for a in installed]
    elif args.agents:
        want = {x.strip() for x in args.agents.split(",") if x.strip()}
        chosen = [a["name"] for a in installed if a["name"] in want]
        missing = want - set(chosen)
        if missing:
            print(f"{_C.Y}Not detected as installed (skipped):{_C.R} "
                  f"{', '.join(sorted(missing))}")
    elif sys.stdin.isatty() and not args.yes:
        print(f"{_C.B}Detected installed agents:{_C.R}")
        for i, a in enumerate(installed, 1):
            print(f"  {i:>2}. {a['name']:<12} {_C.D}{a['display']}{_C.R}")
        raw = input("\nSync which? comma-separated numbers, or 'all' "
                    "[all]: ").strip().lower()
        if raw in ("", "all", "a"):
            chosen = [a["name"] for a in installed]
        else:
            idxs = {int(x) for x in raw.replace(" ", "").split(",") if x.isdigit()}
            chosen = [a["name"] for i, a in enumerate(installed, 1) if i in idxs]
    else:
        chosen = [a["name"] for a in installed]  # --yes / non-interactive default

    if not chosen:
        print("Nothing selected.")
        return 1

    sel = A.load_selection()
    sel["enabled"] = chosen
    if args.adopt_external is not None:
        sel["adopt_external"] = args.adopt_external
    A.save_selection(sel)
    print(f"\n{_C.G}Saved selection:{_C.R} {', '.join(chosen)}")
    print(f"{_C.D}(config/agents.json){_C.R}\n")

    return runner.run_sync(apply=args.apply, adopt_external=args.adopt_external,
                           do_backup=not args.no_backup)


def cmd_sync(args):
    return runner.run_sync(
        apply=args.apply, adopt_external=args.adopt_external,
        do_backup=not args.no_backup, only=args.agent,
        commit=args.commit or None, push=args.push or None,
        quiet=args.quiet, as_json=args.json, self_update=args.self_update)


def cmd_uninstall(args):
    names = [n.strip() for n in args.skill if n and n.strip()]
    if not names:
        print("Nothing to uninstall. Usage: skill-sync uninstall <skill> ...")
        return 1

    # Scan every *installed* agent (not just managed ones) so leftover links are
    # reclaimed even from agents the user later stopped managing.
    plan = engine.build_uninstall_plan(A.all_agents(), names)
    if args.apply:
        engine.execute_uninstall(plan, do_backup=not args.no_backup)
    engine.report_uninstall(plan, apply=args.apply, do_backup=not args.no_backup)

    changed = args.apply and (plan["remove_lib"] or plan["remove_links"])
    if changed and args.commit:
        msg = runner.git_commit_push(
            "skill-sync: uninstall " + ", ".join(names), push=args.push)
        print(f"  git: {msg}")
    elif changed and not args.commit:
        print(f"\n  Review & commit in {A.DATA_ROOT}:")
        print(f"  git -C {A.DATA_ROOT} add -A && "
              f"git -C {A.DATA_ROOT} commit -m 'uninstall skills'")

    # 0 when something was (or would be) removed; 1 when nothing matched.
    return 0 if (plan["remove_lib"] or plan["remove_links"]) else 1


def cmd_watch(args):
    return scheduler.watch(args.interval, adopt_external=args.adopt_external,
                           commit=args.commit or None, push=args.push or None)


def cmd_schedule(args):
    if args.auto_update is not None:
        sel = A.load_selection()
        sel["auto_update"] = args.auto_update
        A.save_selection(sel)
    try:
        info = scheduler.schedule(args.interval, commit=args.commit, push=args.push)
    except Exception as e:
        print(f"{_C.Y}Could not install scheduler:{_C.R} {e}", file=sys.stderr)
        return 2
    print(f"{_C.G}Auto-sync every {info['interval']}{_C.R} "
          f"(commit={info['commit']}, push={info['push']}).")
    print(f"  job: {info['path']}")
    print(f"  log: {info['log']}")
    print(f"  stop with: skill-sync unschedule")
    return 0


def cmd_unschedule(args):
    removed = scheduler.unschedule()
    print("Auto-sync removed." if removed else "No auto-sync job was installed.")
    return 0


# --- parser -----------------------------------------------------------------
def build_parser():
    p = argparse.ArgumentParser(
        prog="skill-sync",
        description="One source of truth for AI-agent Skills; mirror via symlinks.")
    p.add_argument("--version", action="version", version=f"skill-sync {__version__}")
    sub = p.add_subparsers(dest="cmd")

    def add_sync_flags(sp):
        sp.add_argument("--apply", action="store_true", help="execute (default: dry-run)")
        sp.add_argument("--adopt-external", action=argparse.BooleanOptionalAction,
                        default=None, help="centralize skills symlinked to outside hubs")
        sp.add_argument("--no-backup", action="store_true",
                        help="don't back up removed duplicates")

    sp = sub.add_parser("sync", help="collect + mirror (dry-run unless --apply)")
    add_sync_flags(sp)
    sp.add_argument("--agent", action="append", metavar="NAME", help="limit to agent(s)")
    sp.add_argument("--commit", action="store_true", help="git commit after applying")
    sp.add_argument("--push", action="store_true", help="git push after committing")
    sp.add_argument("--self-update", action="store_true",
                    help="pull the latest tool code before syncing")
    sp.add_argument("--quiet", action="store_true")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_sync)

    sp = sub.add_parser("uninstall",
                        help="remove skill(s) from the library and every agent "
                             "(dry-run unless --apply)")
    sp.add_argument("skill", nargs="+", metavar="SKILL", help="skill name(s) to remove")
    sp.add_argument("--apply", action="store_true", help="execute (default: dry-run)")
    sp.add_argument("--no-backup", action="store_true",
                    help="don't back up the removed library copy")
    sp.add_argument("--commit", action="store_true", help="git commit after applying")
    sp.add_argument("--push", action="store_true", help="git push after committing")
    sp.set_defaults(func=cmd_uninstall)

    sp = sub.add_parser("init", help="detect agents, choose which to manage, save config")
    sp.add_argument("--all", action="store_true", help="manage all installed agents")
    sp.add_argument("--agents", metavar="a,b,c", help="comma-separated agent names")
    sp.add_argument("--yes", action="store_true", help="non-interactive; accept all installed")
    add_sync_flags(sp)
    sp.set_defaults(func=cmd_init)

    sp = sub.add_parser("status", help="show platform, agents, auto-sync, and a dry-run")
    sp.set_defaults(func=cmd_status)

    sp = sub.add_parser("list", help="list all known agents and their state")
    sp.set_defaults(func=cmd_list)

    sp = sub.add_parser("watch", help="run sync on an interval in the foreground")
    sp.add_argument("--interval", default="10m", help="e.g. 1m, 10m, 1h, 24h")
    sp.add_argument("--adopt-external", action=argparse.BooleanOptionalAction, default=None)
    sp.add_argument("--commit", action="store_true")
    sp.add_argument("--push", action="store_true")
    sp.set_defaults(func=cmd_watch)

    sp = sub.add_parser("schedule", help="install a native OS timer for auto-sync")
    sp.add_argument("--interval", required=True, help="e.g. 1m, 10m, 1h, 12h, 24h")
    sp.add_argument("--commit", action=argparse.BooleanOptionalAction, default=True,
                    help="git commit on each run (default: on)")
    sp.add_argument("--push", action=argparse.BooleanOptionalAction, default=True,
                    help="git push on each run (default: on)")
    sp.add_argument("--auto-update", action=argparse.BooleanOptionalAction,
                    default=None, help="self-update the tool before each run")
    sp.set_defaults(func=cmd_schedule)

    sp = sub.add_parser("unschedule", help="remove the auto-sync timer")
    sp.set_defaults(func=cmd_unschedule)

    sp = sub.add_parser("update", help="update the tool to the latest version (git pull)")
    sp.add_argument("--check", action="store_true", help="only check, don't apply")
    sp.set_defaults(func=cmd_update)

    sp = sub.add_parser("backup", help="back up your skills to a configured Git repo")
    sp.add_argument("--set", metavar="GIT_URL", help="set & enable the backup repo, then push")
    sp.add_argument("--branch", metavar="NAME", help="branch to push to (default: current)")
    sp.add_argument("--disable", action="store_true", help="turn backup off")
    sp.set_defaults(func=cmd_backup)

    return p


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    # Backward compat: no subcommand, or a leading option, means `sync`.
    if not argv:
        argv = ["sync"]
    elif argv[0] not in KNOWN and argv[0] not in ("-h", "--help", "--version"):
        argv = ["sync"] + argv

    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 0
    return args.func(args)
