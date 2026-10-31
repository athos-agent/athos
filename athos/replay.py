"""Replaying cases (athos/cases.py) on a model: the person's corrections as tests, their approved answers as references.

    athos test <piece>      each corrected case is a test: the request, answered again with the piece's current
                            version, and a judge call says whether the answer respects what the person corrected
    athos shadow            each good case is a reference: a cheaper model answers the request with the piece, and a
                            judge call says how close it is to the answer the person approved (0-100)

One call answers (system = the piece, user = the request, no tools) and one call judges, on the same backend. The
default is a local model through Ollama; Meta Model API only when the person asks for it (`--backend meta`, or
`athos shadow on --backend meta`). Results are `test_run` and `shadow` events in `<home>/events.jsonl`.

When a piece has been shadowed enough and the cheaper model keeps matching, Athos tells the person once, in plain
words, that they could hand it that work (`handoffs`, `offer_text`).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from athos import cases, eval as ev, paths, store

ANSWER_SYSTEM = """Answer the person's request following their know-how below: it is how they do this kind of task. \
You have no tools and no files: answer in text, as well as the request allows.

# Know-how: {title}

{body}"""

JUDGE_TEST = """A person asked an assistant for something and had to correct its answer. Check whether a new answer \
to the same request already respects that correction.

Request:
{request}

The person's correction:
{correction}

New answer:
{answer}

Reply with only a JSON object: {{"pass": true or false, "reason": "<one short line>"}}"""

JUDGE_SHADOW = """A person approved an answer to their request. Say whether a second answer is equivalent in meaning: \
the same conclusions, decisions and content that matter, even if worded differently.

Request:
{request}

Approved answer:
{approved}

Second answer:
{answer}

Reply with only a JSON object: {{"score": <0-100, how equivalent>, "equivalent": true or false, \
"reason": "<one short line>"}}"""

MIN_SHADOWS = 5            # runs of a piece on one model before Athos suggests anything
WINDOW = 10                # the last runs it looks at
MATCH = 0.9                # how many of them must match
EQUIVALENT_SCORE = 80      # a judge that gives no verdict: this score or more counts as equivalent
LOCK_S = 900               # a background run older than this has died; another may start
LABELS = (("muse-spark", "Muse Spark"), ("muse-wonder", "Muse Wonder"))


# ------------------------------------------------------------------------------------------------ the model
def backend(name: str = "ollama", model: str | None = None):
    """`(platform, model, ask)` for a backend; `ask(model, system, user)` returns the model's text. The only place a
    real model is reached: tests pass their own `ask`."""
    if name == "meta":
        from athos.adapters import meta
        chat, default, platform = meta.chat, meta.DEFAULT_MODEL, "meta"
    else:
        from athos import delegate
        chat, default, platform = delegate.chat, delegate.DEFAULT_MODEL, "local"

    def ask(m: str, system: str, user: str) -> str:
        r = chat(m, [{"role": "system", "content": system}, {"role": "user", "content": user}], tools=False)
        return str((r.get("message") or {}).get("content") or "").strip()
    return platform, model or default, ask


def _json(text: str) -> dict:
    m = re.search(r"\{.*\}", text or "", re.S)
    try:
        d = json.loads(m.group(0)) if m else {}
    except ValueError:
        return {}
    return d if isinstance(d, dict) else {}


def _answer(piece: store.Piece, request: str, model: str, ask) -> str:
    return ask(model, ANSWER_SYSTEM.format(title=piece.title, body=piece.body), request)


def _line(text: str, n: int = 160) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= n else text[:n - 1] + "…"


# ------------------------------------------------------------------------------------------------ tests
def run_tests(piece_id: str, model: str, ask, platform: str = "local") -> dict:
    """Every corrected case of the piece against its current version: pass/fail and one line why, per case."""
    piece = store.get(piece_id)
    if piece is None:
        raise LookupError(f"no piece {piece_id}")
    results = []
    for c in cases.tests(piece_id):
        answer = _answer(piece, c["request"], model, ask)
        verdict = ask(model, "You check answers. Reply with JSON only.",
                      JUDGE_TEST.format(request=c["request"], correction=c["correction"], answer=answer))
        d = _json(verdict)
        ok = bool(d["pass"]) if "pass" in d else bool(re.search(r"\bpass", verdict, re.I)) and \
            not re.search(r"\bfail", verdict, re.I)
        results.append({"task_id": c["task_id"], "request": _line(c["request"], 60), "pass": ok,
                        "reason": _line(d.get("reason") or verdict)})
    out = {"piece": piece_id, "title": piece.title, "version": piece.version, "platform": platform, "model": model,
           "total": len(results), "passed": sum(r["pass"] for r in results), "results": results}
    if results:
        ev.append({"type": "test_run", **{k: v for k, v in out.items() if k != "title"}, "at": ev._iso(ev.now())})
    return out


def render_tests(r: dict, lang: str = "en") -> str:
    es = lang == "es"
    if not r["total"]:
        return (f"«{r['title']}» todavía no tiene correcciones guardadas para volver a probar." if es else
                f"«{r['title']}» has no past corrections to re-check yet.")
    out = [f"«{r['title']}» v{r['version']} · {r['total']} " + ("corrección(es) pasada(s)" if es else
                                                                "past correction(s)") + f" · {r['platform']} / {r['model']}"]
    for x in r["results"]:
        mark = ("✓ pasa " if es else "✓ pass ") if x["pass"] else ("✗ falla" if es else "✗ fail ")
        out.append(f"  {mark}  {x['request']:<60}  {x['reason']}")
    out.append(f"{r['passed']} de {r['total']} respetan la corrección." if es else
               f"{r['passed']} of {r['total']} respect the correction.")
    return "\n".join(out)


# ------------------------------------------------------------------------------------------------ shadow
def shadow_events() -> list[dict]:
    return [e for e in ev.events() if e.get("type") == "shadow"]


def pending(model: str, limit: int | None = None) -> list[dict]:
    """The good cases not yet replayed on this model with the piece as it is now, newest first."""
    done = {(e.get("case"), e.get("piece"), e.get("version"), e.get("model")) for e in shadow_events()}
    out = []
    for c in reversed(cases.references()):
        p = store.get(c["piece"])
        if p and (c["task_id"], p.id, p.version, model) not in done:
            out.append(c)
    return out[:limit] if limit else out


def run_shadow(model: str, ask, platform: str = "local", limit: int | None = None) -> list[dict]:
    """Replay pending good cases on the model and judge each against the approved answer; each one a `shadow` event."""
    out = []
    for c in pending(model, limit):
        piece = store.get(c["piece"])
        answer = _answer(piece, c["request"], model, ask)
        verdict = ask(model, "You compare answers. Reply with JSON only.",
                      JUDGE_SHADOW.format(request=c["request"], approved=c["answer"], answer=answer))
        d = _json(verdict)
        try:
            score = max(0, min(100, int(float(d.get("score")))))
        except (TypeError, ValueError):
            score = None
        same = bool(d["equivalent"]) if "equivalent" in d else (score is not None and score >= EQUIVALENT_SCORE)
        rec = {"type": "shadow", "case": c["task_id"], "piece": piece.id, "version": piece.version,
               "platform": platform, "model": model, "score": score, "equivalent": same,
               "reason": _line(d.get("reason") or verdict), "at": ev._iso(ev.now())}
        ev.append(rec)
        out.append(rec)
    return out


def render_shadow(rs: list[dict], lang: str = "en") -> str:
    es = lang == "es"
    if not rs:
        return "No hay tareas aprobadas pendientes de comparar." if es else "No approved tasks waiting to compare."
    out = []
    for r in rs:
        verdict = ("equivalente" if es else "equivalent") if r["equivalent"] else ("distinta" if es else "different")
        out.append(f"  {r['piece']:<28} {('—' if r['score'] is None else r['score']):>4}  {verdict:<11} {r['reason']}")
    same = sum(r["equivalent"] for r in rs)
    out.append(f"{same} de {len(rs)} equivalentes a lo que aprobaste ({rs[0]['platform']} / {rs[0]['model']})." if es
               else f"{same} of {len(rs)} equivalent to what you approved ({rs[0]['platform']} / {rs[0]['model']}).")
    return "\n".join(out)


# ------------------------------------------------------------------------------------------------ the setting
def settings() -> dict:
    from athos import start
    return start.config().get("shadow") or {}


def set_shadow(on: bool, backend_name: str | None = None, model: str | None = None) -> dict:
    """`athos shadow on|off`: stored with the person's other choices (`<home>/config.json`). Meta only when named."""
    from athos import start
    c = start.config()
    s = dict(c.get("shadow") or {})
    s["on"] = on
    if backend_name:
        s["backend"] = backend_name
        s.pop("model", None)                     # a model of the old backend means nothing on the new one
    if model:
        s["model"] = model
    s.setdefault("backend", "ollama")
    c["shadow"] = s
    start.config_file().parent.mkdir(parents=True, exist_ok=True)
    start.config_file().write_text(json.dumps(c, indent=1) + "\n")
    return s


def _lock():
    return cases.root() / ".shadow.lock"


def running() -> bool:
    try:
        return time.time() - _lock().stat().st_mtime < LOCK_S
    except OSError:
        return False


def take_lock() -> bool:
    if running():
        return False
    _lock().parent.mkdir(parents=True, exist_ok=True)
    _lock().write_text(str(os.getpid()))
    return True


def release_lock() -> None:
    _lock().unlink(missing_ok=True)


def maybe_spawn(athos_cmd: Path, popen=subprocess.Popen) -> bool:
    """Stop hook, with background shadowing on: one approved task waiting is replayed by a detached, low-priority
    `athos shadow --limit 1` that prints nothing. The hook never waits for it."""
    s = settings()
    if not s.get("on"):
        return False
    _platform, model, _ask = backend(s.get("backend", "ollama"), s.get("model"))
    if running() or not pending(model, 1):
        return False
    argv = [sys.executable, str(athos_cmd), "shadow", "--limit", "1", "--quiet",
            "--backend", s.get("backend", "ollama"), "--model", model]
    if os.name == "posix" and Path("/usr/bin/nice").exists():
        argv = ["/usr/bin/nice", "-n", "19", *argv]
    popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
          start_new_session=True, close_fds=True)
    return True


# ------------------------------------------------------------------------------------------------ the suggestion
def label(model: str) -> str:
    return next((name for prefix, name in LABELS if (model or "").startswith(prefix)), model)


def _told() -> set:
    return {(e.get("piece"), e.get("model")) for e in ev.events() if e.get("type") == "handoff_told"}


def handoffs() -> list[dict]:
    """Pieces a cheaper model has proven itself on: at least MIN_SHADOWS runs, and MATCH of the last WINDOW
    equivalent to what the person approved. Each with whether the person was already told."""
    runs: dict[tuple, list[dict]] = {}
    for e in shadow_events():
        runs.setdefault((e.get("piece"), e.get("model")), []).append(e)
    told, out = _told(), []
    for (pid, model), rs in runs.items():
        p = store.get(pid)
        last = rs[-WINDOW:]
        matched = sum(1 for e in last if e.get("equivalent"))
        if p is None or len(rs) < MIN_SHADOWS or matched < MATCH * len(last):
            continue
        out.append({"piece": pid, "title": p.title, "model": model, "label": label(model),
                    "platform": last[-1].get("platform"), "matched": matched, "of": len(last),
                    "told": (pid, model) in told})
    return out


def sentence(h: dict, lang: str = "en") -> str:
    if lang == "es":
        return (f"Tu forma de trabajar «{h['title']}» está firme: {h['label']} coincidió en {h['matched']} de tus "
                f"últimas {h['of']} tareas aprobadas. ¿Querés pasársela a {h['label']}?")
    return (f"Your «{h['title']}» way of working is solid: {h['label']} matched {h['matched']} of your last {h['of']} "
            f"approved tasks. Want to hand it to {h['label']}?")


def offer_text(piece_ids: list[str] | None = None, cmd: str = "athos") -> str:
    """For the context Athos adds (session start, or a prompt that loads the piece): tell the person once. Spent as
    soon as it is given."""
    from athos import start
    lang = start.lang()
    lines = []
    for h in handoffs():
        if h["told"] or (piece_ids is not None and h["piece"] not in piece_ids):
            continue
        flag = " --backend meta" if h["platform"] == "meta" else ""
        lines.append(f"- \"{sentence(h, lang)}\" (if they say yes, such tasks run with "
                     f"`{cmd} delegate {h['piece']} \"<request>\"{flag} --model {h['model']}`)")
        ev.append({"type": "handoff_told", "piece": h["piece"], "model": h["model"], "at": ev._iso(ev.now())})
    if not lines:
        return ""
    return ("**Tell the person once**, in one line at the end of your reply, in their language and in plain words "
            "(this is Athos's own news, measured on their approved tasks):\n" + "\n".join(lines))
