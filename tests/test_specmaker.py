"""End-to-end and unit tests for skills/specmaker/scripts/specmaker.py.

Run: python3 -m unittest discover -s tests -v
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "skills" / "specmaker" / "scripts" / "specmaker.py"
TPL = REPO / "skills"
REPORT_PASS = "# Review\n- Verdict: PASS\n\n## Findings\n\nNone above a Nit.\n"

HLD = """\
# HLD: Session expiry

> **TL;DR** Expire idle sessions after 30 minutes to cut account-takeover risk.

## 1. Problem Statement
Sessions never expire, so a stolen cookie works forever.
## 2. Users and Stakeholders
Customers; security team.
## 3. Goals
- G1: idle sessions end automatically.
## 4. Non-Goals
- NG1: no MFA in this change.
## 5. Success Measures
Zero sessions older than 30 idle minutes in audit logs.
## 6. Constraints and Assumptions
Must work with the existing cookie store.
## 7. Solution Overview
The session middleware checks last-seen time on every request.
## 8. Alternatives Weighed
### A1: absolute lifetime
- Why not: logs out active users.
## 9. Risks and Open Questions
Clock skew between nodes.
## 10. Key Decisions Carried Forward
Idle timeout, not absolute.
"""

LLD_SECTIONS = ["Context and Scope", "Architecture", "Data Model", "Interfaces and Contracts",
                "Behaviour and Error Handling", "Cross-Cutting Concerns", "Technology and Deployment",
                "Alternatives Considered", "Test Strategy", "Migration and Rollout",
                "Implementation Phases", "File Boundary", "Risks and Mitigations", "Traceability"]


def lld() -> str:
    body = "# LLD: Session expiry\n\n> **TL;DR** Middleware rejects idle sessions.\n\n"
    for i, s in enumerate(LLD_SECTIONS, 1):
        body += f"## {i}. {s}\n\nContent for {s.lower()}: src/session.py and tests/test_session.py.\n\n"
    return body


SPEC = """\
# identity/session

## Purpose

Keeps a signed-in session valid only while the user is active.

## ADDED Requirements

### Requirement: [AUTH-01] Idle expiry
The system SHALL end a session 30 minutes after its last authenticated request.

#### Scenario: [AUTH-01.1] Idle session expires
- **GIVEN** a session idle for 31 minutes
- **WHEN** a request arrives
- **THEN** it is rejected with 401 `session_expired`

#### Scenario: [AUTH-01.2] Active session continues
- **WHEN** a request arrives after 29 idle minutes
- **THEN** it succeeds and the idle timer resets

<!--
### Requirement: [AUTH-99] Commented example must be ignored
-->
"""

ADR = """\
# ADR-0001: Store last-seen in the session cookie store

- Status: Accepted
- Date: 2026-11-24

## Context
Need last-seen time per session.

## Decision Drivers
- latency

## Options Considered
### Option 1: cookie store
- Pros: no new infra
### Option 2: Redis
- Cons: new infra

## Decision
Option 1.

## Consequences
One extra write per request.
"""

BACKLOG = """\
# Backlog: session-expiry

> **TL;DR** one epic.

## E1 - Idle sessions end

### F1 - Expiry middleware

#### S1 - As a user, I want idle sessions to end, so that stolen cookies expire
- **Covers**: AUTH-01.1, AUTH-01.2
- **Points**: 3
- **Priority**: Must
- **Type**: story
- [ ] T1.1 Write failing tests for AUTH-01.1, AUTH-01.2 - files: tests/test_session.py
- [ ] T1.2 Implement idle check - files: src/session.py

## Sprint Plan

| Sprint | Goal | Stories | Points |
|---|---|---|---|
| 1 | Idle sessions expire | S1 | 3 |
"""

SPRINT = """\
# Sprint 1: session-expiry

> **TL;DR** done.

## Sprint Goal
Idle sessions expire.

## Committed Stories
| Story | Points | Covers | Status |
|---|---|---|---|
| S1 | 3 | AUTH-01.1, AUTH-01.2 | done |

## Progress
- S1 done.

## Deviations
<!-- - [ ] example open question inside a comment must be ignored -->

## Verification
- Gates: PASS

## Sign-off
"""


class Project:
    def __init__(self, git: bool = True) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="specmaker-test-"))
        self.git = git
        if git:
            self.sh("git init -q && git config user.email t@example.com && git config user.name Tester")

    def sh(self, cmd: str) -> str:
        return subprocess.run(cmd, shell=True, cwd=self.tmp, check=True, capture_output=True, text=True).stdout

    def run(self, *args: str, ok: bool = True) -> subprocess.CompletedProcess:
        r = subprocess.run([sys.executable, str(SCRIPT), *args], cwd=self.tmp, capture_output=True, text=True)
        if ok and r.returncode != 0:
            raise AssertionError(f"specmaker {' '.join(args)} failed ({r.returncode}):\n{r.stdout}\n{r.stderr}")
        if not ok and r.returncode == 0:
            raise AssertionError(f"specmaker {' '.join(args)} unexpectedly passed:\n{r.stdout}")
        return r

    def write(self, rel: str, text: str) -> Path:
        p = self.tmp / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return p

    def change(self, cid: str = "session-expiry") -> Path:
        return self.tmp / "specmaker" / "changes" / cid

    def state(self, cid: str = "session-expiry") -> dict:
        return json.loads((self.change(cid) / "change.json").read_text())

    def cleanup(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)


def set_gate_mode(p: Project, mode: str) -> None:
    pm = p.tmp / "specmaker" / "project.md"
    pm.write_text(re.sub(r"(?m)^- Human gates: \w+$", f"- Human gates: {mode}", pm.read_text()))


def chat_gates(p: Project) -> None:
    """Most tests drive the script without a person, so they use chat-mode human gates."""
    set_gate_mode(p, "chat")


def set_gates(p: Project, cmd: str = "python3 -c 'pass'") -> None:
    pm = p.tmp / "specmaker" / "project.md"
    text = pm.read_text()
    text = text.replace('- test: `echo "replace with your test command" && exit 1`', f"- test: `{cmd}`")
    pm.write_text(text)


def design(p: Project) -> None:
    c = "specmaker/changes/session-expiry/"
    p.write(c + "hld.md", HLD)
    p.write(c + "lld.md", lld())
    p.write(c + "specs/identity/session/spec.md", SPEC)
    p.write(c + "adrs/0001-cookie-last-seen.md", ADR)


def reviews(p: Project, lenses=("consistency", "readiness"), rnd: int = 1) -> None:
    for lens in lenses:
        p.write(f"specmaker/changes/session-expiry/reviews/accredit-r{rnd}-{lens}.md", f"# {lens}\n- Verdict: PASS\n\n## Findings\n\nNone above a Nit.\n")
    p.write("specmaker/changes/session-expiry/accreditation.md", "# Accreditation\n")


class EndToEnd(unittest.TestCase):
    def setUp(self) -> None:
        self.p = Project()

    def tearDown(self) -> None:
        self.p.cleanup()

    def test_full_lifecycle(self) -> None:
        p = self.p
        p.run("init")
        chat_gates(p)
        set_gates(p)
        p.run("new", "session-expiry", "--title", "Session expiry")
        self.assertEqual(p.state()["phase"], "ideate")

        # cannot skip phases
        p.run("phase", "session-expiry", "accredit", ok=False)
        p.run("phase", "session-expiry", "propose", ok=False)  # no HLD yet
        design(p)
        p.run("check", "session-expiry", "hld")
        p.run("phase", "session-expiry", "propose")
        p.run("check", "session-expiry", "design")
        p.run("phase", "session-expiry", "accredit")

        # verdict needs reviews + record
        p.run("accredit", "session-expiry", "--verdict", "approved", "--by", "Ravi", ok=False)
        reviews(p)
        p.run("accredit", "session-expiry", "--verdict", "approved", "--by", "Ravi")
        self.assertIn("lock", p.state()["accreditation"])

        # lock detects edits
        lldp = p.change() / "lld.md"
        original = lldp.read_text()
        lldp.write_text(original + "\nsneaky edit\n")
        p.run("phase", "session-expiry", "scrum", ok=False)
        lldp.write_text(original)
        p.run("phase", "session-expiry", "scrum")

        # backlog
        p.write("specmaker/changes/session-expiry/backlog.md", BACKLOG)
        p.run("check", "session-expiry", "backlog")
        p.run("approve-plan", "session-expiry", "--by", "Ravi")
        p.run("phase", "session-expiry", "sprint")

        # sprint
        p.write("src/app.py", "print('hi')\n")
        p.sh("git add -A && git commit -qm base")
        p.run("sprint-start", "session-expiry", "1")
        self.assertTrue(p.state()["sprints"]["1"]["base_sha"])
        p.write("specmaker/changes/session-expiry/sprints/sprint-01.md", SPRINT)
        p.write("src/session.py", "def idle_ok(m):\n    return m < 30\n")
        p.write("tests/test_session.py",
                "# covers: AUTH-01.1\ndef test_expired():\n    pass\n")
        bl = p.change() / "backlog.md"
        bl.write_text(bl.read_text().replace("- [ ] T1.1", "- [x] T1.1").replace("- [ ] T1.2", "- [x] T1.2"))
        p.sh("git add -A && git commit -qm build")
        p.run("gates", "session-expiry", "1")
        p.write("specmaker/changes/session-expiry/reviews/sprint-01-verification.md", "# v\n\nVerdict: PASS\n")

        # AUTH-01.2 has no test -> sign-off refused
        r = p.run("signoff", "session-expiry", "1", "--by", "Ravi", ok=False)
        self.assertIn("AUTH-01.2", r.stdout)

        # add the test, but gates are now stale (HEAD moved)
        p.write("tests/test_session.py",
                "# covers: AUTH-01.1\ndef test_expired():\n    pass\n# covers: AUTH-01.2\ndef test_active():\n    pass\n")
        p.sh("git add -A && git commit -qm tests")
        r = p.run("signoff", "session-expiry", "1", "--by", "Ravi", ok=False)
        self.assertIn("re-run gates", r.stdout)
        p.run("gates", "session-expiry", "1")

        # out-of-boundary file -> refused until declared
        p.write("src/unplanned.py", "x = 1\n")
        p.sh("git add -A && git commit -qm unplanned")
        p.run("gates", "session-expiry", "1")
        r = p.run("signoff", "session-expiry", "1", "--by", "Ravi", ok=False)
        self.assertIn("src/unplanned.py", r.stdout)
        sp = p.change() / "sprints" / "sprint-01.md"
        sp.write_text(sp.read_text().replace(
            "## Deviations\n", "## Deviations\n- [x] src/unplanned.py - shared helper needed (L-001)\n"))
        p.run("signoff", "session-expiry", "1", "--by", "Ravi")
        self.assertEqual(p.state()["sprints"]["1"]["status"], "signed-off")

        # trace + export
        t = p.run("trace", "session-expiry").stdout
        self.assertIn("tests/test_session.py", t)
        csv = p.run("export", "session-expiry").stdout
        self.assertIn("S1,Story", csv)

        # retro + archive
        p.run("archive", "session-expiry", ok=False)  # wrong phase
        p.run("phase", "session-expiry", "retro")
        p.run("archive", "session-expiry", ok=False)  # no retro.md
        p.write("specmaker/changes/session-expiry/retro.md", "# Retro\n")
        p.run("archive", "session-expiry", "--dry-run")
        out = p.run("archive", "session-expiry").stdout
        self.assertIn("verified", out)
        living = (p.tmp / "specmaker/specs/identity/session/spec.md").read_text()
        self.assertIn("[AUTH-01] Idle expiry", living)
        self.assertIn("## Requirements", living)
        self.assertNotIn("ADDED", living)
        self.assertNotIn("AUTH-99", p.run("spec").stdout)
        self.assertTrue((p.tmp / "specmaker/adrs/0001-cookie-last-seen.md").is_file())
        self.assertFalse(p.change().exists())
        self.assertEqual(len([d for d in (p.tmp / "specmaker/archive").iterdir() if d.is_dir()]), 1)
        cov = p.run("coverage").stdout
        self.assertIn("2 with tests", cov)

    def test_modify_remove_and_base_drift(self) -> None:
        p = self.p
        p.run("init")
        chat_gates(p)
        living = SPEC.replace("## ADDED Requirements", "## Requirements").split("<!--")[0]
        living = living.replace("## Purpose\n\nKeeps", "## Purpose\n\nKeeps")
        p.write("specmaker/specs/identity/session/spec.md", living + """
### Requirement: [AUTH-02] Legacy remember-me
The system SHALL keep remember-me sessions for 90 days.

#### Scenario: [AUTH-02.1] Remember me
- **WHEN** the user ticks remember-me
- **THEN** the session lasts 90 days
""")
        # two changes touching AUTH-01
        for cid in ("tighten-expiry", "other-change"):
            p.run("new", cid, "--track", "lite")
            p.write(f"specmaker/changes/{cid}/lld.md",
                    "# LLD\n\n> **TL;DR** x\n\n## Architecture\nx\n## Interfaces\nx\n## Test Strategy\nx\n## File Boundary\nsrc/session.py\n")
        delta = """\
# identity/session

## MODIFIED Requirements

### Requirement: [AUTH-01] Idle expiry (renamed)
The system SHALL end a session 15 minutes after its last authenticated request.

#### Scenario: [AUTH-01.1] Idle session expires
- **WHEN** a request arrives after 16 idle minutes
- **THEN** it is rejected with 401 `session_expired`

## REMOVED Requirements

### Requirement: [AUTH-02] Legacy remember-me
**Reason**: security policy.
**Migration**: users sign in again.
"""
        p.write("specmaker/changes/tighten-expiry/specs/identity/session/spec.md", delta)
        p.write("specmaker/changes/other-change/specs/identity/session/spec.md",
                delta.split("## REMOVED")[0].replace("15 minutes", "20 minutes"))
        r = p.run("check", "tighten-expiry", "specs")
        self.assertIn("other-change", r.stdout)  # overlap warning

        # bad delta: ADDED existing id, MODIFIED unknown id
        bad = "# identity/session\n\n## ADDED Requirements\n\n" + delta.split("## MODIFIED Requirements\n\n")[1].split("## REMOVED")[0]
        p.write("specmaker/changes/other-change/specs/identity/session/spec.md", bad)
        r = p.run("check", "other-change", "specs", ok=False)
        self.assertIn("already exists", r.stdout)
        p.write("specmaker/changes/other-change/specs/identity/session/spec.md",
                delta.split("## REMOVED")[0].replace("15 minutes", "20 minutes"))

        def to_retro(cid: str) -> None:
            p.run("set", cid, "docs_only", "true")
            p.run("phase", cid, "accredit")
            p.write(f"specmaker/changes/{cid}/reviews/accredit-r1-readiness.md", REPORT_PASS)
            p.write(f"specmaker/changes/{cid}/accreditation.md", "# A\n")
            p.run("accredit", cid, "--verdict", "approved", "--by", "Ravi")
            p.run("phase", cid, "retro")
            p.write(f"specmaker/changes/{cid}/retro.md", "# R\n")

        to_retro("tighten-expiry")
        to_retro("other-change")
        p.run("set", "other-change", "depends_on", "tighten-expiry")
        p.run("archive", "other-change", ok=False)  # dependency still open
        p.run("archive", "tighten-expiry")
        spec = (p.tmp / "specmaker/specs/identity/session/spec.md").read_text()
        self.assertIn("15 minutes", spec)
        self.assertIn("(renamed)", spec)
        self.assertNotIn("AUTH-02", spec)
        self.assertNotIn("AUTH-01.2", spec)  # MODIFIED replaced the whole block
        # other-change was accredited against the old AUTH-01 -> base drift
        r = p.run("archive", "other-change", ok=False)
        self.assertIn("base drift", r.stdout)

    def test_amend_and_ledger(self) -> None:
        p = self.p
        p.run("init")
        chat_gates(p)
        p.run("new", "session-expiry")
        design(p)
        p.run("phase", "session-expiry", "propose")
        p.run("phase", "session-expiry", "accredit")
        reviews(p)
        p.run("accredit", "session-expiry", "--verdict", "conditional", "--by", "Ravi", ok=False)  # no condition
        p.run("accredit", "session-expiry", "--verdict", "conditional", "--by", "Ravi", "--condition", "add audit log")
        p.run("ledger", "session-expiry", "--kind", "declined", "--ref", "accredit-r1-critic#G2", "Redis is out of scope")
        p.run("ledger", "session-expiry", "second", "entry")
        ledger = (p.change() / "ledger.md").read_text()
        self.assertIn("L-001", ledger)
        self.assertIn("L-002", ledger)
        self.assertIn("DECLINED", ledger)
        p.run("amend", "session-expiry", "--reason", "scope change")
        st = p.state()
        self.assertEqual(st["phase"], "propose")
        self.assertIsNone(st["accreditation"])
        self.assertEqual(len(st["superseded_accreditations"]), 1)
        status = json.loads(p.run("status", "session-expiry", "--json").stdout)
        self.assertIn("propose", status["next"].lower())


class Lint(unittest.TestCase):
    def setUp(self) -> None:
        self.p = Project(git=False)
        self.p.run("init")
        chat_gates(self.p)
        self.p.run("new", "x", "--track", "lite")

    def tearDown(self) -> None:
        self.p.cleanup()

    def spec_errors(self, text: str) -> str:
        self.p.write("specmaker/changes/x/specs/area/spec.md", text)
        r = self.p.run("check", "x", "specs", ok=False)
        return r.stdout

    def test_spec_rules(self) -> None:
        out = self.spec_errors("# area\n\n## Purpose\n\nThis capability does an important thing for users.\n\n"
                               "## ADDED Requirements\n\n### Requirement: No id here\nThe system SHALL x.\n")
        self.assertIn("needs an ID", out)
        out = self.spec_errors("# area\n\n## Purpose\n\nThis capability does an important thing for users.\n\n"
                               "## ADDED Requirements\n\n### Requirement: [AR-01] Thing\nThe system does x.\n\n"
                               "#### Scenario: [AR-01.1] s\n- **THEN** y\n")
        self.assertIn("SHALL or MUST", out)
        self.assertIn("WHEN", out)
        out = self.spec_errors("# area\n\n## ADDED Requirements\n\n### Requirement: [AR-01] Thing\nThe system SHALL x.\n\n"
                               "#### Scenario: [AR-02.1] s\n- **WHEN** a\n- **THEN** b\n")
        self.assertIn("Purpose", out)
        self.assertIn("is under requirement", out)

    def test_backlog_rules(self) -> None:
        p = self.p
        p.write("specmaker/changes/x/specs/area/spec.md",
                "# area\n\n## Purpose\n\nThis capability does an important thing for users.\n\n"
                "## ADDED Requirements\n\n### Requirement: [AR-01] Thing\nThe system SHALL x.\n\n"
                "#### Scenario: [AR-01.1] s\n- **WHEN** a\n- **THEN** b\n\n"
                "#### Scenario: [AR-01.2] t\n- **WHEN** a\n- **THEN** c\n")
        p.write("specmaker/changes/x/backlog.md", textwrap.dedent("""\
            # Backlog
            #### S1 - story one
            - **Covers**: AR-01.1, AR-09.9
            - **Points**: 4
            - **Depends**: S2
            - [ ] T1.1 do it - files: a.py
            #### S2 - story two
            - **Covers**: AR-01.1
            - **Points**: 2
            - **Depends**: S1
            - [ ] T3.1 wrong number - files: b.py
            ## Sprint Plan
            | Sprint | Goal | Stories |
            |---|---|---|
            | 1 | g | S1 |
            | 3 | h | S2 |
            """))
        out = p.run("check", "x", "backlog", ok=False).stdout
        for needle in ("AR-09.9", "points '4'", "AR-01.2", "cycle", "T3.1", "without gaps"):
            self.assertIn(needle, out, needle)


if __name__ == "__main__":
    unittest.main()


class Example(unittest.TestCase):
    """The worked example in examples/acme-notes must stay valid; the docs point at it."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="specmaker-example-"))
        shutil.copytree(REPO / "examples" / "acme-notes", self.tmp / "acme-notes")
        self.dir = self.tmp / "acme-notes"

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_s(self, *args: str) -> subprocess.CompletedProcess:
        r = subprocess.run([sys.executable, str(SCRIPT), *args], cwd=self.dir, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, f"{args}: {r.stdout}\n{r.stderr}")
        return r

    def test_example_is_valid_and_archives(self) -> None:
        out = self.run_s("check", "idle-session-timeout").stdout
        self.assertNotIn("FAIL", out)
        self.assertNotIn("LOCK BROKEN", self.run_s("status").stdout)
        trace = self.run_s("trace", "idle-session-timeout").stdout
        self.assertIn("4 with tests, 0 without", trace)
        tests = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests"], cwd=self.dir,
                               env={**os.environ, "PYTHONPATH": "src"}, capture_output=True, text=True)
        self.assertEqual(tests.returncode, 0, tests.stderr)
        self.run_s("archive", "idle-session-timeout")
        spec = (self.dir / "specmaker/specs/identity/session/spec.md").read_text()
        self.assertIn("[SESS-03] Absolute session lifetime", spec)
        self.assertIn("idle for 30 minutes", spec)
        self.assertIn("[SESS-02.2] Sign-out invalidates the token", spec)
        self.assertEqual(len(list((self.dir / "specmaker/adrs").glob("*.md"))), 2)
        self.assertIn("5 with tests", self.run_s("coverage").stdout)


class Installer(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="specmaker-install-"))

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def sh(self, *args: str, ok: bool = True) -> subprocess.CompletedProcess:
        r = subprocess.run(["bash", str(REPO / "install.sh"), *args], cwd=self.tmp, capture_output=True, text=True)
        self.assertEqual(r.returncode == 0, ok, r.stdout + r.stderr)
        return r

    def test_install_variants(self) -> None:
        self.sh("--agent", "opencode")
        names = sorted(p.name for p in (self.tmp / ".opencode/skills").iterdir())
        self.assertEqual(len(names), 7)
        self.assertNotIn("specmaker-monorepo", names)          # optional companion: only with its flag
        self.sh("--agent", "opencode", ok=False)  # exists, no --force
        self.sh("--agent", "opencode", "--force", "--explicit-only")
        md = (self.tmp / ".opencode/skills/specmaker-sprint/SKILL.md").read_text()
        self.assertIn("disable-model-invocation: true", md)
        self.assertIn("opencode/autoinvoke: false", md)
        self.assertTrue(md.startswith("---\nname: specmaker-sprint\n"))
        self.sh("--agent", "claude", "--link")
        self.assertTrue((self.tmp / ".claude/skills/specmaker").is_symlink())
        self.sh("--link", "--explicit-only", ok=False)
        self.sh("--agent", "claude", "--uninstall")
        self.assertFalse((self.tmp / ".claude/skills/specmaker").exists())
        self.sh("--agent", "claude", "--with-monorepo")
        self.assertTrue((self.tmp / ".claude/skills/specmaker-monorepo/assets/tools/go_guard/guard.py").is_file())
        self.sh("--agent", "claude", "--uninstall")             # removes optional skills too
        self.assertFalse((self.tmp / ".claude/skills/specmaker-monorepo").exists())
        # installed script works from the installed location
        r = subprocess.run([sys.executable, str(self.tmp / ".opencode/skills/specmaker/scripts/specmaker.py"), "init"],
                           cwd=self.tmp, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((self.tmp / "specmaker/project.md").is_file())


class SkillFiles(unittest.TestCase):
    """Frontmatter and cross-references of every SKILL.md."""

    def test_frontmatter_and_links(self) -> None:
        import re
        for d in sorted((REPO / "skills").iterdir()):
            md = (d / "SKILL.md").read_text()
            self.assertTrue(md.startswith("---\n"), d.name)
            head = md[4:].split("\n---\n", 1)[0]
            self.assertRegex(head, rf"(?m)^name: {re.escape(d.name)}$")
            self.assertRegex(d.name, r"^[a-z0-9]+(-[a-z0-9]+)*$")
            desc = re.search(r"(?ms)^description: >-\n(.*?)^\S", head + "\nX")
            self.assertTrue(desc and 50 < len(" ".join(desc.group(1).split())) <= 1024, d.name)
            self.assertLess(len(md.encode()), 16_000, f"{d.name} SKILL.md too long")
            for link in re.findall(r"\]\(((?:references|assets)/[^)#]+)", md):
                self.assertTrue((d / link).exists(), f"{d.name}: broken link {link}")
            for rel in re.findall(r"`(assets/templates/[\w.-]+)`", md):
                self.assertTrue((d / rel).exists(), f"{d.name}: missing {rel}")


class HumanGates(unittest.TestCase):
    """In terminal mode an agent (no TTY) cannot record a verdict; a person at a terminal can."""

    def setUp(self) -> None:
        self.p = Project()
        p = self.p
        p.run("init")
        set_gate_mode(p, "terminal")
        p.run("new", "session-expiry")
        design(p)
        p.run("phase", "session-expiry", "propose")
        p.run("phase", "session-expiry", "accredit")
        reviews(p)

    def tearDown(self) -> None:
        self.p.cleanup()

    def test_refused_without_terminal(self) -> None:
        r = self.p.run("accredit", "session-expiry", "--verdict", "approved", "--by", "Alex", ok=False)
        self.assertEqual(r.returncode, 3)
        self.assertIn("interactive terminal", r.stderr)
        self.assertIn("accredit session-expiry --verdict approved", r.stderr)
        self.assertIsNone(self.p.state()["accreditation"])

    def test_accepted_from_terminal(self) -> None:
        import pty
        master, slave = pty.openpty()
        os.write(master, b"Alex Chen\n")
        r = subprocess.run([sys.executable, str(SCRIPT), "accredit", "session-expiry", "--verdict", "approved"],
                           cwd=self.p.tmp, stdin=slave, capture_output=True, text=True, timeout=30)
        os.close(slave)
        os.close(master)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        acc = self.p.state()["accreditation"]
        self.assertEqual((acc["by"], acc["via"]), ("Alex Chen", "terminal"))

    def test_typed_name_must_match(self) -> None:
        import pty
        master, slave = pty.openpty()
        os.write(master, b"Someone Else\n")
        r = subprocess.run([sys.executable, str(SCRIPT), "accredit", "session-expiry", "--verdict", "approved",
                            "--by", "Alex Chen"], cwd=self.p.tmp, stdin=slave, capture_output=True, text=True, timeout=30)
        os.close(slave)
        os.close(master)
        self.assertEqual(r.returncode, 3)
        self.assertIsNone(self.p.state()["accreditation"])


class Packaging(unittest.TestCase):
    """Claude Code plugin/marketplace manifests and skills-CLI discovery rules."""

    def test_manifests(self) -> None:
        plugin = json.loads((REPO / ".claude-plugin/plugin.json").read_text())
        market = json.loads((REPO / ".claude-plugin/marketplace.json").read_text())
        self.assertEqual(plugin["name"], "specmaker")
        self.assertEqual(plugin["license"], "MIT")
        self.assertTrue(market["owner"]["name"])
        entry = market["plugins"][0]
        self.assertEqual((entry["name"], entry["source"]), ("specmaker", "./"))
        versions = {plugin["version"]}
        for d in (REPO / "skills").iterdir():
            head = (d / "SKILL.md").read_text().split("\n---\n", 1)[0]
            m = __import__("re").search(r'version: "([^"]+)"', head)
            versions.add(m.group(1))
        self.assertEqual(len(versions), 1, f"versions differ: {versions}")

    def test_skills_cli_layout(self) -> None:
        # the skills CLI names installed folders after frontmatter `name`; they must equal the source folders
        import re
        names = []
        for d in sorted((REPO / "skills").iterdir()):
            head = (d / "SKILL.md").read_text().split("\n---\n", 1)[0]
            names.append(re.search(r"(?m)^name: (.+)$", head).group(1).strip())
            self.assertEqual(names[-1], d.name)
        self.assertIn("specmaker", names)
        self.assertEqual(len(names), 8)                        # seven core skills + optional specmaker-monorepo
        # no other SKILL.md in the repo that the CLI could pick up by accident
        stray = [p for p in REPO.rglob("SKILL.md") if "skills" not in p.relative_to(REPO).parts[:1]
                 and ".git" not in p.parts]
        self.assertEqual(stray, [])


class ChangeRequests(unittest.TestCase):
    """Intake, sprint freeze, batched decisions, impact, rewind with backup, amend, reopen on re-approval."""

    def setUp(self) -> None:
        self.p = p = Project()
        p.run("init")
        chat_gates(p)
        set_gates(p)
        pm = p.tmp / "specmaker/project.md"
        text = pm.read_text()
        self.assertIn("- Sprint freeze: on", text)  # template default
        pm.write_text(text.replace("- Max amendments per change: 3", "- Max amendments per change: 2"))
        p.run("new", "session-expiry")
        design(p)
        p.run("phase", "session-expiry", "propose")
        p.run("phase", "session-expiry", "accredit")
        reviews(p)
        p.run("accredit", "session-expiry", "--verdict", "approved", "--by", "Ravi")
        p.run("phase", "session-expiry", "scrum")
        p.write("specmaker/changes/session-expiry/backlog.md", BACKLOG)
        p.run("approve-plan", "session-expiry", "--by", "Ravi")
        p.run("phase", "session-expiry", "sprint")
        p.write("src/app.py", "print('hi')\n")
        p.sh("git add -A && git commit -qm base")
        p.run("sprint-start", "session-expiry", "1")
        p.write("specmaker/changes/session-expiry/sprints/sprint-01.md", SPRINT)
        p.write("src/session.py", "def idle_ok(m):\n    return m < 30\n")
        p.write("tests/test_session.py", "# covers: AUTH-01.1\n# covers: AUTH-01.2\ndef test_x():\n    pass\n")
        bl = p.change() / "backlog.md"
        bl.write_text(bl.read_text().replace("- [ ] T1.1", "- [x] T1.1").replace("- [ ] T1.2", "- [x] T1.2"))
        p.sh("git add -A && git commit -qm build")

    def tearDown(self) -> None:
        self.p.cleanup()

    def test_freeze_batching_rewind_amend_reopen(self) -> None:
        p, cid = self.p, "session-expiry"
        # intake during the sprint: parked, nothing else changes
        out = p.run("cr", "add", cid, "--title", "Make idle timeout configurable", "--by", "Support").stdout
        self.assertIn("CR-001 recorded as PARKED", out)
        self.assertTrue((p.change() / "requests/CR-001.md").is_file())
        self.assertIn("freeze", p.run("status", cid).stdout)
        # freeze: a non-blocker cannot be accepted mid-sprint, but can be rejected or deferred
        r = p.run("cr", "decide", cid, "CR-001", "--outcome", "amend", "--reason", "x", "--by", "Ravi", ok=False)
        self.assertIn("sprint freeze", r.stderr)
        p.run("cr", "add", cid, "--title", "Dark mode", "--by", "Marketing")
        p.run("cr", "decide", cid, "CR-002", "--outcome", "defer", "--reason", "new scope", "--by", "Ravi")
        # blocker: allowed through the freeze
        p.run("cr", "add", cid, "--title", "Idle limit must be 15 minutes (policy)", "--by", "Security", "--blocker")
        self.assertIn("CR-003", p.run("status", cid).stdout + p.run("cr", "list", cid).stdout)
        p.run("cr", "decide", cid, "CR-003", "--outcome", "amend", "--reason", "policy", "--by", "Ravi")
        # amend refuses the frozen non-blocker and requires --cr
        p.run("amend", cid, "--reason", "x", ok=False)
        # impact before editing: name the requirement
        imp = p.run("impact", cid, "--reqs", "AUTH-01").stdout
        self.assertIn("S1 (S1: active)", imp)
        self.assertIn("tests/test_session.py", imp)
        # uncommitted experiment, then rewind the whole sprint (backup + new commit)
        p.write("src/session.py", "def idle_ok(m):\n    return m < 15  # wip\n")
        head_before = p.sh("git rev-parse HEAD").strip()
        out = p.run("rewind", cid, "--to", "sprint", "--cr", "CR-003", "--by", "Ravi").stdout
        self.assertIn("Backup branch", out)
        self.assertFalse((p.tmp / "src/session.py").exists())          # added in sprint 1 -> removed
        self.assertTrue((p.tmp / "src/app.py").exists())                # before sprint 1 -> kept
        self.assertIn("specmaker-backup/session-expiry/", p.sh("git branch --list 'specmaker-backup/*'"))
        self.assertIn("rewind", p.sh("git log -1 --format=%s"))
        self.assertEqual(p.sh(f"git rev-parse HEAD~1").strip(), head_before)   # history not rewritten
        self.assertIn("- [ ] T1.1", (p.change() / "backlog.md").read_text())   # tasks unticked
        self.assertEqual(p.state()["sprints"]["1"]["status"], "rewound")
        self.assertTrue((p.change() / "ledger.md").read_text().count("REWIND"))
        # amend back to ideate for the blocker; budget counts it
        p.run("amend", cid, "--reason", "security policy", "--cr", "CR-003", "--to", "ideate")
        st = p.state()
        self.assertEqual(st["phase"], "ideate")
        self.assertEqual(st["requests"]["CR-003"]["status"], "applying")
        # parked CR-001 blocks retro later; decide it at the boundary
        p.run("cr", "decide", cid, "CR-001", "--outcome", "reject", "--reason", "not needed for G1", "--by", "Ravi")
        # redesign: change AUTH-01 to 15 minutes, re-approve
        spec = p.change() / "specs/identity/session/spec.md"
        spec.write_text(spec.read_text().replace("30 minutes", "15 minutes"))
        p.run("phase", cid, "propose")
        p.run("phase", cid, "accredit")
        r = p.run("accredit", cid, "--verdict", "approved", "--by", "Ravi", ok=False)
        self.assertIn("needs a new report", r.stdout)          # old reviews do not count after an amendment
        reviews(p, rnd=2)
        p.run("accredit", cid, "--verdict", "approved", "--by", "Ravi")
        st = p.state()
        self.assertEqual(st["requests"]["CR-003"]["status"], "applied")
        self.assertEqual(st["accreditation"]["changed_requirements"], ["AUTH-01"])
        self.assertIn("AUTH-01", p.run("impact", cid).stdout)  # default basis: last approved design

    def test_reopen_signed_off_sprint_and_budget(self) -> None:
        p, cid = self.p, "session-expiry"
        p.run("gates", cid, "1")
        p.write("specmaker/changes/session-expiry/reviews/sprint-01-verification.md", "Verdict: PASS\n")
        p.run("signoff", cid, "1", "--by", "Ravi")
        # boundary: non-blocker requests can now be accepted
        p.run("cr", "add", cid, "--title", "Idle limit 20 minutes", "--by", "Product")
        p.run("cr", "decide", cid, "CR-001", "--outcome", "amend", "--reason", "agreed at review", "--by", "Ravi")
        p.run("amend", cid, "--reason", "idle 20", "--cr", "CR-001")
        spec = p.change() / "specs/identity/session/spec.md"
        spec.write_text(spec.read_text().replace("30 minutes", "20 minutes"))
        p.run("phase", cid, "accredit")
        reviews(p, rnd=2)
        out = p.run("accredit", cid, "--verdict", "approved", "--by", "Ravi").stdout
        self.assertIn("sprint 1 REOPENED", out)
        self.assertEqual(p.state()["sprints"]["1"]["status"], "reopened")
        # re-running the sprint needs fresh evidence
        p.run("phase", cid, "scrum")
        p.run("approve-plan", cid, "--by", "Ravi")
        p.run("phase", cid, "sprint")
        p.run("sprint-start", cid, "1")
        r = p.run("signoff", cid, "1", "--by", "Ravi", ok=False)
        self.assertIn("predates", r.stdout)
        # budget: 1 used of 2; two more amendments -> the second is refused without --over-budget
        for k in (2, 3):
            p.run("cr", "add", cid, "--title", f"tweak {k}", "--by", "Product", "--blocker")
            p.run("cr", "decide", cid, f"CR-00{k}", "--outcome", "amend", "--reason", "r", "--by", "Ravi")
        p.run("amend", cid, "--reason", "t2", "--cr", "CR-002")
        p.run("phase", cid, "accredit")
        reviews(p, rnd=3)
        p.run("accredit", cid, "--verdict", "approved", "--by", "Ravi")
        p.run("phase", cid, "scrum")
        r = p.run("amend", cid, "--reason", "t3", "--cr", "CR-003", ok=False)
        self.assertIn("budget", r.stderr)
        p.run("amend", cid, "--reason", "t3", "--cr", "CR-003", "--over-budget", "regulator deadline", "--by", "Ravi")
        self.assertEqual(p.state()["amendments"][-1]["approved"]["by"], "Ravi")


class AuditRegressions(unittest.TestCase):
    """Regression tests for findings of the independent audit (2026-11-25)."""

    def setUp(self) -> None:
        self.p = Project()
        self.p.run("init")
        chat_gates(self.p)

    def tearDown(self) -> None:
        self.p.cleanup()

    def living(self, extra_intro: str = "") -> str:
        return ("# identity/session\n\n## Purpose\n\nKeeps sessions valid only while users are active.\n\n"
                "## Requirements\n\n" + extra_intro +
                "### Requirement: [AUTH-02] Token format\nThe system SHALL issue opaque tokens.\n\n"
                "#### Scenario: [AUTH-02.1] Example\n- **WHEN** a user signs in\n- **THEN** the token looks like:\n\n"
                "```text\n## not a heading\ntoken: abc\n```\n\n"
                "### Requirement: [AUTH-03] Sign out\nThe system SHALL end sessions on sign-out.\n\n"
                "#### Scenario: [AUTH-03.1] Sign out\n- **WHEN** the user signs out\n- **THEN** the token is invalid\n\n"
                "## Notes\n\nTrailer stays.\n")

    def to_retro_docs_only(self, cid: str, delta: str) -> None:
        p = self.p
        p.run("new", cid, "--track", "lite")
        p.run("set", cid, "docs_only", "true")
        p.write(f"specmaker/changes/{cid}/lld.md", "# LLD\n\n> **TL;DR** x\n\n## Architecture\nx\n## Interfaces\nx\n"
                "## Test Strategy\nx\n## File Boundary\nnone (documentation only)\n")
        p.write(f"specmaker/changes/{cid}/specs/identity/session/spec.md", delta)
        p.run("phase", cid, "accredit")
        p.write(f"specmaker/changes/{cid}/reviews/accredit-r1-readiness.md", REPORT_PASS)
        p.write(f"specmaker/changes/{cid}/accreditation.md", "# A\n")
        p.run("accredit", cid, "--verdict", "approved", "--by", "Ravi")
        p.run("phase", cid, "retro")
        p.write(f"specmaker/changes/{cid}/retro.md", "# R\n")

    ADD = ("# identity/session\n\n## ADDED Requirements\n\n### Requirement: [AUTH-04] Idle expiry\n"
           "The system SHALL end idle sessions.\n\n#### Scenario: [AUTH-04.1] Idle\n- **WHEN** idle 30 minutes\n"
           "- **THEN** the session ends\n")

    def test_merge_keeps_fences_intro_and_trailer(self) -> None:
        p = self.p
        spec = p.write("specmaker/specs/identity/session/spec.md",
                       self.living("All timeouts are measured on the server.\n\n"))
        self.to_retro_docs_only("add-idle", self.ADD)
        p.run("archive", "add-idle")
        text = spec.read_text()
        self.assertIn("All timeouts are measured on the server.", text)
        self.assertIn("```text\n## not a heading\ntoken: abc\n```", text)
        self.assertIn("Trailer stays.", text)
        self.assertLess(text.index("[AUTH-03]"), text.index("[AUTH-04]"))
        self.assertLess(text.index("[AUTH-04]"), text.index("## Notes"))
        reqs = json.loads(p.run("spec", "--json").stdout)["identity/session"]
        self.assertEqual([r["id"] for r in reqs], ["AUTH-02", "AUTH-03", "AUTH-04"])

    def test_failed_merge_writes_nothing(self) -> None:
        p = self.p
        spec = p.write("specmaker/specs/identity/session/spec.md", self.living())
        original = spec.read_text()
        self.to_retro_docs_only("add-idle", self.ADD)
        # living spec changes underneath after accreditation: MODIFY target vanishes -> merge must not half-write
        bad = self.ADD + ("\n## MODIFIED Requirements\n\n### Requirement: [AUTH-03] Sign out\n"
                          "The system SHALL end sessions on sign-out.\n\n#### Scenario: [AUTH-03.1] Sign out\n"
                          "- **WHEN** the user signs out\n- **THEN** the token is invalid\n")
        p.write("specmaker/changes/add-idle/specs/identity/session/spec.md", bad)
        spec.write_text(original.replace("### Requirement: [AUTH-03]", "### Requirement: [AUTH-09]")
                        .replace("[AUTH-03.1]", "[AUTH-09.1]"))
        before = spec.read_text()
        r = p.run("archive", "add-idle", ok=False)
        self.assertIn("design changed after accreditation", r.stdout)
        self.assertEqual(spec.read_text(), before)
        self.assertEqual(p.state("add-idle")["phase"], "retro")

    def test_archive_name_clash_changes_nothing(self) -> None:
        p = self.p
        p.write("specmaker/specs/identity/session/spec.md", self.living())
        self.to_retro_docs_only("add-idle", self.ADD)
        import datetime
        (p.tmp / f"specmaker/archive/{datetime.date.today().isoformat()}-add-idle").mkdir(parents=True)
        r = p.run("archive", "add-idle", ok=False)
        self.assertIn("already exists", r.stdout)
        self.assertEqual(p.state("add-idle")["phase"], "retro")
        self.assertNotIn("AUTH-04", (p.tmp / "specmaker/specs/identity/session/spec.md").read_text())

    def test_depends_on_cycle_is_named(self) -> None:
        p = self.p
        p.write("specmaker/specs/identity/session/spec.md", self.living())
        self.to_retro_docs_only("a-one", self.ADD)
        self.to_retro_docs_only("b-two", self.ADD.replace("AUTH-04", "AUTH-05"))
        p.run("set", "a-one", "depends_on", "b-two")
        p.run("set", "b-two", "depends_on", "a-one")
        self.assertIn("cycle", p.run("archive", "a-one", ok=False).stdout)

    def test_wont_only_coverage_is_an_error(self) -> None:
        p = self.p
        p.run("new", "x", "--track", "lite")
        p.write("specmaker/changes/x/specs/area/spec.md",
                "# area\n\n## Purpose\n\nThis capability does an important thing for users.\n\n"
                "## ADDED Requirements\n\n### Requirement: [AR-01] Thing\nThe system SHALL x.\n\n"
                "#### Scenario: [AR-01.1] s\n- **WHEN** a\n- **THEN** b\n\n#### Scenario: [AR-01.2] t\n- **WHEN** a\n- **THEN** c\n")
        p.write("specmaker/changes/x/backlog.md", textwrap.dedent("""\
            # Backlog
            #### S1 - one
            - **Covers**: AR-01.1
            - **Points**: 2
            - [ ] T1.1 do - files: a.py
            #### S2 - two
            - **Covers**: AR-01.2
            - **Points**: 2
            - **Priority**: Won't
            - [ ] T2.1 do - files: b.py
            ## Sprint Plan
            | Sprint | Goal | Stories |
            |---|---|---|
            | 1 | g | S1 |
            """))
        self.assertIn("covered only by Won't", p.run("check", "x", "backlog", ok=False).stdout)

    def test_tilde_fences_are_skipped(self) -> None:
        p = self.p
        p.run("new", "x", "--track", "lite")
        p.write("specmaker/changes/x/specs/area/spec.md",
                "# area\n\n## Purpose\n\nThis capability does an important thing for users.\n\n"
                "## ADDED Requirements\n\n### Requirement: [AR-01] Thing\nThe system SHALL x.\n\n"
                "#### Scenario: [AR-01.1] s\n- **WHEN** a\n- **THEN** b\n\n~~~~markdown\n"
                "### Requirement: no id inside a tilde fence\n~~~~\n")
        p.run("check", "x", "specs")


class GateHardening(unittest.TestCase):
    def setUp(self) -> None:
        self.p = Project()
        self.p.run("init")
        self.pm = self.p.tmp / "specmaker/project.md"

    def tearDown(self) -> None:
        self.p.cleanup()

    def mode(self) -> str:
        self.p.run("new", "probe")
        m = json.loads(self.p.run("status", "probe", "--json").stdout)["human_gates"]
        shutil.rmtree(self.p.change("probe"))
        return m

    def test_mode_parsing_fails_closed(self) -> None:
        base = self.pm.read_text()
        for line, expected in [("- **Human gates**: chat", "chat"), ("- Human gates: `chat`", "chat"),
                               ("- Human gates: **terminal**", "terminal"), ("- Human gates: maybe", "signed"),
                               ("- Human gates: signed", "signed"), ("", "signed")]:
            self.pm.write_text(base.replace("- Human gates: signed", line))
            self.assertEqual(self.mode(), expected, line)

    def test_editing_project_md_does_not_loosen_existing_change(self) -> None:
        p = self.p
        set_gate_mode(p, "terminal")
        p.run("new", "x")                                   # recorded as terminal
        set_gate_mode(p, "chat")
        self.assertEqual(json.loads(p.run("status", "x", "--json").stdout)["human_gates"], "terminal")
        r = p.run("set", "x", "human_gates", "chat", ok=False)   # loosening is itself a human gate
        self.assertEqual(r.returncode, 3)

    def test_terminal_decision_inside_agent_is_flagged(self) -> None:
        import pty
        p = self.p
        set_gate_mode(p, "terminal")
        p.run("new", "x")
        p.run("cr", "add", "x", "--title", "t", "--by", "someone")
        master, slave = pty.openpty()
        os.write(master, b"Alex Chen\n")
        env = {**os.environ, "CLAUDECODE": "1"}
        r = subprocess.run([sys.executable, str(SCRIPT), "cr", "decide", "x", "CR-001", "--outcome", "reject",
                            "--reason", "r"], cwd=p.tmp, stdin=slave, capture_output=True, text=True, env=env, timeout=30)
        os.close(slave)
        os.close(master)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("WARNING", r.stdout)
        self.assertIn("recorded from inside an agent process", p.run("status", "x").stdout)


class ChangeControlGaps(unittest.TestCase):
    def setUp(self) -> None:
        self.p = p = Project()
        p.run("init")
        chat_gates(p)
        set_gates(p)
        p.run("new", "session-expiry")
        design(p)
        p.run("phase", "session-expiry", "propose")
        p.run("phase", "session-expiry", "accredit")
        reviews(p)
        p.run("accredit", "session-expiry", "--verdict", "approved", "--by", "Ravi")
        p.run("phase", "session-expiry", "scrum")
        p.write("specmaker/changes/session-expiry/backlog.md", BACKLOG)
        p.run("approve-plan", "session-expiry", "--by", "Ravi")
        p.run("phase", "session-expiry", "sprint")
        p.sh("git add -A && git commit -qm base")

    def tearDown(self) -> None:
        self.p.cleanup()

    def test_parked_requests_block_next_sprint(self) -> None:
        p, cid = self.p, "session-expiry"
        p.run("cr", "add", cid, "--title", "nice to have", "--by", "PM")
        self.assertIn("must be triaged first", p.run("sprint-start", cid, "1", ok=False).stderr)
        p.run("cr", "decide", cid, "CR-001", "--outcome", "defer", "--reason", "later", "--by", "Ravi")
        p.run("sprint-start", cid, "1")

    def test_wording_only_amend(self) -> None:
        p, cid = self.p, "session-expiry"
        self.assertIn("--cr", p.run("amend", cid, "--reason", "typo", ok=False).stderr)
        p.run("amend", cid, "--reason", "typo in AUTH-01", "--wording-only", "--by", "Ravi")
        spec = p.change() / "specs/identity/session/spec.md"
        spec.write_text(spec.read_text().replace("last authenticated request", "most recent authenticated request"))
        p.run("phase", cid, "accredit")
        out = p.run("accredit", cid, "--verdict", "approved", "--by", "Ravi").stdout  # no fresh review needed
        self.assertIn("wording-only amendment", out)
        # an ID change is not wording-only
        p.run("phase", cid, "scrum")
        p.run("amend", cid, "--reason", "sneaky", "--wording-only", "--by", "Ravi")
        spec.write_text(spec.read_text().replace("[AUTH-01.2]", "[AUTH-01.3]"))
        p.run("phase", cid, "accredit")
        self.assertIn("not a wording-only", p.run("accredit", cid, "--verdict", "approved", "--by", "Ravi", ok=False).stdout)

    def test_budget_with_annotation(self) -> None:
        p, cid = self.p, "session-expiry"
        pm = p.tmp / "specmaker/project.md"
        pm.write_text(pm.read_text().replace("- Max amendments per change: 3", "- Max amendments per change: 1 (then start over)"))
        p.run("cr", "add", cid, "--title", "a", "--by", "PM", "--blocker")
        p.run("cr", "decide", cid, "CR-001", "--outcome", "amend", "--reason", "r", "--by", "Ravi")
        p.run("amend", cid, "--reason", "first", "--cr", "CR-001")
        p.run("phase", cid, "accredit")
        reviews(p, rnd=2)
        p.run("accredit", cid, "--verdict", "approved", "--by", "Ravi")
        p.run("phase", cid, "scrum")
        p.run("cr", "add", cid, "--title", "b", "--by", "PM", "--blocker")
        p.run("cr", "decide", cid, "CR-002", "--outcome", "amend", "--reason", "r", "--by", "Ravi")
        self.assertIn("budget", p.run("amend", cid, "--reason", "second", "--cr", "CR-002", ok=False).stderr)


class GitRobustness(unittest.TestCase):
    def setUp(self) -> None:
        self.p = Project()

    def tearDown(self) -> None:
        self.p.cleanup()

    def drive_to_sprint(self, sub: str = "") -> Path:
        """Workspace at <repo>/<sub>/specmaker; returns the project dir."""
        p = self.p
        proj = p.tmp / sub if sub else p.tmp
        proj.mkdir(parents=True, exist_ok=True)

        def run(*args: str, ok: bool = True) -> subprocess.CompletedProcess:
            r = subprocess.run([sys.executable, str(SCRIPT), *args], cwd=proj, capture_output=True, text=True)
            self.assertEqual(r.returncode == 0, ok, f"{args}\n{r.stdout}\n{r.stderr}")
            return r
        self.run_s = run
        run("init")
        pm = proj / "specmaker/project.md"
        pm.write_text(re.sub(r"(?m)^- Human gates: \w+$", "- Human gates: chat", pm.read_text())
                      .replace('- test: `echo "replace with your test command" && exit 1`', "- test: `python3 -c 'pass'`"))
        run("new", "session-expiry")
        c = "specmaker/changes/session-expiry/"
        for rel, text in ((c + "hld.md", HLD), (c + "lld.md", lld()), (c + "specs/identity/session/spec.md", SPEC),
                          (c + "adrs/0001-cookie-last-seen.md", ADR)):
            (proj / rel).parent.mkdir(parents=True, exist_ok=True)
            (proj / rel).write_text(text)
        run("phase", "session-expiry", "propose")
        run("phase", "session-expiry", "accredit")
        for lens in ("consistency", "readiness"):
            (proj / c / f"reviews/accredit-r1-{lens}.md").write_text(REPORT_PASS)
        (proj / c / "accreditation.md").write_text("# A\n")
        run("accredit", "session-expiry", "--verdict", "approved", "--by", "Ravi")
        run("phase", "session-expiry", "scrum")
        (proj / c / "backlog.md").write_text(BACKLOG.replace("files: src/session.py", "files: src/session.py, src/café.py")
                                         .replace("files: tests/test_session.py", "files: tests/test_session.py, tests/test_sessión.py"))
        run("approve-plan", "session-expiry", "--by", "Ravi")
        run("phase", "session-expiry", "sprint")
        (proj / ".gitignore").write_text("")
        p.sh("git add -A && git commit -qm base")
        run("sprint-start", "session-expiry", "1")
        (proj / c / "sprints/sprint-01.md").write_text(SPRINT)
        return proj

    def build_and_evidence(self, proj: Path) -> None:
        c = proj / "specmaker/changes/session-expiry"
        (proj / "src").mkdir(exist_ok=True)
        (proj / "src/session.py").write_text("x = 1\n")
        (proj / "src/café.py").write_text("y = 1\n")
        (proj / "tests").mkdir(exist_ok=True)
        (proj / "tests/test_sessión.py").write_text("# covers: AUTH-01.1\n# covers: AUTH-01.2\n")
        (proj / "src/__pycache__").mkdir(exist_ok=True)
        (proj / "src/__pycache__/session.cpython-313.pyc").write_bytes(b"\0\1")
        bl = c / "backlog.md"
        bl.write_text(bl.read_text().replace("- [ ] T1.1", "- [x] T1.1").replace("- [ ] T1.2", "- [x] T1.2"))
        self.p.sh("git add -A && git commit -qm build")
        self.run_s("gates", "session-expiry", "1")
        (c / "reviews/sprint-01-verification.md").write_text("Verdict: PASS\n")
        self.p.sh("git add -A && git commit -qm 'evidence (specmaker only)'")   # after gates: must not break sign-off

    def test_unicode_paths_pycache_and_specmaker_commit(self) -> None:
        proj = self.drive_to_sprint()
        self.build_and_evidence(proj)
        self.assertIn("2 with tests", self.run_s("trace", "session-expiry").stdout)
        self.run_s("signoff", "session-expiry", "1", "--by", "Ravi")

    def test_monorepo_subdirectory(self) -> None:
        proj = self.drive_to_sprint("apps/web")
        self.build_and_evidence(proj)
        self.run_s("signoff", "session-expiry", "1", "--by", "Ravi")

    def test_rewind_unicode_quotes_and_monorepo(self) -> None:
        proj = self.drive_to_sprint("apps/web")
        (proj / "src").mkdir(exist_ok=True)
        (proj / "src/café.py").write_text("y = 1\n")
        (proj / 'src/q"uote.py').write_text("z = 1\n")
        (proj / "src/session.py").write_text("x = 1\n")
        self.p.sh("git add -A && git commit -qm build")
        (proj / "src/wip.py").write_text("wip\n")              # untracked work in progress
        out = self.run_s("rewind", "session-expiry", "--to", "sprint", "--by", "Ravi").stdout
        for name in ("café.py", 'q"uote.py', "session.py", "wip.py"):
            self.assertFalse((proj / "src" / name).exists(), name)
        self.assertIn(":(exclude)specmaker", out)
        self.assertIn("git stash pop", out)
        self.assertTrue((proj / "specmaker/changes/session-expiry/change.json").is_file())

    def test_deviation_paths_match_exactly(self) -> None:
        proj = self.drive_to_sprint()
        c = proj / "specmaker/changes/session-expiry"
        sp = c / "sprints/sprint-01.md"
        sp.write_text(sp.read_text().replace("## Deviations\n", "## Deviations\n- [x] src/data.py - shared helper\n"))
        (proj / "src").mkdir(exist_ok=True)
        (proj / "a.py").write_text("1\n")
        self.build_and_evidence(proj)
        self.run_s("gates", "session-expiry", "1")
        r = self.run_s("signoff", "session-expiry", "1", "--by", "Ravi", ok=False)
        self.assertIn("a.py changed but is outside", r.stdout)

    def test_bad_sprint_check_argument(self) -> None:
        self.drive_to_sprint()
        r = self.run_s("check", "session-expiry", "sprint:abc", ok=False)
        self.assertIn("sprint:<number>", r.stderr)
        self.assertNotIn("Traceback", r.stderr)


class SignedGates(unittest.TestCase):
    """Signed human gates: SSH signatures bound to what was approved; forgeries are detected."""

    def setUp(self) -> None:
        self.p = p = Project()
        keys = p.tmp.parent / (p.tmp.name + "-keys")
        keys.mkdir()
        self.keys = keys
        for name in ("alex", "rogue"):
            subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", name, "-f", str(keys / name)], check=True)
        self.signers = keys / "allowed_signers"
        self.env = {**os.environ, "SPECMAKER_ALLOWED_SIGNERS": str(self.signers),
                    "SPECMAKER_SIGNING_KEY": str(keys / "alex")}
        p.run("init")
        set_gates(p)

    def tearDown(self) -> None:
        self.p.cleanup()
        shutil.rmtree(self.keys, ignore_errors=True)

    def s(self, *args: str, ok: bool = True, env: dict = None) -> subprocess.CompletedProcess:
        r = subprocess.run([sys.executable, str(SCRIPT), *args], cwd=self.p.tmp, capture_output=True, text=True,
                           env=env or self.env)
        self.assertEqual(r.returncode == 0, ok, f"{args}\n{r.stdout}\n{r.stderr}")
        return r

    def to_accredit(self) -> None:
        p = self.p
        self.s("approvers", "add", "--principal", "alex@example.com", "--key", str(self.keys / "alex.pub"))
        self.s("new", "session-expiry")
        design(p)
        self.s("phase", "session-expiry", "propose")
        self.s("phase", "session-expiry", "accredit")
        reviews(p)

    def test_signed_flow_and_ci_verify(self) -> None:
        self.to_accredit()
        out = self.s("approvers", "check").stdout
        self.assertIn("USER-WRITABLE", out)
        self.assertIn("software key", out)
        self.s("accredit", "session-expiry", "--verdict", "approved", "--by", "alex@example.com")
        st = self.p.state()
        self.assertEqual(st["accreditation"]["via"], "signed")
        appr = self.p.change() / st["accreditation"]["context"]["approval"]["file"]
        self.assertTrue(appr.is_file() and Path(str(appr) + ".sig").is_file())
        self.s("verify", "--require-signed")
        self.assertIn("hardware", self.s("verify", "--require-hardware", ok=False).stdout)
        self.s("phase", "session-expiry", "scrum")

    def test_unknown_principal_and_wrong_key_are_refused(self) -> None:
        self.to_accredit()
        r = self.s("accredit", "session-expiry", "--verdict", "approved", "--by", "mallory@example.com", ok=False)
        self.assertIn("not an approver", r.stderr)
        rogue = {**self.env, "SPECMAKER_SIGNING_KEY": str(self.keys / "rogue")}
        r = self.s("accredit", "session-expiry", "--verdict", "approved", "--by", "alex@example.com", ok=False, env=rogue)
        self.assertIn("does not verify", r.stderr)
        self.assertIsNone(self.p.state()["accreditation"])
        self.assertEqual(list((self.p.change() / "approvals").glob("*.json")), [])   # nothing left behind

    def test_forgeries_are_detected(self) -> None:
        p = self.p
        self.to_accredit()
        self.s("accredit", "session-expiry", "--verdict", "approved", "--by", "alex@example.com")
        cj = p.change() / "change.json"
        good = cj.read_text()
        # 1. edit the recorded verdict / lock in change.json
        st = json.loads(good)
        st["accreditation"]["lock"]["lld.md"] = "0" * 64
        cj.write_text(json.dumps(st))
        self.assertIn("differs from what was signed", self.s("verify", ok=False).stdout)
        cj.write_text(good)
        # 2. edit the signed statement itself
        stmt = p.change() / st["accreditation"]["context"]["approval"]["file"]
        original = stmt.read_text()
        stmt.write_text(original.replace('"approved"', '"conditional"', 1))
        self.assertIn("does not verify", self.s("verify", ok=False).stdout)
        self.assertIn("APPROVAL PROBLEM", self.s("status").stdout)
        self.s("phase", "session-expiry", "scrum", ok=False)
        stmt.write_text(original)
        # 3. fake a sprint sign-off with no signature
        st = json.loads(good)
        st["sprints"] = {"1": {"status": "signed-off", "by": "alex@example.com", "via": "terminal"}}
        cj.write_text(json.dumps(st))
        self.assertIn("is not signed", self.s("verify", ok=False).stdout)
        cj.write_text(good)
        self.s("verify", "--require-signed")

    def test_ci_rejects_unsigned_history_and_loosening_needs_signature(self) -> None:
        p = self.p
        set_gate_mode(p, "chat")
        self.s("new", "x")
        self.s("cr", "add", "x", "--title", "t", "--by", "pm")
        self.s("cr", "decide", "x", "CR-001", "--outcome", "reject", "--reason", "r", "--by", "Ravi")
        self.s("verify", "x")                                        # local default: chat records are fine
        self.assertIn("is not signed", self.s("verify", "x", "--require-signed", ok=False).stdout)   # CI policy
        # a signed change cannot be loosened without a signature
        set_gate_mode(p, "signed")
        self.s("approvers", "add", "--principal", "alex@example.com", "--key", str(self.keys / "alex.pub"))
        self.s("new", "y")
        set_gate_mode(p, "chat")
        self.assertEqual(json.loads(self.s("status", "y", "--json").stdout)["human_gates"], "signed")
        self.s("set", "y", "human_gates", "chat", ok=False)
        self.s("set", "y", "human_gates", "chat", "--by", "alex@example.com")
        self.assertEqual(json.loads(self.s("status", "y", "--json").stdout)["human_gates"], "chat")


class DocsInSync(unittest.TestCase):
    """The HOW-TO command reference must cover every CLI command and option (spec <-> implementation)."""

    def test_every_command_and_option_is_documented(self) -> None:
        howto = (REPO / "docs/how-to.md").read_text()
        ref = howto[howto.index("## 21. Command reference"):]
        top = subprocess.run([sys.executable, str(SCRIPT), "-h"], capture_output=True, text=True).stdout
        cmds = re.search(r"\{([a-z,\-]+)\}", top).group(1).split(",")
        missing = []
        for cmd in cmds:
            if f"`{cmd}" not in ref:
                missing.append(f"command {cmd}")
            helps = [[cmd]]
            sub = subprocess.run([sys.executable, str(SCRIPT), cmd, "-h"], capture_output=True, text=True).stdout
            m = re.search(r"\{([a-z,\-]+)\}", sub)
            if m and cmd in ("cr", "approvers"):
                helps = [[cmd, x] for x in m.group(1).split(",")]
            for h in helps:
                out = subprocess.run([sys.executable, str(SCRIPT), *h, "-h"], capture_output=True, text=True).stdout
                for opt in set(re.findall(r"(--[a-z][a-z-]+)", out)) - {"--help"}:
                    if opt not in howto:
                        missing.append(f"option {' '.join(h)} {opt}")
        self.assertEqual(missing, [], "document these in docs/how-to.md")


class Brevity(unittest.TestCase):
    """Word budgets are a REVIEW TRIGGER, not a target to cut towards.

    Short skills are easier to follow and to adapt, but quality wins over the budget. When a skill
    goes over: first move detail into references/ or the HOW-TO, and remove true repetition. If the
    remaining text is needed, raise the budget here, in the same change, with a comment saying why.
    Never delete a rule, a check or a needed explanation just to pass this test."""

    BUDGET = {"specmaker": 850,          # core skill: a route map; recipes live in references/recipes.md
              # scrum holds the implementation trigger (complete tree + human plan approval): kept in full
              "specmaker-scrum": 1150,
              # EGM consensus gates and LLD/HLD reconciliation (per-capability approval, drift listing)
              "specmaker-propose": 1150,
              # EGM triage discipline summarised in-skill (full rules in goldfish.md)
              "specmaker-accredit": 1100,
              # optional companion, loaded only for monorepo work; its generator commands must be verbatim
              # and its configuration rules are project quality rules, so they stay in the skill
              "specmaker-monorepo": 1250}
    DEFAULT = 1050                         # each phase skill
    CONVENTIONS = 900                      # read by every phase

    def test_word_budgets(self) -> None:
        over = []
        for d in sorted((REPO / "skills").iterdir()):
            words = len((d / "SKILL.md").read_text().split())
            limit = self.BUDGET.get(d.name, self.DEFAULT)
            if words > limit:
                over.append(f"{d.name}/SKILL.md: {words} words > {limit}")
        conv = len((REPO / "skills/specmaker/references/conventions.md").read_text().split())
        if conv > self.CONVENTIONS:
            over.append(f"conventions.md: {conv} words > {self.CONVENTIONS}")
        self.assertEqual(over, [], "review: move detail into references/ or the HOW-TO; if the text is needed, "
                                   "raise the budget with a reason (see this class's docstring). Never cut guidance to pass.")


class Tidiness(unittest.TestCase):
    """Markdown stays tidy and every skill can locate the shared script."""

    def markdown_files(self) -> list:
        return [p for p in REPO.rglob("*.md") if ".git" not in p.parts]

    def test_no_empty_or_unclosed_code_blocks(self) -> None:
        problems = []
        for p in self.markdown_files():
            text = p.read_text()
            fences = re.findall(r"(?m)^[ \t]*(`{3,}|~{3,})", text)
            if len(fences) % 2:
                problems.append(f"{p.relative_to(REPO)}: unclosed code block")
            for m in re.finditer(r"(?ms)^[ \t]*```[\w-]*\n(.*?)^[ \t]*```", text):
                if not m.group(1).strip():
                    problems.append(f"{p.relative_to(REPO)}:{text[:m.start()].count(chr(10)) + 1}: empty code block")
        self.assertEqual(problems, [])

    def test_every_skill_locates_the_script(self) -> None:
        snippets = {}
        for d in sorted((REPO / "skills").iterdir()):
            if d.name == "specmaker-monorepo":
                continue  # standalone companion: it locates its own folder (test below)
            m = re.search(r"```bash\n(R=\$\(git rev-parse[^\n]+)\n```", (d / "SKILL.md").read_text())
            self.assertIsNotNone(m, f"{d.name}: locate command missing")
            snippets[d.name] = m.group(1)
        self.assertEqual(len(set(snippets.values())), 1, "locate command differs between skills")
        tmp = Path(tempfile.mkdtemp(prefix="specmaker-locate-"))
        try:
            subprocess.run(["git", "init", "-q"], cwd=tmp, check=True)
            subprocess.run(["bash", str(REPO / "install.sh")], cwd=tmp, check=True, capture_output=True)
            (tmp / "src/deep").mkdir(parents=True)
            env = {k: v for k, v in os.environ.items() if k not in ("SPECMAKER_HOME", "CLAUDE_SKILL_DIR")}
            for name, snip in snippets.items():
                out = subprocess.run(["bash", "-c", snip], cwd=tmp / "src/deep", capture_output=True, text=True,
                                     env=env).stdout.strip()
                self.assertEqual(out, ".agents/skills/specmaker", name)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_monorepo_skill_locates_itself(self) -> None:
        text = (REPO / "skills/specmaker-monorepo/SKILL.md").read_text()
        snip = re.search(r"```bash\n(R=\$\(git rev-parse[^\n]+)\n```", text).group(1)
        tmp = Path(tempfile.mkdtemp(prefix="specmaker-locate-mr-"))
        try:
            subprocess.run(["git", "init", "-q"], cwd=tmp, check=True)
            subprocess.run(["bash", str(REPO / "install.sh"), "--with-monorepo"], cwd=tmp, check=True, capture_output=True)
            (tmp / "apps/go").mkdir(parents=True)
            env = {k: v for k, v in os.environ.items() if k != "CLAUDE_SKILL_DIR"}
            out = subprocess.run(["bash", "-c", snip], cwd=tmp / "apps/go", capture_output=True, text=True,
                                 env=env).stdout.strip()
            self.assertEqual(out, ".agents/skills/specmaker-monorepo")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class MonorepoGoGuard(unittest.TestCase):
    """Run the companion skill's go_guard tests (pytest style) without requiring pytest."""

    def test_go_guard(self) -> None:
        guard_dir = REPO / "skills/specmaker-monorepo/assets/tools/go_guard"
        code = ("import sys, tempfile, pathlib\nsys.path.insert(0, sys.argv[1])\nimport test_guard\nfailed = []\n"
                "for name, fn in sorted(vars(test_guard).items()):\n"
                "    if name.startswith('test_') and callable(fn):\n"
                "        with tempfile.TemporaryDirectory() as d:\n"
                "            try:\n                fn(pathlib.Path(d))\n"
                "            except AssertionError as e:\n                failed.append(f'{name}: {e}')\n"
                "print('\\n'.join(failed))\nsys.exit(1 if failed else 0)\n")
        r = subprocess.run([sys.executable, "-c", code, str(guard_dir)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        cli = subprocess.run([sys.executable, str(guard_dir / "guard.py"), "--root", str(REPO)], capture_output=True,
                             text=True)
        self.assertEqual(cli.returncode, 0, cli.stdout + cli.stderr)   # no Go sources here: clean run


class SignedAttacks(SignedGates):
    """Regression tests for the attacks found by the independent review of signed gates (2026-11-25)."""

    def edit_state(self, fn) -> None:
        cj = self.p.change() / "change.json"
        st = json.loads(cj.read_text())
        fn(st)
        cj.write_text(json.dumps(st))

    def fails(self, *args: str, expect: str) -> None:
        r = self.s(*args, ok=False)
        self.assertIn(expect, r.stdout + r.stderr)

    def to_signed_off(self) -> None:
        p = self.p
        self.to_accredit()
        self.s("accredit", "session-expiry", "--verdict", "approved", "--by", "alex@example.com")
        self.s("phase", "session-expiry", "scrum")
        p.write("specmaker/changes/session-expiry/backlog.md", BACKLOG)
        self.s("approve-plan", "session-expiry", "--by", "alex@example.com")
        self.s("phase", "session-expiry", "sprint")
        p.write("src/app.py", "print('hi')\n")
        p.sh("git add -A && git commit -qm base")
        self.s("sprint-start", "session-expiry", "1")
        p.write("specmaker/changes/session-expiry/sprints/sprint-01.md", SPRINT)
        p.write("src/session.py", "x = 1\n")
        p.write("tests/test_session.py", "# covers: AUTH-01.1\n# covers: AUTH-01.2\n")
        bl = p.change() / "backlog.md"
        bl.write_text(bl.read_text().replace("- [ ] T1.1", "- [x] T1.1").replace("- [ ] T1.2", "- [x] T1.2"))
        p.sh("git add -A && git commit -qm build")
        self.s("gates", "session-expiry", "1")
        p.write("specmaker/changes/session-expiry/reviews/sprint-01-verification.md", "Verdict: PASS\n")
        self.s("signoff", "session-expiry", "1", "--by", "alex@example.com")
        self.s("verify", "--require-signed")

    def test_deleting_the_lock_is_caught(self) -> None:
        self.to_accredit()
        self.s("accredit", "session-expiry", "--verdict", "approved", "--by", "alex@example.com")
        lld_path = self.p.change() / "lld.md"
        lld_path.write_text(lld_path.read_text() + "\nchanged after approval\n")
        self.edit_state(lambda st: st["accreditation"].pop("lock"))
        self.fails("verify", "--require-signed", expect="lock")
        self.s("phase", "session-expiry", "scrum", ok=False)

    def test_restoring_an_old_signoff_after_rewind_is_caught(self) -> None:
        self.to_signed_off()
        self.s("rewind", "session-expiry", "--to", "sprint:1", "--by", "alex@example.com")
        self.s("sprint-start", "session-expiry", "1")
        self.assertEqual(self.p.state()["sprints"]["1"]["run"], 2)          # run counter: 1 -> 2, no skip
        def restore(st):
            old = [h for h in st["sprints"]["1"]["history"] if h.get("status") == "signed-off"][-1]
            st["sprints"]["1"] = {**old, "history": st["sprints"]["1"]["history"]}
        self.edit_state(restore)
        self.fails("verify", "--require-signed", expect="rewound after this sign-off")
        self.edit_state(lambda st: st.__setitem__("rewinds", []))
        self.fails("verify", "--require-signed", expect="not referenced by any decision record")

    def test_foreign_or_misplaced_statements_are_caught(self) -> None:
        self.to_accredit()
        self.s("accredit", "session-expiry", "--verdict", "approved", "--by", "alex@example.com")
        self.edit_state(lambda st: st["accreditation"]["context"]["approval"].__setitem__(
            "file", "approvals/../../other/approvals/001-accredit.json"))
        self.fails("verify", expect="must reference approvals/NNN-accredit.json")
        # a statement from another change, copied in as the next statement
        self.s("new", "other")
        stmt = next((self.p.change() / "approvals").glob("001-*.json"))
        dest = self.p.change("other") / "approvals"
        dest.mkdir()
        shutil.copy(stmt, dest / stmt.name)
        shutil.copy(str(stmt) + ".sig", str(dest / stmt.name) + ".sig")
        self.fails("verify", "other", expect="change identity does not verify")

    def test_forged_wording_only_flag_is_caught(self) -> None:
        self.to_signed_off()
        self.s("cr", "add", "session-expiry", "--title", "t", "--by", "PM")
        self.s("cr", "decide", "session-expiry", "CR-001", "--outcome", "amend", "--reason", "r", "--by", "alex@example.com")
        self.s("amend", "session-expiry", "--cr", "CR-001", "--reason", "real change")
        self.edit_state(lambda st: st["amendments"][-1].__setitem__("wording_only", True))
        self.fails("verify", "--require-signed", expect="amendment #1 approval")

    def test_archived_changes_and_unknown_ids(self) -> None:
        self.to_accredit()
        self.s("accredit", "session-expiry", "--verdict", "approved", "--by", "alex@example.com")
        self.edit_state(lambda st: st["accreditation"].__setitem__("context", {}))     # forge: drop the signature
        arch = self.p.tmp / "specmaker/archive/2026-01-01-session-expiry"
        shutil.move(str(self.p.change()), str(arch))
        self.fails("verify", "--require-signed", expect="is not signed")
        self.fails("verify", "no-such-change", expect="no active or archived change")

    def test_request_status_must_follow_the_decision(self) -> None:
        self.to_accredit()
        self.s("cr", "add", "session-expiry", "--title", "a", "--by", "PM")
        self.s("cr", "add", "session-expiry", "--title", "b", "--by", "PM")
        self.s("cr", "decide", "session-expiry", "CR-001", "--outcome", "reject", "--reason", "r", "--by", "alex@example.com")
        def forge(st):
            st["requests"]["CR-001"]["status"] = "applied"
            st["requests"]["CR-002"]["status"] = "rejected"
        self.edit_state(forge)
        r = self.s("verify", ok=False).stdout
        self.assertIn("CR-001 is 'applied'", r)
        self.assertIn("CR-002 is 'rejected' without a recorded decision", r)

    def test_impersonation_and_malformed_records(self) -> None:
        self.to_accredit()
        self.s("approvers", "add", "--principal", "bob@example.com", "--key", str(self.keys / "rogue.pub"))
        self.s("accredit", "session-expiry", "--verdict", "approved", "--by", "alex@example.com")
        stmt = next((self.p.change() / "approvals").glob("001-*.json"))
        Path(str(stmt) + ".sig").unlink()
        subprocess.run(["ssh-keygen", "-q", "-Y", "sign", "-f", str(self.keys / "rogue"), "-n", "specmaker", str(stmt)],
                       check=True, capture_output=True)
        self.edit_state(lambda st: st["accreditation"]["context"]["approval"].__setitem__("principal", "bob@example.com"))
        self.fails("verify", expect="does not verify")
        self.edit_state(lambda st: st["accreditation"]["context"].__setitem__("approval", "garbage"))
        r = self.s("verify", ok=False)
        self.assertNotIn("Traceback", r.stderr)
        self.assertNotIn("Traceback", self.s("status").stderr)

    def test_statement_gaps_and_append_only_base(self) -> None:
        self.to_signed_off()
        self.p.sh("git add -A && git commit -qm signed")
        stmt = sorted((self.p.change() / "approvals").glob("*.json"))[0]
        stmt.write_text(stmt.read_text().replace("approved", "rejected", 1))
        self.fails("verify", "--base", "HEAD", expect="was modified since HEAD")
        self.p.sh("git checkout -q -- .")
        last = sorted((self.p.change() / "approvals").glob("*.json"))[0]
        last.unlink()
        Path(str(last) + ".sig").unlink()
        self.fails("verify", expect="without gaps")


class PlanBeforeImplementation(unittest.TestCase):
    """Implementation starts only with a complete, human-approved plan and no code written ahead of it."""

    def setUp(self) -> None:
        self.p = p = Project()
        p.run("init")
        chat_gates(p)
        set_gates(p)
        p.write("src/app.py", "print('hi')\n")
        p.sh("git add -A && git commit -qm initial")        # a commit exists, so design approval records a checkpoint
        p.run("new", "session-expiry")
        design(p)
        p.run("phase", "session-expiry", "propose")
        p.run("phase", "session-expiry", "accredit")
        reviews(p)
        p.run("accredit", "session-expiry", "--verdict", "approved", "--by", "Ravi")
        p.run("phase", "session-expiry", "scrum")
        p.write("specmaker/changes/session-expiry/backlog.md", BACKLOG)

    def tearDown(self) -> None:
        self.p.cleanup()

    def test_tree_must_be_complete(self) -> None:
        p = self.p
        bl = p.change() / "backlog.md"
        bl.write_text(BACKLOG.replace("## Sprint Plan", "## E2 - Empty epic\n\n### F9 - Empty feature\n\n## Sprint Plan"))
        out = p.run("check", "session-expiry", "backlog", ok=False).stdout
        self.assertIn("feature F9 (Empty feature) has no stories", out)
        bl.write_text(BACKLOG.replace("## Sprint Plan", "## E2 - Lonely epic\n\n## Sprint Plan"))
        self.assertIn("epic E2 (Lonely epic) has no features", p.run("check", "session-expiry", "backlog", ok=False).stdout)

    def test_plan_approval_gates_the_sprint(self) -> None:
        p, cid = self.p, "session-expiry"
        r = p.run("phase", cid, "sprint", ok=False)
        self.assertIn("not approved", r.stdout)
        self.assertIn("approve-plan", p.run("status", cid).stdout)
        p.run("approve-plan", cid, "--by", "Ravi")
        p.run("phase", cid, "sprint")
        bl = p.change() / "backlog.md"
        bl.write_text(bl.read_text().replace("- [ ] T1.1", "- [x] T1.1"))   # progress is not a plan change
        p.sh("git add -A && git commit -qm specmaker-only")
        p.run("sprint-start", cid, "1")
        p.run("signoff", cid, "1", "--by", "Ravi", ok=False)          # (incomplete sprint; irrelevant here)
        # adding a story is a plan change: the next sprint start needs a new approval
        st = p.state()
        st["sprints"]["1"]["status"] = "signed-off"                     # simulate sprint 1 done (chat mode)
        (p.change() / "change.json").write_text(json.dumps(st))
        bl.write_text(bl.read_text().replace("## Sprint Plan", "#### S2 - As a user, I want x, so that y\n- **Covers**: AUTH-01.1\n"
                      "- **Points**: 1\n- [ ] T2.1 do - files: src/session.py\n\n## Sprint Plan")
                      .replace("| 1 | Idle sessions expire | S1 | 3 |", "| 1 | Idle sessions expire | S1 | 3 |\n| 2 | more | S2 | 1 |"))
        r = subprocess.run([sys.executable, str(SCRIPT), "sprint-start", cid, "2"], cwd=p.tmp, capture_output=True, text=True)
        self.assertIn("changed since the plan was approved", r.stderr)

    def test_plan_approval_setting_and_lite_default(self) -> None:
        p = self.p
        pm = p.tmp / "specmaker/project.md"
        self.assertIn("- Plan approval: full", pm.read_text())          # template default
        p.run("new", "small", "--track", "lite")
        import importlib.util
        spec = importlib.util.spec_from_file_location("specmaker_mod", SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        ws = mod.Workspace(p.tmp / "specmaker")
        for value, full_needs, lite_needs in [("full", True, False), ("all", True, True), ("off", False, False),
                                              ("nonsense", True, False)]:
            pm.write_text(re.sub(r"(?m)^- Plan approval: .*$", f"- Plan approval: {value}", pm.read_text()))
            self.assertEqual(mod.plan_required(ws.change("session-expiry")), full_needs, value)
            self.assertEqual(mod.plan_required(ws.change("small")), lite_needs, value)
        pm.write_text(re.sub(r"(?m)^- Plan approval: .*$", "- Plan approval: off", pm.read_text()))
        p.run("phase", "session-expiry", "sprint")                      # off: no approval needed

    def test_code_written_before_the_sprint_is_refused(self) -> None:
        p, cid = self.p, "session-expiry"
        p.run("approve-plan", cid, "--by", "Ravi")
        p.run("phase", cid, "sprint")
        p.write("src/session.py", "early = True\n")
        p.sh("git add -A && git commit -qm early-work")
        r = subprocess.run([sys.executable, str(SCRIPT), "sprint-start", cid, "1"], cwd=p.tmp, capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("src/session.py", r.stderr)
        self.assertIn("design approval", r.stderr)
        p.write("src/other.py", "uncommitted = True\n")                 # uncommitted work counts too
        r = subprocess.run([sys.executable, str(SCRIPT), "sprint-start", cid, "1"], cwd=p.tmp, capture_output=True, text=True)
        self.assertIn("src/other.py", r.stderr)
        p.run("sprint-start", cid, "1", "--accept-prior", "spike code kept on purpose", "--by", "Ravi")
        st = p.state()
        self.assertEqual(sorted(st["accepted_prior"][0]["files"]), ["src/other.py", "src/session.py"])
        self.assertIn("accepted 2 file(s)", (p.change() / "ledger.md").read_text())


class SignedPlanApproval(SignedGates):
    def test_signed_plan_approval_and_forgery(self) -> None:
        self.to_accredit()
        self.s("accredit", "session-expiry", "--verdict", "approved", "--by", "alex@example.com")
        self.s("phase", "session-expiry", "scrum")
        self.p.write("specmaker/changes/session-expiry/backlog.md", BACKLOG)
        self.s("approve-plan", "session-expiry", "--by", "alex@example.com")
        self.assertTrue(list((self.p.change() / "approvals").glob("*-plan.json")))
        self.s("verify", "--require-signed")
        cj = self.p.change() / "change.json"
        st = json.loads(cj.read_text())
        st["plan_approvals"][-1]["backlog_digest"] = "0" * 64
        cj.write_text(json.dumps(st))
        self.assertIn("plan approval #1: the record differs", self.s("verify", ok=False).stdout)


def load_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location("specmaker_mod", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class LogicReview(unittest.TestCase):
    """Regression tests for the OpenSpec and EGM logic review (2026-11-26)."""

    setUp = AuditRegressions.setUp
    tearDown = AuditRegressions.tearDown
    living = AuditRegressions.living
    to_retro_docs_only = AuditRegressions.to_retro_docs_only
    ADD = AuditRegressions.ADD
    PURPOSE = "Keeps signed-in sessions valid only while their users are active.\n"

    REMOVE = ("# identity/session\n\n## REMOVED Requirements\n\n### Requirement: [AUTH-03] Sign out\n"
              "**Reason**: sign-out moves to the gateway.\n**Migration**: none.\n")

    def delta_check(self, delta: str, ok: bool) -> str:
        p = self.p
        if "x" not in [c.name for c in (p.tmp / "specmaker/changes").iterdir()]:
            p.run("new", "x", "--track", "lite")
        p.write("specmaker/changes/x/specs/identity/session/spec.md", delta)
        return p.run("check", "x", "specs", ok=ok).stdout

    def test_fences_and_hidden_headings(self) -> None:
        self.p.write("specmaker/specs/identity/session/spec.md", self.living())
        req = self.ADD.split("#### Scenario")[0]
        scn = "#### Scenario" + self.ADD.split("#### Scenario")[1]
        # a ~~~ fence hides a fake requirement; an inline ```code``` line opens nothing
        out = self.delta_check(req + "```npm test``` runs it.\n\n" + scn
                               + "\n~~~text\n### Requirement: [AUTH-05] fake\n~~~\n", ok=True)
        self.assertNotIn("AUTH-05", out)
        out = self.delta_check(req + "```text\nSHALL in an example\n" + scn, ok=False)
        self.assertIn("never closed", out)
        out = self.delta_check(req + "### Notes\nhidden\n\n" + scn, ok=False)
        self.assertIn("would be hidden from checks", out)

    def test_spec_folder_and_purpose_rules(self) -> None:
        p = self.p
        p.write("specmaker/specs/identity/session/spec.md", self.living())
        out = self.delta_check(self.ADD.replace("# identity/session\n",
                                                "# identity/session\n\n## Purpose\n\n" + self.PURPOSE), ok=False)
        self.assertIn("'## Purpose' is only for a new capability", out)
        p.write("specmaker/changes/x/specs/billing/spec.md",
                self.ADD.replace("identity/session", "billing").replace("AUTH-04", "BILL-01")
                .replace("## ADDED", "## Purpose\n\nTBD\n\n## ADDED"))
        p.write("specmaker/changes/x/specs/identity/session/spec.md", self.ADD)
        out = p.run("check", "x", "specs", ok=False).stdout
        self.assertIn("at least 50 characters", out)
        p.write("specmaker/changes/x/specs/billing/spec.md", "")
        (p.change("x") / "specs/billing/spec.md").unlink()
        p.write("specmaker/changes/x/specs/notes.md", "# stray\n")
        self.assertIn("not read", p.run("check", "x", "specs", ok=False).stdout)
        (p.change("x") / "specs/notes.md").unlink()
        p.run("set", "x", "skip_specs", "true")
        self.assertIn("skip_specs is set but delta specs exist", p.run("check", "x", "specs", ok=False).stdout)
        p.run("set", "x", "skip_specs", "false")
        out = p.run("check", "x", "specs").stdout
        self.assertNotIn("not merged", out)
        out = self.delta_check(self.ADD.replace("## ADDED Requirements\n", "## ADDED Requirements\n\nStray note.\n"),
                               ok=True)
        self.assertIn("is not merged into the living spec", out)

    def test_living_lint_and_merge_lint(self) -> None:
        p = self.p
        p.write("specmaker/specs/identity/session/spec.md", self.living())
        p.run("spec", "--lint")
        p.write("specmaker/specs/identity/token/spec.md",
                "# identity/token\n\n## Purpose\n\nx\n\n## Requirements\n\n" + self.living().split("## Requirements\n\n")[1])
        out = p.run("spec", "--lint", ok=False).stdout
        self.assertIn("defined more than once", out)
        mod = load_module()
        rep = mod.lint_living({"a/spec.md": "# a\n\n## Requirements\n\n### Requirement: [A-01] x\nNo normative word.\n"})
        self.assertFalse(rep.ok)

    def test_removals_need_a_story_and_no_leftover_tests(self) -> None:
        p = self.p
        p.write("specmaker/specs/identity/session/spec.md", self.living())
        self.to_retro_docs_only("drop-signout", self.REMOVE)
        p.write("tests/test_signout.py", "# covers: AUTH-03.1\ndef test_signout():\n    pass\n")  # written later
        out = p.run("trace", "drop-signout").stdout
        self.assertIn("## Removals", out)
        self.assertIn("tests/test_signout.py", out)
        out = p.run("archive", "drop-signout", ok=False).stdout
        self.assertIn("AUTH-03.1 ([AUTH-03] is removed) is still referenced by tests/test_signout.py", out)
        (p.tmp / "tests/test_signout.py").unlink()
        self.assertIn("nothing (confirmed)", p.run("trace", "drop-signout").stdout)
        p.run("archive", "drop-signout")
        self.assertNotIn("AUTH-03", (p.tmp / "specmaker/specs/identity/session/spec.md").read_text())

    def test_backlog_removes_field(self) -> None:
        p = self.p
        p.write("specmaker/specs/identity/session/spec.md", self.living())
        p.run("new", "trim", "--track", "lite")
        p.write("specmaker/changes/trim/specs/identity/session/spec.md", self.ADD + self.REMOVE.split("\n", 1)[1])
        p.write("specmaker/changes/trim/lld.md", "# LLD\n\n> **TL;DR** x\n\n## Architecture\nx\n## Interfaces\nx\n"
                "## Test Strategy\nx\n## File Boundary\nsrc/session.py\n")
        p.run("phase", "trim", "accredit")
        p.write("specmaker/changes/trim/reviews/accredit-r1-readiness.md", REPORT_PASS)
        p.write("specmaker/changes/trim/accreditation.md", "# A\n")
        p.run("accredit", "trim", "--verdict", "approved", "--by", "Ravi")
        p.run("phase", "trim", "scrum")
        story = ("#### S1 - Idle sessions end\n- **Covers**: AUTH-04.1\n- **Points**: 2\n"
                 "- [ ] T1.1 Expire idle sessions - files: src/session.py\n\n")
        plan = "## Sprint Plan\n\n| Sprint | Goal | Stories | Points |\n|---|---|---|---|\n| 1 | Trim | S1, S2 | 3 |\n"
        remover = ("#### S2 - Remove sign-out\n- **Removes**: AUTH-03\n- **Points**: 1\n"
                   "- [ ] T2.1 Delete sign-out code and tests - files: src/signout.py\n\n")
        p.write("specmaker/changes/trim/backlog.md", "# Backlog: trim\n\n" + story
                + remover.replace("**Removes**: AUTH-03", "**Covers**:") + plan)
        out = p.run("check", "trim", "backlog", ok=False).stdout
        self.assertIn("REMOVED [AUTH-03]", out)
        p.write("specmaker/changes/trim/backlog.md", "# Backlog: trim\n\n" + story
                + remover.replace("AUTH-03", "AUTH-02") + plan)
        self.assertIn("**Removes** [AUTH-02], which no delta spec lists under REMOVED",
                      p.run("check", "trim", "backlog", ok=False).stdout)
        p.write("specmaker/changes/trim/backlog.md", "# Backlog: trim\n\n" + story + remover + plan)
        p.run("check", "trim", "backlog")

    def test_archive_rolls_back_on_failure(self) -> None:
        p = self.p
        spec = p.write("specmaker/specs/identity/session/spec.md", self.living())
        self.to_retro_docs_only("add-idle", self.ADD)
        original = spec.read_text()
        mod = load_module()
        c = mod.Workspace(p.tmp / "specmaker").change("add-idle")
        p.write("specmaker/blocker", "a file where a folder is needed\n")
        plan = {spec: "rewritten\n", p.tmp / "specmaker/blocker/adr.md": "x\n"}
        with self.assertRaises(SystemExit):
            mod.apply_archive(c, plan, p.tmp / "specmaker/archive/add-idle", 1)
        self.assertEqual(spec.read_text(), original)
        self.assertEqual(p.state("add-idle")["phase"], "retro")
        self.assertFalse((p.tmp / "specmaker/archive/add-idle").exists())
        self.assertEqual([x.name for x in spec.parent.iterdir()], ["spec.md"])

    def review_setup(self, report: str) -> None:
        p = self.p
        p.run("new", "rv", "--track", "lite")
        p.write("specmaker/changes/rv/specs/identity/session/spec.md",
                self.ADD.replace("# identity/session\n", "# identity/session\n\n## Purpose\n\n" + self.PURPOSE))
        p.write("specmaker/changes/rv/lld.md", "# LLD\n\n> **TL;DR** x\n\n## Architecture\nx\n## Interfaces\nx\n"
                "## Test Strategy\nx\n## File Boundary\nsrc/session.py\n")
        p.run("phase", "rv", "accredit")
        p.write("specmaker/changes/rv/reviews/accredit-r1-readiness.md", report)
        p.write("specmaker/changes/rv/accreditation.md", "# A\n")

    BLOCKER = ("# Readiness review - round 1\n- Verdict: FAIL\n\n## Findings\n### G1 [Blocker] No error code\n"
               "- Evidence: absent:error code\n- Problem: x\n- Suggested fix: y\n### G2 [Major] Vague timer\n"
               "- Evidence: doc:lld.md#Interfaces\n- Problem: x\n- Suggested fix: y\n")

    def test_incomplete_report_is_refused(self) -> None:
        self.review_setup("# Readiness review\nI looked at it and it seems fine.\n")
        out = self.p.run("accredit", "rv", "--verdict", "approved", "--by", "Ravi", ok=False).stdout
        self.assertIn("is incomplete", out)

    def test_blockers_must_be_resolved_and_never_declined(self) -> None:
        p = self.p
        self.review_setup(self.BLOCKER)
        out = p.run("accredit", "rv", "--verdict", "approved", "--by", "Ravi", ok=False).stdout
        self.assertIn("Blocker accredit-r1-readiness.md#G1 is unresolved", out)
        self.assertNotIn("#G2", out)                                    # Majors are triaged, not script-gated
        p.run("ledger", "rv", "--kind", "declined", "--ref", "accredit-r1-readiness.md#G1", "not worth it")
        out = p.run("accredit", "rv", "--verdict", "approved", "--by", "Ravi", ok=False).stdout
        self.assertIn("L-001 declines Blocker accredit-r1-readiness.md#G1", out)
        # a later condition supersedes the decline, but settles the Blocker only for a conditional verdict
        p.run("ledger", "rv", "--kind", "condition", "--ref", "accredit-r1-readiness.md#G1", "add the error code")
        out = p.run("accredit", "rv", "--verdict", "approved", "--by", "Ravi", ok=False).stdout
        self.assertIn("is unresolved", out)
        self.assertNotIn("declines Blocker", out)
        p.run("accredit", "rv", "--verdict", "conditional", "--condition", "error code", "--by", "Ravi")

    def test_blocker_fixed_and_rereviewed_or_contested(self) -> None:
        p = self.p
        self.review_setup(self.BLOCKER)
        p.run("ledger", "rv", "--kind", "contested", "--ref", "accredit-r1-readiness#G1",
              "contested: doc:lld.md#Interfaces names the code")
        p.run("accredit", "rv", "--verdict", "approved", "--by", "Ravi")
        self.review_setup_round2()

    def review_setup_round2(self) -> None:
        p = self.p
        p.run("amend", "rv", "--reason", "fix G1")
        p.run("phase", "rv", "accredit")
        p.write("specmaker/changes/rv/reviews/accredit-r2-readiness.md", self.BLOCKER.replace("round 1", "round 2"))
        out = p.run("accredit", "rv", "--verdict", "approved", "--by", "Ravi", ok=False).stdout
        self.assertIn("accredit-r2-readiness.md#G1 is unresolved", out)   # the r1 ledger entry does not carry over
        p.write("specmaker/changes/rv/reviews/accredit-r3-readiness.md", REPORT_PASS)
        p.run("accredit", "rv", "--verdict", "approved", "--by", "Ravi")

    def test_ledger_stance_and_report_consistency(self) -> None:
        p = self.p
        self.review_setup(self.BLOCKER)
        # the append-only ledger: a later decision supersedes an earlier decline (short ref form, as documented)
        p.run("ledger", "rv", "--kind", "declined", "--ref", "r1-readiness#G1", "not worth it")
        self.assertIn("L-001 declines Blocker", p.run("accredit", "rv", "--verdict", "approved", "--by", "Ravi",
                                                      ok=False).stdout)
        p.run("ledger", "rv", "--kind", "decision", "--ref", "r1-readiness#G1", "a decision is not a finding outcome")
        out = p.run("accredit", "rv", "--verdict", "approved", "--by", "Ravi", ok=False).stdout
        self.assertIn("L-001 declines Blocker", out)                     # a decision does not supersede a decline
        self.assertIn("L-002 reference it but are not finding outcomes", out)
        p.run("ledger", "rv", "--kind", "escalated", "--ref", "r1-readiness#G1", "owner: the code is in the contract")
        rv = p.change("rv") / "reviews/accredit-r1-readiness.md"
        rv.write_text(self.BLOCKER.replace("Verdict: FAIL", "Verdict: PASS"))
        self.assertIn("a report with any Blocker is FAIL",
                      p.run("accredit", "rv", "--verdict", "approved", "--by", "Ravi", ok=False).stdout)
        rv.write_text(REPORT_PASS.replace("PASS", "FAIL"))
        self.assertIn("says FAIL but lists no",
                      p.run("accredit", "rv", "--verdict", "approved", "--by", "Ravi", ok=False).stdout)
        rv.write_text(self.BLOCKER)
        p.run("accredit", "rv", "--verdict", "approved", "--by", "Ravi")

    def test_verifier_verdict_is_the_last_line(self) -> None:
        mod = load_module()
        self.assertEqual(mod.verification_verdict("- Verdict: <PASS | PASS-WITH-NOTES | FAIL>\n...\nVerdict: FAIL\n"),
                         "FAIL")
        self.assertEqual(mod.verification_verdict("- Verdict: PASS\n\nVerdict: PASS-WITH-NOTES\n"), "PASS-WITH-NOTES")
        self.assertIsNone(mod.verification_verdict("no verdict\n"))

    def test_docs_only_cannot_retire_named_ids(self) -> None:
        p = self.p
        p.write("specmaker/specs/identity/session/spec.md", self.living())
        p.write("tests/test_signout.py", "# covers: AUTH-03.1\n")
        p.run("new", "split", "--track", "lite")
        p.run("set", "split", "docs_only", "true")
        p.write("specmaker/changes/split/specs/identity/session/spec.md", self.REMOVE)
        out = p.run("check", "split", "specs", ok=False).stdout
        self.assertIn("a docs-only change builds nothing", out)
        p.run("set", "split", "docs_only", "false")
        p.run("check", "split", "specs")

    def test_sprint_removals_are_scoped(self) -> None:
        p = self.p
        p.write("specmaker/specs/identity/session/spec.md", self.living())
        p.write("tests/test_signout.py", "# covers: AUTH-03.1\n")
        p.run("new", "trim", "--track", "lite")
        p.write("specmaker/changes/trim/specs/identity/session/spec.md", self.REMOVE)
        mod = load_module()
        c = mod.Workspace(p.tmp / "specmaker").change("trim")
        self.assertFalse(mod.check_removals(c, only_reqs={"AUTH-03"}).ok)  # the sprint that removes it
        self.assertTrue(mod.check_removals(c, only_reqs={"AUTH-02"}).ok)   # another sprint is not blamed
