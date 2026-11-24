# Project Charter

> **TL;DR** <!-- One paragraph: what this system is, who uses it, and the one or two constraints that shape every design. -->

This file is read by every specmaker phase. Keep it short and true. Phases treat
it as settled context: a design that contradicts it must say so and record an
ADR, not silently diverge.

## Context

<!-- What the system does, for whom, and where it runs. Link the architecture overview if one exists. -->

## Stack

<!-- Languages, frameworks, data stores, hosting, CI. One line each. Decisions listed here need no new ADR; changing them does. -->
- Language/runtime:
- Frameworks:
- Data:
- Hosting/deployment:
- CI/CD:

## Conventions

<!-- Code style, layout, naming, error handling, logging, branching/commit rules. Link existing docs instead of copying them. -->

## Rules by Phase

<!-- Extra rules each phase must follow. Delete lines you do not need. -->
- ideate:
- propose:
- accredit:
- scrum:
- sprint:
- retro:

## Spec Areas

<!-- Requirement ID prefixes in use, one per capability area, so IDs stay unique. Example: - AUTH: identity/user-auth -->

## Quality Gates

<!-- Commands `specmaker.py gates` runs before sprint sign-off. Format: - name: `command`. All must exit 0. -->
- test: `echo "replace with your test command" && exit 1`

## Definition of Ready (story)

- Covers at least one scenario ID, or is typed enabler/spike/chore.
- Every task names its files and leaves no design decision to the implementer.
- Dependencies are planned in the same or an earlier sprint.

## Definition of Done (story)

- All tasks ticked; each covered scenario has a test that names its ID.
- Quality gates pass on the committed code.
- No change outside the sprint file boundary, unless it is recorded as a deviation.

## Review Policy

<!-- How much goldfish review each change gets. Presets: quick (2 reviewers), standard (5), deep (7). -->
- Default preset: standard
- Lite track preset: quick
- Max re-review rounds: 2
- Reviewer model: <!-- optional; a different model from the drafting model catches different issues -->
- Reviewer agent: <!-- optional; name of a harness subagent to use for goldfish (default: the general-purpose subagent) -->

## Autonomy

<!-- Mode - guided: the agent asks at every phase gate. autopilot: the agent advances on its own
     through gates that are not human gates.
     Human gates (accreditation verdict, sprint sign-off) - terminal: the script only records them when a
     person types their name in an interactive terminal, so an agent cannot approve on its own (recommended).
     chat: the agent records the decision after you state it in chat (faster; relies on the model obeying). -->
- Mode: guided
- Human gates: terminal

## Approvers

<!-- People who may give an accreditation verdict or a sprint sign-off. -->
-
