"""Read-only health check for the skill library and its mirrored agents.

`doctor` never mutates anything. It reports how many skills are installed, how
big each one is, whether its frontmatter is valid, and what to optimize. The
limits follow the Agent Skills spec / Claude Code skill-creator guidance:

- `name` and `description` are required; name is kebab-case, <= 64 chars.
- `description` is <= 1024 characters and cannot contain angle brackets.
- SKILL.md stays under 500 lines; extra detail belongs in `references/`
  (progressive disclosure).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from pathlib import Path

from . import agents as A
from . import engine as E

# --- limits -----------------------------------------------------------------
DESC_MAX = 1024
NAME_MAX = 64
COMPAT_MAX = 500
BODY_LINES_IDEAL = 500
BODY_BYTES_WARN = 64 * 1024
DESC_SHORT = 20
MANY_SKILLS = 80
HEAVY_SKILL_BYTES = 5 * 1024 * 1024
HEAVY_SKILL_FILES = 500

ALLOWED_KEYS = {"name", "description", "license", "allowed-tools", "metadata",
                "compatibility"}
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__"}

ERROR, WARN, INFO = "error", "warning", "info"


class _C:
    _on = sys.stdout.isatty()
    B = "\033[1m" if _on else ""
    D = "\033[2m" if _on else ""
    G = "\033[32m" if _on else ""
    Y = "\033[33m" if _on else ""
    R = "\033[31m" if _on else ""
    C = "\033[36m" if _on else ""
    Z = "\033[0m" if _on else ""


# --- frontmatter ------------------------------------------------------------
def parse_frontmatter(text: str) -> tuple[dict, str | None]:
    """Parse the small YAML subset skills use. Returns (meta, error).

    No third-party YAML parser: skill frontmatter is flat key/value, with
    optional quoted or block-scalar (`|`, `>` ) descriptions. Anything more
    exotic is reported instead of guessed at."""
    if text.startswith("﻿"):
        text = text[1:]
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, "no YAML frontmatter (SKILL.md must start with ---)"
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() in ("---", "..."):
            end = i
            break
    if end is None:
        return {}, "unterminated frontmatter (missing closing ---)"
    return _parse_yaml_subset(lines[1:end])


def _parse_yaml_subset(lines: list[str]) -> tuple[dict, str | None]:
    meta: dict = {}
    block_style: str | None = None
    current: str | None = None
    i, n = 0, len(lines)
    while i < n:
        raw = lines[i]
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            # Preserve paragraph breaks inside a block scalar.
            if current is not None and block_style:
                meta[current] = str(meta.get(current, "")) + "\n"
            i += 1
            continue
        if raw[:1] in (" ", "\t"):
            if current is None:
                return {}, f"unexpected indented line: {line.strip()[:50]}"
            val = line.strip()
            if block_style:
                joiner = " " if block_style == "fold" else "\n"
                meta[current] = (str(meta.get(current, "")) + joiner + val).strip()
            else:  # folded continuation of a plain or quoted scalar
                meta[current] = (str(meta.get(current, "")) + " " + val).strip()
            i += 1
            continue
        m = re.match(r"^([A-Za-z0-9_.-]+)\s*:\s*(.*)$", line)
        if not m:
            return {}, f"cannot parse line: {line.strip()[:50]}"
        key, val = m.group(1), m.group(2).strip()
        current, block_style = key, None
        if val in ("|", "|-", "|+", ">", ">-", ">+"):
            meta[key] = ""
            block_style = "fold" if val.startswith(">") else "literal"
        elif val[:1] in ('"', "'"):
            quote = val[0]
            if len(val) >= 2 and val.endswith(quote):
                meta[key] = val[1:-1]
            else:
                # Multi-line quoted scalar: consume until the closing quote.
                parts, j, closed = [val[1:]], i + 1, False
                while j < n:
                    nxt = lines[j].strip()
                    if nxt.endswith(quote):
                        parts.append(nxt[:-1])
                        closed, j = True, j + 1
                        break
                    parts.append(nxt)
                    j += 1
                if not closed:
                    return {}, f"unterminated quoted value for '{key}'"
                meta[key] = " ".join(p for p in parts if p).strip()
                i = j
                continue
        elif val.startswith("[") and not val.endswith("]"):
            return {}, f"unterminated flow sequence for '{key}'"
        elif val.startswith("{") and not val.endswith("}"):
            return {}, f"unterminated flow mapping for '{key}'"
        else:
            meta[key] = val
        i += 1
    return meta, None


# --- per-skill metrics ------------------------------------------------------
def _walk_metrics(path: Path) -> tuple[int, int]:
    """(file count, total bytes) under path, without following symlinks."""
    files = total = 0
    for root, dirs, names in os.walk(path, followlinks=False):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and d != ".DS_Store"]
        for fn in names:
            if fn == ".DS_Store":
                continue
            files += 1
            try:
                total += os.path.getsize(os.path.join(root, fn))
            except OSError:
                pass
    return files, total


def _issue(level: str, code: str, message: str) -> dict:
    return {"level": level, "code": code, "message": message}


def check_skill(path: Path, name: str | None = None) -> dict:
    """Metrics + findings for one skill directory."""
    name = name or path.name
    skill_md = path / "SKILL.md"
    info = {"name": name, "path": str(path), "issues": []}
    issues = info["issues"]

    try:
        text = skill_md.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        issues.append(_issue(ERROR, "unreadable", f"cannot read SKILL.md ({e})"))
        info.update(skill_md_bytes=0, skill_md_lines=0, description_chars=0,
                    files=0, bytes=0)
        return info

    lines = text.count("\n") + (1 if text and not text.endswith("\n") else 0)
    info["skill_md_bytes"] = len(text.encode("utf-8"))
    info["skill_md_lines"] = lines
    info["skill_md_hash"] = hashlib.sha256(text.encode("utf-8")).hexdigest()
    info["files"], info["bytes"] = _walk_metrics(path)
    info["has_references"] = any((path / d).is_dir()
                                 for d in ("references", "scripts", "assets"))

    meta, err = parse_frontmatter(text)
    fatal = bool(err)
    if err:
        issues.append(_issue(ERROR, "frontmatter", err))
        meta = {}

    fm_name = meta.get("name", "").strip()
    desc = meta.get("description", "").strip()
    info["fm_name"] = fm_name
    info["description_chars"] = len(desc)

    # When the frontmatter is unparseable, field-level checks are moot: the
    # agent cannot load the skill at all, so one error is the useful signal.
    if fatal:
        pass
    elif not fm_name:
        issues.append(_issue(WARN, "missing-name",
                             "frontmatter has no 'name'; agents fall back to the "
                             "directory name"))
    elif not re.fullmatch(r"[a-z0-9-]+", fm_name):
        issues.append(_issue(WARN, "name-not-kebab",
                             f"name '{fm_name}' should be kebab-case "
                             f"(lowercase letters, digits, hyphens)"))
    elif fm_name.startswith("-") or fm_name.endswith("-") or "--" in fm_name:
        issues.append(_issue(WARN, "name-not-kebab",
                             f"name '{fm_name}' has a leading/trailing or "
                             f"doubled hyphen"))
    if fm_name and len(fm_name) > NAME_MAX:
        issues.append(_issue(WARN, "name-too-long",
                             f"name is {len(fm_name)} chars (max {NAME_MAX})"))
    if fm_name and fm_name != path.name:
        issues.append(_issue(INFO, "name-mismatch",
                             f"frontmatter name '{fm_name}' differs from the "
                             f"directory '{path.name}'"))

    if not fatal and not desc:
        issues.append(_issue(ERROR, "missing-description",
                             "no 'description'; the skill will not be selected "
                             "for the right task"))
    elif not fatal:
        if len(desc) > DESC_MAX:
            issues.append(_issue(WARN, "description-too-long",
                                 f"description is {len(desc)} chars; over "
                                 f"{DESC_MAX} it gets truncated — trim it"))
        if "<" in desc or ">" in desc:
            issues.append(_issue(WARN, "description-angle-brackets",
                                 "description contains < or >; the spec "
                                 "disallows angle brackets"))
        if len(desc) < DESC_SHORT:
            issues.append(_issue(INFO, "description-short",
                                 f"description is only {len(desc)} chars; add "
                                 f"when-to-use triggers so the skill is picked"))

    if lines > BODY_LINES_IDEAL:
        hint = (" and no references/ dir" if not info["has_references"] else "")
        issues.append(_issue(WARN, "body-too-long",
                             f"SKILL.md is {lines} lines{hint}; keep the body "
                             f"under {BODY_LINES_IDEAL} and move detail into "
                             f"references/ (progressive disclosure)"))
    if info["skill_md_bytes"] > BODY_BYTES_WARN:
        issues.append(_issue(INFO, "body-heavy",
                             f"SKILL.md is {info['skill_md_bytes'] / 1024:.0f} KB; "
                             f"the whole file is read when the skill triggers"))

    compat = str(meta.get("compatibility", ""))
    if len(compat) > COMPAT_MAX:
        issues.append(_issue(WARN, "compatibility-too-long",
                             f"compatibility is {len(compat)} chars "
                             f"(max {COMPAT_MAX})"))
    extra = [k for k in meta if k not in ALLOWED_KEYS]
    if extra:
        issues.append(_issue(INFO, "unexpected-key",
                             "unknown frontmatter key(s): " + ", ".join(sorted(extra))))

    if info["bytes"] > HEAVY_SKILL_BYTES or info["files"] > HEAVY_SKILL_FILES:
        issues.append(_issue(INFO, "skill-heavy",
                             f"{info['files']} files / "
                             f"{info['bytes'] / (1024 * 1024):.1f} MB in the "
                             f"skill folder; keep bulky assets out of the repo"))
    return info


# --- agent view -------------------------------------------------------------
def agent_view(agent: dict, library: Path, lib: set[str]) -> dict:
    """Count what an agent has vs. what the library expects. Read-only."""
    sd = agent["skills_dir"]
    view = {"agent": agent["name"], "path": str(sd), "links": 0, "local": 0,
            "missing": 0, "dangling": 0, "blocked": 0,
            "missing_names": [], "dangling_names": [], "blocked_names": []}
    if not sd or not sd.is_dir():
        view["missing"] = len(lib)
        view["missing_names"] = sorted(lib)
        return view
    present = set()
    for entry in sd.iterdir():
        if entry.name.startswith(".") or entry.name in A.IGNORE_NAMES:
            continue
        present.add(entry.name)
        if A.is_link(entry):
            real = os.path.realpath(entry)
            if E._points_into(entry, library):
                view["links"] += 1
                if not os.path.exists(real):
                    view["dangling"] += 1
                    view["dangling_names"].append(entry.name)
            else:
                view["local"] += 1
        elif entry.is_dir():
            if entry.name in lib:
                view["blocked"] += 1
                view["blocked_names"].append(entry.name)
            else:
                view["local"] += 1
    missing = sorted(lib - present)
    view["missing"] = len(missing)
    view["missing_names"] = missing
    view["dangling_names"].sort()
    view["blocked_names"].sort()
    return view


# --- report -----------------------------------------------------------------
def run(agent_filter: list[str] | None = None, limit: int = 10,
        show_all: bool = False) -> dict:
    library = A.skills_root()
    sel = A.load_selection()
    skills = sorted(p for p in library.iterdir() if E.is_skill_dir(p)) \
        if library.is_dir() else []
    lib_names = {p.name for p in skills}

    records = [check_skill(p) for p in skills]
    # Skills the library cannot see at all (dangling links, missing SKILL.md).
    orphans = []
    if library.is_dir():
        for entry in sorted(library.iterdir()):
            if entry.name.startswith(".") or entry.name in A.IGNORE_NAMES:
                continue
            if E.is_skill_dir(entry):
                continue
            if A.is_link(entry) and not entry.exists():
                orphans.append({"name": entry.name, "path": str(entry),
                                "why": "dangling symlink"})
            elif entry.is_dir():
                orphans.append({"name": entry.name, "path": str(entry),
                                "why": "directory without SKILL.md"})

    agents = [a for a in A.managed_agents(agent_filter)
              if a["installed"] and a["skills_dir"]]
    views = [agent_view(a, library, lib_names) for a in agents]

    counts = {ERROR: 0, WARN: 0, INFO: 0}
    for rec in records:
        for it in rec["issues"]:
            counts[it["level"]] += 1
    for o in orphans:
        counts[ERROR] += 1

    total_bytes = sum(r["bytes"] for r in records)
    context_chars = sum(len(r["name"]) + r.get("description_chars", 0)
                        for r in records)
    ranked = sorted(records,
                    key=lambda r: (r["skill_md_lines"], r["skill_md_bytes"]),
                    reverse=True)
    shown = ranked if show_all else ranked[:max(limit, 0)]

    suggestions = _suggestions(records, counts, views, orphans, len(records),
                               context_chars)

    return {
        "library": str(library),
        "skill_count": len(records),
        "orphan_count": len(orphans),
        "total_bytes": total_bytes,
        "context_chars": context_chars,
        "context_tokens_estimate": max(1, round(context_chars / 4)),
        "counts": counts,
        "skills": records,
        "shown": [r["name"] for r in shown],
        "ranked": shown,
        "agents": views,
        "orphans": orphans,
        "suggestions": suggestions,
        "selection": {k: sel.get(k) for k in ("enabled", "disabled")},
    }


def _suggestions(records, counts, views, orphans, total, context_chars) -> list[str]:
    out: list[str] = []
    bad = [r for r in records if any(i["level"] == ERROR for i in r["issues"])]
    if bad:
        names = ", ".join(r["name"] for r in bad[:5])
        more = f" (+{len(bad) - 5} more)" if len(bad) > 5 else ""
        out.append(f"Fix {len(bad)} skill(s) that cannot be selected properly: "
                   f"{names}{more}. `skill-sync doctor --json` has the details.")
    long_body = [r for r in records if r["skill_md_lines"] > BODY_LINES_IDEAL]
    if long_body:
        names = ", ".join(r["name"] for r in long_body[:5])
        more = f" (+{len(long_body) - 5} more)" if len(long_body) > 5 else ""
        out.append(f"Move detail out of {len(long_body)} SKILL.md file(s) over "
                   f"{BODY_LINES_IDEAL} lines into references/: {names}{more}.")
    long_desc = [r for r in records if r.get("description_chars", 0) > DESC_MAX]
    if long_desc:
        out.append(f"Trim {len(long_desc)} description(s) over {DESC_MAX} chars — "
                   f"the tail is truncated before the skill is selected.")
    if total > MANY_SKILLS:
        out.append(f"{total} skills are installed; every name + description is "
                   f"loaded into context (~{context_chars:,} chars, "
                   f"~{max(1, round(context_chars / 4)):,} tokens). Prune what you "
                   f"no longer use with `skill-sync uninstall <name>`.")
    dangling_agents = [v for v in views if v["dangling_names"]]
    if dangling_agents:
        names = sorted({n for v in dangling_agents for n in v["dangling_names"]})
        shown = ", ".join(names[:5])
        more = f" (+{len(names) - 5} more)" if len(names) > 5 else ""
        out.append(f"{len(dangling_agents)} agent(s) keep leftover links to "
                   f"skill(s) no longer in the library: {shown}{more}. Clean them "
                   f"with `skill-sync uninstall <name> --apply`.")
    missing_agents = [v for v in views if v["missing_names"]]
    if missing_agents:
        parts = [f"{v['agent']} ({v['missing']})" for v in missing_agents[:5]]
        more = (f" (+{len(missing_agents) - 5} more)"
                if len(missing_agents) > 5 else "")
        out.append("Agents missing library skills: " + ", ".join(parts) + more +
                   ". Run `skill-sync` to preview the mirror.")
    blocked_agents = [v for v in views if v["blocked_names"]]
    if blocked_agents:
        names = sorted({n for v in blocked_agents for n in v["blocked_names"]})
        out.append(f"{len(blocked_agents)} agent(s) have a real directory where a "
                   f"library skill should be: {', '.join(names[:5])}. Sync never "
                   f"overwrites them — move or delete the directory first.")
    if orphans:
        names = ", ".join(o["name"] for o in orphans[:5])
        more = f" (+{len(orphans) - 5} more)" if len(orphans) > 5 else ""
        out.append(f"{len(orphans)} entr(ies) in the library are not loadable "
                   f"skills: {names}{more}.")
    seen: dict[str, str] = {}
    dupes = []
    for r in records:
        h = r.get("skill_md_hash")
        if h and h in seen:
            dupes.append(f"{seen[h]} / {r['name']}")
        elif h:
            seen[h] = r["name"]
    if dupes:
        out.append(f"{len(dupes)} pair(s) share an identical SKILL.md: "
                   + "; ".join(dupes[:3]))
    if not out:
        out.append("No issues found — the library and every managed agent look "
                   "healthy.")
    return out


def print_report(data: dict, limit: int = 10, show_all: bool = False) -> None:
    C = _C
    print(f"\n{C.B}skill-sync doctor{C.Z} {C.D}(read-only){C.Z}")
    print(f"{C.D}library: {data['library']}{C.Z}")
    print(f"{C.B}skills:{C.Z} {data['skill_count']}   "
          f"{C.B}size:{C.Z} {data['total_bytes'] / (1024 * 1024):.2f} MB   "
          f"{C.B}context:{C.Z} ~{data['context_chars']:,} chars / "
          f"~{data['context_tokens_estimate']:,} tokens")

    n = data["counts"]
    print(f"{C.B}findings:{C.Z} {C.R}{n[ERROR]} errors{C.Z}  "
          f"{C.Y}{n[WARN]} warnings{C.Z}  {C.D}{n[INFO]} info{C.Z}\n")

    if data["agents"]:
        w = max(len("AGENT"), *(len(v["agent"]) for v in data["agents"]))
        print(f"{C.B}{'AGENT':<{w}} {'LINKS':>7} {'MISSING':>8} "
              f"{'DANGLING':>9} {'BLOCKED':>8}{C.Z}")
        for v in data["agents"]:
            miss = (f"{C.R}{v['missing']:>8}{C.Z}" if v["missing"]
                    else f"{v['missing']:>8}")
            dang = (f"{C.R}{v['dangling']:>9}{C.Z}" if v["dangling"]
                    else f"{v['dangling']:>9}")
            block = (f"{C.Y}{v['blocked']:>8}{C.Z}" if v["blocked"]
                     else f"{v['blocked']:>8}")
            print(f"{v['agent']:<{w}} {v['links']:>7} {miss} {dang} {block}")
        print()

    name_w = min(40, max([len("SKILL")] +
                         [len(r["name"]) for r in data["skills"]]))

    if data["ranked"]:
        title = "SIZE — largest SKILL.md files" if limit else "SIZE"
        print(f"{C.B}{title}{C.Z}")
        print(f"{C.D}{'SKILL':<{name_w}} {'LINES':>6} {'DESC':>6} {'FILES':>6} "
              f"{'SIZE':>9}  ISSUES{C.Z}")
        for r in data["ranked"]:
            errs = sum(1 for i in r["issues"] if i["level"] == ERROR)
            warns = sum(1 for i in r["issues"] if i["level"] == WARN)
            marks = (f"{C.R}{errs}E{C.Z} " if errs else "") + \
                    (f"{C.Y}{warns}W{C.Z}" if warns else "")
            print(f"{r['name']:<{name_w}} {r['skill_md_lines']:>6} "
                  f"{r.get('description_chars', 0):>6} {r['files']:>6} "
                  f"{r['bytes'] / 1024:>8.0f}K  {marks}")

    findings = [r for r in data["skills"] if r["issues"]]
    if findings:
        print(f"\n{C.B}FINDINGS{C.Z}")
        order = {ERROR: 0, WARN: 1, INFO: 2}
        rows = sorted(((rec, it) for rec in findings for it in rec["issues"]),
                      key=lambda p: (order[p[1]["level"]], p[0]["name"]))
        infos = [p for p in rows if p[1]["level"] == INFO]
        shown = rows if show_all else [p for p in rows
                                       if p[1]["level"] != INFO] + infos[:12]
        for rec, it in shown:
            color = {ERROR: C.R, WARN: C.Y, INFO: C.D}[it["level"]]
            print(f"  {color}{it['level']:<7}{C.Z} "
                  f"{rec['name']:<{name_w}} {it['message']}")
        hidden = len(infos) - sum(1 for p in shown if p[1]["level"] == INFO)
        if hidden:
            print(f"  {C.D}… {hidden} more info (run with --all to show){C.Z}")

    for o in data["orphans"]:
        print(f"  {C.R}{'error':<7}{C.Z} {o['name']:<{name_w}} {o['why']}")

    print(f"\n{C.B}SUGGESTIONS{C.Z}")
    for s in data["suggestions"]:
        print(f"  • {s}")
    print()


def run_json(agent_filter: list[str] | None = None, limit: int = 10,
             show_all: bool = False) -> int:
    data = run(agent_filter, limit, show_all)
    data.pop("ranked", None)  # the full metrics live in `skills`
    print(json.dumps(data, indent=2, ensure_ascii=False))
    return 0
