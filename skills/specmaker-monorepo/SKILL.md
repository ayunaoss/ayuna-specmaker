---
name: specmaker-monorepo
description: >-
  Optional companion to Ayuna specmaker for Nx-based polyglot monorepos built with
  ayunaoss/ayuna-nxtools (@ayunaio/scaffold): scaffold Go, Python and TypeScript
  libraries and applications, shared types (bufgen or typegen), workspace sync,
  per-language checks, Containerfiles and licence files. Use when the user wants to
  set up, extend or maintain such a monorepo, or asks how to scaffold, check or
  containerise a project inside one. Not needed for other repositories.
license: MIT
compatibility: Agent Skills (OpenCode, Claude Code, Codex, Antigravity). Linux, macOS or WSL2 with pnpm and Nx; Go, uv and Node.js per language used. Works with or without the other specmaker skills.
metadata:
  author: ayuna
  version: "0.1.0"
  repository: https://github.com/ayunaoss/ayuna-specmaker
  keywords: monorepo, nx, golang, python, typescript, applications, libraries
---

# Ayuna monorepo

Scaffolding and maintenance rules for Nx monorepos that mix Go, Python and
TypeScript. Run every command from the monorepo root unless stated otherwise.

**Locate this skill** (your harness may not say where it lives):

```bash
R=$(git rev-parse --show-toplevel 2>/dev/null || pwd); for d in "${CLAUDE_SKILL_DIR}/../specmaker-monorepo" "$R/.opencode/skills/specmaker-monorepo" "$R/.agents/skills/specmaker-monorepo" "$R/.claude/skills/specmaker-monorepo" "${XDG_CONFIG_HOME:-$HOME/.config}/opencode/skills/specmaker-monorepo" "$HOME/.agents/skills/specmaker-monorepo" "$HOME/.claude/skills/specmaker-monorepo" "$HOME/.gemini/config/skills/specmaker-monorepo" $(ls -d "${CLAUDE_CODE_PLUGIN_CACHE_DIR:-$HOME/.claude/plugins}"/cache/*/specmaker/*/skills/specmaker-monorepo "$HOME"/.codex/plugins/cache/*/specmaker/*/skills/specmaker-monorepo "$R"/.agents/plugins/*/skills/specmaker-monorepo "$HOME"/.gemini/config/plugins/*/skills/specmaker-monorepo 2>/dev/null | sort -V | tail -1); do [ -f "$d/assets/tools/go_guard/guard.py" ] && { d=$(cd "$d" && pwd); case "$d" in "$R"/*) echo "${d#"$R"/}";; *) echo "$d";; esac; break; }; done
```

Call the printed folder `MR`. The language guides are in `$MR/references/` and
must be followed for every project in that language:

- `golang_project.md`
- `python_project.md`
- `typescript_project.md`

## Parameters: ask once, reuse everywhere

Before the first scaffold command, ask the user for these values, show them
back, and use only approved values. Reuse the same values for every project,
so the monorepo stays consistent.

| Placeholder | Meaning | Example |
|---|---|---|
| `<repo-namespace>` | Namespace shared by all projects | `acme` |
| `<go-module-prefix>` | Go module path prefix shared by all Go projects | `github.com/acme/platform` |
| `<author-name>`, `<author-email>` | Package author metadata | `Alex Chen`, `alex@example.com` |
| `<license-type>` | SPDX identifier, or `Refer to LICENSE file` | `MIT`, `Apache-2.0` |
| `<project-name>` | One project's name (kebab-case) | `billing-api` |
| `<project-summary>` | One-line description; always quote it | `"Billing HTTP API"` |

## Layout

- `bufgen/`: shared protobuf definitions and generated code (`bufgen/go`,
  `bufgen/py`, `bufgen/ts`).
- `apps/` and `libs/`: applications and libraries, grouped by language
  (`apps/go/<name>`, `libs/py/<name>`, `libs/ts/<name>`).

Root workspace files define project membership:

| Language | Workspace file | Check tooling |
|---|---|---|
| Go | `go.work` | `go vet`, golangci-lint |
| TypeScript | `pnpm-workspace.yaml` | `pnpm`, `biome` |
| Python | `pyproject.toml` `[tool.uv.workspace]` | `uv`, `ruff` |

**Keep workspace files in sync with the commands, never by hand.** Both
commands are idempotent.

```bash
pnpm nx workspace-sync && pnpm nx sync     # after adding or generating projects
pnpm nx workspace-purge && pnpm nx sync    # after deleting projects
```

## Shared types: bufgen (recommended) or typegen

Use one of them for types shared across languages, not both. Prefer
**bufgen**.

```bash
# bufgen: creates bufgen/ with buf.yaml, buf.gen.yaml and bufgen/<repo-namespace>/ for .proto files
pnpm nx g @ayunaio/scaffold:bufgen --repoNamespace <repo-namespace> --authorName <author-name> --authorEmail <author-email> --license <license-type> --goModPrefix <go-module-prefix>
# after adding .proto files (e.g. bufgen/<repo-namespace>/v1/greeting.proto): generate Go, Python and TypeScript code
pnpm nx run <repo-namespace>-bufgen:codegen
pnpm nx workspace-sync && pnpm nx sync
# regenerate from scratch when generated code is stale
pnpm nx run <repo-namespace>-bufgen:codepurge && pnpm nx run <repo-namespace>-bufgen:codegen
```

```bash
# typegen: creates the typegen project; model definitions go in typegen/src/main.tsp
pnpm nx g @ayunaio/scaffold:typegen --repoNamespace <repo-namespace> --authorName <author-name> --authorEmail <author-email> --goModPrefix <go-module-prefix>
pnpm nx workspace-sync && pnpm nx sync
# generate libs/go/gotypes, libs/py/<repo-namespace>-pytypes and libs/ts/<repo-namespace>-tstypes
make -C typegen all
pnpm nx workspace-sync && pnpm nx sync
```

## Libraries and applications

Each generator registers the project in its language's workspace file. Run
the sync commands afterwards.

```bash
pnpm nx g @ayunaio/scaffold:go-lib --repoNamespace <repo-namespace> --name <project-name> --modulePrefix <go-module-prefix> --summary <project-summary>
pnpm nx g @ayunaio/scaffold:go-app --repoNamespace <repo-namespace> --name <project-name> --modulePrefix <go-module-prefix> --summary <project-summary>
pnpm nx g @ayunaio/scaffold:py-lib --repoNamespace <repo-namespace> --name <project-name> --authorName <author-name> --authorEmail <author-email> --summary <project-summary>
pnpm nx g @ayunaio/scaffold:py-app --repoNamespace <repo-namespace> --name <project-name> --authorName <author-name> --authorEmail <author-email> --summary <project-summary>
pnpm nx g @ayunaio/scaffold:ts-lib --repoNamespace <repo-namespace> --name <project-name> --authorName <author-name> --authorEmail <author-email> --summary <project-summary>
pnpm nx g @ayunaio/scaffold:ts-app --repoNamespace <repo-namespace> --name <project-name> --authorName <author-name> --authorEmail <author-email> --summary <project-summary>
```

## Configuration and deployment values

These rules apply to every language, and to templates, scripts and Compose files.

- **No deployment-specific values in source:** no service hostnames and ports,
  URLs, database or broker addresses, TLS and secret file paths, cloud
  endpoints or environment names. Examples of what not to write:
  `ayuna-checkpoint:8091`, `http://ayuna-casdoor:8380`,
  `/run/secrets/egress-keys`.
- **Configuration, resolved once:** put each value in an environment variable
  or a configuration file. A local-development default is allowed only when
  it is safe and clearly local. Resolve values once at the boundary (process
  startup, config loader or template renderer) and pass them down. Never
  scatter `os.Getenv`, `process.env` or `os.environ` reads through business
  logic.
- **One name everywhere:** code, templates and deployment manifests use the
  same names, so one override updates all of them. Prefer a small, documented
  set of scalars (`CHECKPOINT_JWKS_URL`, `CASDOOR_URL`, `TLS_CERT_FILE`), plus
  a structured config file for lists and maps.
- **Replaceable endpoints:** local defaults may match the checked-in Compose
  stack, but Kubernetes and production must be able to replace every endpoint
  without code changes. A default never points at a production host and never
  contains a real credential.
- **Fail fast:** validate required configuration at startup, failing with a
  message that names the missing key. Never silently fall back to a hardcoded
  address, and never log secret values.
- **Fixtures stay in tests:** tests and local verification harnesses may use
  fixed loopback fixtures; production code, reusable libraries, rendered
  configs and deployment scripts may not.
- **New dependencies are configured:** a new external dependency adds its
  endpoint to the configuration surface in the same change, with its variable
  documented and the local default and deployment example updated.

## Checks

- Use LSP diagnostics first (definitions, references, hover); use CLI checks
  when the LSP is unavailable or not enough.
- Scope checks to the changed files or their owning project. Avoid whole-repo
  runs unless asked.
- Exact commands are in the language guides. Repository scripts, Nx targets
  and CI take precedence.
- **Go concurrency guard:**
  `python3 $MR/assets/tools/go_guard/guard.py --root .` enforces the
  goroutine rules in `golang_project.md`. Its README covers options and
  tests.

## Containerfiles and licences

- **Containerfiles:** `$MR/assets/oci/go.Containerfile`,
  `py.Containerfile` and `nextjs.Containerfile`. Set the `AYUNA_PROJECT` build
  argument, or replace its `my-service` default. Remove the optional system
  packages marked in each file if the app doesn't need them.
- **Licence files:** `$MR/assets/license/MIT`, `Apache-v2.0` and `EPL-v2.0`.
  Replace `<year-or-year-range>` and `<license-owner-or-group-name>` with
  approved values.

## With the specmaker workflow

When the repository also uses specmaker:

- **propose:** record the shared-types choice (bufgen or typegen) and any
  new language or framework as an ADR. List the workspace files that the
  sync commands will change in the File Boundary.
- **project.md Quality Gates:** use the scoped check commands from the
  language guides (or the Nx targets), plus the Go guard when Go is used.
- **sprint:** scaffold with the generators above; never hand-write what a
  generator produces.
