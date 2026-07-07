"""Orchestrates one sync run: resolve agents -> plan -> (execute) -> report,
with optional git commit/push. Shared by the CLI and the scheduler/watch loop."""
from __future__ import annotations

import json
import os
import subprocess
import sys

from . import agents as A
from . import engine


def git_commit_push(message: str, push: bool) -> str:
    repo = A.DATA_ROOT
    def git(*args):
        return subprocess.run(["git", "-C", str(repo), *args],
                              capture_output=True, text=True)
    git("add", "-A")
    status = git("status", "--porcelain")
    if not status.stdout.strip():
        return "nothing to commit"
    c = git("commit", "-m", message)
    if c.returncode != 0:
        return f"commit failed: {c.stderr.strip()}"
    if push:
        p = git("push")
        if p.returncode != 0:
            return f"committed; push failed: {p.stderr.strip()}"
        return "committed and pushed"
    return "committed"


def run_sync(*, apply: bool, adopt_external: bool | None = None,
             do_backup: bool = True, only=None, commit: bool | None = None,
             push: bool | None = None, quiet: bool = False,
             as_json: bool = False, self_update: bool = False) -> int:
    # Self-update first (used by the scheduled job): pull the latest tool code,
    # then re-exec so the new code runs this sync. Guarded against re-exec loops.
    if self_update and not os.environ.get("SKILLSYNC_REEXEC"):
        from . import maintenance
        if maintenance.apply_update().get("updated"):
            os.environ["SKILLSYNC_REEXEC"] = "1"
            os.execv(sys.executable, [sys.executable, sys.argv[0], *sys.argv[1:]])

    sel = A.load_selection()
    if adopt_external is None:
        adopt_external = sel.get("adopt_external", True)
    if commit is None:
        commit = sel.get("auto_commit", False)
    if push is None:
        push = sel.get("auto_push", False)

    agent_list = A.managed_agents(only)
    plan = engine.build_plan(agent_list, adopt_external=adopt_external)
    if apply:
        engine.execute(plan, do_backup=do_backup)

    git_msg = None
    if apply and commit:
        git_msg = git_commit_push("skill-sync: auto sync", push=push)

    backup_msg = None
    if apply and (sel.get("backup") or {}).get("enabled"):
        from . import maintenance
        bres = maintenance.push_backup(commit_first=True)
        backup_msg = (f"backed up to {bres['remote']}" if bres.get("ok")
                      else f"backup failed: {bres.get('error')}")

    if as_json:
        summary = {
            "applied": apply,
            "library_count": len(plan["final_names"]),
            **{k: len(plan[k]) for k in
               ("collect", "dedupe", "adopt", "conflicts", "external",
                "non_skill", "links", "relinks", "blocked")},
            "git": git_msg,
            "backup": backup_msg,
            "conflict_detail": [
                {"name": c["name"], "agent": c["agent"],
                 "canonical_from": c["canonical_from"]} for c in plan["conflicts"]],
        }
        print(json.dumps(summary, indent=2, ensure_ascii=False))
    else:
        engine.report(plan, apply=apply, do_backup=do_backup, quiet=quiet)
        if git_msg and not quiet:
            print(f"  git: {git_msg}")
        if backup_msg and not quiet:
            print(f"  backup: {backup_msg}")
        if apply and not commit and not quiet and (plan["collect"] or plan["adopt"]
                                                   or plan["dedupe"]):
            print(f"\n  Review & commit in {A.DATA_ROOT}:")
            print(f"  git -C {A.DATA_ROOT} add -A && "
                  f"git -C {A.DATA_ROOT} commit -m 'sync skills' && "
                  f"git -C {A.DATA_ROOT} push")

    return 1 if engine.has_conflicts(plan) else 0
