# Backlog: idle-session-timeout

> **TL;DR** 1 epic, 2 features, 3 stories, 8 points, 2 sprints. The riskiest
> story is S1: it changes how every request is validated.

- Sprint length: 2 days
- Capacity per sprint: 5 points (a guess; no velocity history yet)
- Team: coding agent builds; Alex Chen reviews and signs off

## E1 - Sessions end when they should

Serves HLD goals G1, G2 and G3.

### F1 - Idle expiry

#### S3 - Enabler: injectable UTC clock for the session store
- **Covers**: none
- **Points**: 1
- **Priority**: Must
- **Type**: enabler
- [x] T3.1 Add `Clock` type and `utc_now()` - files: src/notes/clock.py
- [x] T3.2 Accept `clock` in `SessionStore.__init__`, default `utc_now`; add `FakeClock` to tests - files: src/notes/session.py, tests/test_session.py

#### S1 - As a team member, I want idle sessions to end, so that a token left on a shared laptop stops working
- **Covers**: SESS-02.1, SESS-02.2, SESS-02.3
- **Points**: 5
- **Priority**: Must
- **Depends**: S3
- **Type**: story
- [x] T1.1 Write failing tests for SESS-02.1, SESS-02.2, SESS-02.3 - files: tests/test_session.py
- [x] T1.2 Add `created_at`/`last_seen` to `Session`; implement idle check, refresh and `session_expired` reason - files: src/notes/session.py

### F2 - Absolute lifetime

#### S2 - As a security officer, I want every session to end 12 hours after sign-in, so that no token lives longer than a work day
- **Covers**: SESS-03.1
- **Points**: 2
- **Priority**: Must
- **Depends**: S1
- **Type**: story
- [x] T2.1 Write failing test for SESS-03.1 - files: tests/test_session.py
- [x] T2.2 Implement lifetime check before the idle check, with reason `session_lifetime_exceeded` - files: src/notes/session.py

## Sprint Plan

| Sprint | Goal | Stories | Points |
|---|---|---|---|
| 1 | Idle sessions expire; active ones keep working | S3, S1 | 6 |
| 2 | No session outlives 12 hours | S2 | 2 |
