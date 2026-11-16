"""The dream cycle's opt-in model pass, offline with a stub runner, and the audit's rules about the cycle. All data
here is synthetic."""

import json
import os
import time
from pathlib import Path
from unittest import mock

from athos import audit, eval as ev, memory, paths, store, verify
from athos.memory import cycle, dream_model
from tests.test_memory_cycle import MemoryCase, write, task, stamp

ANSWER = {"project_page": "Releases go through the checklist; the keys rotate before each release.",
          "merge": [{"sources": ["ship", "ship-two"], "title": "Ship a release, the one way",
                     "when": "shipping a release of the service",
                     "body": "## #go\n**When:** shipping.\n**Do:** run the checklist.\n**Check:** `pytest` exits 0\n"}],
          "rules": [{"piece": "keys", "step": "one", "kind": "avoid", "text": "never rotate on a Friday"},
                    {"piece": "learned", "step": "one", "kind": "keep", "text": "tag after the tests pass"}]}


class Stub:
    def __init__(self, answer=ANSWER, cost=0.0123):
        self.calls, self.answer, self.cost = [], answer, cost

    def __call__(self, prompt, folder, model, timeout, cap):
        self.calls.append({"prompt": prompt, "files": sorted(str(p.relative_to(folder)) for p in Path(folder).rglob("*")
                                                             if p.is_file()), "cap": cap})
        return {"ok": True, "started": True, "text": json.dumps(self.answer), "cost_usd": self.cost,
                "duration_s": 1.0}


class ModelPassTest(MemoryCase):
    def setUp(self):
        super().setUp()
        p = store.get("ship")
        store._write(store.Piece(id="ship-two", title="Ship a release", when="shipping a release",
                                 body=p.body, projects=["alpha"], created="2026-11-01", last_used="2026-11-01",
                                 origin={"platform": "test", "model": "test"}))
        store.create("Tag the build", "tagging the build", "## #one\n**When:** done.\n**Do:** tag.\n",
                     projects=["alpha"], piece_id="learned", status="verified", learned_by="m", confidence="0.8")
        store._write(store.Piece(id="alpha-private", title="A private way", when="shipping a release quietly",
                                 body=p.body, projects=["alpha"], visibility="private", created="2026-11-01",
                                 last_used="2026-11-01", origin={"platform": "test", "model": "test"}))
        self.idle()

    def idle(self):
        old = time.time() - 3600
        for f in paths.sessions().glob("*.json") if paths.sessions().exists() else []:
            os.utime(f, (old, old))

    def test_off_by_default(self):
        out = cycle.run()
        self.assertNotIn("model", out)
        self.assertFalse([e for e in ev.events() if e.get("type") == "model_run"])

    def test_not_while_a_session_works(self):
        paths.sessions().mkdir(parents=True, exist_ok=True)
        (paths.sessions() / "busy.json").write_text("{}")
        stub = Stub()
        out = cycle.run(model=True, runner=stub)
        self.assertEqual(out["model"]["outcome"], "skipped: a session is working")
        self.assertEqual(stub.calls, [])

    def test_a_pass_proposes_candidates_and_never_rewrites_the_persons_pieces(self):
        legacy = {pid: store.get(pid).path.read_bytes() for pid in ("ship", "ship-two", "keys", "report")}
        stub = Stub()
        out = cycle.run(model=True, runner=stub)["model"]
        self.assertEqual(out["outcome"], "done")
        self.assertEqual(out["project"], "alpha")
        # It saw the project's own pieces as text, and a summary: never another project's, never a request.
        files = stub.calls[0]["files"]
        self.assertIn("summary.json", files)
        self.assertIn("pieces/ship.md", files)
        self.assertNotIn("pieces/report.md", files)
        self.assertNotIn("pieces/alpha-private.md", files)          # a private piece is never sent
        self.assertNotIn("please do the thing", stub.calls[0]["prompt"])
        self.assertEqual({pid: store.get(pid).path.read_bytes() for pid in legacy}, legacy)      # untouched
        merged = [p for p in store.all_pieces() if "dream:merge" in (p.evidence or [])]
        self.assertEqual(len(merged), 1)
        self.assertEqual((merged[0].status, merged[0].projects), ("candidate", ["alpha"]))
        self.assertTrue((verify.bundle_dir(merged[0], None) / "piece.md").exists())
        learned = store.get("learned")
        self.assertEqual((learned.version, learned.status), (2, "candidate"))     # verified again from scratch
        found = json.loads(memory.findings_file().read_text())
        self.assertEqual(found["proposed_rules"][0]["piece"], "keys")             # a legacy piece: proposed only
        page = (memory.projects_dir() / "alpha.candidate.md").read_text()
        self.assertIn("status: candidate", page)
        # Spent under the cap it shares with the verifier, reserved first.
        runs = [e for e in ev.events() if e.get("type") == "model_run" and e.get("purpose") == "dream"]
        self.assertEqual([e["phase"] for e in runs], ["reserved", "settled"])
        self.assertEqual(verify.spent_today()[0], 1)
        model_event = [e for e in ev.events() if e.get("type") == "memory_cycle" and e.get("phase") == "model"][0]
        self.assertEqual({w["status_before"] for w in model_event["wrote"]}, {"new", "verified"})
        done = [e for e in ev.events() if e.get("type") == "memory_cycle" and e.get("phase") == "done"][-1]
        self.assertAlmostEqual(done["spend_usd"], 0.0123)
        rules = {r["rule"]: r for r in audit._memory_rules(ev.events())}
        self.assertEqual(rules["memory_wrote_legacy"]["status"], "clean")
        self.assertEqual(rules["memory_model_over_cap"]["status"], "clean")

    def test_the_cap_stops_it_before_any_call(self):
        (Path(self.home) / "config.json").write_text(json.dumps({"autolearn": {"budget": {"usd_per_day": 0}}}))
        stub = Stub()
        out = cycle.run(model=True, runner=stub)["model"]
        self.assertTrue(out["outcome"].startswith("refused"))
        self.assertEqual(stub.calls, [])

    def test_a_merge_that_makes_the_router_worse_is_not_applied(self):
        with mock.patch.object(dream_model, "route_gate", return_value={"before": {}, "after": {}, "measured": True,
                                                                     "worse": True}):
            out = cycle.run(model=True, runner=Stub())["model"]
        self.assertTrue(out["merges"][0].startswith("rejected"))
        self.assertFalse([p for p in store.all_pieces() if "dream:merge" in (p.evidence or [])])

    def test_the_route_gate_measures_the_persons_good_tasks(self):
        gate = dream_model.route_gate(store.Piece(id="x", title="Unrelated", when="never matching words here",
                                                  body="b", projects=["alpha"]))
        self.assertEqual(gate["before"], gate["after"])
        self.assertFalse(gate["worse"])

    def good_tasks_that_route_to_ship(self):
        for i in range(4):
            write(task(f"route{i}", 2 - i * 0.1, pieces=("ship",), result="ok",
                       request="ship a release of the service, shipping the release"))
        self.assertEqual(dream_model.route_gate(store.get("ship"))["before"]["hit1"] > 0, True)

    def test_a_faithful_merge_is_not_rejected(self):
        # The merged piece is the same way of working as its sources: a load of it is a load of them.
        self.good_tasks_that_route_to_ship()
        ship = store.get("ship")
        draft = store.Piece(id="dream-draft", title=ship.title, when=ship.when, body=ship.body, projects=["alpha"],
                            status="candidate")
        gate = dream_model.route_gate(draft, sources=["ship", "ship-two"])
        self.assertTrue(gate["measured"])
        self.assertFalse(gate["worse"], gate)

    def test_with_no_good_tasks_the_gate_measures_nothing_and_nothing_is_saved(self):
        from athos import eval as ev_
        with mock.patch.object(ev_, "tasks", return_value=[]):
            out = cycle.run(model=True, runner=Stub())["model"]
        self.assertTrue(out["merges"][0].startswith("not measured"), out["merges"])
        self.assertFalse([p for p in store.all_pieces() if "dream:merge" in (p.evidence or [])])

    def test_the_session_that_started_the_cycle_does_not_count_as_working(self):
        paths.sessions().mkdir(parents=True, exist_ok=True)
        (paths.sessions() / "stopper.json").write_text("{}")            # its Stop hook just touched it
        stub = Stub()
        out = cycle.run(model=True, runner=stub, after_session="stopper")
        self.assertEqual(out["model"]["outcome"], "done")
        calls = []
        (Path(self.home) / "config.json").write_text(json.dumps({"memory": {"model": {"on": True}}}))
        with mock.patch.object(cycle, "due", return_value="late"):
            cycle.maybe_spawn(Path("/x/athos"), lambda argv, **kw: calls.append(argv), session_id="stopper")
        self.assertEqual(calls[-1][-2:], ["--after-session", "stopper"])

    def test_the_per_run_setting_caps_the_reservation(self):
        (Path(self.home) / "config.json").write_text(json.dumps({"memory": {"model": {"max_usd_per_run": 0.07}}}))
        stub = Stub()
        cycle.run(model=True, runner=stub)
        self.assertAlmostEqual(stub.calls[0]["cap"], 0.07)
        reserved = [e for e in ev.events() if e.get("type") == "model_run" and e.get("phase") == "reserved"]
        self.assertAlmostEqual(reserved[-1]["usd_reserved"], 0.07)


class AuditRulesTest(MemoryCase):
    def rules(self):
        audit._MEMORY_CHECK.clear()
        return {r["rule"]: r for r in audit._memory_rules(ev.events())}

    def test_clean_after_a_cycle(self):
        self.assertEqual(self.rules()["memory_archive_integrity"]["status"], "not_evaluated")
        cycle.run()
        r = self.rules()
        self.assertEqual((r["memory_archive_integrity"]["status"], r["memory_rollup_mismatch"]["status"],
                          r["memory_wrote_legacy"]["status"], r["memory_model_over_cap"]["status"]),
                         ("clean", "clean", "clean", "not_evaluated"))

    def test_a_rollup_that_disagrees_with_a_rebuild(self):
        cycle.run()
        roll = json.loads(memory.rollups_file().read_text())
        roll["sums"]["pieces"]["ship"]["uses"] += 5
        memory.write_json(memory.rollups_file(), roll)
        self.assertEqual(self.rules()["memory_rollup_mismatch"]["status"], "flagged")

    def test_an_archive_that_fails_its_integrity_check(self):
        cycle.run()
        seg = memory.manifest()["segments"][0]
        import gzip
        raw = gzip.decompress(memory.segment_path(seg).read_bytes()).replace(b"corrected", b"ok_______")
        memory.segment_path(seg).write_bytes(gzip.compress(raw))
        r = self.rules()
        self.assertEqual(r["memory_archive_integrity"]["status"], "flagged")
        self.assertEqual(r["memory_rollup_mismatch"]["status"], "not_evaluated")

    def test_a_cycle_that_wrote_into_a_legacy_piece(self):
        cycle.run()
        ev.audit({"type": "memory_cycle", "phase": "model", "wrote": [{"piece": "ship", "status_before": "legacy"}]})
        self.assertEqual(self.rules()["memory_wrote_legacy"]["status"], "flagged")

    def test_a_model_pass_outside_the_cap(self):
        ev.audit({"type": "model_run", "phase": "settled", "purpose": "dream", "run_id": "r9", "started": True,
                  "cost_usd": 0.1, "usd_per_day": 1.0, "runs_per_day": 6})
        self.assertEqual(self.rules()["memory_model_over_cap"]["status"], "flagged")
