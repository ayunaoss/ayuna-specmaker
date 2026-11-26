"""Go concurrency guard for Ayuna projects.

Rules (see ``references/golang_project.md`` in this skill):

* non-test Go code must not start a bare ``go`` statement; use conc.WaitGroup
  or conc/pool. A single start/stop lifecycle goroutine may opt out with a
  ``//go:allow-bare-go: <reason>`` comment on the same line or the line above.
* no Go code (including tests) may use ``sync.WaitGroup`` or ``errgroup``;
  use the conc equivalents.
* generated files are skipped.

Run it from the target repository root, or pass ``--root``. The default scan
roots are the Ayuna monorepo layout; pass ``--roots`` for another layout.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOTS = ("apps", "libs", "bufgen")
SKIP_DIRS = {"node_modules", ".venv", "vendor"}

BARE_GO = re.compile(r"^\s*go\s+(?:func\b|[A-Za-z_][A-Za-z0-9_.]*\s*\()")
WAITGROUP = re.compile(r"\bsync\.WaitGroup\b")
ERRGROUP = re.compile(r"\berrgroup\.")
ALLOW_BARE_GO = "//go:allow-bare-go"
ALLOW_WITH_REASON = re.compile(r"//go:allow-bare-go\b\s*:?\s*\S")

BARE_GO_MESSAGE = (
    "bare go statement: use conc.WaitGroup or conc/pool; add "
    "'//go:allow-bare-go: <reason>' (same line or the line above) only for a single "
    "start/stop lifecycle goroutine"
)
WAITGROUP_MESSAGE = "sync.WaitGroup: use conc.WaitGroup"
ERRGROUP_MESSAGE = "errgroup: use conc/pool with errors"


@dataclass(frozen=True)
class Problem:
    path: Path
    line: int
    message: str


def _code(line: str, state: str) -> tuple[str, str]:
    """Return one line's code with comments and string contents removed, plus the carry-over state.

    ``state`` is "" (code), "block" (inside /* */) or "raw" (inside a `raw string`). Strings are
    blanked so that text such as "/*" or "go func()" inside them is neither code nor a comment."""
    out: list[str] = []
    i, n = 0, len(line)
    while i < n:
        if state == "block":
            end = line.find("*/", i)
            if end == -1:
                return "".join(out), "block"
            i, state = end + 2, ""
            out.append(" ")
            continue
        if state == "raw":
            end = line.find("`", i)
            if end == -1:
                return "".join(out), "raw"
            i, state = end + 1, ""
            out.append('""')
            continue
        if line.startswith("//", i):
            break
        if line.startswith("/*", i):
            i, state = i + 2, "block"
            continue
        ch = line[i]
        if ch == "`":
            i, state = i + 1, "raw"
            continue
        if ch in "\"'":
            i += 1
            while i < n and line[i] != ch:
                i += 2 if line[i] == "\\" else 1
            i += 1
            out.append('""')
            continue
        out.append(ch)
        i += 1
    return "".join(out), state


def _is_generated(text: str) -> bool:
    header = "\n".join(text.splitlines()[:10])
    return "Code generated" in header and "DO NOT EDIT" in header


def scan_file(path: Path) -> list[Problem]:
    text = path.read_text(encoding="utf-8")
    if _is_generated(text):
        return []

    is_test = path.name.endswith("_test.go")
    problems: list[Problem] = []
    state = ""
    lines = text.splitlines()

    for number, line in enumerate(lines, start=1):
        code, state = _code(line, state)
        if not is_test and BARE_GO.search(code):
            previous = lines[number - 2] if number > 1 else ""
            allowed = ALLOW_WITH_REASON.search(line) or (
                previous.strip().startswith("//") and ALLOW_WITH_REASON.search(previous)
            )
            if not allowed:
                problems.append(Problem(path, number, BARE_GO_MESSAGE))
        if WAITGROUP.search(code):
            problems.append(Problem(path, number, WAITGROUP_MESSAGE))
        if ERRGROUP.search(code):
            problems.append(Problem(path, number, ERRGROUP_MESSAGE))

    return problems


def scan_root(root: Path, roots: tuple[str, ...] = ROOTS) -> list[Problem]:
    problems: list[Problem] = []
    for name in roots:
        base = root / name
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.go")):
            if any(part in SKIP_DIRS for part in path.parts):
                continue
            problems.extend(scan_file(path))
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="repository root (defaults to the current directory)",
    )
    parser.add_argument(
        "--roots",
        default=",".join(ROOTS),
        help="comma-separated roots to scan (default: apps,libs,bufgen)",
    )
    args = parser.parse_args(argv)

    roots = tuple(root.strip() for root in args.roots.split(",") if root.strip())
    problems = scan_root(args.root, roots)
    for problem in problems:
        try:
            shown = problem.path.relative_to(args.root)
        except ValueError:
            shown = problem.path
        print(f"{shown}:{problem.line}: {problem.message}")

    if problems:
        print(f"go guard: {len(problems)} violation(s)", file=sys.stderr)
        return 1

    print("go guard: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
