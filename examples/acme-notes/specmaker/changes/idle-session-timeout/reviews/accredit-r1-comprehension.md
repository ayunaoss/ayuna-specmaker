# Comprehension review - round 1
- Target: hld.md, lld.md, specs/identity/session/spec.md, adrs/0001, adrs/0002
- Mode: REVIEW | Model: (reviewer model) | Isolation: full
- Verdict: PASS-WITH-NOTES

**What this proposes**
Sessions in Acme Notes will expire in two ways: after 30 minutes without a
request, and 12 hours after sign-in no matter what. The session store will keep
two timestamps per session and check them on each validation, deleting expired
sessions and raising an error whose reason code tells the client which limit
was hit. The current time is passed in as a function, so tests can control it.

**How the existing system works, per these documents**
A user signs in and gets a random token stored in an in-memory dictionary. Each
request looks up the token. The token is valid until the user signs out. An
HTTP layer turns the store's exception into a 401 response, using the
exception's reason.

## Findings
### G1 [Major] Order of the two expiry checks is only in the LLD
- Evidence: doc:lld.md#5
- Problem: when both limits have passed, the client sees `session_lifetime_exceeded`.
  That is observable behaviour, but no spec scenario states it, so a test could
  miss a regression.
- Suggested fix: add a scenario, or state in SESS-03 that it takes precedence.

### G2 [Nit] "shared laptop" finding is referenced but not linked
- Evidence: doc:hld.md#1
- Problem: a reader cannot find the October security review.
- Suggested fix: link the finding or name its ticket.

## Questions for the owner
- Q1: Does the HTTP layer already accept new reason codes without changes? (context: lld.md#1)
