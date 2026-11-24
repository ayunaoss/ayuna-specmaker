#!/usr/bin/env python3
"""specmaker - deterministic helper for the Ayuna specmaker skills.

The skills hold the judgement (conversation, drafting, review). This script holds
the rules that must not depend on a model's mood: phase gates, artifact lint,
the accreditation lock, spec <-> backlog <-> code traceability, and merging
delta specs into the living specs.

Standard library only. Python >= 3.8. Run `specmaker.py -h` for commands.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

VERSION = "0.1.0"
STATE_FILE = "change.json"
DEFAULT_ROOT = "specmaker"
PHASES = ["ideate", "propose", "accredit", "scrum", "sprint", "retro", "archived"]
TRACKS = ["full", "lite"]
SKILL_DIR = Path(__file__).resolve().parent.parent
TEMPLATES = SKILL_DIR / "assets" / "templates"

ID_RE = r"[A-Z][A-Z0-9]{0,11}-\d{1,4}"
REQ_RE = re.compile(r"^###\s+Requirement:\s*\[(" + ID_RE + r")\]\s*(.*?)\s*$")
REQ_LOOSE_RE = re.compile(r"^###\s+Requirement:")
SCN_RE = re.compile(r"^####\s+Scenario:\s*\[(" + ID_RE + r")\.(\d{1,3})\]\s*(.*?)\s*$")
SCN_LOOSE_RE = re.compile(r"^####\s+Scenario:")
DELTA_SECTION_RE = re.compile(r"^##\s+(ADDED|MODIFIED|REMOVED)\s+Requirements\s*$", re.I)
H2_RE = re.compile(r"^##\s+")
STEP_RE = re.compile(r"^\s*[-*]\s+\*\*(GIVEN|WHEN|THEN|AND|BUT)\*\*", re.I)
NORMATIVE_RE = re.compile(r"\b(SHALL|MUST)\b")
SCENARIO_ID_RE = re.compile(r"\b(" + ID_RE + r"\.\d{1,3})\b")

EPIC_RE = re.compile(r"^##\s+(E\d+)\s*[-:—–]\s*(.+?)\s*$")
FEAT_RE = re.compile(r"^###\s+(F\d+)\s*[-:—–]\s*(.+?)\s*$")
STORY_RE = re.compile(r"^####\s+(S\d+)\s*[-:—–]\s*(.+?)\s*$")
TASK_RE = re.compile(r"^\s*[-*]\s+\[([ xX~])\]\s+(T(\d+)\.(\d+))\b\s*(.*)$")
FIELD_RE = re.compile(r"^\s*[-*]\s+\*\*(Points|Priority|Depends|Covers|Type)\*\*\s*:\s*(.*)$", re.I)
FIB = {1, 2, 3, 5, 8, 13}
PRIORITIES = {"must", "should", "could", "won't", "wont"}

TEST_PATH_RE = re.compile(
    r"(^|/)(tests?|__tests__|specs?|e2e|it|integration)/"
    r"|(^|/)test_[^/]+$"
    r"|[._-](test|spec|tests|steps)\.[A-Za-z0-9]+$"
    r"|Tests?\.[A-Za-z0-9]+$"
    r"|\.feature$"
)
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build",
             "target", ".next", ".tox", ".mypy_cache", ".pytest_cache", "vendor", ".opencode",
             ".claude", ".agents", "coverage"}

# --------------------------------------------------------------------------- utils


class Report:
    """Collects errors and warnings for a check run."""

    def __init__(self) -> None:
        self.errors: List[str] = []
        self.warnings: List[str] = []

    def err(self, where: str, msg: str) -> None:
        self.errors.append(f"{where}: {msg}")

    def warn(self, where: str, msg: str) -> None:
        self.warnings.append(f"{where}: {msg}")

    def extend(self, other: "Report") -> None:
        self.errors += other.errors
        self.warnings += other.warnings

    @property
    def ok(self) -> bool:
        return not self.errors

    def render(self, title: str) -> str:
        out = [f"== {title}: {'PASS' if self.ok else 'FAIL'} "
               f"({len(self.errors)} error(s), {len(self.warnings)} warning(s))"]
        out += [f"  ERROR   {e}" for e in self.errors]
        out += [f"  WARN    {w}" for w in self.warnings]
        return "\n".join(out)


def die(msg: str, code: int = 2) -> "NoReturn":  # type: ignore[name-defined]
    print(f"specmaker: {msg}", file=sys.stderr)
    sys.exit(code)


def now() -> str:
    return _dt.datetime.now().astimezone().isoformat(timespec="seconds")


def today() -> str:
    return _dt.date.today().isoformat()


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


class Skipper:
    """Tracks fenced code blocks and multi-line HTML comments, line by line."""

    def __init__(self) -> None:
        self.fence = False
        self.comment = False

    def skip(self, line: str) -> bool:
        """True if this line is inside a fence or comment (or opens/closes one)."""
        if self.comment:
            if "-->" in line:
                self.comment = False
            return True
        if line.strip().startswith("```"):
            self.fence = not self.fence
            return True
        if self.fence:
            return True
        start = line.rfind("<!--")
        if start != -1 and "-->" not in line[start:]:
            self.comment = True
            return line.lstrip().startswith("<!--")
        return False


def strip_comments(text: str) -> str:
    return re.sub(r"<!--.*?-->", "", text, flags=re.S)


def sections(text: str, level: int = 2) -> Dict[str, str]:
    """Map heading text (lower-case, numbering stripped) -> body for one heading level."""
    marker = "#" * level
    pat = re.compile(r"^" + marker + r"\s+(?!#)(.+?)\s*$", re.M)
    out: Dict[str, str] = {}
    matches = list(pat.finditer(text))
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[m.end():end]
        # cut at any higher-level heading
        hi = re.search(r"^#{1," + str(level - 1) + r"}\s", body, re.M) if level > 1 else None
        if hi:
            body = body[:hi.start()]
        name = re.sub(r"^[\d.\s]+", "", m.group(1)).strip().lower()
        out[name] = body
    return out


EMPTY_LINE_RE = re.compile(
    r"^\s*([-*]\s*)?(\*\*)?[\w .()/-]{0,40}(\*\*)?\s*:?\s*$"  # bare bullet or empty label ("- G1:", "- Pros:")
)


def has_content(body: str) -> bool:
    """True if a section holds real content, not just template scaffolding."""
    lines = strip_comments(body).splitlines()
    table: List[str] = []
    real = False
    for ln in lines + [""]:
        if ln.strip().startswith("|"):
            table.append(ln)
            continue
        if table:
            if len(table) > 2:  # header + separator alone is scaffolding
                real = True
            table = []
        st = ln.strip()
        if not st or st.startswith("#") or st.startswith("```"):
            continue
        if re.fullmatch(r"[-*]\s*[\w ]{0,12}:?", st) or (EMPTY_LINE_RE.match(ln) and st.endswith(":")):
            continue
        real = True
    return real


def find_section(secs: Dict[str, str], keyword: str) -> Optional[str]:
    """Best match: exact name, then a name starting with the keyword, then containing it."""
    for test in (lambda n: n == keyword, lambda n: n.startswith(keyword) and not n.startswith(keyword + " driver"),
                 lambda n: keyword in n):
        for name, body in secs.items():
            if test(name):
                return body
    return None


# --------------------------------------------------------------------------- workspace


class Workspace:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.project = root.parent
        self.specs = root / "specs"
        self.changes = root / "changes"
        self.archive = root / "archive"

    @classmethod
    def locate(cls, arg: Optional[str], must_exist: bool = True) -> "Workspace":
        if arg:
            return cls(Path(arg).resolve())
        env = os.environ.get("SPECMAKER_ROOT")
        if env:
            return cls(Path(env).resolve())
        cur = Path.cwd().resolve()
        for d in [cur, *cur.parents]:
            cand = d / DEFAULT_ROOT
            if (cand / "project.md").is_file():
                return cls(cand)
            if (d / ".git").exists():
                break
        ws = cls(Path.cwd().resolve() / DEFAULT_ROOT)
        if must_exist and not ws.root.is_dir():
            die(f"no workspace found (looked for {DEFAULT_ROOT}/project.md upward from {cur}). "
                f"Run `specmaker.py init` first.")
        return ws

    def change(self, cid: str) -> "Change":
        d = self.changes / cid
        if not (d / STATE_FILE).is_file():
            known = ", ".join(self.change_ids()) or "none"
            die(f"unknown change '{cid}'. Active changes: {known}")
        return Change(self, d)

    def change_ids(self) -> List[str]:
        if not self.changes.is_dir():
            return []
        return sorted(p.name for p in self.changes.iterdir() if (p / STATE_FILE).is_file())


class Change:
    def __init__(self, ws: Workspace, d: Path) -> None:
        self.ws = ws
        self.dir = d
        self.id = d.name
        self.state = json.loads(read(d / STATE_FILE))

    def save(self) -> None:
        (self.dir / STATE_FILE).write_text(json.dumps(self.state, indent=2) + "\n", encoding="utf-8")

    def log(self, event: str, detail: str = "") -> None:
        self.state.setdefault("history", []).append({"at": now(), "event": event, "detail": detail})

    @property
    def phase(self) -> str:
        return self.state["phase"]

    @property
    def track(self) -> str:
        return self.state.get("track", "full")

    def p(self, rel: str) -> Path:
        return self.dir / rel

    def delta_specs(self) -> List[Path]:
        d = self.p("specs")
        return sorted(d.rglob("spec.md")) if d.is_dir() else []

    def adrs(self) -> List[Path]:
        d = self.p("adrs")
        return sorted(d.glob("*.md")) if d.is_dir() else []

    def design_files(self) -> List[Path]:
        """Files frozen by accreditation."""
        files = [self.p(n) for n in ("hld.md", "lld.md") if self.p(n).is_file()]
        files += self.adrs() + self.delta_specs()
        contracts = self.p("contracts")
        if contracts.is_dir():
            files += sorted(f for f in contracts.rglob("*") if f.is_file())
        return files

    def rel(self, p: Path) -> str:
        return p.relative_to(self.dir).as_posix()

    def lock_drift(self) -> List[str]:
        acc = self.state.get("accreditation") or {}
        lock = acc.get("lock") or {}
        if not lock:
            return []
        drift = []
        current = {self.rel(f): f for f in self.design_files()}
        for rel, digest in lock.items():
            f = current.get(rel)
            if f is None:
                drift.append(f"{rel} (deleted)")
            elif sha256(f) != digest:
                drift.append(f"{rel} (modified)")
        for rel in current:
            if rel not in lock:
                drift.append(f"{rel} (added)")
        return drift

    def sprint_file(self, n: int) -> Path:
        return self.p(f"sprints/sprint-{n:02d}.md")

    def verification_file(self, n: int) -> Path:
        """Latest verification round: sprint-NN-verification.md, then -r2, -r3 ..."""
        best, best_round = self.p(f"reviews/sprint-{n:02d}-verification.md"), 1
        d = self.p("reviews")
        if d.is_dir():
            for f in d.glob(f"sprint-{n:02d}-verification-r*.md"):
                m = re.search(r"-r(\d+)\.md$", f.name)
                if m and int(m.group(1)) > best_round:
                    best, best_round = f, int(m.group(1))
        return best


# --------------------------------------------------------------------------- spec parsing


class Requirement:
    def __init__(self, rid: str, title: str, section: str, lines: List[str], line_no: int) -> None:
        self.id = rid
        self.title = title
        self.section = section  # ADDED | MODIFIED | REMOVED | LIVING
        self.lines = lines      # full block incl. header
        self.line_no = line_no
        self.scenarios: List[Tuple[str, str, List[str]]] = []

    @property
    def text(self) -> str:
        return "\n".join(self.lines).rstrip() + "\n"


def parse_requirements(text: str, delta: bool) -> Tuple[List[Requirement], Report, Dict[str, str]]:
    """Parse requirement blocks. Returns (requirements, report, h2 sections)."""
    rep = Report()
    reqs: List[Requirement] = []
    section = "LIVING"
    cur: Optional[Requirement] = None
    cur_scn: Optional[Tuple[str, str, List[str]]] = None
    lines = text.splitlines()
    sk = Skipper()
    for i, line in enumerate(lines, 1):
        if sk.skip(line):
            if cur:
                cur.lines.append(line)
                if cur_scn:
                    cur_scn[2].append(line)
            continue
        m = DELTA_SECTION_RE.match(line)
        if m or H2_RE.match(line):
            cur, cur_scn = None, None
            if m:
                section = m.group(1).upper()
            elif delta:
                section = "OTHER"
            elif re.match(r"^##\s+Requirements\s*$", line, re.I):
                section = "LIVING"
            else:
                section = "OTHER"
            continue
        if REQ_LOOSE_RE.match(line):
            m = REQ_RE.match(line)
            if not m:
                rep.err(f"line {i}", f"requirement header needs an ID: '### Requirement: [AREA-01] Title' (got '{line.strip()}')")
                cur, cur_scn = None, None
                continue
            if section == "OTHER":
                rep.err(f"line {i}", f"requirement [{m.group(1)}] is outside a requirements section")
            cur = Requirement(m.group(1), m.group(2), section, [line], i)
            cur_scn = None
            reqs.append(cur)
            continue
        if SCN_LOOSE_RE.match(line):
            m = SCN_RE.match(line)
            if not cur:
                rep.err(f"line {i}", "scenario outside a requirement")
                continue
            cur.lines.append(line)
            if not m:
                rep.err(f"line {i}", f"scenario header needs an ID: '#### Scenario: [{cur.id}.1] Title'")
                cur_scn = None
                continue
            if m.group(1) != cur.id:
                rep.err(f"line {i}", f"scenario [{m.group(1)}.{m.group(2)}] is under requirement [{cur.id}]")
            cur_scn = (f"{m.group(1)}.{m.group(2)}", m.group(3), [])
            cur.scenarios.append(cur_scn)
            continue
        if cur:
            cur.lines.append(line)
            if cur_scn:
                cur_scn[2].append(line)
    h2 = sections(text, 2)
    return reqs, rep, h2


def lint_requirement(r: Requirement, where: str, rep: Report) -> None:
    if r.section == "REMOVED":
        body = "\n".join(r.lines[1:])
        if not re.search(r"\*\*Reason\*\*", body):
            rep.err(where, f"REMOVED [{r.id}] needs a '**Reason**:' line")
        if not re.search(r"\*\*Migration\*\*", body):
            rep.err(where, f"REMOVED [{r.id}] needs a '**Migration**:' line")
        return
    if not strip_comments(r.title).strip():
        rep.err(where, f"[{r.id}] has no title")
    if r.id.startswith("AREA-"):
        rep.err(where, f"[{r.id}] still uses the template prefix AREA; use the capability's prefix from project.md")
    first_scn = next((k for k, ln in enumerate(r.lines) if SCN_LOOSE_RE.match(ln)), len(r.lines))
    statement = strip_comments("\n".join(r.lines[1:first_scn])).strip()
    if re.fullmatch(r"The system (SHALL|MUST)\s*\.?", statement):
        statement = ""
    if not statement:
        rep.err(where, f"[{r.id}] has no requirement statement")
    elif not NORMATIVE_RE.search(statement):
        rep.err(where, f"[{r.id}] statement must use SHALL or MUST")
    elif len(statement) > 600:
        rep.warn(where, f"[{r.id}] statement is {len(statement)} chars; state one behaviour and move detail into scenarios")
    if not r.scenarios:
        rep.err(where, f"[{r.id}] needs at least one scenario")
    seen = set()
    for sid, title, body in r.scenarios:
        if sid in seen:
            rep.err(where, f"duplicate scenario id {sid}")
        seen.add(sid)
        steps = []
        for b in body:
            m = STEP_RE.match(b)
            if m:
                rest = strip_comments(b[m.end():]).strip()
                if not rest:
                    rep.err(where, f"scenario {sid} has an empty **{m.group(1).upper()}** step")
                steps.append(m.group(1).upper())
        if not any(s in ("WHEN", "GIVEN") for s in steps):
            rep.err(where, f"scenario {sid} needs a **WHEN** (or **GIVEN**) step")
        if "THEN" not in steps:
            rep.err(where, f"scenario {sid} needs a **THEN** step")


def living_spec_path(ws: Workspace, cap: str) -> Path:
    return ws.specs / cap / "spec.md"


def capability_of(change: Change, delta: Path) -> str:
    return delta.parent.relative_to(change.p("specs")).as_posix()


def load_living(ws: Workspace) -> Dict[str, Tuple[str, Requirement]]:
    """All living requirements: id -> (capability, requirement)."""
    out: Dict[str, Tuple[str, Requirement]] = {}
    if not ws.specs.is_dir():
        return out
    for f in sorted(ws.specs.rglob("spec.md")):
        cap = f.parent.relative_to(ws.specs).as_posix()
        reqs, _, _ = parse_requirements(read(f), delta=False)
        for r in reqs:
            out[r.id] = (cap, r)
    return out


def check_specs(change: Change) -> Report:
    rep = Report()
    deltas = change.delta_specs()
    if not deltas:
        if change.state.get("skip_specs"):
            return rep
        rep.err("specs/", "no delta specs. Add specs/<capability>/spec.md, or run "
                "`specmaker.py set <id> skip_specs true` for a change with no behaviour change")
        return rep
    living = load_living(change.ws)
    others = other_change_ids(change)
    seen: Dict[str, str] = {}
    for f in deltas:
        where = change.rel(f)
        cap = capability_of(change, f)
        if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*(/[a-z0-9]+(-[a-z0-9]+)*)*", cap):
            rep.err(where, f"capability path '{cap}' must be kebab-case segments")
        text = read(f)
        reqs, prep, h2 = parse_requirements(text, delta=True)
        for e in prep.errors:
            rep.err(where, e)
        if not any(k in h2 for k in ("added requirements", "modified requirements", "removed requirements")):
            rep.err(where, "needs at least one of: '## ADDED Requirements', '## MODIFIED Requirements', '## REMOVED Requirements'")
        is_new = not living_spec_path(change.ws, cap).is_file()
        if is_new:
            purpose = h2.get("purpose")
            if purpose is None or len(strip_comments(purpose).strip()) < 40:
                rep.err(where, "new capability needs a '## Purpose' of at least one full sentence")
        if not reqs:
            rep.err(where, "no requirements found")
        for r in reqs:
            lint_requirement(r, where, rep)
            if r.id in seen:
                rep.err(where, f"[{r.id}] also defined in {seen[r.id]}")
            seen[r.id] = where
            in_living = living.get(r.id)
            if r.section == "ADDED" and in_living:
                rep.err(where, f"ADDED [{r.id}] already exists in living spec '{in_living[0]}'; use MODIFIED or a new ID")
            if r.id in others:
                rep.warn(where, f"[{r.id}] is also touched by open change(s) {', '.join(others[r.id])}; "
                         f"agree an order (`set <id> depends_on ...`) before both are archived")
            if r.section in ("MODIFIED", "REMOVED"):
                if not in_living:
                    rep.err(where, f"{r.section} [{r.id}] does not exist in the living specs")
                elif in_living[0] != cap:
                    rep.err(where, f"{r.section} [{r.id}] lives in capability '{in_living[0]}', not '{cap}'")
    return rep


def delta_req_ids(change: Change) -> Dict[str, str]:
    """requirement id -> section, over all delta specs of a change."""
    out: Dict[str, str] = {}
    for f in change.delta_specs():
        reqs, _, _ = parse_requirements(read(f), delta=True)
        for r in reqs:
            out[r.id] = r.section
    return out


def other_change_ids(change: Change) -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {}
    for cid in change.ws.change_ids():
        if cid == change.id:
            continue
        for rid in delta_req_ids(change.ws.change(cid)):
            out.setdefault(rid, []).append(cid)
    return out


def base_hashes(change: Change) -> Dict[str, str]:
    """Hash of the living text of every requirement this change modifies or removes."""
    living = load_living(change.ws)
    out = {}
    for rid, sec in delta_req_ids(change).items():
        if sec in ("MODIFIED", "REMOVED") and rid in living:
            out[rid] = hashlib.sha256(living[rid][1].text.encode()).hexdigest()
    return out


def delta_scenarios(change: Change) -> Dict[str, Tuple[str, str]]:
    """scenario id -> (requirement id, scenario title), for ADDED and MODIFIED requirements."""
    out: Dict[str, Tuple[str, str]] = {}
    for f in change.delta_specs():
        reqs, _, _ = parse_requirements(read(f), delta=True)
        for r in reqs:
            if r.section in ("ADDED", "MODIFIED"):
                for sid, title, _ in r.scenarios:
                    out[sid] = (r.id, title)
    return out


# --------------------------------------------------------------------------- doc lint

HLD_REQUIRED = {
    "full": ["problem", "goals", "non-goals", "success", "solution overview", "alternatives", "risks"],
    "lite": ["problem", "goals", "solution overview"],
}
LLD_REQUIRED = {
    "full": ["architecture", "data model", "interfaces", "error handling", "cross-cutting",
             "technology", "alternatives", "test strategy", "implementation phases", "file boundary", "risks"],
    "lite": ["architecture", "interfaces", "test strategy", "file boundary"],
}
PLACEHOLDER_RE = re.compile(r"\b(TODO|TBD|FIXME|XXX)\b|<[a-z][a-z \-]*>")


WORD_BUDGET = {"hld.md": 2500, "lld.md": 6000}


def lint_doc(change: Change, name: str, required: List[str]) -> Report:
    rep = Report()
    f = change.p(name)
    if not f.is_file():
        rep.err(name, "missing")
        return rep
    text = read(f)
    secs = sections(text, 2)
    for key in required:
        body = find_section(secs, key)
        if body is None:
            rep.err(name, f"missing section containing '{key}'")
        elif not has_content(body):
            rep.err(name, f"section '{key}' is empty (write 'N/A - <reason>' if it does not apply)")
    for i, line in enumerate(strip_comments(text).splitlines(), 1):
        if PLACEHOLDER_RE.search(re.sub(r"`[^`]*`", "", line)):
            rep.warn(name, f"line {i} looks like an unresolved placeholder: {line.strip()[:80]}")
    words = len(strip_comments(text).split())
    budget = WORD_BUDGET.get(name)
    if budget and words > budget:
        rep.warn(name, f"{words} words (budget {budget}); people must be able to read this - cut or move detail to appendices")
    if not re.search(r"^>\s*\**(TL;DR|Summary)", text, re.M | re.I):
        rep.warn(name, "no '> **TL;DR**' summary block near the top")
    oq = find_section(secs, "open question")
    if oq and re.search(r"^\s*[-*]\s+\[ \]", oq, re.M):
        rep.warn(name, "has unchecked open questions")
    return rep


def check_adrs(change: Change) -> Report:
    rep = Report()
    nums = set()
    for f in change.adrs():
        where = change.rel(f)
        m = re.match(r"^(\d{4})-[a-z0-9-]+\.md$", f.name)
        if not m:
            rep.err(where, "ADR file name must be NNNN-kebab-title.md")
        elif m.group(1) in nums:
            rep.err(where, f"duplicate ADR number {m.group(1)}")
        else:
            nums.add(m.group(1))
        text = read(f)
        if not re.search(r"^\s*[-*]?\s*\**Status\**\s*:\s*\**\s*(Proposed|Accepted|Superseded|Deprecated|Rejected)", text, re.M | re.I):
            rep.err(where, "needs 'Status: Proposed|Accepted|Superseded|Deprecated|Rejected'")
        secs = sections(text, 2)
        for key in ("context", "options", "decision", "consequences"):
            body = find_section(secs, key)
            if body is None or not has_content(body):
                rep.err(where, f"missing or empty section containing '{key}'")
        opts = find_section(secs, "options")
        if opts is not None and len(re.findall(r"^###\s+", opts, re.M)) < 2:
            rep.err(where, "'Options Considered' needs at least two '### Option' subsections")
    return rep


# --------------------------------------------------------------------------- backlog


class Story:
    def __init__(self, sid: str, title: str, line: int, epic: Optional[str], feature: Optional[str]) -> None:
        self.id = sid
        self.title = title
        self.line = line
        self.epic = epic
        self.feature = feature
        self.fields: Dict[str, str] = {}
        self.tasks: List[Tuple[str, bool, str, int]] = []  # (id, done, text, line)

    @property
    def covers(self) -> List[str]:
        return SCENARIO_ID_RE.findall(self.fields.get("covers", ""))

    @property
    def depends(self) -> List[str]:
        return re.findall(r"\bS\d+\b", self.fields.get("depends", ""))

    @property
    def done(self) -> bool:
        return bool(self.tasks) and all(t[1] for t in self.tasks)


class Backlog:
    def __init__(self) -> None:
        self.epics: Dict[str, str] = {}
        self.features: Dict[str, Tuple[str, Optional[str]]] = {}
        self.stories: Dict[str, Story] = {}
        self.plan: Dict[int, List[str]] = {}
        self.plan_goals: Dict[int, str] = {}


def parse_backlog(text: str) -> Tuple[Backlog, Report]:
    rep = Report()
    b = Backlog()
    epic = feat = None
    story: Optional[Story] = None
    in_plan = False
    sk = Skipper()
    task_ids = set()
    for i, line in enumerate(text.splitlines(), 1):
        if sk.skip(line):
            continue
        if re.match(r"^##\s+Sprint Plan\b", line, re.I):
            in_plan, story = True, None
            continue
        if in_plan:
            if H2_RE.match(line):
                in_plan = False
            else:
                cells = [c.strip() for c in line.strip().strip("|").split("|")] if line.strip().startswith("|") else []
                if cells and re.fullmatch(r"\d+", cells[0]):
                    n = int(cells[0])
                    ids = []
                    for c in cells[1:]:
                        found = re.findall(r"\bS\d+\b", c)
                        if found:
                            ids = found
                    if n in b.plan:
                        rep.err(f"line {i}", f"sprint {n} listed twice in the Sprint Plan")
                    b.plan[n] = ids
                    b.plan_goals[n] = cells[1] if len(cells) > 1 else ""
                continue
        m = EPIC_RE.match(line)
        if m:
            epic, feat, story = m.group(1), None, None
            if epic in b.epics:
                rep.err(f"line {i}", f"duplicate epic {epic}")
            b.epics[epic] = m.group(2)
            continue
        m = FEAT_RE.match(line)
        if m:
            feat, story = m.group(1), None
            if feat in b.features:
                rep.err(f"line {i}", f"duplicate feature {feat}")
            b.features[feat] = (m.group(2), epic)
            continue
        m = STORY_RE.match(line)
        if m:
            sid = m.group(1)
            if sid in b.stories:
                rep.err(f"line {i}", f"duplicate story {sid}")
            story = Story(sid, m.group(2), i, epic, feat)
            b.stories[sid] = story
            continue
        if H2_RE.match(line) or re.match(r"^###\s", line):
            story = None
            continue
        if story is None:
            continue
        m = FIELD_RE.match(line)
        if m:
            story.fields[m.group(1).lower()] = strip_comments(m.group(2)).strip()
            continue
        m = TASK_RE.match(line)
        if m:
            tid = m.group(2)
            if tid in task_ids:
                rep.err(f"line {i}", f"duplicate task {tid}")
            task_ids.add(tid)
            if f"S{m.group(3)}" != story.id:
                rep.err(f"line {i}", f"task {tid} sits under story {story.id}; number it T{story.id[1:]}.n")
            story.tasks.append((tid, m.group(1).lower() == "x", strip_comments(m.group(5)).strip(), i))
    return b, rep


def check_backlog(change: Change) -> Tuple[Report, Optional[Backlog]]:
    rep = Report()
    f = change.p("backlog.md")
    if not f.is_file():
        rep.err("backlog.md", "missing")
        return rep, None
    b, prep = parse_backlog(read(f))
    for e in prep.errors:
        rep.err("backlog.md", e)
    full = change.track == "full"
    if not b.stories:
        rep.err("backlog.md", "no stories found ('#### S1 - <story>')")
    if full:
        if not b.epics:
            rep.err("backlog.md", "full track needs at least one epic ('## E1 - <epic>')")
        for fid, (_, eid) in b.features.items():
            if not eid:
                rep.err("backlog.md", f"feature {fid} is not under an epic")
    scen = delta_scenarios(change)
    covered: Dict[str, List[str]] = {}
    for s in b.stories.values():
        where = f"backlog.md:{s.line} {s.id}"
        if full and not s.feature:
            rep.err(where, "story is not under a feature")
        pts = s.fields.get("points", "")
        if not pts:
            rep.err(where, "missing **Points**")
        elif not (pts.isdigit() and int(pts) in FIB):
            rep.err(where, f"points '{pts}' must be one of 1,2,3,5,8,13")
        elif int(pts) == 13:
            rep.warn(where, "13 points: consider splitting the story")
        pri = s.fields.get("priority", "").lower()
        if pri and pri not in PRIORITIES:
            rep.warn(where, f"priority '{pri}' is not MoSCoW (Must/Should/Could/Won't)")
        stype = s.fields.get("type", "story").lower()
        if not s.covers and stype not in ("enabler", "spike", "chore"):
            rep.err(where, "**Covers** lists no scenario IDs (mark **Type**: enabler|spike|chore if it covers none)")
        for sc in s.covers:
            if sc not in scen:
                rep.err(where, f"covers unknown scenario {sc}")
            covered.setdefault(sc, []).append(s.id)
        for d in s.depends:
            if d not in b.stories:
                rep.err(where, f"depends on unknown story {d}")
            if d == s.id:
                rep.err(where, "depends on itself")
        if not s.tasks:
            rep.err(where, "no tasks ('- [ ] T<story>.<n> <imperative> - files: <paths>')")
        for tid, _, text, line in s.tasks:
            if not re.search(r"\bfiles?\s*:\s*[^\s-]", text, re.I):
                (rep.err if full else rep.warn)(f"backlog.md:{line} {tid}", "task has no 'files:' boundary")
    for sc, (rid, title) in sorted(scen.items()):
        if sc not in covered:
            rep.err("backlog.md", f"scenario {sc} ({title}) of [{rid}] is not covered by any story")
    # dependency cycles
    state: Dict[str, int] = {}

    def visit(n: str, path: List[str]) -> None:
        state[n] = 1
        for d in b.stories[n].depends:
            if d not in b.stories:
                continue
            if state.get(d) == 1:
                rep.err("backlog.md", "dependency cycle: " + " -> ".join(path + [d]))
            elif not state.get(d):
                visit(d, path + [d])
        state[n] = 2

    for sid in b.stories:
        if not state.get(sid):
            visit(sid, [sid])
    # sprint plan
    if not b.plan:
        rep.err("backlog.md", "no '## Sprint Plan' table with rows '| 1 | <goal> | S1, S2 |'")
    else:
        where_planned: Dict[str, int] = {}
        for n, ids in sorted(b.plan.items()):
            if not ids:
                rep.err("backlog.md", f"sprint {n} has no stories")
            for sid in ids:
                if sid not in b.stories:
                    rep.err("backlog.md", f"sprint {n} lists unknown story {sid}")
                elif sid in where_planned:
                    rep.err("backlog.md", f"{sid} planned in sprints {where_planned[sid]} and {n}")
                else:
                    where_planned[sid] = n
        expected = list(range(1, len(b.plan) + 1))
        if sorted(b.plan) != expected:
            rep.err("backlog.md", f"sprints must be numbered 1..{len(b.plan)} without gaps")
        for sid, s in b.stories.items():
            won = s.fields.get("priority", "").lower() in ("won't", "wont")
            if sid not in where_planned and not won:
                rep.err("backlog.md", f"{sid} is not in any sprint (or mark **Priority**: Won't)")
            for d in s.depends:
                if sid in where_planned and d in where_planned and where_planned[d] > where_planned[sid]:
                    rep.err("backlog.md", f"{sid} (sprint {where_planned[sid]}) depends on {d} (sprint {where_planned[d]})")
    return rep, b


# --------------------------------------------------------------------------- traceability


def project_files(ws: Workspace) -> List[Path]:
    root = ws.project
    files: List[Path] = []
    try:
        out = subprocess.run(["git", "ls-files", "-co", "--exclude-standard"], cwd=root,
                             capture_output=True, text=True, check=True, timeout=60).stdout
        files = [root / ln for ln in out.splitlines() if ln]
    except (OSError, subprocess.SubprocessError):
        for d, dirs, names in os.walk(root):
            dirs[:] = [x for x in dirs if x not in SKIP_DIRS and not x.startswith(".")]
            files += [Path(d) / n for n in names]
    ws_root = ws.root.resolve()
    keep = []
    for f in files:
        try:
            rf = f.resolve()
        except OSError:
            continue
        if ws_root == rf or ws_root in rf.parents:
            continue
        if any(part in SKIP_DIRS for part in f.relative_to(root).parts[:-1]):
            continue
        keep.append(f)
    return keep


def git(ws: Workspace, *args: str) -> Optional[str]:
    try:
        r = subprocess.run(["git", *args], cwd=ws.project, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def changed_files(ws: Workspace, base: str) -> Optional[List[str]]:
    """Files changed since base (committed, staged, unstaged and untracked)."""
    diff = git(ws, "diff", "--name-only", base)
    if diff is None:
        return None
    untracked = git(ws, "ls-files", "--others", "--exclude-standard") or ""
    files = {ln for ln in (diff + "\n" + untracked).splitlines() if ln.strip()}
    ws_rel = ws.root.relative_to(ws.project).as_posix()
    return sorted(f for f in files if not (f == ws_rel or f.startswith(ws_rel + "/")))


def task_paths(story: "Story") -> List[str]:
    out = []
    for _, _, text, _ in story.tasks:
        m = re.search(r"\bfiles?\s*:\s*(.+?)(?:\s+[\u2014-]\s+owner\s*:.*)?$", text, re.I)
        if m:
            out += [x.strip(" `'\"") for x in re.split(r"[,\s]+", m.group(1)) if x.strip(" `'\"")]
    return out


def path_allowed(path: str, allowed: List[str]) -> bool:
    import fnmatch
    for a in allowed:
        a = a.rstrip("/")
        if path == a or path.startswith(a + "/") or fnmatch.fnmatch(path, a):
            return True
    return False


def scan_refs(ws: Workspace, ids: List[str]) -> Dict[str, Dict[str, List[str]]]:
    """id -> {'tests': [paths], 'code': [paths]}"""
    wanted = set(ids)
    out: Dict[str, Dict[str, List[str]]] = {i: {"tests": [], "code": []} for i in ids}
    if not wanted:
        return out
    for f in project_files(ws):
        try:
            if not f.is_file() or f.stat().st_size > 2_000_000:
                continue
            data = f.read_bytes()
        except OSError:
            continue
        if b"\0" in data[:2048]:
            continue
        text = data.decode("utf-8", "ignore")
        found = wanted.intersection(SCENARIO_ID_RE.findall(text))
        if not found:
            continue
        rel = f.relative_to(ws.project).as_posix()
        kind = "tests" if TEST_PATH_RE.search(rel) else "code"
        for i in found:
            out[i][kind].append(rel)
    return out


def trace_matrix(change: Change, only: Optional[List[str]] = None) -> Tuple[str, List[str]]:
    scen = delta_scenarios(change)
    b = None
    if change.p("backlog.md").is_file():
        b, _ = parse_backlog(read(change.p("backlog.md")))
    by_scn: Dict[str, List[str]] = {}
    if b:
        for s in b.stories.values():
            for sc in s.covers:
                by_scn.setdefault(sc, []).append(s.id)
    ids = sorted(scen) if only is None else sorted(i for i in scen if i in only)
    refs = scan_refs(change.ws, ids)
    gaps = []
    rows = ["| Scenario | Requirement | Stories | Status | Tests | Other code refs |",
            "|---|---|---|---|---|---|"]
    for sc in ids:
        rid, title = scen[sc]
        stories = by_scn.get(sc, [])
        st = "-"
        if b and stories:
            st = "done" if all(b.stories[x].done for x in stories) else "open"
        tests = refs[sc]["tests"]
        if not tests:
            gaps.append(sc)
        rows.append(f"| {sc} {title} | {rid} | {', '.join(stories) or '**none**'} | {st} | "
                    f"{'<br>'.join(tests) or '**none**'} | {'<br>'.join(refs[sc]['code']) or '-'} |")
    head = (f"# Traceability: {change.id}\n\nGenerated {now()} by specmaker.py trace. "
            f"{len(ids)} scenario(s), {len(ids) - len(gaps)} with tests, {len(gaps)} without.\n\n")
    return head + "\n".join(rows) + "\n", gaps


# --------------------------------------------------------------------------- spec merge


def split_living(text: str) -> Tuple[str, List[Requirement], str]:
    """(preamble up to and including '## Requirements', blocks, trailer after requirements)."""
    lines = text.splitlines()
    start = next((i for i, ln in enumerate(lines) if re.match(r"^##\s+Requirements\s*$", ln, re.I)), None)
    if start is None:
        return text.rstrip() + "\n\n## Requirements\n", [], ""
    end = next((i for i in range(start + 1, len(lines)) if H2_RE.match(lines[i])), len(lines))
    pre = "\n".join(lines[:start + 1]) + "\n"
    body = "\n".join(lines[start:end])
    trailer = "\n".join(lines[end:])
    reqs, _, _ = parse_requirements(body, delta=False)
    return pre, reqs, trailer


def render_living(pre: str, reqs: List[Requirement], trailer: str) -> str:
    out = pre.rstrip() + "\n\n" + "\n".join(r.text.rstrip() + "\n" for r in reqs)
    if trailer.strip():
        out = out.rstrip() + "\n\n" + trailer.strip() + "\n"
    return out.rstrip() + "\n"


def merge_change(change: Change, dry: bool) -> List[str]:
    """Apply delta specs to living specs, then verify the result independently."""
    log = []
    expect_present: Dict[str, Tuple[str, int]] = {}
    expect_absent: Dict[str, str] = {}
    before = load_living(change.ws)
    for f in change.delta_specs():
        cap = capability_of(change, f)
        text = read(f)
        reqs, _, h2 = parse_requirements(text, delta=True)
        target = living_spec_path(change.ws, cap)
        if target.is_file():
            pre, living, trailer = split_living(read(target))
        else:
            purpose = strip_comments(h2.get("purpose", "")).strip() or "TBD - add purpose."
            pre = f"# {cap}\n\n## Purpose\n\n{purpose}\n\n## Requirements\n"
            living, trailer = [], ""
            log.append(f"create  specs/{cap}/spec.md")
        index = {r.id: k for k, r in enumerate(living)}
        for r in reqs:
            if r.section in ("ADDED", "MODIFIED"):
                expect_present[r.id] = (cap, len(r.scenarios))
            elif r.section == "REMOVED":
                expect_absent[r.id] = cap
            if r.section == "ADDED":
                living.append(r)
                index[r.id] = len(living) - 1
                log.append(f"add     [{r.id}] -> {cap}")
            elif r.section == "MODIFIED":
                k = index.get(r.id)
                if k is None:
                    die(f"cannot modify [{r.id}]: not in specs/{cap}/spec.md")
                living[k] = r
                log.append(f"modify  [{r.id}] in {cap}")
            elif r.section == "REMOVED":
                k = index.get(r.id)
                if k is None:
                    die(f"cannot remove [{r.id}]: not in specs/{cap}/spec.md")
                living[k] = None  # type: ignore[call-overload]
                log.append(f"remove  [{r.id}] from {cap}")
        living = [r for r in living if r is not None]
        for r in living:
            r.section = "LIVING"
        if not dry:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(render_living(pre, living, trailer), encoding="utf-8")
    if dry:
        return log
    # independent verification of the merge result
    after = load_living(change.ws)
    problems = []
    for rid, (cap, n_scn) in expect_present.items():
        hit = after.get(rid)
        if not hit or hit[0] != cap:
            problems.append(f"[{rid}] missing from specs/{cap} after merge")
        elif len(hit[1].scenarios) != n_scn:
            problems.append(f"[{rid}] has {len(hit[1].scenarios)} scenario(s), delta had {n_scn}")
    for rid in expect_absent:
        if rid in after:
            problems.append(f"[{rid}] still present after REMOVED")
    for rid, (cap, r) in before.items():
        if rid not in expect_present and rid not in expect_absent:
            hit = after.get(rid)
            if not hit or hit[1].text != r.text:
                problems.append(f"[{rid}] was not part of this change but changed during merge")
    if problems:
        die("merge verification failed:\n  " + "\n  ".join(problems))
    added = sum(1 for k in expect_present if k not in before)
    untouched = sum(1 for k in before if k not in expect_present and k not in expect_absent)
    log.append(f"verified: {added} added, {len(expect_present) - added} modified, "
               f"{len(expect_absent)} removed, {untouched} untouched")
    return log


def promote_adrs(change: Change, dry: bool) -> List[str]:
    """Copy the change's ADRs into the project-wide decision log with global numbers."""
    dest = change.ws.root / "adrs"
    existing = [int(m.group(1)) for f in (dest.glob("*.md") if dest.is_dir() else [])
                if (m := re.match(r"^(\d{4})-", f.name))]
    nxt = max(existing or [0]) + 1
    log = []
    for f in change.adrs():
        slug = re.sub(r"^\d{4}-", "", f.name)
        name = f"{nxt:04d}-{slug}"
        text = read(f)
        text = re.sub(r"^(#\s*ADR)[- ]?\d{1,4}", lambda m: f"{m.group(1)}-{nxt:04d}", text, count=1, flags=re.M)
        text = text.rstrip() + f"\n\n<!-- promoted from change {change.id} ({f.name}) on {today()} -->\n"
        if not dry:
            dest.mkdir(parents=True, exist_ok=True)
            (dest / name).write_text(text, encoding="utf-8")
        log.append(f"adr     {change.rel(f)} -> adrs/{name}")
        nxt += 1
    return log


# --------------------------------------------------------------------------- gates


def design_report(change: Change) -> Report:
    rep = Report()
    track = change.track
    if track == "full" or change.p("hld.md").is_file():
        rep.extend(lint_doc(change, "hld.md", HLD_REQUIRED[track]))
    rep.extend(lint_doc(change, "lld.md", LLD_REQUIRED[track]))
    rep.extend(check_specs(change))
    rep.extend(check_adrs(change))
    if track == "full" and not change.adrs():
        rep.warn("adrs/", "no ADRs; record framework, data, and deployment decisions unless project.md already settles them")
    return rep


# Minimum goldfish lenses that must have reported (in any round) before a verdict.
REQUIRED_LENSES = {"full": ["consistency", "readiness"], "lite": ["readiness"]}
REVIEW_NAME_RE = re.compile(r"^accredit-r(\d+)-([a-z0-9-]+)\.md$")


def review_lenses(change: "Change") -> Dict[str, List[int]]:
    """lens -> rounds it reported in, from reviews/accredit-r<N>-<lens>.md."""
    out: Dict[str, List[int]] = {}
    d = change.p("reviews")
    if d.is_dir():
        for f in d.glob("accredit-r*-*.md"):
            m = REVIEW_NAME_RE.match(f.name)
            if m:
                out.setdefault(m.group(2), []).append(int(m.group(1)))
    return out


def gate(change: Change, target: str) -> Report:
    rep = Report()
    cur = change.phase
    order = PHASES.index
    if target == "archived":
        rep.err("phase", "use `archive` to archive a change")
        return rep
    if target not in PHASES:
        rep.err("phase", f"unknown phase '{target}'")
        return rep
    if order(target) <= order(cur):
        rep.err("phase", f"'{target}' is not ahead of '{cur}'; use `amend` to reopen design")
        return rep
    docs_jump = change.state.get("docs_only") and cur == "accredit" and target == "retro"
    if order(target) != order(cur) + 1 and not docs_jump:
        rep.err("phase", f"phases advance one at a time ({cur} -> {PHASES[order(cur) + 1]})"
                + ("; a docs-only change may go accredit -> retro" if change.state.get("docs_only") else ""))
        return rep
    if docs_jump:
        acc = change.state.get("accreditation") or {}
        if acc.get("verdict") not in ("approved", "conditional"):
            rep.err("accreditation", "design is not accredited")
        if change.lock_drift():
            rep.err("lock", "design changed after accreditation: " + ", ".join(change.lock_drift()))
        return rep
    if target == "propose":
        rep.extend(lint_doc(change, "hld.md", HLD_REQUIRED[change.track]))
    elif target == "accredit":
        rep.extend(design_report(change))
    elif target == "scrum":
        acc = change.state.get("accreditation") or {}
        if acc.get("verdict") not in ("approved", "conditional"):
            rep.err("accreditation", "design is not accredited; run the accredit phase and record a human verdict")
        drift = change.lock_drift()
        if drift:
            rep.err("lock", "design changed after accreditation: " + ", ".join(drift))
    elif target == "sprint":
        brep, _ = check_backlog(change)
        rep.extend(brep)
        drift = change.lock_drift()
        if drift:
            rep.err("lock", "design changed after accreditation: " + ", ".join(drift))
    elif target == "retro":
        if change.state.get("docs_only"):
            return rep
        _, b = check_backlog(change)
        sprints = change.state.get("sprints", {})
        if b:
            for n in sorted(b.plan):
                if sprints.get(str(n), {}).get("status") != "signed-off":
                    rep.err("sprints", f"sprint {n} is not signed off")
    return rep


def next_step(change: Change) -> str:
    ph = change.phase
    if ph == "ideate":
        return "Converse to shape the HLD (skill: specmaker-ideate), then `phase <id> propose`."
    if ph == "propose":
        return "Draft LLD, delta specs and ADRs (skill: specmaker-propose), then `phase <id> accredit`."
    if ph == "accredit":
        acc = change.state.get("accreditation") or {}
        if acc.get("verdict") == "rejected":
            return "Verdict was rejected: address findings, `amend`, and re-run accredit."
        if acc.get("verdict") in ("approved", "conditional"):
            return "Accredited. Run `phase <id> scrum` (skill: specmaker-scrum)."
        return "Run goldfish reviews and get the human verdict (skill: specmaker-accredit)."
    if ph == "scrum":
        return "Build backlog.md with sprint plan (skill: specmaker-scrum), then `phase <id> sprint`."
    if ph == "sprint":
        sprints = change.state.get("sprints", {})
        active = [n for n, s in sprints.items() if s.get("status") == "active"]
        if active:
            return f"Continue sprint {active[0]} (skill: specmaker-sprint); finish with `signoff <id> {active[0]}`."
        nxt = 1 + max([int(n) for n in sprints] or [0])
        return f"Start sprint {nxt}: `sprint-start <id> {nxt}` (skill: specmaker-sprint), or `phase <id> retro` when all are signed off."
    if ph == "retro":
        if change.p("retro.md").is_file():
            return "Review `archive <id> --dry-run` with the user, then `archive <id>` (skill: specmaker-retro)."
        return "Write retro.md and merge specs (skill: specmaker-retro), then `archive <id>`."
    return "Archived."


# --------------------------------------------------------------------------- commands


AGENTS_START = "<!-- specmaker:start -->"
AGENTS_END = "<!-- specmaker:end -->"
AGENTS_BLOCK = AGENTS_START + """
## Spec-driven workflow (specmaker)

This project uses Ayuna specmaker; its workspace is `{root}/`.

- Before answering questions about, or changing anything in, `{root}/` (changes,
  specs, ADRs, backlogs, sprints), load the `specmaker` skill with your skill
  tool, then the phase skill it names. Do not work from those files without it,
  and never edit `{root}/changes/*/change.json` by hand.
- Before changing behaviour, check whether a living spec in `{root}/specs/`
  covers it. If one does, the change goes through specmaker.
""" + AGENTS_END


def write_agents_block(ws: "Workspace") -> str:
    """Create or refresh the managed specmaker block in AGENTS.md, and in CLAUDE.md when it exists.

    OpenCode reads AGENTS.md (CLAUDE.md only as a fallback); Claude Code reads CLAUDE.md and reads
    AGENTS.md only when no CLAUDE.md exists. Writing both covers every combination."""
    out = [_write_block(ws, ws.project / "AGENTS.md")]
    if (ws.project / "CLAUDE.md").exists():
        out.append(_write_block(ws, ws.project / "CLAUDE.md"))
    return "\n".join(out)


def _write_block(ws: "Workspace", target: Path) -> str:
    block = AGENTS_BLOCK.format(root=ws.root.relative_to(ws.project).as_posix())
    text = read(target) if target.exists() else ""
    if AGENTS_START in text and AGENTS_END in text:
        new = re.sub(re.escape(AGENTS_START) + r".*?" + re.escape(AGENTS_END), lambda _: block, text, flags=re.S)
        verb = "updated" if new != text else "kept"
    else:
        new = (text.rstrip() + "\n\n" if text.strip() else "") + block + "\n"
        verb = "updated" if text else "created"
    if new != text:
        target.write_text(new, encoding="utf-8")
    return f"{verb:7s} {target.name} (specmaker block)"


def cmd_init(a: argparse.Namespace) -> int:
    ws = Workspace.locate(a.root, must_exist=False) if a.root else Workspace(Path.cwd().resolve() / DEFAULT_ROOT)
    for d in (ws.specs, ws.changes, ws.archive, ws.root / "adrs"):
        d.mkdir(parents=True, exist_ok=True)
        keep = d / ".gitkeep"
        if not any(d.iterdir()):
            keep.touch()
    pm = ws.root / "project.md"
    if pm.exists():
        print(f"kept    {pm.relative_to(ws.project)} (already exists)")
    else:
        shutil.copyfile(TEMPLATES / "project.md", pm)
        print(f"created {pm.relative_to(ws.project)}")
    if not a.no_agents_md:
        print(write_agents_block(ws))
    print(f"workspace ready at {ws.root}")
    return 0


def cmd_new(a: argparse.Namespace) -> int:
    ws = Workspace.locate(a.root)
    cid = a.id
    if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", cid) or len(cid) > 64:
        die("change id must be kebab-case, at most 64 chars (e.g. add-sso-login)")
    d = ws.changes / cid
    if d.exists():
        die(f"change '{cid}' already exists")
    if any(p.name.endswith("-" + cid) for p in ws.archive.iterdir()) if ws.archive.is_dir() else False:
        print(f"note: an archived change named '{cid}' exists", file=sys.stderr)
    for sub in ("specs", "adrs", "reviews", "sprints"):
        (d / sub).mkdir(parents=True)
    state = {
        "id": cid, "title": a.title or cid.replace("-", " ").capitalize(), "track": a.track,
        "phase": "ideate" if a.track == "full" else "propose", "created": now(),
        "skip_specs": False, "accreditation": None, "sprints": {}, "history": [],
        "specmaker": VERSION,
    }
    (d / STATE_FILE).write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    ch = Change(ws, d)
    ch.log("created", f"track={a.track}")
    ch.save()
    print(f"created {d.relative_to(ws.project)}/ (track={a.track}, phase={ch.phase})")
    return 0


def cmd_list(a: argparse.Namespace) -> int:
    ws = Workspace.locate(a.root)
    ids = ws.change_ids()
    if a.json:
        print(json.dumps([{"id": i, "phase": ws.change(i).phase, "track": ws.change(i).track} for i in ids], indent=2))
        return 0
    if not ids:
        print("no active changes")
    for i in ids:
        c = ws.change(i)
        print(f"{i:40s} {c.phase:9s} {c.track:5s} {c.state.get('title', '')}")
    arch = sorted(p.name for p in ws.archive.iterdir() if p.is_dir()) if ws.archive.is_dir() else []
    if arch and not a.json:
        print(f"\n{len(arch)} archived: " + ", ".join(arch[-5:]) + (" ..." if len(arch) > 5 else ""))
    return 0


def cmd_status(a: argparse.Namespace) -> int:
    ws = Workspace.locate(a.root)
    ids = [a.id] if a.id else ws.change_ids()
    if not ids:
        print("no active changes. Start one with `specmaker.py new <id>`.")
        return 0
    payload = []
    for cid in ids:
        c = ws.change(cid)
        files = {n: c.p(n).is_file() for n in ("hld.md", "lld.md", "accreditation.md", "backlog.md", "retro.md")}
        info = {
            "id": c.id, "title": c.state.get("title"), "track": c.track, "phase": c.phase,
            "artifacts": {**files, "delta_specs": len(c.delta_specs()), "adrs": len(c.adrs()),
                          "reviews": sorted(p.name for p in c.p("reviews").glob("*.md")) if c.p("reviews").is_dir() else []},
            "accreditation": {k: v for k, v in (c.state.get("accreditation") or {}).items() if k not in ("lock", "base")} or None,
            "lock_drift": c.lock_drift(),
            "sprints": c.state.get("sprints", {}),
            "next": next_step(c).replace("<id>", c.id),
            "human_gates": human_gate_mode(ws),
            "last_event": (c.state.get("history") or [{}])[-1],
        }
        if c.p("backlog.md").is_file():
            b, _ = parse_backlog(read(c.p("backlog.md")))
            tasks = [t for s in b.stories.values() for t in s.tasks]
            info["backlog"] = {"stories": len(b.stories), "stories_done": sum(s.done for s in b.stories.values()),
                               "tasks": len(tasks), "tasks_done": sum(t[1] for t in tasks), "sprints_planned": len(b.plan)}
        payload.append(info)
    if a.json:
        print(json.dumps(payload if not a.id else payload[0], indent=2))
        return 0
    for info in payload:
        print(f"# {info['id']} - {info['title']}")
        print(f"  track {info['track']}, phase {info['phase'].upper()}, human gates: {info['human_gates']}")
        art = info["artifacts"]
        print("  artifacts: " + ", ".join(
            [f"{k}{'' if v else ' (missing)'}" for k, v in art.items() if isinstance(v, bool)]
            + [f"{art['delta_specs']} delta spec(s)", f"{art['adrs']} ADR(s)", f"{len(art['reviews'])} review(s)"]))
        if info["accreditation"]:
            acc = info["accreditation"]
            print(f"  accreditation: {acc.get('verdict')} by {acc.get('by')} at {acc.get('at')}"
                  + (f" (via {acc['via']})" if acc.get("via") else ""))
        if info["lock_drift"]:
            print("  LOCK BROKEN - design changed after accreditation: " + ", ".join(info["lock_drift"]))
        if "backlog" in info:
            bk = info["backlog"]
            print(f"  backlog: {bk['stories_done']}/{bk['stories']} stories, {bk['tasks_done']}/{bk['tasks']} tasks, {bk['sprints_planned']} sprint(s) planned")
        for n, s in sorted(info["sprints"].items(), key=lambda kv: int(kv[0])):
            print(f"  sprint {n}: {s.get('status')}" + (f" by {s.get('by')}" if s.get("by") else ""))
        print(f"  next: {info['next']}\n")
    return 0


def cmd_check(a: argparse.Namespace) -> int:
    ws = Workspace.locate(a.root)
    c = ws.change(a.id)
    what = a.what or ["auto"]
    total = Report()
    runs: List[Tuple[str, Report]] = []
    if "auto" in what or "all" in what:
        what = []
        if c.p("hld.md").is_file() or (c.track == "full" and c.phase != "ideate"):
            what.append("hld")
        if c.phase not in ("ideate",):
            what += ["lld", "specs", "adrs"]
        if c.p("backlog.md").is_file() or PHASES.index(c.phase) >= PHASES.index("sprint"):
            what.append("backlog")
        for n in sorted(c.state.get("sprints", {}), key=int):
            what.append(f"sprint:{n}")
    for w in what:
        if w == "hld":
            r = lint_doc(c, "hld.md", HLD_REQUIRED[c.track])
        elif w == "lld":
            r = lint_doc(c, "lld.md", LLD_REQUIRED[c.track])
        elif w == "specs":
            r = check_specs(c)
        elif w == "adrs":
            r = check_adrs(c)
        elif w == "design":
            r = design_report(c)
        elif w == "backlog":
            r, _ = check_backlog(c)
        elif w.startswith("sprint:"):
            r = check_sprint(c, int(w.split(":", 1)[1]), for_signoff=False)
        else:
            die(f"unknown check '{w}' (hld, lld, specs, adrs, design, backlog, sprint:N, all)")
        runs.append((w, r))
        total.extend(r)
    if a.json:
        print(json.dumps({w: {"ok": r.ok, "errors": r.errors, "warnings": r.warnings} for w, r in runs}, indent=2))
    else:
        for w, r in runs:
            print(r.render(w))
    return 0 if total.ok else 1


def cmd_set(a: argparse.Namespace) -> int:
    ws = Workspace.locate(a.root)
    c = ws.change(a.id)
    if a.key in ("skip_specs", "docs_only"):
        if a.key == "docs_only" and c.state.get("accreditation"):
            die("set docs_only before accreditation, so reviewers know nothing will be built")
        c.state[a.key] = a.value.lower() in ("1", "true", "yes")
    elif a.key == "depends_on":
        deps = [x.strip() for x in a.value.split(",") if x.strip()]
        for d in deps:
            if d == c.id:
                die("a change cannot depend on itself")
        c.state["depends_on"] = deps
    elif a.key == "title":
        c.state["title"] = a.value
    elif a.key == "track":
        if a.value not in TRACKS:
            die("track must be full or lite")
        if c.state.get("accreditation"):
            die("cannot change track after accreditation")
        c.state["track"] = a.value
    else:
        die("settable keys: skip_specs, docs_only, title, track, depends_on")
    c.log("set", f"{a.key}={a.value}")
    c.save()
    print(f"{a.id}: {a.key} = {a.value}")
    return 0


def cmd_phase(a: argparse.Namespace) -> int:
    ws = Workspace.locate(a.root)
    c = ws.change(a.id)
    rep = gate(c, a.target)
    print(rep.render(f"gate {c.phase} -> {a.target}"))
    if not rep.ok:
        return 1
    prev = c.phase
    c.state["phase"] = a.target
    c.log("phase", f"{prev} -> {a.target}")
    c.save()
    print(f"{c.id}: phase {prev} -> {a.target}\nnext: {next_step(c).replace('<id>', c.id)}")
    return 0


def human_gate_mode(ws: Workspace) -> str:
    """'terminal' or 'chat', from project.md ('- Human gates: terminal'). Missing -> chat."""
    pm = ws.root / "project.md"
    if pm.is_file():
        m = re.search(r"^\s*[-*]\s*Human gates\s*:\s*\**(terminal|chat)\b", strip_comments(read(pm)), re.M | re.I)
        if m:
            return m.group(1).lower()
    return "chat"


def confirm_human(ws: Workspace, what: str, by: Optional[str], cmdline: str) -> Tuple[str, str]:
    """Return (name, via). In terminal mode a person must type their name at an interactive terminal."""
    if human_gate_mode(ws) != "terminal":
        if not by or not by.strip():
            die("--by must name the human who decided")
        return by.strip(), "chat"
    if not sys.stdin.isatty():
        die("this is a human gate, and project.md sets 'Human gates: terminal'.\n"
            "A person must run it in their own interactive terminal:\n\n"
            f"    {cmdline}\n\n"
            "Agents: copy this command to the user character for character, say they must run it in their own\n"
            "terminal and type their name, then stop. Do not run it again, and do not offer to run it.", code=3)
    print(f"\nHUMAN GATE: {what}")
    try:
        name = input("Type your full name to confirm (empty to cancel): ").strip()
    except EOFError:
        name = ""
    if not name:
        die("cancelled; nothing recorded", code=3)
    if by and by.strip() and name != by.strip():
        die(f"typed name '{name}' does not match --by '{by.strip()}'; nothing recorded", code=3)
    return name, "terminal"


def gate_cmdline(ws: Workspace, *parts: str) -> str:
    """Command for the human, relative to the project root when the script lives inside it."""
    import shlex
    script = Path(__file__).resolve()
    try:
        shown = script.relative_to(ws.project.resolve()).as_posix()
        prefix = f"cd {shlex.quote(str(ws.project))} && " if Path.cwd().resolve() != ws.project.resolve() else ""
    except ValueError:
        shown, prefix = str(script), ""
    return prefix + " ".join(["python3", shlex.quote(shown)] + [shlex.quote(x) for x in parts])


def cmd_accredit(a: argparse.Namespace) -> int:
    ws = Workspace.locate(a.root)
    c = ws.change(a.id)
    if c.phase != "accredit":
        die(f"change is in phase '{c.phase}'; accreditation happens in phase 'accredit'")
    rep = design_report(c)
    lenses = review_lenses(c)
    for lens in REQUIRED_LENSES[c.track]:
        if lens not in lenses:
            rep.err("reviews/", f"no goldfish report for lens '{lens}' (reviews/accredit-r<N>-{lens}.md)")
    if not c.p("accreditation.md").is_file():
        rep.err("accreditation.md", "missing; write the accreditation record before recording a verdict")
    if a.verdict != "rejected":
        print(rep.render("accreditation preconditions"))
        if not rep.ok:
            return 1
    if a.verdict == "conditional" and not a.condition:
        die("a conditional verdict needs at least one --condition")
    parts = ["accredit", c.id, "--verdict", a.verdict] + [x for cond in (a.condition or []) for x in ("--condition", cond)]
    by, via = confirm_human(ws, f"record verdict '{a.verdict.upper()}' for design of change '{c.id}'", a.by, gate_cmdline(ws, *parts))
    rec = {"verdict": a.verdict, "by": by, "via": via, "at": now(), "conditions": a.condition or []}
    if a.verdict in ("approved", "conditional"):
        rec["lock"] = {c.rel(f): sha256(f) for f in c.design_files()}
        rec["base"] = base_hashes(c)
    c.state["accreditation"] = rec
    c.log("accredit", f"{a.verdict} by {by} (via {via})")
    c.save()
    print(f"{c.id}: verdict {a.verdict.upper()} recorded for {by} (via {via})")
    if "lock" in rec:
        print(f"locked {len(rec['lock'])} design file(s). Any later edit breaks the lock and requires `amend`.")
    return 0


def cmd_amend(a: argparse.Namespace) -> int:
    ws = Workspace.locate(a.root)
    c = ws.change(a.id)
    if c.phase in ("ideate", "propose", "archived"):
        die(f"nothing to amend in phase '{c.phase}'")
    prev = c.phase
    old = c.state.get("accreditation")
    if old:
        c.state.setdefault("superseded_accreditations", []).append(old)
    c.state["accreditation"] = None
    for n, s in c.state.get("sprints", {}).items():
        if s.get("status") == "active":
            s["status"] = "interrupted"
    c.state["phase"] = "propose"
    c.log("amend", f"from {prev}: {a.reason}")
    c.save()
    print(f"{c.id}: reopened design ({prev} -> propose). Reason recorded. Re-accreditation is required.")
    return 0


def check_sprint(c: Change, n: int, for_signoff: bool) -> Report:
    rep = Report()
    f = c.sprint_file(n)
    where = c.rel(f)
    if not f.is_file():
        rep.err(where, "missing")
        return rep
    secs = sections(read(f), 2)
    for key in ("goal", "committed", "verification", "sign-off"):
        body = find_section(secs, key)
        if body is None:
            rep.err(where, f"missing section containing '{key}'")
        elif key != "sign-off" and not has_content(body):
            rep.err(where, f"section '{key}' is empty")
    dev = find_section(secs, "deviation")
    if dev and re.search(r"^\s*[-*]\s+\[ \]", strip_comments(dev), re.M):
        rep.err(where, "has unresolved deviations ('- [ ]' under Deviations); resolve or `amend` the design")
    brep, b = check_backlog(c)
    if not b:
        rep.extend(brep)
        return rep
    planned = b.plan.get(n)
    if planned is None:
        rep.err("backlog.md", f"sprint {n} is not in the Sprint Plan")
        return rep
    if for_signoff:
        for sid in planned:
            s = b.stories.get(sid)
            if s and not s.done:
                open_t = [t[0] for t in s.tasks if not t[1]]
                rep.err("backlog.md", f"{sid} has open tasks: {', '.join(open_t)}")
        vf = c.verification_file(n)
        if not vf.is_file():
            rep.err(c.rel(vf), "missing goldfish verification report")
        else:
            m = re.search(r"^\W*Verdict\W*:\W*(PASS-WITH-NOTES|PASS|FAIL)\b", read(vf), re.M | re.I)
            if not m:
                rep.err(c.rel(vf), "needs a 'Verdict: PASS | PASS-WITH-NOTES | FAIL' line")
            elif m.group(1).upper() == "FAIL":
                rep.err(c.rel(vf), "verification verdict is FAIL")
        drift = c.lock_drift()
        if drift:
            rep.err("lock", "design changed after accreditation: " + ", ".join(drift))
        rep.extend(check_boundary(c, n, b))
        rep.extend(check_gates_evidence(c, n))
    return rep


def check_boundary(c: Change, n: int, b: Backlog) -> Report:
    """Changed files must be inside the sprint's task file boundary or be declared as deviations."""
    rep = Report()
    base = c.state.get("sprints", {}).get(str(n), {}).get("base_sha")
    if not base:
        rep.warn("boundary", "no git base recorded for this sprint; file boundary not checked")
        return rep
    changed = changed_files(c.ws, base)
    if changed is None:
        rep.warn("boundary", "git diff failed; file boundary not checked")
        return rep
    allowed: List[str] = []
    for sid in b.plan.get(n, []):
        if sid in b.stories:
            allowed += task_paths(b.stories[sid])
    sprint_text = read(c.sprint_file(n)) if c.sprint_file(n).is_file() else ""
    dev = find_section(sections(sprint_text, 2), "deviation") or ""
    for f in changed:
        if not path_allowed(f, allowed) and f not in dev:
            rep.err("boundary", f"{f} changed but is outside the sprint's task files; "
                    f"revert it or record it under '## Deviations' in {c.rel(c.sprint_file(n))}")
    return rep


GATE_RE = re.compile(r"^\s*[-*]\s+\**([A-Za-z][\w .-]*?)\**\s*:\s*`([^`]+)`\s*$")


def quality_gates(ws: Workspace) -> List[Tuple[str, str]]:
    pm = ws.root / "project.md"
    if not pm.is_file():
        return []
    body = find_section(sections(read(pm), 2), "quality gates") or ""
    return [(m.group(1).strip(), m.group(2).strip()) for ln in strip_comments(body).splitlines()
            if (m := GATE_RE.match(ln))]


def gates_file(c: Change, n: int) -> Path:
    return c.p(f"reviews/sprint-{n:02d}-gates.json")


def check_gates_evidence(c: Change, n: int) -> Report:
    rep = Report()
    gates = quality_gates(c.ws)
    if not gates:
        rep.warn("gates", "project.md lists no '## Quality Gates'; sign-off has no machine evidence")
        return rep
    gf = gates_file(c, n)
    if not gf.is_file():
        rep.err("gates", f"no gate run recorded; run `specmaker.py gates {c.id} {n}`")
        return rep
    rec = json.loads(read(gf))
    if not rec.get("passed"):
        failed = [g["name"] for g in rec.get("results", []) if g.get("exit") != 0]
        rep.err("gates", "last gate run failed: " + ", ".join(failed))
    head = git(c.ws, "rev-parse", "HEAD")
    if head and rec.get("sha") != head:
        rep.err("gates", f"gates ran at {str(rec.get('sha'))[:10]} but HEAD is {head[:10]}; re-run gates on the code being signed off")
    if rec.get("dirty"):
        rep.warn("gates", "gates ran on a working tree with uncommitted changes; commit before sign-off for a reproducible record")
    names = {g["name"] for g in rec.get("results", [])}
    for name, _ in gates:
        if name not in names:
            rep.err("gates", f"gate '{name}' was not run")
    return rep


def cmd_gates(a: argparse.Namespace) -> int:
    ws = Workspace.locate(a.root)
    c = ws.change(a.id)
    gates = quality_gates(ws)
    if not gates:
        die("project.md has no '## Quality Gates' entries like: - test: `npm test`")
    results = []
    for name, cmd in gates:
        print(f"--> {name}: {cmd}", flush=True)
        try:
            r = subprocess.run(cmd, shell=True, cwd=ws.project, capture_output=True, text=True, timeout=a.timeout)
            code, out = r.returncode, (r.stdout + r.stderr)
        except subprocess.TimeoutExpired as e:
            code, out = 124, f"timed out after {a.timeout}s\n" + str(e.stdout or "")
        tail = "\n".join(out.strip().splitlines()[-40:])
        print(("    PASS" if code == 0 else f"    FAIL (exit {code})") + ("\n" + tail if code else ""), flush=True)
        results.append({"name": name, "cmd": cmd, "exit": code, "tail": tail})
    rec = {"at": now(), "sprint": a.n, "sha": git(ws, "rev-parse", "HEAD"),
           "dirty": bool(git(ws, "status", "--porcelain")), "passed": all(r["exit"] == 0 for r in results),
           "results": results}
    gf = gates_file(c, a.n)
    gf.parent.mkdir(parents=True, exist_ok=True)
    gf.write_text(json.dumps(rec, indent=2) + "\n", encoding="utf-8")
    c.log("gates", f"sprint {a.n}: {'PASS' if rec['passed'] else 'FAIL'}")
    c.save()
    print(f"{'PASS' if rec['passed'] else 'FAIL'} - recorded in {c.rel(gf)}")
    return 0 if rec["passed"] else 1


LEDGER_KINDS = ["decision", "declined", "question", "answer", "deviation", "condition", "note"]


def cmd_ledger(a: argparse.Namespace) -> int:
    """Append-only decision ledger. Reviewers read it so settled points are not re-raised."""
    ws = Workspace.locate(a.root)
    c = ws.change(a.id)
    f = c.p("ledger.md")
    if not a.text:
        print(read(f) if f.is_file() else "ledger is empty")
        return 0
    text = " ".join(a.text).strip()
    if not f.is_file():
        f.write_text(f"# Ledger: {c.id}\n\nAppend-only. Written by `specmaker.py ledger`. Do not edit entries; add a new one to supersede.\n\n", encoding="utf-8")
    n = len(re.findall(r"^- \*\*L-\d+\*\*", read(f), re.M)) + 1
    ref = f" (re: {a.ref})" if a.ref else ""
    with f.open("a", encoding="utf-8") as fh:
        fh.write(f"- **L-{n:03d}** `{a.kind.upper()}` {today()} [{c.phase}]{ref}: {text}\n")
    print(f"L-{n:03d} recorded")
    return 0


def cmd_export(a: argparse.Namespace) -> int:
    """Export the backlog for issue trackers (Jira/GitHub/Linear CSV import) or tooling."""
    import csv
    import io
    ws = Workspace.locate(a.root)
    c = ws.change(a.id)
    if not c.p("backlog.md").is_file():
        die("backlog.md is missing")
    b, _ = parse_backlog(read(c.p("backlog.md")))
    sprint_of = {sid: n for n, ids in b.plan.items() for sid in ids}
    rows = []
    for eid, title in b.epics.items():
        rows.append({"id": eid, "type": "Epic", "title": title, "parent": "", "points": "", "priority": "",
                     "sprint": "", "covers": "", "depends": "", "status": ""})
    for fid, (title, eid) in b.features.items():
        rows.append({"id": fid, "type": "Feature", "title": title, "parent": eid or "", "points": "", "priority": "",
                     "sprint": "", "covers": "", "depends": "", "status": ""})
    for s in b.stories.values():
        rows.append({"id": s.id, "type": s.fields.get("type", "Story").capitalize(), "title": s.title,
                     "parent": s.feature or s.epic or "", "points": s.fields.get("points", ""),
                     "priority": s.fields.get("priority", ""), "sprint": sprint_of.get(s.id, ""),
                     "covers": " ".join(s.covers), "depends": " ".join(s.depends),
                     "status": "Done" if s.done else "To Do"})
        for tid, done, text, _ in s.tasks:
            rows.append({"id": tid, "type": "Task", "title": text, "parent": s.id, "points": "", "priority": "",
                         "sprint": sprint_of.get(s.id, ""), "covers": "", "depends": "",
                         "status": "Done" if done else "To Do"})
    for r in rows:
        r["change"] = c.id
    if a.format == "json":
        print(json.dumps(rows, indent=2))
    else:
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=list(rows[0].keys()) if rows else ["id"])
        w.writeheader()
        w.writerows(rows)
        print(buf.getvalue(), end="")
    return 0


def cmd_sprint_start(a: argparse.Namespace) -> int:
    ws = Workspace.locate(a.root)
    c = ws.change(a.id)
    if c.phase != "sprint":
        die(f"change is in phase '{c.phase}'; run `phase {c.id} sprint` first")
    drift = c.lock_drift()
    if drift:
        die("design changed after accreditation (" + ", ".join(drift) + "). Run `amend` and re-accredit.")
    brep, b = check_backlog(c)
    if not brep.ok or not b:
        print(brep.render("backlog"))
        return 1
    n = a.n
    if n not in b.plan:
        die(f"sprint {n} is not in the Sprint Plan (planned: {sorted(b.plan)})")
    sprints = c.state.setdefault("sprints", {})
    for k, s in sprints.items():
        if s.get("status") == "active" and int(k) != n:
            die(f"sprint {k} is still active; sign it off first")
    for k in range(1, n):
        if sprints.get(str(k), {}).get("status") != "signed-off":
            die(f"sprint {k} is not signed off")
    if sprints.get(str(n), {}).get("status") == "signed-off":
        die(f"sprint {n} is already signed off")
    sprints[str(n)] = {"status": "active", "started": now(), "stories": b.plan[n],
                       "base_sha": git(ws, "rev-parse", "HEAD")}
    c.log("sprint-start", str(n))
    c.save()
    f = c.sprint_file(n)
    print(f"{c.id}: sprint {n} active with {', '.join(b.plan[n])}")
    print(f"sprint file: {c.rel(f)}{' (exists)' if f.is_file() else ' (create it from the sprint template)'}")
    return 0


def cmd_signoff(a: argparse.Namespace) -> int:
    ws = Workspace.locate(a.root)
    c = ws.change(a.id)
    n = a.n
    s = c.state.get("sprints", {}).get(str(n))
    if not s or s.get("status") != "active":
        die(f"sprint {n} is not active")
    rep = check_sprint(c, n, for_signoff=True)
    _, b = check_backlog(c)
    gaps: List[str] = []
    if b:
        covers = sorted({sc for sid in b.plan.get(n, []) if sid in b.stories for sc in b.stories[sid].covers})
        _, gaps = trace_matrix(c, only=covers)
        if gaps and not a.accept_gaps:
            rep.err("trace", "scenarios with no test referencing their ID: " + ", ".join(gaps)
                    + " (add tests, or re-run with --accept-gaps \"<reason>\" after the human agrees)")
    print(rep.render(f"sign-off sprint {n}"))
    if not rep.ok:
        return 1
    parts = ["signoff", c.id, str(n)] + (["--accept-gaps", a.accept_gaps] if a.accept_gaps else [])
    by, via = confirm_human(ws, f"sign off sprint {n} of change '{c.id}'"
                            + (f" ACCEPTING untested scenarios {', '.join(gaps)}" if gaps else ""), a.by, gate_cmdline(ws, *parts))
    s.update({"status": "signed-off", "by": by, "via": via, "at": now()})
    if gaps:
        s["accepted_gaps"] = {"scenarios": gaps, "reason": a.accept_gaps}
    c.log("signoff", f"sprint {n} by {by} (via {via})")
    c.save()
    print(f"{c.id}: sprint {n} signed off by {by} (via {via})")
    return 0


def cmd_trace(a: argparse.Namespace) -> int:
    ws = Workspace.locate(a.root)
    c = ws.change(a.id)
    md, gaps = trace_matrix(c)
    if a.out:
        out = Path(a.out)
        if not out.is_absolute():
            out = c.dir / out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(md, encoding="utf-8")
        print(f"wrote {out}")
    else:
        print(md)
    if gaps:
        print(f"{len(gaps)} scenario(s) without tests: {', '.join(gaps)}", file=sys.stderr)
    return 0 if not gaps or not a.strict else 1


def cmd_coverage(a: argparse.Namespace) -> int:
    """Scenario -> test coverage across ALL living specs (drift signal)."""
    ws = Workspace.locate(a.root)
    living = load_living(ws)
    scen = {sid: (cap, r.id, title) for cap, r in living.values() for sid, title, _ in r.scenarios}
    if a.capability:
        scen = {k: v for k, v in scen.items() if v[0] == a.capability or v[0].startswith(a.capability + "/")}
    refs = scan_refs(ws, sorted(scen))
    missing = [s for s in sorted(scen) if not refs[s]["tests"]]
    rows = ["| Capability | Scenario | Tests |", "|---|---|---|"]
    for sid in sorted(scen):
        cap, rid, title = scen[sid]
        rows.append(f"| {cap} | {sid} {title} | {'<br>'.join(refs[sid]['tests']) or '**none**'} |")
    out = (f"# Living spec coverage\n\nGenerated {now()}. {len(scen)} scenario(s), "
           f"{len(scen) - len(missing)} with tests, {len(missing)} without.\n\n" + "\n".join(rows) + "\n")
    if a.out:
        Path(a.out).write_text(out, encoding="utf-8")
        print(f"wrote {a.out}")
    else:
        print(out)
    if missing:
        print(f"{len(missing)} living scenario(s) without tests: {', '.join(missing[:20])}"
              + (" ..." if len(missing) > 20 else ""), file=sys.stderr)
    return 1 if (missing and a.strict) else 0


def cmd_archive(a: argparse.Namespace) -> int:
    ws = Workspace.locate(a.root)
    c = ws.change(a.id)
    if c.phase != "retro":
        die(f"change is in phase '{c.phase}'; archive happens after retro")
    if not c.p("retro.md").is_file() and not a.dry_run:
        die("retro.md is missing (a --dry-run works without it)")
    rep = check_specs(c)
    for dep in c.state.get("depends_on", []):
        if dep in ws.change_ids():
            rep.err("depends_on", f"change '{dep}' must be archived first")
    base = (c.state.get("accreditation") or {}).get("base", {})
    now_base = base_hashes(c)
    for rid, digest in base.items():
        if now_base.get(rid) != digest:
            rep.err("base drift", f"living [{rid}] changed since accreditation (another change archived?); "
                    f"re-check the delta against the current spec, then `amend` and re-accredit")
    if not rep.ok:
        print(rep.render("archive preconditions"))
        return 1
    log = merge_change(c, dry=a.dry_run) + promote_adrs(c, dry=a.dry_run)
    print("\n".join(log) or "no spec changes")
    if a.dry_run:
        print("dry run: nothing written")
        return 0
    c.state["phase"] = "archived"
    c.log("archive", f"{len(log)} spec operation(s)")
    c.save()
    dest = ws.archive / f"{today()}-{c.id}"
    if dest.exists():
        die(f"{dest} already exists")
    ws.archive.mkdir(parents=True, exist_ok=True)
    shutil.move(str(c.dir), str(dest))
    print(f"archived to {dest.relative_to(ws.project)}")
    return 0


def cmd_spec(a: argparse.Namespace) -> int:
    """Show living spec inventory or one requirement (cheap context loading)."""
    ws = Workspace.locate(a.root)
    living = load_living(ws)
    if a.req:
        hit = living.get(a.req)
        if not hit:
            die(f"[{a.req}] not found in living specs")
        print(f"# capability: {hit[0]}\n\n{hit[1].text}")
        return 0
    caps: Dict[str, List[Requirement]] = {}
    for cap, r in living.values():
        caps.setdefault(cap, []).append(r)
    if a.json:
        print(json.dumps({k: [{"id": r.id, "title": r.title, "scenarios": len(r.scenarios)} for r in v]
                          for k, v in sorted(caps.items())}, indent=2))
        return 0
    if not caps:
        print("no living specs yet")
    for cap, reqs in sorted(caps.items()):
        print(f"{cap}  ({len(reqs)} requirement(s))")
        for r in reqs:
            print(f"  [{r.id}] {r.title}  - {len(r.scenarios)} scenario(s)")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="specmaker.py", description=__doc__.split("\n\n")[0])
    p.add_argument("--root", help=f"workspace directory (default: nearest ./{DEFAULT_ROOT} or $SPECMAKER_ROOT)")
    p.add_argument("--version", action="version", version=VERSION)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init", help="create the workspace and the AGENTS.md pointer (idempotent)")
    s.add_argument("--no-agents-md", action="store_true",
                   help="do not create or update the specmaker block in AGENTS.md / CLAUDE.md")
    s.set_defaults(fn=cmd_init)
    s = sub.add_parser("new", help="start a change")
    s.add_argument("id")
    s.add_argument("--title")
    s.add_argument("--track", choices=TRACKS, default="full")
    s.set_defaults(fn=cmd_new)
    s = sub.add_parser("list", help="list changes")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_list)
    s = sub.add_parser("status", help="phase, artifacts, lock and next step")
    s.add_argument("id", nargs="?")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_status)
    s = sub.add_parser("check", help="lint artifacts: hld lld specs adrs design backlog sprint:N all")
    s.add_argument("id")
    s.add_argument("what", nargs="*")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_check)
    s = sub.add_parser("set", help="set skip_specs | docs_only | title | track | depends_on (comma list)")
    s.add_argument("id")
    s.add_argument("key")
    s.add_argument("value")
    s.set_defaults(fn=cmd_set)
    s = sub.add_parser("phase", help="advance to the next phase if its entry gate passes")
    s.add_argument("id")
    s.add_argument("target", choices=PHASES)
    s.set_defaults(fn=cmd_phase)
    s = sub.add_parser("accredit", help="record the HUMAN verdict and lock the design")
    s.add_argument("id")
    s.add_argument("--verdict", required=True, choices=["approved", "conditional", "rejected"])
    s.add_argument("--by", help="name of the human approver (required in chat mode; checked against the typed name in terminal mode)")
    s.add_argument("--condition", action="append", help="condition for a conditional verdict (repeatable)")
    s.set_defaults(fn=cmd_accredit)
    s = sub.add_parser("amend", help="reopen an accredited design (clears the lock)")
    s.add_argument("id")
    s.add_argument("--reason", required=True)
    s.set_defaults(fn=cmd_amend)
    s = sub.add_parser("sprint-start", help="activate sprint N")
    s.add_argument("id")
    s.add_argument("n", type=int)
    s.set_defaults(fn=cmd_sprint_start)
    s = sub.add_parser("signoff", help="record the HUMAN sign-off of sprint N")
    s.add_argument("id")
    s.add_argument("n", type=int)
    s.add_argument("--by", help="name of the human signing off (required in chat mode)")
    s.add_argument("--accept-gaps", metavar="REASON", help="allow scenarios without tests, with a recorded reason")
    s.set_defaults(fn=cmd_signoff)
    s = sub.add_parser("gates", help="run project.md Quality Gates and record evidence for sprint N")
    s.add_argument("id")
    s.add_argument("n", type=int)
    s.add_argument("--timeout", type=int, default=1800)
    s.set_defaults(fn=cmd_gates)
    s = sub.add_parser("ledger", help="append to (or print) the change's decision ledger")
    s.add_argument("id")
    s.add_argument("text", nargs="*")
    s.add_argument("--kind", choices=LEDGER_KINDS, default="decision")
    s.add_argument("--ref", help="finding, requirement or story this entry is about")
    s.set_defaults(fn=cmd_ledger)
    s = sub.add_parser("export", help="export backlog as csv or json")
    s.add_argument("id")
    s.add_argument("--format", choices=["csv", "json"], default="csv")
    s.set_defaults(fn=cmd_export)
    s = sub.add_parser("trace", help="scenario -> story -> test matrix")
    s.add_argument("id")
    s.add_argument("--out", help="write markdown here (relative to the change dir)")
    s.add_argument("--strict", action="store_true", help="exit 1 when any scenario has no test")
    s.set_defaults(fn=cmd_trace)
    s = sub.add_parser("archive", help="merge delta specs into living specs and archive the change")
    s.add_argument("id")
    s.add_argument("--dry-run", action="store_true")
    s.set_defaults(fn=cmd_archive)
    s = sub.add_parser("coverage", help="scenario -> test coverage across all living specs")
    s.add_argument("--capability", help="limit to one capability path (and its children)")
    s.add_argument("--out", help="write markdown to this path")
    s.add_argument("--strict", action="store_true", help="exit 1 when any scenario has no test")
    s.set_defaults(fn=cmd_coverage)
    s = sub.add_parser("spec", help="list living specs, or print one requirement by ID")
    s.add_argument("req", nargs="?")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_spec)

    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
