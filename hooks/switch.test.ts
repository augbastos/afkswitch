import { expect, mock, test } from 'claude-code/testing'
import type { Engine } from 'claude-code/testing'
import type { On } from 'claude-code'

const PROPS = {
  hasSurvey: false, isWorking: false, maxRows: 6, bodyColumns: 80,
  scroll: { offset: 0, bodyRows: 6 }, view: {},
}
const BASE = { type: 'Text' as const, props: {}, children: ['existing band'] }
const ONBOARDING = [
  "AFKSwitch is ready — [ AFK □■ ] means you're here.",
  "Click it when you leave; click again when you're back.",
  'Use /afk [note] or /back [note] for optional context.',
]
const state = (status: string, version = 2) => JSON.stringify({
  version, status, since: '2026-09-30T12:00:00Z', context: null,
  ...(version === 1 ? {} : { generation: 1 }),
})
type Disk = { raw: string | null | undefined; reads: string[]; existenceError?: boolean }

const setup = (on: On, raw: string | null | undefined, variables = { AFKSWITCH_STATE_DIR: '/test-state' }): Disk => {
  const disk: Disk = { raw, reads: [] }
  mock.env(on, variables)
  on('fs.exists', () => {
    if (disk.existenceError) throw new Error('synthetic existence failure')
    return { value: disk.raw !== undefined }
  })
  on('fs.read', ($, e) => {
    disk.reads.push(e.path)
    if (disk.raw == null) return { deny: 'synthetic unreadable file' }
    return { value: disk.raw }
  })
  on('fs.write', () => { throw new Error('the UI must never write') })
  on('ui.render', () => BASE)
  on('session.start', ($, e) => ({ cwd: e.cwd }))
  on('prompt.submit', ($, e) => ({ text: e.text }))
  on('turn.complete', ($, e) => ({ text: e.answer }))
  return disk
}

const mount = ($: Engine, surface: 'terminal' | 'desktop' = 'terminal') =>
  $.ui.mount({ plugin: 'afkswitch', surface, component: 'AbovePrompt', props: PROPS })

for (const surface of ['terminal', 'desktop'] as const) {
  for (const seen of [undefined, 1, 2, '1', 0]) {
    test(`${surface}: onboarding version ${seen}`, async ($, on) => {
      setup(on, state('available'))
      const saved: unknown[] = []
      on('store.get', () => ({ value: seen }))
      on('store.set', ($, e) => { saved.push(e); return { value: undefined } })
      await $.session.start({ cwd: '/test-project', surface, isInteractive: true })
      const ui = await mount($, surface)
      const firstUse = typeof seen !== 'number' || seen < 1
      expect(saved).toHaveLength(firstUse ? 1 : 0)
      if (firstUse) expect(saved[0]).toMatchObject({ key: 'onboardingVersion', value: 1 })
      for (const text of ONBOARDING) {
        const line = await ui.find({ type: 'Text', text })
        if (firstUse && surface === 'terminal') expect(line?.props).toMatchObject({ dimColor: true })
        else expect(line).toBeUndefined()
      }
      expect(await $.prompt.submit({ text: 'unchanged', wait: false, origin: { kind: 'composer' } }))
        .toEqual({ text: 'unchanged' })
      expect(await ui.find({ text: ONBOARDING[0] })).toBeUndefined()
      if (surface === 'desktop') expect(await ui.drawn()).toEqual(BASE)
    })
  }
  for (const operation of ['store.get', 'store.set'] as const) {
    test(`${surface}: ${operation} failure skips onboarding`, async ($, on) => {
      setup(on, state('available'))
      on('store.get', () => operation === 'store.get' ? { deny: 'synthetic store failure' } : { value: undefined })
      on('store.set', () => ({ deny: 'synthetic store failure' }))
      await $.session.start({ cwd: '/test-project', surface, isInteractive: true })
      const ui = await mount($, surface)
      expect(await ui.find({ text: ONBOARDING[0] })).toBeUndefined()
      if (surface === 'desktop') expect(await ui.drawn()).toEqual(BASE)
      else expect(await ui.find({ key: 'afkswitch-toggle' })).toBeDefined()
    })
  }
  for (const [name, raw, cells] of [
    ['available', state('available'), '□■'],
    ['afk', state('afk'), '■□'],
    ['missing', undefined, '□□'],
    ['unreadable', null, '□□'],
    ['future', state('available', 99), '□□'],
  ] as const) {
    test(`${surface}: ${name} draws confirmed cells or passes through`, async ($, on) => {
      const disk = setup(on, raw)
      const ui = await mount($, surface)
      if (surface === 'desktop') {
        expect(await ui.drawn()).toEqual(BASE)
        expect(disk.reads).toHaveLength(0)
        return
      }
      expect(await ui.find({ text: cells })).toBeDefined()
      expect(await ui.find({ text: 'existing band' })).toBeDefined()
      const label = await ui.find({ type: 'Text', text: /^AFK$/ })
      expect(label?.props).toMatchObject(name === 'afk' ? { color: '#F28C28', dimColor: false } : { dimColor: true })
      expect(await ui.findAll({ type: 'Button' })).toHaveLength(name === 'available' || name === 'afk' || name === 'missing' ? 1 : 0)
      if (name === 'missing') {
        expect(disk.reads).toHaveLength(0)
        return
      }
      expect(disk.reads[0].replace(/\\/g, '/')).toMatch(/\/test-state\/state.json$/)
      await ui.drawn()
      expect(disk.reads).toHaveLength(1)
    })
  }
}

for (const [before, after, command] of [
  ['missing', 'afk', 'afkswitch:afk'],
  ['available', 'afk', 'afkswitch:afk'],
  ['afk', 'available', 'afkswitch:back'],
] as const) {
  test(`click from ${before} runs exactly ${command} without context`, async ($, on) => {
    const disk = setup(on, before === 'missing' ? undefined : state(before))
    const calls: unknown[] = []
    on('command.run', ($, e) => {
      calls.push({ command: e.command, args: e.args, origin: e.origin })
      disk.raw = state(after)
      return {}
    })
    const ui = await mount($)
    await ui.press({ key: 'afkswitch-toggle' })
    expect(calls).toEqual([{ command, args: '', origin: { kind: 'plugin', name: 'afkswitch' } }])
    expect(await ui.find({ text: 'saving…' })).toBeDefined()
    await $.turn.complete({ answer: '', durationMs: 1, isAborted: false, turnId: 'synthetic', reason: 'answer' })
    expect(await ui.find({ text: after === 'afk' ? '■□' : '□■' })).toBeDefined()
    expect(disk.reads).toHaveLength(before === 'missing' ? 1 : 3)
  })

  test(`another session already changed ${before}: no opposite action`, async ($, on) => {
    const disk = setup(on, before === 'missing' ? undefined : state(before))
    let calls = 0
    on('command.run', () => { calls += 1; return {} })
    const ui = await mount($)
    disk.raw = state(after)
    await ui.press({ key: 'afkswitch-toggle' })
    expect(calls).toBe(0)
    expect(await ui.find({ text: after === 'afk' ? '■□' : '□■' })).toBeDefined()
  })
}

for (const before of ['available', 'missing']) {
test(`${before}: double press while command is queued runs only once and removes the button`, async ($, on) => {
  const disk = setup(on, before === 'missing' ? undefined : state(before))
  let release!: () => void
  let entered!: () => void
  const running = new Promise<void>(resolve => { entered = resolve })
  const held = new Promise<void>(resolve => { release = resolve })
  let calls = 0
  on('command.run', async () => {
    calls += 1
    entered()
    await held
    disk.raw = state('afk')
    return {}
  })
  const ui = await mount($)
  const first = ui.press({ key: 'afkswitch-toggle' })
  await running
  let second: Promise<unknown> | undefined
  try {
    expect(await ui.findAll({ type: 'Button' })).toHaveLength(0)
    expect((await ui.find({ type: 'Text', text: 'saving…' }))?.props).toMatchObject({ dimColor: true })
    expect(await ui.find({ type: 'Text', text: before === 'missing' ? '□□' : '□■' })).toBeDefined()
    second = ui.press({ key: 'afkswitch-toggle' }).catch(() => undefined)
  } finally {
    release()
    await Promise.all([first, second])
  }
  expect(calls).toBe(1)
  expect(await ui.find({ text: 'saving…' })).toBeDefined()
  await $.turn.complete({ answer: '', durationMs: 1, isAborted: false, turnId: 'synthetic', reason: 'answer' })
  expect(await ui.find({ text: 'saving…' })).toBeUndefined()
  expect(await ui.find({ text: '■□' })).toBeDefined()
})
}

test('queued back waits through an earlier turn, then confirms the saved state', async ($, on) => {
  const disk = setup(on, state('afk'))
  let calls = 0
  on('command.run', () => { calls += 1; return {} })
  const ui = await mount($)
  await ui.press({ key: 'afkswitch-toggle' })
  expect(calls).toBe(1)
  expect(await ui.find({ text: 'saving…' })).toBeDefined()
  expect(await ui.find({ text: '■□' })).toBeDefined()
  expect(await ui.find({ text: /not switched/ })).toBeUndefined()
  expect(await ui.findAll({ type: 'Button' })).toHaveLength(0)
  await $.turn.complete({ answer: '', durationMs: 1, isAborted: false, turnId: 'earlier', reason: 'answer' })
  expect(await ui.find({ text: 'saving…' })).toBeDefined()
  expect(await ui.find({ text: /not switched/ })).toBeUndefined()
  await $.command.run({ command: 'afkswitch:back', args: '', origin: { kind: 'plugin', name: 'afkswitch' } })
  disk.raw = state('available')
  await $.turn.complete({ answer: '', durationMs: 1, isAborted: false, turnId: 'switch', reason: 'answer' })
  expect(await ui.find({ text: '□■' })).toBeDefined()
  expect(await ui.find({ text: 'saving…' })).toBeUndefined()
  expect(await ui.find({ text: /not switched/ })).toBeUndefined()
  expect(await ui.find({ key: 'afkswitch-toggle' })).toBeDefined()
})

for (const event of [
  { command: 'afkswitch:back', args: 'unchanged', origin: { kind: 'composer' as const } },
  { command: 'afkswitch:back', args: 'unchanged', origin: { kind: 'plugin' as const, name: 'other-plugin' } },
  { command: 'other:command', args: 'unchanged', origin: { kind: 'plugin' as const, name: 'afkswitch' } },
]) {
  test(`unrelated command ${event.command} from ${JSON.stringify(event.origin)} passes through without starting the switch`, async ($, on) => {
    setup(on, state('afk'))
    const calls: unknown[] = []
    on('command.run', ($, e) => { calls.push(e); return {} })
    const ui = await mount($)
    await ui.press({ key: 'afkswitch-toggle' })
    await $.command.run(event)
    expect(calls[1]).toMatchObject(event)
    await $.turn.complete({ answer: '', durationMs: 1, isAborted: false, turnId: 'unrelated', reason: 'answer' })
    expect(await ui.find({ text: 'saving…' })).toBeDefined()
    expect(await ui.find({ text: /not switched/ })).toBeUndefined()
  })
}

test('started back with unchanged state fails only when its turn completes', async ($, on) => {
  setup(on, state('afk'))
  on('command.run', () => ({}))
  const ui = await mount($)
  await ui.press({ key: 'afkswitch-toggle' })
  await $.command.run({ command: 'afkswitch:back', args: '', origin: { kind: 'plugin', name: 'afkswitch' } })
  expect(await ui.find({ text: 'saving…' })).toBeDefined()
  expect(await ui.find({ text: /not switched/ })).toBeUndefined()
  await $.turn.complete({ answer: '', durationMs: 1, isAborted: false, turnId: 'switch', reason: 'answer' })
  expect(await ui.find({ text: 'saving…' })).toBeUndefined()
  expect(await ui.find({ text: '■□' })).toBeDefined()
  expect(await ui.find({ text: /not switched/ })).toBeDefined()
  expect(await ui.find({ key: 'afkswitch-toggle' })).toBeDefined()
})

for (const boundary of ['prompt.submit', 'session.start'] as const) {
  test(`${boundary} confirms a pending switch saved by another session`, async ($, on) => {
    const disk = setup(on, state('afk'))
    on('command.run', () => ({}))
    on('store.get', () => ({ value: 1 }))
    const ui = await mount($)
    await ui.press({ key: 'afkswitch-toggle' })
    disk.raw = state('available')
    if (boundary === 'prompt.submit') {
      await $.prompt.submit({ text: 'unchanged', wait: false, origin: { kind: 'composer' } })
    } else {
      await $.session.start({ cwd: '/test-project', surface: 'terminal', isInteractive: true })
    }
    expect(await ui.find({ text: '□■' })).toBeDefined()
    expect(await ui.find({ text: 'saving…' })).toBeUndefined()
    expect(await ui.find({ text: /not switched/ })).toBeUndefined()
  })
}

test('first press dismisses onboarding even when the command fails', async ($, on) => {
  setup(on, state('available'))
  on('store.get', () => ({ value: undefined }))
  on('store.set', () => ({ value: undefined }))
  on('command.run', () => { throw new Error('synthetic command failure') })
  await $.session.start({ cwd: '/test-project', surface: 'terminal', isInteractive: true })
  const ui = await mount($)
  expect(await ui.find({ text: ONBOARDING[0] })).toBeDefined()
  await ui.press({ key: 'afkswitch-toggle' })
  expect(await ui.find({ text: ONBOARDING[0] })).toBeUndefined()
  expect((await ui.find({ type: 'Text', text: 'not switched — try /afk or /back' }))?.props).toMatchObject({ color: '#F28C28' })
  await $.turn.complete({ answer: '', durationMs: 1, isAborted: false, turnId: 'synthetic', reason: 'answer' })
  expect(await ui.find({ text: /not switched/ })).toBeUndefined()
})

test('missing drawing re-reads an invalid file before dispatch and fails closed', async ($, on) => {
  const disk = setup(on, undefined)
  let calls = 0
  on('command.run', () => { calls += 1; return {} })
  const ui = await mount($)
  disk.raw = 'not json'
  await ui.press({ key: 'afkswitch-toggle' })
  expect(calls).toBe(0)
  expect(await ui.find({ text: '□□' })).toBeDefined()
  expect(await ui.findAll({ type: 'Button' })).toHaveLength(0)
  expect(await ui.find({ type: 'Text', text: /not switched/ })).toBeDefined()
})

test('missing state after dispatch is unconfirmed', async ($, on) => {
  setup(on, undefined)
  on('command.run', () => ({}))
  const ui = await mount($)
  await ui.press({ key: 'afkswitch-toggle' })
  expect(await ui.find({ text: '□□' })).toBeDefined()
  expect(await ui.find({ text: '■□' })).toBeUndefined()
  expect(await ui.find({ text: 'saving…' })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /not switched/ })).toBeUndefined()
})

test('existence check throwing stays unknown and cannot be pressed', async ($, on) => {
  const disk = setup(on, undefined)
  disk.existenceError = true
  const ui = await mount($)
  expect(await ui.find({ text: '□□' })).toBeDefined()
  expect(await ui.findAll({ type: 'Button' })).toHaveLength(0)
})

for (const failure of ['throw', 'exit', 'unconfirmed'] as const) {
  test(`command ${failure}: re-enabled, disk truth, minimal error`, async ($, on) => {
    setup(on, state('available'))
    on('command.run', () => {
      if (failure === 'throw') throw new Error('synthetic command failure')
      return failure === 'exit' ? { exitCode: 1 } : {}
    })
    const ui = await mount($)
    await ui.press({ key: 'afkswitch-toggle' })
    if (failure !== 'throw') {
      expect(await ui.find({ text: 'saving…' })).toBeDefined()
      expect(await ui.find({ text: /not switched/ })).toBeUndefined()
      await $.command.run({ command: 'afkswitch:afk', args: '', origin: { kind: 'plugin', name: 'afkswitch' } })
      await $.turn.complete({ answer: '', durationMs: 1, isAborted: false, turnId: 'synthetic', reason: 'answer' })
    }
    expect(await ui.find({ key: 'afkswitch-toggle' })).toBeDefined()
    expect(await ui.find({ text: '□■' })).toBeDefined()
    expect(await ui.find({ text: '■□' })).toBeUndefined()
    expect(await ui.find({ type: 'Text', text: /not switched/ })).toBeDefined()
  })
}

test('unreadable or future state before a click never runs a command', async ($, on) => {
  const disk = setup(on, state('available'))
  let calls = 0
  on('command.run', () => { calls += 1; return {} })
  const ui = await mount($)
  disk.raw = state('afk', 99)
  await ui.press({ key: 'afkswitch-toggle' })
  expect(calls).toBe(0)
  expect(await ui.find({ text: '□□' })).toBeDefined()
  expect(await ui.findAll({ type: 'Button' })).toHaveLength(0)
})

test('session.start, prompt.submit and turn.complete refresh; render stays cached', async ($, on) => {
  const disk = setup(on, state('available'))
  await $.session.start({ cwd: '/test-project', surface: 'terminal', isInteractive: true })
  const ui = await mount($)
  expect(disk.reads).toHaveLength(1)
  disk.raw = state('afk')
  await $.prompt.submit({ text: 'draft submitted', wait: false, origin: { kind: 'composer' } })
  expect(await ui.find({ text: '■□' })).toBeDefined()
  disk.raw = null
  await $.turn.complete({ answer: '', durationMs: 1, isAborted: false, turnId: 'synthetic', reason: 'answer' })
  expect(await ui.find({ text: '□□' })).toBeDefined()
  expect(disk.reads).toHaveLength(3)
})

for (const variables of [{ HOME: '/test-home' }, { USERPROFILE: '/test-profile' }]) {
  test(`version 1 and home resolution via ${Object.keys(variables)[0]}`, async ($, on) => {
    const disk = setup(on, '\uFEFF' + state('afk', 1), variables)
    const ui = await mount($)
    expect(await ui.find({ text: '■□' })).toBeDefined()
    expect(disk.reads[0].replace(/\\/g, '/')).toMatch(new RegExp(`${Object.values(variables)[0]}/\\.afkswitch/state\\.json$`))
  })
}

test('unexpected module error continues next(e)', async ($, on) => {
  let nextCalls = 0
  on('env.get', () => { throw new Error('synthetic module error') })
  on('ui.render', () => { nextCalls += 1; return BASE })
  const ui = await mount($)
  expect(await ui.drawn()).toEqual(BASE)
  expect(nextCalls).toBe(1)
})

test('unexpected lifecycle errors continue every boundary unchanged', async ($, on) => {
  let calls = 0
  on('env.get', () => ({ deny: 'synthetic environment error' }))
  on('session.start', ($, e) => { calls += 1; return { cwd: e.cwd } })
  on('prompt.submit', ($, e) => { calls += 1; return { text: e.text } })
  on('turn.complete', ($, e) => { calls += 1; return { text: e.answer } })
  expect(await $.session.start({ cwd: '/test-project', surface: 'terminal', isInteractive: true }))
    .toEqual({ cwd: '/test-project' })
  expect(await $.prompt.submit({ text: 'unchanged', wait: false, origin: { kind: 'composer' } }))
    .toEqual({ text: 'unchanged' })
  expect(await $.turn.complete({ answer: 'unchanged', durationMs: 1, isAborted: false, turnId: 'synthetic', reason: 'answer' }))
    .toEqual({ text: 'unchanged' })
  expect(calls).toBe(3)
})

for (const raw of ['not json', '[]', 'null', '{"version":2,"status":"available"}', state('other'), state('available', 0), state('afk', 1.5)]) {
  test(`invalid drawing fields stay neutral: ${raw}`, async ($, on) => {
    setup(on, raw)
    const ui = await mount($)
    expect(await ui.find({ text: '□□' })).toBeDefined()
    expect(await ui.findAll({ type: 'Button' })).toHaveLength(0)
  })
}
