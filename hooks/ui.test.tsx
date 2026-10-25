import { expect, test } from 'claude-code/testing'

import { savedText, statusText } from './ui'

const BAND = { plugin: 'athos', component: 'AbovePrompt', props: { hasSurvey: false } } as const

const STATUS = {
  pieces: 3,
  enabled: 3,
  loading: 'all',
  loaded: ['cut-a-release'],
  to_mark: 1,
  last: { task_id: 't1', result: 'unevaluated', pieces: ['cut-a-release'], saved: [], improved: ['cut-a-release'] },
}

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
