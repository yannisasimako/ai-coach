<p align="center">
  <img src="docs/banner-v1.png" alt="AI Coach: how you work with Claude Code, reviewed every week. A racing bike on training wheels. By Yannis Asimakopoulos, yannisasimako.substack.com." width="800">
</p>

<h2 align="center">A weekly review of how you work with Claude Code,<br>and a check on whether last week's changes helped.</h2>

<p align="center">Built by a marketer, not an engineer. For anyone who uses Claude Code every day<br>and keeps adding skills, rules and hooks without knowing which ones help.</p>

## What a review looks like

Once a week, after you finish a task, Claude posts a review in your session. It has three parts:
how your setup is doing, whether last week's changes helped, and what to change next:

> **How your setup is doing**
>
> ✅ **Working:** your `/blog-draft` skill runs every day and rarely needs a fix.<br>
> ❌ **Not working:** Claude keeps skipping your "always end with a CTA" rule.<br>
> 🎯 **Biggest gap:** no skill turns a blog post into LinkedIn posts, so you rewrite every draft by hand.
>
> **Did last week's changes help?**
>
> ✅ **Worked:** the rule "keep LinkedIn posts under 150 words". You told Claude "too long" 6 times per 100 prompts before it, once since.<br>
> ⚠️ **No effect:** the rule "always end with a CTA". You still added the CTA yourself 4 times per 100 prompts. Next step: build it into the `/blog-draft` skill.
>
> **What to change next**
>
> 1️⃣ **Build a `/social-from-blog` skill.** You rewrote the opening of 5 LinkedIn drafts by hand this week. No existing skill does this. About 20 minutes of Claude's time.<br>
> 2️⃣ **Archive the `/event-recap` skill.** You haven't used it in 30 days, and nothing depends on it. 1 minute.<br>
> 3️⃣ **Delete 3 old branches** that are already merged. 1 minute.
>
> *Reply in one line, like `1 yes, 2 no, 3 later`.*

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

## Questions people ask

<details>
<summary><b>How is this different from <code>/insights</code>?</b></summary>

`/insights` gives you a snapshot when you run it. The coach reads that snapshot as one input,
remembers what you approved or declined, and checks the next week whether each change helped.
</details>

<details>
<summary><b>Does it change anything on its own?</b></summary>

No. It proposes, you answer, and it only applies your yeses.
</details>

<details>
<summary><b>Does it read my code?</b></summary>

No. It reads your prompts, session logs and memories, plus the files that tell Claude what to do:
CLAUDE.md files and skills.
</details>

<details>
<summary><b>Does it work with claude.ai or the Claude app?</b></summary>

No. It reads Claude Code's files on your computer.
</details>

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
