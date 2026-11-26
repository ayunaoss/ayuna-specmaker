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
compatibility: Agent Skills (OpenCode, Claude Code, Codex, Antigravity). Linux, macOS or WSL2 with python3 >= 3.8 and OpenSSH >= 8.1; git recommended.
metadata:
  author: ayuna
  version: "0.1.0"
---

# Ayuna specmaker

Six phases take an idea to accredited specs, a backlog and verified code. Each
phase is its own skill. This skill sets up the workspace, decides how much
process a change needs, and hands over to the right phase.

**Locate specmaker** (your harness may not say where this skill lives):

```bash
R=$(git rev-parse --show-toplevel 2>/dev/null || pwd); for d in "$SPECMAKER_HOME" "${CLAUDE_SKILL_DIR}/../specmaker" "$R/.opencode/skills/specmaker" "$R/.agents/skills/specmaker" "$R/.claude/skills/specmaker" "${XDG_CONFIG_HOME:-$HOME/.config}/opencode/skills/specmaker" "$HOME/.agents/skills/specmaker" "$HOME/.claude/skills/specmaker" $(ls -d "${CLAUDE_CODE_PLUGIN_CACHE_DIR:-$HOME/.claude/plugins}"/cache/*/specmaker/*/skills/specmaker 2>/dev/null | sort -V | tail -1); do [ -f "$d/scripts/specmaker.py" ] && { d=$(cd "$d" && pwd); case "$d" in "$R"/*) echo "${d#"$R"/}";; *) echo "$d";; esac; break; }; done
```

Call the printed folder `SM`, and run specmaker commands from the project root.
If nothing prints, ask the user to install all seven specmaker skills side by
side, or to set `SPECMAKER_HOME`.

**Read once per session:** `$SM/references/conventions.md` (rules for every
phase). Read the others when they apply:

- `spec-format.md`: writing specs
- `naming.md`: naming code
- `goldfish.md`: reviewers
- `change-requests.md`: someone asks to change a change in flight
- `recipes.md`: repair paths, adopting an existing codebase

For Nx polyglot monorepos, the optional `specmaker-monorepo` skill (if
installed) supplies the scaffolding commands and per-language check rules.

## The script

All state changes go through `python3 $SM/scripts/specmaker.py <command>`
(`-h` lists all commands). It never calls a model or the network. When it
reports an error, fix the artifact; never work around the check.

| Command | Purpose |
|---|---|
| `init` | Create the `specmaker/` workspace (idempotent) |
| `new <id> --track full\|lite` | Start a change |
| `status [<id>]` | Phase, artifacts, lock, requests and the **next step** |
| `check <id>` | Lint the change's artifacts |
| `phase <id> <next>` | Advance if the entry gate passes |
| `ledger <id> --kind ... "text"` | Append a decision, answer or deviation |
| `cr add\|list\|decide`, `impact`, `rewind`, `amend` | Change requests (see `change-requests.md`) |
| `accredit`, `approve-plan`, `signoff`, `cr decide`, `rewind` | **Human gates** (conventions §4) |

Phase skills are installed next to this one, in `$SM/../specmaker-<phase>/`.

## Workspace

```text
specmaker/
  project.md                  charter: stack, conventions, quality gates, gate mode
  specs/<capability>/spec.md  living specs (changed only by `archive`)
  adrs/                       project-wide decision log
  changes/<id>/               change.json (script-owned), ledger.md, hld.md, lld.md, specs/,
                              adrs/, reviews/, approvals/, requests/, backlog.md, sprints/, retro.md
  archive/YYYY-MM-DD-<id>/
```

## Phases

| Phase | Skill | Produces | Leaves when |
|---|---|---|---|
| ideate | `specmaker-ideate` | `hld.md` | HLD passes `check` and the user agrees |
| propose | `specmaker-propose` | `lld.md`, delta specs, ADRs, contracts | design passes `check` |
| accredit | `specmaker-accredit` | reviews, `accreditation.md`, human verdict | approved; the design is locked |
| scrum | `specmaker-scrum` | `backlog.md` with sprint plan | the full tree passes `check` and a person approves the plan |
| sprint | `specmaker-sprint` | code, tests, evidence, human sign-off | every sprint signed off |
| retro | `specmaker-retro` | `retro.md`, merged living specs | archived |

## Start or resume

1. Run `status`. If there is no workspace, follow the workspace guard
   (conventions §7).
2. **Resume:** read the change's `status` and `ledger.md`. Tell the user the
   phase and next step in two lines, then load that phase's skill.
3. **Start:** triage (below), run `new <id> --track <track>`, then load the
   first phase skill.

## Triage: how much process?

| Size | Signals | Track |
|---|---|---|
| Skip | Typo, obvious small fix, dependency bump, no behaviour change | Just do it. If it changes behaviour a living spec describes, it is not a skip: use lite |
| Lite | One capability, a few days, no new infrastructure, clear design | `--track lite`: starts at propose, quick review, flat story list |
| Full | New capability or system, data or infra decisions, real uncertainty | `--track full`: all six phases |

Recommend one in a sentence or two, and let the user overrule it. Process that
doesn't fit the change is the main reason teams drop spec-driven workflows.

**Change requests:** when anyone asks to change scope, behaviour, the design
or the plan of a change in flight, record it with `cr add` (`--by`: who asked)
and keep working.
Never edit a locked design, or a running sprint's backlog, because someone
asked in chat. Follow `change-requests.md`.
