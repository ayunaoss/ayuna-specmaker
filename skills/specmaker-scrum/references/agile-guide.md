# Agile Guide for the Scrum Phase

## Hierarchy

| Level | Size | Test of a good one |
|---|---|---|
| Epic | Weeks to months | States an outcome someone cares about, not a component name |
| Feature | One to three sprints | A coherent slice of behaviour you could switch on behind one flag |
| Story | One to five days (1 to 8 points) | INVEST, below |
| Task | A few hours | One clear action on named files; done or not done |

## INVEST (stories)

- **Independent:** can be built and released without waiting for another
  unfinished story, except through `Depends`.
- **Negotiable:** says what and why; the design already settled how.
- **Valuable:** a user or client can observe the result. Enablers are the
  exception, and say which stories they enable.
- **Estimable:** the team can size it. If it can't, write a spike first.
- **Small:** 8 points or fewer.
- **Testable:** its `Covers` scenarios are its acceptance tests.

## Splitting a story that is too large

Try these in order:

1. **By scenario:** happy path first, then the error and edge scenarios.
2. **By data variation:** one type, format or locale first.
3. **By operation:** create, then read, then update and delete.
4. **By interface:** API first, then the UI on top.
5. **By rule:** the simple business rule first, then the complex ones.
6. **Spike, then build:** when the uncertainty is technical.

Never split into horizontal layers ("the database story", "the API story"),
except for enablers. A layer has no observable behaviour, so it cannot cover a
scenario.

## Estimation

- Points measure relative size: effort, complexity and uncertainty together.
  They are not hours.
- Anchor on a known small story (1 or 2 points) and compare.
- With an agent doing the work, points still matter. They size review effort
  and risk, and drive sprint scope, so the human sign-off stays manageable.

## Sprint planning

- One sprint is one LLD Implementation Phase, or a slice of one. A sprint must
  end with the system building and its quality gates passing.
- Give each sprint a goal that can be demonstrated: "A user can sign in with
  SSO and see their dashboard", not "Auth work".
- Put risky or uncertain stories early, so problems surface while there is
  time to adjust.
- Fill to about 80% of capacity.

## Priority (MoSCoW)

- **Must:** the change fails its goals without it.
- **Should:** important, with a workaround available.
- **Could:** nice to have, and dropped first.
- **Won't:** explicitly not this time. Kept in the file so the decision is
  visible.

## Definition of Ready and Definition of Done

Use the ones in `project.md`. The script checks the mechanical parts: coverage,
points, files and dependencies. You check the rest.
