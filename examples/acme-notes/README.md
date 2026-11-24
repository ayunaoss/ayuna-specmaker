# Example: Acme Notes

A tiny Python project used by the specmaker [walkthrough](../../docs/walkthrough.md).
It shows one full-track change, `idle-session-timeout`, taken through every
phase and stopped just before archiving, so you can run the last step
yourself.

| Where | What to look at |
|---|---|
| `specmaker/project.md` | A filled project charter, including Quality Gates and two rules added by the retro |
| `specmaker/specs/identity/session/spec.md` | The living spec **before** the change is merged |
| `specmaker/changes/idle-session-timeout/` | Every artifact of the change: HLD, LLD, delta spec, ADRs, reviews, accreditation, ledger, backlog, sprints, retro |
| `src/notes/`, `tests/` | The implementation; tests name scenario IDs (`__SESS_02_3`, `covers: SESS-02.3`) |

Try it from this repository:

```bash
cd examples/acme-notes
python3 ../../skills/specmaker/scripts/specmaker.py status
python3 ../../skills/specmaker/scripts/specmaker.py check idle-session-timeout
python3 ../../skills/specmaker/scripts/specmaker.py trace idle-session-timeout
python3 ../../skills/specmaker/scripts/specmaker.py archive idle-session-timeout --dry-run
```

To see the archive step for real, copy the example somewhere first, so that
this folder stays as it is:

```bash
cp -r examples/acme-notes /tmp/acme-notes && cd /tmp/acme-notes
python3 <path-to-ayuna-specmaker>/skills/specmaker/scripts/specmaker.py archive idle-session-timeout
cat specmaker/specs/identity/session/spec.md   # SESS-02 modified, SESS-03 added
ls specmaker/adrs                              # ADRs promoted to the project log
```

Note: the example is not a git repository, so the sprint sign-offs show a
warning that the file boundary was not checked. In a git project that check is
enforced.
