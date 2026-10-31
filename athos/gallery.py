"""The gallery: ways of working anyone can take, kept in this repository's `gallery/` folder.

Each entry is a normal Athos page (markdown with frontmatter: id, title, when, profession, lang; statements with
**When/Do/Because/Links** and **If:**/**Calls:** branches), in English (`gallery/en/`) and Spanish (`gallery/es/`).

    athos gallery build [--out DIR]   writes gallery.json (every page: its steps, branches and the pages it calls) and
                                      index.html, a static page that previews each entry like Athos's panel
    athos add <id|url> [--dry-run]    adds an entry and the pages it links to, from this repository's gallery only

[Use in Athos] on the page copies a short request ("Athos · add from gallery: <id>"); pasted in any agent with Athos,
the prompt hook or athos_find recognise it and the agent runs the add. Nothing is downloaded without that request,
only from the fixed raw URL of this repository, and a page the person already has is never overwritten.
"""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from pathlib import Path

from athos import store, trail, wiki

ROOT = Path(__file__).resolve().parents[1]
DIR = ROOT / "gallery"
TEMPLATE = Path(__file__).with_name("gallery.html")
LANGS = ("en", "es")
HOST = "raw.githubusercontent.com"
BASE = "/athos-agent/athos/main/gallery/"
RAW = f"https://{HOST}{BASE}"
INDEX_URL = RAW + "gallery.json"
PAGE_PATH = re.compile(re.escape(BASE) + r"(en|es)/([a-z0-9][a-z0-9-]{0,59})\.md")
ID = re.compile(r"[a-z0-9][a-z0-9-]{0,59}")
MAX_PAGES = 12              # an entry and the pages it reaches; a gallery walk is a handful of pages, never a crawl
MAX_BYTES = 256_000
REQUEST = {"en": "Athos · add from gallery: {id}", "es": "Athos · agregar desde la galería: {id}"}
ASKED = re.compile(r"Athos · (?:add from gallery|agregar desde la galer[ií]a):\s*(\S+)")


def requested(text: str) -> str | None:
    """The id (or URL) in a pasted "Athos · add from gallery: <id>" request, if the text is one."""
    m = ASKED.search(text or "")
    return m.group(1).rstrip(".,;") if m else None


# ------------------------------------------------------------------------------------------------ the pages
def parse(text: str) -> tuple[dict, store.Piece]:
    meta, body = store.parse_frontmatter(text)
    return meta, store.Piece(id=meta.get("id", ""), title=meta.get("title", ""), when=meta.get("when", ""),
                             body=body.strip() + "\n")


def read(root: Path = DIR) -> list[tuple[dict, store.Piece]]:
    return [parse(f.read_text()) for lang in LANGS for f in sorted((root / lang).glob("*.md"))]


def entry(meta: dict, p: store.Piece) -> dict:
    """One page as the gallery shows it: its steps, each with the branches (If/Calls) it hands over to."""
    steps, calls = [], []
    for s in wiki.statements(p):
        branches = [{"page": c["page"], "statement": c["statement"], "if": c["if"]} for c in s.calls]
        steps.append({"id": s.id, "label": trail.label(s.when, s.do, s.id), "when": s.when, "do": s.do,
                      "because": s.because, "branches": branches})
        calls += [b["page"] for b in branches if b["page"] not in calls and b["page"] != p.id]
    out = {"id": p.id, "title": p.title, "when": p.when, "profession": meta.get("profession", "other"),
           "lang": meta.get("lang", "en"), "path": f"{meta.get('lang', 'en')}/{p.id}.md", "steps": steps,
           "calls": calls, "links": wiki.links_of(p)}
    if meta.get("author"):
        out["author"] = meta["author"]
    return out


def catalog(root: Path = DIR) -> dict:
    """gallery.json: every page; `entry` marks the ones a person starts from (no other page calls them)."""
    entries = [entry(m, p) for m, p in read(root)]
    called = {c for e in entries for c in e["calls"]}
    for e in entries:
        e["entry"] = e["id"] not in called
    return {"source": RAW, "request": REQUEST, "entries": entries}


def build(out: Path | None = None, root: Path = DIR) -> list[Path]:
    """Write gallery.json and index.html (the page carries the same data inline, so it opens from a file too)."""
    out = Path(out) if out else root
    out.mkdir(parents=True, exist_ok=True)
    data = catalog(root)
    text = json.dumps(data, ensure_ascii=False, indent=1) + "\n"
    (out / "gallery.json").write_text(text)
    inline = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    (out / "index.html").write_text(TEMPLATE.read_text().replace("__GALLERY__", inline))
    return [out / "gallery.json", out / "index.html"]


# ------------------------------------------------------------------------------------------------ adding one
def check_url(url: str) -> tuple[str, str]:
    """(lang, id) of a gallery page URL; anything but this repository's raw gallery is refused."""
    u = urllib.parse.urlsplit(url)
    m = PAGE_PATH.fullmatch(u.path)
    if u.scheme != "https" or u.netloc != HOST or u.query or u.fragment or not m:
        raise ValueError(f"not a page of Athos's gallery: {url} (only {RAW}<en|es>/<id>.md)")
    return m.group(1), m.group(2)


def fetch_url(url: str) -> str:
    """GET one gallery file. Only the gallery index and its pages, and only from this repository."""
    if url != INDEX_URL:
        check_url(url)
    with urllib.request.urlopen(url, timeout=10) as r:          # noqa: S310 — the URL was checked above
        if r.geturl() != url:
            raise ValueError(f"the gallery redirected to {r.geturl()}; nothing was added")
        return r.read(MAX_BYTES).decode()


def _locate(ref: str, fetch) -> tuple[str, str]:
    if ref.startswith(("http://", "https://")):
        return check_url(ref)
    if not ID.fullmatch(ref):
        raise ValueError(f"not a gallery id: {ref!r}")
    for e in json.loads(fetch(INDEX_URL)).get("entries", []):
        if e.get("id") == ref and e.get("lang") in LANGS:
            return e["lang"], ref
    raise LookupError(f"no {ref!r} in Athos's gallery")


def add(ref: str, fetch=None, dry_run: bool = False) -> dict:
    """Download a gallery entry and every page it links to (same language), and save each one the person doesn't
    have yet as version 1 with origin `gallery`. A page already in the store is left as it is. `fetch` is injected in
    tests; by default it reads the raw files of this repository."""
    fetch = fetch or fetch_url
    lang, first = _locate(ref.strip(), fetch)
    queue, seen, pages = [first], set(), []
    while queue and len(pages) < MAX_PAGES:
        pid = queue.pop(0)
        if pid in seen:
            continue
        seen.add(pid)
        url = f"{RAW}{lang}/{pid}.md"
        check_url(url)
        meta, p = parse(fetch(url))
        if p.id != pid or not p.title or not p.when or not wiki.is_wiki(p):
            raise ValueError(f"{url} is not a gallery page")
        pages.append((url, p))
        queue += [q for q in wiki.links_of(p) if q not in seen]
    out = []
    for url, p in pages:
        if store.get(p.id):
            status = "exists"
        elif dry_run:
            status = "new"
        else:
            store.create(p.title, p.when, p.body, piece_id=p.id,
                         origin={"platform": "gallery", "model": "athos-agent/athos", "source": url})
            status = "added"
        out.append({"id": p.id, "title": p.title, "status": status,
                    "steps": [trail.label(s.when, s.do, s.id) for s in wiki.statements(p)]})
    if any(x["status"] == "added" for x in out):
        try:
            wiki.rebuild()
        except OSError:
            pass
    return {"lang": lang, "id": first, "source": f"{RAW}{lang}/{first}.md", "pages": out, "dry_run": dry_run}


def summary(r: dict, lang: str = "en") -> str:
    """What was added (or would be), in the person's language, one line per page."""
    es = lang == "es"
    head = {"added": "Agregué de la galería de Athos:" if es else "Added from Athos's gallery:",
            "new": "Esto se agregaría de la galería de Athos:" if es else "This would be added from Athos's gallery:"}
    lines = []
    new = [x for x in r["pages"] if x["status"] != "exists"]
    if new:
        lines.append(head["new" if r["dry_run"] else "added"])
        for x in new:
            lines.append(f"- «{x['title']}» (`{x['id']}`): " + " · ".join(x["steps"]))
    have = [x for x in r["pages"] if x["status"] == "exists"]
    if have:
        lines.append(("Ya estaba en tu know-how, lo dejé como estaba: " if es
                      else "Already in your know-how, left as it was: ")
                     + ", ".join(f"«{x['title']}» (`{x['id']}`)" for x in have))
    return "\n".join(lines)
