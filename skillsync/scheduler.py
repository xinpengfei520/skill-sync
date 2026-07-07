"""Auto-sync: parse intervals, install/remove a native OS scheduler entry
(launchd on macOS, Task Scheduler on Windows, systemd --user on Linux), and a
cross-platform `watch` loop fallback."""
from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from pathlib import Path

from . import agents as A
from . import runner

LABEL = "com.skillsync.autosync"
_UNITS = {
    "s": 1, "sec": 1, "secs": 1, "second": 1, "seconds": 1,
    "m": 60, "min": 60, "mins": 60, "minute": 60, "minutes": 60,
    "h": 3600, "hr": 3600, "hrs": 3600, "hour": 3600, "hours": 3600,
    "d": 86400, "day": 86400, "days": 86400,
}


def parse_interval(s: str) -> int:
    """'1m' '10m' '1h' '12h' '24h' '1d' '90s' -> seconds. Bare number = minutes."""
    m = re.fullmatch(r"\s*(\d+)\s*([a-z]*)\s*", str(s).lower())
    if not m:
        raise ValueError(f"invalid interval: {s!r} (try 10m, 1h, 24h)")
    n, unit = int(m.group(1)), (m.group(2) or "m")
    if unit not in _UNITS:
        raise ValueError(f"unknown interval unit: {unit!r} (use s/m/h/d)")
    secs = n * _UNITS[unit]
    if secs < 30:
        raise ValueError("interval too small; minimum is 30s")
    return secs


def human(seconds: int) -> str:
    for unit, sz in (("d", 86400), ("h", 3600), ("m", 60), ("s", 1)):
        if seconds % sz == 0 and seconds >= sz:
            return f"{seconds // sz}{unit}"
    return f"{seconds}s"


def _job_args(commit: bool, push: bool) -> list[str]:
    args = [sys.executable, str(A.TOOL_ROOT / "bin" / "skill-sync.py"),
            "sync", "--apply", "--quiet"]
    if A.load_selection().get("auto_update"):
        args.append("--self-update")
    if commit:
        args.append("--commit")
    if push:
        args.append("--push")
    return args


def _log_path() -> Path:
    p = Path.home() / ".skill-sync" / "autosync.log"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


# --- macOS: launchd ---------------------------------------------------------
def _plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def _schedule_macos(seconds, args, log):
    prog = "".join(f"    <string>{a}</string>\n" for a in args)
    plist = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
        '<plist version="1.0"><dict>\n'
        f'  <key>Label</key><string>{LABEL}</string>\n'
        f'  <key>ProgramArguments</key><array>\n{prog}  </array>\n'
        '  <key>EnvironmentVariables</key><dict>\n'
        f'    <key>SKILL_SYNC_HOME</key><string>{A.DATA_ROOT}</string>\n'
        '    <key>PATH</key><string>/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>\n'
        '  </dict>\n'
        f'  <key>StartInterval</key><integer>{seconds}</integer>\n'
        '  <key>RunAtLoad</key><false/>\n'
        f'  <key>StandardOutPath</key><string>{log}</string>\n'
        f'  <key>StandardErrorPath</key><string>{log}</string>\n'
        '</dict></plist>\n')
    path = _plist_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["launchctl", "unload", str(path)], capture_output=True)
    path.write_text(plist, encoding="utf-8")
    r = subprocess.run(["launchctl", "load", "-w", str(path)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"launchctl load failed: {r.stderr.strip()}")
    return path


def _unschedule_macos():
    path = _plist_path()
    subprocess.run(["launchctl", "unload", str(path)], capture_output=True)
    if path.exists():
        path.unlink()
        return True
    return False


def _status_macos():
    r = subprocess.run(["launchctl", "list"], capture_output=True, text=True)
    running = LABEL in r.stdout
    return {"installed": _plist_path().exists(), "loaded": running,
            "path": str(_plist_path())}


# --- Windows: Task Scheduler ------------------------------------------------
def _schedule_windows(seconds, args, log):
    minutes = max(1, seconds // 60)
    cmd = " ".join(f'"{a}"' for a in args)
    r = subprocess.run(["schtasks", "/create", "/tn", LABEL, "/tr", cmd,
                        "/sc", "minute", "/mo", str(minutes), "/f"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"schtasks failed: {r.stderr.strip() or r.stdout.strip()}")
    return LABEL


def _unschedule_windows():
    r = subprocess.run(["schtasks", "/delete", "/tn", LABEL, "/f"],
                       capture_output=True, text=True)
    return r.returncode == 0


def _status_windows():
    r = subprocess.run(["schtasks", "/query", "/tn", LABEL],
                       capture_output=True, text=True)
    return {"installed": r.returncode == 0, "loaded": r.returncode == 0, "path": LABEL}


# --- Linux: systemd --user --------------------------------------------------
def _systemd_dir() -> Path:
    return Path.home() / ".config" / "systemd" / "user"


def _schedule_linux(seconds, args, log):
    d = _systemd_dir()
    d.mkdir(parents=True, exist_ok=True)
    execstart = " ".join(args)
    (d / "skillsync.service").write_text(
        "[Unit]\nDescription=skill-sync auto sync\n\n"
        f"[Service]\nType=oneshot\nEnvironment=SKILL_SYNC_HOME={A.DATA_ROOT}\n"
        f"ExecStart={execstart}\n", encoding="utf-8")
    (d / "skillsync.timer").write_text(
        "[Unit]\nDescription=skill-sync auto sync timer\n\n"
        f"[Timer]\nOnBootSec={seconds}\nOnUnitActiveSec={seconds}\n"
        "Persistent=true\n\n[Install]\nWantedBy=timers.target\n", encoding="utf-8")
    subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True)
    r = subprocess.run(["systemctl", "--user", "enable", "--now", "skillsync.timer"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"systemctl failed: {r.stderr.strip()} "
                           "(a login session / lingering may be required)")
    return str(d / "skillsync.timer")


def _unschedule_linux():
    subprocess.run(["systemctl", "--user", "disable", "--now", "skillsync.timer"],
                   capture_output=True)
    removed = False
    for f in ("skillsync.timer", "skillsync.service"):
        p = _systemd_dir() / f
        if p.exists():
            p.unlink()
            removed = True
    subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True)
    return removed


def _status_linux():
    r = subprocess.run(["systemctl", "--user", "is-active", "skillsync.timer"],
                       capture_output=True, text=True)
    return {"installed": (_systemd_dir() / "skillsync.timer").exists(),
            "loaded": r.stdout.strip() == "active",
            "path": str(_systemd_dir() / "skillsync.timer")}


# --- dispatch ---------------------------------------------------------------
def schedule(interval: str, commit: bool, push: bool) -> dict:
    seconds = parse_interval(interval)
    args = _job_args(commit, push)
    log = _log_path()
    osname = A.system_name()
    if osname == "macos":
        path = _schedule_macos(seconds, args, log)
    elif osname == "windows":
        path = _schedule_windows(seconds, args, log)
    else:
        path = _schedule_linux(seconds, args, log)
    return {"seconds": seconds, "interval": human(seconds), "path": str(path),
            "commit": commit, "push": push, "log": str(log)}


def unschedule() -> bool:
    osname = A.system_name()
    if osname == "macos":
        return _unschedule_macos()
    if osname == "windows":
        return _unschedule_windows()
    return _unschedule_linux()


def status() -> dict:
    osname = A.system_name()
    if osname == "macos":
        return _status_macos()
    if osname == "windows":
        return _status_windows()
    return _status_linux()


def watch(interval: str, adopt_external: bool | None, commit: bool | None,
          push: bool | None) -> int:
    seconds = parse_interval(interval)
    print(f"skill-sync watch: every {human(seconds)}. Ctrl-C to stop.")
    try:
        while True:
            try:
                runner.run_sync(apply=True, adopt_external=adopt_external,
                                commit=commit, push=push, quiet=True)
            except Exception as e:  # keep the loop alive on transient errors
                print(f"skill-sync watch: error: {e}", file=sys.stderr)
            time.sleep(seconds)
    except KeyboardInterrupt:
        print("\nskill-sync watch: stopped.")
        return 0
