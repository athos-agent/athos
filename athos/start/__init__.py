"""`athos start`: a first run for people who don't program.

It asks two things (language and profession), installs a few example pieces of know-how for that profession, and
says in plain words what to do next: open Claude Desktop's Code tab (no terminal needed) or a terminal agent, and try
one concrete request. The example pieces are ways of working, not legal or medical advice, and every one of them
leaves the professional decisions to the person.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from athos import paths, store

STARTERS = Path(__file__).resolve().parents[1] / "starters"
LANGS = ("es", "en")
PROFILES = ("law", "sports", "other")

# The words the person sees. Model-facing text stays in English; what a person reads follows their language.
TEXT = {
    "en": {
        "ask_lang": "Language / Idioma:  1) Español  2) English  [2] ",
        "ask_profile": "What is your work?  1) Law  2) Sports coaching  3) Something else  [3] ",
        "installed": "Added {n} example ways of working for your profession:",
        "skipped": "(already there: {names})",
        "none": "No examples for this profession yet: Athos learns your ways of working as you use it.",
        "where": "They are plain files you own, in {dir}. Open them with any editor and change them to how you work.",
        "next": "Next:",
        "desktop": "1. Without a terminal: open Claude Desktop, go to the Code tab, choose a folder with your documents, "
                   "and install Athos there with:  /plugin install athos --marketplace athos-agent/athos",
        "terminal": "2. From a terminal: run `claude`, `codex` or `muse` inside that folder; Athos works the same.",
        "try": "Try asking, in your own words:",
        "privacy": "Your ways of working never leave this machine. The AI model you use (Claude, Codex, Meta's Muse) "
                   "does see the documents you show it: anonymise client or personal data, or use a local model "
                   "(`athos delegate`).",
        "after": "After each task, mark how it went (Good / Corrected / Failed): Athos learns which ways of working "
                 "help you, and improves them with you.",
        "lang_saved": "Language: English. Change it any time with `athos start`.",
        "hello": "Athos keeps how you work with AI, in your words, on your machine.\n\nNew here? Run:  athos start\n"
                 "Your ways of working:  athos list\nEverything else:  athos --help",
    },
    "es": {
        "ask_lang": "Language / Idioma:  1) Español  2) English  [1] ",
        "ask_profile": "¿A qué te dedicás?  1) Abogacía  2) Entrenamiento deportivo  3) Otra cosa  [3] ",
        "installed": "Agregué {n} formas de trabajar de ejemplo para tu profesión:",
        "skipped": "(ya estaban: {names})",
        "none": "Todavía no hay ejemplos para esta profesión: Athos aprende tus formas de trabajar mientras lo usás.",
        "where": "Son archivos tuyos, en {dir}. Abrilos con cualquier editor y cambialos a tu manera de trabajar.",
        "next": "Cómo seguir:",
        "desktop": "1. Sin terminal: abrí Claude Desktop, andá a la pestaña Code, elegí una carpeta con tus documentos "
                   "e instalá Athos ahí con:  /plugin install athos --marketplace athos-agent/athos",
        "terminal": "2. Desde una terminal: corré `claude`, `codex` o `muse` dentro de esa carpeta; Athos funciona igual.",
        "try": "Probá pedir, con tus palabras:",
        "privacy": "Tus formas de trabajar nunca salen de esta máquina. El modelo de IA que uses (Claude, Codex, Muse "
                   "de Meta) sí ve los documentos que le muestres: anonimizá los datos de clientes o datos personales, o "
                   "usá un modelo local (`athos delegate`).",
        "after": "Después de cada tarea, marcá cómo salió (Salió bien / Lo corregí / Falló): Athos aprende qué formas "
                 "de trabajar te sirven y las mejora con vos.",
        "lang_saved": "Idioma: español. Lo cambiás cuando quieras con `athos start`.",
        "hello": "Athos guarda cómo trabajás con la IA, con tus palabras, en tu máquina.\n\n¿Primera vez? Corré:  "
                 "athos start\nTus formas de trabajar:  athos list\nTodo lo demás:  athos --help",
    },
}

TRY = {
    ("es", "law"): ["Ayudame a armar el argumento de esta contestación de demanda (adjunto el escrito de la otra parte).",
                    "Revisá este contrato de locación con mi checklist y devolveme las observaciones."],
    ("en", "law"): ["Help me build the argument of this answer to the complaint (the other side's filing is attached).",
                    "Review this lease against my checklist and give me the comments."],
    ("es", "sports"): ["Planificá la semana que viene de este atleta con mis reglas (adjunto su registro de sesiones).",
                       "Escribí el informe post partido con estas estadísticas."],
    ("en", "sports"): ["Plan next week for this athlete with my rules (their session log is attached).",
                       "Write the post-match report from these stats."],
    ("es", "other"): ["Hacé el informe semanal como lo hago yo: te explico los pasos la primera vez."],
    ("en", "other"): ["Write the weekly report the way I do it: I'll explain the steps the first time."],
}


def config_file() -> Path:
    return paths.home() / "config.json"


def config() -> dict:
    try:
        return json.loads(config_file().read_text())
    except (OSError, ValueError):
        return {}


def lang() -> str:
    """The person's language for what Athos shows them: ATHOS_LANG, then `athos start`'s choice, then the language
    they write their requests in, then English."""
    c = config()
    v = (os.environ.get("ATHOS_LANG") or c.get("lang") or c.get("lang_seen") or "en").lower()[:2]
    return v if v in LANGS else "en"


ES_WORDS = set("que de la el en los las por para con una como esta este pero hay ahora luego puedes hace hacer "
               "tengo quiero dime revisa revisá arranca mergea también sí cómo qué está están".split())
EN_WORDS = set("the and to of is are you can this that with what how please now then could would should".split())


def note_language(prompt: str) -> None:
    """Without a language chosen with `athos start`, remember the one the person writes in (clear cases only), so
    the lines Athos shows them read in it."""
    c = config()
    if c.get("lang"):
        return
    ws = re.findall(r"[a-záéíóúñ]+", (prompt or "").lower())
    es, en = sum(w in ES_WORDS for w in ws), sum(w in EN_WORDS for w in ws)
    seen = "es" if es >= 2 and es > 2 * en else "en" if en >= 2 and en > 2 * es else None
    if seen and seen != c.get("lang_seen"):
        c["lang_seen"] = seen
        config_file().parent.mkdir(parents=True, exist_ok=True)
        config_file().write_text(json.dumps(c, indent=1) + "\n")


def t(key: str, **kw) -> str:
    return TEXT[lang()][key].format(**kw)


def starters(language: str, profile: str) -> list[Path]:
    return sorted((STARTERS / language / profile).glob("*.md"))


def install(language: str, profile: str) -> tuple[list[store.Piece], list[str]]:
    """Add the profession's example pieces to the store, as the person's own (version 1). Pieces already there are
    left as they are: the person may have changed them."""
    added, skipped = [], []
    for f in starters(language, profile):
        meta, body = store.parse_frontmatter(f.read_text())
        if store.get(meta["id"]):
            skipped.append(meta["id"])
            continue
        added.append(store.create(meta["title"], meta["when"], body.strip() + "\n",
                                  origin={"platform": "athos", "model": "starter"}, piece_id=meta["id"]))
    if added:
        from athos import wiki
        try:
            wiki.rebuild()
        except OSError:
            pass
    return added, skipped


def save_choice(language: str, profile: str) -> None:
    c = config()
    c.update(lang=language, profile=profile)
    config_file().parent.mkdir(parents=True, exist_ok=True)
    config_file().write_text(json.dumps(c, indent=1) + "\n")


def welcome(language: str, profile: str, added: list[store.Piece], skipped: list[str]) -> str:
    T = TEXT[language]
    out = [T["lang_saved"], ""]
    if added:
        out.append(T["installed"].format(n=len(added)))
        out += [f"  · {p.title}" for p in added]
    if skipped:
        out.append(T["skipped"].format(names=", ".join(skipped)))
    if not added and not skipped:
        out.append(T["none"])
    out += ["", T["where"].format(dir=paths.know_how()), "", T["next"], T["desktop"], T["terminal"], "", T["try"]]
    out += [f"  «{x}»" for x in TRY[(language, profile)]]
    out += ["", T["privacy"], "", T["after"]]
    return "\n".join(out)
