import contextlib
import io
import json
import os
import socket
from pathlib import Path
from unittest import mock

from athos import cli, eval as ev, load, store
from athos.bench import route
from athos.load import embed
from tests.helpers import TempHome

# A fake embedding model: each word maps to a concept, in English or Spanish, so a Spanish request and an English
# piece land close without sharing a word. No network.
CONCEPTS = {"contract": 0, "contrato": 0, "agreement": 0, "acuerdo": 0, "lease": 0, "alquiler": 0,
            "match": 1, "partido": 1, "report": 2, "informe": 2, "training": 3, "entrenamiento": 3}


def fake(texts, model, timeout):
    out = []
    for t in texts:
        v = [0.05] * 6
        for w in t.lower().replace("?", " ").replace(",", " ").split():
            if w in CONCEPTS:
                v[CONCEPTS[w]] += 1.0
        out.append(v)
    return out


def seed():
    store.create("Review a contract against your checklist", "reviewing a contract before signing it",
                 "## #parties\n**When:** with the contract at hand.\n**Do:** list the parties.\n", piece_id="contract")
    store.create("Write the post-match report", "after a match, preparing the report",
                 "## #data\n**When:** with the match stats.\n**Do:** count.\n", piece_id="match")
    store.create("Plan the training week", "planning next week's training", "Plan it.", piece_id="training")


class RouteBenchTest(TempHome):
    def test_cases_name_starter_pieces_that_exist(self):
        data = route.load_cases()
        ids = {pid for lang in ("en", "es") for pid, *_ in route.starter_pages(lang)}
        for topic in data["topics"].values():
            self.assertIn(topic["en"], ids)
            self.assertIn(topic["es"], ids)
        kinds = {c["kind"] for c in data["cases"]}
        self.assertEqual(kinds, {"direct", "paraphrase", "negative"})

    def test_distractors_are_deterministic_and_unique(self):
        a, b = route.distractors(50), route.distractors(50)
        self.assertEqual(a, b)
        self.assertEqual(len({p[0] for p in a}), 50)

    def test_run_uses_a_throwaway_store_and_reports_every_store(self):
        before = os.environ["ATHOS_HOME"]
        rows = route.run(["lexical"], scale=40)
        self.assertEqual(os.environ["ATHOS_HOME"], before)
        self.assertEqual([r["store"] for r in rows], ["en+es", "es→en", "en→es", "en+es 40p"])
        self.assertEqual(rows[-1]["pages"], 40)
        self.assertEqual(rows[0]["positives"] + rows[0]["negatives"], len(route.load_cases()["cases"]))
        self.assertFalse(store.all_pieces())                      # nothing was written to this home
        self.assertIn("hit@1", route.render(rows))

    def test_from_store_counts_good_tasks_only_and_prints_no_request(self):
        seed()
        for tid, prompt, pieces, res in (("t1", "review this contract before signing", ["contract"], "g"),
                                         ("t2", "plan next week's training", ["training"], "c"),
                                         ("t3", "what time is it", [], "g")):
            ev.append({"type": "task_start", "task_id": tid, "session_id": "s", "at": "2026-10-31T10:00:00+00:00",
                       **ev.request_fields(prompt)})
            ev.append({"type": "task_end", "task_id": tid, "session_id": "s", "at": "2026-10-31T10:01:00+00:00",
                       "pieces": pieces})
            ev.mark(res, tid)
        size = Path(ev.paths.events_file()).stat().st_size
        r = route.from_store(meaning=False)
        self.assertEqual((r["tasks"], r["hit1"], r["none_tasks"], r["none_loads"]), (1, 1, 1, 0))
        self.assertEqual(Path(ev.paths.events_file()).stat().st_size, size)       # read-only
        self.assertNotIn("contract", route.render_store(r))


class MeaningTest(TempHome):
    def setUp(self):
        super().setUp()
        seed()
        self.pieces = store.all_pieces()

    def meaning(self, prompt, pieces):
        return embed.scores(prompt, pieces, embed_fn=fake, spawn=False)

    def test_words_only_is_unchanged_when_the_setting_is_off(self):
        spanish = "revisá este acuerdo de alquiler"
        self.assertEqual(load.relevant(spanish, self.pieces), [])
        with mock.patch.object(embed, "ollama", side_effect=AssertionError("no call while off")):
            self.assertEqual([p.id for p in load.relevant("review this contract", self.pieces)], ["contract"])

    def test_meaning_finds_a_piece_that_shares_no_word(self):
        embed.refresh(self.pieces, embed_fn=fake)
        found = load.relevant("revisá este acuerdo de alquiler", self.pieces, meaning=self.meaning)
        self.assertEqual([p.id for p in found], ["contract"])
        self.assertEqual(load.relevant("what time is it", self.pieces, meaning=self.meaning), [])

    def test_a_sure_lexical_match_never_asks_the_model(self):
        calls = []
        load.relevant("review the contract against my checklist before signing", self.pieces,
                      meaning=lambda p, ps: calls.append(p) or {})
        self.assertEqual(calls, [])

    def test_ollama_down_falls_back_to_words(self):
        embed.refresh(self.pieces, embed_fn=fake)

        def down(texts, model, timeout):
            raise socket.timeout("timed out")
        self.assertIsNone(embed.scores("revisá este acuerdo", self.pieces, embed_fn=down, spawn=False))
        meaning = lambda p, ps: embed.scores(p, ps, embed_fn=down, spawn=False)
        self.assertEqual(load.relevant("revisá este acuerdo de alquiler", self.pieces, meaning=meaning), [])

    def test_index_is_cached_and_only_changed_pieces_are_embedded_again(self):
        embed.refresh(self.pieces, embed_fn=fake)
        self.assertTrue(embed.index_file(embed.DEFAULT_MODEL).exists())
        seen = []
        counting = lambda texts, m, t: seen.extend(texts) or fake(texts, m, t)
        embed.refresh(self.pieces, embed_fn=counting)
        self.assertEqual(seen, [])
        store.update("training", "when changed", when="planning the training week of a team")
        embed.refresh(store.all_pieces(), embed_fn=counting)
        docs = [t for t in seen if "training" in t.lower() and t not in embed.PROBES]
        self.assertEqual(len(docs), 1)

    def test_pieces_not_indexed_yet_start_one_background_refresh(self):
        popen = mock.Mock()
        with mock.patch.object(embed.subprocess, "Popen", popen):
            embed.scores("revisá el acuerdo", self.pieces, embed_fn=fake)
            embed.scores("revisá el acuerdo", self.pieces, embed_fn=fake)
        self.assertEqual(popen.call_count, 1)                      # the lock keeps it to one
        self.assertIn("--refresh", popen.call_args[0][0])

    def test_didnt_apply_holds_for_meaning_loads(self):
        embed.refresh(self.pieces, embed_fn=fake)
        load.dismiss("contract", [])
        self.assertEqual(load.relevant("revisá este acuerdo de alquiler", self.pieces, meaning=self.meaning), [])


class EmbedCliTest(TempHome):
    def run_cli(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cli.main(list(argv))
        return code, out.getvalue()

    def test_on_off_and_status(self):
        seed()
        with mock.patch.object(embed, "ollama", side_effect=fake):
            code, text = self.run_cli("embed", "on")
        self.assertEqual(code, 0)
        self.assertIn("3 pieces indexed", text)
        self.assertTrue(embed.enabled())
        _, text = self.run_cli("embed")
        self.assertIn("on · embeddinggemma · 3/3", text)
        _, text = self.run_cli("embed", "off")
        self.assertFalse(embed.enabled())

    def test_on_with_ollama_down_says_words_only(self):
        with mock.patch.object(embed, "ollama", side_effect=OSError("connection refused")):
            _, text = self.run_cli("embed", "on", "--model", "nomic-embed-text")
        self.assertIn("loads by words only", text)
        self.assertEqual(embed.chosen_model(), "nomic-embed-text")
        self.assertEqual(json.loads((Path(self.home) / "config.json").read_text())["embed"]["on"], True)
