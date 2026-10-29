#!/bin/sh
# Installs the `athos` command without Claude Code: for Muse Code, Codex or the terminal.
#
#   curl -fsSL https://raw.githubusercontent.com/athos-agent/athos/main/install.sh | sh
#
# Athos goes to ~/.athos/app and the command to ~/.local/bin/athos. Your know-how stays in ~/.athos/know-how, which this
# never touches. Needs Python 3.11+ and nothing else. Run it again to update.
#
#   ATHOS_REF=<branch or tag>   what to install (default main)
#   ATHOS_SOURCE=<folder>       install from a local checkout instead of GitHub
set -eu

REF="${ATHOS_REF:-main}"
APP="${ATHOS_APP:-$HOME/.athos/app}"
BIN="${ATHOS_BIN_DIR:-$HOME/.local/bin}"

# The newest Python 3.11+ on the PATH: macOS's own python3 is often 3.9, with a newer one installed beside it.
PY=""
for p in python3.14 python3.13 python3.12 python3.11 python3; do
  if command -v "$p" > /dev/null 2>&1 && "$p" -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2> /dev/null; then
    PY=$(command -v "$p"); break
  fi
done
[ -n "$PY" ] || { echo "athos needs Python 3.11 or newer (found: $(python3 -V 2>&1 || echo none))" >&2; exit 1; }

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
if [ -n "${ATHOS_SOURCE:-}" ]; then
  mkdir "$tmp/athos" && (cd "$ATHOS_SOURCE" && tar -cf - --exclude .git --exclude '__pycache__' .) | (cd "$tmp/athos" && tar -xf -)
else
  curl -fsSL "https://codeload.github.com/athos-agent/athos/tar.gz/$REF" | tar -xz -C "$tmp"
  mv "$tmp"/athos-* "$tmp/athos"
fi
[ -f "$tmp/athos/bin/athos" ] || { echo "the download does not look like Athos (no bin/athos)" >&2; exit 1; }

rm -rf "$APP"
mkdir -p "$(dirname "$APP")" "$BIN"
mv "$tmp/athos" "$APP"
cat > "$BIN/athos" << EOF
#!/bin/sh
exec "$PY" "$APP/bin/athos" "\$@"
EOF
chmod +x "$BIN/athos"

version=$(sed -n 's/.*"version": *"\([^"]*\)".*/\1/p' "$APP/.claude-plugin/plugin.json" | head -1)
echo "Athos ${version:-} installed: $BIN/athos (Python: $PY)"
case ":$PATH:" in
  *":$BIN:"*) ;;
  *) echo "Add it to your PATH: export PATH=\"$BIN:\$PATH\"" ;;
esac
cat << EOF

Next, in the agents you use:
  athos start                pick your language and profession, with example ways of working
  athos opencode install     the plugin in OpenCode (restart it)
  athos codex install        Athos's hooks in Codex (or: codex plugin marketplace add athos-agent/athos)
  Muse Code:                 muse plugins marketplace add athos https://github.com/athos-agent/athos
                             muse plugins install athos@athos && muse plugins approve athos
  Claude Code:               /plugin install athos --marketplace athos-agent/athos
  athos watch                one bar per agent for this project's know-how
EOF
