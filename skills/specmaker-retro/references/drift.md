# Drift check (spec and ADRs against code)

Use this when code may have changed outside specmaker (hotfixes, other
changes), before starting a change in an area, or on a schedule.

1. `coverage [--capability <path>] --out <file>` lists every living scenario
   with no test that names its ID. Missing tests are the cheapest drift
   signal.
2. For each capability in scope, read its living spec and the code that
   implements it, one capability at a time to keep context small. Report only
   the differences:
   - behaviour in a spec that is missing or different in the code
   - fields, codes or limits that differ
   - hardcoded values where the spec implies configuration
   - behaviour in the code that no spec covers
   - code that departs from an **Accepted ADR** in `specmaker/adrs/` touching
     the capability (a different datastore, library or pattern)

   If you cannot find the code for a requirement, ask the user where it
   lives, and suggest adding that file link to the LLD of the next change, so
   later checks are cheaper.
3. Write `specmaker/drift-YYYY-MM-DD.md`: one section per capability, listing
   each divergence with `code:<path>:<line>` evidence, or "No drift found".
4. For each divergence, the user decides:
   - **Code is wrong:** fix it now, or as a lite change.
   - **Spec is outdated:** open a change (lite, or docs-only if behaviour is
     already in production and no test or code names a scenario it drops)
     with a MODIFIED delta.

Never edit living specs directly. They change only through `archive`, so every
change to the source of truth has a review trail.
