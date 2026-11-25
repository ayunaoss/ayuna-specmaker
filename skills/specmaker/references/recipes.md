# Recipes (read when the situation applies)

## Repair paths

| Situation | Path |
|---|---|
| A stakeholder asks for something different mid-change | [change-requests.md](change-requests.md): record, freeze, batch triage, then backlog, amend or a new change |
| The intent or design was wrong, and the change is past accredit | Record it as a request, decide `amend`, then `amend --cr ... --to ideate\|propose` → re-accredit (only changed sections are re-reviewed) |
| The implementation is wrong but the design is right | Stay in the sprint and fix the code; the verifier checks it again |
| A sprint needs a small design decision the LLD did not make | Record a deviation (sprint skill). If it changes a spec, an ADR or a contract, it is a change request |
| A typo or wording fix in a locked design | `amend --wording-only` (a human gate; refused if any requirement or scenario ID changes) |
| Code was edited by hand outside specmaker | Run the retro skill's drift check; fix the code, or open a change for the spec |
| Two open changes touch the same requirement | `set <id> depends_on <other>`; the dependent change archives second |

## Adopt: specs for an existing codebase

1. Run `init`, then fill in `project.md` from what the repository shows
   (stack, CI, test command). Ask about anything you cannot verify.
2. Pick one capability at a time, starting with the area about to change.
   Never spec the whole system in one go.
3. Run `new baseline-<capability> --track lite`, then
   `set baseline-<capability> docs_only true`.
4. Write ADDED requirements describing **current** behaviour, each citing the
   code that proves it (`<!-- code:src/auth/session.ts:42 -->`).
5. Write a short LLD with `File Boundary: none (documentation only)`.
6. Accredit with the quick preset; a human confirms the behaviour is real.
7. Go `phase <id> retro` (a docs-only change skips scrum and sprint), then
   archive. Tag existing tests with scenario IDs over time.
