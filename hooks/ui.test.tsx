import { expect, test } from 'claude-code/testing'

import { barText, savedText, statusText } from './ui'

const BAND = { plugin: 'athos', component: 'AbovePrompt', props: { hasSurvey: false } } as const

const STATUS = {
  pieces: 3,
  enabled: 3,
  loading: 'all',
  loaded: ['cut-a-release'],
  to_mark: 1,
  last: { task_id: 't1', result: 'unevaluated', pieces: ['cut-a-release'], saved: [], improved: ['cut-a-release'] },
  bars: null,
}

const CLAUDE = { platform: 'claude-code', label: 'Claude Code', uses: 5, evaluated: 5, ok: 4, success_rate: 0.8,
  mean_tokens: 12400, tokens_saved: 0.41 }
const CODEX = { platform: 'codex', label: 'Codex', uses: 0, evaluated: 0, ok: 0, success_rate: null,
  mean_tokens: null, tokens_saved: null }

test('the status line counts pieces, loaded and unmarked tasks', () => {
  expect(statusText(STATUS as never)).toBe('athos · 3 pieces · 1 loaded here · 1 to mark')
  expect(statusText({ ...STATUS, to_mark: 0 } as never)).toBe('athos · 3 pieces · 1 loaded here')
  expect(statusText(null)).toBe(undefined)
  expect(savedText(STATUS as never)).toBe('improved cut-a-release')
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
  expect((await ui.find({ type: 'Text', text: /improved cut-a-release/ }))?.text).toBeTruthy()
  await ui.press({ key: 'g' })
  expect(calls.some(a => a.join(' ') === 'mark g')).toBe(true)
  await ui.unmount()
})

test('a bar fills with the success rate and says the tokens saved', () => {
  const t = barText(CLAUDE as never)
  expect(t.filled.length).toBe(16)
  expect(t.empty.length).toBe(4)
  expect(t.words).toBe('4/5 good · 12.4k tokens · 41% fewer tokens')
  expect(barText(CODEX as never).words).toBe('not used yet')
  expect(barText({ ...CLAUDE, mean_tokens: 1133500 } as never).words).toBe('4/5 good · 1.1M tokens · 41% fewer tokens')
  expect(barText({ ...CLAUDE, evaluated: 0, ok: 0, success_rate: null, tokens_saved: -0.2 } as never).words)
    .toBe('not marked yet · 12.4k tokens · 20% more tokens')
})

test('the line under the prompt keeps its hint and adds one bar per agent', async ($, on) => {
  const status = { ...STATUS, bars: { piece: 'cut-a-release', title: 'Cut a release', baseline_tokens: 21000, agents: [CLAUDE, CODEX] } }
  on('session.root', () => ({ value: '/work' }))
  on('process.run', () => ({ value: { exitCode: 0, stdout: JSON.stringify(status), stderr: '' } }))
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('ui.status', () => ({ value: undefined }))
  await $.session.start({ cwd: '/work', surface: 'terminal', isInteractive: true })
  const ui = await $.ui.mount({ plugin: 'athos', component: 'PromptHint', surface: 'terminal',
    props: { hint: '? for shortcuts', isDraft: false, isWorking: false } })
  expect((await ui.find({ type: 'Text', text: /\? for shortcuts/ }))?.text).toBeTruthy()
  expect((await ui.find({ type: 'Text', text: /4\/5 good · 12.4k tokens · 41% fewer tokens/ }))?.text).toBeTruthy()
  expect((await ui.find({ type: 'Text', text: /not used yet/ }))?.text).toBeTruthy()
  await ui.unmount()
})
