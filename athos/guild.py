"""Guilds: one way of working for the team, from each colleague's own copy of it.

In a firm several people improve their own copy of the same piece ("Review a lease"). Each one exports it with
`athos export --guild <folder>`: the piece file and `<id>.stats.json`, which says, per statement, how many of their
tasks walked it (the `step` items of the trail) and how those tasks were marked. Only counts: no request, no client.

`athos merge <id> <file-or-folder>...` lines up the statements of the person's piece and the colleagues' variants (by
id, else by a **When** for the same moment) and proposes one piece:

    same text everywhere        kept
    in one variant only         kept if its tasks went well or nobody marked them; dropped (and listed) when most of
                                its marked tasks were corrected or failed
    different texts             the text with the best success rate; or, with a model, one text merged from them

Nothing changes until `--apply`, which saves the proposal as a new version of the person's piece (history kept).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from athos import paths, store, wiki

RESULTS = ("ok", "corrected", "failed")
MIN_MARKED = 2          # marked tasks a statement needs before its record can drop it
NEUTRAL = 0.5           # the success rate assumed for a text nobody marked: below a proven one, above a failing one
ME = "you"
# Share of words two **When** lines need to be one statement under two ids. Stricter than the wiki's OVERLAP (which
# only flags pages to check): "checking the deposit clause" and "checking the rent clause" are two statements.
ALIGN = 0.6


# ------------------------------------------------------------------------------------------------ stats
def stats(piece_id: str, owner: str | None = None) -> dict:
    """Per statement of the piece: the tasks that walked it and how they were marked. Counts only."""
    from athos import eval as ev
    p = store.get(piece_id)
    if p is None:
        raise LookupError(f"no piece {piece_id!r}")
    result = {t["task_id"]: t["result"] for t in ev.tasks()}
    walked: dict[str, set] = {}
    for e in ev.events():
        if e.get("type") == "trail" and e.get("kind") == "step" and e.get("piece") == p.id and e.get("task_id"):
            walked.setdefault(e.get("step", ""), set()).add(e["task_id"])
    out = {}
    for s in wiki.statements(p):
        tids = walked.get(s.id, set())
        row = {"tasks": len(tids), **{r: 0 for r in RESULTS}, "unmarked": 0}
        for tid in tids:
            r = result.get(tid, "unevaluated")
            row[r if r in RESULTS else "unmarked"] += 1
        out[s.id] = row
    return {"piece": p.id, "version": p.version, "owner": owner or None, "statements": out}


def export(dest: Path, piece_ids: list[str] | None = None, owner: str | None = None) -> list[str]:
    """Write each piece (or the ones named) and its stats to `dest`, for a colleague's `athos merge`."""
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    ids = piece_ids or [p.id for p in store.all_pieces()]
    for pid in ids:
        p = store.get(pid)
        if p is None:
            raise LookupError(f"no piece {pid!r}")
        (dest / f"{p.id}.md").write_text(store.render(p))
        (dest / f"{p.id}.stats.json").write_text(json.dumps(stats(p.id, owner), ensure_ascii=False, indent=2) + "\n")
    return ids


# ------------------------------------------------------------------------------------------------ variants
@dataclass
class Variant:
    owner: str
    piece: store.Piece
    stats: dict = field(default_factory=dict)        # statement id → counts
    blocks: dict = field(default_factory=dict)       # statement id → its text, exactly as written


def blocks(body: str) -> tuple[str, list[tuple[str, str]]]:
    """The text before the first statement, and each statement's id with its text (header excluded), verbatim."""
    parts = wiki.STATEMENT.split(body)
    if len(parts) == 1:
        return "", [("steps", body.strip())]
    return parts[0].strip(), [(sid, text.strip()) for sid, text in zip(parts[1::2], parts[2::2])]


def _variant(f: Path, owner: str | None = None) -> Variant:
    p = store.parse(f.read_text())
    st: dict = {}
    sf = f.with_name(f.name[:-3] + ".stats.json")
    if sf.is_file():
        try:
            data = json.loads(sf.read_text())
            st, owner = data.get("statements") or {}, owner or data.get("owner")
        except ValueError:
            pass
    # Who it is from: the name they exported with, else the folder it came in (`ana/review-a-lease.md`).
    owner = owner or (f.parent.name if f.parent.name not in ("", ".") else f.stem)
    return Variant(owner, p, st, dict(blocks(p.body)[1]))


def find_variants(sources: list[str], piece_id: str) -> list[Variant]:
    """The colleagues' variants: files as given, and in folders every `<piece_id>.md` (subfolders too, one per
    colleague), never an Athos history copy."""
    out = []
    for src in sources:
        path = Path(src).expanduser()
        if path.is_file():
            out.append(_variant(path))
        elif path.is_dir():
            out += [_variant(f) for f in sorted(path.rglob(f"{piece_id}.md")) if ".history" not in f.parts]
        else:
            raise FileNotFoundError(f"{src}: no such file or folder")
    seen: dict[str, int] = {}
    for v in out:                                    # two "Ana"s stay apart in the summary
        seen[v.owner] = seen.get(v.owner, 0) + 1
        if seen[v.owner] > 1:
            v.owner = f"{v.owner} ({seen[v.owner]})"
    return out


def _same_moment(a: str, b: str) -> bool:
    wa, wb = wiki._words(a), wiki._words(b)
    return len(wa) >= 3 and len(wb) >= 3 and len(wa & wb) / len(wa | wb) >= ALIGN


def _when(text: str) -> str:
    m = re.search(r"^\*\*When:\*\*\s*(.*)$", text, re.M)
    return m.group(1) if m else ""


def _norm(text: str) -> str:
    return " ".join(text.split())


def _rate(row: dict | None) -> tuple[float | None, int]:
    row = row or {}
    marked = sum(int(row.get(r) or 0) for r in RESULTS)
    return (int(row.get("ok") or 0) / marked if marked else None), marked


def _has(who: str) -> str:
    return "you have" if who == ME else f"{who} has"


def _record(row: dict | None) -> str:
    rate, marked = _rate(row)
    return f"{int((row or {}).get('ok') or 0)}/{marked} good" if marked else "not marked"


# ------------------------------------------------------------------------------------------------ merge
MERGE_PROMPT = """You merge colleagues' versions of ONE statement of a shared way of working into one statement.
Keep the exact conventions of the texts: their language, their terms, the **When:** / **Do:** / **Because:** /
**Links:** lines, every [[page#statement]] link they share, numbers and names exactly as written. Keep what each version
adds that the others lack; when they contradict, prefer the version whose tasks went better. Answer with the statement
only, starting with the line `## #{sid}`, nothing before or after it."""


def model_merge(sid: str, versions: list[tuple[str, str, dict | None]], model: str, chat_fn) -> str | None:
    """One text for a statement from several versions, by a model (`chat_fn(model, messages)`, Ollama's reply shape).
    None when the answer is not one usable statement: the caller falls back to the best-rated text."""
    shown = "\n\n".join(f"Version from {who} ({_record(row)}):\n## #{sid}\n{text}" for who, text, row in versions)
    r = chat_fn(model, [{"role": "system", "content": MERGE_PROMPT.format(sid=sid)},
                        {"role": "user", "content": shown}])
    answer = ((r or {}).get("message") or {}).get("content") or ""
    answer = re.sub(r"^```\w*\n|\n```\s*$", "", answer.strip())
    parts = wiki.STATEMENT.split(answer)
    if len(parts) != 3 or not re.search(r"^\*\*Do:\*\*\s*\S", parts[2], re.M):
        return None
    return parts[2].strip()


def merge(piece_id: str, variants: list[Variant], model: str | None = None, chat_fn=None) -> dict:
    """The proposal: the merged body and, per statement, what was decided and why. The person's own piece comes
    first and keeps its order; a statement only a colleague has goes right after the one it follows in their copy."""
    base = store.get(piece_id)
    if base is None:
        raise LookupError(f"no piece {piece_id!r} here: merge works on one of your pieces")
    mine = Variant(ME, base, stats(piece_id)["statements"], dict(blocks(base.body)[1]))
    preamble, order_pairs = blocks(base.body)
    order = [sid for sid, _ in order_pairs]
    groups: dict[str, dict[str, tuple[str, dict | None]]] = {sid: {ME: (mine.blocks[sid], mine.stats.get(sid))}
                                                              for sid in order}
    for v in variants:
        prev = None
        for sid, text in v.blocks.items():
            key = sid if sid in groups else None
            if key is None:                          # a different id for the same moment: the same statement
                key = next((k for k in order if v.owner not in groups[k] and k not in v.blocks
                            and _same_moment(_when(text), _when(groups[k][next(iter(groups[k]))][0]))), None)
            if key is None:
                key = sid
                groups[key] = {}
                order.insert(order.index(prev) + 1 if prev in order else len(order), key)
            groups[key][v.owner] = (text, v.stats.get(sid))
            prev = key
    every = [ME] + [v.owner for v in variants]
    body, decisions = [preamble] if preamble else [], []
    for sid in order:
        g = groups[sid]
        texts = {_norm(t) for t, _ in g.values()}
        total = {r: sum(int((row or {}).get(r) or 0) for _, row in g.values()) for r in RESULTS}
        rate, marked = _rate(total)
        if len(g) == 1 and len(every) > 1:
            who = next(iter(g))
            if marked >= MIN_MARKED and rate < NEUTRAL:
                decisions.append({"id": sid, "action": "dropped", "from": who,
                                  "why": f"only {_has(who)} it, and most of its tasks needed corrections or failed "
                                         f"({_record(total)})"})
                continue
            decisions.append({"id": sid, "action": "kept" if who == ME else "added", "from": who,
                              "why": f"only {_has(who)} it ({_record(total)})"})
            text = g[who][0]
        elif len(texts) == 1:
            decisions.append({"id": sid, "action": "same", "from": ME if ME in g else next(iter(g)),
                              "why": "the same in every copy that has it"})
            text = next(iter(g.values()))[0]
        else:
            ranked = sorted(g.items(), key=lambda kv: (_rate(kv[1][1])[0] if _rate(kv[1][1])[0] is not None
                                                       else NEUTRAL, _rate(kv[1][1])[1], kv[0] == ME), reverse=True)
            text = model_merge(sid, [(w, t, r) for w, (t, r) in ranked], model, chat_fn) if chat_fn else None
            if text:
                decisions.append({"id": sid, "action": "merged", "from": ", ".join(w for w, _ in ranked),
                                  "why": f"{model} merged the {len(ranked)} versions into one"})
            else:
                who = ranked[0][0]
                text = ranked[0][1][0]
                rec = "; ".join(f"{w} {_record(r)}" for w, (_, r) in ranked)
                why = (f"best record ({rec})" if any(_rate(r)[1] for _, (_, r) in ranked)
                       else "nobody marked these tasks yet: your text stays" if who == ME
                       else "nobody marked these tasks yet")
                if chat_fn:
                    why += "; the model's answer was not one usable statement"
                decisions.append({"id": sid, "action": "chosen", "from": who, "why": why})
        body.append(f"## #{sid}\n{text}" if sid != "steps" or len(order) > 1 else text)
    return {"piece": piece_id, "version": base.version, "sources": [f"{v.owner} (v{v.piece.version})" for v in variants],
            "body": "\n\n".join(body).strip() + "\n", "decisions": decisions,
            "changed": _norm("\n\n".join(body)) != _norm(base.body)}


def summary(r: dict) -> str:
    """The proposal in plain words, one line per decision that is not "the same everywhere"."""
    verbs = {"kept": "kept", "added": "added from", "chosen": "took the text of", "merged": "merged",
             "dropped": "dropped"}
    lines = [f"Merging {r['piece']} (yours, v{r['version']}) with {', '.join(r['sources']) or 'nobody'}:"]
    same = [d["id"] for d in r["decisions"] if d["action"] == "same"]
    if same:
        lines.append(f"  same everywhere: {', '.join(same)}")
    for d in r["decisions"]:
        if d["action"] == "same":
            continue
        who = f" {d['from']}" if d["action"] in ("added", "chosen") else ""
        lines.append(f"  {verbs[d['action']]}{who}: #{d['id']}, {d['why']}")
    if not r["changed"]:
        lines.append("  Nothing to change: your piece already has the best of each.")
    return "\n".join(lines)


def note(r: dict) -> str:
    n = {a: sum(d["action"] == a for d in r["decisions"]) for a in ("added", "chosen", "merged", "dropped")}
    words = {"added": "added", "chosen": "picked", "merged": "merged", "dropped": "dropped"}
    done = ", ".join(f"{words[k]} {v}" for k, v in n.items() if v)
    return f"merged with {', '.join(r['sources'])}" + (f": {done}" if done else "")


def proposal_file(piece_id: str) -> Path:
    return paths.home() / "guild" / f"{piece_id}.merged.md"


def write_proposal(r: dict, dest: Path | None = None) -> Path:
    """The proposal as a whole piece file, to read (or edit) before applying it."""
    p = store.get(r["piece"])
    p.body = r["body"]
    p.history = [f"proposal: {note(r)}"] + p.history
    dest = Path(dest) if dest else proposal_file(r["piece"])
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(store.render(p))
    return dest


def apply(r: dict) -> tuple[store.Piece, str]:
    """Save the proposal as a new version of the person's piece, the previous one kept in its history."""
    piece, diff = store.update(r["piece"], note(r), body=r["body"])
    try:
        wiki.rebuild()
    except OSError:
        pass
    return piece, diff
