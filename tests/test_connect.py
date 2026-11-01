import json
import os
import subprocess
from pathlib import Path
from unittest import mock

from athos import connect, mcp, start, store
from tests.helpers import TempHome


class FakeAgents(TempHome):
    """A fake home and a PATH with fake `codex`, `opencode` and `muse` commands: no real agent is ever run or touched."""

    def setUp(self):
        super().setUp()
        self._env = {k: os.environ.get(k) for k in ("HOME", "PATH")}
        self.fake_home = Path(self.home) / "home"
        self.bin = Path(self.home) / "fake-bin"
        self.fake_home.mkdir()
        self.bin.mkdir()
        os.environ["HOME"] = str(self.fake_home)
        os.environ["PATH"] = str(self.bin)

    def tearDown(self):
        for k, v in self._env.items():
            os.environ[k] = v
        super().tearDown()

    def command(self, name, body="#!/bin/sh\nexit 0\n"):
        f = self.bin / name
        f.write_text(body)
        f.chmod(0o755)
        return f

    def athos_root(self, where: Path, version: str) -> Path:
        (where / "bin").mkdir(parents=True)
        (where / "bin" / "athos").write_text("#!/usr/bin/env python3\n")
        (where / ".claude-plugin").mkdir()
        (where / ".claude-plugin" / "plugin.json").write_text(json.dumps({"version": version}))
        return where


class ConnectTest(FakeAgents):
    def test_finds_only_the_agents_that_are_here(self):
        self.assertEqual([a["found"] for a in connect.agents()], [False, False, False])
        self.command("codex")
        (Path(os.environ["XDG_CONFIG_HOME"]) / "opencode").mkdir(parents=True)     # a config folder counts too
        got = {a["id"]: a for a in connect.agents()}
        self.assertTrue(got["codex"]["found"] and got["opencode"]["found"])
        self.assertFalse(got["muse"]["found"] or got["codex"]["connected"])

    def test_connect_codex_and_opencode_like_their_install_commands(self):
        self.command("codex")
        line = connect.connect("codex", "es")
        self.assertIn("/hooks", line)
        hooks = (Path(os.environ["CODEX_HOME"]) / "hooks.json").read_text()
        self.assertIn(str(Path(self.home) / "bin" / "athos"), hooks)                    # the shim
        self.assertTrue(connect.connected("codex"))
        self.assertIn("Restart OpenCode", connect.connect("opencode"))
        js = Path(os.environ["XDG_CONFIG_HOME"]) / "opencode" / "plugins" / "athos.js"
        self.assertIn(str(Path(self.home) / "bin" / "athos"), js.read_text())
        self.assertTrue(connect.connected("opencode"))

    def test_connect_muse_runs_its_three_plugin_commands(self):
        self.assertIn("isn't on", connect.connect("muse", run=lambda *a, **k: self.fail("ran without muse")))
        muse = self.command("muse")
        ran = []

        def run(cmd, **kw):
            ran.append(cmd)
            self.assertIn("timeout", kw)
            if cmd[2] == "marketplace":
                return subprocess.CompletedProcess(cmd, 1, "", "marketplace athos already exists")
            return subprocess.CompletedProcess(cmd, 0, "ok", "")
        self.assertIn("Restart Muse Code", connect.connect("muse", run=run))
        self.assertEqual(ran, [[str(muse), *s] for s in connect.MUSE_STEPS])

        def fails(cmd, **kw):
            return subprocess.CompletedProcess(cmd, 0 if cmd[2] == "marketplace" else 2, "", "not approved")
        self.assertIn("plugins install athos@athos", connect.connect("muse", run=fails))
        with self.assertRaises(ValueError):
            connect.connect("other")

    def test_versions_and_who_is_behind(self):
        cache = self.fake_home / ".claude" / "plugins" / "cache" / "athos" / "athos"
        self.athos_root(cache / "0.1.98", "0.1.98")
        self.athos_root(cache / "0.1.99", "0.1.99")
        ext = self.fake_home / "Library" / "Application Support" / "Claude" / "Claude Extensions" / "local.mcpb.x.athos"
        ext.mkdir(parents=True)
        (ext / "manifest.json").write_text(json.dumps({"name": "athos", "version": "0.1.74"}))
        muse_data = Path(os.environ["XDG_DATA_HOME"]) / "muse" / "plugins"
        muse_data.mkdir(parents=True)
        (muse_data / "installed.json").write_text(json.dumps({"plugins": {"athos": {"version": "0.1.75"}}}))
        connect.connect("opencode")                                     # through the shim: the newest plugin
        app = self.athos_root(Path(self.home) / "app", "0.1.60")         # install.sh's launcher on PATH
        self.command("athos", f'#!/bin/sh\nexec "/usr/bin/python3" "{app}/bin/athos" "$@"\n')
        v = connect.versions(run=lambda *a, **k: self.fail("asked muse"))
        self.assertEqual(v["agents"], {"claude-code": "0.1.99", "claude-desktop": "0.1.74", "opencode": "0.1.99",
                                       "muse": "0.1.75", "path": "0.1.60"})
        self.assertEqual(v["newest"], "0.1.99")
        self.assertEqual(sorted(v["behind"]), ["claude-desktop", "muse", "path"])
        line = connect.behind_line(v, "es")
        self.assertIn("Atrasados", line)
        self.assertIn("Muse Code 0.1.75", line)
        self.assertIn("athos.mcpb", line)
        self.assertIn("Muse Code", connect.report(v))

    def test_muse_version_from_its_command_when_its_record_is_missing(self):
        self.command("muse")
        out = "NAME   VERSION\nathos  0.1.70  enabled\n"
        v = connect.versions(run=lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, out, ""))
        self.assertEqual(v["agents"].get("muse"), "0.1.70")
        self.assertNotIn("muse", connect.versions(ask_muse=False)["agents"])


class PanelFirstUseTest(FakeAgents):
    """Claude Desktop's panel: professions on a first use, the other agents with [Connect]."""

    def test_the_panel_offers_professions_and_agents(self):
        self.command("codex")
        mcp._SETUP.clear()
        p = mcp.panel()
        self.assertEqual(p["pieces"], 0)
        self.assertEqual([x[0] for x in p["setup"]["professions"]],
                         ["law", "finance", "journalism", "science", "ops", "other"])
        self.assertEqual([a["id"] for a in p["setup"]["agents"]], ["codex"])

    def test_a_click_on_a_profession_installs_its_starters(self):
        r = json.loads(mcp.call("athos_start", {"profile": "finance", "lang": "es"}))
        self.assertEqual(sorted(r["added"]), ["analizar-una-inversion-con-las-reglas-de-mi-comite",
                                              "revisar-el-tratamiento-fiscal-entre-paises"])
        self.assertIn("Agregué 2 formas de trabajar", r["line"])
        self.assertEqual(start.config()["profile"], "finance")
        self.assertEqual(len(store.all_pieces()), 2)
        again = json.loads(mcp.call("athos_start", {"profile": "finance", "lang": "es"}))
        self.assertIn("Ya las tenías", again["line"])
        self.assertIn("Athos learns", json.loads(mcp.call("athos_start", {"profile": "other", "lang": "en"}))["line"])
        with self.assertRaises(ValueError):
            mcp.call("athos_start", {"profile": "medicine", "lang": "en"})

    def test_a_click_on_connect(self):
        self.command("codex")
        self.assertIn("/hooks", mcp.call("athos_connect", {"agent": "codex"}))
        self.assertTrue(next(a for a in mcp.panel()["setup"]["agents"] if a["id"] == "codex")["connected"])

    def test_the_bar_is_the_newest_release_not_this_copy(self):
        cache = self.fake_home / ".claude" / "plugins" / "cache" / "athos" / "athos"
        self.athos_root(cache / "0.1.80", "0.1.80")
        dev = self.athos_root(Path(self.home) / "checkout", "9.9.9")             # a checkout ahead of the release
        with mock.patch.object(connect, "ROOT", dev):
            v = connect.versions(run=lambda *a, **k: self.fail("asked muse"))
            self.assertEqual((v["this"], v["newest"], v["behind"]), ("9.9.9", "0.1.80", []))
            mk = self.fake_home / ".claude" / "plugins" / "marketplaces" / "athos" / ".claude-plugin"
            mk.mkdir(parents=True)
            (mk / "marketplace.json").write_text(json.dumps({"plugins": [{"name": "athos", "version": "0.1.81"}]}))
            v = connect.versions(run=lambda *a, **k: self.fail("asked muse"))
            self.assertEqual((v["newest"], v["behind"]), ("0.1.81", ["claude-code"]))    # released, not updated
