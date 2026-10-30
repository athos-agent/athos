#!/usr/bin/env node
// Compiles opencode/athos-sidebar.tsx to opencode/athos-sidebar.js: OpenCode loads plugins with Bun's default JSX
// transform, which Solid can't use, so the sidebar ships compiled (Solid's universal mode, @opentui/solid).
//   BABEL_DIR=<a folder with @babel/core, @babel/preset-typescript, babel-preset-solid> node opencode/build-sidebar.mjs
import { readFile, writeFile } from "node:fs/promises"
import { createRequire } from "node:module"
import { resolve } from "node:path"
import { fileURLToPath } from "node:url"

const here = fileURLToPath(new URL(".", import.meta.url))
const req = createRequire(resolve(process.env.BABEL_DIR || process.cwd(), "package.json"))
const { transformAsync } = req("@babel/core")
const source = resolve(here, "athos-sidebar.tsx")
const out = await transformAsync(await readFile(source, "utf8"), {
  filename: source, babelrc: false, configFile: false,
  presets: [
    [req.resolve("@babel/preset-typescript"), { isTSX: true, allExtensions: true }],
    [req.resolve("babel-preset-solid"), { generate: "universal", moduleName: "@opentui/solid" }],
  ],
})
await writeFile(resolve(here, "athos-sidebar.js"),
  "// Compiled from athos-sidebar.tsx by build-sidebar.mjs: edit the .tsx, not this file.\n" + out.code)
console.log("built opencode/athos-sidebar.js")
