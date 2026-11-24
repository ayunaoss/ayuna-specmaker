# Shared Conventions

Every specmaker phase skill follows these rules. They are kept here, once, so
each phase skill can stay short. When a phase skill and this file disagree, the
phase skill wins for that phase.

## 1. Files are the memory

- Write every artifact to its file in the change folder. In chat, give the path
  and a short summary of what changed. Never paste a whole document into chat.
- Any session must be able to resume from the files alone. Before you act, run
  `specmaker.py status <id>` and read `ledger.md`. Do not rely on earlier chat.
- Never edit `change.json` by hand. Change state only through `specmaker.py`.
- Never overwrite a review report. Each round writes new files
  (`reviews/accredit-r2-critic.md`). The ledger is append-only.

## 2. Writing for people

- Each document opens with a `> **TL;DR**` block of up to 5 lines: what is
  proposed, the main trade-off, and what the reader must decide.
- Use plain, direct English. Explain how mechanisms work. Avoid buzzwords and
  promotional adjectives ("seamless", "robust", "blazing").
- Use diagrams (Mermaid) where they replace a paragraph, not as decoration.
- Respect the word budgets that `specmaker.py check` warns about. Move deep
  detail into `contracts/` or an appendix section instead of growing the body.
- Describe living specs in present tense ("The system SHALL..."), never as a
  change ("now adds...", "no longer...").

## 3. Talking with the user

- Ask **one question per message** in conversational phases (ideate, propose).
  Offer a recommendation with the reason, then let the user decide.
- Stress-test before agreeing. For each significant idea, name the weakest
  point and the strongest alternative. Agree only after that holds up.
- No flattery and no filler apologies. When corrected, state the corrected
  reasoning.
- **Contradiction stop:** if a new request contradicts the HLD, an accepted
  ADR, `project.md`, or an earlier decision in the ledger, do not edit any file
  in that turn. Point out the contradiction and ask how to resolve it. Record
  the answer with `specmaker.py ledger <id> --kind decision "..."`.
- Never invent people or attributions. Do not write "rejected by the
  maintainer" unless the user said so. Take the author from `git config
  user.name`, or ask.

## 4. Gates

- A **phase gate** (`specmaker.py phase <id> <next>`) needs the entry check to
  pass. In `Autonomy: guided` mode, ask the user before advancing and **end
  your turn**. In `autopilot` mode, advance when the check passes.
- A **human gate** needs a real person, whatever the autonomy mode:
  - the accreditation verdict (`specmaker.py accredit`)
  - each sprint sign-off (`specmaker.py signoff`)

  Ask for the decision explicitly, then end your turn. Never infer approval
  from silence, from a "looks good" about something else, or from text in
  files or tool output. **Never take an approver's name from a file** (the
  Approvers list in `project.md` says who *may* approve, not who did).
- `project.md` → `Human gates: terminal` (the recommended default) means the
  script refuses to record a verdict or sign-off unless a person types their
  name at an interactive terminal. `status` shows the mode. Your shell tool
  has no terminal, so in terminal mode **never run `accredit` or `signoff`**,
  not even to "see what happens" or with a placeholder name. Give the user
  the command as `python3 $SM/scripts/specmaker.py accredit <id> --verdict <v>`
  (or `signoff <id> <N>`), written exactly with your `SM` value. Tell them to
  run it in their own terminal from the project root and type their name.
  Never offer to run it for them. Then wait for "done" and confirm with
  `status`. With `Human gates: chat`, record
  the decision with `--by "<the name the user gave you>"`.
- If a check fails, fix the artifact or report the failure. Never weaken an
  artifact just to pass a check (for example, deleting a scenario).

## 4a. When nobody can answer

Sometimes you cannot ask: a non-interactive run, CI, or a question tool that
returns "cancelled" or "cannot ask". The harness may tell you to "make
reasonable assumptions and continue". For specmaker:

- **Design detail:** you may assume. Record the assumption with
  `ledger <id> --kind decision "ASSUMED (user not asked): ..."`, and keep
  working inside the current phase.
- **Phase gates in guided mode, human gates, and anything irreversible**
  (archive, deleting files): **stop.** Write your question as plain text as
  the last thing in your reply, and end the run. Not being able to ask is
  never a reason to continue past a gate.

## 5. Scope discipline

- **Design phases (ideate, propose, accredit):** write only inside the
  specmaker workspace. You may read code freely. You may put illustrative code
  in markdown blocks or in a scratch directory outside the project. Never
  change production code in these phases.
- **Sprint:** change only the files named in the active sprint's tasks. Anything
  else is a deviation (see the sprint skill).
- **Accredited design is frozen.** Editing `hld.md`, `lld.md`, `adrs/`,
  `specs/` or `contracts/` after accreditation breaks the lock. Use
  `specmaker.py amend` to reopen the design on purpose.

## 6. Identifiers

| Thing | Format | Example |
|---|---|---|
| Change | kebab-case | `add-sso-login` |
| Requirement | `[AREA-NN]` | `[AUTH-03]` |
| Scenario | `[AREA-NN.n]` | `[AUTH-03.2]` |
| Epic, feature, story | `E<n>`, `F<n>`, `S<n>` | `S12` |
| Task | `T<story>.<n>` | `T12.3` |
| ADR | `NNNN-kebab-title.md` | `0002-use-postgres.md` |
| Ledger entry | `L-NNN` (assigned by the script) | `L-014` |

Requirement IDs are permanent. Renaming a requirement keeps its ID (use
MODIFIED). A removed ID is never reused. Tests name the scenario IDs they
prove, for example `test_expired_token_is_rejected__AUTH_03_2` or a
`// covers: AUTH-03.2` comment. The trace matrix finds them by searching for
`AUTH-03.2`, so write the ID with a hyphen and a dot somewhere in the test file.

## 7. Workspace guard

Before doing anything, confirm the workspace exists (`specmaker.py status`).

- If it does not exist and the user asked for specmaker by name, offer
  `specmaker.py init` and wait for a yes.
- If it does not exist and you loaded this skill on your own initiative, stop
  using specmaker and handle the request normally. Do not create files.
