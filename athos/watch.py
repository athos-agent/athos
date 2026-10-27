"""`athos watch`: a live panel, beside any agent, of how each one applies the know-how of this project.

    athos watch          refreshes every 2 s; g / c / f mark the last task here (good, corrected, failed), q quits

Codex and Muse Code have no room for Athos in their own footer, so this panel shows there what Claude Code shows in
its footer: one bar per agent for the piece this project used last, filled by its success rate, with and how much
shorter its requests are than the first run's: what the know-how spares you from explaining. Everything comes from the local evaluation log.
"""

from __future__ import annotations

import os
import select
import sys
import time

from athos import eval as ev, paths

COLORS = {"claude-code": "38;5;173", "codex": "38;5;74", "muse-code": "38;5;141"}
DIM, RESET, CLEAR = "\x1b[2m", "\x1b[0m", "\x1b[H\x1b[2J"
KEYS = {"g": "g", "c": "c", "f": "f"}


def frame(project: str, color: bool = True) -> str:
    c = (lambda code, s: f"\x1b[{code}m{s}{RESET}") if color else (lambda code, s: s)
    out = [c("1", f"athos watch · {project}"), ""]
    b = ev.bars(project)
    if b is None:
        out.append("  No task here has used a piece of know-how yet.")
    else:
        out.append(c("2", f"  {b['title']}") + (c("2", f"  (first request {b['baseline_request_chars']} chars)")
                                                if b["baseline_request_chars"] else ""))
        for row in b["agents"]:
            bar, words = ev.bar_line(row)
            out.append(f"  {row['label']:<12}" + c(COLORS.get(row["platform"], "0"), bar) + f"  {words}")
    last = next((t for t in reversed(ev.tasks()) if t.get("project") == project), None)
    if last:
        agent = dict(ev.AGENTS).get(last.get("platform"), last.get("platform"))
        out += ["", c("2", f"  last task: {agent} / {last.get('model', 'unknown')} · {last['result']}")]
        if str(last.get("model", "")).endswith("-contributor"):
            out.append(c("33", "  ⚠ contributor mode: Meta may train on what this task sent. Turn it off in muse → /settings."))
    out += ["", c("2", "  g good · c corrected · f failed (marks the last task here) · q quit")]
    return "\n".join(out)


def _import_codex() -> None:
    from athos.cli import import_other_agents
    import_other_agents()


def run(cwd: str | None = None, interval: float = 2.0, once: bool = False) -> int:
    project = paths.project_of(cwd or os.getcwd())
    if once or not sys.stdin.isatty():
        _import_codex()
        print(frame(project, color=sys.stdout.isatty()))
        return 0
    import termios
    import tty
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    note, last_import = "", 0.0
    try:
        tty.setcbreak(fd)
        while True:
            if time.monotonic() - last_import > 5:
                _import_codex()
                last_import = time.monotonic()
            sys.stdout.write(CLEAR + frame(project) + (f"\n\n  {note}" if note else "") + "\n")
            sys.stdout.flush()
            ready, _, _ = select.select([sys.stdin], [], [], interval)
            if not ready:
                continue
            key = sys.stdin.read(1).lower()
            if key == "q":
                return 0
            if key in KEYS:
                try:
                    tid, res = ev.mark(KEYS[key], None, None, project)
                    note = f"task {tid} marked {res}"
                except (ValueError, LookupError) as e:
                    note = str(e)
    except KeyboardInterrupt:
        return 0
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
        sys.stdout.write(RESET + "\n")
