# AI coach for Claude Code

A Claude Code skill that reviews how you work with Claude once a week, proposes up to three
changes at a time, and checks at the next review whether the changes you approved actually helped.

I built it for myself, a marketer, not an engineer. It's shared as-is: it runs on my setup, and
you'll likely want to adapt it to yours.

## What a review looks like

1. When a review is due, the coach reads your recent Claude Code sessions, locally.
2. It grades the changes you approved last time: worked, no effect, or worse.
3. It reviews four things: your setup, your time, your team, and what's new outside.
4. A second AI checks every proposal against the evidence before you see it.
5. It shows you three proposals at a time. You answer in one line: `1 yes, 2 no, 3 later`.
6. It applies only your yeses, and notes a before-number for each so the next review can grade it.

Declined ideas aren't proposed again. Parked ones come back at the next review.

## Install

Needs Claude Code and Python 3.

1. Copy this folder to `~/.claude/skills/ai-coach/`.
2. Run your first review: type `/ai-coach` in Claude Code.
3. Optional, for the weekly nudge: add a SessionStart hook to `~/.claude/settings.json`:

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

When a review is due (weekly, or sooner if you keep correcting Claude), it prints a one-line
notice and Claude runs the review in that session.

If you use a different config folder, set `CLAUDE_CONFIG_DIR`.

## What it reads

Everything stays on your machine. `scripts/scan.py` reads, read-only:
- `~/.claude/history.jsonl` (your prompts)
- `~/.claude/projects/*/*.jsonl` (session logs: skill calls, blocked actions, interrupts)
- saved feedback memories and your skill files

Its own record (`state.json`: past decisions, applied changes and their before-numbers) is written
next to the skill and is git-ignored. `scripts/docs_check.py` fetches public Claude Code docs pages
to spot what changed.

## Files

- `SKILL.md`: the review method
- `scripts/scan.py`: builds the digest, the weekly check, and the decision log
- `scripts/docs_check.py`: diffs the Claude Code docs since the last review
- `bets.md`: the backlog of ideas worth a test
- `team.local.example.md`: optional, if you share skills with a team

## License

MIT
