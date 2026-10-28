import { expect, test } from 'claude-code/testing'

import { announceText, barText, followingText, savedText, statusText } from './ui'

const BAND = { plugin: 'athos', component: 'AbovePrompt', props: { hasSurvey: false } } as const

const STATUS = {
  pieces: 3,
  enabled: 3,
  loading: 'all',
  loaded: ['cut-a-release'],
  to_mark: 1,
  last: { task_id: 't1', result: 'unevaluated', pieces: ['cut-a-release'], saved: [], improved: ['cut-a-release'] },
  bars: null,
  last_saved: null,
  following: [],
}

const CLAUDE = { platform: 'claude-code', label: 'Claude Code', uses: 5, evaluated: 5, ok: 4, success_rate: 0.8,
  mean_request_chars: 80, prompt_saved: 0.85 }
const CODEX = { platform: 'codex', label: 'Codex', uses: 0, evaluated: 0, ok: 0, success_rate: null,
  mean_request_chars: null, prompt_saved: null }

test('the status line counts pieces, loaded and unmarked tasks', () => {
  expect(statusText(STATUS as never)).toBe('athos · 3 ways of working · 1 in use · 1 to mark')
  expect(statusText({ ...STATUS, to_mark: 0 } as never)).toBe('athos · 3 ways of working · 1 in use')
  expect(statusText(null)).toBe(undefined)
  expect(savedText(STATUS as never)).toBe('improved cut-a-release')
})

test('a save is one line: what, which version, where it is ready', () => {
  const saved = { id: 'cut-a-release', title: 'Cut a release', version: 1, platforms: ['Claude Code', 'Codex', 'Muse Code'] }
  expect(announceText({ ...STATUS, last_saved: saved } as never))
    .toBe('athos · saved «Cut a release» · ready in Claude Code · Codex · Muse Code')
  expect(announceText({ ...STATUS, last_saved: { ...saved, version: 3, platforms: ['Claude Code'] } } as never))
    .toBe('athos · improved «Cut a release» → v3 · ready in Claude Code')
  expect(announceText(STATUS as never)).toBe(undefined)
})

test('while a task runs, one line says which know-how it follows', () => {
  const f = { id: 'land', title: 'Land a change', version: 5, steps: 8, wiki: true, platforms: ['Claude Code', 'Codex'] }
  expect(followingText({ ...STATUS, following: [f] } as never))
    .toBe('athos · following «Land a change» v5 · 8 steps · ready in Claude Code · Codex')
  expect(followingText({ ...STATUS, following: [{ ...f, wiki: false }, f] } as never))
    .toBe('athos · following «Land a change» v5 · numbered steps (+1 more) · ready in Claude Code · Codex')
  expect(followingText(STATUS as never)).toBe(undefined)
})

test('an unmarked task gets one-key marking above the prompt', async ($, on) => {
  const calls: string[][] = []
  on('session.root', () => ({ value: '/work' }))
  on('process.run', (_, e) => {
    const argv = (e as unknown as { argv: string[] }).argv
    calls.push(argv.slice(2))
    const marked = calls.some(a => a[0] === 'mark')
    const out = argv[2] === 'mark' ? 'task t1 marked ok'
      : JSON.stringify(marked ? { ...STATUS, to_mark: 0, last: { ...STATUS.last, result: 'ok' } } : STATUS)
    return { value: { exitCode: 0, stdout: out, stderr: '' } }
  })
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('ui.status', () => ({ value: undefined }))
  on('ui.toast', () => ({ value: undefined }))

  await $.session.start({ cwd: '/work', surface: 'terminal', isInteractive: true })
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect((await ui.find({ type: 'Text', text: /How did this task go/ }))?.text).toBeTruthy()
  await ui.press({ key: 'g' })
  expect(calls.some(a => a.join(' ') === 'mark g')).toBe(true)
  await ui.unmount()
})

test('a bar fills with the success rate and says how much shorter the prompt is', () => {
  const t = barText(CLAUDE as never)
  expect(t.filled.length).toBe(16)
  expect(t.empty.length).toBe(4)
  expect(t.words).toBe('4/5 good · 85% shorter prompt')
  expect(barText(CODEX as never).words).toBe('not used yet')
  expect(barText({ ...CLAUDE, evaluated: 0, ok: 0, success_rate: null, prompt_saved: -0.2 } as never).words)
    .toBe('not marked yet · 20% longer prompt')
})

test('the line under the prompt keeps its hint and adds one bar per agent', async ($, on) => {
  const status = { ...STATUS, bars: { piece: 'cut-a-release', title: 'Cut a release', baseline_request_chars: 520, agents: [CLAUDE, CODEX] } }
  on('session.root', () => ({ value: '/work' }))
  on('process.run', () => ({ value: { exitCode: 0, stdout: JSON.stringify(status), stderr: '' } }))
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('ui.status', () => ({ value: undefined }))
  await $.session.start({ cwd: '/work', surface: 'terminal', isInteractive: true })
  const ui = await $.ui.mount({ plugin: 'athos', component: 'PromptHint', surface: 'terminal',
    props: { hint: '? for shortcuts', isDraft: false, isWorking: false } })
  expect((await ui.find({ type: 'Text', text: /\? for shortcuts/ }))?.text).toBeTruthy()
  expect((await ui.find({ type: 'Text', text: /4\/5 good · 85% shorter prompt/ }))?.text).toBeTruthy()
  expect((await ui.find({ type: 'Text', text: /not used yet/ }))?.text).toBeTruthy()
  await ui.unmount()
})

test('in Spanish, the person reads plain Spanish', () => {
  const es = { ...STATUS, lang: 'es' }
  expect(statusText(es as never)).toBe('athos · 3 formas de trabajar · 1 en uso · 1 por marcar')
  const f = { id: 'x', title: 'Revisar un contrato', version: 2, steps: 4, wiki: true, platforms: ['Claude Code'] }
  expect(followingText({ ...es, following: [f] } as never))
    .toBe('athos · siguiendo «Revisar un contrato» v2 · 4 pasos · lista en Claude Code')
  expect(announceText({ ...es, last_saved: { id: 'x', title: 'Revisar un contrato', version: 1, platforms: ['Claude Code'] } } as never))
    .toBe('athos · guardé «Revisar un contrato» · lista en Claude Code')
  expect(barText(CLAUDE as never, es as never).words).toBe('4/5 bien · pedido 85% más corto')
})
