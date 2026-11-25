# Goldfish Protocol (fresh-context review)

You, the drafting agent, are the **elephant**. You remember the whole
conversation, which is exactly why you cannot see the gaps in what you wrote. A
**goldfish** is a reviewer that starts with an empty context. It knows only the
files you hand it. If the documents do not explain something, the goldfish
notices, because it has nowhere else to look.

Three phases use goldfish:

- ideate: optional lens review of the HLD.
- accredit: mandatory design review.
- sprint: mandatory spec-to-code verification.

## 1. Dispatch

Spawn each goldfish with your harness's subagent tool, in a **new** child
session. Never reuse a reviewer session.

| Harness | Tool | Agent |
|---|---|---|
| OpenCode | the subagent tool (`task` in V1, `subagent` in V2) | `general`, or a `goldfish` agent if the project defines one |
| Claude Code | `Agent` | `general-purpose` |
| Codex | `spawn_agent` | default |
| Antigravity | `invoke_subagent` | default |

Run independent goldfish in parallel when the harness allows it. Each one
writes its own report file, so a run that is cut off can resume. Before you
dispatch, check which reports already exist for the round and skip those
reviewers.

In OpenCode 2.x the `subagent` tool returns immediately and the reviewer works
in the background. Wait for each `<background-result kind="subagent">`
message, then check that its report file exists, before you triage. Do not
read a report while it is still being written.

### Prompt shape (pass it verbatim, filled in)

```text
You are a goldfish reviewer. You have no memory of any conversation. Use only the files listed here.
1. Read your persona: <ABS>/references/personas/<lens>.md
2. Read the shared reviewer rules: <ABS-specmaker>/references/goldfish.md, section "Reviewer rules" only.
   Naming guide, for the critic, readiness and verifier lenses: <ABS-specmaker>/references/naming.md
3. Review these files: <ABS paths: hld.md, lld.md, specs/..., adrs/..., contracts/...>
4. Settled decisions (do not re-raise them unless you have new evidence): <ABS>/ledger.md
5. Project charter: <ABS>/specmaker/project.md
Mode: <REVIEW | BRAINSTORM | VERIFY>. Round: <N>. Scope: <whole document | sections changed since round N-1: ...>
Write your report to <ABS>/reviews/<file>.md using the report format in the shared rules. Reply with only that path.
```

Pass **only** paths. Never paste chat history, your reasoning, earlier findings
(except through the ledger), or your opinion of the design.

### Isolation probe

Before the first dispatch in a session, spawn one probe goldfish with this
prompt: "List every instruction file, memory or prior conversation you can see,
and quote the first line of each." If it can see this conversation, it is not a
goldfish. Stop and use the fallback below. If it reports project instruction
files (`AGENTS.md`, `CLAUDE.md`), you can continue, but note
`isolation: partial (instruction files visible)` in each report header.

### Model diversity

If `project.md` names a reviewer model and the harness lets you choose a model
per subagent, use it. A second model catches different issues. Record the model
in each report header.

### Fallback: cold-read mode

If the harness has no subagent tool, or the probe fails, do not review in your
own context. That would not be a goldfish review. Instead:

1. Write the exact prompt to `reviews/pending/<file>.prompt.md`.
2. Tell the user to open a **new** session in the same project and send:
   `Run the goldfish prompt in specmaker/changes/<id>/reviews/pending/<file>.prompt.md`.
3. Continue once the report exists.

## 2. Budget

Before dispatching, tell the user how many reviewers will run and which ones,
for example: "Round 1: 5 reviewers (standard preset)". The cost of a review
grows with the number of reviewers. `project.md` sets the default preset;
the user may change it for this change.

## 3. Reviewer rules

*(This is the section a goldfish reads.)*

- Read-only: never edit project files. Write only your report file.
- Judge only what the listed files say. If something needed is missing, that is
  a finding. Do not fill gaps from general knowledge and then approve.
- Every finding must state its **evidence**, one of:
  - `doc:<file>#<section or line>`: the document says something wrong,
    contradictory or unclear here.
  - `code:<path>:<line>`: the codebase contradicts the document.
  - `absent:<what is missing>`: something the persona's standard requires is
    not there.
  - `question`: you cannot tell without asking the owner. Questions never
    block; the owner answers them.
- Severity:
  - **Blocker**: building as written would produce the wrong system, fail a
    requirement, or force the implementer to make a design decision.
  - **Major**: a real gap or risk that should be fixed before building.
  - **Nit**: wording or polish. Report at most 5 Nits.
  A Blocker or Major finding whose evidence is `question` is invalid. File it
  as a question instead. Use only these three severity words; never "Minor",
  "Low" or "Critical".
- Do not re-raise anything in the ledger marked DECISION or DECLINED unless you
  cite evidence the ledger entry did not consider.
- Prefer a few findings that matter over a long list. If you find nothing above
  a Nit, say so plainly.

### Report format

```markdown
# <Lens> review - round <N>
- Target: <files>
- Mode: <REVIEW|BRAINSTORM|VERIFY> | Model: <model if known> | Isolation: <full|partial ...>
- Verdict: <PASS | PASS-WITH-NOTES | FAIL>   (FAIL if there is any Blocker)

## Findings
### G1 [Blocker|Major|Nit] <short title>
- Evidence: <doc:...|code:...|absent:...>
- Problem: <what is wrong and why it matters, in plain words>
- Suggested fix: <concrete change>

## Questions for the owner
- Q1: <question> (context: <file#section>)
```

## 4. Convergence (for the elephant)

Reviews tend to keep producing findings forever. These rules make them stop:

1. **Triage** every Blocker and Major finding with the user, one at a time
   where needed. Each gets one of these outcomes:
   - `FIX`: you propose the exact edit; the user approves it.
   - `CONTEST`: the finding is wrong; cite the evidence the reviewer missed.
   - `DECLINE`: the finding is valid but accepted as a trade-off; give the reason.
   - `ESCALATE`: only the user can decide.
   Nits are fixed if cheap, otherwise ignored.
2. Record each CONTEST, DECLINE and answered question in the ledger
   (`--kind declined|decision|answer --ref <report>#G<n>`). This stops the next
   round from re-raising them.
3. **Re-review only what changed**, and only with the lenses that raised
   Blockers or Majors.
4. **Stop** when a round has no Blocker or Major with evidence, or when the
   round cap in `project.md` (default 2 re-review rounds) is reached. At the
   cap, what remains is listed in `accreditation.md` as known risk, and the
   human decides.
