#!/usr/bin/env sh
# Sets up the one-folder Athos demo from nothing: a tiny Python package, `greet`, that Claude Code and then Codex both
# work on in the same folder, plus a know-how store of its own, so each take starts empty and the real ~/.athos is
# never involved. Usage:   sh demo/setup.sh   then demo/prep.sh, then follow demo/SCRIPT_GREG.md
# Run it before every take: it deletes the previous demo first. It all lives in ~/athos-demo (ATHOS_DEMO to move it)
# and deliberately not in /tmp, because the report treats Codex sessions run in temporary folders as test runs and
# leaves them out.
set -eu

demo_root="${ATHOS_DEMO:-$HOME/athos-demo}"
project="$demo_root/greet"

fresh_store() {
  rm -rf "$demo_root"
  mkdir -p "$demo_root/home"
  # Only Codex and Muse Code sessions from now on: earlier rehearsals in the same folder stay out of the demo store.
  date -u +%Y-%m-%dT%H:%M:%SZ > "$demo_root/home/import-since"
}

# greet 0.1.0: one function, one test, a changelog and the version in two places, committed as the starting point.
write_package() {
  mkdir -p "$project/greet" "$project/tests"
  cat > "$project/pyproject.toml" <<'TOML'
[project]
name = "greet"
version = "0.1.0"
TOML
  cat > "$project/greet/__init__.py" <<'PY'
__version__ = "0.1.0"


def greet(name):
    return f"Hello, {name}!"
PY
  cat > "$project/tests/test_greet.py" <<'PY'
from greet import greet


def test_greet():
    assert greet("Ana") == "Hello, Ana!"
PY
  cat > "$project/CHANGELOG.md" <<'MD'
# Changelog

## [0.1.0] - 2026-10-01
### Added
- greet()
MD
  cat > "$project/.gitignore" <<'IGNORE'
__pycache__/
.pytest_cache/
.agents/
.venv/
IGNORE
  git -C "$project" init -q -b main
  git -C "$project" add .
  git -C "$project" -c user.name=demo -c user.email=demo@example.com commit -q -m "greet 0.1.0"
}

# pytest runs the package's tests, from a venv of the project's own so the system Python stays as it is.
make_venv() {
  python3 -m venv "$project/.venv"
  "$project/.venv/bin/pip" install -q pytest
}

# Which `athos` the demo uses: the newest version of the installed plugin when there is one, else this checkout.
pick_athos() {
  newest=$(ls -d "$HOME"/.claude/plugins/cache/athos/athos/*/bin/athos 2>/dev/null | sort -V | tail -1)
  if [ -n "$newest" ]; then
    echo "$newest"
  else
    echo "$(cd "$(dirname "$0")/.." && pwd)/bin/athos"
  fi
}

fresh_store
write_package
make_venv
athos_bin=$(pick_athos)

cat <<EOF
Demo ready in $project.

Before anything else, run these in each terminal you will use in the demo:

  export ATHOS_HOME=$demo_root/home
  . $project/.venv/bin/activate
  athos() { python3 "$athos_bin" "\$@"; }

Then sh demo/prep.sh, then follow demo/SCRIPT_GREG.md.
EOF
