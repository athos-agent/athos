"""Share a way of working with Athos's gallery through a web form: for a lawyer or an accountant, not only for
programmers (no GitHub account, no email address in the code).

    athos share <id>                        a draft of the page and the pages it links to, in ~/.athos/share/<id>/,
                                            in the gallery's format, with what looks private flagged
    athos share <id> --send [--as NAME]     open the gallery's form in the browser, filled in with the pages;
                                            they read it and press Submit themselves (no account needed)

Nothing leaves the machine until the person presses Submit on the form. The draft keeps only the
gallery's fields (no history, projects, dates or origin). What looks private (emails, phone numbers, ID numbers,
links, folders on this computer, project names, the person's own name) is flagged; the agent rewrites it with
fictional data in the draft files, shows the person what will be published, and sends only on their yes. `--send`
refuses while something is still flagged.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import urllib.parse
import webbrowser
from pathlib import Path

from athos import paths, store, trail, wiki

# The gallery's form (Google Forms, no sign-in): submissions land in a sheet the maintainers turn into gallery pages.
FORM = "https://docs.google.com/forms/d/e/1FAIpQLSd6BqXjExnLjZ3H8kW59oEKTUmhETXoMVYnrSTZA-qnnJCI2g/viewform"
FIELDS = {"title": "entry.1370055399", "author": "entry.1047448034", "lang": "entry.839330900",
          "pages": "entry.115435207"}
SINCE = (0, 1, 96)             # the first version with `athos share`: an older `athos` on PATH lacks it
MAX_PAGES = 12                 # as `athos add`: an entry and the pages it reaches
URL_MAX = 7500                 # a longer pre-filled link may be cut: the pages then go by the clipboard
PROFESSIONS = ("law", "finance", "journalism", "science", "ops", "other")

# What a published page must not carry. Each finding names its kind so the person reads what was taken out.
PRIVATE = [
    ("email", re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")),
    ("phone", re.compile(r"(?<![\w.])\+?\d[\d ()-]{7,}\d(?![\w.])")),
    ("id number", re.compile(r"\b\d{2}-\d{8}-\d\b|\b\d{1,2}\.\d{3}\.\d{3}\b|\b\d{3}-\d{2}-\d{4}\b")),
    ("link", re.compile(r"https?://\S+")),
    ("folder", re.compile(r"(?:/Users/|/home/|[A-Z]:\\\\)\S+")),
]
WORDS = {
    "en": {"kinds": {"email": "email", "phone": "phone number", "id number": "ID number", "link": "link",
                     "folder": "folder on this computer", "project": "project name", "name": "your name"},
           "draft": "Draft for the gallery in {dir}:", "steps": "{n} steps", "flag": "  to rewrite: {what}",
           "clean": "Nothing private found. Read it once more, then send it with: athos share {id} --send --as \"<name>\"",
           "fix": "Rewrite what is flagged with fictional data in those files, then: athos share {id} --send",
           "missing": "Linked pages not in your know-how (left out): {ids}",
           "refuse": "Still flagged, not sent: {what}. Rewrite it in {dir} first.",
           "opened": "The gallery's form opened in your browser, filled in with {n} page(s). Read it and press "
                     "Submit.",
           "clip": "The pages are long for a link: they are on your clipboard, paste them (⌘V / Ctrl+V) into the "
                   "Pages field before submitting.",
           "noopen": "Couldn't open the browser. Open {url} and paste the pages in {dir}.",
           "paste": "(paste the pages here: they are on your clipboard)", "anon": "anonymous"},
    "es": {"kinds": {"email": "email", "phone": "teléfono", "id number": "número de documento o CUIT", "link": "link",
                     "folder": "carpeta de esta computadora", "project": "nombre de proyecto", "name": "tu nombre"},
           "draft": "Borrador para la galería en {dir}:", "steps": "{n} pasos", "flag": "  para reescribir: {what}",
           "clean": "No encontré nada privado. Leelo una vez más y mandalo con: athos share {id} --send --as \"<nombre>\"",
           "fix": "Reescribí lo marcado con datos ficticios en esos archivos, y después: athos share {id} --send",
           "missing": "Páginas enlazadas que no están en tu know-how (quedan afuera): {ids}",
           "refuse": "Todavía hay datos marcados, no se envió: {what}. Reescribilos antes en {dir}.",
           "opened": "Se abrió en tu navegador el formulario de la galería, completo con {n} página(s). Leelo y "
                     "tocá Enviar.",
           "clip": "Las páginas son largas para un link: están copiadas, pegalas (⌘V / Ctrl+V) en el campo Páginas "
                   "antes de enviar.",
           "noopen": "No pude abrir el navegador. Abrí {url} y pegá las páginas de {dir}.",
           "paste": "(pegá acá las páginas: están copiadas)", "anon": "anónimo"},
}
# The request that starts a share, in the person's words: the prompt hook answers it with SHARE_CONTEXT.
ASKED = re.compile(r"\b(?:compart\w*|publica\w*|sub[ií]\w*|mand[aá]\w*)\b.{0,80}\bgaler[ií]a\b"
                   r"|\b(?:share|publish|send|submit)\b.{0,80}\bgallery\b", re.IGNORECASE | re.DOTALL)

SHARE_CONTEXT = """The person wants to share a way of working with Athos's public gallery. They may not be technical: \
keep every step in plain words, and answer in the language of their request.
1. Pick the page: the one they name, else the one the last task followed (`{cmd} list` shows them). Run \
`{cmd} share <id> --profession <law|finance|journalism|science|ops|other>`: it writes a draft of the page and the pages it links to and flags what looks private.
2. Open each draft file it lists and rewrite, with fictional data, everything flagged AND anything else that could \
identify a real client, person, company, case or amount from their work. Keep their method, criteria and format. \
For stand-ins use example.com / ejemplo.com emails and numbers made of zeros (CUIT 30-00000000-0), which the check \
knows are fictional.
3. Show them, briefly: the title, how many steps, what you took out ("2 client names, 1 CUIT…"), and ask with what \
name they want to be credited (or anonymous) and whether to send it. Offer to show the full page.
4. Only on a clear yes, run `{cmd} share <id> --send --as "<their name>"` (no --as for anonymous): the gallery's \
form opens in their browser, filled in, and they press Submit themselves (no account needed). Tell them that, in \
one line.
Never send without their yes; medical or health ways of working are not accepted by the gallery for now."""


def asked(text: str) -> bool:
    return bool(ASKED.search(text or ""))


def folder(piece_id: str) -> Path:
    return paths.home() / "share" / piece_id


def _lang_of(p: store.Piece) -> str:
    text = f"{p.title} {p.when} {p.body}".lower()
    es = len(re.findall(r"\b(?:el|la|los|las|de|que|con|para|cuando|del|una|por)\b", text))
    en = len(re.findall(r"\b(?:the|of|and|to|with|for|when|a|is|on|by)\b", text))
    return "es" if es > en else "en"


def _walk(first: str) -> tuple[list[store.Piece], list[str]]:
    queue, seen, pages, missing = [first], set(), [], []
    while queue and len(pages) < MAX_PAGES:
        pid = queue.pop(0)
        if pid in seen:
            continue
        seen.add(pid)
        p = store.get(pid)
        if not p:
            missing.append(pid)
            continue
        pages.append(p)
        queue += [q for q in wiki.links_of(p) if q not in seen]
    return pages, missing


def render(p: store.Piece, profession: str, lang: str, author: str = "") -> str:
    """The page as the gallery keeps it: only its public fields, no history."""
    head = [f"id: {p.id}", f"title: {store._quote(p.title)}", f"when: {store._quote(p.when)}",
            f"profession: {profession}", f"lang: {lang}"]
    if author:
        head.append(f"author: {store._quote(author)}")
    return "---\n" + "\n".join(head) + "\n---\n\n" + p.body.strip() + "\n"


def findings(text: str, projects: list[str], name: str = "") -> list[tuple[str, str]]:
    """What looks private in a page: (kind, the text found)."""
    body = store.parse_frontmatter(text)[1] if text.startswith("---") else text
    meta_text = "\n".join(l for l in text.split("\n---", 1)[0].splitlines() if l.startswith(("title:", "when:")))
    scan = meta_text + "\n" + body
    out = [(kind, m.group(0).rstrip(".,;)")) for kind, rx in PRIVATE for m in rx.finditer(scan)
           if not _fictional(m.group(0))]
    low = scan.lower()
    out += [("project", pr) for pr in projects if len(pr) > 2 and re.search(rf"\b{re.escape(pr.lower())}\b", low)]
    if name and len(name) > 2 and re.search(rf"\b{re.escape(name.lower())}\b", low):
        out.append(("name", name))
    ids = {t for k, t in out if k == "id number"}
    out = [(k, t) for k, t in out if not (k == "phone" and t in ids)]     # a CUIT is not also a phone number
    seen, unique = set(), []
    for f in out:
        if f not in seen:
            seen.add(f)
            unique.append(f)
    return unique


# The agent's fictional stand-ins are not private: an example domain, or a number that is all zeros but a digit or two.
def _fictional(text: str) -> bool:
    if re.search(r"@(?:[\w-]+\.)*(?:example|ejemplo)\.", text, re.IGNORECASE):
        return True
    digits = re.sub(r"\D", "", text)
    return len(digits) >= 7 and len(digits.replace("0", "")) <= 2     # 30-00000000-0: a type prefix, then zeros


def _projects() -> list[str]:
    return sorted({pr for p in store.all_pieces() for pr in p.projects})


def prepare(piece_id: str, profession: str = "other", lang: str | None = None, author: str = "") -> dict:
    """Write the draft (kept if it is already there: the agent may have rewritten it) and flag what looks private."""
    first = store.get(piece_id)
    if not first:
        raise LookupError(f"no way of working {piece_id!r}")
    lang = lang or _lang_of(first)
    pages, missing = _walk(piece_id)
    out = folder(piece_id)
    out.mkdir(parents=True, exist_ok=True)
    projects, name = _projects(), trail.person_name()
    report = []
    for p in pages:
        f = out / f"{p.id}.md"
        if not f.exists():
            f.write_text(render(p, profession if profession in PROFESSIONS else "other", lang, author))
        text = f.read_text()
        report.append({"id": p.id, "title": p.title, "file": str(f), "steps": len(wiki.statements(p)),
                       "findings": findings(text, projects, name)})
    return {"id": piece_id, "dir": str(out), "lang": lang, "pages": report, "missing": missing}


def write_draft(piece_id: str, page_id: str, text: str) -> Path:
    """The agent's rewrite of one draft page (Claude Desktop's chat can't edit files: it passes the text)."""
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,59}", page_id or ""):
        raise ValueError(f"not a page id: {page_id!r}")
    meta, _ = store.parse_frontmatter(text)
    if meta.get("id") != page_id:
        raise ValueError(f"the page's id must be {page_id!r}")
    f = folder(piece_id) / f"{page_id}.md"
    if not f.exists():
        raise LookupError(f"{page_id!r} is not in the draft of {piece_id!r}")
    f.write_text(text.strip() + "\n")
    return f


def pages_text(piece_id: str, author: str) -> tuple[str, list[Path]]:
    """Every draft page, the entry first, each under its file name, with the credit in its frontmatter."""
    files = sorted(folder(piece_id).glob("*.md"), key=lambda f: (f.stem != piece_id, f.name))
    parts = []
    for f in files:
        text = f.read_text()
        if author and "\nauthor:" not in text.split("\n---", 1)[0]:
            text = text.replace("\n---\n", f"\nauthor: {store._quote(author)}\n---\n", 1)
        parts += [f"===== {f.name} =====", text.strip(), ""]
    return "\n".join(parts), files


def form_url(values: dict) -> str:
    return FORM + "?usp=pp_url&" + urllib.parse.urlencode({FIELDS[k]: v for k, v in values.items()})


def _open(url: str) -> bool:
    try:
        if sys.platform == "darwin":
            return subprocess.run(["open", url], capture_output=True, timeout=10).returncode == 0
        return webbrowser.open(url)
    except (OSError, subprocess.SubprocessError):
        return False


def _copy(text: str) -> bool:
    for cmd in (["pbcopy"], ["wl-copy"], ["xclip", "-selection", "clipboard"], ["clip"]):
        if shutil.which(cmd[0]):
            try:
                return subprocess.run(cmd, input=text, text=True, timeout=5).returncode == 0
            except (OSError, subprocess.SubprocessError):
                return False
    return False


def send(piece_id: str, author: str = "", lang: str = "en", opener=_open, copier=_copy) -> dict:
    """Open the gallery's form, filled in. Refuses while a draft still holds something flagged."""
    out = folder(piece_id)
    files = sorted(out.glob("*.md"))
    if not files:
        raise LookupError(f"no draft for {piece_id!r}: run `athos share {piece_id}` first")
    projects, name = _projects(), trail.person_name()
    left = [(f.stem, k, t) for f in files for k, t in findings(f.read_text(), projects, name)]
    if left:
        return {"sent": False, "left": left, "dir": str(out)}
    body, files = pages_text(piece_id, author)
    title = store.parse(files[0].read_text()).title
    values = {"title": title, "author": author or WORDS[lang]["anon"], "lang": lang, "pages": body}
    url, clipboard = form_url(values), False
    if len(url) > URL_MAX:
        clipboard = copier(body)
        url = form_url({**values, "pages": WORDS[lang]["paste"]})
    return {"sent": opener(url), "clipboard": clipboard, "pages": len(files), "dir": str(out), "url": FORM}


def report_text(r: dict, lang: str) -> str:
    W = WORDS[lang]
    kinds = W["kinds"]
    out = [W["draft"].format(dir=r["dir"])]
    flagged = False
    for p in r["pages"]:
        out.append(f"- {p['title']} ({W['steps'].format(n=p['steps'])}): {p['file']}")
        if p["findings"]:
            flagged = True
            out.append(W["flag"].format(what=", ".join(f"{kinds[k]} «{t}»" for k, t in p["findings"])))
    if r["missing"]:
        out.append(W["missing"].format(ids=", ".join(r["missing"])))
    out.append(W["fix" if flagged else "clean"].format(id=r["id"]))
    return "\n".join(out)


def send_text(r: dict, lang: str) -> str:
    W = WORDS[lang]
    if r.get("left"):
        what = ", ".join(f"{W['kinds'][k]} «{t}» ({pid})" for pid, k, t in r["left"])
        return W["refuse"].format(what=what, dir=r["dir"])
    if not r["sent"]:
        return W["noopen"].format(dir=r["dir"], url=r["url"])
    return W["opened"].format(n=r["pages"]) + ("\n" + W["clip"] if r.get("clipboard") else "")
