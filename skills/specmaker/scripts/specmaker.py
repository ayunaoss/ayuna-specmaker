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
import uuid
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
FIELD_RE = re.compile(r"^\s*[-*]\s+\*\*(Points|Priority|Depends|Covers|Removes|Type)\*\*\s*:\s*(.*)$", re.I)
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
        self.fence = ""      # opening fence marker while inside a fence, e.g. "```" or "~~~~"
        self.comment = False

    def skip(self, line: str) -> bool:
        """True if this line is inside a fence or comment (or opens/closes one)."""
        if self.comment:
            if "-->" in line:
                self.comment = False
            return True
        m = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line)
        if self.fence:
            # a closing fence is the same marker, at least as long, with nothing after it (CommonMark)
            if m and m.group(1)[0] == self.fence[0] and len(m.group(1)) >= len(self.fence) and not m.group(2).strip():
                self.fence = ""
            return True
        # a backtick fence's info string may not contain a backtick: ```npm test``` is inline code, not a fence
        if m and not (m.group(1)[0] == "`" and "`" in m.group(2)):
            self.fence = m.group(1)
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
        self.state = json.loads(read(d / STATE_FILE))
        self.id = self.state.get("id", d.name)  # archived folders are named YYYY-MM-DD-<id>

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
        files += self.adrs()
        for sub in ("specs", "contracts"):   # every file, not only spec.md: nothing in the design escapes the lock
            d = self.p(sub)
            if d.is_dir():
                files += sorted(f for f in d.rglob("*") if f.is_file())
        return files

    def rel(self, p: Path) -> str:
        return p.relative_to(self.dir).as_posix()

    def lock_drift(self) -> List[str]:
        acc = self.state.get("accreditation") or {}
        lock = acc.get("lock") or {}
        if not lock:
            return ["lock missing from an approved design"] if acc.get("verdict") in ("approved", "conditional") else []
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
    section = "OTHER"       # text above the first section heading belongs to no requirements section
    cur: Optional[Requirement] = None
    cur_scn: Optional[Tuple[str, str, List[str]]] = None
    lines = text.splitlines()
    sk = Skipper()
    fence_line = 0
    for i, line in enumerate(lines, 1):
        was_fenced = bool(sk.fence)
        if sk.skip(line):
            if sk.fence and not was_fenced:
                fence_line = i
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
        if cur and re.match(r"^#{3,6}\s", line):
            rep.err(f"line {i}", f"heading '{line.strip()[:60]}' inside requirement [{cur.id}] is neither "
                    f"'### Requirement: [ID] ...' nor '#### Scenario: [ID.n] ...'; it would be hidden from checks")
        if cur:
            cur.lines.append(line)
            if cur_scn:
                cur_scn[2].append(line)
    if sk.fence:
        rep.err(f"line {fence_line}", "code block is never closed; everything after it is ignored")
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
    sk = Skipper()
    prose = [ln for ln in r.lines[1:first_scn] if not sk.skip(ln)]   # code examples are not the statement
    statement = strip_comments("\n".join(prose)).strip()
    if re.fullmatch(r"The system (SHALL|MUST)\s*\.?", statement):
        statement = ""
    if not statement:
        rep.err(where, f"[{r.id}] has no requirement statement")
    elif not NORMATIVE_RE.search(statement):
        rep.err(where, f"[{r.id}] statement must use SHALL or MUST")
    elif len(statement) > 500:
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


PURPOSE_MIN = 50
PURPOSE_PLACEHOLDER_RE = re.compile(r"\b(TBD|TODO|FIXME|XXX)\b|<[^>]+>", re.I)


def unapplied_content(text: str) -> List[Tuple[int, str]]:
    """(line, where) for delta text that archive does not merge: outside requirement blocks."""
    out: List[Tuple[int, str]] = []
    sk = Skipper()
    h2, in_req = "", False
    for i, line in enumerate(text.splitlines(), 1):
        if sk.skip(line) or not strip_comments(line).strip():
            continue
        if re.match(r"^#\s", line):
            continue
        m = re.match(r"^##\s+(.+?)\s*$", line)
        if m:
            h2, in_req = m.group(1).strip().lower(), False
            continue
        if REQ_LOOSE_RE.match(line):
            in_req = True
            continue
        if in_req or h2 == "purpose":
            continue
        where = (f"under '## {h2}' before its first requirement" if DELTA_SECTION_RE.match("## " + h2)
                 else f"in section '## {h2}'" if h2 else "above the first section")
        out.append((i, where))
    return out


def check_specs(change: Change) -> Report:
    rep = Report()
    deltas = change.delta_specs()
    sdir = change.p("specs")
    if sdir.is_dir():
        for f in sorted(sdir.rglob("*")):
            if f.is_file() and (f.name != "spec.md" or f.parent == sdir):
                rep.err(change.rel(f), "not read: delta specs must be specs/<capability>/spec.md "
                        "(merge it into that file, or move it)")
    if deltas and change.state.get("skip_specs"):
        rep.err("specs/", "skip_specs is set but delta specs exist: remove them, or `set <id> skip_specs false`")
    if not deltas:
        if change.state.get("skip_specs"):
            return rep
        rep.err("specs/", "no delta specs. Add specs/<capability>/spec.md, or run "
                "`specmaker.py set <id> skip_specs true` for a change with no behaviour change")
        return rep
    if change.state.get("docs_only"):
        for e in check_removals(change).errors:
            rep.err("specs/", e.split(": ", 1)[1] + " - a docs-only change builds nothing, so it cannot retire "
                    "IDs that tests or code name: use a lite change whose sprint updates them")
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
        purpose = h2.get("purpose")
        if is_new:
            ptext = strip_comments(purpose or "").strip()
            if len(ptext) < PURPOSE_MIN:
                rep.err(where, f"new capability needs a '## Purpose' of at least {PURPOSE_MIN} characters")
            elif PURPOSE_PLACEHOLDER_RE.search(ptext):
                rep.err(where, "'## Purpose' still contains a placeholder (TBD, TODO, <...>)")
        elif purpose is not None:
            rep.err(where, f"'## Purpose' is only for a new capability: '{cap}' exists and archive keeps its living "
                    f"purpose, so this text would be lost (remove the section)")
        for line_no, wh in unapplied_content(text):
            rep.warn(where, f"line {line_no}: text {wh} is not merged into the living spec")
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
                elif r.section == "MODIFIED":
                    dropped = sorted({sid for sid, _, _ in in_living[1].scenarios} - {sid for sid, _, _ in r.scenarios})
                    if dropped:
                        rep.warn(where, f"MODIFIED [{r.id}] drops scenario(s) {', '.join(dropped)}: they leave the living "
                                 f"spec at archive, and tests naming them must go too (see `trace`)")
    return rep


def lint_living(texts: Dict[str, str]) -> Report:
    """Lint living spec texts (path -> text): structure, requirement rules, duplicate IDs within and across files."""
    rep = Report()
    seen: Dict[str, str] = {}
    for where, text in sorted(texts.items()):
        reqs, prep, h2 = parse_requirements(text, delta=False)
        for e in prep.errors:
            rep.err(where, e)
        if "requirements" not in h2:
            rep.err(where, "missing '## Requirements'")
        for r in reqs:
            lint_requirement(r, where, rep)
            if r.id in seen:
                rep.err(where, f"[{r.id}] is defined more than once (also in {seen[r.id]})")
            seen.setdefault(r.id, where)
    return rep


def living_texts(ws: "Workspace") -> Dict[str, str]:
    if not ws.specs.is_dir():
        return {}
    return {f.relative_to(ws.project).as_posix(): read(f) for f in sorted(ws.specs.rglob("spec.md"))}


def check_living(ws: "Workspace") -> Report:
    return lint_living(living_texts(ws))


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


def removed_reqs(change: Change) -> Dict[str, str]:
    """REMOVED requirement id -> capability, over all delta specs of a change."""
    out: Dict[str, str] = {}
    for f in change.delta_specs():
        for r in parse_requirements(read(f), delta=True)[0]:
            if r.section == "REMOVED":
                out[r.id] = capability_of(change, f)
    return out


def retired_scenarios(change: Change) -> Dict[str, str]:
    """Scenario IDs this change retires -> why: every scenario of a REMOVED requirement and every
    scenario a MODIFIED requirement drops. Tests and code must stop referencing them.
    Read against the living specs, so it is meaningful until the change is archived."""
    living = load_living(change.ws)
    out: Dict[str, str] = {}
    for f in change.delta_specs():
        for r in parse_requirements(read(f), delta=True)[0]:
            hit = living.get(r.id)
            if not hit:
                continue
            old = {sid for sid, _, _ in hit[1].scenarios}
            if r.section == "REMOVED":
                out.update({sid: f"[{r.id}] is removed" for sid in old})
            elif r.section == "MODIFIED":
                kept = {sid for sid, _, _ in r.scenarios}
                out.update({sid: f"dropped from [{r.id}]" for sid in old - kept})
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
    def removes(self) -> List[str]:
        return re.findall(r"\b(" + ID_RE + r")\b(?!\.\d)", self.fields.get("removes", ""))

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
    # the tree must be complete: no empty epic or feature (on any track)
    for eid, title in b.epics.items():
        has_feature = any(e == eid for _, e in b.features.values())
        has_story = any(st.epic == eid for st in b.stories.values())
        if full and not has_feature:
            rep.err("backlog.md", f"epic {eid} ({title}) has no features")
        elif not has_story:
            rep.err("backlog.md", f"epic {eid} ({title}) has no stories")
    for fid, (title, _) in b.features.items():
        if not any(st.feature == fid for st in b.stories.values()):
            rep.err("backlog.md", f"feature {fid} ({title}) has no stories")
    scen = delta_scenarios(change)
    removed = removed_reqs(change)
    removing: Dict[str, List[str]] = {}
    covered: Dict[str, List[str]] = {}
    wont_only: Dict[str, List[str]] = {}
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
        wont = s.fields.get("priority", "").lower() in ("won't", "wont")
        stype = s.fields.get("type", "story").lower()
        if not s.covers and not s.removes and stype not in ("enabler", "spike", "chore"):
            rep.err(where, "**Covers** lists no scenario IDs (mark **Type**: enabler|spike|chore if it covers none, "
                    "or list **Removes** for a story that deletes a requirement)")
        for rid in s.removes:
            if rid not in removed:
                rep.err(where, f"**Removes** [{rid}], which no delta spec lists under REMOVED")
            elif not wont:
                removing.setdefault(rid, []).append(s.id)
        for sc in s.covers:
            if sc not in scen:
                rep.err(where, f"covers unknown scenario {sc}")
            if not wont:
                covered.setdefault(sc, []).append(s.id)
            else:
                wont_only.setdefault(sc, []).append(s.id)
        for d in s.depends:
            if d not in b.stories:
                rep.err(where, f"depends on unknown story {d}")
            if d == s.id:
                rep.err(where, "depends on itself")
        if not s.tasks:
            rep.err(where, "no tasks ('- [ ] T<story>.<n> <imperative> - files: <paths>')")
        for tid, _, text, line in s.tasks:
            if not re.search(r"\bfiles?\s*:\s*[^\s-]", text, re.I):
                rep.err(f"backlog.md:{line} {tid}", "task has no 'files:' boundary")
    for sc, (rid, title) in sorted(scen.items()):
        if sc in covered:
            continue
        if sc in wont_only:
            rep.err("backlog.md", f"scenario {sc} of [{rid}] is covered only by Won't stories "
                    f"({', '.join(wont_only[sc])}): plan a story for it, or remove the scenario from the delta spec "
                    f"(a design change: `amend`)")
        else:
            rep.err("backlog.md", f"scenario {sc} ({title}) of [{rid}] is not covered by any story")
    for rid, cap in sorted(removed.items()):
        if rid not in removing:
            rep.err("backlog.md", f"REMOVED [{rid}] ({cap}) has no story that deletes its code and tests: "
                    f"add one with '**Removes**: {rid}'")
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
        out = subprocess.run(["git", "-c", "core.quotePath=false", "ls-files", "-co", "--exclude-standard", "-z"],
                             cwd=root, capture_output=True, text=True, encoding="utf-8", errors="surrogateescape",
                             check=True, timeout=60).stdout
        files = [root / ln for ln in out.split("\0") if ln]
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


def git(ws: Workspace, *args: str, strip: bool = True) -> Optional[str]:
    """Run git in the project directory with unquoted paths. Returns stdout, or None on failure."""
    try:
        r = subprocess.run(["git", "-c", "core.quotePath=false", *args], cwd=ws.project, capture_output=True,
                           text=True, encoding="utf-8", errors="surrogateescape", timeout=120)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    return r.stdout.strip() if strip else r.stdout


def git_z(ws: Workspace, *args: str) -> Optional[List[str]]:
    """Run git with -z output and return the NUL-separated fields."""
    out = git(ws, *args, strip=False)
    return None if out is None else [x for x in out.split("\0") if x]


def ws_rel(ws: Workspace) -> str:
    return ws.root.relative_to(ws.project).as_posix()


def skip_path(path: str, ws: Workspace) -> bool:
    w = ws_rel(ws)
    return path == w or path.startswith(w + "/") or any(part in SKIP_DIRS for part in path.split("/")[:-1])


def changed_files(ws: Workspace, base: str) -> Optional[List[str]]:
    """Files changed since base (committed, staged, unstaged and untracked), relative to the project directory."""
    diff = git_z(ws, "diff", "--name-only", "-z", "--relative", base)
    if diff is None:
        return None
    untracked = git_z(ws, "ls-files", "--others", "--exclude-standard", "-z") or []
    return sorted(f for f in set(diff) | set(untracked) if not skip_path(f, ws))


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
        if TEST_PATH_RE.search(rel):
            kind = "tests"
        elif rel.lower().endswith((".md", ".rst", ".txt", ".adoc")):
            continue  # documentation mentioning an ID is neither code nor a test
        else:
            kind = "code"
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
    out = head + "\n".join(rows) + "\n"
    retired = retired_scenarios(change) if only is None else {}
    if retired:
        rrefs = scan_refs(change.ws, sorted(retired))
        removers: Dict[str, List[str]] = {}
        if b:
            for s in b.stories.values():
                for rid in s.removes:
                    removers.setdefault(rid, []).append(s.id)
        rows = ["| Retired scenario | Why | Stories | Still referenced by |", "|---|---|---|---|"]
        for sid, why in sorted(retired.items()):
            left = rrefs[sid]["tests"] + rrefs[sid]["code"]
            if left:
                gaps.append(sid)
            rid = sid.rsplit(".", 1)[0]
            rows.append(f"| {sid} | {why} | {', '.join(removers.get(rid, [])) or '-'} | "
                        f"{'<br>'.join(left) or 'nothing (confirmed)'} |")
        out += "\n## Removals\n\nThese must have no tests or code left.\n\n" + "\n".join(rows) + "\n"
    return out, gaps


# --------------------------------------------------------------------------- spec merge


def split_living(text: str) -> Tuple[str, List[Requirement], str]:
    """(preamble incl. '## Requirements' and any intro text, requirement blocks, trailer after the section).

    Headings inside code fences and HTML comments are ignored."""
    lines = text.splitlines()
    sk = Skipper()
    start = end = first_req = None
    for i, ln in enumerate(lines):
        if sk.skip(ln):
            continue
        if start is None:
            if re.match(r"^##\s+Requirements\s*$", ln, re.I):
                start = i
            continue
        if first_req is None and REQ_LOOSE_RE.match(ln):
            first_req = i
        if H2_RE.match(ln):
            end = i
            break
    if start is None:
        return text.rstrip() + "\n\n## Requirements\n", [], ""
    end = len(lines) if end is None else end
    first_req = end if first_req is None or first_req > end else first_req
    pre = "\n".join(lines[:first_req]).rstrip() + "\n"
    reqs, _, _ = parse_requirements("\n".join(lines[start:end]), delta=False)
    return pre, reqs, "\n".join(lines[end:])


def render_living(pre: str, reqs: List[Requirement], trailer: str) -> str:
    out = pre.rstrip() + "\n\n" + "\n".join(r.text.rstrip() + "\n" for r in reqs)
    if trailer.strip():
        out = out.rstrip() + "\n\n" + trailer.strip() + "\n"
    return out.rstrip() + "\n"


def merge_change(change: Change, plan: Dict[Path, str]) -> List[str]:
    """Render delta specs onto living specs and verify the result in memory. Nothing is written
    here: the verified texts are added to `plan`, which the caller applies all-or-nothing."""
    log = []
    expect_present: Dict[str, Tuple[str, int]] = {}
    expect_absent: Dict[str, str] = {}
    before = load_living(change.ws)
    outputs: Dict[Path, str] = {}
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
        outputs[target] = render_living(pre, living, trailer)
    # independent verification: re-parse the rendered text, as if it had been written
    after: Dict[str, Tuple[str, Requirement]] = {
        rid: hit for rid, hit in before.items() if living_spec_path(change.ws, hit[0]) not in outputs}
    for target, text in outputs.items():
        cap = target.parent.relative_to(change.ws.specs).as_posix()
        for r in parse_requirements(text, delta=False)[0]:
            after[r.id] = (cap, r)
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
    for target, text in outputs.items():
        old = target.read_text(encoding="utf-8") if target.is_file() else ""
        old_extra = re.sub(r"(?ms)^###\s+Requirement:.*?(?=^##\s|\Z)", "", strip_comments(old))
        new_extra = re.sub(r"(?ms)^###\s+Requirement:.*?(?=^##\s|\Z)", "", strip_comments(text))
        if old and old_extra.split() != new_extra.split():
            problems.append(f"text outside requirement blocks changed in {target.relative_to(change.ws.project)}")
    # lint the result as it would be on disk: touched files fully, duplicate IDs across all files
    touched = {t.relative_to(change.ws.project).as_posix(): x for t, x in outputs.items()}
    merged = living_texts(change.ws)
    merged.update(touched)
    problems += [e for e in lint_living(merged).errors
                 if e.split(": ", 1)[0] in touched or "defined more than once" in e]
    if problems:
        die("merge verification failed; nothing was written:\n  " + "\n  ".join(problems))
    plan.update(outputs)
    added = sum(1 for k in expect_present if k not in before)
    untouched = sum(1 for k in before if k not in expect_present and k not in expect_absent)
    log.append(f"verified: {added} added, {len(expect_present) - added} modified, "
               f"{len(expect_absent)} removed, {untouched} untouched")
    return log


def promote_adrs(change: Change, plan: Dict[Path, str]) -> List[str]:
    """Plan copies of the change's ADRs into the project-wide decision log with global numbers."""
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
        plan[dest / name] = text
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


REPORT_VERDICT_RE = re.compile(r"^\s*[-*]\s*Verdict\s*:\s*(PASS-WITH-NOTES|PASS|FAIL)\b", re.M | re.I)
REPORT_BLOCKER_RE = re.compile(r"^###\s+(G\d+)\s+\[Blocker\]", re.M | re.I)
LEDGER_ENTRY_RE = re.compile(r"^- \*\*(L-\d+)\*\* `([A-Z]+)`[^\n]*?\(re: ([^)]*)\)", re.M)
LEDGER_REF_RE = re.compile(r"(?<![\w-])(?:accredit-)?(r\d+-[a-z0-9-]+?)(?:\.md)?#(G\d+)", re.I)


def check_removals(change: Change, only_reqs: Optional[set] = None) -> Report:
    """Scenarios this change retires must have no tests or code left that reference them
    (only those of `only_reqs` when given, e.g. the requirements one sprint removes or modifies)."""
    rep = Report()
    retired = {sid: why for sid, why in retired_scenarios(change).items()
               if only_reqs is None or sid.rsplit(".", 1)[0] in only_reqs}
    refs = scan_refs(change.ws, sorted(retired))
    for sid, why in sorted(retired.items()):
        left = refs[sid]["tests"] + refs[sid]["code"]
        if left:
            rep.err("removals", f"{sid} ({why}) is still referenced by {', '.join(left)}: "
                    f"delete or rewrite those tests and code")
    return rep


def verification_verdict(text: str) -> Optional[str]:
    """The binding verdict of a verifier report: its last Verdict line (a header line may come first)."""
    found = re.findall(r"^\W*Verdict\W*:\s*(PASS-WITH-NOTES|PASS|FAIL)\b", text, re.M | re.I)
    return found[-1].upper() if found else None


def report_complete(text: str) -> bool:
    """A finished goldfish report has its Verdict line and a '## Findings' heading."""
    return bool(REPORT_VERDICT_RE.search(text)) and bool(re.search(r"^##\s+Findings\s*$", text, re.M | re.I))


def ledger_refs(change: "Change") -> Dict[Tuple[str, str], List[Tuple[str, str]]]:
    """(report file name, G<n>) -> [(ledger entry, kind)], from '(re: <report>#G<n>)' references."""
    out: Dict[Tuple[str, str], List[Tuple[str, str]]] = {}
    f = change.p("ledger.md")
    if f.is_file():
        for m in LEDGER_ENTRY_RE.finditer(read(f)):
            for rm in LEDGER_REF_RE.finditer(m.group(3)):
                out.setdefault(("accredit-" + rm.group(1).lower() + ".md", rm.group(2).upper()), []).append((m.group(1), m.group(2).lower()))
    return out


def check_review_reports(change: "Change", verdict: str) -> Report:
    """Reports must be complete, and every Blocker resolved: fixed and re-reviewed (a later round
    of that lens), or settled in the ledger. A Blocker is never declined."""
    rep = Report()
    lenses = review_lenses(change)
    refs = ledger_refs(change)
    for lens, rounds in sorted(lenses.items()):
        name = f"accredit-r{max(rounds)}-{lens}.md"
        text = read(change.p("reviews") / name)
        if not report_complete(text):
            msg = (f"{name} is incomplete (no 'Verdict:' line or '## Findings'): the reviewer did not finish; "
                   f"retry once, or record the lens as not run")
            if lens in REQUIRED_LENSES[change.track]:
                rep.err("reviews/", msg)
            else:
                rep.warn("reviews/", msg)
            continue
        blockers = REPORT_BLOCKER_RE.findall(text)
        vm = REPORT_VERDICT_RE.search(text)
        if vm and vm.group(1).upper() == "FAIL" and not blockers:
            rep.err("reviews/", f"{name} says FAIL but lists no '### G<n> [Blocker] ...' finding; "
                    f"fix the report's format so each Blocker can be resolved and traced")
        elif vm and vm.group(1).upper() != "FAIL" and blockers:
            rep.err("reviews/", f"{name} lists Blocker(s) {', '.join(blockers)} but its verdict is "
                    f"{vm.group(1).upper()}; a report with any Blocker is FAIL")
        for g in blockers:
            # Only the lens's latest report counts: a later round means the fix was re-reviewed.
            # The ledger is append-only, so the latest settling entry is the one that stands.
            entries = refs.get((name, g.upper()), [])
            stance = [(lid, k) for lid, k in entries if k in FINDING_KINDS]
            last = stance[-1] if stance else None
            stray = [lid for lid, k in entries if k not in FINDING_KINDS]
            hint = f"; {', '.join(stray)} reference it but are not finding outcomes" if stray else ""
            if last and last[1] == "declined":
                rep.err("ledger.md", f"{last[0]} declines Blocker {name}#{g}; a Blocker is never declined: fix it and "
                        f"re-review, contest or escalate it (`--kind contested|escalated`), or make it a condition" + hint)
            elif not last or (last[1] == "condition" and verdict != "conditional"):
                rep.err("reviews/", f"Blocker {name}#{g} is unresolved: fix it and re-review the lens "
                        f"(round {max(rounds) + 1}), contest or escalate it (`ledger --kind contested|escalated "
                        f"--ref {name}#{g}`), or make it a condition of a conditional verdict (`--kind condition`)"
                        + hint)
    return rep


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
    open_reqs = [f"{cid} is still '{r['status']}'" for cid, r in sorted(change.state.get("requests", {}).items())
                 if r.get("status") in ("parked", "amend", "applying")]
    if target == "retro" and open_reqs:
        for msg in open_reqs:
            rep.err("requests", msg + "; decide or apply it before retro")
    if docs_jump:
        rep.extend(check_approvals(change))
        acc = change.state.get("accreditation") or {}
        if acc.get("verdict") not in ("approved", "conditional"):
            rep.err("accreditation", "design is not accredited")
        if change.lock_drift():
            rep.err("lock", "design changed after accreditation: " + ", ".join(change.lock_drift()))
        return rep
    if target in ("scrum", "sprint", "retro"):
        rep.extend(check_approvals(change))
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
        problem = plan_approval_problem(change)
        if problem and brep.ok:
            rep.err("plan", problem.replace("<id>", change.id))
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
                    rep.err("sprints", f"sprint {n} is not signed off"
                            + (f" (it is {sprints[str(n)]['status']})" if str(n) in sprints else ""))
        rep.extend(check_removals(change))

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
        if plan_required(change) and plan_approval_problem(change):
            return ("Build backlog.md with sprint plan (skill: specmaker-scrum); a person approves it with "
                    "`approve-plan <id>`; then `phase <id> sprint`.")
        return "Build backlog.md with sprint plan (skill: specmaker-scrum), then `phase <id> sprint`."
    reqs = change.state.get("requests", {})
    blockers = [k for k, r in reqs.items() if r.get("status") == "parked" and r.get("blocker")]
    to_apply = [k for k, r in reqs.items() if r.get("status") == "amend"]
    if blockers:
        return f"Triage blocker request(s) {', '.join(sorted(blockers))} now: `impact <id>`, then `cr decide` (skill: specmaker)."
    if to_apply:
        return f"Apply {', '.join(sorted(to_apply))}: optional `rewind`, then `amend <id> --cr {','.join(sorted(to_apply))} --to ideate|propose`."
    if ph == "sprint":
        sprints = change.state.get("sprints", {})
        active = [n for n, s in sprints.items() if s.get("status") == "active"]
        if active:
            return f"Continue sprint {active[0]} (skill: specmaker-sprint); finish with `signoff <id> {active[0]}`."
        parked = sorted(k for k, r in reqs.items() if r.get("status") == "parked")
        if parked:
            return f"Sprint boundary: triage parked requests {', '.join(parked)} together (`cr list`, `cr decide`) before starting the next sprint."
        b = parse_backlog(read(change.p("backlog.md")))[0] if change.p("backlog.md").is_file() else None
        todo = [n for n in sorted(b.plan) if sprints.get(str(n), {}).get("status") != "signed-off"] if b else []
        if todo:
            st = sprints.get(str(todo[0]), {}).get("status")
            return f"Start sprint {todo[0]}{f' (it was {st})' if st else ''}: `sprint-start <id> {todo[0]}` (skill: specmaker-sprint)."
        return "All sprints signed off: `phase <id> retro`."
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
- If you were started as a fresh-context reviewer ("goldfish") with a list of
  files to review, ignore this block and follow only your reviewer prompt.
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
    if project_gate_mode(ws) == "signed":
        if openssh_version() is None or (openssh_version() or (0, 0)) < MIN_OPENSSH:
            print("WARNING: human gates are 'signed' and need OpenSSH 8.1+ (ssh-keygen -Y); install openssh-client")
        if signers_file() is None:
            print("next: each approver registers a key once:  approvers add --principal <you@example.com> "
                  "--key ~/.ssh/id_ed25519_sk.pub")
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
        "human_gates": project_gate_mode(ws),
        "change_uid": uuid.uuid4().hex,
        "specmaker": VERSION,
    }
    (d / STATE_FILE).write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    ch = Change(ws, d)
    ch.log("created", f"track={a.track}")
    ch.save()
    print(f"created {d.relative_to(ws.project)}/ (track={a.track}, phase={ch.phase})")
    return 0


def covered_req_digest(c: "Change", reqs: List[str], hashes: Optional[Dict[str, str]] = None) -> str:
    """Digest of the approved text of the requirements a sprint covers."""
    if hashes is None:
        hashes = (c.state.get("accreditation") or {}).get("req_hashes") or {}
    return digest({rid: hashes.get(rid) for rid in reqs})


def decision_records(c: "Change") -> List[Tuple[str, str, dict, dict]]:
    """(label, action, record, facts) for every human decision on a change, current and historical.

    `facts` holds what the signed payload must match exactly. Fields under `_` are checked separately."""
    out: List[Tuple[str, str, dict, dict]] = []
    st = c.state

    def acc_facts(acc: dict) -> dict:
        return {"verdict": acc.get("verdict"), "conditions": acc.get("conditions") or [],
                "lock_digest": digest(acc["lock"]) if acc.get("lock") else None, "round": acc.get("round"),
                "head": acc.get("head")}
    acc = st.get("accreditation")
    if acc and acc.get("verdict"):
        out.append(("accreditation", "accredit", acc, {**acc_facts(acc), "_current": True}))
    for i, old in enumerate(st.get("superseded_accreditations", [])):
        if old.get("verdict"):
            out.append((f"superseded accreditation #{i + 1}", "accredit", old, acc_facts(old)))
    for n, s in sorted(st.get("sprints", {}).items(), key=lambda kv: int(kv[0])):
        entries = [(f"sprint {n} sign-off", s, True)] + \
                  [(f"sprint {n} sign-off (history #{k + 1})", h, False) for k, h in enumerate(s.get("history", []))]
        for label, rec, current in entries:
            if rec.get("status") != "signed-off" and not (rec.get("context") or {}).get("approval"):
                continue
            if current and rec.get("status") != "signed-off":
                out.append((label + " (stale)", "signoff", rec, {"_stale": True}))
                continue
            out.append((label, "signoff", rec, {"sprint": int(n), "run": rec.get("run"), "base_sha": rec.get("base_sha"),
                                                "_current": current, "_n": int(n)}))
    for cid, r in sorted(st.get("requests", {}).items()):
        d = r.get("decision")
        if d:
            out.append((f"{cid} decision", "cr-decide", d, {"outcome": d.get("outcome"), "reason": d.get("reason"),
                                                         "class": d.get("class"), "pre_lock": d.get("pre_lock"),
                                                         "_cid": cid}))
    for i, rw in enumerate(st.get("rewinds", [])):
        out.append((f"rewind #{i + 1} to {rw.get('to')}", "rewind", rw,
                    {"to": rw.get("to"), "sprint": rw.get("sprint"), "base": rw.get("base")}))
    for i, am in enumerate(st.get("amendments", [])):
        gated = am.get("wording_only") or am.get("over_budget")
        if am.get("approved") or gated:
            out.append((f"amendment #{i + 1} approval", "amend", am.get("approved") or {},
                        {"index": i, "reason": am.get("reason"), "crs": am.get("crs") or [],
                         "wording_only": bool(am.get("wording_only")), "over_budget": am.get("over_budget"),
                         "req_digest": digest(am.get("req_hashes_before") or {}), "_required": True}))
    for i, pa in enumerate(st.get("plan_approvals", [])):
        out.append((f"plan approval #{i + 1}", "plan", pa, {"backlog_digest": pa.get("backlog_digest"),
                                                            "sprints": pa.get("sprints")}))
    for i, ap in enumerate(st.get("accepted_prior", [])):
        out.append((f"accepted prior changes #{i + 1}", "accept-prior", ap,
                    {"sprint": ap.get("sprint"), "files": ap.get("files"), "reason": ap.get("reason"),
                     "checkpoint": ap.get("checkpoint")}))
    for i, g in enumerate(st.get("gate_changes", [])):
        out.append((f"human_gates change #{i + 1}", "set-human-gates", g, {"from": g.get("from"), "value": g.get("value")}))
    return out


def verify_chain(c: "Change", signers: Optional[Path]) -> Tuple[Report, Dict[int, dict]]:
    """Verify approvals/NNN-*.json as one chain: gap-free, linked by hash, bound to this change and repository,
    each signed by the principal named inside it."""
    rep = Report()
    out: Dict[int, dict] = {}
    files, stray = statement_files(c)
    for f in stray:
        rep.err("approvals", f"unexpected file {c.rel(f)} in approvals/")
    if files and signers is None:
        rep.err("approvals", "cannot verify signed decisions: no allowed signers file (see `approvers check`)")
        return rep, out
    prev = None
    repo = repo_identity(c.ws)
    for k, (seq, f) in enumerate(files, 1):
        where = c.rel(f)
        if seq != k:
            rep.err("approvals", f"{where}: statement numbers must run 001, 002, ... without gaps (expected {k:03d})")
        try:
            body = json.loads(read(f))
            if not isinstance(body, dict):
                raise ValueError("not an object")
        except (ValueError, OSError) as e:
            rep.err("approvals", f"{where}: unreadable statement ({e})")
            prev = sha256(f)
            continue
        problems = []
        if body.get("seq") != seq:
            problems.append("sequence number")
        if body.get("prev") != prev:
            problems.append("link to the previous statement")
        if body.get("change") != c.id or body.get("change_uid") != c.state.get("change_uid"):
            problems.append("change identity")
        if repo and body.get("repo") and body.get("repo") != repo:
            problems.append("repository identity")
        ok, msg = verify_signature(f, str(body.get("by", "")), signers) if signers else (False, "no signers file")
        if not ok:
            problems.append(f"signature ({msg})")
        m = re.search(r"with (\S+) key", msg or "")
        for p in problems:
            rep.err("approvals", f"{where}: {p} does not verify")
        out[seq] = {"body": body, "file": f, "ok": not problems, "keytype": (m.group(1) if m else ""), "sha": sha256(f)}
        prev = sha256(f)
    return rep, out


def check_approvals(c: "Change", require_signed: bool = False, require_hardware: bool = False) -> Report:
    """Verify recorded human decisions against the signed statement chain.

    Signed records must match their statement exactly; every statement must belong to a record; decisions must
    still mean what was signed (design lock, sprint evidence, request status). Unsigned decisions are errors
    when signatures are required: by the caller (CI: `verify --require-signed`) or by the change's own mode."""
    must_sign = require_signed or c.state.get("human_gates") == "signed"
    signers = signers_file()
    rep, chain = verify_chain(c, signers)
    used: Dict[int, str] = {}
    sig_of: Dict[int, int] = {}          # id(record) -> statement seq, for later semantic checks
    for label, action, rec, facts in decision_records(c):
        if facts.get("_stale"):
            rep.err("approvals", f"{label}: a sprint that is not signed off still carries a signature")
            continue
        appr = (rec.get("context") or {}).get("approval") if isinstance(rec, dict) else None
        if not appr:
            if must_sign:
                rep.err("approvals", f"{label}{' by ' + str(rec.get('by')) if rec.get('by') else ''} is not signed"
                        + (f" (recorded via {rec.get('via')})" if rec.get("via") else ""))
            elif facts.get("_required") and not rec.get("by"):
                rep.err("approvals", f"{label}: this amendment needs a recorded human approval, and has none")
            continue
        if not isinstance(appr, dict):
            rep.err("approvals", f"{label}: malformed approval reference")
            continue
        m = re.fullmatch(r"approvals/(\d{3,})-([a-z][a-z-]*)\.json", str(appr.get("file", "")))
        if not m or m.group(2) != action:
            rep.err("approvals", f"{label}: approval must reference approvals/NNN-{action}.json in this change")
            continue
        seq = int(m.group(1))
        entry = chain.get(seq)
        if entry is None or entry["file"].name != Path(appr["file"]).name:
            rep.err("approvals", f"{label}: statement {appr['file']} is not in the verified chain")
            continue
        used[seq] = label
        sig_of[id(rec)] = seq
        body = entry["body"]
        if not entry["ok"]:
            rep.err("approvals", f"{label}: its statement does not verify")
            continue
        if not (body.get("by") == rec.get("by") == appr.get("principal")):
            rep.err("approvals", f"{label}: recorded approver '{rec.get('by')}' differs from the signer '{body.get('by')}'")
        if appr.get("sha256") and appr["sha256"] != entry["sha"]:
            rep.err("approvals", f"{label}: statement content changed after it was recorded")
        if body.get("action") != action:
            rep.err("approvals", f"{label}: statement is a '{body.get('action')}', not a '{action}'")
        pay = body.get("payload") or {}
        bad = [k for k, v in facts.items() if not k.startswith("_") and pay.get(k) != v]
        if action == "cr-decide" and facts.get("_cid") not in (pay.get("requests") or []):
            bad.append("requests")
        if bad:
            rep.err("approvals", f"{label}: the record differs from what was signed ({', '.join(bad)}); "
                    f"change.json may have been edited")
            continue
        if require_hardware and not entry["keytype"].upper().endswith("-SK"):
            rep.err("approvals", f"{label}: signed with a {entry['keytype'] or 'unknown'} key, not a hardware-backed (sk) key")
        if action == "signoff" and facts.get("_current"):
            rep.extend(check_signoff_still_valid(c, label, facts["_n"], pay, seq, chain))
    for seq in sorted(set(chain) - set(used)):
        rep.err("approvals", f"{c.rel(chain[seq]['file'])} is not referenced by any decision record "
                f"(was a record deleted from change.json?)")
    rep.extend(check_request_status(c))
    return rep


def check_signoff_still_valid(c: "Change", label: str, n: int, pay: dict, seq: int, chain: Dict[int, dict]) -> Report:
    """A current sign-off must still describe the sprint: same evidence, same approved requirements, not rewound."""
    rep = Report()
    gf, vf = gates_file(c, n), c.verification_file(n)
    if pay.get("gates_digest") != (sha256(gf) if gf.is_file() else None):
        rep.err("approvals", f"{label}: the gate record changed after sign-off")
    if pay.get("verification") != (vf.name if vf.is_file() else None) or \
            pay.get("verification_digest") != (sha256(vf) if vf.is_file() else None):
        rep.err("approvals", f"{label}: the verifier report changed after sign-off")
    reqs = pay.get("covered_reqs") or []
    if pay.get("req_digest") != covered_req_digest(c, reqs):
        # allowed only when every change since then came through signed wording-only amendments
        trailing = []
        for am in reversed(c.state.get("amendments", [])):
            if not am.get("wording_only"):
                break
            trailing.append(am)
        if not any(pay.get("req_digest") == covered_req_digest(c, reqs, am.get("req_hashes_before") or {})
                   for am in trailing):
            rep.err("approvals", f"{label}: requirements it covered ({', '.join(reqs)}) changed after sign-off; "
                    f"the sprint must be re-run and signed off again")
    for later in range(seq + 1, max(chain or [0]) + 1):
        b = (chain.get(later) or {}).get("body") or {}
        if b.get("action") == "rewind":
            target = (b.get("payload") or {}).get("sprint")
            if target is not None and target <= n:
                rep.err("approvals", f"{label}: sprint {target} was rewound after this sign-off "
                        f"({c.rel(chain[later]['file'])})")
    return rep


def check_request_status(c: "Change") -> Report:
    """A request's status must follow from its recorded decision."""
    rep = Report()
    st = c.state
    acc = st.get("accreditation") or {}
    amends = st.get("amendments", [])
    for cid, r in sorted(st.get("requests", {}).items()):
        status, d = r.get("status"), r.get("decision")
        if status == "parked":
            if d:
                rep.err("requests", f"{cid} is parked but has a decision")
            continue
        if not d:
            rep.err("requests", f"{cid} is '{status}' without a recorded decision")
            continue
        outcome = d.get("outcome")
        if status in ("rejected", "deferred", "backlog", "amend"):
            ok = CR_OUTCOME_STATUS.get(outcome) == status
        elif status == "applying":
            ok = outcome == "amend" and any(cid in (am.get("crs") or []) for am in amends)
        elif status == "applied":
            idx = [i for i, am in enumerate(amends) if cid in (am.get("crs") or [])]
            ok = outcome == "amend" and (bool(d.get("pre_lock")) or
                                         (bool(idx) and acc.get("lock") and (acc.get("round") or 0) > idx[-1]))
        else:
            ok = False
        if not ok:
            rep.err("requests", f"{cid} is '{status}', which does not follow from its decision '{outcome}'")
    return rep


def flagged_decisions(c: "Change") -> List[str]:
    """Human decisions recorded 'via terminal' from inside an AI agent's process tree."""
    out = []
    def chk(label: str, rec: Optional[dict]) -> None:
        ctx = (rec or {}).get("context") or {}
        if ctx.get("suspect"):
            out.append(f"{label} by {rec.get('by')} was recorded from inside an agent process "
                       f"({', '.join(ctx.get('agent_processes', []) + ctx.get('agent_env', []))}); confirm it was a person")
    chk("accreditation", c.state.get("accreditation"))
    for n, s in sorted(c.state.get("sprints", {}).items()):
        if s.get("status") == "signed-off":
            chk(f"sprint {n} sign-off", s)
    for cid, r in sorted(c.state.get("requests", {}).items()):
        chk(f"{cid} decision", r.get("decision"))
    for rw in c.state.get("rewinds", []):
        chk(f"rewind to {rw.get('to')}", rw)
    return out


def cmd_approvers(a: argparse.Namespace) -> int:
    v = openssh_version()
    if a.approvers_action == "add":
        require_openssh()
        pub = Path(a.key).expanduser()
        if not pub.is_file():
            die(f"{pub} does not exist")
        parts = read(pub).split()
        if not pub.name.endswith(".pub") or len(parts) < 2 or not parts[0].startswith(("ssh-", "sk-", "ecdsa-")):
            die("--key must be a public key file (*.pub), never the private key")
        if not re.fullmatch(r"[^\s,\"]+", a.principal):
            die("--principal must be a single token without spaces or commas, e.g. alex@example.com")
        target = Path(a.file).expanduser() if a.file else (signers_file() or signers_candidates()[-1])
        line = f'{a.principal} namespaces="{SIG_NAMESPACE}" {parts[0]} {parts[1]}'
        existing = read(target) if target.is_file() else ""
        if line in existing:
            print(f"already present in {target}")
            return 0
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("a", encoding="utf-8") as fh:
                fh.write(("" if not existing or existing.endswith("\n") else "\n") + line + "\n")
        except PermissionError:
            die(f"{target} is not writable by you (good: it is protected). Add the line as an administrator:\n\n"
                f"    echo '{line}' | sudo tee -a {target}")
        print(f"added {a.principal} ({parts[0]}) to {target}")
        if writable_by_me(target):
            print("This file is writable by your user, so an agent running as you could add its own key. Protect it:\n"
                  f"    sudo install -d -m 755 /etc/specmaker && sudo install -m 644 {target} /etc/specmaker/allowed_signers\n"
                  "and keep the authoritative copy in CI (verify --require-signed).")
        return 0
    sf = Path(a.file).expanduser() if a.file else signers_file()
    print(f"OpenSSH: {'.'.join(map(str, v)) if v else 'not found'} (need {MIN_OPENSSH[0]}.{MIN_OPENSSH[1]}+)")
    print("search order: " + ", ".join(str(p) for p in signers_candidates()))
    if sf is None or not sf.is_file():
        print("allowed signers: none found")
        return 1 if a.approvers_action == "check" else 0
    w = writable_by_me(sf)
    print(f"allowed signers: {sf}  [{'USER-WRITABLE (' + ', '.join(w[:2]) + ')' if w else 'PROTECTED'}]")
    for principal, ktype, _ in parse_signers(sf):
        print(f"  {principal:32s} {ktype:28s} {'hardware-backed' if ktype.startswith('sk-') else 'software key'}")
    if a.approvers_action == "check" and w:
        print("protect it: sudo install -d -m 755 /etc/specmaker && "
              f"sudo install -m 644 {sf} /etc/specmaker/allowed_signers  (then remove the user copy)")
    return 0


def cmd_verify(a: argparse.Namespace) -> int:
    """Verify signed human decisions of active and archived changes (for CI). Exit 1 on any problem."""
    if a.allowed_signers:
        os.environ["SPECMAKER_ALLOWED_SIGNERS"] = a.allowed_signers
    require_openssh()
    ws = Workspace.locate(a.root)
    changes = [ws.change(cid) for cid in ws.change_ids()]
    if ws.archive.is_dir():
        changes += [Change(ws, d) for d in sorted(ws.archive.iterdir()) if (d / STATE_FILE).is_file()]
    if a.id:
        changes = [c for c in changes if c.id == a.id or c.dir.name == a.id]
        if not changes:
            die(f"no active or archived change '{a.id}'", code=1)
    failed = False
    if a.base:
        rep = Report()
        fields = git_z(ws, "diff", "--name-status", "--no-renames", "-z", "--relative", a.base, "--", ws_rel(ws))
        if fields is None:
            rep.err("base", f"cannot diff against '{a.base}'")
        else:
            for k in range(0, len(fields) - 1, 2):
                st, path = fields[k], fields[k + 1]
                if "/approvals/" in path and st[0] in "DM":
                    rep.err("approvals", f"{path} was {'deleted' if st[0] == 'D' else 'modified'} since {a.base}; "
                            f"signed statements are append-only")
        print(rep.render(f"append-only approvals since {a.base}"))
        failed |= not rep.ok
    for c in changes:
        rep = check_approvals(c, require_signed=a.require_signed, require_hardware=a.require_hardware)
        for d in c.lock_drift():
            rep.err("lock", f"design changed after accreditation: {d}")
        where = "archived " if c.dir.parent == ws.archive else ""
        print(rep.render(f"{where}{c.id}: {len(decision_records(c))} human decision(s)"))
        failed |= not rep.ok
    return 1 if failed else 0


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
            "human_gates": human_gate_mode(ws, c),
            "flagged_decisions": flagged_decisions(c),
            "approval_problems": check_approvals(c).errors,
            "requests": {k: {"status": r.get("status"), "blocker": r.get("blocker"), "title": r.get("title")}
                         for k, r in sorted(c.state.get("requests", {}).items())},
            "amendments": len(c.state.get("amendments", [])),
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
            print(f"  sprint {n}: {s.get('status')}" + (f" by {s.get('by')}" if s.get("by") and s.get("status") == "signed-off" else ""))
        if info["requests"]:
            counts: Dict[str, int] = {}
            for r in info["requests"].values():
                counts[r["status"]] = counts.get(r["status"], 0) + 1
            blk = sum(1 for r in info["requests"].values() if r["blocker"] and r["status"] == "parked")
            print("  requests: " + ", ".join(f"{v} {k}" for k, v in sorted(counts.items()))
                  + (f" ({blk} blocker)" if blk else "") + f"; amendments: {info['amendments']}")
        for line in info["flagged_decisions"]:
            print(f"  WARNING: {line}")
        for line in info["approval_problems"]:
            print(f"  APPROVAL PROBLEM: {line}")
        if info["human_gates"] == "signed":
            sf = signers_file()
            if sf is None:
                print("  WARNING: human gates are 'signed' but no allowed signers file exists (`approvers add`)")
            elif writable_by_me(sf) and not os.environ.get("SPECMAKER_ALLOWED_SIGNERS"):
                print(f"  note: {sf} is writable by this user, so a local agent could add a key; "
                      f"protect it (`approvers check`) and verify in CI")
        act = active_sprint(c)
        if act and freeze_on(ws):
            print(f"  freeze: sprint {act} active; new requests are parked until the boundary")
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
            if not w.split(":", 1)[1].isdigit():
                die(f"'{w}': use sprint:<number>, e.g. sprint:2")
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
    elif a.key == "human_gates":
        if a.value not in GATE_MODES:
            die("human_gates must be signed, terminal or chat")
        cur = human_gate_mode(ws, c)
        if GATE_MODES.index(a.value) < GATE_MODES.index(cur):
            by, via, ctx = confirm_human(ws, f"LOOSEN human gates of change '{c.id}' from {cur} to {a.value}", a.by,
                                         gate_cmdline(ws, "set", c.id, "human_gates", a.value), c,
                                         {"action": "set-human-gates", "from": cur, "value": a.value})
            append_ledger(c, "decision", f"human gates loosened from {cur} to {a.value} by {by} (via {via})")
            c.state.setdefault("gate_changes", []).append({"from": cur, "value": a.value, "by": by, "via": via,
                                                           "at": now(), "context": ctx})
        c.state["human_gates"] = a.value
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
        die("settable keys: skip_specs, docs_only, title, track, depends_on, human_gates")
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


def project_setting(ws: Workspace, label: str) -> Optional[str]:
    """Value of a '- <label>: value' line in project.md (comments ignored), or None."""
    pm = ws.root / "project.md"
    if not pm.is_file():
        return None
    m = re.search(r"^\s*[-*]\s*" + re.escape(label) + r"\s*:\s*\**([^\n*]+?)\**\s*$",
                  strip_comments(read(pm)), re.M | re.I)
    return m.group(1).strip() if m and m.group(1).strip() else None


def append_ledger(c: "Change", kind: str, text: str, ref: Optional[str] = None) -> str:
    f = c.p("ledger.md")
    if not f.is_file():
        f.write_text(f"# Ledger: {c.id}\n\nAppend-only. Written by `specmaker.py ledger`. Do not edit entries; add a new one to supersede.\n\n", encoding="utf-8")
    n = len(re.findall(r"^- \*\*L-\d+\*\*", read(f), re.M)) + 1
    with f.open("a", encoding="utf-8") as fh:
        fh.write(f"- **L-{n:03d}** `{kind.upper()}` {today()} [{c.phase}]" + (f" (re: {ref})" if ref else "") + f": {text}\n")
    return f"L-{n:03d}"


def delta_req_hashes(c: "Change") -> Dict[str, str]:
    out = {}
    for f in c.delta_specs():
        reqs, _, _ = parse_requirements(read(f), delta=True)
        for r in reqs:
            out[r.id] = hashlib.sha256((r.section + "\n" + r.text).encode()).hexdigest()
    return out


GATE_MODES = ["chat", "terminal", "signed"]  # weakest -> strongest


def project_gate_mode(ws: Workspace) -> str:
    """Mode from project.md. Fails closed: missing or unreadable -> 'signed'."""
    pm = ws.root / "project.md"
    if not pm.is_file():
        return "signed"
    lines = [ln for ln in strip_comments(read(pm)).splitlines() if re.search(r"human\W*gates", ln, re.I)]
    for ln in lines:
        m = re.match(r"^\s*[-*]\s*[*_`]*\s*Human gates\s*[*_`]*\s*:\s*[*_`]*\s*(signed|terminal|chat)\s*[*_`]*\s*$",
                     ln, re.I)
        if m:
            return m.group(1).lower()
    return "signed"


def human_gate_mode(ws: Workspace, change: Optional["Change"] = None) -> str:
    """Effective mode: the stricter of project.md and the mode recorded on the change when it was created.

    Loosening a change (signed -> terminal -> chat) is itself a human gate (`set <id> human_gates ...`)."""
    mode = project_gate_mode(ws)
    snap = change.state.get("human_gates") if change is not None else None
    if snap in GATE_MODES and GATE_MODES.index(snap) > GATE_MODES.index(mode):
        return snap
    return mode


# --------------------------------------------------------------------------- signed approvals

SIG_NAMESPACE = "specmaker"
MIN_OPENSSH = (8, 1)


def openssh_version() -> Optional[Tuple[int, int]]:
    try:
        r = subprocess.run(["ssh", "-V"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    m = re.search(r"OpenSSH_(\d+)\.(\d+)", r.stderr + r.stdout)
    return (int(m.group(1)), int(m.group(2))) if m else None


def require_openssh() -> None:
    v = openssh_version()
    if v is None or shutil.which("ssh-keygen") is None:
        die("OpenSSH (ssh-keygen) is required for signed approvals: install openssh-client (Linux/WSL2); macOS ships it")
    if v < MIN_OPENSSH:
        die(f"OpenSSH {v[0]}.{v[1]} is too old: signed approvals need {MIN_OPENSSH[0]}.{MIN_OPENSSH[1]}+ (ssh-keygen -Y)")


def signers_candidates() -> List[Path]:
    env = os.environ.get("SPECMAKER_ALLOWED_SIGNERS")
    if env:
        return [Path(env).expanduser()]
    xdg = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return [Path("/etc/specmaker/allowed_signers"), xdg / "specmaker" / "allowed_signers"]


def signers_file() -> Optional[Path]:
    return next((p for p in signers_candidates() if p.is_file()), None)


def writable_by_me(path: Path) -> List[str]:
    """Paths (the file and its parent folders) the current user could modify."""
    out = []
    for p in [path, *path.parents]:
        if p.exists() and os.access(p, os.W_OK):
            out.append(str(p))
        if p == Path(p.anchor):
            break
    return out


def parse_signers(path: Path) -> List[Tuple[str, str, str]]:
    """(principal, key type, base64 key) for entries valid in the specmaker namespace."""
    out = []
    for ln in read(path).splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#"):
            continue
        m = re.match(r'^(\S+)\s+(?:(\S*namespaces="([^"]*)"\S*)\s+)?(\S+)\s+(\S+)', ln)
        if not m:
            continue
        spaces = m.group(3)
        if spaces is not None and SIG_NAMESPACE not in [x.strip() for x in spaces.split(",")]:
            continue
        for principal in m.group(1).split(","):
            out.append((principal.strip('"'), m.group(4), m.group(5)))
    return out


def signing_key() -> Optional[Path]:
    env = os.environ.get("SPECMAKER_SIGNING_KEY")
    if env:
        return Path(env).expanduser()
    try:
        gk = subprocess.run(["git", "config", "--get", "user.signingkey"], capture_output=True, text=True,
                            timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        gk = ""
    if gk and not gk.startswith("key::"):
        k = Path(gk).expanduser()
        priv = k.with_suffix("") if k.suffix == ".pub" else k
        if priv.is_file():
            return priv
    for name in ("id_ed25519_sk", "id_ecdsa_sk", "id_ed25519", "id_ecdsa", "id_rsa"):
        k = Path.home() / ".ssh" / name
        if k.is_file():
            return k
    return None


def canonical(obj: dict) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(obj) -> str:
    return hashlib.sha256(canonical(obj if isinstance(obj, dict) else {"v": obj}).encode()).hexdigest()


STMT_NAME_RE = re.compile(r"^(\d{3,})-([a-z][a-z-]*)\.json$")


def repo_identity(ws: Workspace) -> Optional[str]:
    """The repository's root commit(s): binds statements to this repository."""
    roots = git(ws, "rev-list", "--max-parents=0", "HEAD")
    return sorted(roots.split())[0] if roots else None


def statement_files(c: "Change") -> Tuple[List[Tuple[int, Path]], List[Path]]:
    """(sorted (seq, statement) pairs, unexpected files) in the change's approvals/ folder."""
    d = c.p("approvals")
    good, stray = [], []
    if d.is_dir():
        for f in sorted(d.iterdir()):
            if f.name.endswith(".json.sig") and (d / f.name[:-4]).is_file():
                continue
            m = STMT_NAME_RE.match(f.name)
            if m and f.is_file():
                good.append((int(m.group(1)), f))
            else:
                stray.append(f)
    return sorted(good), stray


def verify_signature(statement: Path, principal: str, signers: Path) -> Tuple[bool, str]:
    sig = Path(str(statement) + ".sig")
    if not statement.is_file() or not sig.is_file():
        return False, "statement or signature file missing"
    try:
        with statement.open("rb") as fh:
            r = subprocess.run(["ssh-keygen", "-Y", "verify", "-f", str(signers), "-I", principal, "-n", SIG_NAMESPACE,
                                "-s", str(sig)], stdin=fh, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as e:
        return False, f"ssh-keygen failed: {e}"
    msg = (r.stdout + r.stderr).strip().splitlines()
    return r.returncode == 0, (msg[0] if msg else f"exit {r.returncode}")


def sign_approval(ws: Workspace, change: Optional["Change"], what: str, by: Optional[str], payload: dict,
                  cmdline: str) -> Tuple[str, str, dict]:
    require_openssh()
    signers = signers_file()
    if signers is None:
        die("human gates are 'signed' but no allowed signers file exists. A person adds their key first:\n\n"
            "    python3 " + str(Path(__file__).resolve()) + " approvers add --principal <you@example.com> "
            "--key ~/.ssh/id_ed25519_sk.pub\n\nthen protects it (see `approvers check`).", code=3)
    if not by or not by.strip():
        die("in signed mode --by must give your signer identity (the principal in the allowed signers file), "
            "for example --by alex@example.com. A person runs this command:\n\n    " + cmdline + " --by <you@example.com>",
            code=3)
    principal = by.strip()
    known = {p for p, _, _ in parse_signers(signers)}
    if principal not in known:
        die(f"'{principal}' is not an approver in {signers} (known: {', '.join(sorted(known)) or 'none'})", code=3)
    key = signing_key()
    if key is None:
        die("no SSH signing key found: set SPECMAKER_SIGNING_KEY=<path to private key> or git config user.signingkey",
            code=3)
    if change is None:
        die("internal: signed approvals need a change")
    if not change.state.get("change_uid"):
        change.state["change_uid"] = uuid.uuid4().hex
    adir = change.p("approvals")
    adir.mkdir(parents=True, exist_ok=True)
    files, _ = statement_files(change)
    seq = (files[-1][0] if files else 0) + 1
    kind = payload.get("action", "decision")
    stmt = adir / f"{seq:03d}-{kind}.json"
    body = {"specmaker": VERSION, "namespace": SIG_NAMESPACE, "change": change.id,
            "change_uid": change.state["change_uid"], "repo": repo_identity(ws), "seq": seq,
            "prev": sha256(files[-1][1]) if files else None, "action": kind,
            "payload": payload, "by": principal, "at": now(), "what": what}
    try:
        fd = os.open(stmt, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError:
        die(f"{change.rel(stmt)} already exists; nothing recorded", code=3)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(canonical(body) + "\n")
    print(f"\nHUMAN GATE (signed): {what}\nSigning {change.rel(stmt)} as {principal} with {key} "
          f"(touch your security key if it blinks)...", flush=True)
    try:
        r = subprocess.run(["ssh-keygen", "-Y", "sign", "-f", str(key), "-n", SIG_NAMESPACE, str(stmt)], timeout=300)
    except subprocess.TimeoutExpired:
        r = None
    if r is None or r.returncode != 0 or not Path(str(stmt) + ".sig").is_file():
        stmt.unlink(missing_ok=True)
        Path(str(stmt) + ".sig").unlink(missing_ok=True)
        die("signing failed or was cancelled; nothing recorded", code=3)
    ok, msg = verify_signature(stmt, principal, signers)
    if not ok:
        stmt.unlink(missing_ok=True)
        Path(str(stmt) + ".sig").unlink(missing_ok=True)
        die(f"the signature does not verify against {signers} for {principal}: {msg}. Is {key} the key listed "
            f"for {principal}? Nothing recorded.", code=3)
    ctx = gate_context("signed")
    ctx["approval"] = {"file": change.rel(stmt), "principal": principal, "seq": seq, "sha256": sha256(stmt),
                       "signers": str(signers), "verified": msg}
    return principal, "signed", ctx


AGENT_PROC_RE = re.compile(r"opencode|claude|codex|cursor|gemini|aider|goose|copilot|windsurf|\bamp\b", re.I)


def process_ancestry(limit: int = 15) -> List[str]:
    """Command names of the parent processes, nearest first (best effort; Linux /proc, else ps)."""
    names, pid = [], os.getppid()
    for _ in range(limit):
        if pid <= 1:
            break
        try:
            data = Path(f"/proc/{pid}/stat").read_text()
            comm = data[data.index("(") + 1:data.rindex(")")]
            ppid = int(data[data.rindex(")") + 2:].split()[1])
        except (OSError, ValueError, IndexError):
            try:
                out = subprocess.run(["ps", "-o", "ppid=,comm=", "-p", str(pid)], capture_output=True,
                                     text=True, timeout=5).stdout.strip().split(None, 1)
                ppid, comm = int(out[0]), out[1]
            except (OSError, ValueError, IndexError, subprocess.SubprocessError):
                break
        names.append(os.path.basename(comm))
        pid = ppid
    return names


def gate_context(via: str) -> dict:
    """Audit facts about where a human decision was recorded. A determined agent can fake a terminal;
    this makes such a record visible afterwards (status warns), it does not prevent it."""
    ancestors = process_ancestry()
    agents = sorted({a for a in ancestors if AGENT_PROC_RE.search(a)})
    env = sorted(k for k in os.environ if k == "CLAUDECODE" or k.startswith("OPENCODE") or k.startswith("CODEX_"))
    try:
        tty = os.ttyname(0) if sys.stdin.isatty() else None
    except OSError:
        tty = None
    return {"via": via, "tty": tty, "ancestors": ancestors[:8], "agent_processes": agents, "agent_env": env,
            "suspect": via in ("terminal",) and bool(agents or env)}


def confirm_human(ws: Workspace, what: str, by: Optional[str], cmdline: str,
                  change: Optional["Change"] = None, payload: Optional[dict] = None) -> Tuple[str, str, dict]:
    """Return (name, via, context).

    signed: an SSH signature by a listed approver over a statement binding exactly what is approved.
    terminal: a person types their name at an interactive terminal. chat: the agent records --by."""
    mode = human_gate_mode(ws, change)
    if mode == "signed":
        return sign_approval(ws, change, what, by, payload or {"action": "decision"}, cmdline)
    if mode != "terminal":
        if not by or not by.strip():
            die("--by must name the human who decided")
        return by.strip(), "chat", gate_context("chat")
    if not sys.stdin.isatty():
        die("this is a human gate, and human gates for this change are 'terminal'.\n"
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
    ctx = gate_context("terminal")
    if ctx["suspect"]:
        print("WARNING: this terminal runs inside an AI agent's process tree "
              f"({', '.join(ctx['agent_processes'] + ctx['agent_env'])}). The record will be flagged for review.")
    return name, "terminal", ctx


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
    rep.extend(check_review_reports(c, a.verdict))
    amends = c.state.get("amendments", [])
    last = amends[-1] if amends else None
    if last and c.state.get("accreditation") is None:
        if last.get("wording_only"):
            before_ids = set(last.get("scenario_ids_before", []))
            now_ids = set(delta_scenarios(c)) | set(delta_req_ids(c))
            if before_ids and before_ids != now_ids:
                rep.err("wording-only", "requirement or scenario IDs changed, so this is not a wording-only "
                        "amendment: `amend` again without --wording-only")
        else:
            prior = set(last.get("prior_reviews", []))
            fresh = {f.name for f in c.p("reviews").glob("accredit-r*-*.md")} - prior if c.p("reviews").is_dir() else set()
            for lens in REQUIRED_LENSES[c.track]:
                if not any(REVIEW_NAME_RE.match(f) and REVIEW_NAME_RE.match(f).group(2) == lens for f in fresh):
                    rep.err("reviews/", f"the design was amended: lens '{lens}' needs a new report written after "
                            f"the amendment (next round: reviews/accredit-r<N+1>-{lens}.md)")
    if not c.p("accreditation.md").is_file():
        rep.err("accreditation.md", "missing; write the accreditation record before recording a verdict")
    if a.verdict != "rejected":
        print(rep.render("accreditation preconditions"))
        if not rep.ok:
            return 1
    if a.verdict == "conditional" and not a.condition:
        die("a conditional verdict needs at least one --condition")
    parts = ["accredit", c.id, "--verdict", a.verdict] + [x for cond in (a.condition or []) for x in ("--condition", cond)]
    lock = {c.rel(f): sha256(f) for f in c.design_files()} if a.verdict in ("approved", "conditional") else None
    rnd = len(c.state.get("amendments", []))
    head = git(ws, "rev-parse", "HEAD")
    payload = {"action": "accredit", "verdict": a.verdict, "conditions": a.condition or [],
               "lock_digest": digest(lock) if lock is not None else None, "round": rnd, "head": head}
    by, via, ctx = confirm_human(ws, f"record verdict '{a.verdict.upper()}' for design of change '{c.id}'", a.by,
                                 gate_cmdline(ws, *parts), c, payload)
    rec = {"verdict": a.verdict, "by": by, "via": via, "at": now(), "conditions": a.condition or [], "round": rnd,
           "head": head, "context": ctx}
    if lock is not None:
        rec["lock"] = lock
        rec["base"] = base_hashes(c)
        rec["req_hashes"] = delta_req_hashes(c)
    c.state["accreditation"] = rec
    if lock is not None:
        set_checkpoint(c, "design approval")
    reopened: List[str] = []
    if "lock" in rec:
        reopened = reopen_affected_sprints(c, rec)
        for cr in c.state.get("requests", {}).values():
            if cr.get("status") == "applying":
                cr["status"] = "applied"
                cr["applied_at"] = rec["at"]
    c.log("accredit", f"{a.verdict} by {by} (via {via})")
    c.save()
    print(f"{c.id}: verdict {a.verdict.upper()} recorded for {by} (via {via})")
    if "lock" in rec:
        print(f"locked {len(rec['lock'])} design file(s). Any later edit breaks the lock and requires `amend`.")
    for line in reopened:
        print(line)
    return 0


def active_sprint(c: "Change") -> Optional[str]:
    return next((n for n, s in c.state.get("sprints", {}).items() if s.get("status") == "active"), None)


def freeze_on(ws: Workspace) -> bool:
    return (project_setting(ws, "Sprint freeze") or "on").lower() not in ("off", "no", "false")


def cmd_amend(a: argparse.Namespace) -> int:
    ws = Workspace.locate(a.root)
    c = ws.change(a.id)
    if c.phase in ("ideate", "propose", "archived"):
        die(f"nothing to amend in phase '{c.phase}'")
    if a.to == "ideate" and c.track != "full":
        die("a lite change has no HLD; amend to 'propose'")
    crs = [x.strip().upper() for x in (a.cr or "").split(",") if x.strip()]
    reqs = c.state.get("requests", {})
    for cid in crs:
        r = reqs.get(cid)
        if not r:
            die(f"unknown request {cid} (record it with `cr add`)")
        if r.get("status") != "amend":
            die(f"{cid} is '{r.get('status')}'; only requests decided as 'amend' can drive an amendment (`cr decide`)")
    act = active_sprint(c)
    if a.wording_only and crs:
        die("--wording-only amendments do not apply change requests; amend for the requests separately")
    if c.phase in ("scrum", "sprint", "retro") and not crs and not a.wording_only:
        die("after the plan exists, an amendment must name the change request(s) it applies: --cr CR-001[,CR-002] "
            "(or --wording-only for a meaning-neutral wording fix)")
    if act and freeze_on(ws):
        non_blockers = [cid for cid in crs if not reqs[cid].get("blocker")]
        if non_blockers:
            die(f"sprint {act} is active and the sprint freeze is on: only blocker requests may amend mid-sprint "
                f"({', '.join(non_blockers)} must wait for the sprint boundary). Sign off or rewind the sprint first.")
    raw_budget = project_setting(ws, "Max amendments per change")
    bm = re.match(r"\D*(\d+)", raw_budget or "")
    if raw_budget and not bm:
        print(f"warning: cannot read 'Max amendments per change: {raw_budget}' in project.md; no budget applied",
              file=sys.stderr)
    budget = int(bm.group(1)) if bm else None
    done = len([x for x in c.state.get("amendments", []) if not x.get("wording_only")])
    over = budget is not None and done >= budget and not a.wording_only
    if over and not a.over_budget:
        die(f"amendment budget reached ({done}/{budget}, project.md). Repeated amendments mean the design no longer "
            f"fits; consider closing this change and starting a new one from ideate. To proceed anyway, a person "
            f"approves it: --over-budget \"<reason>\".")
    gate_parts = ["amend", c.id, "--reason", a.reason, "--to", a.to] + (["--cr", a.cr] if a.cr else []) + \
        (["--over-budget", a.over_budget] if a.over_budget else []) + (["--wording-only"] if a.wording_only else [])
    approved = None
    if over or a.wording_only:
        what = ("exceed the amendment budget" if over else "amend WITHOUT reopening sprints (wording only)")
        by, via, ctx = confirm_human(ws, f"{what} for change '{c.id}': {a.reason}", a.by, gate_cmdline(ws, *gate_parts), c,
                                     {"action": "amend", "reason": a.reason, "crs": crs,
                                      "wording_only": bool(a.wording_only), "over_budget": a.over_budget,
                                      "index": len(c.state.get("amendments", [])),
                                      "req_digest": digest(delta_req_hashes(c))})
        approved = {"by": by, "via": via, "context": ctx}
    prev = c.phase
    old = c.state.get("accreditation")
    if old:
        c.state.setdefault("superseded_accreditations", []).append(old)
    c.state["accreditation"] = None
    for n, s in c.state.get("sprints", {}).items():
        if s.get("status") == "active":
            s["status"] = "interrupted"
    for cid in crs:
        reqs[cid]["status"] = "applying"
    c.state.setdefault("amendments", []).append(
        {"at": now(), "from": prev, "to": a.to, "reason": a.reason, "crs": crs,
         "req_hashes_before": delta_req_hashes(c),
         "scenario_ids_before": sorted(set(delta_scenarios(c)) | set(delta_req_ids(c))),
         "prior_reviews": sorted(f.name for f in c.p("reviews").glob("accredit-r*-*.md")) if c.p("reviews").is_dir() else [],
         **({"wording_only": True} if a.wording_only else {}),
         **({"approved": approved} if approved else {}),
         **({"over_budget": a.over_budget} if a.over_budget else {})})
    c.state["phase"] = a.to
    c.log("amend", f"from {prev} to {a.to}: {a.reason}" + (f" [{', '.join(crs)}]" if crs else ""))
    c.save()
    print(f"{c.id}: reopened design ({prev} -> {a.to})" + (f" for {', '.join(crs)}" if crs else "")
          + ". Re-accreditation is required; signed-off sprints affected by the change reopen when it is re-approved.")
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
        prior = c.state.get("sprints", {}).get(str(n), {}).get("prior_verifications", [])
        if not vf.is_file():
            rep.err(c.rel(vf), "missing goldfish verification report")
        elif vf.name in prior:
            rep.err(c.rel(vf), "this verification predates the sprint's (re)start; run a new verifier round "
                    "(sprint-NN-verification-r<N>.md)")
        else:
            verdict = verification_verdict(read(vf))
            if not verdict:
                rep.err(c.rel(vf), "needs a 'Verdict: PASS | PASS-WITH-NOTES | FAIL' line")
            elif verdict == "FAIL":
                rep.err(c.rel(vf), "verification verdict is FAIL")
        drift = c.lock_drift()
        if drift:
            rep.err("lock", "design changed after accreditation: " + ", ".join(drift))
        rep.extend(check_boundary(c, n, b))
        rep.extend(check_gates_evidence(c, n))
        rep.extend(check_approvals(c))
    return rep


def deviation_paths(text: str) -> List[str]:
    """Paths declared in '## Deviations' bullets: backticked tokens, or path-like words."""
    out: List[str] = []
    for ln in text.splitlines():
        if not re.match(r"^\s*[-*]\s+", ln):
            continue
        ticks = re.findall(r"`([^`]+)`", ln)
        cand = ticks or re.findall(r"[\w.*?\[\]@+-]+(?:/[\w.*?\[\]@+-]+)+|[\w*?-]+\.[\w]+", ln)
        out += [t.strip() for t in cand if t.strip()]
    return out


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
    dev = strip_comments(find_section(sections(sprint_text, 2), "deviation") or "")
    declared = deviation_paths(dev)
    for f in changed:
        if not path_allowed(f, allowed) and not path_allowed(f, declared):
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
    run = c.state.get("sprints", {}).get(str(n), {}).get("run")
    if run and rec.get("run") != run:
        rep.err("gates", f"the recorded gate run predates this sprint's (re)start; run `specmaker.py gates {c.id} {n}` again")
    if not rec.get("passed"):
        failed = [g["name"] for g in rec.get("results", []) if g.get("exit") != 0]
        rep.err("gates", "last gate run failed: " + ", ".join(failed))
    head = git(c.ws, "rev-parse", "HEAD")
    if head and rec.get("sha") and rec.get("sha") != head:
        between = git_z(c.ws, "diff", "--name-only", "-z", "--relative", rec["sha"], "HEAD")
        code_changes = [f for f in (between or ["?"]) if not skip_path(f, c.ws)]
        if code_changes:
            rep.err("gates", f"gates ran at {str(rec.get('sha'))[:10]} but code changed since "
                    f"({', '.join(code_changes[:5])}); re-run gates on the code being signed off")
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
        proc = subprocess.Popen(cmd, shell=True, cwd=ws.project, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, errors="replace", start_new_session=(os.name == "posix"))
        try:
            out, _ = proc.communicate(timeout=a.timeout)
            code = proc.returncode
        except subprocess.TimeoutExpired:
            if os.name == "posix":
                import signal
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except OSError:
                    pass
            else:
                proc.kill()
            partial, _ = proc.communicate()
            code, out = 124, f"timed out after {a.timeout}s\n" + (partial or "")
        tail = "\n".join(out.strip().splitlines()[-40:])
        print(("    PASS" if code == 0 else f"    FAIL (exit {code})") + ("\n" + tail if code else ""), flush=True)
        results.append({"name": name, "cmd": cmd, "exit": code, "tail": tail})
    rec = {"at": now(), "sprint": a.n, "run": c.state.get("sprints", {}).get(str(a.n), {}).get("run"),
           "sha": git(ws, "rev-parse", "HEAD"),
           "dirty": bool(git(ws, "status", "--porcelain")), "passed": all(r["exit"] == 0 for r in results),
           "results": results}
    gf = gates_file(c, a.n)
    gf.parent.mkdir(parents=True, exist_ok=True)
    gf.write_text(json.dumps(rec, indent=2) + "\n", encoding="utf-8")
    c.log("gates", f"sprint {a.n}: {'PASS' if rec['passed'] else 'FAIL'}")
    c.save()
    print(f"{'PASS' if rec['passed'] else 'FAIL'} - recorded in {c.rel(gf)}")
    return 0 if rec["passed"] else 1


# decision: a design or process choice. contested / escalated / declined / condition: the outcome of a
# review finding (--ref <report>#G<n>). answer: an answered reviewer question.
LEDGER_KINDS = ["decision", "contested", "escalated", "declined", "condition", "question", "answer", "deviation", "note"]
FINDING_KINDS = ("contested", "escalated", "declined", "condition")


def cmd_ledger(a: argparse.Namespace) -> int:
    """Append-only decision ledger. Reviewers read it so settled points are not re-raised."""
    ws = Workspace.locate(a.root)
    c = ws.change(a.id)
    f = c.p("ledger.md")
    if not a.text:
        print(read(f) if f.is_file() else "ledger is empty")
        return 0
    print(append_ledger(c, a.kind, " ".join(a.text).strip(), a.ref) + " recorded")
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


def baseline_hashes(c: "Change") -> Optional[Dict[str, str]]:
    """Requirement hashes of the approved design before the latest amendment (snapshot taken by `amend`).

    With the design reopened and no amendment snapshot, fall back to the current approval's hashes."""
    amends = c.state.get("amendments", [])
    if amends and amends[-1].get("req_hashes_before") is not None:
        return amends[-1]["req_hashes_before"]
    acc = c.state.get("accreditation") or {}
    if not acc.get("lock") and acc.get("req_hashes"):
        return acc["req_hashes"]
    return None


def reopen_affected_sprints(c: "Change", rec: dict) -> List[str]:
    """After a re-accreditation, reopen signed-off sprints whose stories cover changed requirements."""
    amends = c.state.get("amendments", [])
    if amends and amends[-1].get("wording_only"):
        return ["wording-only amendment: no sprints reopened"]
    old = baseline_hashes(c) if amends else None
    if old is None:
        return []
    new = rec.get("req_hashes", {})
    changed = {rid for rid in set(old) | set(new) if old.get(rid) != new.get(rid)}
    rec["changed_requirements"] = sorted(changed)
    if not changed or not c.p("backlog.md").is_file():
        return [f"changed requirements since last approval: {', '.join(sorted(changed)) or 'none'}"]
    b, _ = parse_backlog(read(c.p("backlog.md")))
    out = [f"changed requirements since last approval: {', '.join(sorted(changed))}"]
    for n, s in sorted(c.state.get("sprints", {}).items(), key=lambda kv: int(kv[0])):
        if s.get("status") != "signed-off":
            continue
        hit = sorted({sc for sid in s.get("stories", b.plan.get(int(n), [])) if sid in b.stories
                      for sc in b.stories[sid].covers if sc.rsplit(".", 1)[0] in changed})
        if hit:
            s.setdefault("history", []).append({k: v for k, v in s.items() if k != "history"})
            for k in ("by", "via", "at", "context", "accepted_gaps"):
                s.pop(k, None)  # the signed sign-off lives on in history only
            s.update({"status": "reopened", "reopened_at": now(), "reopen_scenarios": hit})
            out.append(f"sprint {n} REOPENED: its stories cover changed scenarios {', '.join(hit)}; "
                       f"re-run it (`sprint-start {c.id} {n}`) and sign it off again")
    return out


CR_STATUSES = ["parked", "rejected", "deferred", "backlog", "amend", "applying", "applied"]
CR_OUTCOMES = ["reject", "defer", "backlog", "amend"]
CR_OUTCOME_STATUS = {"reject": "rejected", "defer": "deferred", "backlog": "backlog", "amend": "amend"}
CR_DEFAULT_CLASS = {"backlog": 1, "amend": 2, "defer": 3}


def cmd_cr(a: argparse.Namespace) -> int:
    ws = Workspace.locate(a.root)
    c = ws.change(a.id)
    reqs = c.state.setdefault("requests", {})
    if a.cr_action == "add":
        n = len(reqs) + 1
        cid = f"CR-{n:03d}"
        act = active_sprint(c)
        reqs[cid] = {"title": a.title, "requested_by": a.by, "reason": a.reason or "", "blocker": bool(a.blocker),
                     "received": now(), "phase": c.phase, "sprint": act, "status": "parked"}
        f = c.p(f"requests/{cid}.md")
        f.parent.mkdir(parents=True, exist_ok=True)
        tpl = TEMPLATES / "change-request.md"
        text = read(tpl) if tpl.is_file() else "# {cr}: {title}\n"
        f.write_text(text.replace("{cr}", cid).replace("{title}", a.title).replace("{by}", a.by)
                     .replace("{received}", today()).replace("{phase}", c.phase + (f", sprint {act} active" if act else ""))
                     .replace("{blocker}", "yes" if a.blocker else "no").replace("{reason}", a.reason or ""),
                     encoding="utf-8")
        c.log("cr-add", f"{cid} {'BLOCKER ' if a.blocker else ''}{a.title}")
        c.save()
        print(f"{cid} recorded as PARKED{' (blocker)' if a.blocker else ''}: {c.rel(f)}")
        if act and freeze_on(ws) and not a.blocker:
            print(f"sprint {act} is active and frozen: this request waits for the sprint boundary. Keep building.")
        elif a.blocker:
            print("blocker: triage it now (impact analysis, then `cr decide`).")
        return 0
    if a.cr_action == "list":
        rows = sorted(reqs.items())
        if a.json:
            print(json.dumps(dict(rows), indent=2))
            return 0
        if not rows:
            print("no change requests")
        for cid, r in rows:
            print(f"{cid}  {r['status']:9s} {'BLOCKER ' if r.get('blocker') else ''}{r['title']}  "
                  f"(by {r.get('requested_by')}, {r.get('received', '')[:10]})")
        return 0
    # decide
    ids = [x.upper() for x in a.crs]
    if not ids:
        die("name the request(s) to decide, e.g. `cr decide <id> CR-001 CR-002 --outcome reject --reason ...`")
    for cid in ids:
        r = reqs.get(cid)
        if not r:
            die(f"unknown request {cid}")
        if r["status"] != "parked":
            die(f"{cid} is already '{r['status']}'")
    act = active_sprint(c)
    if act and freeze_on(ws) and a.outcome in ("backlog", "amend"):
        frozen = [cid for cid in ids if not reqs[cid].get("blocker")]
        if frozen:
            die(f"sprint {act} is active and the sprint freeze is on: {', '.join(frozen)} can only be rejected or "
                f"deferred now. Accepting it into the backlog or design waits for the sprint boundary, when all "
                f"parked requests are triaged together.")
    if not a.reason:
        die("--reason is required: record why, so the decision survives the conversation")
    parts = ["cr", "decide", c.id, *ids, "--outcome", a.outcome, "--reason", a.reason] + \
            (["--class", str(a.cls)] if a.cls is not None else [])
    pre_lock = c.phase in ("ideate", "propose") or (c.phase == "accredit" and not (c.state.get("accreditation") or {}).get("lock"))
    cls = a.cls if a.cls is not None else CR_DEFAULT_CLASS.get(a.outcome)
    payload = {"action": "cr-decide", "requests": ids, "outcome": a.outcome, "reason": a.reason, "class": cls,
               "pre_lock": pre_lock}
    by, via, ctx = confirm_human(ws, f"decide {', '.join(ids)} as '{a.outcome.upper()}' for change '{c.id}'", a.by,
                                 gate_cmdline(ws, *parts), c, payload)
    status = CR_OUTCOME_STATUS[a.outcome]
    if a.outcome == "amend" and pre_lock:
        status = "applied"  # design is not locked yet: edit it directly, no amendment needed
    for cid in ids:
        reqs[cid].update({"status": status, "class": cls,
                          "decision": {"outcome": a.outcome, "reason": a.reason, "class": cls, "pre_lock": pre_lock,
                                       "by": by, "via": via, "at": now(), "context": ctx}})
        append_ledger(c, "decision", f"{cid} {a.outcome.upper()}: {a.reason}", ref=f"requests/{cid}.md")
    c.log("cr-decide", f"{', '.join(ids)} -> {a.outcome} by {by} (via {via})")
    c.save()
    print(f"{', '.join(ids)}: {status} (decided by {by}, via {via})")
    hints = {"defer": "start a separate change for it when the time comes: `new <change-id>`",
             "backlog": "add or adjust stories in backlog.md, then `check <id> backlog`",
             "amend": ("design not locked yet: edit the HLD/LLD/specs directly" if pre_lock else
                       "run `impact`, optionally `rewind`, then `amend <id> --cr " + ",".join(ids) + " --to ideate|propose`")}
    if a.outcome in hints:
        print("next: " + hints[a.outcome].replace("<id>", c.id))
    return 0


def impact_report(c: "Change", reqs_arg: Optional[List[str]]) -> str:
    old_h = baseline_hashes(c)
    now_h = delta_req_hashes(c)
    if reqs_arg:
        changed = sorted(set(reqs_arg))
        basis = "requirements named on the command line"
    elif old_h is not None:
        old = old_h
        acc_now = c.state.get("accreditation") or {}
        changed = sorted(rid for rid in set(old) | set(now_h) if old.get(rid) != now_h.get(rid))
        basis = ("changes made by the latest amendment (design before the amendment vs the re-approved design)"
                 if acc_now.get("lock") else "delta specs compared with the design before the current amendment")
    else:
        changed = sorted(now_h)
        basis = "all requirements of this change (nothing approved yet)"
    b = parse_backlog(read(c.p("backlog.md")))[0] if c.p("backlog.md").is_file() else None
    sprint_of = {sid: n for n, ids in (b.plan.items() if b else []) for sid in ids}
    sprints = c.state.get("sprints", {})
    scen = delta_scenarios(c)
    lines = [f"# Impact: {c.id}", "", f"Generated {now()} by specmaker.py impact. Basis: {basis}.", ""]
    if not changed:
        return "\n".join(lines + ["No changed requirements."]) + "\n"
    rows = ["| Requirement | Scenarios | Stories (sprint: status) | Files (from tasks) | Tests |", "|---|---|---|---|---|"]
    touched_sprints: Dict[int, str] = {}
    all_scn: List[str] = []
    for rid in changed:
        scns = sorted(s for s in scen if s.rsplit(".", 1)[0] == rid)
        stories = []
        files: List[str] = []
        if b:
            for sid, st in b.stories.items():
                if any(sc.rsplit(".", 1)[0] == rid for sc in st.covers):
                    n = sprint_of.get(sid)
                    status = sprints.get(str(n), {}).get("status", "not started") if n else "unplanned"
                    stories.append(f"{sid} (S{n}: {status})" if n else f"{sid} (unplanned)")
                    files += task_paths(st)
                    scns = sorted(set(scns) | {sc for sc in st.covers if sc.rsplit(".", 1)[0] == rid})
                    if n:
                        touched_sprints[n] = status
        all_scn += scns
        rows.append(f"| {rid}{'' if rid in now_h else ' (removed)'} | {', '.join(scns) or '-'} | "
                    f"{'<br>'.join(stories) or '-'} | {'<br>'.join(sorted(set(files))) or '-'} | {{tests:{rid}}} |")
    refs = scan_refs(c.ws, sorted(set(all_scn)))
    text = "\n".join(rows)
    for rid in changed:
        tests = sorted({t for sc in all_scn if sc.rsplit(".", 1)[0] == rid for t in refs.get(sc, {}).get("tests", [])})
        text = text.replace(f"{{tests:{rid}}}", "<br>".join(tests) or "-")
    lines.append(text)
    lines.append("")
    done = sorted(n for n, st in touched_sprints.items() if st == "signed-off")
    live = sorted(n for n, st in touched_sprints.items() if st in ("active", "interrupted"))
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Changed requirements: {', '.join(changed)}")
    lines.append(f"- Signed-off sprints affected (reopen on re-approval): {', '.join(map(str, done)) or 'none'}")
    lines.append(f"- In-progress sprints affected: {', '.join(map(str, live)) or 'none'}")
    if done:
        lines.append(f"- Rewind candidate: `rewind {c.id} --to sprint:{min(done)}` discards all code since sprint {min(done)} began")
    elif live:
        lines.append(f"- Rewind candidate: `rewind {c.id} --to sprint` discards the active sprint's work; "
                     f"`--to head` discards only uncommitted work")
    else:
        lines.append("- No implemented work is affected; no rewind needed")
    return "\n".join(lines) + "\n"


def cmd_impact(a: argparse.Namespace) -> int:
    ws = Workspace.locate(a.root)
    c = ws.change(a.id)
    reqs_arg = [x.strip().upper() for x in (a.reqs or "").split(",") if x.strip()] or None
    md = impact_report(c, reqs_arg)
    if a.out:
        out = Path(a.out)
        out = out if out.is_absolute() else c.dir / out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(md, encoding="utf-8")
        print(f"wrote {out}")
    else:
        print(md)
    return 0


def cmd_rewind(a: argparse.Namespace) -> int:
    """Discard implementation work (never specmaker/ files) after taking a backup, as a normal new commit."""
    ws = Workspace.locate(a.root)
    c = ws.change(a.id)
    if git(ws, "rev-parse", "--is-inside-work-tree") != "true":
        die("rewind needs a git repository")
    sprints = c.state.get("sprints", {})
    to = a.to
    n: Optional[int] = None
    if to == "sprint":
        act = active_sprint(c)
        started = [int(k) for k, s in sprints.items() if s.get("base_sha")]
        n = int(act) if act else (max(started) if started else None)
    elif to == "change":
        started = [int(k) for k, s in sprints.items() if s.get("base_sha")]
        n = min(started) if started else None
    elif to.startswith("sprint:") and to[7:].isdigit():
        n = int(to[7:])
    elif to != "head":
        die("--to must be head, sprint, sprint:N or change")
    if to != "head" and (n is None or not sprints.get(str(n), {}).get("base_sha")):
        die(f"no recorded git base for that sprint ({to}); nothing to rewind to")
    wsr = ws_rel(ws)
    spec = ["--", ".", f":(exclude){wsr}"]
    prefix = git(ws, "rev-parse", "--show-prefix") or ""
    dirty = []
    fields = git_z(ws, "status", "--porcelain=v1", "-z", "--untracked-files=all", *spec) or []
    i = 0
    while i < len(fields):
        entry = fields[i]
        path = entry[3:]
        if entry[:2].strip().startswith(("R", "C")):
            i += 1  # renames/copies carry the source path as the next field
        dirty.append(path[len(prefix):] if prefix and path.startswith(prefix) else path)
        i += 1
    base = sprints[str(n)]["base_sha"] if n else None
    committed: List[Tuple[str, str]] = []
    if base:
        fields = git_z(ws, "diff", "--name-status", "--no-renames", "-z", "--relative", base, "HEAD", *spec)
        if fields is None:
            die("git diff against the sprint base failed; nothing was changed")
        committed = [(fields[k], fields[k + 1]) for k in range(0, len(fields) - 1, 2)]
    if not dirty and not committed:
        print("nothing to discard: the working tree already matches the rewind point (outside specmaker/)")
        return 0
    label = "uncommitted work" if to == "head" else f"all work since sprint {n} started ({base[:10]})"
    print(f"REWIND {c.id}: discards {label}")
    for f in (dirty + [p for _, p in committed])[:40]:
        print(f"  {f}")
    parts = ["rewind", c.id, "--to", to] + (["--cr", a.cr] if a.cr else [])
    rw_base = base or git(ws, "rev-parse", "HEAD")
    payload = {"action": "rewind", "to": to, "sprint": n, "base": rw_base}
    by, via, ctx = confirm_human(ws, f"DISCARD {label} for change '{c.id}' (a backup branch and stash are kept)",
                                 a.by, gate_cmdline(ws, *parts), c, payload)
    tag = f"specmaker-backup/{c.id}/{_dt.datetime.now().strftime('%Y%m%d-%H%M%S')}"
    if git(ws, "branch", tag, "HEAD") is None:
        die("could not create the backup branch; nothing was changed")
    if dirty:
        if git(ws, "stash", "push", "--include-untracked", "-m", tag, *spec) is None:
            die(f"could not stash uncommitted work; backup branch {tag} exists, nothing else changed")
    paths, failed = [], []
    for st, path in committed:
        if git(ws, "cat-file", "-e", f"{base}:./{path}") is not None:
            ok = git(ws, "checkout", base, "--", path) is not None
        else:
            ok = git(ws, "rm", "-q", "-f", "--", path) is not None
        (paths if ok else failed).append(path)
    committed_ok = True
    if paths and not failed:
        msg = f"specmaker: rewind {c.id} to start of sprint {n} (backup: {tag})"
        committed_ok = git(ws, "commit", "-q", "-m", msg, "--", *paths) is not None
    if failed or not committed_ok:
        # undo our partial restore so the tree is exactly as it was after the backup
        for path in paths:
            git(ws, "reset", "-q", "HEAD", "--", path)
            git(ws, "checkout", "HEAD", "--", path)
        problem = (f"could not restore: {', '.join(failed)}" if failed else "the rewind commit failed (check git user.name/email)")
        die(f"{problem}. Committed code is unchanged. Backup branch {tag}"
            + ("; uncommitted work was stashed: run `git stash pop` to get it back" if dirty else ""))
    rewound = []
    if n is not None:
        b = parse_backlog(read(c.p("backlog.md")))[0] if c.p("backlog.md").is_file() else None
        untick = set()
        for k, s in sprints.items():
            if int(k) >= n and s.get("status") in ("active", "signed-off", "interrupted", "reopened"):
                s.setdefault("history", []).append({kk: vv for kk, vv in s.items() if kk != "history"})
                for kk in ("by", "via", "at", "context", "accepted_gaps"):
                    s.pop(kk, None)  # the signed sign-off lives on in history only
                s.update({"status": "rewound", "rewound_at": now(), "backup": tag})
                rewound.append(k)
                if b:
                    for sid in s.get("stories", b.plan.get(int(k), [])):
                        if sid in b.stories:
                            untick |= {t[0] for t in b.stories[sid].tasks}
        if untick and c.p("backlog.md").is_file():
            lines = read(c.p("backlog.md")).splitlines(keepends=True)
            for i, ln in enumerate(lines):
                m = TASK_RE.match(ln)
                if m and m.group(2) in untick:
                    lines[i] = re.sub(r"\[[xX~]\]", "[ ]", ln, count=1)
            c.p("backlog.md").write_text("".join(lines), encoding="utf-8")
    set_checkpoint(c, f"rewind to {to}")
    c.state.setdefault("rewinds", []).append({"to": to, "sprint": n, "base": rw_base, "by": by, "via": via,
                                              "at": now(), "backup": tag, "stashed": bool(dirty), "cr": a.cr,
                                              "context": ctx})
    if a.cr and a.cr.upper() in c.state.get("requests", {}):
        c.state["requests"][a.cr.upper()]["rewind"] = {"to": to, "backup": tag, "at": now()}
    lid = append_ledger(c, "note", f"REWIND to {to} ({label}) by {by} via {via}; backup branch {tag}"
                        + (", uncommitted work stashed" if dirty else "")
                        + (f"; sprints {', '.join(rewound)} rewound, their tasks unticked" if rewound else ""), ref=a.cr)
    c.log("rewind", f"to {to} by {by} (via {via}); backup {tag}")
    c.save()
    print(f"rewound. Backup branch: {tag}" + (" (uncommitted work is in `git stash list`)" if dirty else ""))
    if rewound:
        print(f"sprints {', '.join(rewound)} marked rewound; their tasks were unticked in backlog.md ({lid})")
    undo = []
    if paths:
        undo.append(f"git checkout {tag} -- . ':(exclude){wsr}'")
    if dirty:
        undo.append("git stash pop")
    print("undo the code (specmaker/ state is kept): " + " && ".join(f"`{u}`" for u in undo))
    return 0


def plan_required(c: "Change") -> bool:
    """project.md `Plan approval: full|all|off`. full (default): required on the full track only;
    all: every change; off: never. An unreadable value falls back to the default."""
    words = re.findall(r"[a-z]+", (project_setting(c.ws, "Plan approval") or "full").lower())
    v = words[0] if words else "full"
    if v in ("off", "no", "false", "never"):
        return False
    if v in ("all", "always", "required", "yes", "on"):
        return True
    return c.track == "full"  # "full", or anything unreadable: the safe default


def plan_digest(c: "Change") -> Optional[str]:
    """Digest of backlog.md with task ticks ignored: progress is not a plan change."""
    f = c.p("backlog.md")
    if not f.is_file():
        return None
    text = re.sub(r"(?m)^(\s*[-*]\s+)\[[xX~]\]", r"\1[ ]", read(f))
    return hashlib.sha256(text.encode()).hexdigest()


def plan_approval_problem(c: "Change") -> Optional[str]:
    if not plan_required(c):
        return None
    approvals = c.state.get("plan_approvals", [])
    if not approvals:
        return "the backlog and sprint plan are not approved: a person runs `approve-plan <id>`"
    if approvals[-1].get("backlog_digest") != plan_digest(c):
        return "the backlog changed since the plan was approved: a person runs `approve-plan <id>` again"
    return None


def set_checkpoint(c: "Change", event: str) -> None:
    """Record the commit at which code is known to be approved (design approval, sign-off, rewind)."""
    sha = git(c.ws, "rev-parse", "HEAD")
    if sha:
        c.state["checkpoint"] = {"sha": sha, "event": event, "at": now()}


def code_since_checkpoint(c: "Change") -> List[str]:
    cp = (c.state.get("checkpoint") or {}).get("sha")
    if not cp:
        return []
    return changed_files(c.ws, cp) or []


def cmd_approve_plan(a: argparse.Namespace) -> int:
    ws = Workspace.locate(a.root)
    c = ws.change(a.id)
    if c.phase not in ("scrum", "sprint"):
        die(f"change is in phase '{c.phase}'; the plan is approved in scrum (or re-approved during sprints)")
    if c.lock_drift():
        die("design changed after accreditation; `amend` and re-accredit first")
    rep, b = check_backlog(c)
    print(rep.render("backlog"))
    if not rep.ok or not b:
        return 1
    d = plan_digest(c)
    if (c.state.get("plan_approvals") or [{}])[-1].get("backlog_digest") == d:
        print("the current plan is already approved")
        return 0
    sprints = {str(n): ids for n, ids in sorted(b.plan.items())}
    points = sum(int(st.fields.get("points", "0") or 0) for st in b.stories.values() if st.fields.get("points", "").isdigit())
    payload = {"action": "plan", "backlog_digest": d, "sprints": sprints, "stories": len(b.stories),
               "epics": len(b.epics), "features": len(b.features)}
    by, via, ctx = confirm_human(ws, f"approve the plan of change '{c.id}': {len(b.epics)} epic(s), "
                                 f"{len(b.features)} feature(s), {len(b.stories)} stories, {points} points, "
                                 f"{len(b.plan)} sprint(s)", a.by, gate_cmdline(ws, "approve-plan", c.id), c, payload)
    c.state.setdefault("plan_approvals", []).append({"backlog_digest": d, "sprints": sprints, "by": by, "via": via,
                                                    "at": now(), "context": ctx})
    append_ledger(c, "decision", f"plan approved by {by} (via {via}): {len(b.stories)} stories in {len(b.plan)} sprint(s)")
    c.log("approve-plan", f"by {by} (via {via})")
    c.save()
    print(f"{c.id}: plan approved by {by} (via {via})")
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
    brep.extend(check_approvals(c))
    if not brep.ok or not b:
        print(brep.render("backlog and approvals"))
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
    reqs = c.state.get("requests", {})
    parked = sorted(cid for cid, r in reqs.items() if r.get("status") == "parked")
    if parked:
        die(f"parked request(s) {', '.join(parked)} must be triaged first: at a sprint boundary all parked requests "
            f"are decided together (`cr list`, then `cr decide ... --outcome reject|defer|backlog|amend`)")
    blocking = [cid for cid, r in reqs.items() if r.get("status") in ("amend", "applying")]
    if blocking:
        die(f"{', '.join(blocking)} must be applied first (`amend --cr ...` and re-accreditation) before a sprint starts")
    problem = plan_approval_problem(c)
    if problem:
        die(problem.replace("<id>", c.id))
    early = code_since_checkpoint(c)
    if early:
        cp = c.state["checkpoint"]
        if not a.accept_prior:
            die(f"code outside specmaker/ changed since the last checkpoint ({cp['event']}, {cp['sha'][:10]}), "
                f"before implementation was allowed to start:\n  " + "\n  ".join(early[:20])
                + ("\n  ..." if len(early) > 20 else "")
                + "\nRevert it (or commit/stash unrelated work elsewhere), or a person accepts it: "
                f"`sprint-start {c.id} {n} --accept-prior \"<reason>\"` (a human gate).")
        by, via, ctx = confirm_human(ws, f"ACCEPT {len(early)} file(s) changed outside the plan before sprint {n} of "
                                     f"'{c.id}': {a.accept_prior}", a.by,
                                     gate_cmdline(ws, "sprint-start", c.id, str(n), "--accept-prior", a.accept_prior), c,
                                     {"action": "accept-prior", "sprint": n, "files": early, "reason": a.accept_prior,
                                      "checkpoint": cp["sha"]})
        c.state.setdefault("accepted_prior", []).append({"sprint": n, "files": early, "reason": a.accept_prior,
                                                         "checkpoint": cp["sha"], "by": by, "via": via, "at": now(),
                                                         "context": ctx})
        append_ledger(c, "decision", f"accepted {len(early)} file(s) changed before sprint {n}: {a.accept_prior} "
                      f"(by {by}, via {via})")
    old = sprints.get(str(n), {})
    history = list(old.get("history", []))
    snapshot = {k: v for k, v in old.items() if k != "history"}
    if snapshot and (not history or history[-1] != snapshot):
        history.append(snapshot)
    prior = sorted(f.name for f in c.p("reviews").glob(f"sprint-{n:02d}-verification*.md")) if c.p("reviews").is_dir() else []
    sprints[str(n)] = {"status": "active", "started": now(), "stories": b.plan[n], "run": (old.get("run") or 0) + 1,
                       "base_sha": git(ws, "rev-parse", "HEAD"), **({"history": history} if history else {}),
                       **({"prior_verifications": prior} if prior else {})}
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
        mine = {rid for sid in b.plan.get(n, []) if sid in b.stories
                for rid in b.stories[sid].removes + [sc.rsplit(".", 1)[0] for sc in b.stories[sid].covers]}
        rrep = check_removals(c, only_reqs=mine)
        rep.extend(rrep)  # never accepted as a gap: leftover tests of removed behaviour are wrong, not missing
    print(rep.render(f"sign-off sprint {n}"))
    if not rep.ok:
        return 1
    parts = ["signoff", c.id, str(n)] + (["--accept-gaps", a.accept_gaps] if a.accept_gaps else [])
    gf, vf = gates_file(c, n), c.verification_file(n)
    covered_reqs = sorted({sc.rsplit(".", 1)[0] for sid in (b.plan.get(n, []) if b else []) if sid in b.stories
                           for sc in b.stories[sid].covers})
    payload = {"action": "signoff", "sprint": n, "run": s.get("run"), "base_sha": s.get("base_sha"),
               "accepted_gaps": gaps,
               "gates_digest": sha256(gf) if gf.is_file() else None,
               "verification": vf.name if vf.is_file() else None,
               "verification_digest": sha256(vf) if vf.is_file() else None,
               "covered_reqs": covered_reqs, "req_digest": covered_req_digest(c, covered_reqs)}
    by, via, ctx = confirm_human(ws, f"sign off sprint {n} of change '{c.id}'"
                            + (f" ACCEPTING untested scenarios {', '.join(gaps)}" if gaps else ""), a.by,
                                 gate_cmdline(ws, *parts), c, payload)
    s.update({"status": "signed-off", "by": by, "via": via, "at": now(), "context": ctx})
    set_checkpoint(c, f"sprint {n} sign-off")
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
        print(f"{len(gaps)} gap(s) (scenarios without tests, or retired scenarios still referenced): "
              f"{', '.join(gaps)}", file=sys.stderr)
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
    rep.extend(check_approvals(c))
    rep.extend(check_removals(c))
    drift = c.lock_drift()
    if drift:
        rep.err("lock", "design changed after accreditation: " + ", ".join(drift) + "; `amend` and re-accredit first")
    dest = ws.archive / f"{today()}-{c.id}"
    if dest.exists() and not a.dry_run:
        rep.err("archive", f"{dest.relative_to(ws.project)} already exists; rename or remove it first (nothing was changed)")
    for cid, r in sorted(c.state.get("requests", {}).items()):
        if r.get("status") in ("parked", "amend", "applying"):
            rep.err("requests", f"{cid} is still '{r['status']}'; decide or apply it before archiving")
    for dep in c.state.get("depends_on", []):
        if dep in ws.change_ids():
            back = c.id in ws.change(dep).state.get("depends_on", [])
            rep.err("depends_on", f"change '{dep}' must be archived first"
                    + (f" - but '{dep}' also depends on '{c.id}' (a cycle): remove one of the two depends_on" if back else ""))
    base = (c.state.get("accreditation") or {}).get("base", {})
    now_base = base_hashes(c)
    for rid, digest in base.items():
        if now_base.get(rid) != digest:
            rep.err("base drift", f"living [{rid}] changed since accreditation (another change archived?); "
                    f"re-check the delta against the current spec, then `amend` and re-accredit")
    if not rep.ok:
        print(rep.render("archive preconditions"))
        return 1
    plan: Dict[Path, str] = {}
    log = merge_change(c, plan) + promote_adrs(c, plan)
    print("\n".join(log) or "no spec changes")
    if a.dry_run:
        print("dry run: nothing written")
        return 0
    apply_archive(c, plan, dest, len(log))
    print(f"archived to {dest.relative_to(ws.project)}")
    return 0


def apply_archive(c: Change, plan: Dict[Path, str], dest: Path, n_ops: int) -> None:
    """Write the planned files and move the change folder as one unit: on any failure every
    written file is restored (or removed if new) and the change folder stays where it was."""
    old: Dict[Path, Optional[bytes]] = {t: (t.read_bytes() if t.is_file() else None) for t in plan}
    state_before = (c.dir / STATE_FILE).read_bytes()
    written: List[Path] = []
    try:
        for target, text in plan.items():
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_name(target.name + ".specmaker-tmp")
            tmp.write_text(text, encoding="utf-8")
            os.replace(tmp, target)
            written.append(target)
        c.state["phase"] = "archived"
        c.log("archive", f"{n_ops} spec operation(s)")
        c.save()
        c.ws.archive.mkdir(parents=True, exist_ok=True)
        os.rename(c.dir, dest)
    except BaseException as e:
        for target in written:
            if old[target] is None:
                target.unlink()
            else:
                target.write_bytes(old[target])  # type: ignore[arg-type]
        for target in plan:
            try:
                target.with_name(target.name + ".specmaker-tmp").unlink()
            except OSError:
                pass  # no temp file was written there
        if c.dir.is_dir():
            (c.dir / STATE_FILE).write_bytes(state_before)
        die(f"archive failed and was rolled back ({type(e).__name__}: {e}); nothing changed")


def cmd_spec(a: argparse.Namespace) -> int:
    """Show living spec inventory or one requirement (cheap context loading)."""
    ws = Workspace.locate(a.root)
    if a.lint:
        rep = check_living(ws)
        print(rep.render("living specs"))
        return 0 if rep.ok else 1
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
    s = sub.add_parser("set", help="set skip_specs | docs_only | title | track | depends_on (comma list) | human_gates")
    s.add_argument("id")
    s.add_argument("key")
    s.add_argument("value")
    s.add_argument("--by", help="approver when loosening human_gates (chat mode name, signed mode principal)")
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
    s.add_argument("--cr", help="change request(s) decided as 'amend' that this amendment applies, comma-separated")
    s.add_argument("--to", choices=["propose", "ideate"], default="propose",
                   help="phase to return to: ideate when the HLD (goals, scope, shape) changes, else propose")
    s.add_argument("--over-budget", metavar="REASON", help="HUMAN gate: exceed the project.md amendment budget, with a reason")
    s.add_argument("--wording-only", action="store_true",
                   help="HUMAN gate: meaning-neutral wording fix; signed-off sprints are not reopened, IDs must not change")
    s.add_argument("--by", help="name of the human approving a gated amendment (chat mode)")
    s.set_defaults(fn=cmd_amend)
    s = sub.add_parser("cr", help="change requests: add | list | decide")
    crsub = s.add_subparsers(dest="cr_action", required=True)
    x = crsub.add_parser("add", help="record a request (it is parked until triage)")
    x.add_argument("id")
    x.add_argument("--title", required=True)
    x.add_argument("--by", required=True, help="who asked")
    x.add_argument("--reason", help="why they need it")
    x.add_argument("--blocker", action="store_true", help="continuing would build something known to be wrong")
    x.set_defaults(fn=cmd_cr)
    x = crsub.add_parser("list", help="list requests and their status")
    x.add_argument("id")
    x.add_argument("--json", action="store_true")
    x.set_defaults(fn=cmd_cr)
    x = crsub.add_parser("decide", help="HUMAN decision on parked request(s)")
    x.add_argument("id")
    x.add_argument("crs", nargs="*")
    x.add_argument("--outcome", required=True, choices=CR_OUTCOMES)
    x.add_argument("--reason")
    x.add_argument("--class", dest="cls", type=int, choices=[0, 1, 2, 3])
    x.add_argument("--by", help="name of the human deciding (chat mode)")
    x.set_defaults(fn=cmd_cr)
    s = sub.add_parser("impact", help="changed requirements -> scenarios, stories, files, tests, sprints")
    s.add_argument("id")
    s.add_argument("--reqs", help="requirement IDs to analyse (default: changes since the last approval)")
    s.add_argument("--out", help="write markdown here (relative to the change dir)")
    s.set_defaults(fn=cmd_impact)
    s = sub.add_parser("rewind", help="HUMAN gate: discard implementation work back to head, sprint, sprint:N or change start")
    s.add_argument("id")
    s.add_argument("--to", required=True, help="head | sprint | sprint:N | change")
    s.add_argument("--cr", help="change request this rewind serves")
    s.add_argument("--by", help="name of the human approving (chat mode)")
    s.set_defaults(fn=cmd_rewind)
    s = sub.add_parser("sprint-start", help="activate sprint N")
    s.add_argument("id")
    s.add_argument("n", type=int)
    s.add_argument("--accept-prior", metavar="REASON",
                   help="HUMAN gate: accept code changed outside specmaker/ since the last checkpoint")
    s.add_argument("--by", help="approver for --accept-prior (chat mode name, signed mode principal)")
    s.set_defaults(fn=cmd_sprint_start)
    s = sub.add_parser("approve-plan", help="HUMAN gate: approve the backlog tree and sprint plan before implementation")
    s.add_argument("id")
    s.add_argument("--by", help="approver (chat mode name, signed mode principal)")
    s.set_defaults(fn=cmd_approve_plan)
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
    s = sub.add_parser("approvers", help="manage and check the allowed signers for signed human gates")
    asub = s.add_subparsers(dest="approvers_action", required=True)
    x = asub.add_parser("add", help="register an approver's SSH public key")
    x.add_argument("--principal", required=True, help="approver identity used with --by, e.g. alex@example.com")
    x.add_argument("--key", required=True, help="public key file (*.pub); hardware-backed sk keys recommended")
    x.add_argument("--file", help="allowed signers file to write (default: the one in use, else ~/.config/specmaker/)")
    x.set_defaults(fn=cmd_approvers)
    for name, hlp in (("list", "show approvers and their key types"),
                      ("check", "show OpenSSH version, the signers file in use and whether it is protected")):
        x = asub.add_parser(name, help=hlp)
        x.add_argument("--file", help="allowed signers file to inspect")
        x.set_defaults(fn=cmd_approvers)
    s = sub.add_parser("verify", help="verify signed human decisions (CI); exit 1 on any problem")
    s.add_argument("id", nargs="?")
    s.add_argument("--require-signed", action="store_true", help="every human decision must carry a valid signature")
    s.add_argument("--require-hardware", action="store_true", help="every signer must use a hardware-backed (sk-*) key")
    s.add_argument("--allowed-signers", help="allowed signers file to trust (CI: a file the agent cannot change)")
    s.add_argument("--base", help="git ref (e.g. origin/main): fail if any approval file was deleted or modified since")
    s.set_defaults(fn=cmd_verify)
    s = sub.add_parser("spec", help="list living specs, print one requirement by ID, or lint them (--lint)")
    s.add_argument("req", nargs="?")
    s.add_argument("--json", action="store_true")
    s.add_argument("--lint", action="store_true", help="lint all living specs; exit 1 on errors")
    s.set_defaults(fn=cmd_spec)

    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
