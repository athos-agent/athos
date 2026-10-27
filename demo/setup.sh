#!/bin/sh
# Prepares a clean, repeatable Athos demo: one tiny Python package that Claude Code and then Codex work on, in the same
# folder, and a demo know-how store of its own, so every take starts from zero and your real store is untouched.
#
#   sh demo/setup.sh            then demo/prep.sh, then follow demo/SCRIPT_GREG.md
#
# Run it again before each take. Everything lives under ~/athos-demo (not /tmp: the report leaves out Codex sessions
# run in temporary folders, as test runs).
set -eu

DEMO="${ATHOS_DEMO:-$HOME/athos-demo}"
rm -rf "$DEMO"
mkdir -p "$DEMO/home"
# Only Codex and Muse Code sessions from now on: earlier rehearsals in the same folder stay out of the demo store.
date -u +%Y-%m-%dT%H:%M:%SZ > "$DEMO/home/import-since"

d="$DEMO/greet"
mkdir -p "$d/greet" "$d/tests"
printf '[project]\nname = "greet"\nversion = "0.1.0"\n' > "$d/pyproject.toml"
printf '__version__ = "0.1.0"\n\n\ndef greet(name):\n    return f"Hello, {name}!"\n' > "$d/greet/__init__.py"
printf 'from greet import greet\n\n\ndef test_greet():\n    assert greet("Ana") == "Hello, Ana!"\n' > "$d/tests/test_greet.py"
printf '# Changelog\n\n## [0.1.0] - 2026-10-01\n### Added\n- greet()\n' > "$d/CHANGELOG.md"
printf '__pycache__/\n.pytest_cache/\n.agents/\n.venv/\n' > "$d/.gitignore"
(cd "$d" && git init -q -b main && git add -A && git -c user.name=demo -c user.email=demo@example.com commit -q -m "greet 0.1.0")

# The tests run with pytest; a venv keeps it out of the system Python.
python3 -m venv "$d/.venv" && "$d/.venv/bin/pip" install -q pytest

# The athos command: the newest installed plugin, or this checkout.
ATHOS_BIN=$(ls -d "$HOME"/.claude/plugins/cache/athos/athos/*/bin/athos 2>/dev/null | sort -V | tail -1)
[ -n "$ATHOS_BIN" ] || ATHOS_BIN="$(cd "$(dirname "$0")/.." && pwd)/bin/athos"

cat <<EOF2
Demo ready in $d.

In every terminal of the demo, first run:

  export ATHOS_HOME=$DEMO/home
  . $d/.venv/bin/activate
  athos() { python3 "$ATHOS_BIN" "\$@"; }

Then sh demo/prep.sh, then follow demo/SCRIPT_GREG.md.
EOF2
