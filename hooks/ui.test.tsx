import { expect, test } from 'claude-code/testing'

import { announceText, barText, followingText, savedText, statusText, stepsText, trailRows, trailText, whyText, words }
  from './ui'

type Body = Extract<Parameters<typeof test>[1], (...a: never[]) => unknown>
type Harness = Parameters<Body>[0]
type On = Parameters<Body>[1]

// The store most tests start from: three pieces, one in use, and a last task that improved it and has no verdict yet.
const PIECE = 'cut-a-release'
const STATUS = {
  pieces: 3, enabled: 3, loading: 'all', loaded: [PIECE], to_mark: 1,
  last: { task_id: 't1', result: 'unevaluated', pieces: [PIECE], saved: [], improved: [PIECE] },
  bars: null, last_saved: null, following: [],
}

/** The engine around the hooks, as these tests fake it: the session's folder is /work, `athos` answers with
 * `cli(args)` (args are what follows `python3 bin/athos`), and the status line and toasts go nowhere. Any other
 * answer a test needs is registered beside it, before `start`. */
function fakeEngine(on: On, cli: (args: string[]) => string): void {
  on('session.root', () => ({ value: '/work' }))
  on('process.run', (_, e) => {
    const stdout = cli((e as unknown as { argv: string[] }).argv.slice(2))
    return { value: { exitCode: 0, stdout, stderr: '' } }
  })
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('ui.status', () => ({ value: undefined }))
  on('ui.toast', () => ({ value: undefined }))
}

/** `athos` answering every command with this status, as `athos status --json` would. */
const always = (status: object) => () => JSON.stringify(status)

/** An interactive terminal session in /work. */
const start = ($: Harness) => $.session.start({ cwd: '/work', surface: 'terminal', isInteractive: true })

/** The band above the prompt, in the terminal, with no survey of the engine's own on screen. */
const mountBand = ($: Harness) =>
  $.ui.mount({ plugin: 'athos', component: 'AbovePrompt', surface: 'terminal', props: { hasSurvey: false } })

const CLAUDE = { platform: 'claude-code', label: 'Claude Code', uses: 5, evaluated: 5, ok: 4, success_rate: 0.8,
  mean_request_chars: 80, prompt_saved: 0.85 }
const CODEX = { platform: 'codex', label: 'Codex', uses: 0, evaluated: 0, ok: 0, success_rate: null,
  mean_request_chars: null, prompt_saved: null }

test('the status line: the know-how, what is in use, and what still waits for a verdict', () => {
  expect(statusText(STATUS as never)).toBe('3 ways of working · 1 in use · 1 to mark')
  expect(statusText({ ...STATUS, to_mark: 0 } as never)).toBe('3 ways of working · 1 in use')
  expect([statusText(null), savedText(null)]).toEqual([undefined, ''])
})

test('what the last task changed reads as one line', () => {
  expect(savedText(STATUS as never)).toBe(`improved ${PIECE}`)
  expect(savedText({ ...STATUS, last: { ...STATUS.last, saved: ['draft-a-memo'] } } as never))
    .toBe(`saved draft-a-memo · improved ${PIECE}`)
})

test('a save is one line: what, which version, where it is ready', () => {
  const saved = { id: 'cut-a-release', title: 'Cut a release', version: 1, platforms: ['Claude Code', 'Codex', 'Muse Code'] }
  expect(announceText({ ...STATUS, last_saved: saved } as never))
    .toBe('saved «Cut a release» · ready in Claude Code · Codex · Muse Code')
  expect(announceText({ ...STATUS, last_saved: { ...saved, version: 3, platforms: ['Claude Code'] } } as never))
    .toBe('improved «Cut a release» → v3 · ready in Claude Code')
  expect(announceText(STATUS as never)).toBe(undefined)
  expect(announceText({ ...STATUS, last_saved: { ...saved, version: 2, platforms: ['Claude Code'], recheck: '2 past corrections to re-check' } } as never))
    .toBe('improved «Cut a release» → v2 · ready in Claude Code · 2 past corrections to re-check')
})

test('while a task runs, one line says which know-how it follows', () => {
  const f = { id: 'land', title: 'Land a change', version: 5, steps: 8, wiki: true, platforms: ['Claude Code', 'Codex'] }
  expect(followingText({ ...STATUS, following: [f] } as never))
    .toBe('athos · following «Land a change» v5 · 8 steps · ready in Claude Code · Codex')
  expect(followingText({ ...STATUS, following: [{ ...f, wiki: false }, f] } as never))
    .toBe('athos · following «Land a change» v5 · numbered steps (+1 more) · ready in Claude Code · Codex')
  expect(followingText(STATUS as never)).toBe(undefined)
})

test('a task with no verdict is marked with one key from the band', async ($, on) => {
  // Before the mark the status still asks; once `athos mark` ran, the last task reads ok.
  const ran: string[] = []
  const afterMark = { ...STATUS, to_mark: 0, last: { ...STATUS.last, result: 'ok' } }
  fakeEngine(on, args => {
    ran.push(args.join(' '))
    if (args[0] === 'mark') return 'task t1 marked ok'
    return JSON.stringify(ran.some(c => c.startsWith('mark ')) ? afterMark : STATUS)
  })
  await start($)
  const ui = await mountBand($)
  expect((await ui.find({ type: 'Text', text: /How did this task go/ }))?.text).toBeTruthy()
  await ui.press({ key: 'g' })
  expect(ran).toContain('mark g')
  await ui.unmount()
})

test('a task worth keeping offers [Save], which sends the save, not a question to the model', async ($, on) => {
  const status = { ...STATUS, offer: { task_id: STATUS.last.task_id, reason: 'work' },
                   save_prompt: 'Athos · save: keep it' }
  const sent: string[] = []
  fakeEngine(on, always(status))
  on('prompt.submit', (_, e) => { const text = (e as unknown as { text: string }).text; sent.push(text); return { text } })
  await start($)
  const ui = await mountBand($)
  expect((await ui.find({ type: 'Text', text: /can become a way of working/ }))?.text).toBeTruthy()
  await ui.press({ key: 's' })
  expect(sent).toEqual(['Athos · save: keep it'])
  await ui.unmount()
})

test('the band says which know-how the task used, why, how it has done, and takes a "didn\'t apply"', async ($, on) => {
  const status = { ...STATUS, loads: [{ id: 'cut-a-release', title: 'Cut a release', why: ['release', 'version'],
                                        record: { uses: 5, ok: 4, marked: 4, agents: ['Claude Code', 'Codex'] } }] }
  const ran: string[] = []
  fakeEngine(on, args => {
    ran.push(args.join(' '))
    return args[0] === 'dismiss' ? 'ok' : JSON.stringify(status)
  })
  await start($)
  const ui = await mountBand($)
  const line = await ui.find({ type: 'Text', text: /used «Cut a release»/ })
  expect(line?.text).toContain('4/4 good in Claude Code, Codex')
  expect(line?.text).toContain('matched: release, version')
  await ui.press({ key: 'x' })
  expect(ran).toContain('dismiss cut-a-release')
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
  fakeEngine(on, always(status))
  await start($)
  const ui = await $.ui.mount({ plugin: 'athos', component: 'PromptHint', surface: 'terminal',
    props: { hint: '? for shortcuts', isDraft: false, isWorking: false } })
  expect((await ui.find({ type: 'Text', text: /\? for shortcuts/ }))?.text).toBeTruthy()
  expect((await ui.find({ type: 'Text', text: /4\/5 good · 85% shorter prompt/ }))?.text).toBeTruthy()
  expect((await ui.find({ type: 'Text', text: /not used yet/ }))?.text).toBeTruthy()
  await ui.unmount()
})

test('in Spanish, the person reads plain Spanish', () => {
  const es = { ...STATUS, lang: 'es' }
  expect(statusText(es as never)).toBe('3 formas de trabajar · 1 en uso · 1 por marcar')
  const f = { id: 'x', title: 'Revisar un contrato', version: 2, steps: 4, wiki: true, platforms: ['Claude Code'] }
  expect(followingText({ ...es, following: [f] } as never))
    .toBe('athos · siguiendo «Revisar un contrato» v2 · 4 pasos · lista en Claude Code')
  expect(announceText({ ...es, last_saved: { id: 'x', title: 'Revisar un contrato', version: 1, platforms: ['Claude Code'] } } as never))
    .toBe('guardé «Revisar un contrato» · lista en Claude Code')
  expect(barText(CLAUDE as never, es as never).words).toBe('4/5 bien · pedido 85% más corto')
})

test('while a task runs, the steps of the know-how it follows are listed in order', () => {
  const f = { id: 'review', title: 'Review a contract', version: 2, steps: 7, wiki: true,
    step_names: ['client_data', 'summary', 'clauses', 'table', 'decision', 'missing'], platforms: ['Claude Code'] }
  expect(stepsText({ ...STATUS, following: [f] } as never))
    .toBe('#client_data → #summary → #clauses → #table → #decision → #missing → …')
  expect(stepsText({ ...STATUS, following: [{ ...f, steps: 6 }] } as never)).toContain('#missing')
  expect(stepsText({ ...STATUS, following: [{ ...f, step_names: [] }] } as never)).toBe(undefined)
  expect(stepsText(STATUS as never)).toBe(undefined)
})

test('the "used" row keeps to one line: at most three matched words', () => {
  const w = words(STATUS as never)
  expect(whyText({ id: 'x', title: 'Review a contract', why: ['against', 'checklist', 'lease', 'review'] }, w))
    .toBe('used «Review a contract» · first time · matched: against, checklist, lease…')
})


const TRAIL = {
  task_id: 't2',
  pieces: [{ id: 'cut-a-release', title: 'Cut a release', version: 2, how: 'loaded', why: ['release'],
             steps: [{ id: 'bump', do: 'bump the version', state: 'done' }, { id: 'tag', do: 'tag and push', state: 'now' },
                     { id: 'notes', do: 'write the notes', state: 'ahead' }] }],
  beside: [{ kind: 'agent', name: 'Explore', why: 'find the changelog' }, { kind: 'skill', name: 'pdf' }],
  new: ['announce it'],
  busy: true,
}

test('the trail reads like thinking: the piece, its steps done, now and ahead, the new ones, and what ran beside', () => {
  const rows = trailRows(TRAIL as never, words({ lang: 'es' } as never))
  expect(rows.map(r => `${r.mark}|${r.text}`)).toEqual([
    '|«Cut a release» v2 · 1/3 pasos · coincidió: release',
    '✓|bump',
    '▶|tag — tag and push',
    '○|notes',
    '+|nuevo: announce it',
    '|Subagentes: Explore (find the changelog)',
    '|Skills: pdf',
  ])
  expect(trailText(TRAIL as never, words(null))).toBe('«Cut a release» · 1/3 steps')
  expect(trailText({ ...TRAIL, pieces: [] } as never, words(null))).toBe('new: announce it')
  expect(trailRows({ ...TRAIL, pieces: [] } as never, words(null))[0].text).toMatch(/No know-how for this task yet/)
})

test('the pane shows the trail and [Adjust step] puts the step in the prompt for the person to finish', async ($, on) => {
  const status = { ...STATUS, last: null, trail: TRAIL }
  const filled: string[] = []
  fakeEngine(on, always(status))
  on('prompt.fill', (_, e) => { filled.push((e as unknown as { text: string }).text); return { isFilled: true } })
  await start($)
  const ui = await $.ui.mount({ plugin: 'athos', component: 'Pane', requestId: 'athos-trail', surface: 'terminal',
                                props: { title: 'athos · Trail', isFocused: true, bodyColumns: 80, placement: 'dock' } } as never)
  expect((await ui.find({ type: 'Text', text: /tag — tag and push/ }))?.text).toBeTruthy()
  await ui.press({ key: 'a' })
  expect(filled).toEqual(['Athos · adjust cut-a-release#tag: '])
  await ui.unmount()
})

test('before the first request the band greets the person and says what is ready', async ($, on) => {
  const status = { ...STATUS, last: null, greeting: 'Buen día, Ana', lang: 'es' }
  fakeEngine(on, always(status))
  await start($)
  const ui = await mountBand($)
  expect((await ui.find({ type: 'Text', text: /Buen día, Ana · 3 formas de trabajar listas/ }))?.text).toBeTruthy()
  await ui.unmount()
})

test('when the pane is not on screen, the band says where the task is and opens it with one press', async ($, on) => {
  const status = { ...STATUS, last: null, trail: TRAIL }
  const opened: string[] = []
  fakeEngine(on, always(status))
  on('ui.panes', () => ({ value: [] }))
  on('ui.open', (_, e) => { opened.push((e as unknown as { id: string }).id); return { value: { isPlaced: true } } })
  await start($)
  const ui = await mountBand($)
  expect((await ui.find({ type: 'Text', text: /«Cut a release» · 1\/3 steps/ }))?.text).toBeTruthy()
  await ui.press({ key: 't' })
  expect(opened).toEqual(['athos-trail'])
  await ui.unmount()
})

test('a step reads as its sentence, not its id', () => {
  const t = { ...TRAIL, pieces: [{ ...TRAIL.pieces[0], steps: [
    { id: 'key', label: 'Deciding where to keep the key', do: 'keep it in ~/.athos/.env', state: 'now' }] }] }
  expect(trailRows(t as never, words(null))[1].text).toBe('Deciding where to keep the key — keep it in ~/.athos/.env')
})
