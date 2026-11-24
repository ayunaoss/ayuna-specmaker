---
name: specmaker-retro
description: >-
  Specmaker retro phase and drift check. Closes a change: runs a retrospective
  with metrics, checks living specs against code for drift, rewrites delta specs
  into present-tense wording, merges them into the living specs with a
  deterministic, self-verifying merge, promotes ADRs to the project decision log,
  feeds lessons back into project.md, and archives. Also use any time the user
  asks to check spec/code drift or spec coverage in a specmaker workspace.
license: MIT
compatibility: Requires the specmaker skill installed alongside (shared script and references).
metadata:
  author: ayuna
  version: "0.1.0"
---

# Retro: learn, merge, archive (and drift checks)

**Goal:** the living specs describe the system as it now is, the decisions
behind it are in the project's ADR log, the team has learned something
specific, and the change folder is archived.

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
- This skill's own files (`references/`, `assets/`) are in `$SM/../specmaker-retro/`.

## A. Closing a change (phase `retro`)

### 1. Retrospective

Copy `assets/templates/retro.md` to `changes/<id>/retro.md`. Gather the facts
first, from `status <id> --json`, the backlog, the sprint files, the review
reports and the ledger:

- the points planned and finished per sprint
- the number of review rounds and findings by severity
- the deviations and amendments, and what caused each
- the gate failures, verifier FAILs, and accepted gaps

Then discuss them with the user, **one question at a time**: what helped, what
hurt, and what to change. Keep only lessons that are specific and actionable.
"Communicate better" is not one. "Name the external rate limit in the HLD
constraints" is.

### 2. Promote lessons

For each lesson that should change future work, propose an exact edit to
`project.md`: a line under Rules by Phase, the Definition of Ready or Done, the
Review Policy, or the Quality Gates. Apply it only after the user agrees.

### 3. Check the wording

Living specs must read as plain facts about the system. The propose phase
writes deltas in end-state, present-tense wording, so this is normally a quick
read. Scan the deltas for change wording: "now", "no longer", "new",
"instead of", "will be changed to".

If you find any, fixing it means editing locked files. Show the user the exact
rewording. If they want it fixed before merging:

1. Run `amend <id> --reason "retro: wording-only fix to delta specs"`.
2. Make the edit.
3. Run `phase <id> accredit`.
4. Once the user confirms the diff does not change meaning, record
   `accredit <id> --verdict approved --by "<name>"`. The existing review
   reports satisfy the lens minimum.
5. Walk forward again with `phase` (scrum → sprint → retro). These steps pass,
   because the backlog and sign-offs are unchanged.

### 4. Merge and archive

1. `archive <id> --dry-run` shows every add, modify and remove, plus the ADRs
   to be promoted. Show the user that output, with a one-line explanation of
   each operation, and **end your turn** with the question "Archive now?"
2. Only after the user has seen the dry-run and says yes, run `archive <id>`.
   An earlier "merge the specs" or "finish the retro" is not that yes, because
   the user had not yet seen what will change. The script:
   - refuses if a `depends_on` change is still open
   - refuses if a requirement this change modifies was changed in the living
     specs since accreditation (base drift)
   - merges by requirement ID, then verifies the result independently
   - copies the ADRs into `specmaker/adrs/` with project-wide numbers
   - moves the change to `specmaker/archive/YYYY-MM-DD-<id>/`
3. Suggest committing the archive move and the living-spec changes together, so
   reviewers see exactly how the source of truth changed.

## B. Drift check (any time)

Use this when code may have changed outside specmaker (hotfixes, other
changes), before starting a change in an area, or on a schedule.

1. `coverage [--capability <path>] --out <file>` lists every living scenario
   with no test that names its ID. Missing tests are the cheapest drift
   signal.
2. For each capability in scope, read its living spec and the code that
   implements it, one capability at a time to keep context small. Report only
   the differences:
   - behaviour in a spec that is missing or different in the code
   - fields, codes or limits that differ
   - hardcoded values where the spec implies configuration
   - behaviour in the code that no spec covers
3. Write `specmaker/drift-YYYY-MM-DD.md`: one section per capability, listing
   each divergence with `code:<path>:<line>` evidence, or "No drift found".
4. For each divergence, the user decides:
   - **Code is wrong:** fix it now, or as a lite change.
   - **Spec is outdated:** open a change (lite, or docs-only if behaviour is
     already in production) with a MODIFIED delta.

Never edit living specs directly. They change only through `archive`, so every
change to the source of truth has a review trail.

## C. Spec hygiene (optional, occasional)

When a capability spec grows too large (dozens of requirements), or has
requirements that overlap, propose a docs-only change that reorganises it:
split it into child capabilities (`billing/invoices`, `billing/refunds`) or
merge duplicates. Requirement IDs never change. Moving a requirement between
capabilities is a REMOVED in one and an ADDED with a **new** ID in the other.
Note the old ID in the Migration line.
