# Backlog: <!-- change-id -->

> **TL;DR** <!-- Number of epics, stories and points; number of sprints; the riskiest story and why. -->

- Sprint length: <!-- e.g. 1 week -->
- Capacity per sprint: <!-- points; say if it is a guess -->
- Team: <!-- agent / humans; who owns human-only tasks -->

<!--
Format (the script parses it):
## E<n> - <epic>                     epics: level-2 headings
### F<n> - <feature>                 features: level-3 headings under an epic
#### S<n> - As a <role>, I want <x>, so that <y>
- **Covers**: AREA-01.1, AREA-01.2   scenario IDs (acceptance criteria)
- **Points**: 3                      1, 2, 3, 5, 8, 13
- **Priority**: Must                 Must | Should | Could | Won't
- **Depends**: S1                    optional
- **Removes**: AREA-02               REMOVED requirement IDs whose code and tests this story deletes
- **Type**: story                    story | enabler | spike | chore
- [ ] T<story>.<n> <imperative step> - files: path/a.ts, path/a.test.ts - owner: agent|human
-->

## E1 - <!-- epic outcome -->

<!-- One or two sentences: the outcome and the HLD goal it serves (G1...). -->

### F1 - <!-- feature -->

#### S1 - As a <!-- role -->, I want <!-- capability -->, so that <!-- benefit -->
- **Covers**: <!-- AREA-01.1, AREA-01.2 -->
- **Points**: 3
- **Priority**: Must
- **Type**: story
- [ ] T1.1 Write failing tests for <!-- AREA-01.1, AREA-01.2 --> - files: <!-- tests/... -->
- [ ] T1.2 <!-- implement ... --> - files: <!-- src/... -->

## Sprint Plan

| Sprint | Goal | Stories | Points |
|---|---|---|---|
| 1 | <!-- demoable goal --> | S1 | 3 |
