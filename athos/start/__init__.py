"""`athos start`: a first run for people who don't program.

It asks two things (language and profession), installs a few example pieces of know-how for that profession, and
says in plain words what to do next: open Claude Desktop's Code tab (no terminal needed) or a terminal agent, and try
one concrete request. The example pieces are ways of working, not legal, financial or other professional advice, and every one of them
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
PROFILES = ("law", "sports", "ops", "journalism", "science", "finance", "other")

# The words the person sees. Model-facing text stays in English; what a person reads follows their language.
TEXT = {
    "en": {
        "ask_lang": "Language / Idioma:  1) Español  2) English  [2] ",
        "ask_profile": "What is your work?  1) Law  2) Sports coaching  3) Engineering on call  4) Journalism  "
                       "5) Science  6) Finance and tax advice  7) Something else  [7] ",
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
        "ask_profile": "¿A qué te dedicás?  1) Abogacía  2) Entrenamiento deportivo  3) Guardias de ingeniería  "
                       "4) Periodismo  5) Ciencia  6) Finanzas y asesoría impositiva  7) Otra cosa  [7] ",
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
    ("es", "ops"): ["Se cayó el checkout desde las 14:05, ayudame a encontrar qué pasó (adjunto el log)."],
    ("en", "ops"): ["Checkout has been failing since 14:05, help me find what happened (the log is attached)."],
    ("es", "journalism"): ["Verificá esta pista sobre la licitación del puente antes de que la publique."],
    ("en", "journalism"): ["Check this lead about the bridge contract before I publish it."],
    ("es", "science"): ["Analizá estos resultados del ensayo con mis reglas de limpieza (adjunto los crudos)."],
    ("en", "science"): ["Analyse these test results with my cleaning rules (the raw files are attached)."],
    ("es", "finance"): ["Analizá este fideicomiso inmobiliario para mi cliente (adjunto el prospecto)."],
    ("en", "finance"): ["Analyse this real-estate trust for my client (the prospectus is attached)."],
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


def detect(text: str) -> str | None:
    """The language a text is written in, in clear cases only: "es", "en" or None."""
    ws = re.findall(r"[a-záéíóúñ]+", (text or "").lower())
    es, en = sum(w in ES_WORDS for w in ws), sum(w in EN_WORDS for w in ws)
    return "es" if es >= 2 and es > 2 * en else "en" if en >= 2 and en > 2 * es else None


def note_language(prompt: str) -> None:
    """Without a language chosen with `athos start`, remember the one the person writes in (clear cases only), so
    the lines Athos shows them read in it."""
    c = config()
    if c.get("lang"):
        return
    seen = detect(prompt)
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


# The professions as Desktop's panel offers them on a first use, one button each, in the person's language.
PANEL_ORDER = ("law", "finance", "journalism", "science", "ops", "sports", "other")
NAMES = {
    "en": {"law": "Law", "finance": "Finance and tax", "journalism": "Journalism", "science": "Science",
           "ops": "Engineering on call", "sports": "Sports coaching", "other": "Something else"},
    "es": {"law": "Abogacía", "finance": "Finanzas e impuestos", "journalism": "Periodismo", "science": "Ciencia",
           "ops": "Guardias de ingeniería", "sports": "Entrenamiento deportivo", "other": "Otra cosa"},
}
PANEL_TEXT = {
    "en": {"added": "Added {n} ways of working for {who}: {names}.", "none": TEXT["en"]["none"],
           "skipped": "You already had them: {names}."},
    "es": {"added": "Agregué {n} formas de trabajar para {who}: {names}.", "none": TEXT["es"]["none"],
           "skipped": "Ya las tenías: {names}."},
}


def professions(language: str) -> list[list[str]]:
    return [[p, NAMES["es" if language == "es" else "en"][p]] for p in PANEL_ORDER]


def from_panel(language: str, profile: str) -> dict:
    """A click on a profession in Desktop's panel: the same as `athos start --lang L --profile P`, told in one line,
    with a first request to try."""
    if language not in LANGS or profile not in PROFILES:
        raise ValueError(f"expected lang in {LANGS} and profile in {PROFILES}")
    save_choice(language, profile)
    added, skipped = install(language, profile)
    T = PANEL_TEXT[language]
    if added:
        line = T["added"].format(n=len(added), who=NAMES[language][profile].lower(),
                                 names=", ".join(f"«{p.title}»" for p in added))
    elif skipped:
        line = T["skipped"].format(names=", ".join(skipped))
    else:
        line = T["none"]
    return {"line": line, "added": [p.id for p in added], "try": TRY[(language, profile)][0]}


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
