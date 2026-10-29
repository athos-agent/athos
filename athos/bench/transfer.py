"""`athos bench transfer`: does what a person taught one agent carry to the others, whole?

1. **Teach.** Claude Code works the case's teaching task with a fresh Athos home, turn by turn, as the person would:
   the request with their checklist, their corrections, and "save it". What Athos saves is the know-how under test.
   The home is kept in `~/.athos/bench/teach/<case>-<time>/`, so later replays can reuse it (`--teach-home`).
2. **Replay.** A fresh workspace with another document and no checklist, the one-line request, on each agent:
   - A: no Athos at all;
   - B: only the project's `.athos/` folder (`athos project sync`), no plugin, an empty store;
   - C: `.athos/` plus Athos's plugin with the taught store.
   Arm C reaches every agent: Claude Code and Codex honour `ATHOS_HOME`; OpenCode gets the plugin in the run's own
   config; Muse Code, whose hooks get a sanitized environment, a copy whose hook commands name the run's store.
3. **Judge.** The case's `check.py` scores each point of the person's know-how separately (`items`), and says which
   came from their checklist and which from what they added while teaching (`sources`). Completeness = points applied.

Rows go to `~/.athos/bench/results.jsonl` with `arm`, `items` and `teach`; `report()` and `render()` turn them into
the per-agent table and `REPORT.md`.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

from athos import bench, paths, store

ARMS = ("A", "B", "C")
ARM_NAMES = {"A": "no Athos", "B": ".athos/ folder only", "C": ".athos/ + plugin"}
BIN = Path(__file__).resolve().parents[2] / "bin"


def teach_root() -> Path:
    return paths.home() / "bench" / "teach"


def _claude_turn(prompt: str, ws: Path, env: dict, session: str | None, case: dict) -> dict:
    cmd = ["claude", "-p", prompt, "--output-format", "json", "--permission-mode", "acceptEdits",
           "--allowedTools", bench.CLAUDE_TOOLS]
    if session:
        cmd += ["--resume", session]
    if case.get("max_usd_per_run"):
        cmd += ["--max-budget-usd", str(case["max_usd_per_run"])]
    r = subprocess.run(cmd, cwd=ws, env=env, capture_output=True, text=True, timeout=bench._timeout(case))
    try:
        return json.loads(r.stdout)
    except ValueError:
        return {"is_error": True, "result": r.stderr.strip()[-300:]}


def teach(name: str, case: dict, out=print) -> dict:
    """Run the case's teaching turns in Claude Code against a new Athos home; returns where it is and what it saved."""
    stamp = time.strftime("%Y%m%d-%H%M%S")
    home = teach_root() / f"{name}-{stamp}"
    ws = Path(tempfile.mkdtemp(prefix="athos-teach-")) / "work"
    home.mkdir(parents=True)
    subprocess.run([sys.executable, str(case["dir"] / "teach_setup.py"), str(ws)], check=True, timeout=120)
    # Capture on, and this checkout's `athos` first on PATH, so the save lands in the teaching home.
    env = {**os.environ, "ATHOS_HOME": str(home), "CLAUDE_CODE_AUTO_CONNECT_IDE": "false",
           "PATH": f"{BIN}{os.pathsep}{os.environ.get('PATH', '')}"}
    env.pop("ATHOS_CAPTURE", None)
    session, cost, t0 = None, 0.0, time.monotonic()
    for i, turn in enumerate(case["teach"], 1):
        res = _claude_turn(turn, ws, env, session, case)
        session = res.get("session_id") or session
        cost += res.get("total_cost_usd") or 0.0
        out(f"teach {i}/{len(case['teach'])}: {'error' if res.get('is_error') else 'ok'}"
            f" (US${res.get('total_cost_usd') or 0:.3f})")
    old = os.environ.get("ATHOS_HOME")
    os.environ["ATHOS_HOME"] = str(home)
    try:
        pieces = [p.id for p in store.all_pieces()]
    finally:
        if old is None:
            os.environ.pop("ATHOS_HOME", None)
        else:
            os.environ["ATHOS_HOME"] = old
    info = {"home": str(home), "pieces": pieces, "cost_usd": round(cost, 4),
            "duration_s": round(time.monotonic() - t0, 1), "session": session, "workspace": str(ws)}
    (home / "teach.json").write_text(json.dumps(info, indent=1))
    if not pieces:
        raise RuntimeError(f"the teaching run saved no know-how (see {ws}); nothing to transfer")
    return info


def _sync(ws: Path, home: Path) -> None:
    """`athos project sync --all` into the workspace, from the taught store."""
    from athos import project
    old = os.environ.get("ATHOS_HOME")
    os.environ["ATHOS_HOME"] = str(home)
    try:
        project.sync(ws, everything=True)
    finally:
        if old is None:
            os.environ.pop("ATHOS_HOME", None)
        else:
            os.environ["ATHOS_HOME"] = old


def _with_env(key: str, value: str, fn):
    old = os.environ.get(key)
    os.environ[key] = value
    try:
        return fn()
    finally:
        if old is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = old


def _muse_plugin(home: Path, tmp: Path) -> None:
    """Muse Code runs the Claude Code plugin, but hands hooks a sanitized environment without ATHOS_HOME: install a
    copy of this checkout whose hook commands name the run's store, into the run's own Muse config."""
    root = BIN.parent
    copy = tmp / "athos-plugin"
    for part in (".claude-plugin", "hooks", "bin", "athos"):
        shutil.copytree(root / part, copy / part, ignore=shutil.ignore_patterns("__pycache__", "cases"))
    hooks = copy / "hooks" / "hooks.json"
    data = json.loads(hooks.read_text())
    for groups in data["hooks"].values():
        for g in groups:
            for h in g["hooks"]:
                h["command"] = f"ATHOS_HOME='{home}' {h['command']}"
    hooks.write_text(json.dumps(data, indent=2))
    env = {**os.environ, **bench._isolated(home)}
    for cmd in (["muse", "plugins", "install", str(copy), "--scope", "user", "--json"],
                ["muse", "plugins", "approve", "athos", "--json"]):
        r = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=120)
        if r.returncode:
            raise RuntimeError(f"{' '.join(cmd[:3])}: {(r.stderr or r.stdout).strip()[-200:]}")


def _plugin_home(taught: Path, tmp: Path, agent: str) -> Path:
    """Arm C: a copy of the taught store, so the run's own events never touch the kept teaching home, and Athos's
    plugin where the agent loads it from: Claude Code and Codex already have it and honour ATHOS_HOME; OpenCode
    and Muse Code get it in the run's own config folder."""
    home = tmp / "home"
    shutil.copytree(taught, home, ignore=shutil.ignore_patterns("teach.json", "reviews", "REPORT.md"))
    if agent == "opencode":
        from athos.adapters import opencode
        _with_env("XDG_CONFIG_HOME", str(home / "xdg-config"), lambda: opencode.install(BIN / "athos"))
    elif agent == "muse":
        _muse_plugin(home, tmp)
    return home


def replay_once(name: str, case: dict, agent: str, arm: str, taught: Path, teach_id: str, model=None) -> dict:
    tmp = Path(tempfile.mkdtemp(prefix="athos-transfer-"))
    ws = tmp / "work"
    bench.setup(case, ws)
    if arm in ("B", "C"):
        _sync(ws, taught)
    if arm == "C":
        try:
            home = _plugin_home(taught, tmp, agent)
        except (RuntimeError, OSError, subprocess.SubprocessError) as e:
            shutil.rmtree(tmp, ignore_errors=True)
            raise RuntimeError(f"arm C for {agent}: {e}") from e
    else:
        home = tmp / "home"
        home.mkdir()
    model = model or bench.DEFAULT_MODELS.get(agent)
    runner = bench.RUNNERS[agent]
    if arm == "C" and agent == "opencode":
        runner = lambda *a: bench.run_opencode(*a, pure=False)  # noqa: E731
    t0 = time.monotonic()
    try:
        out = runner(case, ws, home, False, model)
    except subprocess.TimeoutExpired:
        out = {"tokens": {}, "cost_usd": None, "model": model, "note": f"timed out after {bench._timeout(case)} s"}
    except Exception as e:  # noqa: BLE001 — a crashed agent is a failed run
        out = {"tokens": {}, "cost_usd": None, "model": model, "note": f"{type(e).__name__}: {e}"[:200]}
    duration = round(time.monotonic() - t0, 1)
    res = bench.check(case, ws)
    review = ws / "review.md"
    kept = teach_root() / teach_id / "reviews"
    kept.mkdir(parents=True, exist_ok=True)
    rid = uuid.uuid4().hex[:12]
    (kept / f"{agent}-{arm}-{rid}.md").write_text(review.read_text() if review.is_file() else
                                                  f"(no review.md)\n\n{out.get('note', '')}\n{out.get('last_text', '')}")
    row = {"id": rid, "at": time.strftime("%Y-%m-%dT%H:%M:%S"), "case": name, "agent": agent,
           "model": out.get("model"), "know_how": arm != "A", "arm": arm, "teach": teach_id,
           "verdict": res.get("verdict", "f"), "score": res.get("score"), "missed": res.get("missed", []),
           "items": res.get("items", {}), "sources": res.get("sources", {}), "duration_s": duration,
           "tokens": out.get("tokens") or {}, "cost_usd": out.get("cost_usd"), "note": out.get("note", ""),
           "named_page": bool(review.is_file() and "athos" in review.read_text().lower())}
    shutil.rmtree(tmp, ignore_errors=True)
    return row


def run(name: str, agents: list[str], arms: list[str], runs: int, teach_home: Path | None = None,
        max_usd: float | None = None, out=print) -> dict:
    """Teach once (or reuse a teaching home), then replay `runs` times per agent and arm, interleaved."""
    case = bench.cases()[name]
    if "teach" not in case:
        raise ValueError(f"{name} has no teaching turns: not a transfer case")
    info = json.loads((teach_home / "teach.json").read_text()) if teach_home else teach(name, case, out)
    taught = Path(info["home"])
    teach_id = taught.name
    out(f"know-how taught: {', '.join(info['pieces'])} ({taught})")
    rows, spent = [], 0.0 if teach_home else (info.get("cost_usd") or 0.0)
    for i in range(runs):
        for agent in agents:
            for arm in arms:
                if max_usd is not None and spent >= max_usd:
                    out(f"stopped: US${spent:.2f} spent, the cap is US${max_usd:.2f}")
                    return {"teach": info, "rows": rows}
                row = replay_once(name, case, agent, arm, taught, teach_id)
                bench.save(row)
                rows.append(row)
                spent += row["cost_usd"] or 0.0
                n = sum(row["items"].values()) if row["items"] else 0
                out(f"{i + 1}/{runs} {agent:<8} {arm} ({ARM_NAMES[arm]}): {n}/{len(row['items']) or '?'} points, "
                    f"{row['duration_s']} s" + (f", US${row['cost_usd']:.3f}" if row["cost_usd"] is not None else "")
                    + (f"  missed: {', '.join(row['missed'][:5])}" if row["missed"] else "")
                    + (f"  [{row['note']}]" if row["note"] else ""))
    return {"teach": info, "rows": rows}


def rescore(name: str, teach_id: str) -> int:
    """Score a teaching's kept reviews again with the case's current `check.py` (after a check was fixed), without
    running any agent. Rewrites those rows in results.jsonl; returns how many changed."""
    case = bench.cases()[name]
    kept = teach_root() / teach_id / "reviews"
    lines = bench.results_file().read_text().splitlines()
    changed, out = 0, []
    for line in lines:
        row = json.loads(line) if line.strip() else None
        f = kept / f"{row['agent']}-{row['arm']}-{row['id']}.md" if row and row.get("teach") == teach_id else None
        if f is not None and f.is_file():
            ws = Path(tempfile.mkdtemp(prefix="athos-rescore-"))
            if not f.read_text().startswith("(no review.md)"):
                (ws / "review.md").write_text(f.read_text())
            res = bench.check(case, ws)
            shutil.rmtree(ws, ignore_errors=True)
            new = {**row, "verdict": res.get("verdict", "f"), "score": res.get("score"),
                   "missed": res.get("missed", []), "items": res.get("items", {}), "sources": res.get("sources", {})}
            changed += new != row
            line = json.dumps(new, ensure_ascii=False)
        out.append(line)
    bench.results_file().write_text("\n".join(out) + "\n")
    return changed


# ------------------------------------------------------------------------------------------------ report
def report(name: str, teach_id: str | None = None, rows: list[dict] | None = None) -> dict:
    rows = [r for r in (bench.load_results() if rows is None else rows) if r.get("case") == name and r.get("arm")]
    if teach_id:
        rows = [r for r in rows if r.get("teach") == teach_id]
    elif rows:
        teach_id = rows[-1].get("teach")
        rows = [r for r in rows if r.get("teach") == teach_id]
    groups: dict[tuple, list] = {}
    for r in rows:
        groups.setdefault((r["agent"], r["arm"]), []).append(r)
    lines = []
    for (agent, arm), rs in sorted(groups.items(), key=lambda kv: (bench.AGENTS.index(kv[0][0]), kv[0][1])):
        keys = list(rs[0]["items"])
        taught = [k for k in keys if rs[0]["sources"].get(k) == "taught"]
        per_item = {k: round(sum(bool(r["items"].get(k)) for r in rs) / len(rs), 2) for k in keys}
        complete = [sum(r["items"].values()) / len(keys) for r in rs if keys]
        lines.append({"agent": agent, "arm": arm, "runs": len(rs), "model": rs[0].get("model"),
                      "completeness": round(sum(complete) / len(complete), 3) if complete else None,
                      "taught_applied": round(sum(per_item[k] for k in taught) / len(taught), 3) if taught else None,
                      "all_points": sum(r["verdict"] == "g" for r in rs), "items": per_item,
                      "median_s": bench._median([r["duration_s"] for r in rs]),
                      "median_tokens": bench._median([sum((r.get("tokens") or {}).values()) or None for r in rs]),
                      "median_cost_usd": bench._median([r.get("cost_usd") for r in rs]),
                      "named_page": sum(r.get("named_page", False) for r in rs)})
    teach_info = {}
    for d in teach_root().glob(f"{teach_id}/teach.json") if teach_id else []:
        teach_info = json.loads(d.read_text())
    return {"case": name, "teach": teach_id, "teach_info": teach_info, "lines": lines}


def render(rep: dict) -> str:
    if not rep["lines"]:
        return f"No transfer runs for {rep['case']} yet. Run `athos bench transfer {rep['case']}`."
    label = {"claude": "Claude Code", "codex": "Codex", "muse": "Muse Code", "opencode": "OpenCode"}
    t = rep.get("teach_info") or {}
    out = [f"# Transfer: {rep['case']}", "",
           f"Taught once in Claude Code ({rep['teach']}"
           + (f", US${t['cost_usd']:.2f}, {t['duration_s']:.0f} s" if t.get("cost_usd") is not None else "")
           + (f"; saved {', '.join('`' + p + '`' for p in t.get('pieces', []))}" if t.get("pieces") else "") + ").",
           "Replayed in a fresh folder with another contract and no checklist, from a one-line request.", "",
           "| Agent | Model | Arm | Runs | Points applied | Taught rules applied | All points | Time | Tokens | Cost |",
           "|---|---|---|---|---|---|---|---|---|---|"]
    for x in rep["lines"]:
        pct = lambda v: "–" if v is None else f"{v * 100:.0f}%"  # noqa: E731
        cost = "–" if x["median_cost_usd"] is None else f"${x['median_cost_usd']:.3f}"
        out.append(f"| {label.get(x['agent'], x['agent'])} | {x['model'] or '–'} | {x['arm']}: {ARM_NAMES[x['arm']]} "
                   f"| {x['runs']} | {pct(x['completeness'])} | {pct(x['taught_applied'])} | {x['all_points']}/{x['runs']} "
                   f"| {x['median_s'] or '–'} s | {int(x['median_tokens'] or 0):,} | {cost} |")
    keys = list(rep["lines"][0]["items"])
    out += ["", "## Point by point (share of runs that applied it)", "",
            "| Agent | Arm | " + " | ".join(keys) + " |", "|---|---|" + "---|" * len(keys)]
    for x in rep["lines"]:
        out.append(f"| {label.get(x['agent'], x['agent'])} | {x['arm']} | "
                   + " | ".join(f"{x['items'].get(k, 0) * 100:.0f}%" for k in keys) + " |")
    out += ["", "Points come from the person's checklist file, except `governing_law_row` and `push_first_line`, the",
            "two rules they added while teaching: those exist nowhere but in their know-how.", ""]
    return "\n".join(out)
