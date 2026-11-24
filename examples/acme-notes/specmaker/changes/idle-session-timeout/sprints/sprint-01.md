# Sprint 1: idle-session-timeout

> **TL;DR** Idle expiry works and is proven by tests for SESS-02.1 to 02.3.
> One cosmetic deviation (a test helper). Gates green.

## Sprint Goal

Idle sessions expire; active ones keep working.

## Committed Stories

| Story | Points | Covers | Status |
|---|---|---|---|
| S3 | 1 | - (enabler) | done |
| S1 | 5 | SESS-02.1, SESS-02.2, SESS-02.3 | done |

## Progress

- 2026-11-10 S3: added src/notes/clock.py, clock parameter, FakeClock; existing tests green.
- 2026-11-10 S1: tests for SESS-02.1..02.3 written and failing (no timestamps); implemented; 4/4 green.

## Deviations

- [x] `FakeClock.advance(**kw)` takes timedelta keywords instead of minutes only - local test-helper choice, no design impact.

## Verification

- Gates: [reviews/sprint-01-gates.json](../reviews/sprint-01-gates.json) - PASS
- Trace: [reviews/sprint-01-trace.md](../reviews/sprint-01-trace.md) - 3/3 sprint scenarios with tests
- Verifier: [reviews/sprint-01-verification.md](../reviews/sprint-01-verification.md) - PASS
- Manually verified scenarios: none
- Known issues carried forward: none

## Demo

```bash
PYTHONPATH=src python3 -m unittest -v tests.test_session
```

Then look at `test_idle_session_expires__SESS_02_3`: a session idle for exactly 30 minutes is rejected with `session_expired`.

## Sign-off

- Signed off by: Alex Chen
- Date: 2026-11-10
- Accepted gaps: none
