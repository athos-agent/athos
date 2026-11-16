"""Long-term memory: the event log in three layers, so what the hooks read stays small however old the store is.

    short-term     `<home>/events.jsonl`, the raw events of a recent window (by age and by size). Hooks append to it.
    consolidated   `<home>/memory/`: the raw events outside the window, archived compressed and never deleted
                   (`archive/events-NNNNN.jsonl.gz`, with `archive/manifest.json` holding each segment's lines, bytes
                   and sha256), and what is derived from them: `ledger.json` (the archived events folded per task,
                   without any request text) and `rollups.json` (small sums per piece, project, platform and pair of
                   pieces, the grading history of learned pieces, the verifier's and the shadow runs' outcomes, the
                   stars). Both are rebuildable: deleting them and folding the archive again gives the same files.
    long-term      the wiki: the pieces in `know-how/`, and one page per project in `projects/` (athos/memory/cycle.py)

The dream cycle (athos/memory/cycle.py) moves a prefix of the live log into the archive and folds it; the hot paths
(the hooks and `athos status`) read only `rollups.json` and the live log through `View`, never the archive. Offline
commands (`athos report`, `audit`, `curate`, `bench route --from-store`, `repair`) read the whole history,
archive and live log (`eval.events`), and say so when an archive exists.

A segment is always a prefix of the live log at the moment it was cut, written before the live log is trimmed, so a
crash at any step leaves either the old live log or the new one, and the step is redone on the next run. While a
segment is written but the live log not yet trimmed, its lines are in both: readers skip them in the live log
(`live_skip`), the full history once the segment exists, the hot view once the rollups have folded it.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Iterable

from athos import paths

V = 1
DEFAULTS = {
    "auto": True,            # the hooks start the no-model cycle on their own when the live log passes the threshold
    "keep_days": 30,         # the live log keeps at least this many days...
    "keep_bytes": 4_000_000,  # ...and at most this many bytes, cutting older days if it has to...
    "min_keep_days": 8,      # ...but never the last this many days (the journal and the marks look a week back)
    "trigger_bytes": 6_000_000,  # the hooks start a cycle when the live log is larger than this...
    "trigger_days": 37,      # ...or its oldest event is older than this
    "model": {"on": False, "model": None, "max_usd_per_run": 0.5, "idle_minutes": 30},
    "associations_line": False,   # a frontier index line "often used with": off, since it did not help (REFERENCE)
}
PAIR_MIN = 3                       # two pieces used in at least this many of the same tasks are "often used together"


def partner(pid: str, pool_ids: set, skip: set) -> tuple[str, int] | None:
    """The piece most often used in the same task as `pid` (PAIR_MIN or more), among `pool_ids` and not in `skip`:
    from the rollups and the live log, never the archive."""
    best = None
    for key, n in view().sums()["pairs"].items():
        a, b = key.split("|", 1)
        other = b if a == pid else a if b == pid else None
        if other and n >= PAIR_MIN and other in pool_ids and other not in skip and (best is None or n > best[1]
                                                                                   or (n == best[1] and other < best[0])):
            best = (other, n)
    return best


def settings() -> dict:
    from athos import autolearn, start
    saved = start.config().get("memory")
    return autolearn._merge(DEFAULTS, saved if isinstance(saved, dict) else {})


# ------------------------------------------------------------------------------------------------ where
def root() -> Path:
    return paths.home() / "memory"


def archive_dir() -> Path:
    return root() / "archive"


def manifest_file() -> Path:
    return archive_dir() / "manifest.json"


def ledger_file() -> Path:
    return root() / "ledger.json"


def rollups_file() -> Path:
    return root() / "rollups.json"


def findings_file() -> Path:
    return root() / "findings.json"


def projects_dir() -> Path:
    """The long-term page per project (the person's own words there are never rewritten: athos/memory/cycle.py)."""
    return paths.home() / "projects"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_json(target: Path) -> dict:
    try:
        data = paths.read_state(target)
    except paths.StateUnreadable:
        raise
    return data if isinstance(data, dict) else {}


# ------------------------------------------------------------------------------------------------ the archive
def manifest() -> dict:
    """The archive's table of segments, oldest first; an absent manifest is an empty archive. A manifest that cannot
    be read is paths.StateUnreadable: never taken for an empty one, which would hide the archive."""
    data = _read_json(manifest_file())
    data.setdefault("v", V)
    data.setdefault("segments", [])
    return data


def has_archive() -> bool:
    try:
        return manifest_file().stat().st_size > 0 and bool(manifest()["segments"])
    except (OSError, paths.StateUnreadable):
        return manifest_file().exists()


def segment_path(entry: dict) -> Path:
    return archive_dir() / entry["file"]


def read_segment(entry: dict, check: bool = True) -> bytes:
    """A segment's raw bytes; ValueError when they do not match what the manifest recorded (an archive that fails its
    integrity check is never read as if it were whole)."""
    raw = gzip.decompress(segment_path(entry).read_bytes())
    if check and (len(raw) != entry.get("bytes") or _sha(raw) != entry.get("sha256")):
        raise ValueError(f"archive segment {entry.get('file')} fails its integrity check")
    return raw


def decode(raw: bytes) -> list:
    """The events in raw log bytes, oldest first; a line that is not JSON is skipped, as the live log's readers do."""
    out = []
    for line in raw.decode("utf-8", errors="replace").splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            pass
    return out


_ARCHIVE_CACHE: dict = {}


def archived_events() -> list:
    """Every archived event, oldest first (the whole archive, decompressed): for offline commands only. Cached per
    process until the manifest changes."""
    try:
        st = manifest_file().stat()
        key = (str(manifest_file()), st.st_ino, st.st_size, st.st_mtime_ns)
    except OSError:
        return []
    if _ARCHIVE_CACHE.get("key") != key:
        rows, bad = [], []
        for entry in manifest()["segments"]:
            try:
                raw = read_segment(entry)
            except ValueError:                   # read as it is, and said (`full_read_note`, `athos memory check`)
                bad.append(entry.get("file"))
                raw = read_segment(entry, check=False)
            except (OSError, EOFError):
                bad.append(entry.get("file"))
                continue
            rows.extend(decode(raw))
        _ARCHIVE_CACHE.update(key=key, rows=rows, bad=bad)
    return _ARCHIVE_CACHE["rows"]


def pending_segment() -> dict | None:
    """The newest segment whose prefix may still be at the start of the live log (written, the live log not trimmed
    yet: a cycle under way or interrupted), or None."""
    try:
        segs = manifest()["segments"]
    except paths.StateUnreadable:
        return None
    last = segs[-1] if segs else None
    return last if last and last.get("state") != "pruned" else None


def live_skip(raw: bytes, entry: dict | None) -> int:
    """How many bytes at the start of the live log are the segment's own (0 when the log no longer starts with it)."""
    if not entry:
        return 0
    n = int(entry.get("bytes") or 0)
    if n and len(raw) >= n and _sha(raw[:n]) == entry.get("sha256"):
        return n
    return 0


def live_raw() -> bytes:
    try:
        return paths.events_file().read_bytes()
    except OSError:
        return b""


# ------------------------------------------------------------------------------------------------ the ledger
GRADE_TYPES = ("verify", "reuse", "grade", "learn")
_GRADE_KEEP = ("type", "at", "piece", "version", "outcome", "tier", "basis", "from", "to", "decision", "body_sha",
               "paths_only", "bundle_clean", "model", "task_id", "status", "reason")
_SHADOW_KEEP = ("piece", "model", "equivalent", "platform", "case", "version", "at")
_RATING_KEEP = ("id", "stars", "piece", "step", "label", "version", "task_id", "did", "at")
NOISE = re.compile(r"^\s*(<(task-notification|system-reminder|agent-message)[\s>]|Athos · )")


def empty_ledger() -> dict:
    return {"v": V, "folded": [], "lines": 0, "rows": {}, "wrong": [], "grade": {}, "verify_done": [],
            "shadows": [], "told": [], "ratings": [], "route": {}, "misfires": {}, "step_edits": {},
            "lfe_wrong": [], "first_at": None, "last_at": None}


def load_ledger() -> dict:
    data = _read_json(ledger_file())
    return data if data.get("v") == V else empty_ledger()


def _compact_row(row: dict) -> dict:
    """A folded task as the ledger keeps it: no words of its request, only whether the journal would show it (`jr`),
    and its total tokens."""
    out = {k: v for k, v in row.items() if k not in ("request", "steps", "tokens")}
    if "request" in row:
        req = row.get("request") or ""
        out["jr"] = bool(req) and not NOISE.match(req)
    tokens = row.get("tokens")
    if isinstance(tokens, dict) and tokens.get("total") is not None:
        out["tok"] = tokens.get("total")
    elif "tok" in row:
        out["tok"] = row["tok"]
    return out


def fold(ledger: dict, events: Iterable[dict]) -> dict:
    """Fold archived events into the ledger, in order, the way `eval.tasks` folds the log (the same handlers), plus
    what the hot paths need of events that are not a task's: grading history, verifier and shadow outcomes, stars,
    route decisions (counted, never their words), dismissals and the person's edits per step."""
    from athos import eval as ev
    rows = ledger["rows"]
    wrong = {tuple(x) for x in ledger["wrong"]}
    done = {tuple(x) for x in ledger["verify_done"]}
    told = {tuple(x) for x in ledger["told"]}
    lfe_wrong = {tuple(x) for x in ledger["lfe_wrong"]}
    seq = int(ledger.get("lines") or 0)
    for e in events:
        seq += 1
        if not isinstance(e, dict):
            continue
        at = e.get("at") if isinstance(e.get("at"), str) else None
        if at:
            ledger["first_at"] = min(filter(None, [ledger.get("first_at"), at]))
            ledger["last_at"] = max(filter(None, [ledger.get("last_at"), at]))
        kind, tid, pid = e.get("type"), e.get("task_id"), e.get("piece")
        if tid and kind == "correction":
            if e.get("target") == "task_pieces":
                wrong.add((tid, e.get("piece")))
            elif e.get("target") == "learned_from_edit":
                lfe_wrong.add((tid, e.get("piece"), e.get("original_at")))
        elif tid:
            row = rows.get(tid)
            if row is None:
                row = rows[tid] = {"task_id": tid, "result": ev.UNMARKED, "pieces": [], "saved": [], "seq": seq}
            handler = ev._FOLD.get(kind)
            if handler:
                handler(row, e)
                rows[tid] = _compact_row(row)
            elif kind == "trail" and e.get("kind") == "step" and pid:
                row.setdefault("walked", [])
                if pid not in row["walked"]:
                    row["walked"].append(pid)
            elif kind == "piece_opened" and pid:
                row.setdefault("opened", [])
                if pid not in row["opened"]:
                    row["opened"].append(pid)
        if kind in GRADE_TYPES and pid:
            ledger["grade"].setdefault(pid, []).append({k: e[k] for k in _GRADE_KEEP if k in e})
        if kind == "verify" and e.get("outcome") in ("pass", "fail") and pid:
            done.add((pid, e.get("version")))
        elif kind == "shadow":
            ledger["shadows"].append({k: e[k] for k in _SHADOW_KEEP if k in e})
        elif kind == "handoff_told":
            told.add((pid, e.get("model")))
        elif kind == "rating" and pid:
            ledger["ratings"].append({k: e[k] for k in _RATING_KEEP if k in e})
        elif kind == "route" and e.get("request_kind") == "person":
            r = ledger["route"].setdefault(e.get("project") or "-", {"requests": 0, "nothing": 0, "chosen": {},
                                                                    "offered": {}, "named_how": {}, "repeats": {}})
            r["requests"] += 1
            for c in e.get("chosen") or []:
                r["chosen"][c] = r["chosen"].get(c, 0) + 1
            for c in e.get("offered") or []:
                r["offered"][c] = r["offered"].get(c, 0) + 1
            for d in (e.get("named_how") or {}).values():
                r["named_how"][d] = r["named_how"].get(d, 0) + 1
            for d, n in (e.get("named_how_count") or {}).items():
                r["named_how"][d] = r["named_how"].get(d, 0) + int(n or 0)
            if not e.get("chosen") and not e.get("delivery"):
                r["nothing"] += 1
                sha = e.get("request_sha")
                if sha:                                   # the same request again, still with no piece: counted
                    r["repeats"][sha] = r["repeats"].get(sha, 0) + 1
                    if len(r["repeats"]) > 4000:
                        r["repeats"] = {k: v for k, v in r["repeats"].items() if v > 1}
        elif kind == "misfire" and pid:
            ledger["misfires"][pid] = ledger["misfires"].get(pid, 0) + 1
        elif kind == "learned_from_edit" and pid and e.get("basis") and \
                (tid, pid, e.get("at")) not in lfe_wrong:
            key = f"{pid}#{e.get('statement') or ''}"
            ledger["step_edits"][key] = ledger["step_edits"].get(key, 0) + 1
    ledger["lines"] = seq
    ledger["wrong"] = sorted([list(x) for x in wrong], key=str)
    ledger["verify_done"] = sorted([list(x) for x in done], key=str)
    ledger["told"] = sorted([list(x) for x in told], key=str)
    ledger["lfe_wrong"] = sorted([list(x) for x in lfe_wrong], key=str)
    return ledger


def rebuild_ledger() -> dict:
    """The ledger folded again from the whole archive, segment by segment (what `ledger.json` must equal)."""
    led = empty_ledger()
    for entry in manifest()["segments"]:
        fold(led, decode(read_segment(entry)))
        led["folded"].append(entry["id"])
    return led


# ------------------------------------------------------------------------------------------------ sums over tasks
def finished(rows: Iterable[dict], wrong: set, copy: bool = True) -> list[dict]:
    """Folded rows as `eval.tasks` returns them: only tasks that stopped, with the uses `athos repair` corrected left
    out, in the order they first appeared. `copy` False changes the rows themselves (the view's own)."""
    out = []
    for row in sorted(rows, key=lambda r: r.get("seq") or 0):
        if "ended" not in row:
            continue
        t = dict(row) if copy else row
        if wrong:
            t["pieces"] = [p for p in row.get("pieces") or [] if (row["task_id"], p) not in wrong]
        out.append(t)
    return out


def _tok(t: dict):
    if "tok" in t:
        return t["tok"]
    tokens = t.get("tokens") or {}
    return tokens.get("total") if isinstance(tokens, dict) else None


def _add(d: dict, key, n=1) -> None:
    d[key] = d.get(key, 0) + n


def sums(tasks: list[dict]) -> dict:
    """What the hot paths add up over tasks, in a form where two disjoint sets of tasks merge by adding (`merge`):
    per piece its uses and outcomes by platform, tier and project, its last use, means' sums, its baseline (the first
    task that saved it without using it); per project its tasks, the ones the journal would show and the pieces they
    used; the platforms seen; and how often two pieces were used in the same task."""
    from athos import tiers
    out: dict = {"tasks": 0, "pieces": {}, "projects": {}, "platforms": {}, "pairs": {}}
    for t in tasks:
        out["tasks"] += 1
        plat, proj, res = t.get("platform"), t.get("project"), t.get("result")
        if plat:
            _add(out["platforms"], plat)
        used = t.get("pieces") or []
        for pid in used:
            p = out["pieces"].setdefault(pid, {"uses": 0, "ok": 0, "marked": 0, "by_platform": {}, "by_tier": {},
                                               "by_project": {}, "outcomes": {}, "last_used": "", "dur": [0.0, 0],
                                               "tok": [0, 0], "rc": [0, 0], "bars": {}})
            p["uses"] += 1
            p["ok"] += res == "ok"
            p["marked"] += res != "unevaluated"
            _add(p["by_platform"], plat or "")
            _add(p["by_tier"], tiers.tier_of(t.get("model")) if t.get("model") else "unknown")
            _add(p["by_project"], proj or "-")
            _add(p["outcomes"], res)
            p["last_used"] = max(p["last_used"], (t.get("ended") or "")[:10])
            if t.get("duration_s") is not None:
                p["dur"][0] += t["duration_s"]
                p["dur"][1] += 1
            if _tok(t) is not None:
                p["tok"][0] += _tok(t)
                p["tok"][1] += 1
            if t.get("request_chars") is not None:
                p["rc"][0] += t["request_chars"]
                p["rc"][1] += 1
        for pid in t.get("saved") or []:
            if pid in used:
                continue
            p = out["pieces"].setdefault(pid, {"uses": 0, "ok": 0, "marked": 0, "by_platform": {}, "by_tier": {},
                                               "by_project": {}, "outcomes": {}, "last_used": "", "dur": [0.0, 0],
                                               "tok": [0, 0], "rc": [0, 0], "bars": {}})
            if not p.get("base") or (t.get("seq") or 0) < p["base"]["seq"]:
                p["base"] = {"seq": t.get("seq") or 0, "task_id": t["task_id"], "started": t.get("started"),
                             "request_chars": t.get("request_chars"), "duration_s": t.get("duration_s"),
                             "tokens": _tok(t)}
        if proj:
            pr = out["projects"].setdefault(proj, {"tasks": 0, "journal": 0, "journal_pieces": {}, "last": None,
                                                   "scratch": 0, "ok": 0, "marked": 0})
            pr["tasks"] += 1
            pr["scratch"] += bool(t.get("scratch"))
            pr["ok"] += res == "ok"
            pr["marked"] += res != "unevaluated"
            if t.get("jr", bool(t.get("request")) and not NOISE.match(t.get("request") or "")):
                pr["journal"] += 1
                for pid in used:
                    _add(pr["journal_pieces"], pid)
            first = (used or t.get("saved") or [None])[0]
            if first and (pr["last"] is None or (t.get("seq") or 0) > pr["last"][0]):
                pr["last"] = [t.get("seq") or 0, first]
        together = sorted(set(used) | set(t.get("opened") or []))
        for i, a in enumerate(together):
            for b in together[i + 1:]:
                _add(out["pairs"], f"{a}|{b}")
    # The bars count a piece's uses per project and platform after the run that taught it (its baseline).
    for t in tasks:
        for pid in t.get("pieces") or []:
            p = out["pieces"][pid]
            base = p.get("base")
            bar = p["bars"].setdefault(f"{t.get('project') or ''}|{t.get('platform') or ''}",
                                       {"all": [0, 0, 0, 0, 0], "after": [0, 0, 0, 0, 0]})
            row = [1, int(t.get("result") == "ok"), int(t.get("result") != "unevaluated"),
                   t.get("request_chars") or 0, int(t.get("request_chars") is not None)]
            bar["all"] = [a + b for a, b in zip(bar["all"], row)]
            if base is None or (t.get("started") or "") >= (base.get("started") or ""):
                bar["after"] = [a + b for a, b in zip(bar["after"], row)]
    return out


def merge_counts(a: dict, b: dict) -> dict:
    out = dict(a)
    for k, v in b.items():
        out[k] = out.get(k, 0) + v
    return out


def merge(a: dict, b: dict) -> dict:
    """Two `sums` over disjoint sets of tasks, added (b's tasks come after a's)."""
    out = {"tasks": a["tasks"] + b["tasks"], "platforms": merge_counts(a["platforms"], b["platforms"]),
           "pairs": merge_counts(a["pairs"], b["pairs"]), "pieces": {}, "projects": {}}
    for pid in a["pieces"].keys() | b["pieces"].keys():
        x, y = a["pieces"].get(pid), b["pieces"].get(pid)
        if x is None or y is None:
            out["pieces"][pid] = json.loads(json.dumps(x or y))
            continue
        m = {k: x[k] + y[k] for k in ("uses", "ok", "marked")}
        for k in ("by_platform", "by_tier", "by_project", "outcomes"):
            m[k] = merge_counts(x[k], y[k])
        m["last_used"] = max(x["last_used"], y["last_used"])
        for k in ("dur", "tok", "rc"):
            m[k] = [x[k][0] + y[k][0], x[k][1] + y[k][1]]
        bases = [s for s in (x.get("base"), y.get("base")) if s]
        if bases:
            m["base"] = min(bases, key=lambda s: s["seq"])
        # The bars count uses after the baseline. With the baseline among the earlier tasks, every later use is
        # after it; with it among the later tasks only, the earlier uses came before it (they started earlier).
        m["bars"] = {}
        for key in x["bars"].keys() | y["bars"].keys():
            bx = x["bars"].get(key, {"all": [0] * 5, "after": [0] * 5})
            by = y["bars"].get(key, {"all": [0] * 5, "after": [0] * 5})
            if x.get("base"):
                after = [i + j for i, j in zip(bx["after"], by["all"])]
            elif y.get("base"):
                after = list(by["after"])
            else:
                after = [i + j for i, j in zip(bx["all"], by["all"])]
            m["bars"][key] = {"all": [i + j for i, j in zip(bx["all"], by["all"])], "after": after}
        out["pieces"][pid] = m
    for name in a["projects"].keys() | b["projects"].keys():
        x, y = a["projects"].get(name), b["projects"].get(name)
        if x is None or y is None:
            out["projects"][name] = json.loads(json.dumps(x or y))
            continue
        last = max([v for v in (x["last"], y["last"]) if v], key=lambda v: v[0], default=None)
        out["projects"][name] = {**{k: x[k] + y[k] for k in ("tasks", "journal", "scratch", "ok", "marked")},
                                 "journal_pieces": merge_counts(x["journal_pieces"], y["journal_pieces"]),
                                 "last": last}
    return out


def _walked(rows: Iterable[dict]) -> dict:
    """In how many tasks each page was walked (a step of it on the trail), finished or not: the star review's
    trajectories."""
    out: dict = {}
    for r in rows:
        for pid in r.get("walked") or []:
            _add(out, pid)
    return out


# ------------------------------------------------------------------------------------------------ the rollups
def _task_ids(events: Iterable) -> set:
    return {e.get("task_id") for e in events if isinstance(e, dict) and e.get("task_id")}


def aggregate(ledger: dict, live: list, live_bytes: int = 0, live_head: str = "") -> dict:
    """The rollups: `sums` over the archived tasks that no live event mentions (the others, the boundary, are kept
    whole in `boundary` so a hot reader folds their live lines on top of them), and the archived history of the
    events the hot paths read besides tasks. `live_bytes` and `live_head`: how much of the live log was looked at, so
    a reader can tell a live line written later (an `athos mark` of an archived task, say) from one already known."""
    boundary_ids = _task_ids(live) & ledger["rows"].keys()
    wrong = {tuple(x) for x in ledger["wrong"]}
    archived = finished((r for tid, r in ledger["rows"].items() if tid not in boundary_ids), wrong)
    return {"v": V, "through": ledger["folded"][-1] if ledger["folded"] else None, "lines": ledger["lines"],
            "first_at": ledger.get("first_at"), "last_at": ledger.get("last_at"),
            "archived_tasks": sum(1 for r in ledger["rows"].values() if "ended" in r),
            "sums": sums(archived),
            "boundary": {tid: ledger["rows"][tid] for tid in sorted(boundary_ids)},
            "wrong": ledger["wrong"], "grade": ledger["grade"], "verify_done": ledger["verify_done"],
            "shadows": ledger["shadows"], "told": ledger["told"], "ratings": ledger["ratings"],
            "rated_results": {r["task_id"]: ledger["rows"][r["task_id"]].get("result")
                              for r in ledger["ratings"] if r.get("task_id") in ledger["rows"]},
            "walked": _walked(r for tid, r in ledger["rows"].items() if tid not in boundary_ids),
            "route": ledger["route"], "misfires": ledger["misfires"], "step_edits": ledger["step_edits"],
            "live_mark": {"bytes": live_bytes, "head": live_head}}


def load_rollups() -> dict | None:
    """The rollups as written, or None when there are none (no archive yet, or deleted: then the hot view reads the
    live log alone, which is then the whole history)."""
    try:
        st = rollups_file().stat()
    except OSError:
        return None
    key = (str(rollups_file()), st.st_ino, st.st_size, st.st_mtime_ns)
    if _ROLLUP_CACHE.get("key") != key:
        try:
            data = _read_json(rollups_file())
        except paths.StateUnreadable:
            data = {}
        _ROLLUP_CACHE.update(key=key, data=data if data.get("v") == V else None)
    return _ROLLUP_CACHE["data"]


_ROLLUP_CACHE: dict = {}


def write_json(target: Path, data: dict) -> int:
    text = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    paths.write_atomic(target, text)
    return len(text.encode())


# ------------------------------------------------------------------------------------------------ the hot view
def _head_sha(raw: bytes) -> str:
    end = raw.find(b"\n")
    return _sha(raw[:end if end >= 0 else len(raw)])[:16] if raw else ""


class View:
    """What a hot path may read: the rollups and the live log, never the archive. With no archive it is exactly the
    live log, which is then the whole history. Built once per hook process (`view()`), rebuilt when either file
    changes."""

    def __init__(self):
        self.rollups = load_rollups()
        raw = live_raw()
        entry = pending_segment()
        skip = 0
        if entry and self.rollups and self.rollups.get("through") == entry.get("id"):
            skip = live_skip(raw, entry)             # folded already: the live copy of the segment is not counted twice
        raw = raw[skip:]
        mark = (self.rollups or {}).get("live_mark") or {}
        known = int(mark.get("bytes") or 0) if mark.get("head") and mark.get("head") == _head_sha(raw) else 0
        # The live log decoded once; `cut`: how many of its lines the rollups already looked at.
        cut = raw[:known].count(b"\n") if known else 0
        self.events, numbers = [], []
        for n, line in enumerate(raw.decode("utf-8", errors="replace").split("\n")):
            if not line:
                continue
            try:
                self.events.append(json.loads(line))
            except ValueError:            # a half-written or hand-edited line is skipped, never fatal
                continue
            numbers.append(n)
        # Lines written after the rollups were made that name an archived task we know nothing of: a late mark or a
        # correction of a task the cycle archived. Left out until a cycle folds them (`stale` asks for one).
        self.stale = False
        self._late: set = set()
        if self.rollups is not None:
            started = {e.get("task_id") for e in self.events if isinstance(e, dict) and e.get("type") == "task_start"}
            boundary = self.rollups.get("boundary") or {}
            for e, n in zip(self.events, numbers):
                if n < cut or not isinstance(e, dict):
                    continue
                tid = e.get("task_id")
                if tid and tid not in started and tid not in boundary and e.get("type") in (
                        "task_end", "mark", "correction"):
                    self._late.add(tid)
            self.stale = bool(self._late)
        self._tasks = None
        self._rows: dict = {}
        self._sums = None

    # -- tasks
    def tasks(self) -> list[dict]:
        """The tasks of the live log, with those an archived line began (the boundary) folded on top of their
        archived part: `eval.tasks` over the recent window. Order: as they first appeared."""
        if self._tasks is None:
            from athos import eval as ev
            boundary = {tid: dict(r) for tid, r in ((self.rollups or {}).get("boundary") or {}).items()}
            wrong = {tuple(x) for x in (self.rollups or {}).get("wrong") or []}
            base = int((self.rollups or {}).get("lines") or 0)
            rows: dict = {tid: {**r, "pieces": list(r.get("pieces") or []), "saved": list(r.get("saved") or [])}
                          for tid, r in boundary.items()}
            for i, line in enumerate(self.events, 1):
                if not isinstance(line, dict) or not line.get("task_id") or line["task_id"] in self._late:
                    continue
                tid = line["task_id"]
                if line.get("type") == "correction":
                    if line.get("target") == "task_pieces":
                        wrong.add((tid, line.get("piece")))
                    continue
                row = rows.get(tid)
                if row is None:
                    row = rows[tid] = {"task_id": tid, "result": ev.UNMARKED, "pieces": [], "saved": [],
                                       "seq": base + i}
                handler = ev._FOLD.get(line.get("type"))
                if handler:
                    handler(row, line)
                elif line.get("type") == "trail" and line.get("kind") == "step" and line.get("piece"):
                    row.setdefault("walked", [])
                    if line["piece"] not in row["walked"]:
                        row["walked"].append(line["piece"])
                elif line.get("type") == "piece_opened" and line.get("piece"):
                    row.setdefault("opened", [])
                    if line["piece"] not in row["opened"]:
                        row["opened"].append(line["piece"])
            self._rows = rows
            self._tasks = finished(rows.values(), wrong, copy=False)
        return self._tasks

    def walked(self) -> dict:
        """`_walked` over the whole history: archived counts plus the recent rows (finished or not)."""
        self.tasks()
        return merge_counts((self.rollups or {}).get("walked") or {}, _walked(self._rows.values()))

    def bars(self, project: str | None = None) -> dict | None:
        """`eval.bars` over the whole history: the piece this project used last, and per agent its uses here since
        the run that taught it, how many were marked good, and how much shorter the requests were."""
        from athos import eval as ev, store
        total = self.sums()
        here = [t for t in self.tasks() if project is None or t.get("project") == project]
        last = next((t for t in reversed(here) if t["pieces"] or t["saved"]), None)
        if last is not None:
            pid = (last["pieces"] or last["saved"])[0]
        else:
            arch = ((self.rollups or {}).get("sums") or {}).get("projects") or {}
            marks = [v["last"] for k, v in arch.items() if v.get("last") and (project is None or k == project)]
            if not marks:
                return None
            pid = max(marks, key=lambda m: m[0])[1]
        p = total["pieces"].get(pid) or {}
        base = p.get("base")
        base_chars = base.get("request_chars") if base else None
        piece = store.get(pid)
        rows = []
        for platform, label in ev.AGENTS:
            sel = [b["after"] for key, b in (p.get("bars") or {}).items()
                   if key.rsplit("|", 1)[1] == platform and (project is None or key.rsplit("|", 1)[0] == project)]
            n, ok, judged, rc, rc_n = [sum(x[i] for x in sel) for i in range(5)] if sel else [0] * 5
            if platform in ev.OPTIONAL_AGENTS and not n and not ev.installed(platform) and \
                    not total["platforms"].get(platform):
                continue
            mean_chars = rc / rc_n if rc_n else None
            rows.append({"platform": platform, "label": label, "uses": n, "evaluated": judged, "ok": ok,
                         "success_rate": ok / judged if judged else None, "mean_request_chars": mean_chars,
                         "prompt_saved": (base_chars - mean_chars) / base_chars
                         if base_chars and mean_chars is not None else None})
        return {"piece": pid, "title": piece.title if piece else pid, "baseline_request_chars": base_chars,
                "agents": rows}

    def sums(self) -> dict:
        """`sums` over the whole history: the rollups' archived part plus the recent tasks."""
        if self._sums is None:
            recent = sums(self.tasks())
            arch = (self.rollups or {}).get("sums")
            self._sums = merge(arch, recent) if arch else recent
        return self._sums

    # -- what the hot paths ask
    def record(self, pid: str) -> dict:
        """`eval.record` over the whole history."""
        from athos import eval as ev
        p = self.sums()["pieces"].get(pid)
        labels = dict(ev.AGENTS)
        if not p:
            return {"uses": 0, "ok": 0, "marked": 0, "agents": []}
        agents = sorted({labels.get(k, k) for k, n in p["by_platform"].items() if n and k})
        return {"uses": p["uses"], "ok": p["ok"], "marked": p["marked"], "agents": agents}

    def of_type(self, *kinds: str) -> list[dict]:
        return [e for e in self.events if isinstance(e, dict) and e.get("type") in kinds]

    def grade_events(self, pid: str) -> list[dict]:
        old = ((self.rollups or {}).get("grade") or {}).get(pid) or []
        return list(old) + [e for e in self.events if isinstance(e, dict) and e.get("piece") == pid
                            and e.get("type") in GRADE_TYPES]

    def verify_done(self) -> set:
        done = {tuple(x) for x in (self.rollups or {}).get("verify_done") or []}
        done |= {(e.get("piece"), e.get("version")) for e in self.of_type("verify")
                 if e.get("outcome") in ("pass", "fail")}
        return done

    def shadows(self) -> list[dict]:
        return list((self.rollups or {}).get("shadows") or []) + self.of_type("shadow")

    def told(self) -> set:
        return {tuple(x) for x in (self.rollups or {}).get("told") or []} | \
            {(e.get("piece"), e.get("model")) for e in self.of_type("handoff_told")}

    def ratings(self) -> list[dict]:
        return list((self.rollups or {}).get("ratings") or []) + self.of_type("rating")

    def results(self) -> dict:
        """The verdict of every task a rating points at, and of every recent task: what the star review needs."""
        out = dict((self.rollups or {}).get("rated_results") or {})
        out.update({t["task_id"]: t.get("result") for t in self.tasks()})
        for e in self.of_type("mark"):
            if e.get("task_id") in out:
                out[e["task_id"]] = e.get("result")
        return out


_VIEW: dict = {}


def view() -> View:
    """The hot view, rebuilt only when the live log, the rollups or the manifest changed."""
    key = []
    for f in (paths.events_file(), rollups_file(), manifest_file()):
        try:
            st = f.stat()
            key.append((str(f), st.st_ino, st.st_size, st.st_mtime_ns))
        except OSError:
            key.append((str(f), None))
    key = tuple(key)
    if _VIEW.get("key") != key:
        _VIEW.update(key=key, view=View())
    return _VIEW["view"]


def full_read_note() -> str:
    """What an offline command says when it read the archive too ("" without one)."""
    if not has_archive():
        return ""
    try:
        segs = manifest()["segments"]
    except paths.StateUnreadable:
        return "history: the archive's manifest cannot be read; only the live log was read"
    lines = sum(int(s.get("lines") or 0) for s in segs)
    bad = _ARCHIVE_CACHE.get("bad") or []
    return (f"history: {lines} archived event(s) in {len(segs)} segment(s) read with the live log ({archive_dir()})"
            + (f"; {len(bad)} segment(s) fail their integrity check (`athos memory check`)" if bad else ""))


def sizes() -> dict:
    """Bytes of each layer: the live log, the archive, the ledger and the rollups."""
    def size(f: Path) -> int:
        try:
            return f.stat().st_size
        except OSError:
            return 0
    try:
        segs = manifest()["segments"]
    except paths.StateUnreadable:
        segs = []
    return {"live": size(paths.events_file()), "archive": sum(size(segment_path(s)) for s in segs),
            "archive_raw": sum(int(s.get("bytes") or 0) for s in segs), "segments": len(segs),
            "ledger": size(ledger_file()), "rollups": size(rollups_file())}


def os_fsync(path: Path) -> None:
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)
