# Retro: idle-session-timeout

> **TL;DR** Shipped both limits in two sprints, as planned (8/8 points). The
> lesson that matters: behaviour a client can observe belongs in a spec, even
> when it seems minor. We declined that finding at accreditation and then
> carried a related test gap through two sprints.

## Outcome

G1 to G3 are delivered: idle expiry (SESS-02), absolute lifetime (SESS-03),
and distinct reason codes. The success measures are checked by the weekly
security probe (13-hour-old token replay) and by the `signed-out` support tag
from 2026-11-17.

## Metrics

| Measure | Value |
|---|---|
| Sprints planned / run | 2 / 2 |
| Points planned / done | 8 / 8 |
| Review rounds (accredit) | 1 |
| Findings: Blocker / Major / Nit | 0 / 2 (one issue) / 3 |
| Amendments (re-accreditations) | 0 |
| Deviations recorded | 1 (test helper) |
| Gate failures before sign-off | 0 |
| Verifier FAIL rounds | 0 |
| Accepted test gaps | 0 (one weak assertion carried forward, L-006) |

## What Helped

- The fake clock (ADR-0002) made the 12-hour test run in milliseconds.
- Two reviewers independently raised the precedence question, which made the
  trade-off explicit (L-003) instead of accidental.

## What Hurt

- The quick preset left no zoom-out lens, so no one asked whether 12 hours fits
  night-shift users. Support may surface it.
- The sprint 1 verifier nit was not turned into a task, so it reappeared as a
  Major in sprint 2.

## Lessons and Actions

| Lesson | Action | Applied to |
|---|---|---|
| Error codes clients can see are contract, not LLD detail | Add rule "propose: every client-visible error code appears in a spec scenario" | project.md (Rules by Phase) |
| Verifier notes evaporate between sprints | Add rule "sprint: each verifier finding becomes a task or a ledger decision before sign-off" | project.md (Rules by Phase) |
| Security ticket was not linked | Reference SEC-114 in the HLD of the next session change | team habit |

## Spec Merge

Output of `specmaker.py archive idle-session-timeout --dry-run`:

```text
modify  [SESS-02] in identity/session
add     [SESS-03] -> identity/session
adr     adrs/0001-server-side-session-records.md -> adrs/0001-server-side-session-records.md
adr     adrs/0002-inject-the-clock.md -> adrs/0002-inject-the-clock.md
```
