# Spec Format

Specs describe **observable behaviour**: what users or other systems can rely
on. They are contracts, not plans. Leave class names, libraries and step-by-step
implementation to the LLD and the backlog.

Quick test: if the implementation could change without anyone outside noticing,
it does not belong in the spec.

## Living specs (`specmaker/specs/<capability>/spec.md`)

The source of truth for how the system behaves today. Only `specmaker.py
archive` writes these, by merging the delta specs of a finished change.

```markdown
# identity/user-auth

## Purpose

Lets people prove who they are and keeps their session valid while they work.

## Requirements

### Requirement: [AUTH-01] Session expiry
The system SHALL end a session 30 minutes after the last authenticated request.

#### Scenario: [AUTH-01.1] Idle session expires
- **GIVEN** a user whose last request was 31 minutes ago
- **WHEN** they make a request
- **THEN** the request is rejected with 401 and the reason `session_expired`
```

- A capability path is one or more kebab-case segments (`billing`,
  `identity/user-auth`). Name it after a lasting behaviour, not after this
  change's work.
- Pick one ID prefix per capability area and list it in `project.md` under
  "Spec Areas".

## Delta specs (`changes/<id>/specs/<capability>/spec.md`)

A change describes how it alters the living specs. Use these sections:

| Section | Meaning | Rules |
|---|---|---|
| `## Purpose` | Purpose of a **new** capability | Required for a new capability; omit it for an existing one |
| `## ADDED Requirements` | New behaviour | The ID must not exist yet |
| `## MODIFIED Requirements` | Changed behaviour, including a rename | Same ID. Write the **whole** new block, with every scenario that should remain |
| `## REMOVED Requirements` | Behaviour that goes away | Keep the header and add `**Reason**:` and `**Migration**:` lines. No scenarios are needed |

There is no RENAMED section: a stable ID makes a rename an ordinary MODIFIED.

## Writing requirements

- Each requirement states **one** behaviour, using SHALL or MUST. Keep the
  statement short. Put examples and edge cases in scenarios.
- Each requirement has at least one scenario. Each scenario has a
  `**WHEN**` (or `**GIVEN**`) step and a `**THEN**` step. `**AND**` and
  `**BUT**` steps are allowed.
- Scenario IDs extend their requirement ID: `[AUTH-01.1]`, `[AUTH-01.2]`.
- Cover failure and edge behaviour (invalid input, limits, concurrency,
  permissions), not only the happy path.
- State non-functional needs (latency, availability, privacy) as requirements
  with measurable scenarios when they form part of the contract.

## Validation

`specmaker.py check <id> specs` enforces the format above. It also checks:

- ADDED IDs are new, and MODIFIED/REMOVED IDs exist in the right capability.
- No requirement ID appears twice within the change.
- It warns when another open change touches the same requirement.

At archive, the script checks that each requirement the change modifies or
removes has not changed in the living specs since accreditation. It then
verifies the merge result independently.
