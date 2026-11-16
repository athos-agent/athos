"""The dream cycle: what of the recent past goes into long-term memory, in three phases (after the bio-inspired model of
slow-wave replay, REM abstraction and consolidation).

    1 replay and prune   the events outside the live window (older than `keep_days`, or past `keep_bytes`, never the
                         last `min_keep_days`) are cut as a prefix of the live log, written to a compressed segment of
                         the archive, folded into the ledger and the rollups, and only then trimmed from the live log.
                         Nothing is deleted: every rollup can be rebuilt from the archive and the live log.
    2 abstraction        counting, no model: pieces used together, requests that keep finding no piece, pieces that
                         look like the same way of working, steps the person corrected again and again, pieces whose
                         Checks keep failing; and the star review `athos dream` always made (athos/consolidate.py).
    3 consolidation      what is worth keeping goes to long-term memory: a page per project (`projects/<name>.md`)
                         saying what is known about working there. A page without `written_by: athos` is the person's
                         and is never touched; an earlier page Athos wrote is kept in `projects/.history/`. No piece
                         file is written by the no-model cycle.

Every step can be interrupted and run again: a segment is written (atomically) before anything refers to it, the
ledger records which segments it folded, and the live log is trimmed only while it still starts with the segment's
exact bytes, under the same lock every append takes. One cycle runs at a time (`memory/.cycle.lock`). The hooks start
it detached, the way they start the verifier, when the live log passes `trigger_bytes` or `trigger_days`
(`maybe_spawn`); `athos memory cycle` runs it in the foreground. Each phase is one `memory_cycle` event.

The opt-in model pass (`memory.model.on`, off by default) is in athos/memory/dream_model.py.
"""

from __future__ import annotations

import datetime as _dt
import gzip
import zlib
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

from athos import memory, paths

LOCK_STALE_S = 15 * 60
PAIR_MIN = 3             # pieces used together in at least this many tasks
REPEAT_MIN = 2           # the same request, with no piece, at least this many times
STEP_EDITS_MIN = 2       # a step the person corrected by hand at least this many times
CHECK_FAILS_MIN = 2      # a piece whose own Check failed in at least this many reuses


# ------------------------------------------------------------------------------------------------ the lock
def lock_file() -> Path:
    return memory.root() / ".cycle.lock"


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def running() -> bool:
    try:
        data = json.loads(lock_file().read_text())
        return time.time() - float(data.get("at") or 0) < LOCK_STALE_S and _alive(int(data.get("pid") or 0))
    except (OSError, ValueError, TypeError):
        return False


def take_lock() -> bool:
    """Taken in one step (created only if absent), so two sessions never run a cycle at once; a lock left by a cycle
    that died (its process gone, or older than LOCK_STALE_S) is taken over."""
    memory.root().mkdir(parents=True, exist_ok=True)
    for _ in range(2):
        try:
            fd = os.open(lock_file(), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            if running():
                return False
            try:
                lock_file().unlink()
            except FileNotFoundError:
                pass
            continue
        with os.fdopen(fd, "w") as out:
            out.write(json.dumps({"pid": os.getpid(), "at": time.time()}))
        return True
    return False


def release_lock() -> None:
    try:
        lock_file().unlink()
    except FileNotFoundError:
        pass


# ------------------------------------------------------------------------------------------------ when
def _first_at(raw: bytes) -> str | None:
    for line in raw.split(b"\n", 50)[:50]:
        try:
            at = json.loads(line).get("at")
        except (ValueError, AttributeError):
            continue
        if isinstance(at, str):
            return at
    return None


def due(now: _dt.datetime | None = None) -> str:
    """Why a cycle should run now ("" when it need not): the live log is past `trigger_bytes`, its oldest event is
    older than `trigger_days`, a segment was left half done, or a live line names an archived task the rollups have
    not folded (a late mark or correction). Cheap enough for a hook: a stat and the first lines."""
    s = memory.settings()
    try:
        size = paths.events_file().stat().st_size
    except OSError:
        return ""
    if memory.pending_segment():
        return "resume"
    if size > int(s["trigger_bytes"]):
        return "size"
    try:
        with paths.events_file().open("rb") as f:
            head = f.read(65536)
    except OSError:
        head = b""
    first = _first_at(head)
    now = now or _now()
    if first and _days(now, first) > float(s["trigger_days"]):
        return "age"
    if memory.has_archive() and (memory.load_rollups() is None or memory.view().stale):
        return "late" if memory.load_rollups() is not None else "rollups"
    return ""


def _now() -> _dt.datetime:
    from athos import eval as ev
    return ev.now()


def _days(now: _dt.datetime, at: str) -> float:
    from athos import eval as ev
    t = ev._parse(at)
    if t is None:
        return 0.0
    if t.tzinfo is None:
        t = t.replace(tzinfo=_dt.timezone.utc)
    return (now - t).total_seconds() / 86400


def maybe_spawn(athos_cmd: Path, popen=subprocess.Popen) -> bool:
    """Stop hook: when a cycle is due and none is running, start `athos memory cycle --quiet` detached and at low
    priority, so no hook waits. Nothing starts with `memory.auto` off, or with ATHOS_SPAWN=off (the tests) unless a stub
    `popen` is passed."""
    if os.environ.get("ATHOS_SPAWN", "").lower() == "off" and popen is subprocess.Popen:
        return False
    if not memory.settings().get("auto") or running() or not due():
        return False
    argv = [sys.executable, str(athos_cmd), "memory", "cycle", "--quiet"]
    if os.name == "posix" and Path("/usr/bin/nice").exists():
        argv = ["/usr/bin/nice", "-n", "15", *argv]
    try:
        popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
              start_new_session=True, close_fds=True)
    except OSError:
        return False
    return True


# ------------------------------------------------------------------------------------------------ phase 1: the cut
def cut(raw: bytes, now: _dt.datetime, s: dict | None = None) -> int:
    """How many bytes at the start of the live log leave it: whole lines only, a prefix, oldest first. A line older
    than `keep_days` leaves; so does an older line while the live log would still be over `keep_bytes`, but never one
    of the last `min_keep_days`. A line whose time cannot be read goes with the line before it."""
    from athos import eval as ev
    s = s or memory.settings()
    floor_days = float(s["min_keep_days"])
    keep_days = max(float(s["keep_days"]), floor_days)    # never the last min_keep_days, whatever keep_days says
    keep_bytes = int(s["keep_bytes"])
    total, at, out, previous_old = len(raw), 0, 0, True
    while at < total:
        end = raw.find(b"\n", at)
        if end < 0:
            break                                         # a line still being written stays
        line = raw[at:end]
        try:
            stamp = json.loads(line).get("at")
        except (ValueError, AttributeError):
            stamp = None
        t = ev._parse(stamp) if isinstance(stamp, str) else None
        if t is None:
            old = previous_old
        else:
            age = _days(now, stamp)
            old = age > keep_days or (total - at > keep_bytes and age > floor_days)
        if not old:
            break
        previous_old = old
        at = end + 1
        out = at
    return out


def _next_id(segments: list[dict]) -> int:
    return (max((int(s["id"]) for s in segments), default=0)) + 1


def write_segment(data: bytes) -> dict:
    """The prefix as a new segment: compressed into a temporary file, synced, moved into place, and only then listed
    in the manifest (state `written`). Returns the manifest entry."""
    from athos import eval as ev
    man = memory.manifest()
    seg_id = _next_id(man["segments"])
    name = f"events-{seg_id:05d}.jsonl.gz"
    target = memory.archive_dir() / name
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name("." + name + ".tmp")
    with open(tmp, "wb") as out:
        out.write(gzip.compress(data, mtime=0))
        out.flush()
        os.fsync(out.fileno())
    os.replace(tmp, target)
    events = memory.decode(data)
    stamps = [e.get("at") for e in events if isinstance(e, dict) and isinstance(e.get("at"), str)]
    entry = {"id": seg_id, "file": name, "lines": data.count(b"\n"), "events": len(events), "bytes": len(data),
             "sha256": memory._sha(data), "first_at": min(stamps, default=None), "last_at": max(stamps, default=None),
             "state": "written", "written_at": ev._iso(ev.now())}
    man["segments"].append(entry)
    memory.write_json(memory.manifest_file(), man)
    return entry


def _set_state(seg_id: int, state: str) -> None:
    from athos import eval as ev
    man = memory.manifest()
    for s in man["segments"]:
        if s["id"] == seg_id:
            s["state"] = state
            s[f"{state}_at"] = ev._iso(ev.now())
    memory.write_json(memory.manifest_file(), man)


def fold_segment(entry: dict) -> dict:
    """Fold one segment into the ledger, once (the ledger lists the segments it folded), and write the ledger."""
    led = memory.load_ledger()
    if entry["id"] not in led["folded"]:
        memory.fold(led, memory.decode(memory.read_segment(entry)))
        led["folded"].append(entry["id"])
        memory.write_json(memory.ledger_file(), led)
    return led


def write_rollups(led: dict | None = None) -> int:
    """The rollups from the ledger and the live log as it is now (its archived prefix left out while it is still
    there), under the append lock so the mark of how much of the live log they saw is exact."""
    led = led if led is not None else memory.load_ledger()
    with paths.locked(paths.events_file()):
        raw = memory.live_raw()
        raw = raw[memory.live_skip(raw, memory.pending_segment()):]
        live = memory.decode(raw)
        roll = memory.aggregate(led, live, len(raw), memory._head_sha(raw))
        return memory.write_json(memory.rollups_file(), roll)


def prune(entry: dict) -> int:
    """Trim the segment's bytes from the start of the live log, under the lock every append takes, and only while the
    log still starts with exactly those bytes (so running it twice trims once). Lines an older Athos appended without
    the lock while the new file was being written are carried over. Returns the bytes trimmed."""
    log = paths.events_file()
    trimmed = 0
    with paths.locked(log):
        try:
            handle = open(log, "rb")
        except FileNotFoundError:
            handle = None
        if handle is not None:
            with handle:
                raw = handle.read()
                n = memory.live_skip(raw, entry)
                if n:
                    tmp = log.with_name("." + log.name + f".{uuid.uuid4().hex[:8]}.tmp")
                    with open(tmp, "wb") as out:
                        out.write(raw[n:])
                        out.flush()
                        os.fsync(out.fileno())
                    try:
                        os.chmod(tmp, os.stat(log).st_mode & 0o777)
                    except OSError:
                        pass
                    os.replace(tmp, log)
                    late = handle.read()             # written to the old file after it was read: not lost
                    if late:
                        with open(log, "ab") as out:
                            out.write(late)
                    trimmed = n
    _set_state(entry["id"], "pruned")
    return trimmed


def recover() -> dict:
    """Put the archive's table back in order, never deleting a segment: a temporary file of an interrupted write is
    dropped; a segment the manifest does not list (a cycle stopped between writing it and listing it, or a manifest
    lost) is listed again, `written` while the live log still starts with its bytes and `pruned` otherwise, and one
    that cannot be read is moved to `archive/damaged/`; a ledger that is unreadable or did not fold exactly the
    listed segments is folded again from them."""
    out = {"listed_again": 0, "damaged": 0, "ledger_rebuilt": False}
    folder = memory.archive_dir()
    if folder.is_dir():
        for f in folder.iterdir():
            if f.name.endswith(".tmp"):
                f.unlink(missing_ok=True)
        man = memory.manifest()
        listed = {e["file"] for e in man["segments"]}
        live = memory.live_raw()
        for f in sorted(folder.glob("events-*.jsonl.gz")):
            if f.name in listed:
                continue
            try:
                data = gzip.decompress(f.read_bytes())
                seg_id = int(f.name.split("-")[1].split(".")[0])
            except (OSError, EOFError, ValueError, zlib.error):
                (folder / "damaged").mkdir(exist_ok=True)
                os.replace(f, folder / "damaged" / f.name)
                out["damaged"] += 1
                continue
            events = memory.decode(data)
            stamps = [e.get("at") for e in events if isinstance(e, dict) and isinstance(e.get("at"), str)]
            entry = {"id": seg_id, "file": f.name, "lines": data.count(b"\n"), "events": len(events),
                     "bytes": len(data), "sha256": memory._sha(data), "first_at": min(stamps, default=None),
                     "last_at": max(stamps, default=None), "recovered": True}
            entry["state"] = "written" if memory.live_skip(live, entry) else "pruned"
            man["segments"].append(entry)
            out["listed_again"] += 1
        if out["listed_again"]:
            man["segments"].sort(key=lambda e: int(e["id"]))
            memory.write_json(memory.manifest_file(), man)
    segs = memory.manifest()["segments"]
    try:
        led = memory.load_ledger()
        consistent = led["folded"] == [e["id"] for e in segs if e.get("state") != "written"] or \
            led["folded"] == [e["id"] for e in segs]
    except paths.StateUnreadable:
        consistent = False
    if segs and not consistent:
        memory.write_json(memory.ledger_file(), memory.rebuild_ledger())
        out["ledger_rebuilt"] = True
    return out


def resume() -> dict:
    """Finish a segment a stopped cycle left half done (after `recover`)."""
    done = {"folded": 0, "pruned": 0, "bytes": 0, **recover()}
    entry = memory.pending_segment()
    if entry is None:
        return done
    if entry.get("state") == "written":
        led = fold_segment(entry)
        write_rollups(led)
        _set_state(entry["id"], "folded")
        done["folded"] += 1
    done["bytes"] = prune(entry)
    done["pruned"] += 1
    write_rollups()
    return done


def replay_and_prune(now: _dt.datetime | None = None) -> dict:
    """Phase 1: resume what a stopped cycle left, then cut the prefix outside the window, archive it, fold it, and
    trim it. With nothing to cut, the rollups are still refreshed when an archive exists (late lines, a deleted
    rollup file)."""
    now = now or _now()
    out = {"resumed": resume(), "archived_lines": 0, "archived_bytes": 0, "segment": None, "compressed": 0}
    raw = memory.live_raw()
    n = cut(raw, now)
    if n:
        entry = write_segment(raw[:n])
        led = fold_segment(entry)
        write_rollups(led)
        _set_state(entry["id"], "folded")
        prune(entry)
        out.update(archived_lines=entry["lines"], archived_bytes=entry["bytes"], segment=entry["id"],
                   compressed=memory.segment_path(entry).stat().st_size)
    if memory.has_archive():
        out["rollup_bytes"] = write_rollups()
    return out


# ------------------------------------------------------------------------------------------------ rebuild and check
def check_archive() -> list[dict]:
    """Every segment against its manifest entry: present, readable, the same bytes and sha256. Returns the failures."""
    bad = []
    for entry in memory.manifest()["segments"]:
        try:
            memory.read_segment(entry)
        except (OSError, ValueError, EOFError, gzip.BadGzipFile) as problem:
            bad.append({"segment": entry.get("file"), "problem": type(problem).__name__})
    return bad


def _canon(data) -> str:
    return json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def compare_rebuild() -> dict:
    """Fold the whole archive again and compare with `ledger.json`, then compute the rollups from that and compare
    with `rollups.json` (both against the live log as it is now, so the live mark is left out). Derived data that
    differs from its rebuild is a fault."""
    led = memory.rebuild_ledger()
    stored = memory.load_ledger()
    with paths.locked(paths.events_file()):
        raw = memory.live_raw()
        raw = raw[memory.live_skip(raw, memory.pending_segment()):]
        live = memory.decode(raw)
    fresh = memory.aggregate(led, live)
    roll = memory.load_rollups() or {}
    roll_cmp = {k: v for k, v in roll.items() if k != "live_mark"}
    fresh_cmp = {k: v for k, v in fresh.items() if k != "live_mark"}
    return {"ledger_equal": _canon(led) == _canon(stored), "rollups_equal": _canon(fresh_cmp) == _canon(roll_cmp),
            "rollups_present": bool(roll)}


def rebuild() -> dict:
    """Throw the derived files away and make them again from the archive (and the live log)."""
    led = memory.rebuild_ledger()
    memory.write_json(memory.ledger_file(), led)
    return {"ledger_bytes": memory.ledger_file().stat().st_size, "rollup_bytes": write_rollups(led)}


# ------------------------------------------------------------------------------------------------ phase 2: abstraction
def findings() -> dict:
    """What counting finds, over the whole history (the rollups and the live log, never the archive): pieces used
    together, requests that found no piece (counted per project, never quoted), near-duplicate pieces, steps the
    person corrected by hand again and again, pieces whose own Checks keep failing. Ids only for pieces that exist."""
    from athos import store, wiki
    v = memory.view()
    total = v.sums()
    pieces = {p.id: p for p in store.all_pieces()}
    pairs = sorted(((k.split("|"), n) for k, n in total["pairs"].items() if n >= PAIR_MIN),
                   key=lambda kv: (-kv[1], kv[0]))
    together = [{"pieces": ab, "tasks": n} for ab, n in pairs if all(p in pieces for p in ab)]
    route: dict = json.loads(json.dumps((v.rollups or {}).get("route") or {}))
    for e in v.of_type("route"):
        if e.get("request_kind") != "person":
            continue
        r = route.setdefault(e.get("project") or "-", {"requests": 0, "nothing": 0, "repeats": {}})
        r["requests"] = r.get("requests", 0) + 1
        if not e.get("chosen") and not e.get("delivery"):
            r["nothing"] = r.get("nothing", 0) + 1
            if e.get("request_sha"):
                r.setdefault("repeats", {})[e["request_sha"]] = r["repeats"].get(e["request_sha"], 0) + 1
    no_piece = [{"project": p, "requests": r.get("requests", 0), "nothing": r.get("nothing", 0),
                 "repeated": sum(1 for n in (r.get("repeats") or {}).values() if n >= REPEAT_MIN)}
                for p, r in sorted(route.items()) if r.get("nothing")]
    # Two pieces whose title and "when" share most of their words (the same test as `athos curate`), and statements
    # of two pages for the same moment that neither links to (wiki.overlaps): the same way of working twice.
    from athos import curate
    heads = {pid: curate._words(p.title + " " + p.when) for pid, p in pieces.items()}
    ids = sorted(heads)
    overlaps = [{"pieces": [a, b]} for i, a in enumerate(ids) for b in ids[i + 1:]
                if heads[a] and heads[b] and len(heads[a] & heads[b]) / len(heads[a] | heads[b]) >= curate.SIMILAR]
    seen = {tuple(o["pieces"]) for o in overlaps}
    for p in pieces.values():
        for ref in wiki.overlaps(p, list(pieces.values())):
            pair = tuple(sorted({x.strip().split("#", 1)[0] for x in ref.split("~")}))
            if len(pair) == 2 and pair not in seen:
                seen.add(pair)
                overlaps.append({"pieces": list(pair), "steps": ref})
    edits = dict((v.rollups or {}).get("step_edits") or {})
    for e in v.of_type("learned_from_edit"):
        if e.get("piece") and e.get("basis"):
            key = f"{e['piece']}#{e.get('statement') or ''}"
            edits[key] = edits.get(key, 0) + 1
    corrected = [{"piece": k.split("#", 1)[0], "step": k.split("#", 1)[1] or None, "edits": n}
                 for k, n in sorted(edits.items()) if n >= STEP_EDITS_MIN and k.split("#", 1)[0] in pieces]
    failing = []
    for pid in pieces:
        fails = sum(1 for e in v.grade_events(pid) if e.get("type") == "reuse" and "check_failed" in (e.get("basis")
                                                                                                    or []))
        if fails >= CHECK_FAILS_MIN:
            failing.append({"piece": pid, "check_failed": fails})
    return {"together": together, "no_piece": no_piece, "overlaps": overlaps, "corrected_steps": corrected,
            "checks_failing": failing}


def abstraction() -> dict:
    """Phase 2: the findings, kept in `memory/findings.json`, and the star review `athos dream` shows."""
    from athos import consolidate, eval as ev
    found = findings()
    found["at"] = ev._iso(ev.now())
    memory.write_json(memory.findings_file(), found)
    review = consolidate.run()
    return {"together": len(found["together"]), "no_piece_projects": len(found["no_piece"]),
            "overlaps": len(found["overlaps"]), "corrected_steps": len(found["corrected_steps"]),
            "checks_failing": len(found["checks_failing"]), "star_proposals": len(review.get("proposals") or [])}


# ------------------------------------------------------------------------------------------------ phase 3: consolidation
ATHOS_PAGE = "written_by: athos"


def _project_public(project: str, v: memory.View) -> bool:
    """Whether the project's sessions ran in a repository marked public (the latest route event that says), so its
    page names nothing a public repository may not."""
    routes = [e for e in v.of_type("route") if e.get("project") == project]
    if routes:
        return bool(routes[-1].get("public"))
    return bool(((v.rollups or {}).get("route") or {}).get(project, {}).get("public"))


def _play(project: str, total: dict) -> bool:
    from athos import curate
    pr = total["projects"].get(project) or {}
    return bool(curate.PLAY.search(project)) or (pr.get("tasks") and pr.get("scratch") == pr.get("tasks")) or \
        project in set(curate.state().get("ignore") or [])


def project_page(project: str, found: dict | None = None) -> str:
    """What is known about working in a project, counted from the log and the store, as the page says it: its ways of
    working with their uses and outcomes, the pieces used together, how often a request found nothing, and what to
    look at. It names only pieces that may be named in that project's own sessions (load.nameable); another
    project's pieces are only counted. No request is quoted."""
    from athos import eval as ev, load, store
    v = memory.view()
    total = v.sums()
    found = found if found is not None else findings()
    public = _project_public(project, v)
    pieces = [p for p in store.all_pieces() if load.nameable(p, project, public)]
    named = {p.id for p in pieces}
    pr = total["projects"].get(project) or {}
    lines = ["---", f"project: {project}", ATHOS_PAGE, f"updated: {ev.now().date().isoformat()}",
             "visibility: project", "---", f"# Working in {project}", "",
             "What Athos has seen of the work in this project, counted from its own log; no request is quoted. The "
             "dream cycle rewrites this page (earlier ones are in `projects/.history/`); delete the "
             f"`{ATHOS_PAGE}` line and it is yours: Athos will never touch it again.", ""]
    own = sorted((p for p in pieces if project in p.projects), key=lambda p: -total["pieces"].get(p.id, {}).get("uses", 0))
    lines.append("## Ways of working")
    for p in own:
        s = total["pieces"].get(p.id) or {}
        uses = (s.get("by_project") or {}).get(project, 0)
        status = store.status(p)
        lines.append(f"- `{p.id}` — {p.title}: used in {uses} task(s) here"
                     + (f", {s.get('ok', 0)} of {s.get('marked', 0)} marked good overall" if s.get("marked") else "")
                     + (f", last used {store.last_used(p)}" if store.last_used(p) else "")
                     + ("" if status == store.LEGACY else f", {status}"))
    if not own:
        lines.append("- none of its own yet")
    elsewhere = {pid: n for pid, s in total["pieces"].items() for proj, n in (s.get("by_project") or {}).items()
                 if proj == project and pid not in {p.id for p in own}}
    if elsewhere:
        shown = {pid: n for pid, n in elsewhere.items() if pid in named}
        hidden = sum(n for pid, n in elsewhere.items() if pid not in named)
        lines.append("- also used here: " + ", ".join(f"`{pid}` ×{n}" for pid, n in sorted(shown.items()))
                     + (("; " if shown else "") + f"{hidden} use(s) of pieces of other projects" if hidden else ""))
    pairs = [f for f in found.get("together") or [] if all(x in named for x in f["pieces"])
             and any(project in (store.get(x).projects if store.get(x) else []) for x in f["pieces"])]
    if pairs:
        lines += ["", "## Used together"]
        lines += [f"- `{a}` with `{b}` ({n} tasks)" for (a, b), n in ((f["pieces"], f["tasks"]) for f in pairs[:8])]
    nothing = next((f for f in found.get("no_piece") or [] if f["project"] == project), None)
    lines += ["", "## Activity", f"- {pr.get('tasks', 0)} task(s) recorded, {pr.get('ok', 0)} of {pr.get('marked', 0)}"
              " marked good"]
    if nothing:
        lines.append(f"- {nothing['nothing']} of {nothing['requests']} request(s) found no piece"
                     + (f"; {nothing['repeated']} came back more than once still without one" if nothing["repeated"]
                        else ""))
    look = []
    for f in found.get("overlaps") or []:
        if all(x in named for x in f["pieces"]) and any(x in {p.id for p in own} for x in f["pieces"]):
            look.append(f"- `{f['pieces'][0]}` and `{f['pieces'][1]}` look like the same way of working")
    for f in found.get("corrected_steps") or []:
        if f["piece"] in {p.id for p in own}:
            look.append(f"- `{f['piece']}`" + (f" step `{f['step']}`" if f["step"] else "")
                        + f" was corrected by hand {f['edits']} times")
    for f in found.get("checks_failing") or []:
        if f["piece"] in {p.id for p in own}:
            look.append(f"- `{f['piece']}`: its Check failed in {f['check_failed']} reuses")
    if look:
        lines += ["", "## To look at", *look]
    return "\n".join(lines) + "\n"


def _is_athos_page(text: str) -> bool:
    head = text.split("\n---", 1)[0] if text.startswith("---") else ""
    return ATHOS_PAGE in head.splitlines()


def write_project_page(project: str, text: str) -> str:
    """Write a project's page unless it is the person's (no `written_by: athos` in its frontmatter): `written`,
    `unchanged` or `person's`. An earlier page Athos wrote is kept in `projects/.history/` first."""
    target = memory.projects_dir() / f"{project}.md"
    try:
        before = target.read_text()
    except FileNotFoundError:
        before = None
    except (OSError, UnicodeDecodeError):
        return "person's"
    if before is not None and not _is_athos_page(before):
        return "person's"
    body = lambda t: "\n".join(l for l in (t or "").splitlines() if not l.startswith("updated: "))  # noqa: E731
    if before is not None and body(before) == body(text):
        return "unchanged"
    if before is not None:
        hist = memory.projects_dir() / ".history"
        hist.mkdir(parents=True, exist_ok=True)
        n = len(list(hist.glob(f"{project}.v*.md"))) + 1
        paths.write_atomic(hist / f"{project}.v{n}.md", before)
    paths.write_atomic(target, text)
    return "written"


def consolidation() -> dict:
    """Phase 3: the project pages. Projects that are tests or rehearsals get none."""
    v = memory.view()
    total = v.sums()
    found = findings()
    out = {"written": 0, "unchanged": 0, "person": 0, "projects": 0}
    for project in sorted(total["projects"]):
        if not project or project == "-" or _play(project, total):
            continue
        out["projects"] += 1
        what = write_project_page(project, project_page(project, found))
        out["person" if what == "person's" else what] += 1
    return out


# ------------------------------------------------------------------------------------------------ the cycle
def _event(run_id: str, phase: str, started: float, **counts) -> None:
    from athos import eval as ev
    ev.audit({"type": "memory_cycle", "run_id": run_id, "phase": phase,
              "duration_ms": round((time.perf_counter() - started) * 1000, 1), **counts},
             line=f"dream cycle {phase}: " + ", ".join(f"{k} {v}" for k, v in counts.items()
                                                        if not isinstance(v, (dict, list))))


def run(now: _dt.datetime | None = None, model: bool | None = None, runner=None) -> dict:
    """One whole cycle, under its lock: replay and prune, abstraction, consolidation, and (only when asked or turned
    on, and idle) the model pass. Returns what each phase did; `skipped` when another cycle holds the lock."""
    if not take_lock():
        return {"skipped": "another cycle is running"}
    run_id = uuid.uuid4().hex[:12]
    out: dict = {"run_id": run_id}
    try:
        t0 = time.perf_counter()
        before = memory.sizes()
        out["replay"] = replay_and_prune(now)
        after = memory.sizes()
        _event(run_id, "replay", t0, archived_lines=out["replay"]["archived_lines"],
               archived_bytes=out["replay"]["archived_bytes"], compressed_bytes=out["replay"]["compressed"],
               resumed=out["replay"]["resumed"], live_before=before["live"], live_after=after["live"],
               rollup_bytes=after["rollups"], segments=after["segments"])
        t1 = time.perf_counter()
        out["abstraction"] = abstraction()
        _event(run_id, "abstraction", t1, **out["abstraction"])
        t2 = time.perf_counter()
        out["consolidation"] = consolidation()
        _event(run_id, "consolidation", t2, **out["consolidation"])
        wanted = memory.settings()["model"].get("on") if model is None else model
        if wanted:
            from athos.memory import dream_model
            t3 = time.perf_counter()
            out["model"] = dream_model.run(runner=runner)
            _event(run_id, "model", t3, wrote=out["model"].get("wrote") or [],
                   **{k: v for k, v in out["model"].items() if not isinstance(v, (dict, list))})
        _event(run_id, "done", t0, spend_usd=(out.get("model") or {}).get("spend_usd", 0.0))
    finally:
        release_lock()
    return out


def status() -> dict:
    """The three layers' sizes and dates, whether a cycle is due or running, and the last one's outcome."""
    s = memory.sizes()
    roll = memory.load_rollups() or {}
    return {**s, "archived_tasks": roll.get("archived_tasks", 0), "archived_from": roll.get("first_at"),
            "archived_to": roll.get("last_at"), "due": due(), "running": running(), "settings": memory.settings()}
