"""End-to-end and unit tests for skills/specmaker/scripts/specmaker.py.

Run: python3 -m unittest discover -s tests -v
"""

import json
import os
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


def chat_gates(p: Project) -> None:
    """Tests drive the script without a terminal, so they use chat-mode human gates."""
    pm = p.tmp / "specmaker" / "project.md"
    pm.write_text(pm.read_text().replace("- Human gates: terminal", "- Human gates: chat"))


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


def reviews(p: Project, lenses=("consistency", "readiness")) -> None:
    for lens in lenses:
        p.write(f"specmaker/changes/session-expiry/reviews/accredit-r1-{lens}.md", f"# {lens}\n- Verdict: PASS\n")
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
            p.write(f"specmaker/changes/{cid}/reviews/accredit-r1-readiness.md", "ok\n")
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
        p.run("init")  # template default: Human gates: terminal
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
        self.assertEqual(len(names), 7)
        # no other SKILL.md in the repo that the CLI could pick up by accident
        stray = [p for p in REPO.rglob("SKILL.md") if "skills" not in p.relative_to(REPO).parts[:1]
                 and ".git" not in p.parts]
        self.assertEqual(stray, [])
