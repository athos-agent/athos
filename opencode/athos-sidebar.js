// Compiled from athos-sidebar.tsx by build-sidebar.mjs: edit the .tsx, not this file.
import { effect as _$effect } from "@opentui/solid";
import { createTextNode as _$createTextNode } from "@opentui/solid";
import { insertNode as _$insertNode } from "@opentui/solid";
import { setProp as _$setProp } from "@opentui/solid";
import { insert as _$insert } from "@opentui/solid";
import { createElement as _$createElement } from "@opentui/solid";
import { createComponent as _$createComponent } from "@opentui/solid";
// Athos's trail in OpenCode's own sidebar: which of the person's ways of working the task follows, in a sentence,
// then its steps ticked as the agent reports them (✓ done, ▶ now, ○ ahead), and whether a connector guards the data.
// The same data as Claude Desktop's panel and `athos watch --trail`, read from `athos status --json`.
// Its two buttons are commands in OpenCode's palette (ctrl+p): "Athos: change this step" and "Athos: save as a way of
// working". Each sends the same message as Desktop's panel to the session, so nobody has to type a command.
//
// OpenCode loads plugins without Solid's JSX transform, so this file is compiled once to athos-sidebar.js
// (`node opencode/build-sidebar.mjs`) and `athos opencode install` installs the compiled file.
import { createSignal } from "solid-js";
import { execFile } from "node:child_process";
const ATHOS = process.env.ATHOS_BIN || "__ATHOS__";
const POLL_MS = 1500;
function read(cwd) {
  return new Promise(resolve => {
    execFile(ATHOS, ["status", "--json"], {
      cwd,
      timeout: 10000
    }, (err, out) => {
      if (err) return resolve({});
      try {
        resolve(JSON.parse(String(out).trim().split("\n").pop() || "{}"));
      } catch {
        resolve({});
      }
    });
  });
}
const MARK = {
  done: "✓",
  now: "▶",
  ahead: "○"
};

// The step a change is about: the one in progress, else the last one done, else the first.
function current(piece) {
  const done = piece.steps.filter(x => x.state === "done");
  return piece.steps.find(x => x.state === "now") || done[done.length - 1] || piece.steps[0];
}
export const tui = async api => {
  const cwd = process.cwd();
  const [status, setStatus] = createSignal(await read(cwd));
  const timer = setInterval(async () => setStatus(await read(cwd)), POLL_MS);
  api.lifecycle.onDispose(() => clearInterval(timer));

  // The message goes to the session as the person's own, through the prompt, as when they type it.
  const say = async text => {
    await api.client.tui.appendPrompt({
      text
    });
    await api.client.tui.submitPrompt();
  };
  const change = () => {
    const s = status();
    const es = s.lang === "es";
    const piece = s.trail?.pieces?.[0];
    const step = piece && current(piece);
    if (!piece || !step) return;
    api.ui.dialog.replace(() => _$createComponent(api.ui.DialogPrompt, {
      title: es ? "¿Cómo tiene que cambiar este paso?" : "How should this step change?",
      description: () => (() => {
        var _el$ = _$createElement("text");
        _$insert(_el$, () => step.label);
        return _el$;
      })(),
      placeholder: es ? "por ejemplo: además, comparar con el índice ICL" : "e.g. also compare against the CPI",
      onConfirm: value => {
        api.ui.dialog.clear();
        if (value.trim()) say(`${es ? "Athos · ajustar" : "Athos · adjust"} ${piece.id}#${step.id}: ${value.trim()}`);
      },
      onCancel: () => api.ui.dialog.clear()
    }));
  };
  const save = () => {
    const s = status();
    say(s.save_prompt || "Athos · save: keep this task as a way of working");
  };
  // Legacy in OpenCode 1.19, still how a v1 plugin adds palette entries.
  if (api.command?.register) {
    const off = api.command.register(() => {
      const s = status();
      const es = s.lang === "es";
      const piece = s.trail?.pieces?.[0];
      return [{
        title: es ? "Athos: cambiar este paso" : "Athos: change this step",
        value: "athos.change",
        category: "Athos",
        enabled: !!piece,
        onSelect: change
      }, {
        title: es ? "Athos: guardar como forma de trabajar" : "Athos: save as a way of working",
        value: "athos.save",
        category: "Athos",
        onSelect: save
      }];
    });
    api.lifecycle.onDispose(off);
  }
  api.slots.register({
    slots: {
      sidebar_content: ctx => {
        const t = ctx.theme.current;
        const s = status();
        const es = s.lang === "es";
        const piece = s.trail?.pieces?.[0];
        if (!piece) return null;
        const steps = piece.steps;
        const i = steps.findIndex(x => x.state === "now");
        const done = steps.filter(x => x.state === "done").length;
        const where = i >= 0 ? es ? `Paso ${i + 1} de ${steps.length}` : `Step ${i + 1} of ${steps.length}` : done === steps.length ? es ? `Apliqué los ${done} pasos` : `All ${done} steps applied` : es ? `${steps.length} pasos` : `${steps.length} steps`;
        const guard = (s.trail?.connectors || []).map(c => c.active ? es ? `🔒 datos por ${c.name}` : `🔒 data through ${c.name}` : es ? `⚠ ${c.name} no está activo` : `⚠ ${c.name} is not running`);
        return (() => {
          var _el$2 = _$createElement("box"),
            _el$3 = _$createElement("text"),
            _el$5 = _$createElement("text"),
            _el$6 = _$createElement("text");
          _$insertNode(_el$2, _el$3);
          _$insertNode(_el$2, _el$5);
          _$insertNode(_el$2, _el$6);
          _$setProp(_el$2, "flexDirection", "column");
          _$setProp(_el$2, "paddingTop", 1);
          _$insertNode(_el$3, _$createTextNode(`Athos`));
          _$insert(_el$5, () => (es ? "Sigo «" : "Following «") + piece.title + "»");
          _$insert(_el$6, where);
          _$insert(_el$2, () => guard.map(g => (() => {
            var _el$7 = _$createElement("text");
            _$insert(_el$7, g);
            _$effect(_$p => _$setProp(_el$7, "fg", t.textMuted, _$p));
            return _el$7;
          })()), null);
          _$insert(_el$2, () => steps.map(x => (() => {
            var _el$8 = _$createElement("text");
            _$insert(_el$8, () => MARK[x.state] + " " + (x.label.length > 34 ? x.label.slice(0, 33) + "…" : x.label));
            _$effect(_$p => _$setProp(_el$8, "fg", x.state === "now" ? t.accent : x.state === "done" ? t.success : t.textMuted, _$p));
            return _el$8;
          })()), null);
          _$insert(_el$2, () => (s.trail?.new || []).map(n => (() => {
            var _el$9 = _$createElement("text");
            _$insert(_el$9, "+ " + n);
            _$effect(_$p => _$setProp(_el$9, "fg", t.warning, _$p));
            return _el$9;
          })()), null);
          _$effect(_p$ => {
            var _v$ = t.accent,
              _v$2 = t.textMuted,
              _v$3 = t.textMuted;
            _v$ !== _p$.e && (_p$.e = _$setProp(_el$3, "fg", _v$, _p$.e));
            _v$2 !== _p$.t && (_p$.t = _$setProp(_el$5, "fg", _v$2, _p$.t));
            _v$3 !== _p$.a && (_p$.a = _$setProp(_el$6, "fg", _v$3, _p$.a));
            return _p$;
          }, {
            e: undefined,
            t: undefined,
            a: undefined
          });
          return _el$2;
        })();
      }
    }
  });
};
export default {
  id: "athos-sidebar",
  tui
};