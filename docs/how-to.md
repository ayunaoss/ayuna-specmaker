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
- [13. Handle deviations and change requests](#13-handle-deviations-and-change-requests)
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
skills.

**Requirements:**

- Linux, macOS or WSL2
- Python 3.8+ for the helper script
- **OpenSSH 8.1+** (`ssh-keygen -Y`), which signs and verifies human approvals.
  macOS ships it; on Linux and WSL2 install `openssh-client`. The installer
  refuses to continue without it.
- Git, strongly recommended (sprint evidence and rewind use it)

Install **all seven**: every phase skill needs the core
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

- Without `--skill '*'` the CLI asks which skills to install. Pick the seven
  core skills, plus the optional `specmaker-monorepo` only if you work in an
  Nx polyglot monorepo. `--skill '*'` installs all eight.
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

### 1c. As a Codex plugin

The repository is a Codex plugin (`.codex-plugin/plugin.json`) and a
one-plugin marketplace (`.agents/plugins/marketplace.json`):

```bash
codex plugin marketplace add ayunaoss/ayuna-specmaker
```

Then install `specmaker` from the `ayuna` marketplace in the Codex plugin
browser, or enable it per project in `.codex/config.toml`:

```toml
[plugins."specmaker@ayuna"]
enabled = true
```

Codex also reads the plain skills in `.agents/skills/`, so 1a or 1e works
without the plugin.

### 1d. As an Antigravity plugin

The repository is an Antigravity plugin (`.antigravity-plugin/plugin.json`):

```bash
agy plugin install https://github.com/ayunaoss/ayuna-specmaker
```

From a clone, `agy plugin install ../ayuna-specmaker` works too. Antigravity
also reads `.agents/skills/` in the workspace, and `~/.gemini/config/skills/`
globally (1e, `--agent antigravity --global`).

### 1e. From a clone, with install.sh (no Node needed)

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

```bash
../ayuna-specmaker/install.sh --agent antigravity --global  # -> ~/.gemini/config/skills/
```

Useful options:

| Option | Effect |
|---|---|
| `--link` | Symlink instead of copying, so `git pull` in the specmaker repo updates you |
| `--explicit-only` | The agent loads specmaker skills only when you name them; they never auto-trigger. In Claude Code this also stops the core skill from loading a phase skill for you, so name each phase yourself (`/specmaker-propose` and so on) |
| `--with-monorepo` | Also install the optional `specmaker-monorepo` companion skill (Nx polyglot monorepos with ayuna-nxtools) |
| `--dry-run` | Show what would be installed |
| `--uninstall` | Remove the seven skill folders from the target |

Check the result, whichever way you installed:

```bash
python3 .agents/skills/specmaker/scripts/specmaker.py doctor
```

```text
PASS  python        3.12.3
PASS  openssh       9.6
PASS  git           found
PASS  install       script 0.1.0 at /home/alex/shop/.agents/skills/specmaker
WARN  copies        /home/alex/.claude/skills/specmaker is version 0.0.9; an agent may load it instead of 0.1.0: update or remove it
WARN  workspace     no specmaker/project.md here: run `init` in the project root
...
0 failure(s), 2 warning(s)
```

`doctor` checks the requirements, that all seven skills sit side by side at
one version, and other installed copies an agent might load instead. After
`init` it also checks the workspace: approvers for signed gates, the
`AGENTS.md`/`CLAUDE.md` block, and the Quality Gates placeholder. It exits 1 on
any FAIL.

The skills must stay **side by side** in the same folder. The phase skills reach
the shared script and references through the `specmaker` folder next to them.

Some harnesses, OpenCode 2.x included, hand a skill's text to the agent without
saying where its folder is. Each specmaker skill therefore starts with a short
command that looks in these standard locations, in order:

- `$SPECMAKER_HOME`
- the project's `.opencode/skills`, `.agents/skills` or `.claude/skills`
- the global `~/.config/opencode/skills`, `~/.agents/skills`,
  `~/.claude/skills` or `~/.gemini/config/skills`
- plugin installs: Claude Code, Codex and Antigravity plugin folders

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
project also has a `CLAUDE.md`, the block is written to both files: Claude Code
reads `AGENTS.md` only when there is no `CLAUDE.md`.
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

**Register approvers.** Human decisions are SSH-signed by default
(`Human gates: signed`). Each person who may approve designs, sign off
sprints, decide change requests or authorise rewinds registers a public key
once:

```bash
S approvers add --principal alex@example.com --key ~/.ssh/id_ed25519_sk.pub
```

Use a **hardware-backed key** where you can (`ssh-keygen -t ed25519-sk`). The
agent may be able to read a normal key file, or use your SSH agent; a
hardware key needs a physical touch for every signature. Then check where the
signer list lives, and protect it:

```bash
S approvers check
```

```text
OpenSSH: 10.0 (need 8.1+)
search order: /etc/specmaker/allowed_signers, /home/alex/.config/specmaker/allowed_signers
allowed signers: /home/alex/.config/specmaker/allowed_signers  [USER-WRITABLE (...)]
  alex@example.com                 sk-ssh-ed25519@openssh.com   hardware-backed
protect it: sudo install -d -m 755 /etc/specmaker && sudo install -m 644 ... /etc/specmaker/allowed_signers
```

A signer list your user can write is a list an agent running as you could add
its own key to. `/etc/specmaker/allowed_signers`, owned by root, is the
protected location. CI should verify against its own copy (§18).
`SPECMAKER_ALLOWED_SIGNERS` overrides the search, and
`SPECMAKER_SIGNING_KEY` (or `git config user.signingkey`) selects the private
key used to sign.

Also fill in **Spec Areas** (one requirement-ID prefix per capability, such as
`- SESS: identity/session`), **Review Policy** and **Approvers**. See the filled
example: [`examples/acme-notes/specmaker/project.md`](../examples/acme-notes/specmaker/project.md).

Commit `specmaker/`. It is meant to live in the repository next to the code.

**Naming.** Every phase names things by the specmaker naming guide,
[`skills/specmaker/references/naming.md`](../skills/specmaker/references/naming.md):

- English names, in each language's standard casing
- short, descriptive names without abbreviations
- no repeating the surrounding context
- names that state their result
- functions named `action + context` (`getUserMessages`, `get_user_messages`)
- singular and plural matched

It has a casing table and examples for TypeScript, Python, Go, Java, Kotlin,
C#, Rust, Swift, C++, Ruby, PHP and SQL. Your repository's own rules win. List
the exceptions under `project.md` → Conventions:

```markdown
## Conventions

- Database columns stay camelCase (legacy schema shared with the billing service).
- React components use PascalCase file names (`UserCard.tsx`).
```

The LLD fixes every new public name, and the sprint uses those names exactly.
The critic reviewer and the sprint verifier flag naming breaks as Nit, or as
Major when a public API or contract is affected.

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
       rejected, and the approver identity to sign with.
You:   approved, alex@example.com
Agent: Human gates are "signed", so please sign it yourself. In your terminal, run:
           python3 .agents/skills/specmaker/scripts/specmaker.py accredit idle-session-timeout --verdict approved --by alex@example.com
       and tell me when it's done.
```

You run the command in **your own terminal**. Touch your security key when it
blinks:

```text
HUMAN GATE (signed): record verdict 'APPROVED' for design of change 'idle-session-timeout'
Signing approvals/001-accredit.json as alex@example.com with /home/alex/.ssh/id_ed25519_sk (touch your security key if it blinks)...
idle-session-timeout: verdict APPROVED recorded for alex@example.com (via signed)
locked 5 design file(s). Any later edit breaks the lock and requires `amend`.
```

`approvals/001-accredit.json` states exactly what you approved:

- the change
- the verdict and its conditions
- a digest of the locked design files
- your identity and the time

`001-accredit.json.sig` is your signature over that statement. Every later
gate verifies it before trusting the verdict. So does `S status`, and so does
CI (§18).

Statements form a **chain**. Each one carries a sequence number, the hash of
the previous statement, the change's unique ID and the repository's identity.
The script checks the following:

- The chain has no gaps.
- Every statement is signed by the approver it names.
- Every decision in `change.json` matches its statement field for field.
- Every statement belongs to a decision.
- Decisions still mean what was signed:
  - A verdict still matches the locked design.
  - A sprint sign-off still matches its gate record, its verifier report and
    the approved requirements it covered.
  - The sprint has not been rewound since its sign-off.
  - A request's status follows from its signed decision.

So editing `change.json`, removing or reordering a statement, copying one in
from another change, or restoring an old sign-off after a rewind is reported
as an error. Then the agent confirms with
`S status` and runs `S phase idle-session-timeout scrum`.

**Why signatures?** In testing, an agent that could not ask its question (a
non-interactive OpenCode run) approved the design itself, using the name in
`project.md`'s Approvers list. Asking for a typed name at a terminal doesn't
fix that, because any program running under your account can fake a terminal.
Running inside a sandbox doesn't fix it either: fake terminals work inside
sandboxes, and the approval record lives in the project folder the agent may
write. What an agent cannot produce is a signature from a key it can't use.

The same applies to all human gates: the verdict, sprint sign-offs,
change-request decisions (`cr decide`), discarding code (`rewind`), and
amendments that need approval (`--over-budget`, `--wording-only`).

| `Human gates:` | What a decision needs | Can an agent fake it? |
|---|---|---|
| `signed` (default) | An SSH signature from a key in the allowed signers file, over a statement of exactly what is approved | Not with a hardware key (needs a touch). With a software key, only if the agent can read the key or use your SSH agent. In CI against a signer list the agent can't change: no |
| `terminal` | A name typed at an interactive terminal | Yes, with a fake terminal. Each record notes its terminal and parent processes, and `status` warns when one came from inside an agent |
| `chat` | `--by "<name>"`, recorded by the agent after you say so | Yes; it relies on the model obeying |

**Where enforcement happens.** On your machine the agent can edit files, so
local checks catch mistakes and detect tampering, but a determined agent
could also edit the signer list if your user can write it. Protect it
(§3), and let **CI be the place that enforces**: `verify --require-signed`,
run against a signer list that lives in CI configuration.

**Changing modes.** If the `Human gates` line is missing or unreadable, the
script uses `signed`. Each change keeps the mode it was created with, and the
stricter of that and `project.md` applies. Loosening an existing change
(`S set <id> human_gates terminal|chat`) is itself a human gate, signed in
signed mode. Every record shows how it was made (`via signed`,
`via terminal` or `via chat`).

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

- isn't a complete tree: an epic with no features, a feature with no stories,
  or a story with no tasks
- leaves a scenario uncovered
- has a task without files
- has a dependency cycle, or a dependency planned in a later sprint

**Approving the plan starts implementation.** Nothing is built until a person
approves the complete tree and the sprint plan. This is a human gate, like the
design verdict, and is signed in signed mode:

```bash
S phase idle-session-timeout sprint
# ERROR   plan: the backlog and sprint plan are not approved: a person runs `approve-plan idle-session-timeout`
S approve-plan idle-session-timeout --by alex@example.com      # you run this, as with accredit
# idle-session-timeout: plan approved by alex@example.com (via signed)
S phase idle-session-timeout sprint
```

`project.md` → `Plan approval: full | all | off` controls this:

- `full` (default): required on the full track
- `all`: required on every change
- `off`: never required

Ticking tasks doesn't count as a plan change. Adding, removing or editing
stories, tasks or the sprint plan does: the next `sprint-start` then asks for a
new `approve-plan`.

Result: [`backlog.md`](../examples/acme-notes/specmaker/changes/idle-session-timeout/backlog.md)

### 4.6 Sprint → code, evidence, sign-off

```text
@specmaker-sprint start sprint 1
```

```bash
S sprint-start idle-session-timeout 1    # records the git base commit
```

`sprint-start` refuses if any code outside `specmaker/` changed since the last
checkpoint (design approval, a sprint sign-off or a rewind), committed or not.
Code written before its sprint is unplanned work:

```text
specmaker: code outside specmaker/ changed since the last checkpoint (design approval, 34a5171959), before implementation was allowed to start:
  src/session.py
Revert it (or commit/stash unrelated work elsewhere), or a person accepts it: `sprint-start idle-session-timeout 1 --accept-prior "<reason>"` (a human gate).
```

For each story, the agent:

1. writes failing tests named with scenario IDs
2. implements the code
3. runs the tests
4. ticks the tasks
5. logs progress in `sprints/sprint-01.md`

It changes only the files the tasks name. Anything else is a recorded
deviation (see [§13](#13-handle-deviations-and-change-requests)).

Then it collects evidence:

```bash
S gates idle-session-timeout 1                                      # runs project.md Quality Gates
S trace idle-session-timeout --out reviews/sprint-01-trace.md       # scenario -> story -> test
```

A **fresh-context verifier** compares the specs with the diff and the tests, and
writes `reviews/sprint-01-verification.md`, ending with `Verdict: PASS`. Then the
agent asks you:

```text
Agent: Do you sign off sprint 1? Reply yes with your approver identity, or tell me what is missing.
You:   yes, alex@example.com
Agent: Please run in your terminal:
           python3 .agents/skills/specmaker/scripts/specmaker.py signoff idle-session-timeout 1 --by alex@example.com
```

As with the verdict, you run it and touch your key. The signed statement binds
the sprint run, the digest of the gate record, and the verifier report's name
and digest. Re-running gates or replacing the report after you sign is
detected. In `terminal` mode you type your name instead; in `chat` mode the
agent runs the command with `--by` itself.

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
# adr     adrs/0002-inject-the-clock.md -> adrs/0002-inject-the-clock.md
# dry run: nothing written
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
#   track full, phase SPRINT, human gates: terminal
#   artifacts: hld.md, lld.md, accreditation.md, backlog.md, retro.md (missing), 1 delta spec(s), 2 ADR(s), 4 review(s)
#   accreditation: approved by Alex Chen at 2026-11-06T... (via terminal)
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

A Blocker is never declined. `accredit` refuses a verdict while a Blocker in
a lens's latest report has no later round and no ledger entry that contests or
escalates it (`--kind contested` or `escalated`), or makes it a condition of a `conditional`
verdict (`--kind condition`). The ledger is append-only, so the latest
entry for a finding stands. It also refuses incomplete reports (no
`Verdict:` line or no `## Findings`), and a report whose verdict disagrees
with its findings (FAIL without a Blocker, or a Blocker without FAIL).

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

Before the first review in a session, the agent checks that its subagents
really start fresh:

```bash
S doctor --isolation start
```

This prints a random canary (now in the agent's context) and a probe prompt
without it. The agent sends the prompt to one fresh subagent, which writes
what it can see to a file. Then:

```bash
S doctor --isolation check
```

```text
isolation: partial (instruction files visible: AGENTS.md)
Write it into each report header: Isolation: partial
```

If the probe repeats the canary, it sees the parent conversation: the result
is `NONE` (exit 1), and reviews use cold-read mode. Only the canary's hash is
stored, outside the repository, so a reviewer reading files cannot find it.

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

## 13. Handle deviations and change requests

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

### Change requests: when someone asks for something different

Requests that arrive mid-implementation and edit the specs straight away are
the main reason spec-driven projects drift. Specmaker handles them in four
steps: **record**, **freeze**, **batch**, and **apply deliberately**. The full
strategy is in
[`skills/specmaker/references/change-requests.md`](../skills/specmaker/references/change-requests.md).

**1. Record it.** It is parked, and nothing else changes.

```text
You:   Support says night-shift teams get signed out mid-shift. The 12-hour lifetime should be
       configurable per team.
Agent: Recorded as CR-001 (parked). Sprint 2 is active and frozen, so it will be triaged with
       the other requests at the sprint boundary. Continuing with T2.2.
```

```bash
S cr add idle-session-timeout --title "Lifetime configurable per team" --by "Support (Priya)" \
  --reason "Night-shift teams get signed out mid-shift"
# CR-001 recorded as PARKED: requests/CR-001.md
# sprint 2 is active and frozen: this request waits for the sprint boundary. Keep building.
```

Mark a request `--blocker` only when continuing would build something known to
be wrong (a legal or security finding, or a spec that contradicts reality).
Blockers are triaged at once. Everything else waits. During a sprint, the
script refuses to accept a non-blocker into the backlog or design:

```text
specmaker: sprint 2 is active and the sprint freeze is on: CR-001 can only be rejected or deferred now.
```

**2. Triage together at the sprint boundary.** After sign-off, the agent goes
through all parked requests (`S cr list`). For each one it fills
`requests/CR-NNN.md`:

- goal fit
- the two questions: does it change observable behaviour, and is it needed
  for the current goals?
- the **class**:
  - 0: implementation detail
  - 1: plan change → backlog
  - 2: design change → amend
  - 3: new scope → defer to a new change
- impact, options, and a recommendation

```bash
S impact idle-session-timeout --reqs SESS-03
```

```text
| Requirement | Scenarios | Stories (sprint: status) | Files (from tasks) | Tests |
|---|---|---|---|---|
| SESS-03 | SESS-03.1 | S2 (S2: signed-off) | src/notes/session.py<br>tests/test_session.py | tests/test_session.py |

## Summary

- Changed requirements: SESS-03
- Signed-off sprints affected (reopen on re-approval): 2
- In-progress sprints affected: none
- Rewind candidate: `rewind idle-session-timeout --to sprint:2` discards all code since sprint 2 began
```

You decide each request: reject, defer, backlog or amend. Several requests
with the same outcome go in one command. Like an approval, this is a human
gate (in terminal mode you run it yourself):

```bash
S cr decide idle-session-timeout CR-001 --outcome amend --class 2 --reason "Serves G2; night shift exceeds 12h"
```

**3. Discard work the change makes wrong (optional).** `rewind` is a human
gate too.

| `--to` | Discards |
|---|---|
| `head` | uncommitted changes only |
| `sprint` | everything since the active or latest sprint started |
| `sprint:N` | everything since sprint N started |
| `change` | everything since the first sprint |

Files under `specmaker/` are never touched. Before discarding, the script
creates a backup branch `specmaker-backup/<change>/<timestamp>` and stashes
uncommitted work. It then records the revert as a **new commit**, so history
is not rewritten. Tasks of rewound sprints are unticked in `backlog.md`.

```bash
S rewind idle-session-timeout --to sprint:2 --cr CR-001
# rewound. Backup branch: specmaker-backup/idle-session-timeout/20261125-083000
# sprints 2 marked rewound; their tasks were unticked in backlog.md (L-008)
# undo the code (specmaker/ state is kept): `git checkout specmaker-backup/idle-session-timeout/20261125-083000 -- . ':(exclude)specmaker'`
```

Skip the rewind when existing code can be adapted. Re-approval reopens the
affected sprints anyway.

**4. Apply through the design, then re-approve.**

```bash
S amend idle-session-timeout --cr CR-001 --to propose --reason "CR-001: per-team lifetime"
```

- Use `--to ideate` when the request changes goals, scope or the solution's
  shape (HLD).
- Use `--to propose` for behaviour, interfaces or data inside the same shape
  (LLD and specs).

The agent then works through the usual phases:

1. Update only the affected design sections.
2. Run a goldfish re-review of just those sections.
3. Ask you for the verdict.

On re-approval the script compares the requirements with the snapshot taken
at `amend` time, and reopens the affected sprints:

```text
changed requirements since last approval: SESS-03
sprint 2 REOPENED: its stories cover changed scenarios SESS-03.1; re-run it (`sprint-start idle-session-timeout 2`) and sign it off again
```

Scrum re-plans the affected stories (`S impact idle-session-timeout` now shows
what changed since the snapshot). The reopened sprint runs again **before** any
later sprint. Its sign-off needs fresh gates and a new verifier round; the
script rejects evidence from the earlier run.

**Guard rails that keep noise down**

These are in `project.md` → Change Control:

| Setting | Default | Effect |
|---|---|---|
| `Sprint freeze` | `on` | Mid-sprint, only blockers can be accepted |
| `Max amendments per change` | `3` | Beyond it, `amend` needs `--over-budget "<reason>"`. Repeated amendments usually mean the HLD was wrong; consider a new change from ideate |

The script also blocks a few things outright:

- a new sprint while a request decided as `amend` is not yet applied
- retro while any request is still parked or unapplied
- an amendment after planning that doesn't name its requests (`--cr`)

Retro reports request counts by outcome and source, so you can see where the
churn comes from.

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

The first rows (epics and features come first, then each story followed by its tasks):

```text
id,type,title,parent,points,priority,sprint,covers,depends,status,change
E1,Epic,Sessions end when they should,,,,,,,,idle-session-timeout
F1,Feature,Idle expiry,E1,,,,,,,idle-session-timeout
F2,Feature,Absolute lifetime,E1,,,,,,,idle-session-timeout
S3,Enabler,Enabler: injectable UTC clock for the session store,F1,1,Must,1,,,Done,idle-session-timeout
T3.1,Task,Add `Clock` type and `utc_now()` - files: src/notes/clock.py,S3,,,1,,,Done,idle-session-timeout
...
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
        with: { fetch-depth: 0 }
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
      - name: Every human decision is validly signed
        env:
          ALLOWED_SIGNERS: ${{ vars.SPECMAKER_ALLOWED_SIGNERS }}   # repository variable, edited by admins only
        run: |
          printf '%s\n' "$ALLOWED_SIGNERS" > "$RUNNER_TEMP/allowed_signers"
          python3 .agents/skills/specmaker/scripts/specmaker.py verify --require-signed \
            --allowed-signers "$RUNNER_TEMP/allowed_signers" \
            --base "origin/${{ github.base_ref }}"   # add --require-hardware to insist on sk keys
```

`checkout` needs `fetch-depth: 0` so the base branch is available for
`--base`, which fails the job if a pull request deletes or edits any existing
approval file: statements are append-only. `verify` covers active **and**
archived changes. The signature check is where enforcement can't be faked from
a developer machine. The signer list comes from CI configuration that only admins can
change, and `--require-signed` rejects any decision without a valid signature,
whatever `project.md` or `change.json` say. Make the job a required status check
on your protected branch.

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
sprint to the next. It still stops for the **human gates**: the accreditation
verdict, each sprint sign-off, change-request decisions, rewinds and gated
amendments. Keep `Human gates: signed` with autopilot: the stop then needs a
signature, not just the model obeying a rule.

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
| `the backlog and sprint plan are not approved` / `the backlog changed since the plan was approved` | A person reviews the plan and runs `S approve-plan <id>` (§4.5) |
| `epic E2 (...) has no features` / `feature F3 (...) has no stories` | Complete the tree, or remove the empty epic or feature |
| `code outside specmaker/ changed since the last checkpoint` | Revert work done ahead of the sprint (or stash unrelated work). If it should stay, a person accepts it with `--accept-prior "<reason>"` |
| `this is a human gate, and human gates for this change are 'terminal'` (exit 3) | Working as intended: run the printed command yourself in an interactive terminal. Agents must not retry it |
| `no allowed signers file exists` (exit 3) | Register yourself once: `S approvers add --principal <you> --key <key>.pub` (§3) |
| `in signed mode --by must give your signer identity` | Add `--by <principal>`, the identity you registered with `approvers add` |
| `'<name>' is not an approver` | That principal is not in the allowed signers file; `S approvers list` shows who is |
| `the signature does not verify` | The key used to sign is not the one registered for that principal: set `SPECMAKER_SIGNING_KEY` to the right private key |
| `the record differs from what was signed` / `signature does not verify` in `status` or `verify` | `change.json` or an approval statement was edited after signing. Restore it from git; if the decision really changed, sign a new one |
| `is not referenced by any decision record` / `without gaps` | A decision record or a statement was deleted. Restore both from git; statements are append-only |
| `requirements it covered ... changed after sign-off` / `was rewound after this sign-off` | The sprint's signed sign-off no longer describes it: re-run the sprint and sign it off again |
| `OpenSSH ... is too old` / `OpenSSH (ssh-keygen) is required` | Install OpenSSH 8.1+ (`openssh-client` on Linux/WSL2) |
| `no gate run recorded` | Run `S gates <id> N` before sign-off |
| `<file> changed but is outside the sprint's task files` | Revert it, or record it under `## Deviations` |
| `scenarios with no test referencing their ID` | Add tests named with the IDs (§12), or the human accepts with `--accept-gaps "reason"` |
| `sprint N is active and the sprint freeze is on` | Working as intended: park the request; triage it at the sprint boundary, or mark it `--blocker` only if continuing would build something wrong |
| `CR-NNN must be applied first` | A request decided as `amend` is waiting: `amend --cr CR-NNN`, re-accredit, then start the sprint |
| `amendment budget reached` | Stop and discuss: re-ideate as a new change, or pass `--over-budget "<reason>"` with the human's agreement |
| `the recorded gate run predates this sprint's (re)start` | A reopened or rewound sprint needs fresh evidence: run `gates` and a new verifier round |
| `<report> is incomplete (no 'Verdict:' line or '## Findings')` | The reviewer did not finish: re-dispatch once, otherwise record the lens as `not run` (§9) |
| `Blocker <report>#G1 is unresolved` | Fix it and re-review the lens (a new round), contest or escalate it in the ledger (`--kind contested\|escalated --ref <report>#G1`), or make it a condition of a `conditional` verdict (`--kind condition`) |
| `L-00N declines Blocker ...` | A Blocker is never declined. Fix it, contest it with evidence, or make it a condition |
| `REMOVED [X-01] ... has no story` / `**Removes** [X-01], which no delta spec lists` | Add a story with `**Removes**: X-01` whose tasks delete the code and tests; list only REMOVED IDs |
| `... a docs-only change builds nothing, so it cannot retire IDs that tests or code name` | Make it a lite change (`S set <id> docs_only false`); its sprint updates the tests |
| `X-01.2 ([X-01] is removed) is still referenced by ...` | Delete or rewrite the listed tests and code; `S trace <id>` shows the Removals table |
| `new capability needs a '## Purpose' of at least 50 characters` / `'## Purpose' is only for a new capability` | Write a real purpose for a new capability; remove the section from deltas of existing ones |
| `not read: delta specs must be specs/<capability>/spec.md` | Move the text into that capability's `spec.md` |
| `heading ... would be hidden from checks` / `code block is never closed` | Use only `#### Scenario:` headings inside a requirement; close every fence |
| `living [X-01] changed since accreditation` | Another change was archived first; re-base the delta, `amend`, re-accredit |
| Skills don't trigger | Check they are side by side in a scanned folder (§1); name them explicitly (`@specmaker`) |
| Agent says it cannot find `scripts/specmaker.py` | Install to a standard location (§1), or set `SPECMAKER_HOME` to the installed `specmaker` skill folder before starting the agent |

## 21. Command reference

Every command accepts `--root <dir>`, written **before** the command name:
`S --root path/to/specmaker status`. Without it the workspace is
`$SPECMAKER_ROOT` if set, otherwise the nearest `specmaker/` containing
`project.md`, searching upward from the current folder.

| Command | Example | Notes |
|---|---|---|
| `init` | `S init` | Idempotent; never overwrites `project.md` |
| `new` | `S new add-sso --track lite --title "Add SSO"` | Full starts at ideate, lite at propose |
| `list` | `S list --json` | Active changes, plus the latest archived |
| `status` | `S status add-sso --json` | Phase, artifacts, lock, sprints, **next step** |
| `check` | `S check add-sso specs backlog` | `hld lld specs adrs design backlog sprint:N`, or nothing for automatic; exit 1 on errors |
| `set` | `S set add-sso depends_on other` | Keys: `skip_specs`, `docs_only`, `title`, `track`, `depends_on`, `human_gates` (`signed`/`terminal`/`chat`; loosening is a human gate, `--by` names the approver) |
| `approvers add` | `S approvers add --principal alex@example.com --key ~/.ssh/id_ed25519_sk.pub [--file PATH]` | Register an approver's public key in the allowed signers file |
| `approvers list` / `approvers check` | `S approvers check [--file PATH]` | Show approvers and key types; `check` also shows the OpenSSH version and whether the signer list is protected |
| `verify` | `S verify [<id>] --require-signed [--require-hardware] [--allowed-signers PATH] [--base REF]` | Verify the signed decision chain of active and archived changes (CI); `--base` also fails if any approval file was deleted or edited since REF; exit 1 on any problem |
| `phase` | `S phase add-sso accredit` | One step forward, only if the entry gate passes |
| `ledger` | `S ledger add-sso --kind declined --ref r1-critic#G2 "reason"` | Kinds: `decision` (design or process choice); `contested`, `escalated`, `declined`, `condition` (outcome of a review finding, with `--ref <report>#G<n>`); `question`, `answer`, `deviation`, `note`. No text prints the ledger |
| `accredit` | `S accredit add-sso --verdict conditional --condition "add audit log" --by alex@example.com` | Human verdict; locks the design. `signed` mode: you run it and sign (`--by` is your approver identity). `terminal`: you run it and type your name. `chat`: the agent adds `--by "<name>"` |
| `cr add` | `S cr add add-sso --title "..." --by "Support" [--blocker]` | Record a request; it is parked |
| `cr list` | `S cr list add-sso` | Requests and their status |
| `cr decide` | `S cr decide add-sso CR-001 CR-002 --outcome reject --reason "..."` | Human decision: reject, defer, backlog or amend; the freeze applies |
| `impact` | `S impact add-sso [--reqs AUTH-01]` | Changed requirements → scenarios, stories, files, tests, sprints |
| `rewind` | `S rewind add-sso --to sprint:2 --cr CR-001` | Human gate: discard code with a backup branch and stash; records a new commit |
| `amend` | `S amend add-sso --cr CR-001 --to ideate\|propose --reason "..."` | Reopen the design for decided requests; re-accreditation needs new review reports; budget applies (`--over-budget` is a human gate) |
| `amend --wording-only` | `S amend add-sso --wording-only --reason "typo"` | Human gate: meaning-neutral fix; no new reviews needed, no sprints reopened; refused if any requirement or scenario ID changes |
| `approve-plan` | `S approve-plan add-sso --by alex@example.com` | Human gate: approve the complete backlog tree and sprint plan; required before `phase <id> sprint` and again after any plan change (per `Plan approval`) |
| `sprint-start` | `S sprint-start add-sso 2 [--accept-prior "<reason>" --by <approver>]` | Previous sprints must be signed off and the plan approved; refuses code changed since the last checkpoint unless a person accepts it (`--accept-prior`, a human gate); records the git base |
| `gates` | `S gates add-sso 2 --timeout 900` | Runs `project.md` Quality Gates; writes `reviews/sprint-NN-gates.json` |
| `trace` | `S trace add-sso --out reviews/trace.md --strict` | Scenario → story → test matrix, plus a Removals table of retired scenarios and anything still naming them |
| `signoff` | `S signoff add-sso 2 --by alex@example.com` | Human sign-off; re-checks all evidence; same signed, terminal and chat rules as `accredit` |
| `export` | `S export add-sso --format csv` | Backlog for trackers |
| `coverage` | `S coverage --capability billing --strict` | Living-scenario test coverage |
| `doctor` | `S doctor [--json]` · `S doctor --isolation start` · `S doctor --isolation check [--report FILE]` | Requirements, installation, other copies, workspace setup; exit 1 on any FAIL. `--isolation` runs the canary probe of reviewer isolation (§11) |
| `spec` | `S spec` · `S spec SESS-02` · `S spec --lint` | Inventory, one requirement's text, or lint all living specs (duplicate IDs across capabilities included; exit 1 on errors) |
| `archive` | `S archive add-sso --dry-run` | Merge, verify, lint, promote ADRs, move to `archive/`; all or nothing (a failure restores every file) |
