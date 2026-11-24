---
name: specmaker
description: >-
  Entry point of Ayuna specmaker, a spec-driven development workflow with phases
  ideate (HLD), propose (LLD, specs, ADRs), accredit (fresh-context review plus
  human approval), scrum (epics, features, stories, tasks), sprint (build, verify
  spec against code, sign-off) and retro (merge specs, archive). Use when the user
  mentions specmaker, wants to start, resume or triage a spec-driven change, asks
  "where are we" on a change, or wants to adopt specs for an existing codebase.
license: MIT
compatibility: Agent Skills (OpenCode, Claude Code, Codex, Antigravity). Needs python3 >= 3.8 and optionally git.
metadata:
  author: ayuna
  version: "0.1.0"
---

# Ayuna specmaker

Specmaker turns an idea into accredited specs, a backlog, and verified code in
six phases. Each phase is its own skill. This skill sets up the workspace,
decides how much process a change needs, and sends the work to the right phase.

Read these files once per session, before doing phase work:

- [conventions.md](references/conventions.md): the rules every phase follows.
- [spec-format.md](references/spec-format.md): requirement and scenario format.
- [goldfish.md](references/goldfish.md): fresh-context review. Read it when a
  phase needs reviewers.

## The helper script

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

All state changes go through the helper script:

```bash
python3 $SM/scripts/specmaker.py <command> ...
```

The references linked above are in `$SM/references/`. The phase skills are
installed next to this one, in `$SM/../specmaker-<phase>/`.

| Command | Purpose |
|---|---|
| `init` | Create the `specmaker/` workspace and the specmaker block in `AGENTS.md` (idempotent) |
| `new <id> [--track full\|lite] [--title ...]` | Start a change |
| `status [<id>] [--json]` | Show phase, artifacts, lock state and **next step** |
| `check <id> [hld lld specs adrs design backlog sprint:N]` | Lint artifacts |
| `phase <id> <next-phase>` | Advance if the entry gate passes |
| `ledger <id> [--kind ...] "text"` | Append a decision, declined finding, answer or deviation |
| `accredit <id> --verdict ... --by "<human>"` | Record the human verdict and lock the design |
| `amend <id> --reason "..."` | Reopen an accredited design |
| `sprint-start <id> N` / `gates <id> N` / `signoff <id> N --by "<human>"` | Run a sprint |
| `trace <id> [--out trace.md]` | Matrix of scenario → story → test |
| `export <id> --format csv\|json` | Backlog for issue trackers |
| `archive <id> [--dry-run]` | Merge delta specs into living specs, promote ADRs, archive |
| `spec [<REQ-ID>]` | List living specs, or print one requirement |

The script never needs network access and never calls a model. When it reports
an error, fix the artifact. Do not work around the check.

## Workspace

```text
specmaker/
  project.md                 charter: stack, conventions, quality gates, review policy
  specs/<capability>/spec.md living specs (source of truth)
  adrs/NNNN-*.md             project-wide decision log (promoted at archive)
  changes/<change-id>/
    change.json              state (script-owned)
    ledger.md                append-only decisions, declined findings, answers
    hld.md                   ideate
    lld.md  adrs/  specs/  contracts/      propose
    reviews/  accreditation.md             accredit
    backlog.md                             scrum
    sprints/sprint-NN.md                   sprint
    retro.md                               retro
  archive/YYYY-MM-DD-<change-id>/
```

## Phases

| Phase | Skill | Produces | Leaves when |
|---|---|---|---|
| ideate | `specmaker-ideate` | `hld.md` | HLD passes `check` and the user agrees |
| propose | `specmaker-propose` | `lld.md`, delta specs, ADRs, contracts | design passes `check` |
| accredit | `specmaker-accredit` | review reports, `accreditation.md`, verdict | a named human approves; design is locked |
| scrum | `specmaker-scrum` | `backlog.md` with sprint plan | backlog passes `check` |
| sprint | `specmaker-sprint` | code, tests, sprint log, verification | each sprint is signed off by a human |
| retro | `specmaker-retro` | `retro.md`, merged living specs, archive | archived |

Load the phase skill for the change's current phase. If the user asks for a
different phase, explain what the script's gate requires and offer the path
there.

## Start or resume

1. Run `status`. If no workspace exists, follow the workspace guard in
   conventions.md.
2. **Resume:** if the user names a change, or only one is active, read its
   `status` and `ledger.md`. Tell the user the phase and next step in two
   lines, then load the phase skill.
3. **Start:** triage first (below), then run
   `new <id> --track <track>` and load the first phase skill.

## Triage: how much process?

Ask about the change, or read it, then recommend one of these:

| Size | Signals | Track |
|---|---|---|
| **Skip specmaker** | Typo, small bug fix with an obvious cause, dependency bump, no behaviour change | Do the work directly. If it changes behaviour a living spec describes, update that spec in the same commit and say so. |
| **Lite** | One capability, a few days of work, no new infrastructure, design is clear | `--track lite`: starts at propose (short LLD, specs), quick review preset, a flat story list, one or two sprints |
| **Full** | New capability or system, several components, data or infra decisions, real uncertainty | `--track full`: all six phases |

State the recommendation and the reason in one or two sentences, and let the
user overrule it. Ceremony that does not fit the change is the most common
reason teams drop spec-driven workflows.

## Repair paths

| Situation | Path |
|---|---|
| The intent or design was wrong and the change is past accredit | `amend` → propose → re-accredit (re-review only what changed) |
| The implementation is wrong but the design is right | Stay in the sprint and fix the code; the verifier checks it again |
| A sprint needs a small design decision the LLD did not make | Record a deviation (sprint skill). If it changes a spec, an ADR or a contract, `amend` |
| Code was edited by hand outside specmaker | Run the retro skill's drift check; fix the code or open a change for the spec |
| Two open changes touch the same requirement | `set <id> depends_on <other>`; the dependent change archives second |

## Adopt: specs for an existing codebase

When the user wants specmaker on a brownfield project:

1. Run `init`, then fill `project.md` from what the repository shows (stack, CI,
   test command). Ask about anything you cannot verify.
2. Choose one capability at a time, starting with the area about to change.
   Never try to spec the whole system in one go.
3. Run `new baseline-<capability> --track lite`, then
   `set baseline-<capability> docs_only true`. Write a delta spec with
   ADDED requirements describing **current** behaviour. Cite the code that
   proves each one in an HTML comment (`<!-- code:src/auth/session.ts:42 -->`).
   Write a short LLD that documents the existing design, with
   `File Boundary: none (documentation only)`.
4. Accredit with the quick preset; a human confirms the behaviour is real. A
   docs-only change then goes straight from accredit to retro
   (`phase <id> retro`), because there is nothing to build. Existing tests that
   already prove a scenario should be tagged with its ID over time.
