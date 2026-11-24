# ADR-0001: Keep server-side session records with timestamps

- Status: Accepted
- Date: 2026-11-05
- Deciders: Alex Chen
- Change: `idle-session-timeout`

## Context

Expiry needs to know when a session was created and when it was last used.
Today the token is an opaque key into an in-memory store.

## Decision Drivers

1. No new runtime dependencies (project charter).
2. Sign-out must take effect immediately.
3. Simple to test.

## Options Considered

### Option 1: Timestamps in the existing server-side record
- Pros: no new dependency; sign-out already works; trivial to test with a fake clock.
- Cons: state is lost on restart (already accepted).
- Cost / effort: about half a day.

### Option 2: Signed, self-expiring tokens (JWT-style)
- Pros: stateless validation; survives restarts.
- Cons: needs a signing library or home-grown crypto; immediate sign-out needs a deny-list, which brings the state back.
- Cost / effort: 2 to 3 days, plus key management.

## Decision

Option 1. It meets all three drivers. Option 2 fails driver 1 and only
partially meets driver 2.

## Consequences

- Validation remains a dictionary lookup plus two comparisons.
- Running several processes later would need a shared store. That would be a
  new ADR.
