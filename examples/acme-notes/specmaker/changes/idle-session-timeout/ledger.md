# Ledger: idle-session-timeout

Append-only. Written by `specmaker.py ledger`. Do not edit entries; add a new one to supersede.

- **L-001** `DECISION` 2026-11-03 [ideate]: Idle timeout is 30 minutes, matching the laptop screen-lock policy; security (Dana) confirmed. Absolute lifetime 12 hours.
- **L-002** `DECISION` 2026-11-03 [ideate]: Keep server-side session records; self-expiring signed tokens rejected (dependency rule, sign-out still needs state).
- **L-003** `DECLINED` 2026-11-06 [accredit] (re: accredit-r1-comprehension#G1, accredit-r1-consistency#G1): Precedence (lifetime before idle) stays an LLD detail for now: both reasons trigger the same client action (sign in again). Revisit if a client ever branches on the code.
- **L-004** `ANSWER` 2026-11-06 [accredit] (re: accredit-r1-comprehension#Q1): Yes: the HTTP layer forwards SessionExpired.reason verbatim into the 401 body (src/notes/http.py in the main product; not part of this example).
- **L-005** `DECISION` 2026-11-06 [accredit] (re: accredit-r1-comprehension#G2): Nit fixed in wording only; ticket reference SEC-114 noted in the retro.
- **L-006** `NOTE` 2026-11-12 [sprint] (re: sprint-02-verification#G1): Owner accepts PASS-WITH-NOTES; follow-up test for the SESS-02.3 AND step goes to the next change touching sessions.
