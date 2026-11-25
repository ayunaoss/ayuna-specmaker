# Walkthrough: idle session timeout, from idea to archive

This follows one real change through all six phases. Every file mentioned
exists in [`examples/acme-notes`](../examples/acme-notes). Open them side by
side as you read. The conversation excerpts are shortened but faithful to how
the skills behave.

**The setup.** Acme Notes is a small Python service. Its sessions never expire.
A security review found five-week-old tokens on a shared laptop that still
worked. Alex, the tech lead, opens OpenCode in the repository, where specmaker
is installed under `.agents/skills/`.

---

## Day 1: triage and ideate

> **Alex:** @specmaker Session tokens never expire. Security found five-week-old tokens on a
> shared laptop that still work. I want sessions to time out.
>
> **Agent:** This changes how every request is authorised and has security sign-off
> implications, so I recommend the **full track** (all six phases) over lite. Shall I start
> change `idle-session-timeout`?
>
> **Alex:** Yes.

The agent runs `specmaker.py new idle-session-timeout`, loads
`specmaker-ideate`, and starts asking questions, **one at a time**:

> **Agent:** What does "time out" mean to security: after inactivity, after a fixed period, or
> both? A fixed period alone would still leave a stolen token usable for that whole period.
>
> **Alex:** After inactivity. 30 minutes, same as the laptop lock.
>
> **Agent:** An idle limit alone has a gap: a script replaying the token every 29 minutes keeps
> it alive forever. Do you also want an absolute lifetime? One working day (12 hours) is common.
>
> **Alex:** Good point. Yes, 12 hours. Dana from security agrees with both.

Each firm decision goes into the append-only ledger
([`ledger.md`](../examples/acme-notes/specmaker/changes/idle-session-timeout/ledger.md),
L-001 and L-002). The agent challenges the obvious alternatives: self-expiring
signed tokens would break the no-dependency rule in
[`project.md`](../examples/acme-notes/specmaker/project.md), and a proxy timeout
works on connections, not sessions. Those rejections become HLD §8,
"Alternatives Weighed".

When nothing important is left open, the agent writes
[`hld.md`](../examples/acme-notes/specmaker/changes/idle-session-timeout/hld.md).
It has:

- a TL;DR with the one decision to make
- three goals, three non-goals and measurable success criteria
- a context diagram
- the risks

`check hld` passes. Alex agrees, and the agent runs
`phase idle-session-timeout propose`.

## Day 2: propose

> **Alex:** @specmaker-propose
>
> **Agent:** Section plan: modify `SESS-02 Session validity` (it currently says "until sign-out")
> and add `SESS-03 Absolute session lifetime`, both in `identity/session`. Two decisions need
> ADRs: where expiry state lives, and how code gets the current time. No contracts: the API
> shape is unchanged. Agree?

The decisions come first, so the LLD can rest on them.
[ADR-0001](../examples/acme-notes/specmaker/changes/idle-session-timeout/adrs/0001-server-side-session-records.md)
compares server-side timestamps with signed tokens against three named drivers.
[ADR-0002](../examples/acme-notes/specmaker/changes/idle-session-timeout/adrs/0002-inject-the-clock.md)
chooses an injected clock over patching `datetime.now`.

The [LLD](../examples/acme-notes/specmaker/changes/idle-session-timeout/lld.md)
is written in five groups, with Alex's go-ahead after each. The details that
matter most to the implementer are exact:

- the order of the checks (lifetime first)
- inclusive bounds (exactly 30 minutes means expired)
- three reason codes
- two Implementation Phases
- a File Boundary of three paths

Then the [delta spec](../examples/acme-notes/specmaker/changes/idle-session-timeout/specs/identity/session/spec.md):
SESS-02 is rewritten in full under MODIFIED, keeping the sign-out scenario
SESS-02.2 and adding SESS-02.3. SESS-03 is ADDED. Both are in present tense,
because this text becomes the living spec word for word.

`check design` passes, and the agent runs `phase idle-session-timeout accredit`.

## Day 3: accredit

> **Agent:** Review preset: your default is *standard* (5 reviewers). This change is about 60
> lines in one module, so I suggest *quick + comprehension*: 3 reviewers. Go?
>
> **Alex:** Go.

The agent first spawns an isolation probe to confirm that the subagents cannot
see the conversation. Then it spawns three goldfish in parallel. Each gets only
file paths: its persona, the design files, the ledger and the charter. The
comprehension reviewer does not even get those last two.

- [Comprehension](../examples/acme-notes/specmaker/changes/idle-session-timeout/reviews/accredit-r1-comprehension.md)
  paraphrases the design back. The paraphrase matches Alex's intent. It raises a
  Major: what a client sees when both limits pass is only stated in the LLD.
- [Consistency](../examples/acme-notes/specmaker/changes/idle-session-timeout/reviews/accredit-r1-consistency.md)
  independently raises the same Major.
- [Readiness](../examples/acme-notes/specmaker/changes/idle-session-timeout/reviews/accredit-r1-readiness.md)
  finds no open decisions.

> **Agent:** One Major, raised by two reviewers: the precedence of `session_lifetime_exceeded`
> over `session_expired` is client-observable but only in the LLD. I recommend FIX: add a
> scenario. Your call: FIX, CONTEST, DECLINE or ESCALATE?
>
> **Alex:** Decline. Clients do the same thing for both codes.

The decline goes into the ledger (L-003), so a later round would not raise it
again. The agent writes
[`accreditation.md`](../examples/acme-notes/specmaker/changes/idle-session-timeout/accreditation.md),
with counts, residual risks and a recommended verdict, then asks the question
that only a human can answer:

> **Agent:** Do you approve this design? Reply approved, conditional (with conditions), or
> rejected, and the name to record as approver.
>
> **Alex:** approved, Alex Chen
>
> **Agent:** This project uses `terminal` human gates, so please record it yourself:
> `python3 …/specmaker.py accredit idle-session-timeout --verdict approved`

Alex runs that in their own terminal and types their name. Only then does the
script record the verdict, as `via terminal`, and hash the five design files.
(The example uses `terminal` gates so it runs without anyone's SSH key. New
projects default to `signed`: Alex would add `--by alex@example.com` and touch
a security key, and the verdict would be an SSH-signed statement that later
steps and CI verify. See HOW-TO §4.4.) From now on, any
edit to the design files shows up as `LOCK BROKEN` until someone runs `amend`
on purpose.

## Day 3, later: scrum

> **Alex:** @specmaker-scrum two-day sprints, about 5 points each.

The agent builds the
[backlog](../examples/acme-notes/specmaker/changes/idle-session-timeout/backlog.md):

| Story | Covers | Points | Depends |
|---|---|---|---|
| S3: enabler, injectable clock | none (enabler) | 1 | none |
| S1: idle sessions end | SESS-02.1, SESS-02.2, SESS-02.3 | 5 | S3 |
| S2: 12-hour limit | SESS-03.1 | 2 | S1 |

Each story's first task writes the failing tests, and every task names its
files. The Sprint Plan follows the LLD's two phases. `check backlog` confirms
that every scenario is covered, there are no cycles, and no dependency is
planned in a later sprint.

## Days 4 and 5: two sprints

> **Alex:** @specmaker-sprint start sprint 1

`sprint-start` records the git base commit. For S3 and then S1, the agent:

1. writes tests named `test_..._SESS_02_3` with `covers: SESS-02.3` docstrings
2. watches them fail
3. implements [`session.py`](../examples/acme-notes/src/notes/session.py)
   exactly as the LLD says
4. ticks the tasks and logs progress in
   [`sprint-01.md`](../examples/acme-notes/specmaker/changes/idle-session-timeout/sprints/sprint-01.md)

One small, local choice (a test helper's signature) is noted as a resolved
deviation.

Evidence, not claims:

- `gates idle-session-timeout 1` runs the two Quality Gates from `project.md`
  and stores the result:
  [`sprint-01-gates.json`](../examples/acme-notes/specmaker/changes/idle-session-timeout/reviews/sprint-01-gates.json).
- `trace` maps each scenario to its test:
  [`sprint-01-trace.md`](../examples/acme-notes/specmaker/changes/idle-session-timeout/reviews/sprint-01-trace.md).
- A fresh verifier reads the specs, the diff and the tests:
  [`sprint-01-verification.md`](../examples/acme-notes/specmaker/changes/idle-session-timeout/reviews/sprint-01-verification.md).
  It passes, with one Nit: the "AND the token is rejected from then on" step of
  SESS-02.3 isn't asserted.

> **Agent:** Sprint 1: gates PASS, 3/3 scenarios traced to tests, verifier PASS with one Nit.
> Demo: `PYTHONPATH=src python3 -m unittest -v tests.test_session`. Do you sign off sprint 1?
>
> **Alex:** yes, Alex Chen

Alex runs the `signoff` command the agent prints, in the same way as the
verdict. Sprint 2 adds the 12-hour limit in the same way. The verifier raises the Nit
from sprint 1 again, now as a Major, because nobody turned it into a task.
Alex accepts PASS-WITH-NOTES and logs a follow-up (L-006). That slip
becomes a retro lesson.

## Day 6: retro and archive

> **Alex:** @specmaker-retro

The agent collects the numbers (8/8 points, 1 review round, 0 gate failures)
and asks what helped and what hurt. Two lessons become new rules in
`project.md`, after Alex agrees:

- "Every client-visible error code appears in a spec scenario."
- "Each verifier finding becomes a task or a ledger decision before sign-off."

See [`retro.md`](../examples/acme-notes/specmaker/changes/idle-session-timeout/retro.md).

The example stops here, so you can run the last step yourself:

```bash
cd examples/acme-notes
python3 ../../skills/specmaker/scripts/specmaker.py archive idle-session-timeout --dry-run
# modify  [SESS-02] in identity/session
# add     [SESS-03] -> identity/session
# adr     adrs/0001-server-side-session-records.md -> adrs/0001-server-side-session-records.md
# adr     adrs/0002-inject-the-clock.md -> adrs/0002-inject-the-clock.md
```

Running it for real merges by requirement ID and re-reads the living spec to
verify the result. It promotes both ADRs into `specmaker/adrs/` and moves the
change to `specmaker/archive/`. The living spec
[`specs/identity/session/spec.md`](../examples/acme-notes/specmaker/specs/identity/session/spec.md)
then says, in plain present tense, how sessions behave today. The next change
to sessions starts from there.

## What to take away

- **The conversation shapes the design; the files remember it.** Any new
  session can resume from `status` and the ledger.
- **Fresh eyes review; a human decides.** Reviewers find gaps the author can't
  see. The ledger stops them from re-raising settled points. Only a named human
  can approve or sign off.
- **Evidence over claims.** The gates run and are recorded against a commit.
  Tests are found by scenario ID, and changed files are checked against the
  plan.
- **Specs accumulate.** Each change merges its delta into living specs, so the
  source of truth grows with the system instead of being thrown away with the
  change.
