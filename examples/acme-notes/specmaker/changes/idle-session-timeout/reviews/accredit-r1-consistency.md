# Consistency review - round 1
- Target: hld.md, lld.md, specs/identity/session/spec.md, adrs/*; living specs/identity/session
- Mode: REVIEW | Model: (reviewer model) | Isolation: full
- Verdict: PASS-WITH-NOTES

## Findings
### G1 [Major] Precedence of lifetime over idle expiry is behaviour hiding in the LLD
- Evidence: doc:lld.md#5 vs absent:specs/identity/session/spec.md scenario for both limits passed
- Problem: same as the comprehension finding. The reason code a client receives
  is part of the contract (HLD G3).
- Suggested fix: state precedence in SESS-03 or add a scenario.

### G2 [Nit] HLD Success Measures mention a "weekly security probe" no requirement covers
- Evidence: doc:hld.md#5
- Problem: it is an operational check, not system behaviour; fine to keep out of specs.
- Suggested fix: none needed; note it in the retro.

No contradictions found between the LLD, the specs and the ADRs. The MODIFIED
SESS-02 keeps the living scenario SESS-02.2 unchanged.
