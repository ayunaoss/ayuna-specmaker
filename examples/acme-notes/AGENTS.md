<!-- specmaker:start -->
## Spec-driven workflow (specmaker)

This project uses Ayuna specmaker; its workspace is `specmaker/`.

- Before answering questions about, or changing anything in, `specmaker/` (changes,
  specs, ADRs, backlogs, sprints), load the `specmaker` skill with your skill
  tool, then the phase skill it names. Do not work from those files without it,
  and never edit `specmaker/changes/*/change.json` by hand.
- Before changing behaviour, check whether a living spec in `specmaker/specs/`
  covers it. If one does, the change goes through specmaker.
<!-- specmaker:end -->
