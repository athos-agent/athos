"""`athos bench`: the same task, several times, on each agent and model, with and without the know-how, and a verdict
that comes from the result itself (git, the tests, the files written), never from the model's own word.

Each case is a folder in `cases/`, or in your own `~/.athos/bench/cases/` (and any folder in `ATHOS_BENCH_CASES`,
separated by `:`), for cases whose data must stay on your machine: `case.json` (title, domain, when, request), `piece.md` (the know-how), `setup.py <dir>`
(builds a fresh workspace) and `check.py <dir>` (prints `{"verdict": "g|c|f", "score": 0..1, "missed": [...]}`).
`case.json` may also set `timeout_s` (default 900), `max_usd_per_run` (Claude Code's own budget cap), `max_steps`
(Athos's loop, default 20), `check_timeout_s` (default 300) and `network` (true lets Codex's and Muse Code's sandboxes
reach the network, e.g. to install packages) for long tasks.
Every run gets its own temporary workspace and its own temporary Athos home, so nothing touches the user's store or
their recorded tasks. Results go to `~/.athos/bench/results.jsonl`, apart from the real-work events.
"""

from __future__ import annotations

import json
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

from athos import paths

CASES = Path(__file__).parent / "cases"
AGENTS = ("claude", "codex", "muse", "opencode", "meta", "local")
TIMEOUT = 900
# Meta Model API list price for muse-spark-1.3 (US$ per 1M tokens, input / output), from third-party sources.
MUSE_SPARK_PRICE = (1.25, 4.25)
DEFAULT_MODELS = {"meta": "muse-spark-1.3", "muse": "muse-spark-1.3", "opencode": "muse-spark-1.3", "local": "gemma4:12b"}
CLAUDE_TOOLS = "Bash Read Edit Write Glob Grep"


def results_file() -> Path:
    return paths.home() / "bench" / "results.jsonl"


def case_dirs() -> list[Path]:
    extra = [Path(p).expanduser() for p in os.environ.get("ATHOS_BENCH_CASES", "").split(os.pathsep) if p]
    return [CASES, paths.home() / "bench" / "cases", *extra]


def cases() -> dict[str, dict]:
    out = {}
    for d in sorted(d for root in case_dirs() if root.is_dir() for d in root.iterdir()):
        if (d / "case.json").exists() and d.name not in out:
            out[d.name] = {**json.loads((d / "case.json").read_text()), "dir": d,
                           "piece": (d / "piece.md").read_text()}
    return out


def setup(case: dict, ws: Path) -> None:
    subprocess.run([sys.executable, str(case["dir"] / "setup.py"), str(ws)], check=True, capture_output=True,
                   text=True, timeout=120)
    if (ws / ".git").is_dir():                         # what agents write about themselves stays out of `git status`
        with open(ws / ".git" / "info" / "exclude", "a") as fh:
            fh.write("\n.agents/\n.muse/\n.codex/\n.claude/\n")


def check(case: dict, ws: Path) -> dict:
    r = subprocess.run([sys.executable, str(case["dir"] / "check.py"), str(ws)], capture_output=True, text=True,
                       timeout=int(case.get("check_timeout_s") or 300))
    try:
        return json.loads(r.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return {"verdict": "f", "score": 0.0, "missed": [f"check failed: {r.stderr.strip()[-300:]}"]}


def _timeout(case: dict) -> int:
    return int(case.get("timeout_s") or TIMEOUT)


def _env(home: Path) -> dict:
    return {**os.environ, "ATHOS_HOME": str(home), "ATHOS_CAPTURE": "off", "CLAUDE_CODE_AUTO_CONNECT_IDE": "false"}


def _isolated(home: Path) -> dict:
    """Muse Code and OpenCode keep their config, plugins and sessions under XDG folders: a run gets its own, so the
    person's installed plugins (Athos's included) neither run nor record anything, and their sessions stay clean."""
    return {"XDG_CONFIG_HOME": str(home / "xdg-config"), "XDG_DATA_HOME": str(home / "xdg-data")}


def _meta_key() -> str:
    from athos.adapters import meta
    key = meta.api_key()
    if not key:
        raise PermissionError("no Meta Model API key: put a MODEL_API_KEY=... line in ~/.athos/.env")
    return key


def _spark_cost(model: str, tokens: dict) -> float | None:
    return round(tokens["input"] / 1e6 * MUSE_SPARK_PRICE[0] + tokens["output"] / 1e6 * MUSE_SPARK_PRICE[1], 4) \
        if model.startswith("muse-spark") else None


def _skill(case: dict) -> str:
    return (f"---\nname: bench-{case['dir'].name}\ndescription: {case['title']}. When: {case['when']}\n---\n\n"
            f"# {case['title']}\n\n{case['piece']}")


# --- one runner per agent. Each returns {"tokens": {...}, "cost_usd": float|None, "model": str, "note": str}. ---

def run_claude(case, ws, home, with_piece, model=None):
    cmd = ["claude", "-p", case["request"], "--output-format", "json", "--permission-mode", "acceptEdits",
           "--allowedTools", CLAUDE_TOOLS, "--no-session-persistence"]
    if model:
        cmd += ["--model", model]
    if case.get("max_usd_per_run"):
        cmd += ["--max-budget-usd", str(case["max_usd_per_run"])]
    if with_piece:
        cmd += ["--append-system-prompt", f"Know-how for this kind of task ({case['title']}):\n\n{case['piece']}"]
    r = subprocess.run(cmd, cwd=ws, env=_env(home), capture_output=True, text=True, timeout=_timeout(case))
    try:
        out = json.loads(r.stdout)
    except ValueError:
        return {"tokens": {}, "cost_usd": None, "model": model or "default", "note": r.stderr.strip()[-200:]}
    u = out.get("usage") or {}
    tokens = {"input": u.get("input_tokens", 0) + u.get("cache_read_input_tokens", 0) +
              u.get("cache_creation_input_tokens", 0), "output": u.get("output_tokens", 0)}
    mu = out.get("modelUsage") or {}
    main_model = max(mu, key=lambda k: (mu[k] or {}).get("costUSD") or 0) if mu else None
    return {"tokens": tokens, "cost_usd": out.get("total_cost_usd"), "model": model or main_model or "default",
            "note": "" if not out.get("is_error") else str(out.get("result"))[:200]}


def run_codex(case, ws, home, with_piece, model=None):
    if with_piece:
        d = ws / ".agents" / "skills" / f"bench-{case['dir'].name}"
        d.mkdir(parents=True, exist_ok=True)
        (d / "SKILL.md").write_text(_skill(case))
    cmd = ["codex", "exec", "--json", "--ephemeral", "--skip-git-repo-check", "-s", "workspace-write", "-C", str(ws)]
    if (ws / ".git").is_dir():
        cmd += ["-c", f'sandbox_workspace_write.writable_roots=["{ws / ".git"}"]']
    if model:
        cmd += ["-m", model]
    if case.get("network"):
        cmd += ["-c", "sandbox_workspace_write.network_access=true"]
    r = subprocess.run(cmd + [case["request"]], cwd=ws, env=_env(home), capture_output=True, text=True,
                       timeout=_timeout(case), stdin=subprocess.DEVNULL)
    tokens = {"input": 0, "output": 0}
    for line in r.stdout.splitlines():
        try:
            d = json.loads(line)
        except ValueError:
            continue
        u = d.get("usage") if isinstance(d, dict) else None
        if isinstance(u, dict):
            tokens["input"] += int(u.get("input_tokens") or 0)
            tokens["output"] += int(u.get("output_tokens") or 0)
    return {"tokens": tokens, "cost_usd": None, "model": model or "default",
            "note": "" if r.returncode == 0 else r.stderr.strip()[-200:]}


def run_muse(case, ws, home, with_piece, model=None):
    model = model or "muse-spark-1.3"
    if with_piece:
        d = ws / ".agents" / "skills" / f"bench-{case['dir'].name}"
        d.mkdir(parents=True, exist_ok=True)
        (d / "SKILL.md").write_text(_skill(case))
    cmd = ["muse", "exec", "--json", "--model", model, "--trust-workspace", "--disable-approval",
           "--no-foreign-personal-context", "--api-key-stdin", "--workspace", str(ws)]
    if case.get("network"):
        cmd += ["--sandbox-network", "enabled"]
    cmd.append(case["request"])
    r = subprocess.run(cmd, cwd=ws, env={**_env(home), **_isolated(home)}, capture_output=True, text=True,
                       timeout=_timeout(case), input=_meta_key())
    tokens, note = {"input": 0, "output": 0}, ""
    for line in r.stdout.splitlines():
        try:
            d = json.loads(line)
        except ValueError:
            continue
        p = d.get("payload") or {}
        if d.get("payload_type") == "run.usage":
            for m in p.get("models") or []:
                tokens["input"] += int(m.get("input_tokens") or 0)
                tokens["output"] += int(m.get("output_tokens") or 0) + int(m.get("reasoning_tokens") or 0)
        elif d.get("payload_type", "").startswith("run.terminal.") and p.get("terminal") != "completed":
            note = f"{p.get('terminal')}: {p.get('reason') or ''}"[:200]
    if r.returncode and not note:
        note = r.stderr.strip()[-200:]
    return {"tokens": tokens, "cost_usd": _spark_cost(model, tokens), "model": model, "note": note}


OPENCODE_CONFIG = {"$schema": "https://opencode.ai/config.json",
                   "provider": {"meta": {"npm": "@ai-sdk/openai-compatible", "name": "Meta Model API",
                                         "options": {"baseURL": "https://api.meta.ai/v1",
                                                     "apiKey": "{env:MODEL_API_KEY}"},
                                         "models": {"muse-spark-1.3": {"name": "Muse Spark 1.3"},
                                                    "muse-wonder-1.0": {"name": "Muse Wonder 1.0"}}}}}


def _opencode_events(stdout: str, tokens: dict) -> tuple[bool, str, str]:
    """Adds a run's tokens; returns whether it changed anything (a write, an edit, a command), its last text and an
    error, if any. Reading files and then stopping is the stall a nudge is for."""
    acted, last, note = False, "", ""
    for line in stdout.splitlines():
        try:
            d = json.loads(line)
        except ValueError:
            continue
        kind = d.get("type")
        if kind == "tool_use":
            acted = acted or (d.get("part") or {}).get("tool") in ("write", "edit", "multiedit", "patch", "bash")
        elif kind == "text":
            last = (d.get("part") or {}).get("text") or last
        elif kind == "step_finish":
            t = (d.get("part") or {}).get("tokens") or {}
            tokens["input"] += int(t.get("input") or 0) + int((t.get("cache") or {}).get("read") or 0)
            tokens["output"] += int(t.get("output") or 0) + int(t.get("reasoning") or 0)
        elif kind == "error":
            note = json.dumps(d.get("error") or d)[:200]
    return acted, last, note


def run_opencode(case, ws, home, with_piece, model=None, pure=True):
    """OpenCode on Meta Model API, with its own config and session store and, unless `pure` is off, no plugin.
    Headless, Muse Spark sometimes announces what it will do and stops before changing anything; a person would say
    "go ahead", so such a run gets that one nudge in the same session (every arm alike)."""
    model = model or "muse-spark-1.3"
    if with_piece:
        d = ws / ".agents" / "skills" / f"bench-{case['dir'].name}"
        d.mkdir(parents=True, exist_ok=True)
        (d / "SKILL.md").write_text(_skill(case))
    cfg = home / "xdg-config" / "opencode"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "opencode.json").write_text(json.dumps(OPENCODE_CONFIG))
    env = {**_env(home), **_isolated(home), "MODEL_API_KEY": _meta_key()}
    base = ["opencode", "run"] + (["--pure"] if pure else []) + ["--format", "json", "-m", f"meta/{model}",
                                                                 "--dir", str(ws)]
    tokens, nudged = {"input": 0, "output": 0}, False
    r = subprocess.run(base + [case["request"]], cwd=ws, env=env, capture_output=True, text=True,
                       timeout=_timeout(case), stdin=subprocess.DEVNULL)
    acted, last, note = _opencode_events(r.stdout, tokens)
    if not acted and r.returncode == 0:
        nudged = True
        r = subprocess.run(base + ["--continue", "Go ahead."], cwd=ws, env=env, capture_output=True, text=True,
                           timeout=_timeout(case), stdin=subprocess.DEVNULL)
        acted, last, note = _opencode_events(r.stdout, tokens)
    if r.returncode and not note:
        note = r.stderr.strip()[-200:]
    note = ("nudged once; " if nudged else "") + note
    return {"tokens": tokens, "cost_usd": _spark_cost(model, tokens), "model": model, "note": note.strip("; "),
            "last_text": last[-600:]}


def _run_delegate(case, ws, home, with_piece, model, platform):
    """Athos's own loop (`athos delegate`), in-process, against a temporary store holding only this case's piece."""
    from athos import delegate, store
    old = os.environ.get("ATHOS_HOME")
    os.environ["ATHOS_HOME"] = str(home)
    try:
        body = case["piece"] if with_piece else "No know-how for this task yet: work it out from the files."
        p = store.create(case["title"], case["when"], body, origin={"platform": "bench", "model": "bench"})
        if platform == "meta":
            from athos.adapters import meta
            chat_fn, model = meta.chat, model or meta.DEFAULT_MODEL
        else:
            chat_fn, model = delegate.chat, model or delegate.DEFAULT_MODEL
        r = delegate.delegate(p.id, case["request"], model, cwd=ws, yes=True, out=lambda *_: None,
                              max_steps=int(case.get("max_steps") or delegate.MAX_STEPS),
                              chat_fn=chat_fn, platform=platform)
    finally:
        if old is None:
            os.environ.pop("ATHOS_HOME", None)
        else:
            os.environ["ATHOS_HOME"] = old
    t = r["tokens"]
    cost = _spark_cost(model, t) if platform == "meta" else (0.0 if platform == "local" else None)
    return {"tokens": {"input": t["input"], "output": t["output"]}, "cost_usd": cost, "model": model,
            "note": r["summary"][:200] if r["summary"].startswith("(stopped") else ""}


def run_meta(case, ws, home, with_piece, model=None):
    return _run_delegate(case, ws, home, with_piece, model, "meta")


def run_local(case, ws, home, with_piece, model=None):
    return _run_delegate(case, ws, home, with_piece, model, "local")


RUNNERS = {"claude": run_claude, "codex": run_codex, "muse": run_muse, "opencode": run_opencode, "meta": run_meta,
           "local": run_local}


def run_once(name: str, case: dict, agent: str, with_piece: bool = True, model: str | None = None,
             runner=None, keep: bool = False) -> dict:
    """One run in a fresh workspace: set up, let the agent work, check what it left. Returns the result row."""
    tmp = Path(tempfile.mkdtemp(prefix="athos-bench-"))
    ws, home = tmp / "work", tmp / "home"
    home.mkdir()
    setup(case, ws)
    t0 = time.monotonic()
    model = model or DEFAULT_MODELS.get(agent)        # so a run that crashes still says which model it was
    try:
        out = (runner or RUNNERS[agent])(case, ws, home, with_piece, model)
    except subprocess.TimeoutExpired:
        out = {"tokens": {}, "cost_usd": None, "model": model or "default",
               "note": f"timed out after {_timeout(case)} s"}
    except Exception as e:  # noqa: BLE001 — a crashed agent is a failed run, not a crashed bench
        out = {"tokens": {}, "cost_usd": None, "model": model or "default", "note": f"{type(e).__name__}: {e}"[:200]}
    duration = round(time.monotonic() - t0, 1)
    res = check(case, ws)
    row = {"id": uuid.uuid4().hex[:12], "at": time.strftime("%Y-%m-%dT%H:%M:%S"), "case": name, "agent": agent,
           "model": out.get("model"), "know_how": with_piece, "verdict": res.get("verdict", "f"),
           "score": res.get("score"), "missed": res.get("missed", []), "duration_s": duration,
           "tokens": out.get("tokens") or {}, "cost_usd": out.get("cost_usd"), "note": out.get("note", "")}
    for k in ("stages_done", "stages_total", "invented", "check_cost_usd"):
        if k in res:
            row[k] = res[k]
    if keep:
        row["workspace"] = str(ws)
    else:
        shutil.rmtree(tmp, ignore_errors=True)
    return row


def save(row: dict) -> None:
    f = results_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    with open(f, "a") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def load_results() -> list[dict]:
    try:
        return [json.loads(line) for line in results_file().read_text().splitlines() if line.strip()]
    except OSError:
        return []


def run(names: list[str], agents: list[str], runs: int = 5, with_piece: bool = True, without_piece: bool = False,
        models: dict | None = None, max_usd: float | None = None, out=print, runner=None, keep: bool = False) -> list:
    """Every case × agent × arm, `runs` times, interleaved so a slow afternoon hurts every agent alike. Stops before a
    run once the money spent in this call reaches `max_usd`."""
    all_cases = cases()
    arms = ([True] if with_piece else []) + ([False] if without_piece else [])
    rows, spent = [], 0.0
    for i in range(runs):
        for name in names:
            for agent in agents:
                for arm in arms:
                    if max_usd is not None and spent >= max_usd:
                        out(f"stopped: US${spent:.2f} spent, the cap is US${max_usd:.2f}")
                        return rows
                    row = run_once(name, all_cases[name], agent, arm, (models or {}).get(agent), runner, keep)
                    save(row)
                    rows.append(row)
                    spent += (row["cost_usd"] or 0.0) + (row.get("check_cost_usd") or 0.0)
                    cost = f"US${row['cost_usd']:.3f}" if row["cost_usd"] is not None else "cost unknown"
                    out(f"{i + 1}/{runs} {name:<15} {agent:<6} {'with' if arm else 'without':<7} know-how: "
                        f"{row['verdict']} ({row['score']}) {row['duration_s']} s, {cost}"
                        + (f"  missed: {', '.join(row['missed'][:4])}" if row["missed"] else "")
                        + (f"  [{row['note']}]" if row["note"] else ""))
    return rows


def _median(xs):
    xs = [x for x in xs if x is not None]
    return round(statistics.median(xs), 4) if xs else None


def report(rows: list[dict] | None = None) -> dict:
    """Per case, per agent/model and arm: runs, g/c/f, success rate, median time, tokens and cost; and per case the
    cheapest agent whose success rate matches the best one with the know-how."""
    rows = load_results() if rows is None else rows
    groups: dict[tuple, list] = {}
    for r in rows:
        groups.setdefault((r["case"], r["agent"], r.get("model"), r.get("know_how", True)), []).append(r)
    out = {}
    for (case, agent, model, kh), rs in sorted(groups.items(), key=lambda kv: (kv[0][0], kv[0][1], str(kv[0][2]),
                                                                             not kv[0][3])):
        n = len(rs)
        g = sum(r["verdict"] == "g" for r in rs)
        line = {"agent": agent, "model": model, "know_how": kh, "runs": n, "g": g,
                "c": sum(r["verdict"] == "c" for r in rs), "f": sum(r["verdict"] == "f" for r in rs),
                "success": round(g / n, 3), "median_score": _median([r.get("score") for r in rs]),
                "median_s": _median([r["duration_s"] for r in rs]),
                "median_tokens": _median([sum((r.get("tokens") or {}).values()) or None for r in rs]),
                "median_cost_usd": _median([r.get("cost_usd") for r in rs])}
        if any("invented" in r for r in rs):
            line["median_invented"] = _median([r.get("invented") for r in rs])
            line["median_stages"] = _median([r.get("stages_done") for r in rs])
            line["stages_total"] = max((r.get("stages_total") or 0 for r in rs), default=0) or None
        out.setdefault(case, {"lines": []})["lines"].append(line)
    for case, c in out.items():
        with_kh = [x for x in c["lines"] if x["know_how"]]
        best = max((x["success"] for x in with_kh), default=0)
        ok = [x for x in with_kh if x["success"] >= best and best > 0 and x["median_cost_usd"] is not None]
        if ok:
            pick = min(ok, key=lambda x: x["median_cost_usd"])
            c["recommend"] = {"agent": pick["agent"], "model": pick["model"], "success": pick["success"],
                              "median_cost_usd": pick["median_cost_usd"]}
    return out


def render(rep: dict) -> str:
    if not rep:
        return "No bench results yet. Run `athos bench <case|all> --agents claude,meta`."
    lines = []
    for case, c in rep.items():
        lines.append(f"\n{case}")
        lines.append(f"  {'agent / model':<34} {'know-how':<8} {'runs':>4}  {'g/c/f':<7} {'success':>7} "
                     f"{'time':>7} {'tokens':>8} {'cost':>8}")
        for x in c["lines"]:
            cost = f"${x['median_cost_usd']:.3f}" if x["median_cost_usd"] is not None else "?"
            tok = f"{int(x['median_tokens']):,}" if x["median_tokens"] else "?"
            of = f"/{x['stages_total']}" if x.get("stages_total") else ""
            st = "?" if x.get("median_stages") is None else f"{x['median_stages']:g}"
            inv = "?" if x.get("median_invented") is None else f"{x['median_invented']:g}"
            extra = f"  stages {st}{of}, invented {inv}" \
                if "median_invented" in x else ""
            lines.append(f"  {(x['agent'] + ' / ' + str(x['model']))[:34]:<34} {'with' if x['know_how'] else 'without':<8}"
                         f" {x['runs']:>4}  {x['g']}/{x['c']}/{x['f']:<3} {x['success']:>7.0%} {x['median_s']:>6}s "
                         f"{tok:>8} {cost:>8}{extra}")
        if c.get("recommend"):
            r = c["recommend"]
            lines.append(f"  → cheapest at the best success rate ({r['success']:.0%}): {r['agent']} / {r['model']}, "
                         f"${r['median_cost_usd']:.3f} a run")
    lines.append("\nMedians per run. Verdicts come from each case's check (git, tests, files), not from the agents.")
    return "\n".join(lines).lstrip("\n")
