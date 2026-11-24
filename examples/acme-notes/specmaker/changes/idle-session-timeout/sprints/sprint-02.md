# Sprint 2: idle-session-timeout

> **TL;DR** Absolute 12-hour lifetime works (SESS-03.1). The verifier's nit from
> sprint 1 was not picked up and is carried forward. Gates green.

## Sprint Goal

No session outlives 12 hours.

## Committed Stories

| Story | Points | Covers | Status |
|---|---|---|---|
| S2 | 2 | SESS-03.1 | done |

## Progress

- 2026-11-12 S2: test for SESS-03.1 written (24 requests at 29-minute intervals, then one more); failed as expected; lifetime check added before the idle check; 5/5 green.

## Deviations

None.

## Verification

- Gates: [reviews/sprint-02-gates.json](../reviews/sprint-02-gates.json) - PASS
- Trace: [reviews/sprint-02-trace.md](../reviews/sprint-02-trace.md) - 4/4 change scenarios with tests
- Verifier: [reviews/sprint-02-verification.md](../reviews/sprint-02-verification.md) - PASS-WITH-NOTES
- Manually verified scenarios: none
- Known issues carried forward: SESS-02.3 AND step not asserted (sprint-01 verifier G1); logged for retro.

## Demo

```bash
PYTHONPATH=src python3 -m unittest -v tests.test_session
```

`test_absolute_lifetime_ends_active_session__SESS_03_1` keeps a session busy for just over 12 hours and shows `session_lifetime_exceeded`.

## Sign-off

- Signed off by: Alex Chen
- Date: 2026-11-12
- Accepted gaps: none
