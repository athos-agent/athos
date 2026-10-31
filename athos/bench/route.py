"""`athos bench route`: how well the router picks the way of working a request needs, measured before changing it.

Cases (`route_cases.json`, public and fictional) are `request → the piece it should load, or none`. Each run builds
a throwaway store from the starters (both languages, or one language for the cross-language run), asks
`load.relevant` exactly as the prompt hook does, and counts: hit@1 (the first piece loaded is the expected one),
missed (nothing loaded), wrong loads (a piece loaded that the request didn't call for) and, for the requests that
need nothing ("what time is it"), how often nothing loaded. `--scale N` pads the store to N pages with generated
pages from other trades that borrow the starters' words, to see the false loads a large store brings.
`--from-store` replays the person's own tasks marked good against their real store, read-only, aggregates only.
"""

from __future__ import annotations

import contextlib
import json
import os
import random
import statistics
import tempfile
import time
import unicodedata
from pathlib import Path

from athos import eval as ev, store

CASES = Path(__file__).parent / "route_cases.json"
SEED = 7


def load_cases() -> dict:
    return json.loads(CASES.read_text())


def starter_pages(language: str) -> list[tuple[str, str, str, str]]:
    """(id, title, when, body) of every starter in one language."""
    from athos import start
    out = []
    for f in sorted((start.STARTERS / language).glob("*/*.md")):
        meta, body = store.parse_frontmatter(f.read_text())
        out.append((meta["id"], meta["title"], meta["when"], body.strip() + "\n"))
    return out


# --- distractors: other trades' ways of working, worded like the starters (review, plan, analyse, verify, report…)
TRADES = {
    # trade: (en: a thing, a report, a plan, some data) / (es: the same, with their articles)
    "marketing": (("campaign brief", "campaign results report", "launch calendar", "ad performance numbers"),
                  ("el brief de campaña", "el informe de resultados de la campaña", "el calendario de lanzamiento",
                   "los números de rendimiento de los anuncios")),
    "hr": (("job offer letter", "quarterly hiring report", "onboarding week", "employee survey answers"),
           ("la carta de oferta laboral", "el informe trimestral de contrataciones", "la semana de incorporación",
            "las respuestas de la encuesta a empleados")),
    "teaching": (("lesson plan", "term report card", "unit for next week", "quiz scores"),
                 ("el plan de clase", "el boletín del trimestre", "la unidad de la semana próxima",
                  "las notas de las pruebas")),
    "architecture": (("floor plan", "site visit report", "construction schedule", "load calculations"),
                     ("el plano de planta", "el informe de visita de obra", "el cronograma de obra",
                      "los cálculos de carga")),
    "logistics": (("shipping manifest", "delivery delays report", "route plan for the week", "warehouse stock counts"),
                  ("el manifiesto de carga", "el informe de demoras de entrega", "el plan de rutas de la semana",
                   "los conteos de stock del depósito")),
    "support": (("customer ticket", "weekly support report", "on-call rota", "satisfaction survey scores"),
                ("el ticket de un cliente", "el informe semanal de soporte", "la rotación de guardias",
                 "los puntajes de la encuesta de satisfacción")),
    "realty": (("listing description", "open house report", "viewing schedule", "comparable sale prices"),
               ("la descripción del aviso", "el informe de la visita abierta", "la agenda de visitas",
                "los precios de ventas comparables")),
    "translation": (("translated manual", "terminology report", "delivery plan for the book", "glossary entries"),
                    ("el manual traducido", "el informe de terminología", "el plan de entregas del libro",
                     "las entradas del glosario")),
    "design": (("logo proposal", "design review notes", "sprint of mockups", "usability test results"),
               ("la propuesta de logo", "las notas de la revisión de diseño", "el sprint de maquetas",
                "los resultados de las pruebas de usabilidad")),
    "procurement": (("purchase order", "supplier evaluation report", "buying calendar", "price quotes"),
                    ("la orden de compra", "el informe de evaluación de proveedores", "el calendario de compras",
                     "las cotizaciones de precios")),
    "grants": (("grant application", "impact report for the donor", "proposal timeline", "beneficiary numbers"),
               ("la solicitud de subsidio", "el informe de impacto para el donante", "el cronograma de la propuesta",
                "los números de beneficiarios")),
    "events": (("event run sheet", "post-event report", "conference week", "attendee registrations"),
               ("el guion del evento", "el informe posterior al evento", "la semana del congreso",
                "las inscripciones de asistentes")),
    "kitchen": (("menu", "food cost report", "prep schedule for the week", "supplier deliveries"),
                ("el menú", "el informe de costo de alimentos", "el plan de producción de la semana",
                 "las entregas de proveedores")),
    "farming": (("planting plan", "harvest report", "irrigation week", "soil sample readings"),
                ("el plan de siembra", "el informe de cosecha", "la semana de riego",
                 "las lecturas de muestras de suelo")),
    "retail": (("shop window layout", "monthly sales report", "staff rota", "till receipts"),
               ("el armado de la vidriera", "el informe mensual de ventas", "los turnos del personal",
                "los tickets de caja")),
    "hotel": (("guest complaint", "occupancy report", "housekeeping week", "booking numbers"),
              ("la queja de un huésped", "el informe de ocupación", "la semana de limpieza", "los números de reservas")),
    "music": (("mix of the single", "tour report", "recording session week", "streaming numbers"),
              ("la mezcla del single", "el informe de la gira", "la semana de sesiones de grabación",
               "los números de reproducciones")),
    "film": (("shooting script", "daily production report", "shooting week", "budget actuals"),
             ("el guion técnico", "el parte diario de producción", "la semana de rodaje",
              "los costos reales del presupuesto")),
    "archives": (("donated collection", "cataloguing report", "digitisation plan", "inventory records"),
                 ("la colección donada", "el informe de catalogación", "el plan de digitalización",
                  "los registros del inventario")),
    "product": (("feature spec", "release notes", "roadmap quarter", "usage analytics"),
                ("la especificación de una función", "las notas de la versión", "el trimestre del roadmap",
                 "las métricas de uso")),
    "travel": (("group itinerary", "trip feedback report", "travel week", "fare quotes"),
               ("el itinerario del grupo", "el informe de opiniones del viaje", "la semana de viaje",
                "las cotizaciones de pasajes")),
    "nonprofit": (("volunteer handbook", "annual activity report", "fundraising month", "donation records"),
                  ("el manual del voluntario", "la memoria anual de actividades", "el mes de recaudación",
                   "los registros de donaciones")),
}
TASKS = {
    "en": [("Review the {o} against your checklist", "reviewing or commenting the {o} before it goes out or is signed off"),
           ("Write the {r} in my format", "after the period closes, preparing the {r} from the {d} and notes"),
           ("Plan the {p} with my rules", "planning the {p} from the calendar, availability and last month's {d}"),
           ("Analyse the {d} so it can be repeated", "analysing the {d} for a decision or a report, reproducibly"),
           ("Verify the {d} before sending anything", "checking the {d} against their source before they reach anyone"),
           ("Triage a problem with the {o}", "the {o} is late, wrong or rejected and the cause must be found first"),
           ("Prepare the {o} for its audience", "preparing the {o} to convince a manager, a client or a board"),
           ("Compare two versions of the {o}", "two drafts of the {o} differ and the changes must be listed")],
    "es": [("Revisar {o} con tu checklist", "revisar o comentar {o} antes de que salga o se apruebe"),
           ("Escribir {r} en mi formato", "al cerrar el período, preparar {r} a partir de {d} y las notas"),
           ("Planificar {p} con mis reglas", "planificar {p} a partir del calendario, la disponibilidad y {d}"),
           ("Analizar {d} de forma reproducible", "analizar {d} para una decisión o un informe, de forma reproducible"),
           ("Verificar {d} antes de enviar nada", "chequear {d} contra su fuente antes de que le lleguen a alguien"),
           ("Atender un problema con {o}", "{o} está atrasado, mal o rechazado y hay que encontrar la causa primero"),
           ("Preparar {o} para su auditorio", "preparar {o} para convencer a un gerente, un cliente o un directorio"),
           ("Comparar dos versiones de {o}", "hay dos borradores de {o} y hay que listar los cambios")],
}
STEPS = {"en": ("before starting", "with the material at hand", "the work is ready"),
         "es": ("antes de empezar", "con el material a mano", "el trabajo está listo")}


def _contract(text: str) -> str:
    """Spanish contractions after filling a template ("de el" is "del", "a el" is "al")."""
    return text.replace(" de el ", " del ").replace(" a el ", " al ")


def _ascii(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()


def distractors(n: int, seed: int = SEED) -> list[tuple[str, str, str, str]]:
    """`n` plausible pages from other trades (same seed, same pages): titles and "when"s shaped like the starters'
    so they share their verbs, with three statements each, like a real page."""
    combos = [(trade, lang, i) for trade in TRADES for lang in ("en", "es") for i in range(len(TASKS[lang]))]
    random.Random(seed).shuffle(combos)
    out = []
    for trade, lang, i in combos[:max(0, n)]:
        o, r, p, d = TRADES[trade][0 if lang == "en" else 1]
        title, when = (_contract(s.format(o=o, r=r, p=p, d=d)) for s in TASKS[lang][i])
        pid = store.slugify(_ascii(f"{title} {trade}"))
        body = "\n".join(f"## #step_{k + 1}\n**When:** {w}.\n**Do:** {title.lower()}, step {k + 1}.\n"
                         for k, w in enumerate(STEPS[lang]))
        out.append((pid, title, when, body))
    return out


@contextlib.contextmanager
def throwaway_store(pages: list[tuple[str, str, str, str]], config: dict | None = None):
    """A temporary Athos home holding only these pages (and this config), so the real store is never read or
    touched; the previous ATHOS_HOME comes back after."""
    old = os.environ.get("ATHOS_HOME")
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["ATHOS_HOME"] = tmp
        try:
            for pid, title, when, body in pages:
                p = store.Piece(id=pid, title=title, when=when, body=body, created=store.today(),
                                last_used=store.today(), origin={"platform": "athos", "model": "bench"})
                store._write(p)
            if config:
                (Path(tmp) / "config.json").write_text(json.dumps(config))
            yield Path(tmp)
        finally:
            if old is None:
                os.environ.pop("ATHOS_HOME", None)
            else:
                os.environ["ATHOS_HOME"] = old


def _ids(topics: dict, names: list[str], langs: tuple[str, ...]) -> set[str]:
    return {topics[t][lang] for t in names for lang in langs if t in topics}


def evaluate(cases: list[dict], topics: dict, langs: tuple[str, ...], meaning=None) -> dict:
    """Run each request through the router as the prompt hook does (the store read included in the time) and
    count what loaded against what was expected."""
    from athos import load, wiki
    out = {"n": 0, "positives": 0, "hit1": 0, "missed": 0, "wrong": 0, "negatives": 0, "none_ok": 0, "ms": [],
           "by_kind": {}}
    for c in cases:
        t0 = time.perf_counter()
        pieces = store.all_pieces()
        loaded = load.relevant(c["request"], pieces, meaning=meaning)
        out["ms"].append((time.perf_counter() - t0) * 1000)
        ids = [p.id for p in loaded]
        out["n"] += 1
        k = out["by_kind"].setdefault(c["kind"], {"n": 0, "ok": 0, "wrong": 0})
        k["n"] += 1
        if c["topic"] is None:
            out["negatives"] += 1
            out["none_ok"] += not ids
            out["wrong"] += bool(ids)
            k["ok"] += not ids
            k["wrong"] += bool(ids)
            continue
        expect = _ids(topics, [c["topic"]], langs)
        fine = expect | _ids(topics, topics[c["topic"]].get("accept", []), langs)
        # The pages a fine piece hands over to (**Calls:** / **If:**) come along by design: not a wrong load.
        fine |= {call["page"] for p in loaded if p.id in fine for s in wiki.statements(p) for call in s.calls}
        out["positives"] += 1
        hit = bool(ids) and ids[0] in expect
        out["hit1"] += hit
        out["missed"] += not ids
        bad = any(i not in fine for i in ids)
        out["wrong"] += bad
        k["ok"] += hit
        k["wrong"] += bad
    ms = out.pop("ms")
    out["ms_mean"] = round(statistics.mean(ms), 2) if ms else 0.0
    out["ms_p95"] = round(sorted(ms)[int(0.95 * (len(ms) - 1))], 2) if ms else 0.0
    return out


def _hybrid_config(model: str | None) -> dict:
    from athos.load import embed
    return {"embed": {"on": True, "model": model or embed.DEFAULT_MODEL}}


def _warm(meaning_model: str | None) -> None:
    """Build the meaning index of the throwaway store before timing, as `athos embed on` does for the person."""
    from athos.load import embed
    embed.refresh(store.all_pieces(), model=meaning_model or embed.DEFAULT_MODEL)


def run(routers: list[str], scale: int = 0, model: str | None = None) -> list[dict]:
    """Every router on: both languages together, each language's requests against the other language's starters
    only (cross-language), and, with `scale`, both languages padded to `scale` pages."""
    data = load_cases()
    topics, cases = data["topics"], data["cases"]
    en, es = starter_pages("en"), starter_pages("es")
    runs = [("en+es", en + es, cases, ("en", "es")),
            ("es→en", en, [c for c in cases if c["lang"] == "es"], ("en",)),
            ("en→es", es, [c for c in cases if c["lang"] == "en"], ("es",))]
    if scale:
        runs.append((f"en+es {scale}p", en + es + distractors(scale - len(en) - len(es)), cases, ("en", "es")))
    rows = []
    for router in routers:
        for name, pages, cs, langs in runs:
            with throwaway_store(pages, _hybrid_config(model) if router == "hybrid" else None):
                if router == "hybrid":
                    _warm(model)
                r = evaluate(cs, topics, langs)
            rows.append({"router": router, "store": name, "pages": len(pages), **r})
    return rows


def from_store(meaning=None, scoped: bool = False) -> dict:
    """The person's own tasks marked good, against their real store: the request that started each one and the
    pieces it used (those still in the store, not the ones the task itself saved). Read-only: nothing is written,
    and only counts come out, never a request. `scoped`: each task sees only its project's pieces (and another
    project's when the request names it), the way the hooks load them by default."""
    from athos import control, load
    pieces = load.enabled()
    have = {p.id for p in pieces}
    out = {"tasks": 0, "hit1": 0, "any": 0, "missed": 0, "extra": 0, "none_tasks": 0, "none_loads": 0, "ms": [],
           "other_project": 0, "all_tasks": 0}
    known = {q for p in pieces for q in p.projects}
    byid = {p.id: p for p in pieces}
    for t in ev.tasks():
        if t.get("result") != "ok" or not t.get("request"):
            continue
        expect = (set(t.get("pieces") or []) - set(t.get("saved") or [])) & have
        pool = control.scope_project(pieces, t.get("project") or "", t["request"]) if scoped else pieces
        t0 = time.perf_counter()
        ids = [p.id for p in load.relevant(t["request"], pool, meaning=meaning)]
        out["ms"].append((time.perf_counter() - t0) * 1000)
        # A page of another project loaded for this task: the mixing per-project memory is for. The tasks' recorded
        # pieces count every page that loaded, misloads included, so hit@1 above can't judge it on its own.
        here = t.get("project") or ""
        out["all_tasks"] += 1
        out["other_project"] += here in known and any(byid[i].projects and here not in byid[i].projects
                                                      for i in ids)
        if not expect:                           # done well with nothing loaded: does the router load something now?
            out["none_tasks"] += 1
            out["none_loads"] += bool(ids)
            continue
        out["tasks"] += 1
        out["hit1"] += bool(ids) and ids[0] in expect
        out["any"] += bool(set(ids) & expect)
        out["missed"] += not ids
        out["extra"] += bool(set(ids) - expect)
    ms = out.pop("ms")
    out["ms_mean"] = round(statistics.mean(ms), 2) if ms else 0.0
    out["pieces"] = len(pieces)
    return out


def _pct(a: int, b: int) -> str:
    return f"{a}/{b} {a / b:4.0%}" if b else "—"


def render(rows: list[dict]) -> str:
    lines = [f"{'router':<8} {'store':<14} {'pages':>5}  {'hit@1':>11}  {'missed':>6}  {'wrong':>5}  "
             f"{'none ok':>11}  {'ms/req':>6}  {'p95':>6}"]
    for r in rows:
        lines.append(f"{r['router']:<8} {r['store']:<14} {r['pages']:>5}  {_pct(r['hit1'], r['positives']):>11}  "
                     f"{r['missed']:>6}  {r['wrong']:>5}  {_pct(r['none_ok'], r['negatives']):>11}  "
                     f"{r['ms_mean']:>6.1f}  {r['ms_p95']:>6.1f}")
    lines.append("\nhit@1: the first piece loaded is the expected one. wrong: requests that loaded a piece they "
                 "didn't call for. none ok: requests that need no know-how and loaded nothing. es→en: Spanish "
                 "requests against the English starters only.")
    return "\n".join(lines)


def render_store(r: dict) -> str:
    return (f"Your store ({r['pieces']} pieces), {r['tasks']} tasks marked good that used a piece:\n"
            f"  hit@1 {_pct(r['hit1'], r['tasks'])} · any of its pieces {_pct(r['any'], r['tasks'])} · "
            f"nothing loaded {r['missed']} · loaded one it didn't use {r['extra']}\n"
            f"  {r['none_tasks']} good tasks used no piece; the router loads one for {r['none_loads']} of them.\n"
            f"  a page of another project loaded for {r['other_project']} of {r['all_tasks']} tasks.\n"
            f"  {r['ms_mean']:.1f} ms per request. Read-only: no request is printed or written.")
