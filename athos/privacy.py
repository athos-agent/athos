"""Read-only reports for deciding who may see each piece, before anything is marked.

    athos privacy [--json]           which pieces look private (counts, and ids for the person to review)
    athos profile --untagged [--json]   which pieces have no project, and whether each is in the profile

Neither writes anything: a piece becomes private only when the person adds `visibility: private` to its frontmatter,
and joins the profile only with `athos profile add <id>`. The reports name pieces by id only, never by title, and
print none of their text.
"""

from __future__ import annotations

import re

from athos import control, share, store

# Words that say a piece is about someone's clients, patients, money or production systems: know-how that should not
# travel to another project's session. Both languages; a word counts once however often it appears.
SENSITIVE = re.compile(
    r"\b(?:clients?|clientes?|customers?|patients?|pacientes?|clinic(?:al|s)?|cl[ií]nic[ao]s?|medical|m[eé]dic[oa]s?|"
    r"health|salud|hospital(?:es|s)?|hipaa|baa|dpa|gdpr|personal data|datos personales|invoices?|facturas?|"
    r"payroll|salar(?:y|ies|io|ios)|production|producci[oó]n|credentials?|credenciales?|passwords?|contrase[ñn]as?|"
    r"secrets?|api keys?|\.env)\b", re.IGNORECASE)
ACCOUNT = re.compile(r"(?<!\d)\d{12}(?!\d)")                 # a cloud account number
STRONG = {"email", "phone", "id number"}                      # share.py's findings that point at a real person
SENSITIVE_MIN = 3                                            # distinct sensitive words for that signal alone


def _phone(found: str) -> bool:
    """share.py's phone pattern also catches dates (2026-11-15), ids and hashes: a phone here is written as one, with
    a leading + or with spaces or parentheses between its groups."""
    if re.match(r"\d{4}-\d{2}-\d{2}", found):
        return False
    return found.startswith("+") or bool(re.search(r"\d[ (]+\d|\(\d", found))


def signals(piece: store.Piece) -> list[str]:
    """Why a piece looks private: data that points at a real person or account, or a body about clients, patients,
    money or production. Empty for a piece that looks safe to see anywhere."""
    text = "\n".join((piece.title, piece.when, piece.body))
    kinds = {kind for kind, found in share.findings(text, []) if kind != "phone" or _phone(found)}
    out = sorted(kinds & STRONG)
    if ACCOUNT.search(text):
        out.append("account number")
    words = {w.lower() for w in SENSITIVE.findall(text)}
    if len(words) >= SENSITIVE_MIN:
        out.append("clients, patients, money or production")
    return out


def propose(pieces: list[store.Piece] | None = None) -> dict:
    """Which pieces look private, for the person to review. Only pieces tagged with a project are proposed: an
    untagged piece (a profession's starter, a gallery page) is generic by design. Pieces already marked are counted
    apart. Read-only."""
    pieces = store.all_pieces() if pieces is None else pieces
    marked = [p.id for p in pieces if p.visibility in store.VISIBILITIES]
    proposed, by_signal = [], {}
    for p in pieces:
        if not p.projects or p.visibility in store.VISIBILITIES:
            continue
        found = signals(p)
        if found:
            proposed.append({"id": p.id, "signals": found})
            for s in found:
                by_signal[s] = by_signal.get(s, 0) + 1
    return {"pieces": len(pieces), "tagged": sum(1 for p in pieces if p.projects), "already_marked": len(marked),
            "proposed": proposed, "by_signal": by_signal}


def render_proposal(r: dict, cmd: str = "athos") -> str:
    lines = [f"{len(r['proposed'])} of {r['tagged']} pieces tagged with a project look private "
             f"({r['pieces']} pieces in all, {r['already_marked']} already have a visibility):"]
    lines += [f"  {s}: {n}" for s, n in sorted(r["by_signal"].items(), key=lambda kv: -kv[1])]
    if r["proposed"]:
        lines.append("To review (ids only):")
        lines += [f"  {x['id']} · {', '.join(x['signals'])}" for x in r["proposed"]]
    lines.append("Nothing was changed. To make a piece private, add the line `visibility: private` to its "
                 "frontmatter (under `projects:`): it then loads only in its own projects, never in a repository "
                 "marked public, and is never named in another project's session.")
    return "\n".join(lines)


def untagged(pieces: list[store.Piece] | None = None) -> dict:
    """The pieces with no project: since the profile exists they load in a project only when they are in it.
    Read-only."""
    pieces = store.all_pieces() if pieces is None else pieces
    profile = set(control.profile_ids())
    rows = [{"id": p.id, "in_profile": p.id in profile, "origin": p.origin.get("platform", "unknown"),
             "private": store.private(p)} for p in pieces if not p.projects]
    return {"pieces": len(pieces), "untagged": len(rows), "in_profile": sum(r["in_profile"] for r in rows),
            "profile": len(profile), "profile_max": control.PROFILE_MAX, "rows": rows}


def render_untagged(r: dict, cmd: str = "athos") -> str:
    lines = [f"{r['untagged']} of {r['pieces']} pieces have no project; {r['in_profile']} of them are in your "
             f"profile ({r['profile']} of at most {r['profile_max']} pieces)."]
    lines += [f"  {x['id']} · {'in the profile' if x['in_profile'] else 'not in the profile'} · from {x['origin']}"
              + (" · private" if x["private"] else "") for x in r["rows"]]
    lines.append(f"Outside the profile, an untagged piece loads only where no folder is known (Claude Desktop's chat) "
                 f"or with `{cmd} load all`. Put one in it with `{cmd} profile add <id>`, or tag it with its project "
                 f"(`projects: [name]` in its frontmatter). Nothing was changed.")
    return "\n".join(lines)
