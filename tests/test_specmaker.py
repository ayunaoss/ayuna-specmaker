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
        p.write(f"specmaker/changes/session-expiry/reviews/accredit-r{rnd}-{lens}.md", f"# {lens}\n- Verdict: PASS\n")
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
        self.assertEqual(len(names), 7)
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
        p.write(f"specmaker/changes/{cid}/reviews/accredit-r1-readiness.md", "ok\n")
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
            (proj / c / f"reviews/accredit-r1-{lens}.md").write_text("ok\n")
        (proj / c / "accreditation.md").write_text("# A\n")
        run("accredit", "session-expiry", "--verdict", "approved", "--by", "Ravi")
        run("phase", "session-expiry", "scrum")
        (proj / c / "backlog.md").write_text(BACKLOG.replace("files: src/session.py", "files: src/session.py, src/café.py")
                                         .replace("files: tests/test_session.py", "files: tests/test_session.py, tests/test_sessión.py"))
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

    BUDGET = {"specmaker": 850}           # core skill: a route map; recipes live in references/recipes.md
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
