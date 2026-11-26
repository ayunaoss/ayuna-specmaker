# Change Requests

Specs only help if they stay stable long enough to build against. Requests that
arrive mid-implementation and edit the design straight away turn the specs into
a record of whoever spoke last. Specmaker controls change requests in three
ways:

- **When** a request may change anything: intake, the sprint freeze, and
  batched triage.
- **How far** it reaches: a class decides where it re-enters the workflow.
- **What happens to work already built:** impact analysis, an optional rewind,
  and sprints that reopen on re-approval.

## 1. Intake: record, never edit

Whatever the source (stakeholder, user, reviewer, or something you noticed
yourself), a request that would change scope, behaviour, the design or the
plan of a running change is first **recorded**:

```bash
python3 $SM/scripts/specmaker.py cr add <id> --title "<short title>" --by "<who asked>" --reason "<their words>" [--blocker]
```

`--by` is **who asked**, in the user's words ("Product", "Security (Dana)").
If it's unclear, ask; never record a placeholder like "user". This creates
`requests/CR-NNN.md` from a template, with status **parked**.
Recording does not edit the HLD, LLD, specs, ADRs, contracts or backlog. Tell
the user it is parked and keep working on the current task.

Mark `--blocker` only when continuing would build something known to be wrong:

- a legal or security finding
- a spec that contradicts reality
- a dependency that disappeared

"Important" and "the boss wants it" are not blockers.

Small things are not change requests. Fixing a typo in a comment, or a local
implementation choice inside the file boundary, is a deviation or simply the
work (class 0, below).

## 2. Sprint freeze and batched triage

While a sprint is active (`project.md` → `Sprint freeze: on`, the default):

- Non-blocker requests can only be **rejected** or **deferred**. The script
  refuses to accept them into the backlog or design until the sprint boundary.
- **Blockers** are triaged at once (step 3), with the user, and may stop the
  sprint.

At the **sprint boundary** (after sign-off, before the next `sprint-start`),
triage every parked request **together**, in one sitting. Batching lets
related requests merge, lets conflicting ones be weighed against each other,
and costs one amendment and one re-review instead of one each. `status` lists
what is parked, and `next` points here.

## 3. Triage one request

For each request, fill its `requests/CR-NNN.md`:

1. **Goal fit:** which HLD goal does it serve?
2. **Two questions:**
   - Q1: does it change anything observable from outside (a spec scenario, a
     contract, an accepted ADR)?
   - Q2: is it needed to meet the current HLD goals?
3. **Class:** answer Q2 first. A request not needed for the current goals is
   class 3, whatever Q1 says.

| Class | Test | Outcome | Path |
|---|---|---|---|
| 0: Implementation | Q2 yes, Q1 no; stays within the file boundary | not a CR: do it in the sprint, or note a deviation | sprint |
| 1: Plan | scenarios unchanged; order, size or split of work changes | `backlog` | edit `backlog.md`, `check backlog` |
| 2: Design | Q1 yes and Q2 yes | `amend` | rewind if needed → `amend --to ideate\|propose` → re-accredit → re-plan → re-build |
| 3: New scope | Q2 no | `defer` | a new change (`new <id>`), with `depends_on` if it overlaps |

**Reject** is a valid outcome for any class: say why, in a sentence the
requester would accept.

4. **Impact:** run `impact <id> --reqs <REQ-IDs>` and paste or link the result.
   It follows each changed requirement to its scenarios, the stories that cover
   them (and their sprint's status), the files those stories touch, and the
   tests that name the scenarios. It also lists the signed-off sprints that
   will reopen and suggests a rewind point.
5. **Options and recommendation:**
   - **reject**
   - **defer**
   - **the cheapest acceptable way in:** where it re-enters (backlog, LLD or
     HLD), and what code, if any, must be discarded

Then ask the user for the decision. That is a **human gate**, like accreditation:

```bash
python3 $SM/scripts/specmaker.py cr decide <id> CR-003 [CR-004 ...] --outcome reject|defer|backlog|amend --reason "<why>"
```

In `signed` or `terminal` mode, give the user that command to run, as with
`accredit`. Several requests with the same outcome go in one command.

## 4. Applying a design change (class 2)

```text
cr decide ... --outcome amend
   -> impact                       (what is affected)
   -> rewind (optional)            (discard code that the change makes wrong)
   -> amend --cr CR-NNN[,..] --to ideate|propose
   -> ideate: update the HLD   (only when goals, scope or solution shape change)
   -> propose: update LLD, specs, ADRs, contracts (only what the request needs)
   -> accredit: goldfish re-review of the changed sections, then a human verdict
   -> scrum: re-plan the affected stories
   -> sprint: re-run reopened or rewound sprints first, then continue
```

**Choosing where to re-enter:**

- `--to ideate` when the request changes a goal, a non-goal, the success
  measures, or the solution's shape.
- `--to propose` for everything else: behaviour, interfaces, data or decisions
  inside the same shape.

**Rewinding code** discards implementation work. Everything under `specmaker/`
is kept, including the ledger, specs and request records. Choose the smallest
rewind that removes the wrong work:

| `--to` | Discards | Use when |
|---|---|---|
| `head` | uncommitted changes only | work in progress is now pointless |
| `sprint` | everything since the active or latest sprint started | the current sprint built on the old design |
| `sprint:N` | everything since sprint N started | earlier signed-off sprints are invalid too |
| `change` | everything since the first sprint | the design changes so much that a clean start is cheaper |

`rewind` is a human gate. Before discarding anything it saves:

- a backup branch `specmaker-backup/<id>/<timestamp>`
- a stash of the uncommitted work

The revert is recorded as a **new commit**; history is not rewritten. To undo
it, restore the code but not the specmaker state:
`git checkout <backup-branch> -- . ':(exclude)specmaker'`, plus
`git stash pop` if uncommitted work was stashed. The script prints the exact
commands. Rewound sprints get status `rewound`, and their tasks are unticked
in `backlog.md`.

**Not rewinding** is often right. Code that still satisfies the changed
scenarios can stay. Re-approval reopens every signed-off sprint whose stories
cover a changed requirement, and that sprint is re-run with fresh gates, a new
verifier round and a new sign-off. The script refuses old evidence.

**Amendment budget.** `project.md` → `Max amendments per change` (default 3 in
the template). Past it, `amend` needs `--over-budget "<reason>"`. Hitting the
budget usually means the HLD was wrong. Say so, and suggest closing the change
and starting again from ideate.

## 5. What the script enforces

| Rule | Enforced by |
|---|---|
| Non-blockers cannot be accepted while a sprint is active | `cr decide`, `amend` |
| No sprint starts while any request is still parked: parked requests are triaged together at the boundary | `sprint-start` |
| Re-approval after an amendment needs new review reports for the required lenses | `accredit` |
| Meaning-neutral wording fixes use `amend --wording-only` (a human gate): no re-review, no reopened sprints, and refused if any requirement or scenario ID changes | `amend`, `accredit` |
| After planning, an amendment must name the requests it applies | `amend` |
| A request decided as `amend` must be applied before the next sprint starts | `sprint-start` |
| Decisions and rewinds need a human (a signature in signed mode) | `cr decide`, `rewind` |
| Reopened sprints need fresh gates, a new verifier round and a new sign-off | `signoff` |
| No parked or unapplied request may remain at retro or archive | `phase <id> retro`, `archive` |
| Amendments beyond the budget need a person's approval and a reason | `amend --over-budget` |

## 6. Talking to requesters

- Acknowledge the request and say what happens next: "Recorded as CR-004.
  Sprint 2 is frozen, so it will be triaged with the others on Friday."
- Never promise an outcome before the human decision.
- Report decisions with their reason, and point deferred requests to the change
  that will carry them.
