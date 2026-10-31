import tempfile
from pathlib import Path

from athos import delegate, eval as ev, paths, session, store, wiki
from athos.delegate import route
from tests.helpers import TempHome

BODY = """## #extract
**When:** the invoices are in the folder.
**Do:** extract the totals into totals.csv.
**Model:** local

## #judge
**When:** the totals are extracted.
**Do:** decide which invoices look wrong, and why.
**Because:** this needs judgement.
**Model:** meta

## #table
**When:** the judgement is done.
**Do:** format the result as a table.
"""


def fake(platform, log, reply="done"):
    """A fake model for one backend: answers each turn with no tool call, and logs which model and step it got."""
    def chat(model, messages):
        log.append((platform, model, messages[-1]["content"]))
        return {"message": {"content": f"{reply} by {model}"}, "prompt_eval_count": 50, "eval_count": 5}
    return chat


class StatementModelTest(TempHome):
    def test_the_model_line_is_parsed_and_optional(self):
        p = store.create("Check invoices", "checking invoices", BODY)
        got = {s.id: s.model for s in wiki.statements(p)}
        self.assertEqual(got, {"extract": "local", "judge": "meta", "table": ""})
        self.assertEqual(wiki.statements(p)[1].because, "this needs judgement.")
        old = store.create("Old", "x", "1. do this\n2. then that")
        self.assertEqual(wiki.statements(old)[0].model, "")

    def test_specs(self):
        self.assertEqual(delegate.parse_spec("local"), ("local", delegate.DEFAULT_MODEL))
        self.assertEqual(delegate.parse_spec("meta"), ("meta", "muse-spark-1.3"))
        self.assertEqual(delegate.parse_spec("ollama:qwen3.5:9b"), ("local", "qwen3.5:9b"))
        self.assertEqual(delegate.parse_spec("meta:muse-wonder-1.0"), ("meta", "muse-wonder-1.0"))
        self.assertIsNone(delegate.parse_spec("gpt"))
        self.assertEqual(delegate.spec_of("local", "qwen3.5:9b"), "ollama:qwen3.5:9b")


class ByStepTest(TempHome):
    def setUp(self):
        super().setUp()
        self.piece = store.create("Check invoices", "checking invoices", BODY)
        self._dir = tempfile.TemporaryDirectory()
        self.cwd = Path(self._dir.name)
        self.log = []
        self.fns = {"local": fake("local", self.log), "meta": fake("meta", self.log)}

    def tearDown(self):
        self._dir.cleanup()
        super().tearDown()

    def run_it(self, **kw):
        return delegate.by_step(self.piece.id, "check October", ("local", "tiny:1b"), chat_fns=self.fns,
                                cwd=self.cwd, yes=True, out=lambda _: None, **kw)

    def test_each_step_runs_on_its_model_in_one_conversation(self):
        r = self.run_it(allow_hosted=True)
        self.assertEqual([(p, m) for p, m, _ in self.log],
                         [("local", delegate.DEFAULT_MODEL), ("meta", "muse-spark-1.3"), ("local", "tiny:1b")])
        self.assertEqual(self.log[1][2], "Now do only this step: #judge — decide which invoices look wrong, and why.")
        self.assertEqual(r["summary"], "done by tiny:1b")
        t = ev.tasks()[0]
        self.assertEqual((t["task_id"], t["platform"], t["pieces"]), (r["task_id"], "mixed", [self.piece.id]))
        self.assertEqual([(s["id"], s["model"], s["tokens"]["total"]) for s in t["steps"]],
                         [("extract", delegate.DEFAULT_MODEL, 55), ("judge", "muse-spark-1.3", 55),
                          ("table", "tiny:1b", 55)])
        self.assertEqual(t["tokens"]["total"], 165)

    def test_the_trail_ticks_each_step(self):
        r = self.run_it(allow_hosted=True)
        trail = session.load(f"delegate-{r['task_id']}")["trail"]
        self.assertEqual([(x["step"], x["done"]) for x in trail if x["kind"] == "step"],
                         [("extract", True), ("judge", True), ("table", True)])
        steps = [e for e in ev.events() if e["type"] == "trail"]
        self.assertTrue(all(e["task_id"] == r["task_id"] for e in steps))

    def test_a_hosted_step_needs_explicit_consent(self):
        with self.assertRaises(PermissionError) as e:
            self.run_it()
        self.assertIn("#judge", str(e.exception))
        self.assertEqual(self.log, [])
        self.assertEqual(ev.tasks(), [])

    def test_an_unknown_model_line_stops_before_running(self):
        store.update(self.piece.id, "x", body=BODY.replace("**Model:** local", "**Model:** gpt-9"))
        with self.assertRaises(ValueError):
            self.run_it(allow_hosted=True)
        self.assertEqual(self.log, [])


def by_step_task(steps, result):
    tid = ev.record_external("local", "x", ["check-invoices"], 1.0, {"total": 1},
                             steps=[{"id": sid, "platform": p, "model": m, "duration_s": 2.0,
                                     "tokens": {"total": 100}} for sid, p, m in steps])
    if result:
        ev.mark(result, tid)


class RouteTest(TempHome):
    def setUp(self):
        super().setUp()
        self.piece = store.create("Check invoices", "checking invoices", BODY.replace("**Model:** local\n", ""),
                                  piece_id="check-invoices")

    def test_too_few_runs_suggest_nothing(self):
        by_step_task([("extract", "local", "gemma4:12b")], "ok")
        r = route.table("check-invoices")
        self.assertIsNone(r["steps"][0]["suggest"])
        self.assertIn("not enough runs", route.render(r))

    def test_the_cheapest_clean_model_is_suggested_and_applied(self):
        for _ in range(3):
            by_step_task([("extract", "local", "qwen3.5:4b"), ("judge", "meta", "muse-spark-1.3"),
                          ("table", "local", "gemma4:12b")], "ok")
        # A larger model also ran #extract cleanly; the 4B one is cheaper. A failed task counts against every step's
        # model in it: #table on 4B never gets a suggestion.
        for _ in range(3):
            by_step_task([("extract", "local", "gemma4:12b")], "ok")
        by_step_task([("table", "local", "qwen3.5:4b")], "failed")
        by_step_task([("judge", "local", "gemma4:12b")], "corrected")
        r = route.table("check-invoices")
        got = {s["id"]: s["suggest"] for s in r["steps"]}
        self.assertEqual(got, {"extract": "ollama:qwen3.5:4b", "judge": "meta", "table": "local"})
        judge = next(s for s in r["steps"] if s["id"] == "judge")
        self.assertEqual([(m["model"], m["ok"], m["corrected"]) for m in judge["models"]],
                         [("gemma4:12b", 0, 1), ("muse-spark-1.3", 3, 0)])

        p, _ = route.apply("check-invoices")
        self.assertEqual(p.version, 2)
        self.assertIn("routed by results", p.history[0])
        self.assertTrue((paths.history() / p.id / "v1.md").is_file())
        self.assertEqual({s.id: s.model for s in wiki.statements(p)},
                         {"extract": "ollama:qwen3.5:4b", "judge": "meta", "table": "local"})
        self.assertIn("**Because:** this needs judgement.\n**Model:** meta\n", p.body)
        self.assertIsNone(route.apply("check-invoices")[0])        # nothing new: no new version

    def test_unmarked_runs_prove_nothing(self):
        for _ in range(5):
            by_step_task([("extract", "local", "qwen3.5:4b")], None)
        self.assertIsNone(route.table("check-invoices")["steps"][0]["suggest"])
