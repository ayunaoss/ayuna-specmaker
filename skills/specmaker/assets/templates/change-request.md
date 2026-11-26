# {cr}: {title}

> **TL;DR** <!-- One line: what is asked, the class (0-3), and the recommended outcome. Fill in at triage. -->

- Requested by: {by}
- Received: {received} (phase: {phase})
- Blocker: {blocker}
- Status: see `specmaker.py cr list` (the script owns the status)

## Request

<!-- The request in the requester's own words. Quote; do not improve it. -->
{reason}

## Goal Fit

<!-- Which HLD goal (G1...) does this serve? If none, it is new scope (class 3) and belongs in a new change. -->

## Classification

<!-- Answer both questions, then pick the class.
Q1: Does it change anything observable from outside (a spec scenario, a contract, an accepted ADR)?
Q2: Is it needed to meet the current HLD goals?
- Class 3 New scope: Q2 no -> defer to a new change (check this first)
- Class 0 Implementation: Q2 yes, Q1 no, stays within the file boundary -> fix in the sprint
- Class 1 Plan: scenarios unchanged; order/size/split of work changes -> backlog
- Class 2 Design: Q1 yes and Q2 yes -> amend (HLD if goals/scope/shape change, else LLD)
Blocker = continuing the current sprint would build something known to be wrong. -->
- Q1 observable change:
- Q2 needed for current goals:
- Class:

## Impact

<!-- Paste or link the output of `specmaker.py impact <id> --reqs <IDs>`: requirements, scenarios,
stories, files, tests, and signed-off sprints that would reopen. Add effort in points. -->

## Options

<!-- At least: reject, defer, and the cheapest way to accept. For accept options, say where the change
re-enters (backlog / LLD / HLD) and whether code must be rewound (head / sprint / sprint:N / change). -->

## Recommendation

<!-- One option with the reason. The human decides with `specmaker.py cr decide`. -->

## Decision

<!-- Filled in after the decision: outcome, reason, by whom, ledger entry (L-NNN). -->
