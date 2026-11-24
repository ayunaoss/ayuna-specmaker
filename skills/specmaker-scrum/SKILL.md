---
name: specmaker-scrum
description: >-
  Specmaker scrum phase. Breaks an accredited design into an agile backlog
  (epics, features, user stories with acceptance criteria tied to spec scenario
  IDs, and tasks with exact file boundaries), estimates it, and plans sprints that
  follow the design's implementation phases. Exports to issue trackers. Use when
  a specmaker change is in the scrum phase, or the user asks to plan, break down
  or estimate the work for one.
license: MIT
compatibility: Requires the specmaker skill installed alongside (shared script and references).
metadata:
  author: ayuna
  version: "0.1.0"
---

# Scrum: from design to backlog and sprint plan

**Goal:** `backlog.md`, which turns the accredited design into work items that
satisfy three conditions:

- Every scenario is covered by a story.
- Every task names the files it touches and leaves no design decision open.
- The sprint plan follows the LLD's Implementation Phases, so each sprint ends
  with a buildable, tested system.

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
- Read `$SM/references/conventions.md` first.
- This skill's own files (`references/`, `assets/`) are in `$SM/../specmaker-scrum/`.

## Steps

### 1. Ingest

- Run `status <id>`. The phase must be `scrum` and the lock must be intact.
- Read the LLD (especially Implementation Phases, File Boundary and Test
  Strategy), the delta specs, the ADRs, `accreditation.md` and the ledger. Every
  `CONDITION` entry in the ledger must become a story or a task.
- Run `trace <id>` to list all scenario IDs that need coverage.
- Ask the user two things, one at a time:
  - Sprint length and capacity in points. If they have no velocity history,
    propose a default and say it is a guess.
  - Who does the work (agent, humans, or both). Tasks that need a human, such
    as credentials, vendor accounts or manual QA, get `owner: human`.

### 2. Structure

Copy `assets/templates/backlog.md` to `changes/<id>/backlog.md`.

- **Epics** (`## E1 - ...`) are large outcomes, usually one per HLD goal or
  per major component. On the lite track a single epic is fine.
- **Features** (`### F1 - ...`) are coherent slices of behaviour, usually one
  per capability or per group of requirements.
- **Stories** (`#### S1 - As a <role>, I want <capability>, so that <benefit>`)
  are vertical slices that a user or client can observe. Each story has:
  - `**Covers**`: the scenario IDs it makes pass. These are its acceptance
    criteria. Do not restate the scenarios; the IDs point to them.
  - `**Points**` (1, 2, 3, 5, 8 or 13), `**Priority**` (MoSCoW) and
    `**Depends**` (story IDs).
  - `**Type**`: `story` (the default), `enabler` (infrastructure or a
    refactor the stories need), `spike` (time-boxed learning, with a question
    and a time box), or `chore`. Only non-story types may cover no scenario.
- **Tasks** (`- [ ] T<story>.<n> <imperative> - files: <paths>`) are concrete
  steps of a few hours each. The paths must come from the LLD File Boundary.
  Start each behaviour story with a task that writes the failing tests for its
  scenarios, named with their IDs.

Number IDs in order through the file, and never renumber after the sprint phase
has started.

### 3. Estimate and plan

- Estimate in Fibonacci points, relative to the smallest story. Split anything
  at 13 points. Spikes get a time box instead of points that look precise.
- Fill in the `## Sprint Plan` table. Map LLD phases to sprints in order. Keep
  dependencies in the same or an earlier sprint. Stay within capacity, and leave
  slack (about 20%) for review and fixes. Each sprint has a goal that a person
  can demo.
- Stories marked `Won't` stay in the file, out of the plan, as a record of
  what was dropped.

### 4. Validate

Run `check <id> backlog` and fix every error. The script checks:

- every scenario is covered, and every covered ID exists
- every story has points and tasks, and every task has files
- there are no dependency cycles and no dependency planned in a later sprint
- every story is planned exactly once

Then review the plan with the user: the sprint goals, the points per sprint
against capacity, and the riskiest story. Adjust until they agree.

### 5. Export (optional)

If the team uses an issue tracker, run `export <id> --format csv` (Jira, Linear
and GitHub Projects can import CSV) or `--format json` for scripts. Keep
`backlog.md` as the source of truth, and sync status back into it, not the
other way around.

### 6. Close

Run `phase <id> sprint`. Tell the user that the sprint phase
(`specmaker-sprint`) runs one sprint at a time and ends each with a human
sign-off.

## Changing the backlog later

The backlog is not locked, because plans change. During the sprint phase:

- Add, split or re-plan stories freely, but run `check <id> backlog` after
  every edit.
- Never delete a story that has finished tasks. Mark it `Won't` with a reason.
- Removing scenario coverage is not a backlog change. It is a design change,
  so `amend` the design.
