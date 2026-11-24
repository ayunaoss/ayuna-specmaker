---
name: specmaker-ideate
description: >-
  Specmaker ideate phase. Free-flowing, challenging conversation that turns a raw
  idea into a High-Level Design (hld.md): problem, users, goals and non-goals,
  success measures, solution shape, alternatives, risks. Use when the user wants
  to brainstorm, explore or shape an idea inside a specmaker workspace, or a
  change is in the ideate phase.
license: MIT
compatibility: Requires the specmaker skill installed alongside (shared script and references).
metadata:
  author: ayuna
  version: "0.1.0"
---

# Ideate: from idea to HLD

**Goal:** a short HLD that a newcomer can read in ten minutes and understand
*what* problem we are solving, *for whom*, *why this shape of solution*, and
*what we decided not to do*. It is not an LLD. Data models, APIs and libraries
come later.

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
- Read `$SM/references/conventions.md` before starting.
- Read `$SM/references/goldfish.md` only if you run the optional lens review.
- This skill's own files (`references/`, `assets/`) are in `$SM/../specmaker-ideate/`.

## Steps

### 1. Orient

- Run `status`. If no change exists, follow the triage step in the `specmaker`
  skill first: a full-track change starts here; a lite change skips this phase.
- Read `project.md`, `ledger.md` if present, and the living-spec inventory
  (`spec`). In an existing codebase, look at the code areas the idea touches
  before asking questions, so your questions are informed.

### 2. Converse (most of the phase)

Explore the idea with the user, **one question per message**. Lead with what you
understood and what worries you, then ask the single most useful next question.
Cover these, in whatever order the conversation goes:

- **Problem:** what hurts today, for whom, and how often? How is it handled now,
  and why is that not good enough?
- **Users and stakeholders:** who uses it, who operates it, who pays, and who
  can say no?
- **Outcome:** what does success look like, and how will it be measured
  (numbers, not adjectives)?
- **Boundaries:** what is explicitly out of scope? Ask about the tempting
  neighbour features.
- **Constraints:** deadlines, budget, compliance, platforms, existing systems
  that must not change, team skills.
- **Shape:** two or three candidate approaches, including "buy or reuse
  instead of build" and "do nothing". Push on the weakest point of each.
- **Risks and unknowns:** what would make this fail? What must be learned
  first, and is that a spike?

Behaviour during the conversation:

- Challenge before you agree. When the user states a conclusion, test it: name
  the strongest counter-argument and what they may not be seeing.
- Bring in knowledge the user may lack (prior art, known failure modes,
  standards), and say where it came from.
- Keep a running hypothesis. Every few turns, restate it in two or three
  sentences so the user can correct drift early.
- Record firm decisions as they happen:
  `ledger <id> --kind decision "<decision and reason>"`.
- If the user wants to stop and continue later, write what you have to
  `hld.md`, with open questions as `- [ ]` items, so the next session can pick
  up from the file.

### 3. Draft the HLD

When the problem, scope and shape are clear, ask once: "Ready for me to write
the HLD?" Then copy `assets/templates/hld.md` to `changes/<id>/hld.md` and fill
it in.

- Use the user's words for the problem. Use your own words for the solution
  overview.
- **Alternatives Weighed** must list each option discussed, with the concrete
  reason it lost. These carry forward into ADRs in the propose phase.
- Include a Mermaid context diagram: the system as one box, with the actors and
  external systems around it.
- Keep it under about 2,500 words. Write the `> **TL;DR**` last.

Run `check <id> hld` and fix every error.

### 4. Optional lens review

For a risky or novel idea, offer a goldfish lens review **before** the user
signs off on the HLD. It costs one reviewer per lens.

- Pick three to five lenses from [lenses.md](references/lenses.md) that fit the
  idea (for example, "cost and scale" for a data pipeline, or "migration" for a
  rewrite).
- Dispatch per goldfish.md with `Mode: BRAINSTORM`. Each reviewer gets the
  persona path `references/lenses.md#<lens>`, `hld.md`, `project.md` and the
  ledger. Reports go to `reviews/ideate-r1-<lens>.md`.
- Summarise the two or three objections that matter most. Discuss each with
  the user, update the HLD, and record each outcome in the ledger.

### 5. Close

Show the user the HLD path, the TL;DR, and any open questions that remain.
Unresolved questions that block design must be answered, or turned into an
explicit assumption, before leaving the phase.

When the user agrees the HLD is right, run `phase <id> propose`. Then tell them
the next step is the propose phase (`specmaker-propose`).
