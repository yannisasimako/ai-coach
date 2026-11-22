"""Which Claude Code docs pages changed since the last /ai-coach review.

    python docs_check.py --out DIR     fetch the watched pages, write a report + unified diffs to DIR
    python docs_check.py --accept      save the fetched pages as the new baseline (run at review close)

Kept apart from scan.py so the usage scanner stays local-only. The docs pages carry no
last-updated date, so each page's Markdown is compared with the copy saved at the last review.
"""

import difflib
import os
import sys
import urllib.request
from pathlib import Path

BASE = "https://code.claude.com/docs/en/"
PAGES = ["best-practices", "memory", "skills", "hooks", "sub-agents", "whats-new/index"]
# Per profile, next to that profile's state.json (see DATA in scan.py).
CONFIG = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
SNAP = CONFIG / "ai-coach-data" / "docs_snapshots"
PENDING = SNAP / "_pending"


def fetch(page):
    req = urllib.request.Request(BASE + page + ".md", headers={"User-Agent": "ai-coach-docs-check"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")


def name(page):
    return page.replace("/", "__") + ".md"


def check(out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    PENDING.mkdir(parents=True, exist_ok=True)
    report = ["# Claude Code docs — changes since the last review", ""]
    for page in PAGES:
        try:
            new = fetch(page)
        except Exception as e:
            report.append(f"- {page}: fetch failed ({e}); skip it this review")
            continue
        (PENDING / name(page)).write_text(new, encoding="utf-8")
        old_path = SNAP / name(page)
        if not old_path.exists():
            (out / name(page)).write_text(new, encoding="utf-8")
            report.append(f"- {page}: first review — audit the whole page: {out / name(page)}")
            continue
        old = old_path.read_text(encoding="utf-8")
        if old == new:
            report.append(f"- {page}: unchanged")
            continue
        diff = "".join(difflib.unified_diff(old.splitlines(True), new.splitlines(True),
                                            f"{page} (last review)", f"{page} (now)"))
        (out / (name(page) + ".diff")).write_text(diff, encoding="utf-8")
        report.append(f"- {page}: CHANGED — read the diff: {out / (name(page) + '.diff')}")
    text = "\n".join(report) + "\n"
    (out / "docs-report.md").write_text(text, encoding="utf-8")
    sys.stdout.write(text)


def accept():
    if not PENDING.exists():
        print("Nothing fetched yet; run --out first.")
        return
    for f in PENDING.glob("*.md"):
        f.replace(SNAP / f.name)
    PENDING.rmdir()
    print("Docs baseline saved.")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    a = sys.argv[1:]
    if "--accept" in a:
        accept()
    else:
        check(a[a.index("--out") + 1] if "--out" in a else ".")
