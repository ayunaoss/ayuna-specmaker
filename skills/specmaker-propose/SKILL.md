---
name: specmaker-propose
description: >-
  Specmaker propose phase. Turns an HLD (or a clear request, on the lite track)
  into a Low-Level Design (lld.md), behaviour specs with requirement and scenario
  IDs (specs/), Architecture Decision Records for framework, data and deployment
  choices (adrs/), and interface contracts (contracts/), confirming each section
  with the user. Use when a specmaker change is in the propose phase, or the user
  asks to design, specify or write the LLD for one.
license: MIT
compatibility: Requires the specmaker skill installed alongside (shared script and references).
metadata:
  author: ayuna
  version: "0.1.0"
---

# Propose: LLD, specs, decisions

**Goal:** a design complete enough that an engineer who was not in the room can
build it without making a single design decision. That is the bar the accredit
phase will test against.

**Locate specmaker first.** Some harnesses (OpenCode included) load this text
without saying where the skill folder is (Claude Code fills in
`${CLAUDE_SKILL_DIR}` below; elsewhere it is simply empty). Find it with:

```bash
R=$(git rev-parse --show-toplevel 2>/dev/null || pwd); for d in "$SPECMAKER_HOME" "${CLAUDE_SKILL_DIR}/../specmaker" "$R/.opencode/skills/specmaker" "$R/.agents/skills/specmaker" "$R/.claude/skills/specmaker" "${XDG_CONFIG_HOME:-$HOME/.config}/opencode/skills/specmaker" "$HOME/.agents/skills/specmaker" "$HOME/.claude/skills/specmaker" $(ls -d "${CLAUDE_CODE_PLUGIN_CACHE_DIR:-$HOME/.claude/plugins}"/cache/*/specmaker/*/skills/specmaker 2>/dev/null | sort -V | tail -1); do [ -f "$d/scripts/specmaker.py" ] && { d=$(cd "$d" && pwd); case "$d" in "$R"/*) echo "${d#"$R"/}";; *) echo "$d";; esac; break; }; done
```

Call the printed folder `SM`. It is relative to the project root when
specmaker is installed in the project, so run specmaker commands from the
project root and copy `SM` exactly. If nothing is printed, ask the user where
specmaker is installed (or to set `SPECMAKER_HOME`). All seven specmaker
skills must be installed side by side, including the core `specmaker` skill. Never guess paths from the
project's working directory.

Then:

- Run the helper script as `python3 $SM/scripts/specmaker.py <command>`.
- Read `$SM/references/conventions.md` and `$SM/references/spec-format.md` first.
- This skill's own files (`references/`, `assets/`) are in `$SM/../specmaker-propose/`.

**Outputs, all in `changes/<id>/`:**

| File | Template | Purpose |
|---|---|---|
| `lld.md` | `assets/templates/lld.md` | How it is built |
| `specs/<capability>/spec.md` | `assets/templates/spec.md` | What it must do (delta specs) |
| `adrs/NNNN-<title>.md` | `assets/templates/adr.md` | Why each significant choice was made |
| `contracts/*` | none | Machine-readable interfaces (OpenAPI, JSON Schema, proto, SQL DDL), where they apply |

## Steps

### 1. Ingest

Run `status`. Read `hld.md` (full track), `ledger.md`, `project.md`, and the
living specs this change touches (`spec`, then `spec <REQ-ID>` for the
details). Read the code areas named in the HLD.

On the **lite track** there is no HLD. Run a short version of the ideate
conversation instead: problem, goal, non-goals and the chosen approach, in a
few questions. Record them in the ledger and in LLD section 1.

Then propose a **section plan** to the user: which capabilities get delta specs
(new or modified, with their ID prefixes), which decisions need ADRs, and which
contracts are needed. Agree on it before writing anything.

### 2. Decisions first (ADRs)

Read [adr-guide.md](references/adr-guide.md). It lists the decision topics to
consider (language, framework, persistence, messaging, API style, auth, hosting
and deployment topology, infrastructure-as-code, CI/CD, observability, test
tooling) and when each needs an ADR.

- Write an ADR only for a decision that is **new or changed** relative to
  `project.md`. Choices `project.md` already settles need none.
- Each ADR compares at least two real options against named decision drivers.
  Recommend one, explain the reason, and ask the user to choose. Set
  `Status: Accepted` only after they agree.
- Settle decisions before the LLD sections that depend on them. Writing the
  LLD first and justifying it afterwards is how designs end up rationalised
  rather than reasoned.

### 3. LLD, section by section

Copy the LLD template. Work through it in this order, pausing after each group
for the user's go-ahead (one question per message):

1. Context and Scope → Architecture → Data Model
2. Interfaces and Contracts → Behaviour and Error Handling
3. Cross-Cutting Concerns → Technology and Deployment
4. Alternatives Considered → Test Strategy → Migration and Rollout
5. Implementation Phases → File Boundary → Risks → Traceability

Rules for the LLD:

- Every decision the implementer would otherwise have to make goes into the LLD
  or an ADR. Examples: names of new modules, schema fields and types, error
  codes, retry and timeout values, config keys, library versions.
- **Implementation Phases** must leave the system buildable and testable after
  each phase. These become the backbone of the sprint plan.
- **File Boundary** lists the exact repository paths to create, modify or
  delete. Use a glob only for generated output. The sprint phase enforces this
  list.
- A section that truly does not apply says `N/A - <reason>`. Do not delete it.

### 4. Delta specs

Write one capability at a time. Before each one, say which capability you are
writing. Save each file as soon as it is drafted, so an interrupted session
keeps its progress.

- Follow spec-format.md exactly. Requirements say *what*, never *how*.
- Write them in present tense, describing the system **after** the change
  ("The system SHALL lock the account after 5 failed attempts"). Never
  describe the change itself ("now locks", "no longer allows"). The archive
  step merges this text into the living specs word for word.
- Cover error, limit and permission behaviour, not just the happy path. Every
  Non-Goal that users might expect gets either a requirement or nothing; never
  a vague mention.
- A change with no behaviour change at all (pure refactor, tooling) runs
  `set <id> skip_specs true` and says why in the LLD. Never invent a
  requirement to satisfy the checker.

### 5. Self-consistency pass

Before leaving the phase, check the whole set yourself:

- Every HLD goal maps to at least one requirement, or the LLD explains why not.
- Nothing normative (SHALL or MUST behaviour) appears only in the LLD. Move it
  into a spec.
- The LLD, the specs, the ADRs and the contracts agree on names, fields, error
  codes and limits.
- Nothing duplicates or contradicts a living spec that this change does not
  modify.

Fix what you find. Then run `check <id> design` and fix every error. Review the
warnings with the user.

### 6. Close

Give the user the list of files and the TL;DR of the LLD. Ask whether the design
is ready for review. On a yes, run `phase <id> accredit`, and tell them that the
accredit phase (`specmaker-accredit`) runs fresh-context reviewers and then asks
them for a verdict.

## When re-entered after `amend`

Read the ledger entries since the last accreditation and the review reports that
caused the amendment. Change only what they require. List the changed sections
in the ledger (`--kind note`), so the accredit phase can re-review only those
sections.
