"""AI coach scanner: reads Claude Code usage across all projects.

    py scan.py --check          fast, incremental; prints one nudge line only when a threshold is crossed
    py scan.py --digest [--days N] [--out FILE]
                                usage digest for the /ai-coach review (default: since last review, else 30 days)
    py scan.py --mark-reviewed  record that a review happened (resets the nudge counters)
    py scan.py --park "item"    park a suggestion the user didn't apply; the next review re-checks it
    py scan.py --unpark N       drop parked item N (applied, or resolved itself)
    py scan.py --reject "item"  record a suggestion the user declined; not re-proposed unless it recurs
    py scan.py --count "regex" [--days N]
                                hits of a regex over the user's prompts, per 100 prompts (a baseline)
    py scan.py --applied "item" --watch "regex" --baseline "H/P"
                                record an applied change and what to recount at the next review
    py scan.py --decide KIND OUTCOME "item"
                                log one decision (kind = lens, outcome = yes|no|park|corrected)
    py scan.py --label real=K noise=M [--noise "hit text"]...
                                how many correction-like hits were real this review (detector tuning)

Sources (all local, read-only): <config>/history.jsonl (every prompt, all projects),
<config>/projects/*/*.jsonl (session logs: skill calls, permission denials, interrupts),
<config>/projects/*/memory/ (saved feedback), <config>/skills/ and project .claude/skills (skill inventory).
"""

import json
import os
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

CONFIG = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
STATE = Path(__file__).resolve().parent.parent / "state.json"
DAY = 86400

# Automated runs (headless digests, background agents) land in Temp; keep them out of "your" numbers.
AUTOMATED_PROJECT_MARKERS = ("AppData-Local-Temp", "AppData\\Local\\Temp")

CORRECTION = re.compile(
    r"^\s*(no+\b|nah\b|nope\b|wrong\b|stop\b|wait\b|don'?t\b|not what|why (did|do|is|are|would|didn'?t)\b|"
    r"i (told|said|asked)\b|again\b|still\b|wtf\b|man\b|hold on\b|actually\b|you (missed|forgot|didn'?t)\b)",
    re.I,
)
DENIAL = re.compile(r"(Permission to use .* has been denied|denied by the Claude Code auto mode classifier|"
                    r"Permission for this action was denied)", re.I)
INTERRUPT = "[Request interrupted by user"

THRESHOLDS = {"corrections": 30, "denials": 15, "sessions": 10}
WEEKLY_DAYS = 7    # a review is due at least this often
MIN_GAP_DAYS = 3   # a crossed threshold brings it forward, but never sooner than this


def load_state():
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(s):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(s, indent=2), encoding="utf-8")


def is_automated(project):
    return any(m in (project or "") for m in AUTOMATED_PROJECT_MARKERS)


def iter_history(since_ms):
    path = CONFIG / "history.jsonl"
    if not path.exists():
        return
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                d = json.loads(line)
            except Exception:
                continue
            if d.get("timestamp", 0) >= since_ms:
                yield d


def iter_session_files(since_s):
    for proj in (CONFIG / "projects").glob("*"):
        if not proj.is_dir():
            continue
        for f in proj.glob("*.jsonl"):
            try:
                if f.stat().st_mtime >= since_s:
                    yield proj.name, f
            except OSError:
                continue


def scan_sessions(since_s):
    """Skill calls, permission denials and interrupts from session logs modified since `since_s`."""
    skills, denials, interrupts = Counter(), [], 0
    sessions = defaultdict(int)
    for proj, f in iter_session_files(since_s):
        sessions["automated" if is_automated(proj) else "interactive"] += 1
        try:
            fh = open(f, encoding="utf-8", errors="replace")
        except OSError:
            continue
        with fh:
            for line in fh:
                if '"Skill"' not in line and "denied" not in line and INTERRUPT not in line:
                    continue
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                ts = d.get("timestamp", "")
                msg = d.get("message") or {}
                content = msg.get("content")
                if not isinstance(content, list):
                    if isinstance(content, str) and INTERRUPT in content:
                        interrupts += 1
                    continue
                for c in content:
                    if not isinstance(c, dict):
                        continue
                    if c.get("type") == "tool_use" and c.get("name") == "Skill":
                        skills[(c.get("input") or {}).get("skill", "?")] += 1
                    elif c.get("type") == "tool_result":
                        text = c.get("content")
                        if isinstance(text, list):
                            text = " ".join(x.get("text", "") for x in text if isinstance(x, dict))
                        if isinstance(text, str) and DENIAL.search(text):
                            denials.append({"project": proj, "ts": ts, "text": text[:220].replace("\n", " ")})
                    elif c.get("type") == "text" and INTERRUPT in c.get("text", ""):
                        interrupts += 1
    return skills, denials, interrupts, dict(sessions)


def prompts_since(since_ms):
    out = []
    for d in iter_history(since_ms):
        text = (d.get("display") or "").strip()
        if not text:
            continue
        out.append({"ts": d.get("timestamp", 0), "project": d.get("project", ""), "text": text,
                    "session": d.get("sessionId", "")})
    return out


def _skill_desc(path):
    """First line of the `description:` frontmatter field, trimmed."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")[:4000]
    except OSError:
        return ""
    m = re.search(r"^description:\s*(.+)$", text, re.M)
    return m.group(1).strip().strip("\"'")[:140] if m else ""


def skill_inventory():
    """Every SKILL.md reachable on this machine, grouped by skill name.

    Scopes: user skills, project skills (~/*/.claude/skills), plugin sources inside repos
    (~/*/plugins/*/skills), and the plugin cache. The cache keeps one folder per version, so
    only its most recently modified copy counts; older cache copies are reported as a count.
    Returns {name: [{"scope", "path", "mtime", "desc"}]} with the newest copy first.
    """
    found = defaultdict(list)

    def add(scope, skill_md):
        try:
            mt = skill_md.stat().st_mtime
        except OSError:
            return
        found[skill_md.parent.name].append(
            {"scope": scope, "path": str(skill_md), "mtime": mt, "desc": _skill_desc(skill_md)})

    for p in (CONFIG / "skills").glob("*/SKILL.md"):
        add("user", p)
    for p in Path.home().glob("*/.claude/skills/*/SKILL.md"):
        add(f"project:{p.parents[3].name}", p)
    for p in Path.home().glob("*/plugins/*/skills/*/SKILL.md"):
        add(f"plugin-source:{p.parents[4].name}/{p.parents[2].name}", p)
    cache = defaultdict(list)
    for p in (CONFIG / "plugins" / "cache").glob("*/*/*/skills/*/SKILL.md"):
        cache[(p.parents[4].name, p.parent.name)].append(p)
    old_versions = 0
    for (plugin, _), copies in cache.items():
        copies.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        add(f"plugin-cache:{plugin}", copies[0])
        old_versions += len(copies) - 1
    for name in found:
        found[name].sort(key=lambda c: c["mtime"], reverse=True)
    return found, old_versions


def _git(repo, *args):
    import subprocess
    try:
        r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=20)
        return r.stdout if r.returncode == 0 else ""
    except Exception:
        return ""


def claude_version():
    import subprocess
    try:
        r = subprocess.run("claude --version", shell=True, capture_output=True, text=True, timeout=20)
        m = re.search(r"\d+\.\d+\.\d+", r.stdout or "")
        return m.group(0) if m else ""
    except Exception:
        return ""


def _text_of(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text")
    return ""


def rewrites(since_s, limit=30):
    """Long user messages paired with the assistant text just before them: where the user rewrote
    a draft themselves, the gap between the two is a taste signal."""
    pairs = []
    for proj, f in iter_session_files(since_s):
        if is_automated(proj):
            continue
        last = ""
        try:
            fh = open(f, encoding="utf-8", errors="replace")
        except OSError:
            continue
        with fh:
            for line in fh:
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                msg = d.get("message") or {}
                if d.get("type") == "assistant":
                    t = _text_of(msg.get("content")).strip()
                    if t:
                        last = t
                elif d.get("type") == "user" and not d.get("isMeta"):
                    content = msg.get("content")
                    if isinstance(content, list) and any(isinstance(c, dict) and c.get("type") == "tool_result"
                                                         for c in content):
                        continue
                    t = _text_of(content).strip()
                    if len(t) > 280 and last and not t.startswith("<") and "<system-reminder>" not in t[:200]:
                        pairs.append({"ts": d.get("timestamp", ""), "project": proj,
                                      "draft": last[:500], "user": t[:500]})
                    last = ""
    pairs.sort(key=lambda x: x["ts"])
    lines = [f"## Draft vs. user rewrite ({len(pairs)}) — taste signal: what the user changed, kept, cut"]
    for p in pairs[-limit:]:
        lines.append(f"- [{p['ts'][:10]}] {Path(p['project']).name}")
        lines.append("  DRAFT: " + p["draft"].replace("\n", " "))
        lines.append("  USER:  " + p["user"].replace("\n", " "))
    lines.append("")
    return lines


def knowledge_files(project_paths):
    """Per project: learnings without an expiry line, and when each context file last changed."""
    lines = ["## Knowledge files — learnings to re-test, context files to check for drift"]
    for proj in sorted(project_paths):
        root = Path(proj)
        if not (root / ".git").exists():
            continue
        learn = root / "intelligence" / "learnings.md"
        if learn.exists():
            text = learn.read_text(encoding="utf-8", errors="replace")
            entries = [b for b in re.split(r"\n(?=## )", text) if b.startswith("## ") and "- topic:" in b]
            missing = [b for b in entries if "- stop-trusting-if:" not in b]
            lines.append(f"- {root.name}: {len(entries)} learnings, {len(missing)} without a stop-trusting-if line")
        files = []
        for pat in ("context/**/*.md", "product-marketing/*.md", "*/taste.md"):
            files += [f for f in root.glob(pat) if f.is_file()]
        for f in sorted(set(files)):
            rel = f.relative_to(root).as_posix()
            when = _git(root, "log", "-1", "--format=%cs", "--", rel).strip() or "untracked"
            lines.append(f"  - {rel}: last changed {when}")
    if len(lines) == 1:
        lines.append("- none found")
    lines.append("")
    return lines


def count_hits(pattern, days):
    """Regex hits over the user's own prompts in the last `days`, with the prompt total."""
    rx = re.compile(pattern, re.I)
    prompts = [p for p in prompts_since(int((time.time() - days * DAY) * 1000)) if not is_automated(p["project"])]
    hits = [p for p in prompts if rx.search(p["text"])]
    return len(hits), len(prompts), hits


def recheck_applied(st):
    """Recount each applied item's watch pattern since it was applied, next to its baseline."""
    items = st.get("applied", [])
    lines = ["## Re-check applied changes — did each one work? (worked / no effect / worse, with the numbers)"]
    if not items:
        lines += ["- none recorded yet", ""]
        return lines
    for i, a in enumerate(items, 1):
        applied_ts = time.mktime(time.strptime(a["date"], "%Y-%m-%d"))
        days = max(1, int((time.time() - applied_ts) / DAY))
        if not a.get("watch"):
            lines.append(f"{i}. [{a['date']}] {a['text']} — no watch pattern; judge it from the window")
            continue
        try:
            h, n, hits = count_hits(a["watch"], days)
        except re.error as e:
            lines.append(f"{i}. [{a['date']}] {a['text']} — bad watch regex ({e})")
            continue
        rate = f"{100 * h / n:.1f}" if n else "?"
        lines.append(f"{i}. [{a['date']}, {days}d ago] {a['text']} — baseline {a.get('baseline', '?')} (hits/prompts, 30d before), "
                     f"since: {h}/{n} = {rate} per 100 · watch: /{a['watch']}/")
        for p in hits[-3:]:
            lines.append(f"   - [{time.strftime('%m-%d', time.localtime(p['ts'] / 1000))}] {p['text'][:140]}".replace("\n", " "))
    lines.append("")
    return lines


MODEL_FIT = "Model fit:"
FIT_LINE = re.compile(r"(?m)^Model fit: .+$")  # line start only: quotes and prose mentions don't count
SWITCH = re.compile(r"<command-name>/(model|effort)</command-name>|^\s*/(model|effort)\b")
# user entries the user didn't type: injected tags and the summary after compaction
NOT_TYPED = re.compile(r"\s*(<|This session is being continued)")
STRETCH_PROMPTS = 30  # a suggestion's stretch ends at the next suggestion, the session end, or this many prompts


def model_fit(since_s):
    """Each 'Model fit:' line Claude ended a reply with, whether the user ran /model or /effort within
    their next 3 prompts, and that stretch's prompts, correction-like prompts and tokens."""
    rows = []
    for proj, f in iter_session_files(since_s):
        if is_automated(proj):
            continue
        try:
            raw = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if MODEL_FIT not in raw:
            continue
        events = []  # ("fit", text) | ("user", text) | ("tokens", n)
        for line in raw.splitlines():
            try:
                d = json.loads(line)
            except Exception:
                continue
            msg = d.get("message") or {}
            content = msg.get("content")
            if d.get("type") == "assistant":
                u = msg.get("usage") or {}
                events.append(("tokens", sum(u.get(k, 0) or 0 for k in (
                    "input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens", "output_tokens"))))
                for c in content if isinstance(content, list) else []:
                    if isinstance(c, dict) and c.get("type") == "text":
                        events += [("fit", m.group(0)) for m in FIT_LINE.finditer(c.get("text", ""))][-1:]
                    elif isinstance(c, dict) and c.get("type") == "tool_use" and c.get("name") == "Agent":
                        events.append(("agent", ((c.get("input") or {}).get("model") or "").lower()))
            elif d.get("type") == "user" and not d.get("isMeta"):
                if isinstance(content, str):
                    events.append(("user", content))
                elif isinstance(content, list) and not any(
                        isinstance(c, dict) and c.get("type") == "tool_result" for c in content):
                    events.append(("user", " ".join(c.get("text", "") for c in content if isinstance(c, dict))))
        for i, (kind, text) in enumerate(events):
            if kind != "fit":
                continue
            users, tokens, corr, agents = [], 0, 0, []
            for k2, v in events[i + 1:]:
                if k2 == "fit" or len(users) >= STRETCH_PROMPTS:
                    break
                if k2 == "tokens":
                    tokens += v
                elif k2 == "agent" and sum(not NOT_TYPED.match(u) for u in users) < 3:
                    agents.append(v)
                elif k2 == "user":
                    users.append(v)
                    corr += bool(CORRECTION.search(v))
            # a line that offers a subagent on a smaller model is taken when Claude starts one (Oct 25 review)
            sub = re.search(r"(?i)subagent.{0,40}\b(sonnet|haiku)\b|\b(sonnet|haiku)\b.{0,40}subagent", text)
            accepted = any(SWITCH.search(u) for u in users[:3]) or bool(
                sub and (sub.group(1) or sub.group(2)).lower() in agents)
            rows.append({"session": f.stem[:6], "fit": text[:160], "accepted": accepted,
                         "prompts": len(users), "corrections": corr, "tokens": tokens})
    return rows


def model_fit_section(since_s):
    rows = model_fit(since_s)
    lines = [f"## Model fit suggestions ({len(rows)}) — accepted vs declined: fewer corrections or tokens? "
             f"Keep or drop the rule after two reviews (rule in <config>/CLAUDE.md, added 2026-10-17)"]
    for label, grp in (("accepted", [r for r in rows if r["accepted"]]), ("declined", [r for r in rows if not r["accepted"]])):
        p = sum(r["prompts"] for r in grp)
        c = sum(r["corrections"] for r in grp)
        tk = sum(r["tokens"] for r in grp)
        rate = f"{100 * c / p:.0f} per 100 prompts" if p else "n/a"
        lines.append(f"- {label}: {len(grp)} · stretch prompts {p} · correction-like {c} ({rate}) · "
                     f"tokens {tk:,} ({tk // max(p, 1):,} per prompt)")
    for r in rows[-20:]:
        lines.append(f"  - s:{r['session']} {'YES' if r['accepted'] else 'no '} · {r['prompts']} prompts, "
                     f"{r['corrections']} corr, {r['tokens']:,} tok · {r['fit']}")
    lines.append("- scope: only sessions on this machine, stretches capped at 30 prompts; corrections are the "
                 "regex detector's hits (noisy); tokens include cache reads, so a switch's re-read shows up here")
    lines.append("")
    return lines


CLEAR_FIRST = "Clear first:"
CLEAR_LINE = re.compile(r"(?m)^Clear first: .+$")  # line start only, like FIT_LINE
CLEAR_CMD = re.compile(r"<command-name>/clear</command-name>|^\s*/clear\b")


def clear_fit(since_s):
    """Each 'Clear first:' line Claude opened a reply with. Taken if the user ran /clear in their next
    2 prompts or sent nothing more in that session (/clear starts a new transcript). For declined lines,
    the prompts and tokens the old context kept costing until the next suggestion or STRETCH_PROMPTS."""
    rows = []
    for proj, f in iter_session_files(since_s):
        if is_automated(proj):
            continue
        try:
            raw = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if CLEAR_FIRST not in raw:
            continue
        events = []  # ("clear", text) | ("user", text) | ("tokens", n)
        for line in raw.splitlines():
            try:
                d = json.loads(line)
            except Exception:
                continue
            msg = d.get("message") or {}
            content = msg.get("content")
            if d.get("type") == "assistant":
                u = msg.get("usage") or {}
                events.append(("tokens", sum(u.get(k, 0) or 0 for k in (
                    "input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens", "output_tokens"))))
                for c in content if isinstance(content, list) else []:
                    if isinstance(c, dict) and c.get("type") == "text":
                        events += [("clear", m.group(0)) for m in CLEAR_LINE.finditer(c.get("text", ""))][:1]
            elif d.get("type") == "user" and not d.get("isMeta"):
                if isinstance(content, str):
                    events.append(("user", content))
                elif isinstance(content, list) and not any(
                        isinstance(c, dict) and c.get("type") == "tool_result" for c in content):
                    events.append(("user", " ".join(c.get("text", "") for c in content if isinstance(c, dict))))
        for i, (kind, text) in enumerate(events):
            if kind != "clear":
                continue
            users, tokens = [], 0
            for k2, v in events[i + 1:]:
                if k2 == "clear" or len(users) >= STRETCH_PROMPTS:
                    break
                if k2 == "tokens":
                    tokens += v
                elif k2 == "user":
                    users.append(v)
            taken = not users or any(CLEAR_CMD.search(u) for u in users[:2])
            rows.append({"session": f.stem[:6], "line": text[:160], "taken": taken,
                         "prompts": 0 if taken else len(users), "tokens": 0 if taken else tokens})
    return rows


def clear_fit_section(since_s):
    rows = clear_fit(since_s)
    taken = [r for r in rows if r["taken"]]
    declined = [r for r in rows if not r["taken"]]
    p = sum(r["prompts"] for r in declined)
    tk = sum(r["tokens"] for r in declined)
    lines = [f"## Clear suggestions ({len(rows)}) — taken {len(taken)}, declined {len(declined)}. "
             f"Keep or drop the rule after two reviews (rule in <config>/CLAUDE.md, added 2026-10-19)",
             f"- declined stretches: {p} prompts on the old context · tokens {tk:,} ({tk // max(p, 1):,} per prompt)"]
    for r in rows[-20:]:
        lines.append(f"  - s:{r['session']} {'YES' if r['taken'] else 'no '} · {r['prompts']} prompts, "
                     f"{r['tokens']:,} tok · {r['line']}")
    lines.append("- scope: only sessions on this machine; 'taken' also counts a session that simply ended after "
                 "the line, so it overstates clears a little")
    lines.append("")
    return lines


def self_learning(st):
    """What the coach knows about its own proposals and detector: acted on only past the thresholds."""
    lines = ["## Coach self-learning"]
    dec = st.get("decisions", [])
    by = Counter((d["kind"], d["outcome"]) for d in dec)
    kinds = sorted({k for k, _ in by})
    lines.append(f"- decisions logged: {len(dec)} (threshold to act on the pattern: 50)")
    for k in kinds:
        parts = ", ".join(f"{o} {by[(k, o)]}" for o in ("yes", "no", "park", "corrected") if by[(k, o)])
        lines.append(f"  - {k}: {parts}")
    if len(dec) >= 50:
        lines.append("- ENOUGH DATA: raise the bar for kinds mostly declined or corrected; say so in the report")
    lab = st.get("detector", {"real": 0, "noise": 0, "samples": []})
    tot = lab["real"] + lab["noise"]
    lines.append(f"- correction detector: {lab['real']} real / {lab['noise']} noise of {tot} labelled "
                 f"(threshold to propose a new pattern: 300)")
    for t in lab["samples"][-15:]:
        lines.append(f"  - noise: {t}")
    if tot >= 300:
        lines.append("- ENOUGH DATA: propose a tighter CORRECTION regex, tested with --count against the samples")
    lines.append("")
    return lines


def setup_health(inv, since_s):
    """Setup checks the usage logs can't see: leftover worktrees and branches, untracked piles,
    stale settings, skills shadowed by an older copy, and hooks that block or fail."""
    lines = ["## Setup health — verify each before proposing a fix"]

    # 1 + 4. git repos under home: worktrees, local-only branches, untracked files
    repos = []
    for pat in ("*/.git", "*/*/.git", "*/*/*/.git"):
        repos += [g.parent for g in Path.home().glob(pat) if g.is_dir() and "node_modules" not in str(g)]
    for repo in sorted(set(repos)):
        notes = []
        if not _git(repo, "rev-parse", "--verify", "-q", "origin/main"):
            base = "origin/master" if _git(repo, "rev-parse", "--verify", "-q", "origin/master") else ""
        else:
            base = "origin/main"
        wt = _git(repo, "worktree", "list", "--porcelain").split("\n\n")
        for block in wt[1:]:
            m = re.search(r"^worktree (.+)$", block, re.M)
            b = re.search(r"^branch refs/heads/(.+)$", block, re.M)
            if not m:
                continue
            dirty = len([l for l in _git(m.group(1), "status", "--short").splitlines() if l.strip()])
            ahead = len(_git(repo, "log", "--oneline", f"{base}..{b.group(1)}").splitlines()) if (b and base) else "?"
            notes.append(f"worktree {m.group(1)} [{b.group(1) if b else 'detached'}]: "
                         f"{dirty} uncommitted, {ahead} commits not on {base or 'main'}")
        for br in _git(repo, "for-each-ref", "--format=%(refname:short)|%(upstream:track)|%(upstream)",
                       "refs/heads").splitlines():
            name, track, up = (br.split("|") + ["", ""])[:3]
            if name in ("main", "master"):
                continue
            gone = (not up) or "gone" in track
            ahead = len(_git(repo, "log", "--oneline", f"{base}..{name}").splitlines()) if base else "?"
            if gone:
                notes.append(f"local branch {name}: no remote branch, {ahead} commits not on {base or 'main'}")
        untracked = len(_git(repo, "ls-files", "--others", "--exclude-standard").splitlines())
        if untracked >= 20:
            notes.append(f"{untracked} untracked files")
        if notes:
            lines.append(f"- {repo.name}: " + "; ".join(notes))

    # 2. settings: overrides for skills that no longer exist, hook scripts that are missing
    settings = [CONFIG / "settings.json"] + list(Path.home().glob("*/.claude/settings*.json"))
    for sf in settings:
        try:
            cfg = json.loads(sf.read_text(encoding="utf-8"))
        except Exception:
            continue
        for k in (cfg.get("skillOverrides") or {}):
            if k not in inv:
                lines.append(f"- {sf}: skillOverrides names '{k}', which no longer exists")
        for ev, groups in (cfg.get("hooks") or {}).items():
            for g in groups:
                for h in g.get("hooks", []):
                    base = None  # a bare name after a wrapper (_once.py x.py) sits next to the wrapper
                    for script in re.findall(r"[\w$/\:.{}\-\"]+\.py", h.get("command", "")):
                        path = script.strip('"').replace("$CLAUDE_PROJECT_DIR", str(sf.parent.parent))
                        path = os.path.expandvars(os.path.expanduser(path))
                        if base and not re.search(r"[/\\]", path):
                            path = str(Path(base) / path)
                        elif re.search(r"[/\\]", path):
                            base = str(Path(path).parent)
                        if "$" not in path and not Path(path).exists():
                            lines.append(f"- {sf} {ev} hook: script missing: {path}")

    # 3. a user-level skill overrides a project copy; flag when the project copy is newer
    for name, copies in inv.items():
        user = [c for c in copies if c["scope"] == "user"]
        proj = [c for c in copies if c["scope"].startswith("project:")]
        for pc in proj:
            if user and pc["mtime"] > user[0]["mtime"]:
                lines.append(f"- {name}: user-level copy ({time.strftime('%Y-%m-%d', time.localtime(user[0]['mtime']))}) "
                             f"overrides the newer {pc['scope']} copy "
                             f"({time.strftime('%Y-%m-%d', time.localtime(pc['mtime']))}); edits to the project copy don't run")

    # 5. hooks: how often each one blocked, and any that reported a skip or error
    blocks, problems = Counter(), Counter()
    for proj, f in iter_session_files(since_s):
        if is_automated(proj):
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for m in re.finditer(r'blocking error from command: \\"([^\\"]+)', text):
            blocks[m.group(1)] += 1
        for m in re.finditer(r'"type":"hook_system_message"[^}]{0,400}?"content":"([^"]{0,120})', text):
            if re.search(r"skipped|error|failed|not found|timed out", m.group(1), re.I):
                problems[m.group(1)[:90]] += 1
    for k, n in blocks.most_common(10):
        lines.append(f"- hook blocked {n}x: {k}")
    for k, n in problems.most_common(10):
        lines.append(f"- hook reported a problem {n}x: {k}")

    if len(lines) == 1:
        lines.append("- nothing flagged")
    lines.append("")
    return lines


# Lines that talk *about* an old path or banned term (history notes, never-use lists) aren't uses of it.
HISTORY_LINE = re.compile(r"\b(deleted|retired|removed|superseded|deprecated|banned|never|avoid|instead of|"
                          r"no longer|stale|replaced|was moved|moved to|old copy|don'?t (use|read|write))\b", re.I)
# Folders never walked: archives, caches, old plugin copies, worktrees, dated campaign output,
# and the coach's own snapshots of the public docs (they describe ~/.claude, not this setup).
PRUNE = {"skills-archive", "file-history", ".trash", "cache", "node_modules", ".git", "worktrees",
         "campaigns", "docs_snapshots", "__pycache__"}


def _repos():
    found = []
    for pat in ("*/.git", "*/*/.git", "*/*/*/.git"):
        found += [g.parent for g in Path.home().glob(pat) if g.is_dir() and "node_modules" not in str(g)]
    return sorted(set(found))


def _live_lines(text):
    """(line number, line) for lines that state something as current. Skips lines where the line or the
    two before it talk about history ("retired", "deleted"…), and anything between
    <!-- coach:skip-start --> and <!-- coach:skip-end --> (kept-on-purpose historical examples)."""
    rows, skipping = text.splitlines(), False
    for n, line in enumerate(rows, 1):
        if "coach:skip-start" in line:
            skipping = True
        elif "coach:skip-end" in line:
            skipping = False
        elif not skipping and not any(HISTORY_LINE.search(l) for l in rows[max(0, n - 3):n]):
            yield n, line


def _walk_md(root, only_claude_md=False):
    for dirpath, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if d not in PRUNE and not d.endswith("-workspace")]
        for n in names:
            if (n == "CLAUDE.md") if only_claude_md else n.endswith(".md"):
                yield Path(dirpath) / n


def instruction_files():
    """The files that tell Claude what to read and how to write: skills, commands, every CLAUDE.md,
    memory, and the repos' context folders. Old copies, archives and dated campaign output are left out."""
    files = set(_walk_md(CONFIG / "skills")) | set((CONFIG / "commands").glob("*.md"))
    files |= {p for p in [CONFIG / "CLAUDE.md"] if p.exists()}
    for proj in (CONFIG / "projects").glob("*"):
        files |= {p for p in [proj / "CLAUDE.md"] if p.exists()}
        files |= set((proj / "memory").glob("*.md"))
        if (proj / "skills").is_dir():
            files |= set(_walk_md(proj / "skills"))
    for sub in CONFIG.iterdir():
        if sub.is_dir() and sub.name not in PRUNE and sub.name not in ("projects", "skills", "plugins"):
            files |= set(_walk_md(sub, only_claude_md=True))
    for repo in _repos():
        files |= set(_walk_md(repo, only_claude_md=True))
        for sub in (".claude/skills", "context", "product-marketing", "channels"):
            if (repo / sub).is_dir():
                # performance logs record what was posted; they're history, not instructions
                files |= {f for f in _walk_md(repo / sub) if "performance" not in f.name}
    return sorted(files)


WIN_PATH = re.compile(r"(?<![\w/])(?:[A-Za-z]:[\\/](?![\\/])|~[\\/])[^`\"'<>|*?\n\r)\]]+")


def _resolve(raw):
    """The longest prefix of `raw` (cut at spaces) that exists, else None. Paths can contain spaces,
    so try the whole match first, then shorter cuts."""
    raw = raw.rstrip(" .,;:")
    cuts = [raw] + [raw[:i].rstrip(" .,;:") for i in range(len(raw) - 1, 0, -1) if raw[i] == " "]
    for c in cuts:
        if Path(os.path.expanduser(c)).exists():
            return c
    return None


def dead_paths(files):
    """Absolute paths written inside instruction files that no longer exist on disk."""
    lines = ["## Paths that no longer exist — named in skills, CLAUDE.md, memory or context files",
             "Each one sends Claude to a file that's gone (or to an old copy). Repoint it to the live file."]
    missing = defaultdict(list)
    for f in files:
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for n, line in _live_lines(text):
            for m in WIN_PATH.finditer(line):
                raw = m.group(0)
                # Placeholders and scratch locations (Downloads, image cache) come and go by design.
                if any(t in raw for t in ("<", "{", "[", "YYYY", "...", "%", "$", "Downloads", "image-cache")) \
                        or _resolve(raw):
                    continue
                key = raw.split(" ")[0].rstrip(" .,;:")
                missing[key].append(f"{f}:{n}")
    for path, where in sorted(missing.items(), key=lambda kv: -len(kv[1]))[:40]:
        lines.append(f"- {path} — named in {len(where)} place(s): " + "; ".join(where[:6])
                     + (" …" if len(where) > 6 else ""))
    if len(lines) == 2:
        lines.append("- nothing flagged")
    lines.append("")
    return lines


def banned_terms():
    """The never-use list from the canonical messaging framework, as (label, regex) pairs.
    Entries that only make sense in context (", as positioning", "as the headline") are skipped."""
    terms = []
    for repo in _repos():
        mf = repo / "product-marketing" / "messaging-framework.md"
        if not mf.exists():
            continue
        text = mf.read_text(encoding="utf-8", errors="replace")
        block = re.search(r"### Never use\s*\n(.*?)(?:\n###|\n## |\Z)", text, re.S)
        if not block:
            continue
        for row in block.group(1).splitlines():
            cells = [c.strip() for c in row.strip().strip("|").split("|")]
            if len(cells) < 2 or set(cells[0]) <= set("-: ") or cells[0].lower() == "banned":
                continue
            for item in re.split(r"\s+·\s+|\s+/\s+", cells[0]):
                item = item.strip().strip("\"'“”*")
                if re.search(r",\s*(as|without)\b|\bas the headline\b", item):
                    item = re.split(r",\s*without\b", item)[0].strip() if "without" in item else ""
                item = item.split("→")[0].strip().strip("\"'“”")
                if len(item) >= 4:
                    terms.append((item, re.compile(r"(?<![\w-])" + re.escape(item).replace(r"\ ", r"\s+")
                                                   + r"(?![\w-])", re.I)))
        break
    return terms


def retired_terms(files):
    """Banned terms still written in instruction and context files (where they get copied into new work)."""
    terms = banned_terms()
    lines = ["## Retired terms still in use — skills, CLAUDE.md, memory or context files",
             "Source: the never-use list in product-marketing/messaging-framework.md."
             + ("" if terms else " (Not found: check skipped.)")]
    hits = defaultdict(list)
    for f in files:
        if f.name in ("messaging-framework.md", "positioning-changelog.md"):
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for n, line in _live_lines(text):
            for label, rx in terms:
                if rx.search(line):
                    hits[label].append(f"{f}:{n}")
    # Retired phrases first (a whole old line or category is the costly kind); single house-rule words last.
    for label, where in sorted(hits.items(), key=lambda kv: (-len(kv[0].split()), -len(kv[1]))):
        lines.append(f"- \"{label}\" — {len(where)} line(s): " + "; ".join(where[:6]) + (" …" if len(where) > 6 else ""))
    if terms and len(lines) == 2:
        lines.append("- nothing flagged")
    lines.append("")
    return lines


def check():
    """Fast, incremental. Silent unless a threshold is crossed since the last review."""
    st = load_state()
    now = time.time()
    since = st.get("last_review_ts") or (now - 30 * DAY)
    recent = now - st.get("last_check_ts", 0) < 6 * 3600
    if recent and not st.get("pending_nudge"):
        return
    if recent and st.get("nudge_text"):
        print(st["nudge_text"])  # reuse the last result; no rescan
        return
    prompts = [p for p in prompts_since(int(since * 1000)) if not is_automated(p["project"])]
    corrections = sum(1 for p in prompts if CORRECTION.search(p["text"]))
    sessions = len({p["session"] for p in prompts if p["session"]})
    _, denials, _, _ = scan_sessions(since)
    st["denials_since_review"] = len(denials)
    st["last_check_ts"] = now
    hits = []
    if corrections >= THRESHOLDS["corrections"]:
        hits.append(f"{corrections} corrections")
    if st["denials_since_review"] >= THRESHOLDS["denials"]:
        hits.append(f"{st['denials_since_review']} blocked actions")
    if sessions >= THRESHOLDS["sessions"]:
        hits.append(f"{sessions} sessions")
    last = st.get("last_review_ts")
    days_since = (now - last) / DAY if last else 999
    # Weekly by default; sooner (but not more than every 3 days) when a threshold is crossed.
    due = days_since >= WEEKLY_DAYS or (hits and days_since >= MIN_GAP_DAYS)
    st["pending_nudge"] = bool(due)
    st["nudge_text"] = ""
    if due:
        when = ("since " + time.strftime("%b %d", time.localtime(last))) if last else "in the last 30 days"
        why = ", ".join(hits) if hits else "weekly review"
        st["nudge_text"] = (f"AI COACH REVIEW DUE ({why} {when}). Run the ai-coach skill automatically in this "
                            f"session: if the user's first message is a quick question or greeting, run it first; "
                            f"if it's real work, finish that, then run it. Present the ranked recommendations and "
                            f"ask for the batch answer. Apply nothing without approval.")
        print(st["nudge_text"])
    save_state(st)


def digest(days=None, out=None):
    st = load_state()
    now = time.time()
    since = now - days * DAY if days else (st.get("last_review_ts") or now - 30 * DAY)
    prompts = prompts_since(int(since * 1000))
    mine = [p for p in prompts if not is_automated(p["project"])]
    skills, denials, interrupts, sessions = scan_sessions(since)

    lines = [f"# AI coach digest — since {time.strftime('%Y-%m-%d', time.localtime(since))}", ""]
    parked = st.get("parked", [])
    if parked:
        lines.append("## Parked from earlier reviews — re-check each against this window first")
        lines += [f"{i}. [{p['date']}] {p['text']}" for i, p in enumerate(parked, 1)]
        lines.append("")
    lines += recheck_applied(st)
    rejected = st.get("rejected", [])
    if rejected:
        lines.append("## Declined at earlier reviews — do not re-propose unless the user repeated it since")
        lines += [f"- [{p['date']}] {p['text']}" for p in rejected]
        lines.append("")
    lines.append(f"Interactive prompts: {len(mine)} · automated prompts: {len(prompts) - len(mine)} · "
                 f"session logs touched: {sessions} · interrupts: {interrupts} · permission denials: {len(denials)}")
    lines.append("")

    by_proj = Counter(p["project"] for p in mine)
    lines.append("## Prompts by project")
    lines += [f"- {n} · {proj}" for proj, n in by_proj.most_common()]
    lines.append("")

    slash = Counter(p["text"].split()[0] for p in mine if p["text"].startswith("/"))
    lines.append("## Slash commands typed")
    lines += [f"- {n} · {c}" for c, n in slash.most_common(30)] or ["- none"]
    lines.append("")

    lines.append("## Skills invoked (from session logs)")
    lines += [f"- {n} · {s}" for s, n in skills.most_common(40)] or ["- none"]
    lines.append("")

    inv, old_versions = skill_inventory()
    used = {s.split(":")[-1] for s in skills}
    lines.append(f"## Skill inventory ({len(inv)} skills) — newest copy first; map each correction to its owner here")
    for name in sorted(inv):
        top = inv[name][0]
        tag = "" if name in used else "  [not invoked]"
        lines.append(f"- {name}{tag} · {top['scope']} · {time.strftime('%Y-%m-%d', time.localtime(top['mtime']))}"
                     f" · {top['desc']}")
    lines.append("")
    dupes = {n: c for n, c in inv.items() if len(c) > 1}
    lines.append(f"## Skills that exist in more than one place ({len(dupes)}) · "
                 f"old plugin-cache versions on disk: {old_versions}")
    for name, copies in sorted(dupes.items()):
        lines.append(f"- {name}: " + " | ".join(
            f"{c['scope']} ({time.strftime('%Y-%m-%d', time.localtime(c['mtime']))})" for c in copies))
    lines.append("")

    lines += setup_health(inv, since)
    files = instruction_files()
    lines += dead_paths(files)
    lines += retired_terms(files)
    lines += knowledge_files({p["project"] for p in mine if p["project"]})
    lines += rewrites(since)

    cur, seen = claude_version(), st.get("claude_version_reviewed", "")
    lines.append("## Claude Code releases — check the changelog for features that fit how the user works")
    lines.append(f"- installed {cur or '?'} · last reviewed at {seen or 'never'}"
                 + ("" if cur != seen else " · no new releases since the last review"))
    lines.append("")
    lines += self_learning(st)
    lines += model_fit_section(since)
    lines += clear_fit_section(since)

    def stamp(p):
        return (f"- [{time.strftime('%m-%d', time.localtime(p['ts'] / 1000))} s:{(p['session'] or '?')[:6]}] "
                f"{Path(p['project']).name}: ")

    corr = [p for p in mine if CORRECTION.search(p["text"])]
    lines.append(f"## Correction-like prompts ({len(corr)}) — cluster these by theme")
    for p in corr[-150:]:
        lines.append((stamp(p) + p["text"][:200]).replace("\n", " "))
    lines.append("")

    pasted = [p for p in mine if len(p["text"]) > 280 or "[Pasted text" in p["text"]]
    lines.append(f"## Long or pasted prompts ({len(pasted)}) — check for copy the user rewrote themselves")
    for p in pasted[-60:]:
        lines.append((stamp(p) + p["text"][:200]).replace("\n", " "))
    lines.append("")

    lines.append(f"## Permission denials ({len(denials)})")
    for d in denials[-60:]:
        lines.append(f"- {d['project']}: {d['text']}")
    lines.append("")

    lines.append("## All interactive prompts (oldest first) — find repeated requests with no skill behind them")
    for p in mine[-1200:]:
        lines.append((stamp(p) + p["text"][:160]).replace("\n", " "))
    lines.append("")

    mem = []
    for md in (CONFIG / "projects").glob("*/memory"):
        for f in md.glob("feedback_*.md"):
            mem.append(f"{md.parent.name}/{f.name}")
    lines.append(f"## Saved feedback memories ({len(mem)}) — look for overlaps and rules that belong in a skill or hook")
    lines += [f"- {m}" for m in sorted(mem)]

    text = "\n".join(lines)
    if out:
        Path(out).write_text(text, encoding="utf-8")
        print(f"Digest written: {out} ({len(text)//1024} KB, {len(mine)} prompts)")
    else:
        sys.stdout.write(text)


def mark_reviewed():
    st = load_state()
    st["last_review_ts"] = time.time()
    st["claude_version_reviewed"] = claude_version() or st.get("claude_version_reviewed", "")
    st["denials_since_review"] = 0
    st["pending_nudge"] = False
    st["nudge_text"] = ""
    save_state(st)
    print("AI coach: review recorded.")


def park(text):
    st = load_state()
    st.setdefault("parked", []).append({"date": time.strftime("%Y-%m-%d"), "text": text})
    save_state(st)
    print(f"Parked #{len(st['parked'])}: {text[:80]}")


def reject(text):
    st = load_state()
    st.setdefault("rejected", []).append({"date": time.strftime("%Y-%m-%d"), "text": text})
    save_state(st)
    print(f"Declined, won't re-propose unless it recurs: {text[:80]}")


def applied(text, watch, baseline):
    st = load_state()
    st.setdefault("applied", []).append({"date": time.strftime("%Y-%m-%d"), "text": text,
                                         "watch": watch or "", "baseline": baseline or ""})
    save_state(st)
    print(f"Recorded applied #{len(st['applied'])}: {text[:80]}")


def decide(kind, outcome, text):
    st = load_state()
    st.setdefault("decisions", []).append({"date": time.strftime("%Y-%m-%d"), "kind": kind,
                                           "outcome": outcome, "text": text})
    save_state(st)
    print(f"Logged {kind}/{outcome}: {text[:80]}")


def label(real, noise, samples):
    st = load_state()
    d = st.setdefault("detector", {"real": 0, "noise": 0, "samples": []})
    d["real"] += real
    d["noise"] += noise
    d["samples"] = (d["samples"] + [x[:100] for x in samples])[-200:]
    save_state(st)
    print(f"Detector: {d['real']} real / {d['noise']} noise labelled so far")


def unpark(n):
    st = load_state()
    items = st.get("parked", [])
    if 1 <= n <= len(items):
        gone = items.pop(n - 1)
        save_state(st)
        print(f"Unparked: {gone['text'][:80]}")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    args = sys.argv[1:]
    try:
        if "--check" in args:
            check()
        elif "--mark-reviewed" in args:
            mark_reviewed()
        elif "--park" in args:
            park(args[args.index("--park") + 1])
        elif "--reject" in args:
            reject(args[args.index("--reject") + 1])
        elif "--unpark" in args:
            unpark(int(args[args.index("--unpark") + 1]))
        elif "--count" in args:
            days = int(args[args.index("--days") + 1]) if "--days" in args else 30
            h, n, _ = count_hits(args[args.index("--count") + 1], days)
            print(f"{h}/{n} prompts in {days}d = {100 * h / n if n else 0:.1f} per 100 · baseline string: {h}/{n}")
        elif "--applied" in args:
            applied(args[args.index("--applied") + 1],
                    args[args.index("--watch") + 1] if "--watch" in args else "",
                    args[args.index("--baseline") + 1] if "--baseline" in args else "")
        elif "--decide" in args:
            i = args.index("--decide")
            decide(args[i + 1], args[i + 2], args[i + 3])
        elif "--label" in args:
            kv = dict(x.split("=") for x in args[args.index("--label") + 1:args.index("--label") + 3] if "=" in x)
            samples = [args[i + 1] for i, a in enumerate(args) if a == "--noise" and i + 1 < len(args)]
            label(int(kv.get("real", 0)), int(kv.get("noise", 0)), samples)
        else:
            days = int(args[args.index("--days") + 1]) if "--days" in args else None
            out = args[args.index("--out") + 1] if "--out" in args else None
            digest(days, out)
    except Exception as e:  # the session-start check must never break a session
        if "--check" not in args:
            raise
