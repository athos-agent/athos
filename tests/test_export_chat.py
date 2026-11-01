import contextlib
import io
import json
from pathlib import Path
from unittest import mock

from athos import cli, store, wiki
from tests.helpers import TempHome

LEASE = """## #read_parties
**When:** a lease arrives for review.
**Do:** check who signs and that each party can sign, see [[guarantees#deep|the guarantee audit]].
**Because:** a lease signed by someone without power was void once.

## #check_term
**When:** the parties are clear.
**Do:** read the term and the renewal clause.
"""

TASKS = [
    {"task_id": "t1", "pieces": ["review-a-lease"], "request": "Review the Pine Street lease", "result": "ok",
     "started": "2026-10-01"},
    {"task_id": "t2", "pieces": ["review-a-lease"], "request": "Review the Oak Avenue lease", "result": "corrected",
     "started": "2026-10-02"},
    {"task_id": "t3", "pieces": ["review-a-lease"], "request": "Review the Elm Road lease", "result": "failed",
     "started": "2026-10-03"},
    {"task_id": "t4", "pieces": ["review-a-lease"], "request": "Review the Birch Lane lease", "result": "unevaluated",
     "started": "2026-10-04"},
    {"task_id": "t5", "pieces": ["review-a-lease"], "request": "review the PINE street lease", "result": "ok",
     "started": "2026-10-05"},
    {"task_id": "t6", "pieces": ["notes"], "request": "Tidy my notes", "result": "ok", "started": "2026-10-06"},
]


class ChatDatasetTest(TempHome):
    def pieces(self):
        store.create("Review a lease", "a client sends a lease to review", LEASE, piece_id="review-a-lease")
        store.create("Tidy notes", "the notes folder is messy", "1. sort by date\n2. merge duplicates",
                     piece_id="notes")

    def test_rows_are_situations_and_the_way_of_working(self):
        self.pieces()
        rows = wiki.chat_dataset(tasks=TASKS)
        lease = [r for r in rows if r["messages"][2]["content"].startswith("Review a lease")]
        self.assertEqual([r["messages"][1]["content"] for r in lease],
                         ["a client sends a lease to review", "Review the Pine Street lease"])  # dupes once
        answer = lease[0]["messages"][2]["content"]
        self.assertEqual(answer, "Review a lease\n\n"
                         "1. When a lease arrives for review: check who signs and that each party can sign, see the "
                         "guarantee audit. Because a lease signed by someone without power was void once.\n"
                         "2. When the parties are clear: read the term and the renewal clause.")
        for r in rows:
            self.assertEqual([m["role"] for m in r["messages"]], ["system", "user", "assistant"])
            self.assertIsNone(wiki.check_chat_row(r))
        users = [r["messages"][1]["content"] for r in rows]
        for left_out in ("Oak Avenue", "Elm Road", "Birch Lane"):     # corrected, failed, unmarked
            self.assertFalse([u for u in users if left_out in u])
        notes = [r for r in rows if r["messages"][2]["content"].startswith("Tidy notes")]
        self.assertEqual([r["messages"][1]["content"] for r in notes], ["the notes folder is messy", "Tidy my notes"])
        self.assertIn("1. sort by date", notes[0]["messages"][2]["content"])

    def test_check_chat_row_refuses_malformed_rows(self):
        ok = {"messages": [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}]}
        self.assertIsNone(wiki.check_chat_row(ok))
        bad = [
            [],
            {"messages": []},
            {"messages": [{"role": "system", "content": "s"}]},
            {"messages": [{"role": "user", "content": "a"}]},
            {"messages": [{"role": "user", "content": "a"}, {"role": "assistant", "content": "  "}]},
            {"messages": [{"role": "assistant", "content": "b"}, {"role": "user", "content": "a"}]},
            {"messages": [{"role": "user", "content": "a"}, {"role": "user", "content": "a"},
                          {"role": "assistant", "content": "b"}]},
            {"messages": [{"role": "bot", "content": "a"}, {"role": "assistant", "content": "b"}]},
        ]
        for row in bad:
            self.assertIsNotNone(wiki.check_chat_row(row), row)

    def run_export(self, *flags):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch("athos.eval.tasks", return_value=TASKS), contextlib.redirect_stdout(out), \
                contextlib.redirect_stderr(err):
            code = cli.main(["export", *flags])
        return code, out.getvalue(), err.getvalue()

    def test_cli_fireworks_and_openai_write_valid_jsonl(self):
        self.pieces()
        for fmt in ("fireworks", "openai"):
            dest = Path(self.home) / f"{fmt}.jsonl"
            code, out, err = self.run_export("--dataset", str(dest), "--format", fmt)
            self.assertIn(code, (0, None))
            lines = dest.read_text().splitlines()
            self.assertEqual(len(lines), 4)
            self.assertIn(f"4 rows to {dest}", out)
            for line in lines:
                self.assertIsNone(wiki.check_chat_row(json.loads(line)))
            self.assertEqual(bool(err), fmt == "openai")          # OpenAI wants 10 examples, Fireworks 3

    def test_cli_default_format_unchanged(self):
        self.pieces()
        dest = Path(self.home) / "default.jsonl"
        self.run_export("--dataset", str(dest))
        kinds = {json.loads(line)["kind"] for line in dest.read_text().splitlines()}
        self.assertEqual(kinds, {"statement", "task"})

    def test_cli_refuses_to_write_a_bad_row(self):
        self.pieces()
        dest = Path(self.home) / "bad.jsonl"
        with mock.patch("athos.wiki.chat_dataset", return_value=[{"messages": [{"role": "user", "content": "x"}]}]):
            code, _, err = self.run_export("--dataset", str(dest), "--format", "fireworks")
        self.assertEqual(code, 1)
        self.assertIn("row 1 would be refused", err)
        self.assertFalse(dest.exists())
