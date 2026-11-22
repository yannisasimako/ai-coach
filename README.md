<p align="center">
  <img src="docs/banner-v1.png" alt="AI Coach: how you work with Claude Code, reviewed every week. A racing bike on training wheels. By Yannis Asimakopoulos, yannisasimako.substack.com." width="800">
</p>

<h2 align="center">A weekly review of how you work with Claude Code,<br>and a check on whether last week's changes helped.</h2>

<p align="center">Built by a marketer, not an engineer. For people who run real work through Claude Code<br>and can't tell if their setup is getting better or just getting bigger.</p>

## What a review looks like

> **State of the system**
> Works: the `/blog-draft` skill runs every day and rarely needs fixing.
> Doesn't: LinkedIn copy still gets rewritten by hand.
> Biggest gap: no skill turns a blog post into social posts.
>
> **Last week's changes**
> - Memory: "keep LinkedIn posts under 150 words" — **worked.** "Too long" corrections went from 6 to 1 per 100 prompts.
> - Memory: "always end with a CTA" — **no effect.** Missing-CTA fixes stayed at 4 per 100 prompts.
>   Next: move the rule into the `/blog-draft` skill.
>
> **Proposals**
> 1. **Build a `/social-from-blog` skill.** You rewrote the opening of 5 LinkedIn drafts by hand
>    this week (Nov 3, 5, 6). Checked: no existing skill does this. Effort: about 20 min of Claude's time.
> 2. **Archive `/event-recap`.** Not run in 30 days, and no other file mentions it. Effort: 1 min.
> 3. **Housekeeping:** 3 merged branches still on GitHub. Delete them? One yes or no.
>
> *Answer in one line: `1 yes, 2 no, 3 later`*

*Made-up example.*

## Install

Needs Claude Code and Python 3. Takes about five minutes.

1. Copy this folder into your skills:
   ```
   git clone https://github.com/yannisasimako/ai-coach.git ~/.claude/skills/ai-coach
   ```
2. In Claude Code, type `/ai-coach` to run your first review.
3. To make it run itself, add a SessionStart hook to `~/.claude/settings.json`:
   ```json
   {
     "hooks": {
       "SessionStart": [
         { "hooks": [ { "type": "command",
           "command": "python ~/.claude/skills/ai-coach/scripts/scan.py --check" } ] }
       ]
     }
   }
   ```
   Already have hooks? Add this inside your existing `SessionStart` list.

On macOS or Linux, use `python3` if `python` isn't found. If you keep Claude Code's config
somewhere else, set `CLAUDE_CONFIG_DIR`.

## How it works

| Step | What happens |
|---|---|
| **Read** | Your recent sessions, prompts, saved memories and skills, plus your latest `/insights` report (Claude Code's built-in usage report). |
| **Grade** | Each change you approved last time: worked, no effect, or worse. |
| **Check** | A separate Claude agent, which only sees the claims, checks each proposal against the evidence. Weak ones are dropped. |
| **Propose** | Three at a time, each with its evidence and effort. |
| **Apply** | Only your yeses. Before a change, the coach counts how often the problem shows up. Next week it counts again. |

It reviews four areas:

| Area | What it looks for |
|---|---|
| **Your setup** | Corrections you keep repeating, rules that get broken anyway, tasks still done by hand, skills nobody runs, stale memory, broken hooks |
| **Your routines** | If you use skills for recurring work, like a morning plan or meeting prep, whether they get used and what you still do by hand |
| **Your team** | Whether what you learn reaches the people who use your skills. Skipped if you work alone. |
| **What's new** | Claude Code releases and docs changes, scored as ideas worth a test |

<details>
<summary>What's in the folder</summary>

| File | What it does |
|---|---|
| `SKILL.md` | The review method Claude follows |
| `scripts/scan.py` | Reads your usage, runs the weekly check, logs your decisions |
| `scripts/docs_check.py` | Spots what changed in the Claude Code docs since the last review |
| `bets.md` | Starting point for your list of ideas to try |
| `team.local.example.md` | Optional: describe your teammates for the team review |

Your own record lives in `~/.claude/ai-coach-data/`, outside this folder. Updating the skill never
touches it.

</details>

## Using it

A review comes due once a week, or sooner if you've been correcting Claude a lot. Claude runs it in
your next session, once your task is done. You answer in one line, like `1 yes, 2 no, 3 later`, and
can ask about any item first. Declined ideas don't come back. Parked ones get checked again next
time. To run one yourself, type `/ai-coach`.

## Privacy and time

The scanner runs on your machine. It reads:

- your prompts and session logs in `~/.claude`
- your saved memories and skill files
- your `/insights` report, if you have one

The scanner turns that into a summary. The review is a normal Claude Code session, so Claude reads
the summary like anything else you send it. Nothing goes anywhere else. The coach's own record (your decisions and its counts) stays
local and out of git. The only thing it fetches is the public Claude Code docs, to spot what changed.

A review takes about half an hour from start to last change shipped. 10–15 minutes of that is you
reading and answering.

## If something goes wrong

| Problem | Fix |
|---|---|
| `python` not found | Use `python3` in the hook command. On Windows, try `py`. |
| The hook runs but no review ever comes due | Check the path in the hook points at `scripts/scan.py` inside your skills folder. |

## Status

I use it every week on my own setup, on Windows. It should work on macOS and Linux, but I haven't
tested it there yet. Issues and pull requests are welcome.

Why I built it and what it's caught so far: **[Fast, or just pedaling hard?](https://yannisasimako.substack.com/p/fast-or-just-pedaling-hard)**

---

## Built by Yannis Asimakopoulos

Honest writing on marketing, AI, and figuring it out as you go.

[LinkedIn](https://www.linkedin.com/in/yannis-asimakopoulos/) · [Substack](https://substack.com/@yannisasimako)

More from me: **[Competitor Watch](https://github.com/yannisasimako/competitor-watch)**, every competitor move, checked against your positioning.

---

MIT license
