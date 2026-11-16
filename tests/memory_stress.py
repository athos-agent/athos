"""A stress run of the dream cycle against real concurrent writers: some take the append lock (this Athos), some do
not (an older Athos, another tool), while cycles run in a loop and are killed at random points. Every line written
must end up in the history exactly once, and the derived files must equal a rebuild. Synthetic data only.

    python3 -m tests.memory_stress <seconds> [locked writers] [unlocked writers] [kill every ~seconds, 0: never]

The unit suite runs a short version (tests/test_memory_integrity.py)."""

from __future__ import annotations

import json
import os
import random
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = str(Path(__file__).resolve().parents[1])

WRITER = r"""
import json, os, sys, time, datetime as dt
sys.path.insert(0, sys.argv[1])
from athos import eval as ev, paths
name, locked, until = sys.argv[2], sys.argv[3] == "1", float(sys.argv[4])
old = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=60)).isoformat(timespec="milliseconds")
n = 0
while time.time() < until:
    n += 1
    e = {"type": "stress", "w": name, "n": n, "at": old}
    if locked:
        ev.append(e)
    else:                                      # an older Athos: open, append, close, no lock
        with open(paths.events_file(), "a") as out:
            out.write(json.dumps(e) + "\n")
print(n)
"""

LOOP = r"""
import sys, time, datetime as dt
sys.path.insert(0, sys.argv[1])
from athos import eval as ev
from athos.memory import cycle
until = float(sys.argv[2])
while time.time() < until:
    try:
        cycle.run(now=ev.now() + dt.timedelta(days=30))     # everything but the newest lines is outside the window
    except Exception as problem:
        print("cycle raised", type(problem).__name__, problem, file=sys.stderr)
        raise
"""


def stress(seconds: float, locked: int = 2, unlocked: int = 2, kill_every: float = 0.0, home: str | None = None,
           seed: int = 1) -> dict:
    home = home or tempfile.mkdtemp(prefix="athos-stress-")
    env = {**os.environ, "ATHOS_HOME": home, "ATHOS_SPAWN": "off"}
    Path(home).mkdir(parents=True, exist_ok=True)
    (Path(home) / "config.json").write_text(json.dumps({"memory": {"keep_days": 8, "keep_bytes": 20000,
                                                                   "auto": False}}))
    rnd = random.Random(seed)
    until = time.time() + seconds
    writers = [subprocess.Popen([sys.executable, "-c", WRITER, REPO, f"{'L' if i < locked else 'U'}{i}",
                                 "1" if i < locked else "0", str(until)], env=env, stdout=subprocess.PIPE, text=True)
               for i in range(locked + unlocked)]
    kills = cycles_started = 0
    errors = []
    while time.time() < until:
        loop = subprocess.Popen([sys.executable, "-c", LOOP, REPO, str(until)], env=env, stderr=subprocess.PIPE,
                                text=True)
        cycles_started += 1
        if kill_every:
            time.sleep(rnd.uniform(0.05, 2 * kill_every))
            if loop.poll() is None:
                loop.send_signal(signal.SIGKILL)
                kills += 1
        _out, err = loop.communicate()
        if loop.returncode not in (0, -signal.SIGKILL) or "cycle raised" in (err or ""):
            errors.append((err or "")[-2000:])
    written = {}
    for i, w in enumerate(writers):
        written[f"{'L' if i < locked else 'U'}{i}"] = int(w.communicate()[0].strip() or 0)
    # Writers are done: two last cycles carry over whatever reached a trimmed log's old file.
    finish = subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0, sys.argv[1]);"
                             "from athos.memory import cycle; cycle.run(); cycle.run();"
                             "from athos import eval as ev, memory; import json;"
                             "rows=[e for e in ev.events() if e.get('type')=='stress'];"
                             "segs=memory.manifest()['segments'];"
                             "print(json.dumps({'rows':[[e['w'],e['n']] for e in rows],"
                             "'check':cycle.check_archive(),'rebuild':cycle.compare_rebuild(),"
                             "'segments':len(segs),'cycles':sum(1 for e in ev.events() if e.get('type')=="
                             "'memory_cycle' and e.get('phase')=='done'),"
                             "'states':sorted({s.get('state') for s in segs})}))", REPO],
                            env=env, capture_output=True, text=True)
    if finish.returncode:
        raise RuntimeError(finish.stderr[-3000:])
    got = json.loads(finish.stdout)
    seen: dict = {}
    for w, n in got["rows"]:
        seen[(w, n)] = seen.get((w, n), 0) + 1
    expected = {(w, n) for w, total in written.items() for n in range(1, total + 1)}
    return {"written": sum(written.values()), "by_writer": written,
            "missing": len(expected - set(seen)), "duplicated": sum(1 for v in seen.values() if v > 1),
            "unexpected": len(set(seen) - expected), "cycles_done": got["cycles"], "loops_started": cycles_started,
            "kills": kills, "segments": got["segments"], "states": got["states"], "archive_failures": got["check"],
            "rebuild": got["rebuild"], "errors": errors, "home": home}


if __name__ == "__main__":
    args = [float(a) for a in sys.argv[1:]]
    out = stress(args[0], int(args[1]) if len(args) > 1 else 2, int(args[2]) if len(args) > 2 else 2,
                 args[3] if len(args) > 3 else 0.0)
    print(json.dumps({k: v for k, v in out.items() if k != "errors"}, indent=1))
    for e in out["errors"][:3]:
        print(e, file=sys.stderr)
