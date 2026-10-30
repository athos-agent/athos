// Compiled from athos-sidebar.tsx by build-sidebar.mjs: edit the .tsx, not this file.
import { effect as _$effect } from "@opentui/solid";
import { insert as _$insert } from "@opentui/solid";
import { createTextNode as _$createTextNode } from "@opentui/solid";
import { insertNode as _$insertNode } from "@opentui/solid";
import { setProp as _$setProp } from "@opentui/solid";
import { createElement as _$createElement } from "@opentui/solid";
// Athos's trail in OpenCode's own sidebar: which of the person's ways of working the task follows, in a sentence,
// then its steps ticked as the agent reports them (✓ done, ▶ now, ○ ahead), and whether a connector guards the data.
// The same data as Claude Desktop's panel and `athos watch --trail`, read from `athos status --json`.
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
export const tui = async api => {
  const cwd = process.cwd();
  const [status, setStatus] = createSignal(await read(cwd));
  const timer = setInterval(async () => setStatus(await read(cwd)), POLL_MS);
  api.lifecycle.onDispose(() => clearInterval(timer));
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
          var _el$ = _$createElement("box"),
            _el$2 = _$createElement("text"),
            _el$4 = _$createElement("text"),
            _el$5 = _$createElement("text");
          _$insertNode(_el$, _el$2);
          _$insertNode(_el$, _el$4);
          _$insertNode(_el$, _el$5);
          _$setProp(_el$, "flexDirection", "column");
          _$setProp(_el$, "paddingTop", 1);
          _$insertNode(_el$2, _$createTextNode(`Athos`));
          _$insert(_el$4, () => (es ? "Sigo «" : "Following «") + piece.title + "»");
          _$insert(_el$5, where);
          _$insert(_el$, () => guard.map(g => (() => {
            var _el$6 = _$createElement("text");
            _$insert(_el$6, g);
            _$effect(_$p => _$setProp(_el$6, "fg", t.textMuted, _$p));
            return _el$6;
          })()), null);
          _$insert(_el$, () => steps.map(x => (() => {
            var _el$7 = _$createElement("text");
            _$insert(_el$7, () => MARK[x.state] + " " + (x.label.length > 34 ? x.label.slice(0, 33) + "…" : x.label));
            _$effect(_$p => _$setProp(_el$7, "fg", x.state === "now" ? t.accent : x.state === "done" ? t.success : t.textMuted, _$p));
            return _el$7;
          })()), null);
          _$insert(_el$, () => (s.trail?.new || []).map(n => (() => {
            var _el$8 = _$createElement("text");
            _$insert(_el$8, "+ " + n);
            _$effect(_$p => _$setProp(_el$8, "fg", t.warning, _$p));
            return _el$8;
          })()), null);
          _$effect(_p$ => {
            var _v$ = t.accent,
              _v$2 = t.textMuted,
              _v$3 = t.textMuted;
            _v$ !== _p$.e && (_p$.e = _$setProp(_el$2, "fg", _v$, _p$.e));
            _v$2 !== _p$.t && (_p$.t = _$setProp(_el$4, "fg", _v$2, _p$.t));
            _v$3 !== _p$.a && (_p$.a = _$setProp(_el$5, "fg", _v$3, _p$.a));
            return _p$;
          }, {
            e: undefined,
            t: undefined,
            a: undefined
          });
          return _el$;
        })();
      }
    }
  });
};
export default {
  id: "athos-sidebar",
  tui
};