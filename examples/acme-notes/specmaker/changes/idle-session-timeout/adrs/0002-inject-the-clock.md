# ADR-0002: Inject the clock into SessionStore

- Status: Accepted
- Date: 2026-11-05
- Deciders: Alex Chen
- Change: `idle-session-timeout`

## Context

Expiry logic depends on the current time. Tests must cover 30-minute and
12-hour boundaries without sleeping.

## Decision Drivers

1. Deterministic, fast tests.
2. A single source of time, in UTC.

## Options Considered

### Option 1: Constructor parameter `clock: Callable[[], datetime]`
- Pros: explicit; no test-only patching; one obvious place for time.
- Cons: one more constructor argument (it has a default).

### Option 2: Patch `datetime.now` in tests (unittest.mock)
- Pros: no production signature change.
- Cons: brittle (patch targets depend on import style); easy to forget; breaks the charter rule against calling `datetime.now()` inside logic.

## Decision

Option 1, with the default `utc_now()` in the new `src/notes/clock.py`.

## Consequences

- Future time-based features reuse `Clock`.
- Code reviews reject direct `datetime.now()` calls in logic.
