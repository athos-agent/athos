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

PAIR_MIN = 3             # pieces used together in at least this many tasks
REPEAT_MIN = 2           # the same request, with no piece, at least this many times
STEP_EDITS_MIN = 2       # a step the person corrected by hand at least this many times
CHECK_FAILS_MIN = 2      # a piece whose own Check failed in at least this many reuses


# ------------------------------------------------------------------------------------------------ the lock
def lock_file() -> Path:
    return memory.root() / ".cycle.lock"


def _alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


_HELD: dict = {}


def _flock():
    try:
        import fcntl
    except ImportError:                                  # pragma: no cover - not on POSIX
        return None
    return fcntl


def running() -> bool:
    """Whether a cycle holds the lock now (this process or another). The lock is an `flock` held for the whole run,
    so it goes with the process that held it, however it ended: nothing about it is ever stale."""
    if _HELD:
        return True
    fcntl = _flock()
    try:
        fd = os.open(lock_file(), os.O_RDWR)
    except OSError:
        return False
    try:
        if fcntl is not None:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return True
            except OSError:
                return _linked_holder_alive()
            fcntl.flock(fd, fcntl.LOCK_UN)
            return False
        return _linked_holder_alive()
    finally:
        os.close(fd)


def take_lock() -> bool:
    """One cycle at a time: an exclusive `flock` on `memory/.cycle.lock`, taken without waiting and held until
    `release_lock` (or the process ends), so it cannot be taken from a live process, and two processes can never both
    hold it. Where the filesystem has no `flock`, a lock file made whole before it is linked into place, taken over
    only when the process that made it is gone."""
    memory.root().mkdir(parents=True, exist_ok=True)
    if _HELD:
        return False
    fcntl = _flock()
    if fcntl is not None:
        fd = os.open(lock_file(), os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(fd)
            return False
        except OSError:
            os.close(fd)
            return _take_by_link()
        try:
            os.ftruncate(fd, 0)
            os.write(fd, json.dumps({"pid": os.getpid(), "at": time.time()}).encode())
        except OSError:
            pass
        _HELD["fd"] = fd
        return True
    return _take_by_link()


def _linked_holder_alive() -> bool:
    try:
        data = json.loads(lock_file().read_text() or "{}")
        return _alive(int(data.get("pid") or 0))
    except (OSError, ValueError, TypeError):
        return False


def _take_by_link() -> bool:
    """No `flock` here: the lock file is written whole under a unique name and linked into place (never seen empty);
    one whose process is gone is taken over."""
    mine = lock_file().with_name(f".cycle.lock.{os.getpid()}.{uuid.uuid4().hex[:6]}")
    mine.write_text(json.dumps({"pid": os.getpid(), "at": time.time()}))
    try:
        for _ in range(2):
            try:
                os.link(mine, lock_file())
                _HELD["link"] = mine.read_text()
                return True
            except FileExistsError:
                if _linked_holder_alive():
                    return False
                lock_file().unlink(missing_ok=True)
            except OSError:
                return False
        return False
    finally:
        mine.unlink(missing_ok=True)


def release_lock() -> None:
    fd = _HELD.pop("fd", None)
    if fd is not None:
        fcntl = _flock()
        try:
            if fcntl is not None:
                fcntl.flock(fd, fcntl.LOCK_UN)
        except OSError:
            pass
        finally:
            os.close(fd)
    text = _HELD.pop("link", None)
    if text is not None:
        try:
            if lock_file().read_text() == text:       # only our own lock, never one another process took since
                lock_file().unlink()
        except OSError:
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


def triggers(s: dict | None = None) -> tuple[int, float]:
    """`trigger_bytes` and `trigger_days` as they act: always past what the window keeps (`keep_bytes`, `keep_days`),
    or a cycle would be due that can archive nothing."""
    s = s or memory.settings()
    keep_days = max(float(s["keep_days"]), float(s["min_keep_days"]))
    return max(int(s["trigger_bytes"]), int(s["keep_bytes"]) + 1), max(float(s["trigger_days"]), keep_days + 1)


def state_file() -> Path:
    return memory.root() / "cycle-state.json"


def _state() -> dict:
    try:
        data = json.loads(state_file().read_text())
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


BACKOFF_S = 3600              # a cycle that could not make progress waits this long before the hooks start one again,
BACKOFF_MAX_S = 24 * 3600     # ...twice as long each time it still cannot, up to a day


def backing_off(reason: str, now: float | None = None) -> bool:
    """Whether the last cycle could not make progress (or raised) for this same reason, recently enough that the
    hooks should not start another yet."""
    st = _state()
    if not st.get("streak") or (st.get("reason") != reason and st.get("outcome") != "failed"):
        return False
    wait = min(BACKOFF_MAX_S, BACKOFF_S * 2 ** (int(st["streak"]) - 1))
    return (now or time.time()) - float(st.get("at") or 0) < wait


def _record(reason: str, progress: bool, outcome: str) -> dict:
    """The last cycle's attempt: when, why it was due, what came of it, and how many in a row made no progress."""
    st = _state()
    streak = 0 if progress else (int(st.get("streak") or 0) + 1 if st.get("reason") == reason else 1)
    new = {"at": time.time(), "reason": reason, "outcome": outcome, "streak": streak}
    try:
        paths.write_atomic(state_file(), json.dumps(new))
    except OSError:
        pass
    return {**new, "first": streak == 1 or (streak and st.get("outcome") != outcome)}


def due(now: _dt.datetime | None = None) -> str:
    """Why a cycle should run now ("" when it need not): a segment was left half done, a line an older Athos wrote
    into the log just trimmed waits to be carried over, the live log is past `trigger_bytes`, its oldest event is
    older than `trigger_days`, or a live line names an archived task the rollups have not folded (a late mark or
    correction). Cheap enough for a hook: a stat and the first lines."""
    s = memory.settings()
    try:
        size = paths.events_file().stat().st_size
    except OSError:
        return ""
    if memory.pending_segment():
        return "resume"
    if any(unswept(f) for f in sidecars()):
        return "sweep"
    trigger_bytes, trigger_days = triggers(s)
    if size > trigger_bytes:
        return "size"
    try:
        with paths.events_file().open("rb") as f:
            head = f.read(65536)
    except OSError:
        head = b""
    first = _first_at(head)
    now = now or _now()
    if first and _days(now, first) > trigger_days:
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


def maybe_spawn(athos_cmd: Path, popen=subprocess.Popen, session_id: str | None = None) -> bool:
    """Stop hook: when a cycle is due and none is running, start `athos memory cycle --quiet` detached and at low
    priority, so no hook waits. Nothing starts with `memory.auto` off, or with ATHOS_SPAWN=off (the tests) unless a stub
    `popen` is passed."""
    if os.environ.get("ATHOS_SPAWN", "").lower() == "off" and popen is subprocess.Popen:
        return False
    if not memory.settings().get("auto") or running():
        return False
    why = due()
    if not why or backing_off(why):
        return False
    argv = [sys.executable, str(athos_cmd), "memory", "cycle", "--quiet"]
    if session_id:                        # its turn just ended: the model pass does not count it as working
        argv += ["--after-session", session_id]
    if os.name == "posix" and Path("/usr/bin/nice").exists():
        argv = ["/usr/bin/nice", "-n", "15", *argv]
    try:
        popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
              start_new_session=True, close_fds=True)
    except OSError:
        return False
    return True


# ------------------------------------------------------------------------------------------------ phase 1: the cut
SEGMENT_MAX = 8_000_000      # raw bytes per segment at most: a first cycle on a long log writes several, never one huge
SIDE_QUIET_S = 30            # a trimmed log's old file nobody wrote into for this long is let go (after a last sweep)
NOT_AT_HEAD = ("the live log no longer starts with the segment (it was replaced or put back meanwhile): nothing was "
               "trimmed, and the log was left as it is")
REPEATS = ("the lines about to be archived are a segment the archive already holds: nothing was archived twice, and the "
           "log was left as it is")


def _cut_stream(f, total: int, now: _dt.datetime, s: dict | None = None) -> int:
    from athos import eval as ev
    s = s or memory.settings()
    floor_days = float(s["min_keep_days"])
    keep_days = max(float(s["keep_days"]), floor_days)    # never the last min_keep_days, whatever keep_days says
    keep_bytes = int(s["keep_bytes"])
    at, out, previous_old = 0, 0, True
    while at < total:
        line = f.readline()
        if not line or not line.endswith(b"\n"):
            break                                         # a line still being written stays
        try:
            stamp = json.loads(line).get("at")
        except (ValueError, AttributeError):
            stamp = None
        t = ev._parse(stamp) if isinstance(stamp, str) else None
        if t is not None and _days(now, stamp) < -1:
            t = None                                      # stamped in the future (a clock that was wrong): no time
        if t is None:
            old = previous_old
        else:
            age = _days(now, stamp)
            old = age > keep_days or (total - at > keep_bytes and age > floor_days)
        if not old:
            break
        previous_old = old
        at += len(line)
        out = at
    return out


def cut(raw: bytes, now: _dt.datetime, s: dict | None = None) -> int:
    """How many bytes at the start of the live log leave it: whole lines only, a prefix, oldest first. A line older
    than `keep_days` leaves; so does an older line while the live log would still be over `keep_bytes`, but never one
    of the last `min_keep_days`. A line whose time cannot be read goes with the line before it. The cycle reads the
    log as a stream (`_cut_stream`); this is the same over bytes."""
    import io
    return _cut_stream(io.BytesIO(raw), len(raw), now, s)


def _next_id(segments: list[dict]) -> int:
    return (max((int(s["id"]) for s in segments), default=0)) + 1


def write_segment(data: bytes, repeats: list | None = None) -> dict:
    """The prefix as a new segment: compressed into a temporary file of its own, synced, moved into place, the folder
    synced, and only then listed in the manifest (state `written`, synced too). Returns the manifest entry; bytes the
    archive already holds (the same sha256) are never written again: that segment's entry is returned. `repeats`: the
    numbers of its lines that repeat lines archived before (kept, never counted again)."""
    from athos import eval as ev
    man = memory.manifest()
    sha = memory._sha(data)
    same = next((s for s in man["segments"] if s.get("sha256") == sha), None)
    if same is not None:
        return same
    seg_id = _next_id(man["segments"])
    name = f"events-{seg_id:05d}.jsonl.gz"
    target = memory.archive_dir() / name
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f".{name}.{uuid.uuid4().hex[:8]}.tmp")
    with open(tmp, "wb") as out:
        out.write(gzip.compress(data, mtime=0))
        out.flush()
        os.fsync(out.fileno())
    os.replace(tmp, target)
    paths.fsync_dir(target.parent)
    events = memory.decode(data)
    stamps = [e.get("at") for e in events if isinstance(e, dict) and isinstance(e.get("at"), str)]
    entry = {"id": seg_id, "file": name, "lines": data.count(b"\n"), "events": len(events), "bytes": len(data),
             "sha256": sha, "head": memory._head_sha(data), "first_at": min(stamps, default=None),
             "last_at": max(stamps, default=None), "state": "written", "written_at": ev._iso(ev.now())}
    if repeats:
        entry["repeats"] = sorted(repeats)
        entry["events"] = len(memory.segment_events(entry, data))
    man["segments"].append(entry)
    memory.write_json(memory.manifest_file(), man)
    return entry


def _set_state(seg_id, state: str) -> None:
    """Set one segment's state (or several: a list of ids), in one write of the manifest."""
    from athos import eval as ev
    ids = set(seg_id) if isinstance(seg_id, (list, tuple, set)) else {seg_id}
    man = memory.manifest()
    for s in man["segments"]:
        if s["id"] in ids:
            s["state"] = state
            s[f"{state}_at"] = ev._iso(ev.now())
    memory.write_json(memory.manifest_file(), man)


def fold_segment(entry: dict, led: dict | None = None, write: bool = True) -> dict:
    """Fold one segment into the ledger, once (the ledger lists the segments it folded), and write the ledger."""
    led = led if led is not None else memory.load_ledger()
    if entry["id"] not in led["folded"]:
        memory.fold(led, memory.segment_events(entry))
        led["folded"].append(entry["id"])
        if write:
            memory.write_json(memory.ledger_file(), led)
    return led


def write_rollups(led: dict | None = None) -> int:
    """The rollups from the ledger and the live log as it is now (the segments the ledger folded left out while the
    live log still starts with them). The live log and the manifest are read as one view under the append lock,
    which is held only for that read: the sums are made outside it, so no hook waits on them."""
    led = led if led is not None else memory.load_ledger()
    raw, segs, _ok = memory.live_and_segments()
    upto = int(led["folded"][-1]) if led["folded"] else 0
    raw = raw[memory.archived_prefix(raw, segs, upto):]
    live = memory.decode(raw)
    roll = memory.aggregate(led, live, len(raw), memory._head_sha(raw))
    return memory.write_json(memory.rollups_file(), roll)


# -- the trim, and lines an older Athos writes into the log while it is trimmed
def _side_prefix() -> str:
    return "." + paths.events_file().name + ".trim-"


def sidecars() -> list[Path]:
    """The trimmed log's old files, kept reachable under a hidden name (`.events.jsonl.trim-<segment>-<trimmed
    bytes>-<end of what was kept>-<swept up to>`) so that a line a writer without the lock put into the old file after
    the trim is carried over, never lost."""
    try:
        return sorted(paths.events_file().parent.glob(_side_prefix() + "*"))
    except OSError:
        return []


def _side_parts(f: Path) -> tuple[int, int, int, int] | None:
    fields = f.name[len(_side_prefix()):].split("-")
    try:
        seg_id, n, end, swept = (int(x) for x in fields[:4])
    except ValueError:
        return None
    if len(fields) not in (4, 5):
        return None
    return seg_id, n, end, swept


def _side_name(f: Path, seg_id, n, end, swept) -> Path:
    """A trimmed log's old file under its name for this point swept; the unique token its trim gave it is kept (two
    trims of the same bytes, a log put back twice, never share a name)."""
    fields = f.name[len(_side_prefix()):].split("-")
    token = f"-{fields[4]}" if len(fields) == 5 else ""
    return f.with_name(f"{_side_prefix()}{seg_id}-{n}-{end}-{swept}{token}")


def unswept(f: Path) -> bool:
    parts = _side_parts(f)
    try:
        return parts is not None and f.stat().st_size > parts[3]
    except OSError:
        return False


def _sweep(f: Path, whole_lines: bool = True) -> tuple[int, Path | None]:
    """Carry over what was written into a trimmed log's old file after the point already carried over, unless the live
    log already holds it (a sweep stopped between its append and its rename). Under the append lock. Returns the bytes
    appended and the old file's name now (None when it is gone)."""
    parts = _side_parts(f)
    log = paths.events_file()
    if parts is None:
        return 0, f
    seg_id, n, end, swept = parts
    try:
        if log.exists() and os.path.samefile(f, log):     # stopped between the link and the trim: the log itself
            f.unlink()
            return 0, None
        with open(f, "rb") as h:
            h.seek(swept)
            chunk = h.read()
    except OSError:
        return 0, f
    if whole_lines:
        chunk = chunk[:chunk.rfind(b"\n") + 1]           # a line still being written waits for the next sweep
    if not chunk:
        return 0, f
    added = 0
    if memory.live_raw().find(chunk) < 0:
        with open(log, "ab") as out:
            out.write(chunk)
            out.flush()
            os.fsync(out.fileno())
        added = len(chunk)
    now = _side_name(f, seg_id, n, end, swept + len(chunk))
    os.replace(f, now)
    return added, now


def sweep(let_go: bool = False) -> dict:
    """Every trimmed log's old file: what reached it is carried over; with `let_go`, one nobody wrote into for
    SIDE_QUIET_S is let go after a last sweep that takes even an unfinished line."""
    out = {"swept_bytes": 0, "let_go": 0}
    states = {s.get("id"): s.get("state") for s in memory.segments()}
    for f in sidecars():
        with paths.locked(paths.events_file()):
            try:
                st = f.stat()
            except OSError:
                continue
            # Kept while its segment is not marked trimmed: it is the proof that the trim happened.
            quiet = let_go and time.time() - max(st.st_mtime, st.st_ctime) > SIDE_QUIET_S and \
                states.get((_side_parts(f) or (None,))[0]) in ("pruned", "kept", None)
            added, now = _sweep(f, whole_lines=not quiet)
            out["swept_bytes"] += added
            if quiet and now is not None:
                now.unlink(missing_ok=True)
                out["let_go"] += 1
    return out


NOLINK_QUIET_S = 1.0         # without hard links: the old file is read until nothing reached it for this long...
NOLINK_MAX_S = 15.0          # ...but no longer than this
NO_LINKS = ("this filesystem has no hard links: the trimmed log's old file was read until it stayed quiet for "
            f"{NOLINK_QUIET_S:g} s instead of being kept under a hidden name; a line an older Athos writes into it "
            "later than that, or while this cycle is killed, is not carried over")
_LAST: dict = {}             # what the last prune had to do differently (said in the cycle's event)


def _links_ok() -> bool:
    return os.environ.get("ATHOS_NO_HARDLINKS", "") not in ("1", "on", "true")


def _carry(chunk: bytes) -> None:
    """Append bytes read from a trimmed log's old file to the live log, ending a fragment with a newline so it never
    joins the next event. Under the append lock (the caller's)."""
    if not chunk:
        return
    if not chunk.endswith(b"\n"):
        chunk += b"\n"
    with open(paths.events_file(), "ab") as out:
        out.write(chunk)
        out.flush()
        os.fsync(out.fileno())


def _drain_old(h, at: int, clock=time.monotonic, sleep=time.sleep) -> int:
    """No hard links: the old file is reachable only through the open handle `h`, so it is read here, whole lines
    carried over as they arrive, until nothing reached it for NOLINK_QUIET_S (a writer that opened the log just before
    the trim writes within milliseconds), at most NOLINK_MAX_S; then what is left, even an unfinished line. Outside the
    append lock except for each append. Returns the bytes carried."""
    carried = 0
    start = last = clock()
    while True:
        try:
            size = os.fstat(h.fileno()).st_size
        except OSError:
            break
        if size > at:
            h.seek(at)
            chunk = h.read(size - at)
            whole = chunk[:chunk.rfind(b"\n") + 1]
            if whole:
                with paths.locked(paths.events_file()):
                    _carry(whole)
                at += len(whole)
                carried += len(whole)
                last = clock()
        now = clock()
        if now - last >= NOLINK_QUIET_S or now - start >= NOLINK_MAX_S:
            break
        sleep(min(0.05, NOLINK_QUIET_S))
    h.seek(at)
    rest = h.read()
    if rest:
        with paths.locked(paths.events_file()):
            _carry(rest)
        carried += len(rest)
    return carried


def prune(entry: dict) -> int:
    """Trim from the start of the live log the archived segments it starts with, up to this one, and only while it
    still starts with exactly their bytes (so running it twice trims once, and a log replaced meanwhile is left as it
    is). The old file stays reachable under a hidden, unique name until it is quiet, so a line a writer without the
    lock puts into it after the trim (an older Athos) is carried over (`sweep`). Where the filesystem has no hard
    links, the old file is instead read through the handle kept open until it stays quiet (`_drain_old`), and said
    (`NO_LINKS`). The append lock is held only for the copy of what stays and the swap. Returns the bytes trimmed (0:
    nothing was)."""
    log = paths.events_file()
    segs = memory.segments()
    try:
        st = log.stat()
        h = open(log, "rb")
    except OSError:
        return 0
    with h:
        def read(a, b, h=h):
            h.seek(a)
            return h.read(b - a)
        n, used = memory.prefix_chain(read, st.st_size, segs, int(entry["id"]))
        if not n:
            return 0
        head, edge = read(0, 4096), read(max(0, n - 4096), n)
    held = None
    with paths.locked(log):
        try:
            h = open(log, "rb")
        except FileNotFoundError:
            return 0
        try:
            def read(a, b, h=h):
                h.seek(a)
                return h.read(b - a)
            now_st = os.fstat(h.fileno())
            if now_st.st_ino != st.st_ino or now_st.st_size < st.st_size or read(0, 4096) != head or \
                    read(max(0, n - 4096), n) != edge:
                n, used = memory.prefix_chain(read, now_st.st_size, segs, int(entry["id"]))    # changed: look again
                if not n:
                    return 0
            end = now_st.st_size
            side = log.with_name(f"{_side_prefix()}{entry['id']}-{n}-{end}-{end}-{uuid.uuid4().hex[:8]}")
            linked = False
            if _links_ok():
                try:
                    os.link(log, side)
                    linked = True
                except OSError:                           # no hard links here: the old file is read through `h`
                    pass
            tmp = log.with_name("." + log.name + f".{uuid.uuid4().hex[:8]}.tmp")
            with open(tmp, "wb") as out:
                at = n
                while at < end:
                    piece = read(at, min(end, at + (1 << 22)))
                    if not piece:
                        break
                    out.write(piece)
                    at += len(piece)
                out.flush()
                os.fsync(out.fileno())
            try:
                os.chmod(tmp, now_st.st_mode & 0o777)
            except OSError:
                pass
            os.replace(tmp, log)
            paths.fsync_dir(log.parent)
            if linked:
                _sweep(side)
            else:
                held, h = h, None                         # kept open past the lock: read until it is quiet
                _LAST["no_links"] = NO_LINKS
        finally:
            if h is not None:
                h.close()
    if held is not None:
        try:
            _drain_old(held, end)
        finally:
            held.close()
    ids = [e["id"] for e in used if e.get("state") != "pruned"]
    if ids:
        _set_state(ids, "pruned")
    return n


def recover() -> dict:
    """Put the archive's table back in order, never deleting a segment: lines written into a trimmed log's old file
    are carried over; a trim's half-written copy is dropped (the live log is whole); a temporary segment that
    decompresses is promoted (or, when the same bytes are already in place, dropped as a copy), one that does not is
    moved to `archive/damaged/`; a manifest that cannot be read is moved there and rebuilt from the segments on disk;
    a segment the manifest does not list is listed again, `written` while the live log still starts with its bytes and
    `pruned` otherwise (one whose bytes are already listed goes to `archive/duplicates/`, one that cannot be read to
    `archive/damaged/`); a ledger that is unreadable or did not fold exactly the listed segments is folded again."""
    out = {"listed_again": 0, "damaged": 0, "promoted": 0, "manifest_rebuilt": False, "ledger_rebuilt": False,
           "stray": 0, **sweep(let_go=True)}
    log = paths.events_file()
    for f in log.parent.glob("." + log.name + ".*.tmp"):
        f.unlink(missing_ok=True)                        # a trim stopped before its swap: the live log is still whole
        out["stray"] += 1
    folder = memory.archive_dir()
    if folder.is_dir():
        def aside(f: Path, where: str = "damaged") -> None:
            (folder / where).mkdir(exist_ok=True)
            os.replace(f, folder / where / f.name)
        changed = False
        try:
            man = memory.manifest()
        except paths.StateUnreadable:
            (folder / "damaged").mkdir(exist_ok=True)
            os.replace(memory.manifest_file(), folder / "damaged" / f"manifest-{int(time.time())}.json")
            man, changed = {"v": memory.V, "segments": []}, True
            out["manifest_rebuilt"] = True
        for f in sorted(folder.glob(".events-*.tmp")):
            final = folder / (f.name[1:].split(".jsonl.gz", 1)[0] + ".jsonl.gz")
            try:
                raw = gzip.decompress(f.read_bytes())
            except (OSError, EOFError, zlib.error):
                aside(f)
                out["damaged"] += 1
                continue
            if not final.exists():
                os.replace(f, final)
                paths.fsync_dir(folder)
                out["promoted"] += 1
                continue
            try:
                same = gzip.decompress(final.read_bytes()) == raw
            except (OSError, EOFError, zlib.error):
                same = False
            if same:
                f.unlink()                               # the same bytes are in place: only a copy goes
            else:
                aside(f)
                out["damaged"] += 1
        for f in folder.glob(".*.tmp"):
            f.unlink(missing_ok=True)                    # a manifest's temporary copy: the manifest itself is whole
        listed = {e["file"] for e in man["segments"]}
        shas = {e.get("sha256") for e in man["segments"]}
        found = []
        for f in sorted(folder.glob("events-*.jsonl.gz")):
            if f.name in listed:
                continue
            try:
                data = gzip.decompress(f.read_bytes())
                seg_id = int(f.name.split("-")[1].split(".")[0])
            except (OSError, EOFError, ValueError, zlib.error):
                aside(f)
                out["damaged"] += 1
                continue
            if memory._sha(data) in shas:
                aside(f, "duplicates")
                continue
            events = memory.decode(data)
            stamps = [e.get("at") for e in events if isinstance(e, dict) and isinstance(e.get("at"), str)]
            entry = {"id": seg_id, "file": f.name, "lines": data.count(b"\n"), "events": len(events),
                     "bytes": len(data), "sha256": memory._sha(data), "head": memory._head_sha(data),
                     "first_at": min(stamps, default=None), "last_at": max(stamps, default=None), "recovered": True}
            again = repeated_lines(data, [e for e in man["segments"] if int(e["id"]) < seg_id])
            if again:                                    # the same rule as when it was cut: the same lines skipped
                entry["repeats"] = again
                entry["events"] = len(memory.segment_events(entry, data))
            man["segments"].append(entry)
            shas.add(entry["sha256"])
            found.append(entry)
            out["listed_again"] += 1
        for e in man["segments"]:
            if "head" not in e:                          # listed before heads were kept
                try:
                    e["head"] = memory._head_sha(memory.read_segment(e, check=False))
                    changed = True
                except (OSError, ValueError):
                    pass
        if found:
            man["segments"].sort(key=lambda e: int(e["id"]))
            raw = memory.live_raw()
            _n, at_head = memory.prefix_chain(lambda a, b: raw[a:b], len(raw), man["segments"], partial=False)
            heads = {e["id"] for e in at_head}
            for e in found:
                e["state"] = "written" if e["id"] in heads else "pruned"
            changed = True
        if changed:
            memory.write_json(memory.manifest_file(), man)
    segs = memory.segments()
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
    """Finish what a stopped cycle left half done (after `recover`): segments written are folded, then the live log
    is trimmed of them; one the live log no longer starts with is marked `kept`, and said."""
    done = {"folded": 0, "pruned": 0, "bytes": 0, **recover()}
    left = memory.pending_segments()
    if not left:
        return done
    led = memory.load_ledger()
    written = [e for e in left if e.get("state") == "written"]
    for entry in written:
        fold_segment(entry, led, write=False)
        done["folded"] += 1
    if written:
        memory.write_json(memory.ledger_file(), led)
        _set_state([e["id"] for e in written], "folded")
    write_rollups(led)
    done["bytes"] = prune(left[-1])
    if done["bytes"]:
        done["pruned"] += 1
    elif any((_side_parts(f) or (None,))[0] == left[-1]["id"] for f in sidecars()):
        _set_state([e["id"] for e in left], "pruned")    # trimmed already: stopped before the manifest said so
        done["pruned"] += 1
    else:
        _set_state([e["id"] for e in left], "kept")
        done["refused"] = NOT_AT_HEAD
    write_rollups()
    return done


def _stamps(lines) -> tuple[str | None, str | None]:
    lo = hi = None
    for line in lines:
        try:
            at = json.loads(line).get("at")
        except (ValueError, AttributeError):
            continue
        if isinstance(at, str):
            lo = at if lo is None or at < lo else lo
            hi = at if hi is None or at > hi else hi
    return lo, hi


def archived_lines(data: bytes, segs: list) -> set:
    """The lines of every segment whose time span overlaps that of `data` (or has none recorded): what a line about
    to be archived may already be, wherever it sits in the archive, read only from the segments that can hold it."""
    lo, hi = _stamps(data.splitlines())
    out: set = set()
    for e in segs:
        first, last = e.get("first_at"), e.get("last_at")
        if lo is not None and first and last and (last < lo or first > hi):
            continue
        try:
            out.update(memory.read_segment(e, check=False).splitlines())
        except (OSError, ValueError):
            continue
    return out


def repeated_lines(data: bytes, earlier: list) -> list:
    """The numbers of the lines of `data` byte for byte equal to a line archived in an earlier segment (a log put back
    or merged from a copy, turns an older Athos imported again): kept in the segment, so the live log can be trimmed
    of them, but never counted twice. Lines equal to each other within `data` are each counted. Deterministic: the
    same data against the same earlier segments gives the same lines, also when a lost manifest is rebuilt."""
    if not earlier:
        return []
    old = archived_lines(data, earlier)
    return [n for n, line in enumerate(data.split(b"\n")) if line.strip() and line in old]


def replay_and_prune(now: _dt.datetime | None = None) -> dict:
    """Phase 1: resume what a stopped cycle left, trim again the archived segments a log put back starts with, then
    cut the prefix outside the window, archive it (in segments of SEGMENT_MAX bytes at most, read as a stream), fold
    it, and trim it. With nothing to cut, the rollups are still refreshed when an archive exists (late lines, a
    deleted rollup file). Anything it cannot do safely it leaves as it is and says why (`refused`)."""
    now = now or _now()
    _LAST.clear()
    out = {"resumed": resume(), "archived_lines": 0, "archived_bytes": 0, "segment": None, "segments": 0,
           "compressed": 0}
    if out["resumed"].get("refused"):
        out["refused"] = out["resumed"]["refused"]
    segs = memory.segments()
    if segs:
        again = prune(segs[-1])                          # a log from before earlier cycles: never archived twice
        if again:
            out["trimmed_again"] = again
    log = paths.events_file()
    try:
        size = log.stat().st_size
        f = open(log, "rb")
    except OSError:
        size, f = 0, None
    entries: list = []
    if f is not None:
        with f:
            total = _cut_stream(f, size, now)
            a = 0
            while a < total:
                f.seek(a)
                data = f.read(min(total - a, SEGMENT_MAX))
                if a + len(data) < total:
                    end = data.rfind(b"\n") + 1
                    if end <= 0:                         # one line longer than a segment: it goes whole
                        data += f.readline()
                    else:
                        data = data[:end]
                again = repeated_lines(data, segs + entries)
                entry = write_segment(data, again)
                if entry.get("state") != "written" or any(e["id"] == entry["id"] for e in entries):
                    out["refused"] = REPEATS                 # already archived: never twice
                    break
                entries.append(entry)
                out["repeats_skipped"] = out.get("repeats_skipped", 0) + len(again)
                a += len(data)
    if entries:
        led = memory.load_ledger()
        for entry in entries:
            fold_segment(entry, led, write=False)
        memory.write_json(memory.ledger_file(), led)
        _set_state([e["id"] for e in entries], "folded")
        write_rollups(led)
        if not prune(entries[-1]):
            _set_state([e["id"] for e in entries], "kept")
            out["refused"] = NOT_AT_HEAD
        out.update(archived_lines=sum(e["lines"] for e in entries), archived_bytes=sum(e["bytes"] for e in entries),
                   segment=entries[-1]["id"], segments=len(entries),
                   compressed=sum(memory.segment_path(e).stat().st_size for e in entries))
    if memory.has_archive():
        out["rollup_bytes"] = write_rollups()
    if _LAST.get("no_links"):
        out["no_links"] = _LAST["no_links"]
    return out


# ------------------------------------------------------------------------------------------------ rebuild and check
def check_archive() -> list[dict]:
    """Every segment against its manifest entry: present, readable, the same bytes and sha256. Returns the failures."""
    bad = []
    for entry in memory.manifest()["segments"]:
        try:
            memory.read_segment(entry)
        except (OSError, ValueError) as problem:
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
    raw, segs, _ok = memory.live_and_segments()
    raw = raw[memory.archived_prefix(raw, segs, int(led["folded"][-1]) if led["folded"] else 0):]
    fresh = memory.aggregate(led, memory.decode(raw))
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
    """What counting finds, over the whole history (the rollups, the ledger's counts and the live log, never the
    archive itself): pieces used
    together, requests that found no piece (counted per project, never quoted), near-duplicate pieces, steps the
    person corrected by hand again and again, pieces whose own Checks keep failing. Ids only for pieces that exist."""
    from athos import store, wiki
    v = memory.view()
    total = v.sums()
    pieces = {p.id: p for p in store.all_pieces()}
    pairs = sorted(((k.split("|"), n) for k, n in total["pairs"].items() if n >= PAIR_MIN),
                   key=lambda kv: (-kv[1], kv[0]))
    together = [{"pieces": ab, "tasks": n} for ab, n in pairs if all(p in pieces for p in ab)]
    led = memory.ledger_counts()              # what only the cycle reads is in the ledger, never in the rollups
    route: dict = json.loads(json.dumps(led.get("route") or {}))
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
    edits = dict(led.get("step_edits") or {})
    undone = {(e.get("task_id"), e.get("piece"), e.get("original_at")) for e in v.of_type("correction")
              if e.get("target") == "learned_from_edit"} | {tuple(x) for x in led.get("lfe_wrong") or []}
    for tid, pid, at in undone:                  # an archived edit a live correction takes back
        key = (led.get("lfe_keys") or {}).get(f"{tid}|{pid}|{at}")
        if key and edits.get(key):
            edits[key] -= 1
    for e in v.of_type("learned_from_edit"):
        if e.get("piece") and e.get("basis") and (e.get("task_id"), e.get("piece"), e.get("at")) not in undone:
            key = f"{e['piece']}#{e.get('statement') or ''}"
            edits[key] = edits.get(key, 0) + 1
    corrected = [{"piece": k.split("#", 1)[0], "step": k.split("#", 1)[1] or None, "edits": n}
                 for k, n in sorted(edits.items()) if n >= STEP_EDITS_MIN and k.split("#", 1)[0] in pieces]
    failing = []
    for pid in pieces:
        fails = int((led.get("check_failed") or {}).get(pid) or 0) + sum(
            1 for e in v.of_type("reuse") if e.get("piece") == pid and "check_failed" in (e.get("basis") or []))
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
    return bool((memory.ledger_counts().get("route") or {}).get(project, {}).get("public"))


def _play(project: str, total: dict) -> bool:
    from athos import curate
    pr = total["projects"].get(project) or {}
    return bool(curate.PLAY.search(project)) or (pr.get("tasks") and pr.get("scratch") == pr.get("tasks")) or \
        project in set(curate.state().get("ignore") or [])


def project_page(project: str, found: dict | None = None, public: bool | None = None) -> str:
    """What is known about working in a project, counted from the log and the store, as the page says it: its ways of
    working with their uses and outcomes, the pieces used together, how often a request found nothing, and what to
    look at. It names only pieces that may be named in that project's own sessions (load.nameable); another
    project's pieces are only counted. No request is quoted."""
    from athos import eval as ev, load, store
    v = memory.view()
    total = v.sums()
    found = found if found is not None else findings()
    public = _project_public(project, v) if public is None else public
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


STUCK = {"size": "the live log is past trigger_bytes but all of it is inside the window it keeps (min_keep_days)",
         "age": "its oldest event is past trigger_days but nothing outside the window could be cut",
         "resume": "a segment left half done could not be finished"}


def run(now: _dt.datetime | None = None, model: bool | None = None, runner=None, auto: bool = False,
        after_session: str | None = None) -> dict:
    """One whole cycle, under its lock: replay and prune, abstraction, consolidation, and (only when asked or turned
    on, and idle) the model pass. Returns what each phase did; `skipped` when another cycle holds the lock. `auto`: a
    cycle a hook started; one that archived nothing and found nothing late skips the counting and the pages, and
    says once why it could make no progress (a `stuck` event), after which the hooks back off. A cycle that raises
    leaves a `failed` event (its error's kind and where), and the hooks back off from it too."""
    if not take_lock():
        return {"skipped": "another cycle is running"}
    run_id = uuid.uuid4().hex[:12]
    out: dict = {"run_id": run_id}
    reason = due() or "asked"
    try:
        t0 = time.perf_counter()
        before = memory.sizes()
        out["replay"] = replay_and_prune(now)
        after = memory.sizes()
        r = out["replay"]
        _event(run_id, "replay", t0, archived_lines=r["archived_lines"], archived_bytes=r["archived_bytes"],
               compressed_bytes=r["compressed"], resumed=r["resumed"], live_before=before["live"],
               live_after=after["live"], rollup_bytes=after["rollups"], segments=after["segments"],
               **{k: r[k] for k in ("refused", "trimmed_again", "no_links", "repeats_skipped") if r.get(k)})
        progress = bool(r["archived_lines"] or r.get("trimmed_again") or r["resumed"].get("pruned")
                        or r["resumed"].get("folded")) or reason in ("late", "rollups", "sweep", "asked")
        if auto and not progress:
            rec = _record(reason, False, "stuck")
            if rec["first"]:
                _event(run_id, "stuck", t0, reason=reason, why=r.get("refused") or STUCK.get(reason, reason),
                       streak=rec["streak"])
            return {**out, "stuck": reason}
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
            out["model"] = dream_model.run(runner=runner, after_session=after_session)
            _event(run_id, "model", t3, wrote=out["model"].get("wrote") or [],
                   **{k: v for k, v in out["model"].items() if not isinstance(v, (dict, list))})
        swept = sweep()                       # what reached the trimmed log's old file while the cycle ran
        _event(run_id, "done", t0, spend_usd=(out.get("model") or {}).get("spend_usd", 0.0),
               swept_bytes=swept["swept_bytes"])
        _record(reason, progress or not auto, "done")
    except Exception as problem:
        from athos import eval as ev
        _record(reason, False, "failed")
        _event(run_id, "failed", time.perf_counter(), reason=reason, error=type(problem).__name__,
               line=ev._place(problem))
        raise
    finally:
        release_lock()
    return out


def status() -> dict:
    """The three layers' sizes and dates, whether a cycle is due or running, and the last one's outcome."""
    s = memory.sizes()
    roll = memory.load_rollups() or {}
    return {**s, "archived_tasks": roll.get("archived_tasks", 0), "archived_from": roll.get("first_at"),
            "archived_to": roll.get("last_at"), "due": due(), "running": running(), "settings": memory.settings()}
