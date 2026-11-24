# Project Charter

> **TL;DR** Acme Notes is a small note-taking service for teams. It is a Python
> package with no runtime dependencies, so it stays easy to embed and audit.

## Context

Acme Notes stores short notes for signed-in team members. It runs as a single
process behind the company's reverse proxy. The session store keeps state in
memory. A restart signs everyone out, and that is accepted.

## Stack

- Language/runtime: Python 3.10+
- Frameworks: none (standard library only)
- Data: in-process memory
- Hosting/deployment: single container behind the shared reverse proxy
- CI/CD: unittest on every push

## Conventions

- Source in `src/notes/`, tests in `tests/`, one test module per source module.
- Test names end with the scenario ID they prove: `test_..._SESS_02_2`, plus a
  `covers: SESS-02.2` docstring.
- Errors that reach the API carry a snake_case `reason` code.

## Rules by Phase

- propose: every time value (timeouts, lifetimes) is a named module constant.
- propose: every client-visible error code appears in a spec scenario. (retro idle-session-timeout)
- sprint: inject the clock; never call `datetime.now()` inside logic.
- sprint: each verifier finding becomes a task or a ledger decision before sign-off. (retro idle-session-timeout)

## Spec Areas

- SESS: identity/session

## Quality Gates

- unit tests: `PYTHONPATH=src python3 -m unittest discover -s tests`
- byte-compile: `python3 -m compileall -q src`

## Definition of Ready (story)

- Covers at least one scenario ID, or is typed enabler/spike/chore.
- Every task names its files and leaves no design decision to the implementer.
- Dependencies are planned in the same or an earlier sprint.

## Definition of Done (story)

- All tasks ticked; each covered scenario has a test that names its ID.
- Quality gates pass on the committed code.
- No change outside the sprint file boundary, unless it is recorded as a deviation.

## Review Policy

- Default preset: standard
- Lite track preset: quick
- Max re-review rounds: 2
- Reviewer model: a different model family from the drafting model, when available

## Autonomy

- Mode: guided
- Human gates: terminal

## Approvers

- Alex Chen (tech lead)
