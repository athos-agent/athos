import io
import json
import os
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

from athos import cli, eval as ev, guild, mcp, paths, store, trail
from tests.helpers import TempHome

MINE = """## #read
**When:** the lease is open.
**Do:** Read it whole before commenting.

## #term
**When:** checking the term of the lease.
**Do:** Note the start and end dates.
**Links:** [[review-a-lease#rent]]

## #rent
**When:** checking the rent clause.
**Do:** Check the rent and its index.

## #guess
**When:** a clause is unclear.
**Do:** Guess what the parties meant.
"""

ANA = """## #read
**When:** the lease is open.
**Do:** Read it whole before commenting.

## #term
**When:** checking the term of the lease.
**Do:** Note the start and end dates, and any automatic renewal.
**Links:** [[review-a-lease#rent]]

## #deposit
**When:** checking the deposit clause.
**Do:** Check the deposit is at most two months of rent.

## #rent_index
**When:** checking the rent clause and its index.
**Do:** Check the rent, its index and how often it is updated.
"""

LUIS = """## #read
**When:** the lease is open.
**Do:** Read it whole before commenting.

## #pets
**When:** the tenant has pets.
**Do:** Ask the client whether pets matter to them.
"""


def counts(ok=0, corrected=0, failed=0):
    return {"tasks": ok + corrected + failed, "ok": ok, "corrected": corrected, "failed": failed, "unmarked": 0}


class GuildTest(TempHome):
    def setUp(self):
        super().setUp()
        store.create("Review a lease", "reviewing a lease for a client", MINE, piece_id="review-a-lease")
        self.team = Path(self.home) / "team"

    def colleague(self, who, body, stats=None, pid="review-a-lease"):
        d = self.team / who.lower()
        d.mkdir(parents=True, exist_ok=True)
        p = store.Piece(id=pid, title="Review a lease", when="reviewing a lease", body=body, version=3,
                        origin={"platform": "claude-code"}, history=["v3 2026-10-20: tidy"])
        (d / f"{pid}.md").write_text(store.render(p))
        if stats is not None:
            (d / f"{pid}.stats.json").write_text(json.dumps({"piece": pid, "owner": who, "statements": stats}))

    def walk(self, steps, result):
        """A task of mine that walked these statements and was marked."""
        sid = f"s{len(ev.events())}"
        tid = ev.task_start({"session_id": sid, "prompt": "review the lease of client X"})
        for s in steps:
            trail.step(sid, f"review-a-lease#{s}", None)
        ev.task_end({"session_id": sid})
        ev.mark(result, tid)

    def test_stats_count_steps_and_marks_and_say_nothing_of_the_request(self):
        self.walk(["read", "term"], "g")
        self.walk(["read", "guess"], "f")
        st = guild.stats("review-a-lease", "Mati")
        self.assertEqual(st["owner"], "Mati")
        self.assertEqual(st["statements"]["read"], {"tasks": 2, "ok": 1, "corrected": 0, "failed": 1, "unmarked": 0})
        self.assertEqual(st["statements"]["rent"]["tasks"], 0)
        out = Path(self.home) / "out"
        with redirect_stdout(io.StringIO()):
            self.assertEqual(cli.main(["export", "--guild", str(out), "--piece", "review-a-lease", "--as", "Mati"]), 0)
        self.assertEqual(sorted(f.name for f in out.iterdir()), ["review-a-lease.md", "review-a-lease.stats.json"])
        self.assertNotIn("client X", (out / "review-a-lease.stats.json").read_text())

    def test_deterministic_merge_keeps_takes_and_drops_by_record(self):
        for _ in range(2):
            self.walk(["guess"], "c")                               # my #guess mostly needed corrections
        self.colleague("Ana", ANA, {"term": counts(ok=4), "deposit": counts(ok=2), "rent_index": counts(ok=1)})
        self.colleague("Luis", LUIS, {"pets": counts(corrected=1, failed=2)})
        r = guild.merge("review-a-lease", guild.find_variants([str(self.team)], "review-a-lease"))
        d = {x["id"]: x for x in r["decisions"]}
        self.assertEqual(d["read"]["action"], "same")
        self.assertEqual((d["term"]["action"], d["term"]["from"]), ("chosen", "Ana"))   # 4/4 beats unmarked
        self.assertIn("automatic renewal", r["body"])
        self.assertEqual((d["deposit"]["action"], d["deposit"]["from"]), ("added", "Ana"))
        self.assertEqual((d["pets"]["action"], d["pets"]["from"]), ("dropped", "Luis"))
        self.assertEqual((d["guess"]["action"], d["guess"]["from"]), ("dropped", "you"))
        # Ana's #rent_index is the same moment as my #rent: aligned, and it keeps my id so links still resolve.
        self.assertNotIn("rent_index", d)
        self.assertEqual(d["rent"]["from"], "Ana")
        self.assertIn("## #rent\n**When:** checking the rent clause and its index.", r["body"])
        self.assertLess(r["body"].index("#term"), r["body"].index("#deposit"))   # after what it follows in Ana's
        self.assertNotIn("#pets", r["body"])
        self.assertIn("[[review-a-lease#rent]]", r["body"])

    def test_dry_run_writes_a_proposal_and_apply_saves_a_new_version(self):
        self.colleague("Ana", ANA, {"term": counts(ok=3)})
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(cli.main(["merge", "review-a-lease", str(self.team / "ana")]), 0)
        self.assertIn("took the text of Ana: #term", out.getvalue())
        self.assertIn("added from Ana: #deposit", out.getvalue())
        self.assertEqual(store.get("review-a-lease").version, 1)                       # nothing changed yet
        prop = store.parse(guild.proposal_file("review-a-lease").read_text())
        self.assertIn("automatic renewal", prop.body)
        with redirect_stdout(io.StringIO()):
            self.assertEqual(cli.main(["merge", "review-a-lease", str(self.team / "ana"), "--apply"]), 0)
        p = store.get("review-a-lease")
        self.assertEqual(p.version, 2)
        self.assertIn("automatic renewal", p.body)
        self.assertIn("merged with Ana (v3)", p.history[0])
        self.assertTrue((paths.history() / "review-a-lease" / "v1.md").is_file())

    def test_a_different_id_with_as_id_and_no_stats(self):
        self.colleague("Ana", ANA, None, pid="lease-review")
        with redirect_stdout(io.StringIO()):
            self.assertEqual(cli.main(["merge", "review-a-lease", str(self.team)]), 1)   # nothing named like mine
        r = guild.merge("review-a-lease", guild.find_variants([str(self.team)], "lease-review"))
        d = {x["id"]: x for x in r["decisions"]}
        self.assertEqual(d["term"]["from"], "you")          # nobody marked anything: the person's own text stays
        self.assertEqual(d["deposit"]["action"], "added")    # no stats: kept

    def test_a_model_merges_differing_texts_and_a_bad_answer_falls_back(self):
        self.colleague("Ana", ANA, {"term": counts(ok=1)})
        asked = []

        def fake(model, messages):
            asked.append((model, messages[-1]["content"]))
            sid = messages[0]["content"].split("## #")[1].split("`")[0]
            if sid == "term":
                return {"message": {"content": "## #term\n**When:** checking the term of the lease.\n**Do:** Note "
                                               "the dates and any automatic renewal.\n**Links:** [[review-a-lease#rent]]"}}
            return {"message": {"content": "Sure! Here it is."}}

        r = guild.merge("review-a-lease", guild.find_variants([str(self.team)], "review-a-lease"),
                        model="m", chat_fn=fake)
        d = {x["id"]: x for x in r["decisions"]}
        self.assertEqual(d["term"]["action"], "merged")
        self.assertIn("Note the dates and any automatic renewal.", r["body"])
        self.assertEqual(d["rent"]["action"], "chosen")
        self.assertIn("not one usable statement", d["rent"]["why"])
        self.assertIn("Version from Ana (1/1 good)", asked[0][1])

    def test_the_chat_can_merge_through_mcp(self):
        self.colleague("Ana", ANA, {"term": counts(ok=2)})
        text = mcp.call("athos_merge", {"id": "review-a-lease", "paths": [str(self.team)]})
        self.assertIn("Proposal in", text)
        self.assertEqual(store.get("review-a-lease").version, 1)
        text = mcp.call("athos_merge", {"id": "review-a-lease", "paths": [str(self.team)], "apply": True})
        self.assertIn("v2", text)
        with self.assertRaises(LookupError):
            mcp.call("athos_merge", {"id": "review-a-lease", "paths": [os.path.join(self.home, "nope")]})
