#!/usr/bin/env bash
# Install the Ayuna specmaker skills into a project or user skills folder.
# Usage: install.sh [--agent agents|opencode|claude] [--global | --target DIR]
#                   [--link] [--explicit-only] [--force] [--dry-run] [--uninstall]
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/skills"
SKILLS=(specmaker specmaker-ideate specmaker-propose specmaker-accredit specmaker-scrum specmaker-sprint specmaker-retro)

agent="agents"; global=0; target=""; link=0; explicit=0; force=0; dry=0; uninstall=0

usage() {
  sed -n '2,4p' "$0" | sed 's/^# \{0,1\}//'
  cat <<'EOF'

Targets:
  --agent agents     ./.agents/skills          (--global: ~/.agents/skills)   DEFAULT; read by OpenCode, Codex, Cursor, others
  --agent opencode   ./.opencode/skills        (--global: ~/.config/opencode/skills)
  --agent claude     ./.claude/skills          (--global: ~/.claude/skills)
  --target DIR       any directory

Options:
  --link             symlink skill folders instead of copying (updates follow the repo)
  --explicit-only    skills load only when named (@specmaker...), never auto-triggered
  --force            replace existing specmaker skill folders
  --dry-run          print what would happen
  --uninstall        remove the specmaker skill folders from the target
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --agent) agent="${2:-}"; shift 2 ;;
    --global) global=1; shift ;;
    --target) target="${2:-}"; shift 2 ;;
    --link) link=1; shift ;;
    --explicit-only) explicit=1; shift ;;
    --force) force=1; shift ;;
    --dry-run) dry=1; shift ;;
    --uninstall) uninstall=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ -z "$target" ]]; then
  case "$agent:$global" in
    opencode:0) target=".opencode/skills" ;;
    opencode:1) target="${XDG_CONFIG_HOME:-$HOME/.config}/opencode/skills" ;;
    claude:0)   target=".claude/skills" ;;
    claude:1)   target="$HOME/.claude/skills" ;;
    agents:0)   target=".agents/skills" ;;
    agents:1)   target="$HOME/.agents/skills" ;;
    *) echo "unknown agent '$agent' (opencode, claude, agents)" >&2; exit 2 ;;
  esac
fi

if [[ $link -eq 1 && $explicit -eq 1 ]]; then
  echo "--explicit-only edits SKILL.md frontmatter, so it cannot be combined with --link" >&2
  exit 2
fi

run() { if [[ $dry -eq 1 ]]; then echo "  would: $*"; else "$@"; fi; }

if [[ $uninstall -eq 1 ]]; then
  echo "Removing specmaker skills from $target"
  for s in "${SKILLS[@]}"; do
    if [[ -e "$target/$s" || -L "$target/$s" ]]; then run rm -rf "${target:?}/$s"; echo "  removed $s"; fi
  done
  exit 0
fi

command -v python3 >/dev/null 2>&1 || echo "warning: python3 not found; the specmaker helper script needs Python 3.8+" >&2

for s in "${SKILLS[@]}"; do
  if [[ -e "$target/$s" || -L "$target/$s" ]] && [[ $force -eq 0 ]]; then
    echo "error: $target/$s already exists (use --force to replace, or --uninstall first)" >&2
    exit 1
  fi
done

echo "Installing specmaker skills into $target ($([[ $link -eq 1 ]] && echo symlink || echo copy)$([[ $explicit -eq 1 ]] && echo ', explicit-only'))"
run mkdir -p "$target"
for s in "${SKILLS[@]}"; do
  [[ -e "$target/$s" || -L "$target/$s" ]] && run rm -rf "${target:?}/$s"
  if [[ $link -eq 1 ]]; then
    run ln -s "$SRC/$s" "$target/$s"
  else
    run cp -R "$SRC/$s" "$target/$s"
    [[ $dry -eq 0 ]] && find "$target/$s" -name '__pycache__' -type d -prune -exec rm -rf {} +
  fi
  echo "  $s"
done

if [[ $explicit -eq 1 && $dry -eq 0 ]]; then
  python3 - "$target" "${SKILLS[@]}" <<'PY'
import sys, pathlib, re
root = pathlib.Path(sys.argv[1])
for name in sys.argv[2:]:
    p = root / name / "SKILL.md"
    text = p.read_text(encoding="utf-8")
    head, sep, body = text[4:].partition("\n---\n")
    if "disable-model-invocation" not in head:
        head += "\ndisable-model-invocation: true"
    if "opencode/autoinvoke" not in head:
        head = re.sub(r"^metadata:\n", "metadata:\n  opencode/autoinvoke: false\n", head, count=1, flags=re.M)
    p.write_text("---\n" + head + sep + body, encoding="utf-8")
PY
  echo "  marked explicit-only (disable-model-invocation, opencode/autoinvoke: false)"
fi

[[ $dry -eq 0 ]] && chmod +x "$target/specmaker/scripts/specmaker.py" 2>/dev/null || true

cat <<EOF

Done. Next steps:
  1. Start your agent in the project (OpenCode: \`opencode\`).
  2. Say: @specmaker set this project up
  3. Read docs/how-to.md in the specmaker repository for recipes and examples.
Helper script: python3 $target/specmaker/scripts/specmaker.py --help
EOF
