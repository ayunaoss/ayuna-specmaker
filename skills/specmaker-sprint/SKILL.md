---
name: specmaker-sprint
description: >-
  Specmaker sprint phase. Runs one planned sprint: implements its stories test
  first inside the accredited design's file boundary, handles deviations, runs the
  project's quality gates, verifies spec against code with a fresh-context
  reviewer and a scenario-to-test trace, and asks a named human to sign off. Use
  when a specmaker change is in the sprint phase, or the user asks to build,
  implement, continue or sign off a sprint.
license: MIT
compatibility: Requires the specmaker skill alongside; git recommended (file-boundary and evidence checks use it).
metadata:
  author: ayuna
  version: "0.1.0"
---

# Sprint: build, verify, sign off

**Goal:** the sprint's stories work. Every scenario they cover has a passing
test that names its ID. Nothing outside the agreed files changed without being
recorded. A human signs off based on evidence: the gate results, the trace, and
the verifier's report, not ticked boxes.

**Locate specmaker** (your harness may not say where this skill lives):

```bash
R=$(git rev-parse --show-toplevel 2>/dev/null || pwd); for d in "$SPECMAKER_HOME" "${CLAUDE_SKILL_DIR}/../specmaker" "$R/.opencode/skills/specmaker" "$R/.agents/skills/specmaker" "$R/.claude/skills/specmaker" "${XDG_CONFIG_HOME:-$HOME/.config}/opencode/skills/specmaker" "$HOME/.agents/skills/specmaker" "$HOME/.claude/skills/specmaker" $(ls -d "${CLAUDE_CODE_PLUGIN_CACHE_DIR:-$HOME/.claude/plugins}"/cache/*/specmaker/*/skills/specmaker 2>/dev/null | sort -V | tail -1); do [ -f "$d/scripts/specmaker.py" ] && { d=$(cd "$d" && pwd); case "$d" in "$R"/*) echo "${d#"$R"/}";; *) echo "$d";; esac; break; }; done
```

Call the printed folder `SM`; run `python3 $SM/scripts/specmaker.py` from the project root. If nothing prints, ask the user to install all seven specmaker skills side by side, or to set `SPECMAKER_HOME`. This skill's own files are in `$SM/../specmaker-sprint/`.

- Read `$SM/references/conventions.md` and `$SM/references/goldfish.md` first.

## 0. Requests during the sprint

If anyone asks for something new or different, don't change course. Record it
with `cr add` (`$SM/references/change-requests.md`), say it is parked until the
sprint boundary, and continue. Only a **blocker** (continuing would build
something known to be wrong) is triaged at once, with the user.

## 1. Start or resume

- Run `status <id>`. If a sprint is `active`, read its sprint file and the
  ledger, and continue from the first unticked task.
- `reopened` or `rewound` sprints run before any later sprint. `impact <id>`
  shows what changed; only affected stories need work, but evidence and
  sign-off start over.
- To start sprint N: commit or stash unrelated work, run `sprint-start <id> N`,
  then copy `assets/templates/sprint.md` to `sprints/sprint-NN.md` with the
  goal and stories from the Sprint Plan. Tell the user the goal, the stories,
  and any `owner: human` tasks.
- `sprint-start` refuses when:
  - the plan is unapproved or changed since its approval: the user runs
    `approve-plan`.
  - code outside `specmaker/` changed since the last checkpoint (design
    approval, a sign-off or a rewind). Never write code before a sprint
    starts. Show the user the files: they revert them, or accept them with
    `sprint-start <id> N --accept-prior "<reason>"`, a human gate.

## 2. Build, one story at a time

In dependency order:

1. **Read** the story's scenarios (`spec <ID>`, delta specs), the LLD
   sections it touches, and its tasks.
2. **Tests first:** one test per covered scenario, named with its ID
   (`test_idle_session_expires__AUTH_01_1` plus `covers: AUTH-01.1`). Watch
   them fail for the right reason.
3. **Implement** exactly as the LLD and ADRs say, with the names the LLD
   fixed. Name anything new by `$SM/references/naming.md`, after the
   repository's own rules.
4. **Run** the story's tests and the relevant existing suite.
5. **Tick** tasks in `backlog.md` only when done and passing. Never tick
   `owner: human` tasks; the user does.
6. **Log** one line in the sprint file's Progress section. Commit at story
   boundaries if the user's workflow allows.

You may delegate a story to a subagent; review its diff before ticking.

**Stay inside the design:**

- Change only files in the sprint's task `files:` lists. Any other file goes
  under `## Deviations` with a reason **before** you change it.
- If a design decision is missing:
  - **Small and invisible** (a private helper's name): decide, and note it as
    `- [x] <decision> - reason`.
  - **Anything observable, or contradicting the LLD, an ADR, a spec or a
    contract:** stop. Add `- [ ] <question>`, record
    `ledger <id> --kind deviation`, and ask the user. Design changes go
    through a change request. Never edit a locked design file to fit the code,
    and never weaken a test to pass a wrong scenario.

## 3. Verify

When every committed story is done:

1. **Gates:** commit, then `gates <id> N`. Fix and re-run until they pass.
   Code changes after `gates` need a new run; committing `specmaker/` files
   doesn't.
2. **Trace:** `trace <id> --out reviews/sprint-NN-trace.md`. Every covered
   scenario needs a test. A scenario that can only be checked by hand is
   recorded in the sprint file's Verification section, and accepted by the
   user at sign-off (`--accept-gaps "manually verified: <how>"`).
3. **Verifier:** dispatch one fresh-context goldfish (`goldfish.md`) with
   persona [references/personas/verifier.md](references/personas/verifier.md)
   and `Mode: VERIFY`. Give it the delta specs, the LLD, the sprint file,
   `backlog.md`, the gates JSON, the trace, and the git base SHA from
   `status <id> --json`. It writes `reviews/sprint-NN-verification.md`, ending
   with `Verdict: PASS | PASS-WITH-NOTES | FAIL`. On FAIL, fix the code (not
   the specs), re-run the gates, and use a **new** verifier writing `-r2`,
   then `-r3`.
4. `check <id> sprint:N` passes.

## 4. Sign off

Fill in the sprint file's Verification section: the gates, trace and verifier
results, deviations, and known issues. Add a short demo: commands or steps
that show the sprint goal working. Then ask:
**"Do you sign off sprint N? Reply yes with your approver identity, or tell me
what is missing."** End your turn. If you cannot ask, stop (conventions §4a).

On a yes, it is a human gate (conventions §4):
`signoff <id> N --by <approver>`. In `signed` or `terminal` mode the user runs
it; in `chat` mode you do. The script re-checks all the evidence and reports
what is missing. Then write the sign-off into the sprint file and remind the
user of parked requests: they are triaged before the next sprint starts.

## 5. Next

Offer the next sprint. After the last one, run `phase <id> retro` (in guided
mode, ask first) and hand over to `specmaker-retro`.
