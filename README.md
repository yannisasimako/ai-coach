# AI Coach for Claude Code

A Claude Code skill that reviews how you work with Claude every week, proposes up to three
changes at a time, and checks at the next review whether the changes you approved actually helped.

Built by a marketer, not an engineer, for people who run real work through Claude Code and can't
tell whether their setup is getting better or just getting bigger.

## Why

Claude Code's `/insights` gives you a snapshot when you remember to run it. This coach:

- **runs itself.** A review comes due weekly, or sooner when you've been correcting Claude a lot.
- **remembers your decisions.** Every yes, no and later is logged. Declined ideas don't come back.
- **follows up.** Every change you approve gets a before-number, and the next review grades it:
  worked, no effect, or worse.
- **makes the change once you say yes.** Nothing changes without your OK.
- **checks itself.** A second AI verifies every proposal against the evidence before you see it.
- **looks outside.** New Claude Code releases and docs changes become ideas worth testing.

## What a review looks like

1. The coach reads your recent Claude Code sessions, on your machine.
2. It grades the changes you approved last time.
3. It reviews four areas: your setup, your time, your team, and what's new.
4. A second AI checks every proposal.
5. It shows you three at a time. You answer in one line: `1 yes, 2 no, 3 later`.
6. It applies your yeses and records a before-number for each.

A real proposal from one review:

> **Biggest gap:** content briefs are written by hand, and there are a lot of them in the backlog.
> **Proposal:** build a `/content-brief` skill. The last brief needed at least five corrections.
> Start with a short interview, then build it.

## What it looks at

| Area | Examples |
|---|---|
| Setup | Corrections you keep repeating, rules that get broken anyway, tasks you still do by hand, skills nobody runs, stale memory and CLAUDE.md conflicts, leftover branches and broken hooks |
| Time | How often the skills that run your day actually get used, and why not |
| Team | Whether what you learn reaches the people who use your skills (skip it if you work alone) |
| What's new | Claude Code releases and docs changes since the last review, scored as "bets" worth a test |

## Install

Needs Claude Code and Python 3. Takes about five minutes.

1. Copy this folder to `~/.claude/skills/ai-coach/`:
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
   When a review is due, the hook prints a one-line notice and Claude runs the review in that
   session.

On macOS or Linux, use `python3` if `python` isn't found. If you use a different config folder,
set `CLAUDE_CONFIG_DIR`.

## Cost

A typical review takes about half an hour from start to last change shipped, and only 10–15
minutes of that is you reading and answering. Claude does the rest.

## Privacy

Everything stays on your machine. `scripts/scan.py` reads, read-only:

- `~/.claude/history.jsonl` (your prompts)
- `~/.claude/projects/*/*.jsonl` (session logs: skill calls, blocked actions, interrupts)
- your saved feedback memories and skill files

The coach's own record (`state.json`: decisions, applied changes, before-numbers) is written next
to the skill and is git-ignored. `scripts/docs_check.py` fetches public Claude Code docs pages to
spot what changed. Nothing else leaves your machine.

## Files

| File | What it does |
|---|---|
| `SKILL.md` | The review method Claude follows |
| `scripts/scan.py` | Builds the usage digest, the weekly check, and the decision log |
| `scripts/docs_check.py` | Diffs the Claude Code docs since the last review |
| `bets.md` | Backlog of ideas worth a test, re-scored each review |
| `team.local.example.md` | Optional: describe your teammates for the team review |

## Status

Shared as-is. It runs daily on my setup (Windows). It should work on macOS and Linux but hasn't
been tested there yet. Issues and pull requests are welcome.

## The story behind it

I wrote about why I built it and what it's caught so far: **[Look mom, no hands.](https://yannisasimako.substack.com)**

Yannis Asimakopoulos · [Substack](https://yannisasimako.substack.com) · [LinkedIn](https://www.linkedin.com/in/yannis-asimakopoulos)

## License

MIT
