---
name: ai-coach
description: "A weekly coach for how you work with Claude Code. Reviews your sessions across all projects in four parts, then applies only what you approve: your setup (what keeps going wrong, what to automate, what's no longer true), your time (the skills that run your day), your team (whether what you learn reaches them) and the frontier (new Claude features and practices worth a test). Use when the user says /ai-coach, asks how to use Claude better, what skills to build, what they keep correcting, or wants a setup audit. Also run it automatically, without being asked, when a session-start notice says 'AI COACH REVIEW DUE'. Otherwise never run it unprompted."
---

# AI coach

A periodic review of how the user works with Claude, across every project on this machine, in four
parts: two face inward (their setup, their time) and two outward (their team, the frontier).
The output is the state of the system in three lines, then a ranked list of concrete changes, each
tied to evidence, that the user approves in batches. Nothing changes without their OK.

## Principles

- **Top-down first.** Start from what the system is for: who uses it, what gets shipped, the current
  goals. Then look for evidence. Never build the list bottom-up from the digest's counts.
- **Rank by impact on what ships, then by time saved.** Conveniences are housekeeping, however
  often they run.
- **Equal weight inward and outward.** Half the list comes from setup and time, half from team and
  frontier. A side with fewer items says it came up short; the other side doesn't fill the gap.
- **Judge the system, never the person.** A teammate who doesn't use a skill is a finding about the
  skill or how it reaches them.
- **Grade a change by the outcome it targeted.** A usage count is not quality. Where nothing
  measures the outcome, say "unmeasured".

## Data

`scripts/scan.py` reads, read-only:
- `<config>/history.jsonl`: every prompt the user typed, all projects, with timestamps and session IDs.
- `<config>/projects/*/*.jsonl`: session logs (skill calls, permission denials, interrupts).
- `<config>/projects/*/memory/feedback_*.md`: corrections the user already asked Claude to remember.
- Every reachable `SKILL.md`: user skills, project skills (`~/*/.claude/skills`), plugin sources in
  repos (`~/*/plugins/*/skills`) and the plugin cache (newest version only).

`<config>` is `$CLAUDE_CONFIG_DIR`, else `~/.claude`. Sessions under a Temp folder are automated runs
(headless jobs, background agents) and are kept out of the user's own numbers. The scan is local and
depends on no outside service. Connected tools (issue tracker, chat search, docs) may be read,
read-only; nothing is written through them except in step 9, on the user's yes.

Never send this data anywhere, never quote secrets, tokens or personal data from it in the report,
and refer to personal projects by folder name only. Skip anything about health, legal matters or
personal finance entirely; say only that it was skipped.

## Method: run every step

1. **Build the digest.** `python "<this skill>/scripts/scan.py" --digest --out "<scratchpad>/ai-coach-digest.md"`.
   It covers the time since the last review, or the last 30 days. `--days N` overrides that.
2. **Start with applied, parked and declined items.** The digest opens with "Re-check applied
   changes": every change applied at an earlier review, with the count of its watch pattern before
   and since. Give each a verdict: worked, no effect, or worse. Grade it by the outcome it targeted
   where that is measurable, otherwise by the watch count, and say which. No effect twice: propose
   the stronger fix (a memory becomes a hook or a skill instruction). Worse: propose the revert. A
   count only means something if the same kind of work happened in the window; say so when it
   didn't.
   Then the suggestions parked at earlier reviews: re-check each against the new window (still
   happening: keep it with fresh evidence; applied or resolved on its own: `--unpark N`). Items
   under "Declined" are not proposed again unless the user repeated the same rule or request since.
3. **Read the whole digest**, then open the feedback memories and the SKILL.md files that look
   related. The counts are heuristics. The correction detector matches phrasing like "no", "why
   did", "again", and most raw hits are noise ("I don't know"). Before claiming a pattern, read the
   prompts around it. Strong signals: a rule stated twice in one window (it isn't saved anywhere),
   and copy the user rewrote themselves (the "Long or pasted prompts" section).
4. **Map the system.** Before looking for items, note in the scratchpad: who uses it (the user, and
   any teammates from `team.local.md`), on which surface (Claude Code, claude.ai, desktop), and the
   current goals (project memories, CLAUDE.md files). Every part is judged against this map.
5. **Run the four parts** below, then the coach itself.
6. **Name the biggest gaps.** One to three gaps between what the system does and what the goals
   need; the big moves should close them. Then write the state of the system in three lines: what
   works, what doesn't, the biggest gap.
7. **Verify every item before it goes in the list.** Every proposal must be one the user can approve
   as it stands. For each candidate item:
   - Re-check the evidence over 30 days (`--days 30`), not only the window since the last review.
     "Not invoked" in a short window is not "unused".
   - Search every CLAUDE.md, settings file and skill for references to anything the item would
     archive, change or delete. A referenced skill or file stays, or the item says what else
     changes with it.
   - Check live state: which config dir actually loads a folder, whether a branch is merged,
     whether a worktree has uncommitted work, whether the hook or rule already exists.
   - Test a proposed threshold against the actual data: how often would it have fired?
   An item that fails a check is dropped or rewritten before the report, never shipped with a
   hedge. Each item says in a few words what it was verified against.

   **Then hand the whole list to a blind verifier subagent before the report.** The agent that
   wrote the proposals is not the one that grades them. Give it the digest path, the candidate list
   with each item's evidence, and read access. Do not give it the reasoning that produced the items,
   which part each came from, or any ranking: it sees claims, not a case. For each item it checks
   that the evidence cited exists and says what the item claims, that anything the item would
   change or delete is not referenced elsewhere, and that the live state is as described. It
   returns PASS, or FAIL with the one line that fails. Tell it not to propose new items, rank, or
   flag style: a reviewer asked for gaps will invent them. A FAIL is fixed or the item is dropped.
   Report the pass count to the user in one line.
8. **Report.** Open with the three state lines. Then the big moves, ranked, at most twelve items in
   all, **three per message**: show three, ask for one batch answer ("1 yes, 2 no, 3 later") and
   wait for it before the next three. Housekeeping is one item with one yes or no. Each item: the
   finding in one line, the evidence (counts, dates, one example), what it was verified against,
   the change and where it lands (which SKILL.md, hook, permission, memory), and the effort as
   Claude's own working time. Never a human-time guess. No item without evidence. After the last
   batch, the top bets (Part 4) in their own group.
9. **Apply only what the user approves.**
   - Skill edits: edit the newest copy the inventory names.
   - New skills: interview the user first, one question at a time, under four headings (what it
     starts from, what it does, what it produces, who checks it), then build.
   - Settings, hooks and permissions: show the change before saving.
   - Duplicate removal: show the exact paths first; delete only on a yes for that path.
   - An ask for someone else: write it out for the user to send. Never send it.
   For every applied item run `--applied "<item>" --watch "<regex>" --baseline "<H/P>"`: the watch
   pattern is what should get rarer if the change works (the user's correction phrasing), and the
   baseline comes from `--count "<regex>" --days 30` run before applying. An item with nothing to
   count gets no watch. Then reply with one status line per item: applied, parked or declined.
10. **Close the review.** `--decide <part>:<lens> <yes|no|park|corrected> "<item>"` for every item
   in the list, e.g. `setup:drift`, `time:daily`, `team:reach`, `frontier:release` (corrected = the
   user had to fix the proposal before deciding). `--label real=K noise=M` with a `--noise "<text>"`
   per noise hit for the correction-like prompts read in step 3. `--park "<item and its evidence>"`
   for items the user deferred; `--reject "<item>"` for items they declined; `--unpark N` for what
   was applied. Then run `python "<this skill>/scripts/scan.py" --mark-reviewed` and
   `python "<this skill>/scripts/docs_check.py" --accept`, even if nothing was applied. This resets
   the session-start nudge.

## Part 1: Your setup (inward)

**What keeps going wrong**
- **Corrections that belong in a skill.** Keep only corrections that would change future runs;
  drop one-off decisions. Map each to the skill that owns it. If no skill owns it, it's a memory
  item or a hint a new skill is needed.
- **Drift.** A rule already saved (memory, CLAUDE.md or skill) that got broken anyway. Report it as
  drift, not a new rule. Broken twice despite the memory: it needs a hook or a skill instruction,
  not another memory.
- **Taste.** The digest's "Draft vs. user rewrite" section pairs a draft with the user's own version
  that followed it. Name what they cut, kept and replaced. A change made twice or more becomes a
  proposed rule for the project's taste or style file, written as the rule plus why. One-off picks
  are not taste.

**What to automate**
- **Skills to build.** Tasks prompted by hand three or more times, in two or more sessions, with no
  skill invoked. Screen against the full inventory first: if an existing skill covers it, propose
  an addition to that skill, not a new one. For each new one: name, what it does, when it triggers,
  evidence (dates, two example prompts).
- **Friction.** Permission denials (propose a specific allow rule, or say why the block is right),
  steps done by hand, interrupts showing work going the wrong way.

**What's no longer true**
- **CLAUDE.md vs memory.** Flag a CLAUDE.md rule a memory note contradicts (quote both), a memory
  note made stale by a later decision or a passed date, and a rule written in both.
- **Learnings that stopped holding.** If a project keeps `intelligence/learnings.md`, check each
  learning's `stop-trusting-if:` line against what happened in the window, and propose retiring
  the ones whose condition is met.
- **Context drift.** Context files (positioning, personas, voice, product overview) that newer
  evidence contradicts. Also context the user typed or pasted in two or more sessions: it belongs
  in a context file.

**Housekeeping: one item, one yes or no**
- **Overlap.** The same skill in several places, old plugin-cache versions, two skills collecting
  the same kind of rules.
- **Setup health.** Leftover worktrees and branches, settings that name scripts that no longer
  exist, hooks that block often or error.
- **Dead paths and retired terms.** Paths that no longer exist, and banned terms (if a
  `product-marketing/messaging-framework.md` has a never-use list) still in skills or context files.
- **Dead weight.** Skills not invoked in the window (say "not invoked", never "unused"), memories
  that duplicate or contradict each other.

## Part 2: Your time (inward)

The skills that run the user's day, if they have any (a morning triage, meeting agendas, an
end-of-day wrap). Grade each: on how many workdays it ran, what the user still did by hand in the
same sessions, and the corrections in its runs. A skill that runs on a few days a month is a
finding: find out what made it not worth running before proposing a fix. Never act on the user's
calendar: list proposals; the user acts on them.

## Part 3: Your team (outward)

Skip this part if the user works alone. Otherwise, what the user learns only pays off once it
reaches the team. Who the teammates are, their surfaces and where their work leaves a footprint go
in `team.local.md` next to this file (kept out of any repo; see `team.local.example.md`). Teammates'
chats are not visible: infer only from footprints, and say "unmeasured" where there are none.
- **Reach.** Which version of the shared skills each teammate runs, and how updates get to them.
- **Use.** Skill footprints in their work. Never read a usage count as quality.
- **Outcome.** The review rounds and corrections the user left on a teammate's work, before and
  after a skill reached them. The same correction twice is a rule missing from the shared layer.
- **Promote.** Each correction or rule from the window that would change a teammate's output too
  but lives only in the user's setup: name where it should be shared.
- **Never add a step to a teammate's work.** No surveys, no check-ins. A question becomes a note
  for the user's next 1:1.

## Part 4: The frontier (outward)

Two bars. A **rule** changes something that exists: it needs a problem the digest shows in this
user's sessions, and it joins the ranked list. A **bet** is a capability the system doesn't have (a
skill, routine, agent, way of working): it needs no proof, goes to the bets backlog, and is judged
on whether it's worth a test of a week or less. A practice the user already declined stays declined.
Inputs:

(a) **Releases.** The digest's "Claude Code releases" line gives the installed version and the one
at the last review; if they differ, read the changelog
(https://github.com/anthropics/claude-code/blob/main/CHANGELOG.md) for the releases in between.

(b) **Docs.** `python "<this skill>/scripts/docs_check.py" --out "<scratchpad>/docs"` fetches the
watched Claude Code docs pages and writes a diff for each page that changed since the last review.
Read only the diffs. Skip test, build and CI advice unless the user codes.

(c) **Saved links (optional).** If the user keeps a folder of links and posts they saved (a "read
later" folder, a notes inbox), read each item since the last review and judge it with the two bars.
Show one line per item: what it says, the verdict (rule, bet, already done, or no) and why.

(d) **New capabilities.** Connectors and features the user already has that no skill uses yet.
Each is a bet unless the digest shows the problem it solves.

**The bets backlog.** Copy every bet into `<this skill>/bets.md` (merge duplicates: a repeat raises
its Signal score). Re-score the backlog each review on Leverage, Fit (current goals), Cost and
Signal, each 1-3. Show the top two after the ranked list, each with its first test. One unchanged
for eight weeks moves to Archived, never deleted. Log each shown bet with
`--decide bets <yes|no|park> "<bet>"`; a declined bet is not shown again.

## The coach itself

The digest's "Coach self-learning" section logs every decision the user made on a proposal and how
many correction-like hits were real. With 50+ decisions, a kind mostly declined or corrected gets a
stricter verification rule in this file; with 300+ labelled hits, propose a tighter CORRECTION
pattern in `scan.py`, tested with `--count`. Changes to this skill go in the same ranked list as
everything else and need the same yes.

## Automatic runs

A `SessionStart` hook runs `scan.py --check`, at most every six hours. A review is due once a week,
or sooner (no sooner than 3 days) when the user logged 30+ correction-like prompts, 15+ blocked
actions, or 10+ sessions. When it prints "AI COACH REVIEW DUE", run this skill in that session
without being asked: first if the user opened with a quick question or a greeting, otherwise right
after their task. Applying still needs their yes. The transcripts live on this machine, so the
review runs here, never as a cloud job.

## Report style

Plain language. Lead with the three state lines, then the biggest move; one line per item plus its
evidence. The user can ask for detail on any item.
