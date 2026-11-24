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
- Read `$SM/references/conventions.md` and `$SM/references/goldfish.md` first.
- This skill's own files (`references/`, `assets/`) are in `$SM/../specmaker-sprint/`.

## 1. Start or resume

- Run `status <id>`. If a sprint is `active`, resume it: read its sprint file
  and the ledger, then continue from the first unticked task.
- To start sprint N:
  - Commit or stash unrelated work first, so the recorded git base is clean.
  - Run `sprint-start <id> N`. It refuses if the design lock is broken, if an
    earlier sprint is not signed off, or if the backlog fails its checks.
  - Copy `assets/templates/sprint.md` to `sprints/sprint-NN.md` and fill in the
    goal and the committed stories from the Sprint Plan.
- Tell the user the sprint goal, the stories and the points, and any tasks marked
  `owner: human` that they will need to do.

## 2. Build, one story at a time

Work in dependency order. For each story:

1. **Read** the scenarios it covers (`spec` shows the living ones; the delta
   specs hold the new ones), the LLD sections it touches, and its tasks.
2. **Write the tests first.** Write tests for every covered scenario. Each test
   names its scenario ID (for example `test_idle_session_expires__AUTH_01_1`,
   with a `covers: AUTH-01.1` comment or a test title containing `AUTH-01.1`).
   Run them and confirm they fail for the right reason.
3. **Implement** until the tests pass. Follow the LLD and the ADRs exactly.
   Follow the codebase's existing patterns where the design is silent on
   style.
4. **Run** the story's tests plus the relevant existing suite. Fix any
   regressions you caused.
5. **Tick** each task in `backlog.md` (`- [x]`) only when its work is done and
   its tests pass. Never tick a task marked `owner: human`; ask the user to do
   it and tick it themselves.
6. **Log** a line in the sprint file's Progress section: the story, the files
   changed, and the test result. Commit at story boundaries if the user's
   workflow allows it.

You may delegate a story to a subagent when the harness supports it. Give it the
story, its scenarios, the relevant LLD sections and its file list. Review the
subagent's diff yourself before ticking anything.

### Staying inside the design

- Change only files in the sprint's task `files:` lists. If another file must
  change (an import, a fixture, a generated file), add it to `## Deviations`
  in the sprint file with the reason, **before** changing it.
- If you need a design decision the LLD did not make:
  - **Small and local** (a private helper's name, the order of internal
    steps): decide, follow the codebase's patterns, and note it under
    Deviations as `- [x] <decision> - reason`.
  - **Anything observable, or anything that contradicts the LLD, an ADR, a
    spec or a contract:** stop. Add `- [ ] <question>` under Deviations, record
    it with `ledger <id> --kind deviation`, and ask the user. If the answer
    changes a design file, the path is `amend`, re-accreditation, then
    resuming. Never edit a locked design file to make the code fit.
- If a scenario turns out to be wrong or untestable as written, that is a
  design problem. Raise it as above; do not quietly weaken the test.

## 3. Verify

When every committed story's tasks are ticked:

1. **Quality gates.** Commit the work, then run `gates <id> N`. It runs the
   commands in `project.md` → Quality Gates and records exit codes, output
   tails and the commit SHA in `reviews/sprint-NN-gates.json`. Fix failures and
   re-run. Never edit the gates file by hand.
2. **Trace.** Run `trace <id> --out reviews/sprint-NN-trace.md`. Every scenario
   covered by this sprint's stories must list at least one test. Fill the
   gaps with tests, or mark a scenario as manually verified in the sprint file
   and get the user's agreement.
3. **Goldfish verification.** Dispatch one fresh-context verifier per
   goldfish.md, with persona
   [references/personas/verifier.md](references/personas/verifier.md) and
   `Mode: VERIFY`. Give it these paths:
   - the delta specs and the LLD
   - the sprint file and `backlog.md`
   - the gates JSON and the trace file
   - the git base SHA from `status <id> --json`, so it can run
     `git diff <base>` itself

   Its report goes to `reviews/sprint-NN-verification.md` and must end with
   `Verdict: PASS | PASS-WITH-NOTES | FAIL`. On FAIL, fix the code (not the
   specs), re-run the gates, and re-verify with a **new** verifier writing
   `reviews/sprint-NN-verification-r2.md` (then `-r3`, and so on). Sign-off
   reads the highest round. Never overwrite an earlier round.
4. Run `check <id> sprint:N` and fix every error.

## 4. Sign off

Fill in the sprint file's Verification section: links to the gates, trace and
verifier reports, the scenarios proven, deviations, and known issues. Then give
the user a short demo script: the commands to run, or the steps to try, that
show the sprint goal working.

Ask directly: **"Do you sign off sprint N? Reply yes with the name to record, or
tell me what is missing."**

- Only an explicit yes from the user in chat counts. End your turn after
  asking. If you cannot ask (conventions §4a), stop.
- Record it with `signoff <id> N --by "<name the user gave>"`. With
  `Human gates: terminal` (see `status`), do not run it. Give the user the
  command (conventions §4) to run in their own terminal, wait for "done", then
  confirm with `status <id>`. The script re-checks:
  - the tasks are ticked and there are no open deviations
  - the gates passed on the current commit
  - the verifier verdict is PASS or PASS-WITH-NOTES
  - the design lock is intact
  - no file outside the boundary changed without being listed as a deviation
  - every covered scenario is referenced by a test
- If the user consciously accepts untested scenarios, pass
  `--accept-gaps "<their reason>"`. The reason is stored in the record.
- Write the sign-off into the sprint file.

## 5. Next

- If more sprints are planned, offer to start the next one.
- After the last sprint, run `phase <id> retro` and hand over to the retro
  phase (`specmaker-retro`).
