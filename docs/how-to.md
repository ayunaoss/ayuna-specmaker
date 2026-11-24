# Specmaker HOW-TO

Task-oriented recipes. Each one gives:

- what to type to your coding agent
- what the agent does, and which script commands it runs
- what you get

All examples come from the worked example in
[`examples/acme-notes`](../examples/acme-notes). The
[walkthrough](walkthrough.md) tells the same story as a narrative.

In the commands below, `S` stands for the helper script. The agent finds it on
its own. To run it yourself, set:

```bash
S="python3 .agents/skills/specmaker/scripts/specmaker.py"   # default project install
```

- [1. Install](#1-install)
- [2. Talk to specmaker](#2-talk-to-specmaker)
- [3. Set up a project](#3-set-up-a-project)
- [4. Build a feature, end to end (full track)](#4-build-a-feature-end-to-end-full-track)
- [5. Small change (lite track)](#5-small-change-lite-track)
- [6. Tiny fix (skip specmaker)](#6-tiny-fix-skip-specmaker)
- [7. Adopt specmaker in an existing codebase](#7-adopt-specmaker-in-an-existing-codebase)
- [8. Resume after a break or in a new session](#8-resume-after-a-break-or-in-a-new-session)
- [9. Handle review findings](#9-handle-review-findings)
- [10. Control review cost and reviewer model](#10-control-review-cost-and-reviewer-model)
- [11. Review without subagents (cold-read mode)](#11-review-without-subagents-cold-read-mode)
- [12. Tag tests with scenario IDs](#12-tag-tests-with-scenario-ids)
- [13. Handle a deviation, or change an approved design](#13-handle-a-deviation-or-change-an-approved-design)
- [14. Human-only tasks](#14-human-only-tasks)
- [15. Export the backlog to Jira, GitHub or Linear](#15-export-the-backlog-to-jira-github-or-linear)
- [16. Check specs against code (drift)](#16-check-specs-against-code-drift)
- [17. Two changes touching the same requirement](#17-two-changes-touching-the-same-requirement)
- [18. Run specmaker checks in CI](#18-run-specmaker-checks-in-ci)
- [19. Autopilot mode](#19-autopilot-mode)
- [20. Troubleshooting](#20-troubleshooting)
- [21. Command reference](#21-command-reference)

---

## 1. Install

Specmaker is seven skill folders. Copy them into a folder your agent scans for
skills. Python 3.8 or later is needed for the helper script. Git is optional but
recommended. Install **all seven**: every phase skill needs the core
`specmaker` skill beside it. The repository is
[github.com/ayunaoss/ayuna-specmaker](https://github.com/ayunaoss/ayuna-specmaker).

### 1a. With the skills CLI (any agent)

[`npx skills`](https://skills.sh) works for OpenCode, Claude Code, Codex,
Cursor and many more. `bunx skills` also works if you use Bun.

```bash
npx skills add ayunaoss/ayuna-specmaker --skill '*' -a opencode -a claude-code
```

What you get (verified with skills 1.9.0):

```text
.agents/skills/specmaker ... specmaker-sprint     <- real folders (OpenCode, Codex, Cursor read these)
.claude/skills/specmaker -> ../../.agents/skills/specmaker   <- symlinks for Claude Code
skills-lock.json                                  <- lets `npx skills update` / `check` track versions
```

- Without `--skill '*'` the CLI asks which skills to install. Pick all seven.
- Add `-g` for a global install.
- Use `npx skills update` to upgrade and `npx skills remove --all` to
  uninstall.

### 1b. As a Claude Code plugin

```bash
claude plugin marketplace add ayunaoss/ayuna-specmaker
```

```bash
claude plugin install specmaker@ayuna
```

In a session, use `/plugin marketplace add ayunaoss/ayuna-specmaker`, then
`/plugin install specmaker@ayuna`. The repository root is both the plugin and a
one-plugin marketplace named `ayuna`. `claude plugin validate .` passes on it.

### 1c. From a clone, with install.sh (no Node needed)

```bash
git clone https://github.com/ayunaoss/ayuna-specmaker.git
cd your-project
```

Then pick the line for your agent:

```bash
../ayuna-specmaker/install.sh                             # -> .agents/skills/ (default: OpenCode, Codex, Cursor and others)
```

```bash
../ayuna-specmaker/install.sh --global                    # -> ~/.agents/skills/
```

```bash
../ayuna-specmaker/install.sh --agent claude              # -> .claude/skills/
```

```bash
../ayuna-specmaker/install.sh --agent opencode            # -> .opencode/skills/ (OpenCode-only folder)
```

Useful options:

| Option | Effect |
|---|---|
| `--link` | Symlink instead of copying, so `git pull` in the specmaker repo updates you |
| `--explicit-only` | The agent loads specmaker skills only when you name them; they never auto-trigger |
| `--dry-run` | Show what would be installed |
| `--uninstall` | Remove the seven skill folders from the target |

Check the result:

```bash
ls .agents/skills
# specmaker  specmaker-accredit  specmaker-ideate  specmaker-propose  specmaker-retro  specmaker-scrum  specmaker-sprint
```

The skills must stay **side by side** in the same folder. The phase skills reach
the shared script and references through the `specmaker` folder next to them.

Some harnesses, OpenCode 2.x included, hand a skill's text to the agent without
saying where its folder is. Each specmaker skill therefore starts with a short
command that looks in these standard locations, in order:

- `$SPECMAKER_HOME`
- the project's `.opencode/skills`, `.agents/skills` or `.claude/skills`
- the global `~/.config/opencode/skills`, `~/.agents/skills` or
  `~/.claude/skills`

If you install somewhere else (`--target DIR`), set
`SPECMAKER_HOME=/abs/path/to/skills/specmaker` in the environment you start
your agent from.

## 2. Talk to specmaker

There are no slash commands. You talk to the agent, and it loads the right skill:

- **By name** (most reliable):
  - OpenCode: write `@specmaker` (or `@specmaker-sprint` and so on) in your
    message.
  - Claude Code with skills in `.claude/skills`: `/specmaker`,
    `/specmaker-sprint` and so on.
  - Claude Code with the plugin: `/specmaker:specmaker`,
    `/specmaker:specmaker-sprint` and so on (plugin skills are namespaced).
- **By intent:** the skill descriptions make the agent pick them up when you say
  things like "let's spec this feature with specmaker" or "where are we on the
  session change?". If you installed with `--explicit-only`, use names.

Good opening messages:

```text
@specmaker I want to add idle session timeouts to Acme Notes. Tokens never expire today.
@specmaker where are we?
@specmaker-sprint start sprint 2 of idle-session-timeout
@specmaker-retro check the identity/session specs for drift
```

## 3. Set up a project

```text
@specmaker set this project up
```

The agent runs `S init`, which creates:

```text
AGENTS.md        <- a short marked block telling any agent to load the specmaker skill first
specmaker/
  project.md     <- charter template
  specs/  changes/  archive/  adrs/
```

The `AGENTS.md` block matters. Without it, agents often answer questions about
`specmaker/` by reading the files directly and skip the skills, and with them
the rules and the script. We observed this in testing with OpenCode. If the
project has a `CLAUDE.md` and no `AGENTS.md`, the block goes into `CLAUDE.md`.
Re-running `init` refreshes the block and never touches the rest of the file.
Use `--no-agents-md` to skip it.

It then fills in `project.md` with you. The section that matters most is
**Quality Gates**: commands that must exit 0 before any sprint can be signed off.
The script runs them itself; the agent does not just claim they passed.

```markdown
## Quality Gates

- unit tests: `PYTHONPATH=src python3 -m unittest discover -s tests`
- byte-compile: `python3 -m compileall -q src`
```

Gate examples for other stacks:

| Stack | Gates |
|---|---|
| Node/TypeScript | ``- test: `npm test --silent` `` · ``- types: `npx tsc --noEmit` `` · ``- lint: `npx eslint .` `` |
| Python (pytest) | ``- test: `pytest -q` `` · ``- lint: `ruff check .` `` · ``- types: `mypy src` `` |
| Go | ``- test: `go test ./...` `` · ``- vet: `go vet ./...` `` |
| Java (Maven) | ``- verify: `mvn -q verify` `` |
| Rust | ``- test: `cargo test -q` `` · ``- clippy: `cargo clippy -- -D warnings` `` |

Also fill in **Spec Areas** (one requirement-ID prefix per capability, such as
`- SESS: identity/session`), **Review Policy** and **Approvers**. See the filled
example: [`examples/acme-notes/specmaker/project.md`](../examples/acme-notes/specmaker/project.md).

Commit `specmaker/`. It is meant to live in the repository next to the code.

## 4. Build a feature, end to end (full track)

### 4.1 Start and triage

```text
@specmaker Tokens in Acme Notes never expire. Security found five-week-old tokens on a
shared laptop that still work. I want sessions to time out.
```

The agent recommends a track and says why: here, **full**, because this changes
security behaviour for every request. It then runs:

```bash
S new idle-session-timeout --title "Idle session timeout"
```

### 4.2 Ideate → `hld.md`

The agent asks **one question at a time** and pushes back on weak points.
Expect questions like these:

```text
Agent: Before choosing a timeout: what is the company's screen-lock policy? If laptops
       lock after 30 minutes but sessions live for 8 hours, the lock is the weaker control.
You:   30 minutes. Security confirmed they want the same.
Agent: Then an idle timeout alone still lets an always-busy token live for weeks if a script
       replays it. Do you also want an absolute lifetime? I'd suggest 12 hours (one working day).
You:   Yes, 12 hours.
```

Decisions go straight into the ledger:

```bash
S ledger idle-session-timeout --kind decision "Idle timeout is 30 minutes ... Absolute lifetime 12 hours."
```

When the shape is clear, the agent writes `hld.md` (problem, goals, non-goals,
success measures, alternatives, risks) and runs `S check idle-session-timeout hld`.
For a risky idea, it offers a goldfish **lens review** (cost, security,
migration and so on) before you agree.

You say "HLD looks right", and the agent runs:

```bash
S phase idle-session-timeout propose
```

Result: [`hld.md`](../examples/acme-notes/specmaker/changes/idle-session-timeout/hld.md)

### 4.3 Propose → LLD, specs, ADRs

```text
@specmaker-propose
```

The agent works in this order:

1. **Section plan:** which capabilities get specs (here, modify `SESS-02` and
   add `SESS-03`), which decisions need ADRs, and whether contracts are needed.
   You confirm the plan.
2. **ADRs first:** for example, server-side records versus self-expiring
   tokens. It lays out the options against drivers, recommends one, and you
   choose. See [`adrs/`](../examples/acme-notes/specmaker/changes/idle-session-timeout/adrs/).
3. **LLD section by section**, pausing for your go-ahead. This includes exact
   values (30 minutes, inclusive bounds), reason codes, Implementation Phases
   and the File Boundary.
4. **Delta specs**, one capability at a time:

```markdown
## MODIFIED Requirements

### Requirement: [SESS-02] Session validity
The system SHALL accept a session token only until the user signs out or the session has
been idle for 30 minutes, and every accepted request SHALL restart the idle period.

#### Scenario: [SESS-02.3] Idle session expires
- **GIVEN** a user whose last request was 30 minutes ago or more
- **WHEN** a request arrives with their token
- **THEN** it is rejected with 401 and reason `session_expired`
```

5. **Self-consistency pass**, then `S check idle-session-timeout design` and
   `S phase idle-session-timeout accredit`.

Results: [`lld.md`](../examples/acme-notes/specmaker/changes/idle-session-timeout/lld.md),
[`specs/`](../examples/acme-notes/specmaker/changes/idle-session-timeout/specs/identity/session/spec.md)

### 4.4 Accredit → reviews, verdict, lock

```text
@specmaker-accredit
```

1. The agent proposes a review preset and says what it costs:
   "standard = 5 reviewers. This change is about 60 lines; I suggest quick plus
   comprehension (3 reviewers)."
2. It spawns **fresh-context reviewers** (goldfish). They see only the files, the
   ledger and the charter, never your conversation. Reports land in
   `reviews/accredit-r1-<lens>.md`.
3. It walks you through each Blocker or Major, one at a time (see
   [§9](#9-handle-review-findings)).
4. It writes `accreditation.md` with a recommended verdict, then asks you:

```text
Agent: Do you approve this design? Reply approved, conditional (with conditions), or
       rejected, and the name to record as approver.
You:   approved, Alex Chen
Agent: Human gates are set to "terminal", so please record it yourself. In your terminal, run:
           python3 .agents/skills/specmaker/scripts/specmaker.py accredit idle-session-timeout --verdict approved
       and tell me when it's done.
```

You run the command in **your own terminal** and type your name when asked:

```text
HUMAN GATE: record verdict 'APPROVED' for design of change 'idle-session-timeout'
Type your full name to confirm (empty to cancel): Alex Chen
idle-session-timeout: verdict APPROVED recorded for Alex Chen (via terminal)
locked 5 design file(s). Any later edit breaks the lock and requires `amend`.
```

Then the agent confirms with `S status` and runs
`S phase idle-session-timeout scrum`.

**Why the terminal step?** In testing, an agent that could not ask its question
(a non-interactive OpenCode run) approved the design itself, using the name in
`project.md`'s Approvers list. With `Human gates: terminal` (the default in
`project.md`), the script records verdicts and sign-offs only when someone types
a name at an interactive terminal. Agent shell tools have no terminal, so no
model can approve on its own. If you prefer speed and trust your model, set
`- Human gates: chat`. The agent then records the decision with
`--by "<your name>"` after you state it in chat. Every record shows how it
was made (`via terminal` or `via chat`).

Results: [`reviews/`](../examples/acme-notes/specmaker/changes/idle-session-timeout/reviews/),
[`accreditation.md`](../examples/acme-notes/specmaker/changes/idle-session-timeout/accreditation.md),
[`ledger.md`](../examples/acme-notes/specmaker/changes/idle-session-timeout/ledger.md)

### 4.5 Scrum → `backlog.md`

```text
@specmaker-scrum sprints are 2 days, capacity about 5 points
```

The agent turns the LLD phases into epics, features and stories. Each story
lists the scenario IDs it **covers**, and each task lists its **files**:

```markdown
#### S1 - As a team member, I want idle sessions to end, so that a token left on a shared laptop stops working
- **Covers**: SESS-02.1, SESS-02.2, SESS-02.3
- **Points**: 5
- **Priority**: Must
- **Depends**: S3
- [ ] T1.1 Write failing tests for SESS-02.1, SESS-02.2, SESS-02.3 - files: tests/test_session.py
- [ ] T1.2 Add `created_at`/`last_seen` ...; implement idle check ... - files: src/notes/session.py

## Sprint Plan

| Sprint | Goal | Stories | Points |
|---|---|---|---|
| 1 | Idle sessions expire; active ones keep working | S3, S1 | 6 |
| 2 | No session outlives 12 hours | S2 | 2 |
```

`S check idle-session-timeout backlog` refuses a backlog that:

- leaves a scenario uncovered
- has a task without files
- has a dependency cycle, or a dependency planned in a later sprint

Then the agent runs `S phase idle-session-timeout sprint`.

Result: [`backlog.md`](../examples/acme-notes/specmaker/changes/idle-session-timeout/backlog.md)

### 4.6 Sprint → code, evidence, sign-off

```text
@specmaker-sprint start sprint 1
```

```bash
S sprint-start idle-session-timeout 1    # records the git base commit
```

For each story, the agent:

1. writes failing tests named with scenario IDs
2. implements the code
3. runs the tests
4. ticks the tasks
5. logs progress in `sprints/sprint-01.md`

It changes only the files the tasks name. Anything else is a recorded
deviation (see [§13](#13-handle-a-deviation-or-change-an-approved-design)).

Then it collects evidence:

```bash
S gates idle-session-timeout 1                                      # runs project.md Quality Gates
S trace idle-session-timeout --out reviews/sprint-01-trace.md       # scenario -> story -> test
```

A **fresh-context verifier** compares the specs with the diff and the tests, and
writes `reviews/sprint-01-verification.md`, ending with `Verdict: PASS`. Then the
agent asks you:

```text
Agent: Do you sign off sprint 1? Reply yes with the name to record, or tell me what is missing.
You:   yes, Alex Chen
Agent: Please run in your terminal:
           python3 /…/specmaker.py signoff idle-session-timeout 1
```

As with the verdict, you run it and type your name. In `chat` mode the agent
runs `S signoff idle-session-timeout 1 --by "Alex Chen"` itself.

The sign-off is refused if:

- a task is open, or a deviation is unresolved
- the gates failed, or ran on a different commit
- the verifier said FAIL
- the design lock is broken
- a file outside the boundary changed without being recorded
- a covered scenario has no test

Results: [`sprints/`](../examples/acme-notes/specmaker/changes/idle-session-timeout/sprints/),
[`sprint-01-gates.json`](../examples/acme-notes/specmaker/changes/idle-session-timeout/reviews/sprint-01-gates.json),
[`sprint-01-trace.md`](../examples/acme-notes/specmaker/changes/idle-session-timeout/reviews/sprint-01-trace.md)

### 4.7 Retro → lessons, merge, archive

```text
@specmaker-retro
```

The agent:

1. gathers metrics (points, review findings, deviations, gate failures)
2. asks what helped and what hurt
3. proposes exact `project.md` rule edits for you to accept
4. runs `S phase idle-session-timeout retro`, then

```bash
S archive idle-session-timeout --dry-run
# modify  [SESS-02] in identity/session
# add     [SESS-03] -> identity/session
# adr     adrs/0001-server-side-session-records.md -> adrs/0001-server-side-session-records.md
S archive idle-session-timeout
```

The merge matches by requirement ID, then re-reads the result to verify it. The
ADRs move to the project-wide `specmaker/adrs/`, and the change folder moves to
`specmaker/archive/2026-11-24-idle-session-timeout/`.

Result: [`retro.md`](../examples/acme-notes/specmaker/changes/idle-session-timeout/retro.md)

## 5. Small change (lite track)

```text
@specmaker Add a "copy link" button to notes. Small change, one component.
```

The agent recommends **lite** and runs `S new copy-note-link --track lite`.
Differences from the full track:

| Full | Lite |
|---|---|
| ideate → `hld.md` | skipped; a few questions are captured in LLD §1 |
| LLD: 11 required sections | 4 required: Architecture, Interfaces, Test Strategy, File Boundary |
| standard review preset | quick preset (consistency + readiness) |
| epics → features → stories | a flat list of stories is fine |
| files on every task (error) | files strongly encouraged (warning) |

Everything else is unchanged: specs with IDs, a human verdict, gates, a verifier
and a human sign-off.

## 6. Tiny fix (skip specmaker)

```text
@specmaker typo in the sign-in error message
```

The agent should tell you this does not need a change folder and just fix it.
If the fix changes behaviour a living spec describes, the agent says which
requirement and opens a lite change instead. Living specs are only edited
through `archive`.

## 7. Adopt specmaker in an existing codebase

Don't try to spec the whole system at once. Start with the area you are about to
change.

```text
@specmaker we want to start using specmaker. First capture how sessions work today.
```

The agent:

1. runs `S init` and fills `project.md` from what it can see (CI config, test
   command, stack), asking about anything it cannot verify
2. runs `S new baseline-session --track lite`, then
   `S set baseline-session docs_only true`
3. writes ADDED requirements that describe **current** behaviour, citing code in
   comments:

```markdown
### Requirement: [SESS-02] Session validity
The system SHALL accept a session token until the user signs out.
<!-- code:src/notes/session.py:41 -->
```

4. writes a short LLD (`File Boundary: none (documentation only)`), runs a
   quick-preset accredit, and you confirm "yes, that is really how it behaves"
5. goes straight from accredit to retro (`S phase baseline-session retro`),
   then archives

Now `specmaker/specs/identity/session/spec.md` exists, and the next real change
can MODIFY it. The example's living spec was made this way.

## 8. Resume after a break or in a new session

Everything lives in files, so a fresh session can pick up where the last one
stopped:

```text
@specmaker where are we?
```

```bash
S status
# idle-session-timeout - Idle session timeout
#   track full, phase SPRINT
#   accreditation: approved by Alex Chen at 2026-11-06T...
#   backlog: 2/3 stories, 4/6 tasks, 2 sprint(s) planned
#   sprint 1: signed-off by Alex Chen
#   sprint 2: active
#   next: Continue sprint 2 (skill: specmaker-sprint); finish with `signoff idle-session-timeout 2`.
```

The agent also reads `ledger.md`, so it knows what was decided. A half-written
HLD keeps its open questions as `- [ ]` items, and the next session starts from
those.

## 9. Handle review findings

Every finding must cite **evidence**: `doc:`, `code:`, `absent:`, or it is
filed as a `question`. Questions never block. The agent goes through the
Blockers and Majors one at a time, with a recommendation for each:

```text
Agent: Finding 1 of 1 (Major, raised by comprehension and consistency):
       "When both limits pass, the client gets session_lifetime_exceeded, but only the
       LLD says so." Evidence: doc:lld.md#5.
       Options: FIX (add a scenario to SESS-03), CONTEST, DECLINE (accept the trade-off), ESCALATE.
       I'd FIX it: reason codes are part of the client contract (goal G3).
You:   Decline. Clients do the same thing for both codes.
```

```bash
S ledger idle-session-timeout --kind declined \
  --ref "accredit-r1-comprehension#G1, accredit-r1-consistency#G1" \
  "Precedence stays an LLD detail: both reasons trigger the same client action."
```

Declined and decided items are in the ledger, and every reviewer reads the
ledger, so the next round won't re-raise them. A re-review runs only the lenses
that raised Blockers or Majors, and only on the changed sections. Reviews stop
after the round cap (default 2 re-review rounds). Anything left is listed in
`accreditation.md` for you to accept or reject.

## 10. Control review cost and reviewer model

| Preset | Reviewers | Typical use |
|---|---|---|
| quick | consistency, readiness | lite track, docs-only baselines |
| standard | zoom-out, comprehension, critic, consistency, readiness | most full-track changes |
| deep | standard + security + codebase | auth, payments, personal data, migrations, public APIs |

Set the default in `project.md`:

```markdown
## Review Policy
- Default preset: standard
- Lite track preset: quick
- Max re-review rounds: 2
- Reviewer model: a different model family from the drafting model, when available
```

Override it for one change by saying so: "use the deep preset for this one". The
agent always states the reviewer count before dispatching.

**Different reviewer model in OpenCode (optional).** Define a subagent and tell
specmaker to use it. Create `.opencode/agents/goldfish.md`:

```markdown
---
description: Fresh-context specmaker reviewer. Reads only the files it is given and writes one report.
mode: subagent
model: <provider>/<model>
---
You are a goldfish reviewer. Follow the persona and rules files named in your prompt exactly.
```

Then add this line to `project.md` under Review Policy:
`- Reviewer agent: goldfish`. OpenCode's permission syntax differs between
versions, so check its agents documentation before adding edit or shell
restrictions. The verifier needs read-only shell access for `git diff`.

## 11. Review without subagents (cold-read mode)

If your agent cannot spawn subagents, or the isolation probe finds that a
"fresh" reviewer can see your chat, the agent will not review the design in its
own context. Instead it writes the reviewer prompt to a file and asks you to run
it in a new session:

```text
Agent: I can't run an isolated reviewer here. Open a NEW session in this project and send:
       Run the goldfish prompt in specmaker/changes/idle-session-timeout/reviews/pending/accredit-r1-readiness.prompt.md
       Tell me when the report exists.
```

## 12. Tag tests with scenario IDs

The trace and the sign-off look for the scenario ID text (for example
`SESS-02.3`) anywhere in test files. Name the test after the ID **and** put the
dotted form in a comment, docstring or title.

Files count as tests when:

- their path contains `test/`, `tests/`, `__tests__/`, `spec/`, `specs/`,
  `e2e/` or `integration/`, or
- their name matches `test_*`, `*.test.*`, `*_test.*`, `*.spec.*` or
  `*Test.*`, or
- they are `.feature` files.

```python
def test_idle_session_expires__SESS_02_3(self):
    """covers: SESS-02.3"""
```

```ts
// vitest / jest
it("SESS-02.3 idle session expires", () => { /* ... */ });
```

```java
@Test
@DisplayName("SESS-02.3 idle session expires")
void idleSessionExpires() { }
```

```go
// covers: SESS-02.3
func TestIdleSessionExpires_SESS_02_3(t *testing.T) { }
```

```gherkin
@SESS-02.3
Scenario: Idle session expires
```

Check the result at any time:

```bash
S trace idle-session-timeout              # this change's scenarios
S coverage --capability identity/session  # all living scenarios
```

## 13. Handle a deviation, or change an approved design

**During a sprint, a file outside the plan must change** (for example, a shared
fixture). The agent adds it under `## Deviations` in the sprint file before
editing it:

```markdown
## Deviations
- [x] tests/conftest.py - shared FakeClock fixture also used by test_notes.py (L-007)
```

If an undeclared file changed, sign-off fails:

```text
ERROR   boundary: src/unplanned.py changed but is outside the sprint's task files; revert it
        or record it under '## Deviations' in sprints/sprint-01.md
```

**The build needs a design decision the LLD did not make.**

- If it is invisible from outside (a private helper's name, the order of internal
  steps), the agent decides and records it as `- [x]`.
- If anything is observable, or it contradicts the LLD, an ADR or a spec, the
  agent stops, records `- [ ] <question>`, and asks you. An open `- [ ]`
  deviation blocks sign-off.

**The design itself must change.** Editing a locked file is detected
immediately:

```text
LOCK BROKEN - design changed after accreditation: lld.md (modified)
```

Reopen the design on purpose:

```text
@specmaker the 12-hour lifetime must be configurable per team. Amend the design.
```

```bash
S amend idle-session-timeout --reason "lifetime configurable per team (support request)"
# phase -> propose; old accreditation kept in history; active sprint marked interrupted
```

Propose updates only what is needed. Accredit re-reviews only the changed
sections. Then scrum and the sprints continue. Sprints that are already signed
off stay signed off.

## 14. Human-only tasks

Some tasks need a person: creating a vendor account, rotating a credential, or a
manual accessibility check. Mark them in the backlog:

```markdown
- [ ] T4.3 Create the SSO app registration in the IdP console - files: docs/sso-setup.md - owner: human
```

The agent never ticks these. It asks you to do the task and tick it.

## 15. Export the backlog to Jira, GitHub or Linear

```bash
S export idle-session-timeout --format csv > backlog.csv
```

```text
id,type,title,parent,points,priority,sprint,covers,depends,status,change
E1,Epic,Sessions end when they should,,,,,,,,idle-session-timeout
F1,Feature,Idle expiry,E1,,,,,,,idle-session-timeout
S1,Story,"As a team member, I want idle sessions to end, so that a token left on a shared laptop stops working",F1,5,Must,1,SESS-02.1 SESS-02.2 SESS-02.3,S3,Done,idle-session-timeout
T1.1,Task,"Write failing tests for SESS-02.1, SESS-02.2, SESS-02.3 - files: tests/test_session.py",S1,,,1,,,Done,idle-session-timeout
```

Import the CSV with the tracker's own importer, mapping `parent` to the
epic/parent link. Use `--format json` for scripts. `backlog.md` stays the
source of truth.

## 16. Check specs against code (drift)

Run this when code may have changed outside specmaker: hotfixes, other teams, or
months later.

```text
@specmaker-retro check identity/session for drift
```

1. A cheap signal: `S coverage --capability identity/session` lists living
   scenarios that no test names.
2. The agent then reads each capability's spec and its code, one at a time, and
   writes `specmaker/drift-YYYY-MM-DD.md` listing only the differences, with
   `code:path:line` evidence.
3. For each difference, you decide: is the **code** wrong (fix it) or the
   **spec** outdated (open a lite or docs-only change)?

Living specs are never edited directly.

## 17. Two changes touching the same requirement

`S check <id> specs` warns you:

```text
WARN    specs/identity/session/spec.md: [SESS-02] is also touched by open change(s) other-change;
        agree an order (`set <id> depends_on ...`) before both are archived
```

Choose an order:

```bash
S set other-change depends_on idle-session-timeout
```

`archive other-change` is refused until `idle-session-timeout` is archived.
Afterwards it is refused again with **base drift**, because the requirement it
modifies changed underneath it. The agent then re-bases the delta on the
current living text, runs `amend`, and gets it re-accredited. Nothing is lost
silently.

## 18. Run specmaker checks in CI

The script needs only Python. Copy `skills/specmaker/scripts/specmaker.py` into
the repository (or use the installed skill) and add a job:

```yaml
# .github/workflows/specmaker.yml
name: specmaker
on: [pull_request]
jobs:
  specs:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - name: Lint active changes
        run: |
          S="python3 .agents/skills/specmaker/scripts/specmaker.py"
          for id in $($S list --json | python3 -c 'import json,sys;[print(c["id"]) for c in json.load(sys.stdin)]'); do
            $S check "$id"
            $S status "$id" | grep -q "LOCK BROKEN" && { echo "::error::$id design changed after accreditation"; exit 1; } || true
          done
      - name: Living scenarios have tests
        run: python3 .agents/skills/specmaker/scripts/specmaker.py coverage --strict
```

`check` fails on a design that is still a draft, for example an HLD in progress.
Run the job on the main branch, or let work-in-progress designs live on their
own branches until they pass. Start without `--strict` on `coverage` if you are
adopting specmaker gradually.

## 19. Autopilot mode

In `project.md`:

```markdown
## Autonomy
- Mode: autopilot
```

The agent then advances through phase gates on its own whenever the script's
checks pass: ideate → propose, propose → accredit, scrum → sprint, and from one
sprint to the next. It still stops for the two **human gates**, the
accreditation verdict and each sprint sign-off. Keep `Human gates: terminal`
with autopilot, so the stop does not depend on the model obeying the rule.

**Non-interactive runs** (`opencode run`, CI): the agent cannot ask anything.
Specmaker skills tell it to record design assumptions in the ledger and carry
on within the phase. At any guided-mode phase gate, human gate, or
irreversible step, it ends the run with its question written out. Continue
with `opencode run -s <session-id> "<your answer>"`.

## 20. Troubleshooting

| Message | Meaning and fix |
|---|---|
| `no workspace found` | Run `S init` in the project root, or pass `--root path/to/specmaker` |
| `requirement header needs an ID` | Write `### Requirement: [AREA-01] Title`. IDs are required |
| `still uses the template prefix AREA` | Replace `AREA` with the capability's prefix from `project.md` Spec Areas |
| `ADDED [X-01] already exists in living spec` | Use MODIFIED for existing behaviour, or pick a new ID |
| `scenario X has an empty **THEN** step` | Fill in every step; template comments do not count |
| `section 'data model' is empty` | Write content, or `N/A - <reason>` if it does not apply |
| `scenario ... is not covered by any story` | Add the ID to a story's `**Covers**` |
| `task has no 'files:' boundary` | End the task line with `- files: path/a, path/b` |
| `design changed after accreditation` | Undo the edit, or `S amend` to reopen the design on purpose |
| `gates ran at <sha> but HEAD is <sha>` | Commit, then run `S gates <id> N` again |
| `this is a human gate, and project.md sets 'Human gates: terminal'` (exit 3) | Working as intended: run the printed command yourself in an interactive terminal. Agents must not retry it |
| `no gate run recorded` | Run `S gates <id> N` before sign-off |
| `<file> changed but is outside the sprint's task files` | Revert it, or record it under `## Deviations` |
| `scenarios with no test referencing their ID` | Add tests named with the IDs (§12), or the human accepts with `--accept-gaps "reason"` |
| `living [X-01] changed since accreditation` | Another change was archived first; re-base the delta, `amend`, re-accredit |
| Skills don't trigger | Check they are side by side in a scanned folder (§1); name them explicitly (`@specmaker`) |
| Agent says it cannot find `scripts/specmaker.py` | Install to a standard location (§1), or set `SPECMAKER_HOME` to the installed `specmaker` skill folder before starting the agent |

## 21. Command reference

Every command accepts `--root <dir>` (default: the nearest `specmaker/`
containing `project.md`, or `$SPECMAKER_ROOT`).

| Command | Example | Notes |
|---|---|---|
| `init` | `S init` | Idempotent; never overwrites `project.md` |
| `new` | `S new add-sso --track lite --title "Add SSO"` | Full starts at ideate, lite at propose |
| `list` | `S list --json` | Active changes, plus the latest archived |
| `status` | `S status add-sso --json` | Phase, artifacts, lock, sprints, **next step** |
| `check` | `S check add-sso specs backlog` | `hld lld specs adrs design backlog sprint:N`, or nothing for automatic; exit 1 on errors |
| `set` | `S set add-sso depends_on other` | Keys: `skip_specs`, `docs_only`, `title`, `track`, `depends_on` |
| `phase` | `S phase add-sso accredit` | One step forward, only if the entry gate passes |
| `ledger` | `S ledger add-sso --kind declined --ref r1-critic#G2 "reason"` | Kinds: decision, declined, question, answer, deviation, condition, note. No text prints the ledger |
| `accredit` | `S accredit add-sso --verdict conditional --condition "add audit log"` | Human verdict; locks the design. `terminal` mode: run it yourself and type your name. `chat` mode: the agent adds `--by "<name>"` |
| `amend` | `S amend add-sso --reason "..."` | Back to propose; needs re-accreditation |
| `sprint-start` | `S sprint-start add-sso 2` | Previous sprints must be signed off; records the git base |
| `gates` | `S gates add-sso 2 --timeout 900` | Runs `project.md` Quality Gates; writes `reviews/sprint-NN-gates.json` |
| `trace` | `S trace add-sso --out reviews/trace.md --strict` | Scenario → story → test matrix |
| `signoff` | `S signoff add-sso 2` | Human sign-off; re-checks all evidence; same terminal and chat rules as `accredit` |
| `export` | `S export add-sso --format csv` | Backlog for trackers |
| `coverage` | `S coverage --capability billing --strict` | Living-scenario test coverage |
| `spec` | `S spec` · `S spec SESS-02` | Inventory, or one requirement's text |
| `archive` | `S archive add-sso --dry-run` | Merge, verify, promote ADRs, move to `archive/` |
