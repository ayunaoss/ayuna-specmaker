# Go concurrency guard

This asset enforces the Go concurrency rules in
`references/golang_project.md`:

- non-test Go code must not use a bare `go` statement; use `conc.WaitGroup` or
  `conc/pool`. A single start/stop lifecycle goroutine may opt out with
  `//go:allow-bare-go: <reason>` on the same line or the line directly above.
  The directive covers only that statement;
- no Go code, including `_test.go`, may use `sync.WaitGroup` or `errgroup`;
- generated files are skipped; comments and string contents never count as code.

Run it from the target repository root (`$MR` is this skill's folder, see
SKILL.md). It needs only Python 3.8+:

```sh
python3 $MR/assets/tools/go_guard/guard.py --root .
```

Pass other scan roots for another layout:

```sh
python3 $MR/assets/tools/go_guard/guard.py --root . --roots services,pkg
```

Run the guard's own tests with `pytest $MR/assets/tools/go_guard`. The
specmaker repository also runs them in its test suite, without pytest.

The default scan roots are the Ayuna monorepo layout (`apps`, `libs`, `bufgen`).
Override them with `--roots` for another layout.
