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

COLORS = {"claude-code": "38;5;173", "codex": "38;5;74", "muse-code": "38;5;141", "opencode": "38;5;108"}
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


# ------------------------------------------------------------------------------------------------ the trail, in text
def trail_frame(cwd: str | None = None, color: bool = True, width: int = 72) -> str:
    """The trail panel as text, for a terminal beside an agent: the reasoning in sentences, then the way of working
    with its steps ticked (✓ done, ▶ now, ○ ahead). The same data as the Desktop panel and `athos watch --web`."""
    import textwrap
    from athos import cli, mcp
    c = (lambda code, s: f"\x1b[{code}m{s}{RESET}") if color else (lambda code, s: s)
    sid = cli._current_session(os.path.realpath(cwd or os.getcwd())).get("session_id")
    p = mcp.panel(sid or "__none__")
    es = p["lang"] == "es"
    t = p["trail"]
    out = [c("38;5;173;1", "ATHOS") + "  " + c("2", p["greeting"]), ""]
    piece = t["pieces"][0] if t["pieces"] else None
    if not piece and t["new"]:
        # A task no way of working covers (a first run): the steps it drafts are the way of working to keep.
        out += [c("2", "  ▾ " + ("Cómo lo estoy resolviendo" if es else "How I am going about it")),
                c("2", "    " + ("No hay una forma de trabajar para esto todavía: anoto los pasos para que la guardes."
                                 if es else "No way of working for this yet: I'm noting the steps so you can keep it.")),
                "", c("2", "  " + ("PASOS NUEVOS" if es else "NEW STEPS"))]
        out += ["  " + c("38;5;179", "+ " + textwrap.shorten(n, width - 8, placeholder="…")) for n in t["new"]]
        return "\n".join(out + _no_buttons(c, es, now=False, new=True, width=width))
    if not piece:
        out.append(c("2", "  Acá se ve la trayectoria de la próxima tarea." if es else "  The next task's trail shows here."))
        return "\n".join(out)
    steps = piece["steps"]
    i = next((k for k, s in enumerate(steps) if s["state"] == "now"), -1)
    done = sum(s["state"] == "done" for s in steps)
    think = [("Sigo «%s»." if es else "I'm following «%s».") % piece["title"]]
    if i >= 0:
        think.append(("Paso %d de %d: %s." if es else "Step %d of %d: %s.") % (i + 1, len(steps), steps[i]["label"][0].lower() + steps[i]["label"][1:]))
    elif done == len(steps):
        think.append(("Apliqué los %d pasos." if es else "All %d steps applied.") % done)
    for k in t.get("connectors") or []:
        think.append(("🔒 Los datos personales pasan por %s." if es else "🔒 Personal data goes through %s.") % k["name"] if k["active"]
                     else ("⚠ %s no está activo: sin datos de clientes." if es else "⚠ %s is not running: no client data.") % k["name"])
    out.append(c("2", "  ▾ " + ("Cómo lo estoy resolviendo" if es else "How I am going about it")))
    for line in think:
        out += [c("2", "    " + w) for w in textwrap.wrap(line, width - 4)]
    out += ["", c("1", "  " + piece["title"]), c("2", "  " + ("PASOS" if es else "STEPS"))]
    for s in steps:
        mark, tone = {"done": ("✓", "38;5;71"), "now": ("▶", "38;5;173;1"), "ahead": ("○", "2")}[s["state"]]
        label = textwrap.shorten(s["label"], width - 8, placeholder="…")
        out.append("  " + c(tone, f"{mark} {label}"))
    for n in t["new"]:
        out.append("  " + c("38;5;179", "+ " + textwrap.shorten(n, width - 8, placeholder="…")))
    # No buttons here (Codex, Muse Code): the agent asked in its answer, and a plain "yes" keeps the rule.
    for x in t.get("edits") or []:
        line = (f"✎ Editaste {x['name']}: respondé «sí» para guardar la regla" if es
                else f"✎ You edited {x['name']}: answer \"yes\" to keep the rule")
        out.append("  " + c("38;5;179", textwrap.shorten(line, width - 4, placeholder="…")))
    return "\n".join(out + _no_buttons(c, es, now=i >= 0, new=bool(t["new"]), width=width))


def _no_buttons(c, es: bool, now: bool, new: bool, width: int) -> list[str]:
    """What the panel's buttons do, said as words to type to the agent: a terminal beside Codex or Muse Code has no
    buttons, and the person did not know they could just say it."""
    import textwrap
    tips = []
    if now:
        tips.append("Para cambiar este paso, decíselo al agente: «cambiá este paso: …»." if es
                    else "To change this step, tell the agent: \"change this step: …\".")
    if new:
        tips.append("Para guardar estos pasos: «guardalo como forma de trabajar»." if es
                    else "To keep these steps: \"save this as a way of working\".")
    lines = [c("2", "  " + w) for tip in tips for w in textwrap.wrap(tip, width - 2)]
    return ([""] + lines) if lines else []


def run_trail(cwd: str | None = None) -> int:
    try:
        while True:
            sys.stdout.write(CLEAR + trail_frame(cwd) + "\n")
            sys.stdout.flush()
            time.sleep(1)
    except KeyboardInterrupt:
        return 0
