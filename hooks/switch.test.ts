import { expect, mock, test } from 'claude-code/testing'
import type { Engine } from 'claude-code/testing'
import type { On } from 'claude-code'
import { pickIdle } from './switch.tsx'

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
type Disk = { raw: string | null | undefined; reads: string[]; existenceError?: boolean; clock: ReturnType<typeof mock.clock> }

const setup = (on: On, raw: string | null | undefined, variables = { AFKSWITCH_STATE_DIR: '/test-state' }): Disk => {
  const disk: Disk = { raw, reads: [], clock: mock.clock(on) }
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

const mount = ($: Engine, surface: 'terminal' | 'desktop' | 'vscode' = 'terminal') =>
  $.ui.mount({ plugin: 'afkswitch', surface, component: 'AbovePrompt', props: PROPS })

// terminal and desktop draw the switch; vscode passes through.
for (const surface of ['terminal', 'desktop', 'vscode'] as const) {
  for (const seen of [undefined, 1, 2, '1', 0]) {
    test(`${surface}: onboarding version ${seen}`, async ($, on) => {
      setup(on, state('available'))
      const saved: unknown[] = []
      on('store.get', () => ({ value: seen }))
      on('store.set', ($, e) => { saved.push(e); return { value: undefined } })
      await $.session.start({ cwd: '/test-project', surface, isInteractive: true })
      const ui = await mount($, surface)
      const firstUse = typeof seen !== 'number' || seen < 1
      const spent = firstUse && surface !== 'vscode'
      expect(saved).toHaveLength(spent ? 1 : 0)
      if (spent) expect(saved[0]).toMatchObject({ key: 'onboardingVersion', value: 1 })
      for (const text of ONBOARDING) {
        const line = await ui.find({ type: 'Text', text })
        if (spent) expect(line?.props).toMatchObject({ dimColor: true })
        else expect(line).toBeUndefined()
      }
      expect(await $.prompt.submit({ text: 'unchanged', wait: false, origin: { kind: 'composer' } }))
        .toEqual({ text: 'unchanged' })
      expect(await ui.find({ text: ONBOARDING[0] })).toBeUndefined()
      if (surface === 'vscode') expect(await ui.drawn()).toMatchObject(BASE)
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
      if (surface === 'vscode') expect(await ui.drawn()).toMatchObject(BASE)
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
      if (surface === 'vscode') {
        expect(await ui.drawn()).toMatchObject(BASE)
        expect(disk.reads).toHaveLength(0)
        return
      }
      expect(await ui.find({ text: 'existing band' })).toBeDefined()
      const pressable = name === 'available' || name === 'afk' || name === 'missing'
      expect(await ui.findAll({ type: 'Button' })).toHaveLength(pressable ? 1 : 0)
      if (pressable) {
        // The whole inside of the border is the button; "away" shows on the border.
        const button = await ui.find({ key: 'afkswitch-toggle' })
        expect(button?.props).toMatchObject({ label: ` AFK  ${cells} `, dimColor: name !== 'afk' })
        const boxes = await ui.findAll({ type: 'Box' })
        const border = boxes.find(b => (b.props as { borderStyle?: string })?.borderStyle === 'single')
        expect((border?.props as { borderColor?: string })?.borderColor).toBe(name === 'afk' ? '#F28C28' : undefined)
      } else {
        expect(await ui.find({ text: cells })).toBeDefined()
        const label = await ui.find({ type: 'Text', text: /^AFK$/ })
        expect(label?.props).toMatchObject({ dimColor: true })
      }
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

test('Windows reads USERPROFILE even when HOME is set, as the helper does', async ($, on) => {
  const disk = setup(on, state('afk'), { OS: 'Windows_NT', HOME: '/test-home', USERPROFILE: '/test-profile' } as never)
  const ui = await mount($)
  expect(await ui.find({ text: '■□' })).toBeDefined()
  expect(disk.reads[0].replace(/\\/g, '/')).toMatch(/\/test-profile\/\.afkswitch\/state\.json$/)
})

test('an environment error draws unknown state and keeps the band beneath', async ($, on) => {
  let nextCalls = 0
  on('env.get', () => ({ deny: 'synthetic module error' }))
  on('ui.render', () => { nextCalls += 1; return BASE })
  const ui = await mount($)
  expect(await ui.find({ text: 'existing band' })).toBeDefined()
  expect(await ui.find({ text: '□□' })).toBeDefined()
  expect(await ui.findAll({ type: 'Button' })).toHaveLength(0)
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

const away = (context: string | null) => JSON.stringify({
  version: 2, status: 'afk', since: '2026-09-30T12:00:00Z', context, generation: 1,
})
const IDLE_LABELS = [
  '🌳 at the park', '💃 dancing', '💬 chatting', '☕ coffee break',
  '🚶 out for a walk', '🎧 listening to music', '🍜 grabbing a bite', '📚 reading',
  '🦆 arguing with a duck', '🧦 hunting the other sock', '🍕 negotiating with a pizza',
  '🐈 being ignored by a cat', '🪴 talking to the plants',
  // rare ones
  '🛸 abducted, back soon', '👻 haunting the hallway', '🌀 stuck in a time loop',
]
const KIND_LABELS = ['💼 at work', '💤 sleeping', '🛒 shopping', '🛫 traveling']
const submit = ($: Engine) => $.prompt.submit({ text: 'unchanged', wait: false, origin: { kind: 'composer' } })
type Mounted = Awaited<ReturnType<typeof mount>>
const texts = async (ui: Mounted) => (await ui.findAll({ type: 'Text' })).map(node => String(node.children?.[0]))
// The label beside the switch, if any: ' <emoji> words', or ' <two spaces> words' on a blink's off beat.
const label = async (ui: Mounted) => (await texts(ui)).find(text =>
  [...IDLE_LABELS, ...KIND_LABELS].some(known => text.endsWith(known.replace(/^\S+/, ''))) && text !== ' AFK')
const blinked = (shown: string) => shown.replace(/^ \S+/, '   ')

for (const [context, kind] of [
  ['sleep', '💤 sleeping'], ['Vou dormir, volto 8h', '💤 sleeping'], ['good night', '💤 sleeping'],
  ['napping', '💤 sleeping'], ['soneca rápida', '💤 sleeping'],
  ['work', '💼 at work'], ['indo pro trabalho', '💼 at work'], ['night shift', '💼 at work'],
  ['in a meeting until 3', '💼 at work'], ['Working from the Office', '💼 at work'], ['reunião', '💼 at work'],
  ['shopping for groceries', '🛒 shopping'], ['compras no supermercado', '🛒 shopping'],
  ['Trip to Dublin', '🛫 traveling'], ['viagem até domingo', '🛫 traveling'],
  ['two flights today', '🛫 traveling'], ['férias', '🛫 traveling'], ['bank holiday', '🛫 traveling'],
  // The earliest hit in the text wins.
  ['at work, then shopping', '💼 at work'], ['shopping, then back at work', '🛒 shopping'],
  ['going to sleep after the flight', '💤 sleeping'],
] as const) {
  for (const surface of ['terminal', 'desktop'] as const) {
    test(`indicator on ${surface}: "${context}" shows ${kind}`, async ($, on) => {
      const disk = setup(on, away(context))
      const ui = await mount($, surface)
      expect(await label(ui)).toBe(` ${kind}`)
      expect((await ui.find({ type: 'Text', text: ` ${kind}` }))?.props).toMatchObject({ dimColor: true })
      // The label names a kind only; the note itself is never drawn.
      if (context.length > 8) expect((await texts(ui)).some(text => text.includes(context))).toBe(false)
      // A kind label holds still: it never blinks, leaves or gives way to an idle one.
      for (let i = 0; i < 4; i += 1) await submit($)
      for (let i = 0; i < 16; i += 1) {
        await disk.clock.advance(600)
        expect(await label(ui)).toBe(` ${kind}`)
      }
    })
  }
}

for (const context of [
  'workout', 'work out at the gym', 'store the file', 'trip wire', 'network down', 'nightly build', 'homework',
  'cron job is running', 'let claude keep working', "it doesn't work yet", 'post office', 'out of office',
  'coffee shop', 'napkins', 'workshop', 'mercado livre', 'flight sim', 'sleep mode', 'walking the dog', 'dentist',
]) {
  test(`indicator: "${context}" is no known kind, and a note never gets an idle label`, async ($, on) => {
    const disk = setup(on, away(context))
    const ui = await mount($)
    expect(await label(ui)).toBeUndefined()
    for (let i = 0; i < 6; i += 1) {
      await submit($)
      expect(await label(ui)).toBeUndefined()
    }
    await disk.clock.advance(20000)
    expect(await label(ui)).toBeUndefined()
  })
}

test('indicator: with no note an idle label shows on every third event, blinks 3 seconds, and leaves at 8', async ($, on) => {
  const disk = setup(on, away(null))
  const ui = await mount($)
  expect(await label(ui)).toBeUndefined()
  await submit($)
  await $.turn.complete({ answer: '', durationMs: 1, isAborted: false, turnId: 'one', reason: 'answer' })
  expect(await label(ui)).toBeUndefined()
  await submit($)
  const shown = await label(ui)
  expect(IDLE_LABELS.map(known => ` ${known}`)).toContain(shown)
  // Later events neither restart nor remove it.
  await submit($)
  // The emoji goes off at 600 ms and back at 1200, with the words in place.
  await disk.clock.advance(599)
  expect(await label(ui)).toBe(shown)
  await disk.clock.advance(1)
  expect(await label(ui)).toBe(blinked(shown!))
  await disk.clock.advance(599)
  expect(await label(ui)).toBe(blinked(shown!))
  await disk.clock.advance(1)
  expect(await label(ui)).toBe(shown)
  // After 3 seconds it holds still.
  await disk.clock.advance(1800)
  for (let i = 0; i < 8; i += 1) {
    expect(await label(ui)).toBe(shown)
    await disk.clock.advance(600)
  }
  // 7800 ms so far: still there just before 8 seconds, gone at 8.
  await disk.clock.advance(199)
  expect(await label(ui)).toBe(shown)
  await disk.clock.advance(1)
  expect(await label(ui)).toBeUndefined()
  // Every timer has stopped: nothing comes back by itself.
  await disk.clock.advance(30000)
  expect(await label(ui)).toBeUndefined()
  // The next label comes on the sixth event, not before.
  await submit($)
  expect(await label(ui)).toBeUndefined()
  await submit($)
  expect(IDLE_LABELS.map(known => ` ${known}`)).toContain(await label(ui))
})

test('indicator: a new idle label replaces the old clock instead of inheriting it', async ($, on) => {
  const disk = setup(on, away(null))
  const ui = await mount($)
  for (let i = 0; i < 3; i += 1) await submit($)
  await disk.clock.advance(5000)
  for (let i = 0; i < 3; i += 1) await submit($)
  // The first label's clock would end now; the second label is 3.1 seconds old.
  await disk.clock.advance(3100)
  const second = await label(ui)
  expect(IDLE_LABELS.map(known => ` ${known}`)).toContain(second)
  // And the first label's blink is not still toggling it.
  await disk.clock.advance(600)
  expect(await label(ui)).toBe(second)
  await disk.clock.advance(4300)
  expect(await label(ui)).toBeUndefined()
})

test('indicator: an idle label is dropped at once on return, its clocks stop, and the count restarts', async ($, on) => {
  const disk = setup(on, away(null))
  const ui = await mount($)
  for (let i = 0; i < 3; i += 1) await submit($)
  expect(await label(ui)).toBeDefined()
  disk.raw = state('available')
  await submit($)
  expect(await label(ui)).toBeUndefined()
  disk.raw = away(null)
  await submit($)
  expect(await label(ui)).toBeUndefined()
  await disk.clock.advance(9000)
  expect(await label(ui)).toBeUndefined()
  await submit($)
  expect(await label(ui)).toBeUndefined()
  await submit($)
  expect(await label(ui)).toBeDefined()
})

test('indicator: the timers armed from session.start show and remove the label too', async ($, on) => {
  const disk = setup(on, away(null))
  on('store.get', () => ({ value: 1 }))
  on('store.set', () => ({ value: undefined }))
  await $.session.start({ cwd: '/test-project', surface: 'terminal', isInteractive: true })
  const ui = await mount($)
  for (let i = 0; i < 3; i += 1) await submit($)
  const shown = await label(ui)
  expect(shown).toBeDefined()
  await disk.clock.advance(600)
  expect(await label(ui)).toBe(blinked(shown!))
  await disk.clock.advance(7400)
  expect(await label(ui)).toBeUndefined()
})

test('indicator: the label follows the note when it changes while away', async ($, on) => {
  const disk = setup(on, away('sleep'))
  const ui = await mount($)
  expect(await label(ui)).toBe(' 💤 sleeping')
  disk.raw = away('at work')
  await submit($)
  expect(await label(ui)).toBe(' 💼 at work')
  disk.raw = away(null)
  await submit($)
  expect(await label(ui)).toBeUndefined()
  disk.raw = 'not json'
  await submit($)
  expect(await label(ui)).toBeUndefined()
})

test('indicator: an unreadable state hides the label but is not a return', async ($, on) => {
  const disk = setup(on, away(null))
  const ui = await mount($)
  for (let i = 0; i < 2; i += 1) await submit($)
  disk.raw = 'not json'
  await submit($)
  expect(await label(ui)).toBeUndefined()
  // The count did not restart: the next readable event is the third one.
  disk.raw = away(null)
  await submit($)
  expect(await label(ui)).toBeDefined()
})

test('indicator: nothing is drawn or timed while present', async ($, on) => {
  const disk = setup(on, state('available'))
  const ui = await mount($)
  for (let i = 0; i < 6; i += 1) {
    await submit($)
    expect(await label(ui)).toBeUndefined()
  }
  const reads = disk.reads.length
  await disk.clock.advance(60000)
  expect(disk.reads).toHaveLength(reads)  // no polling: the clock alone never reads the state
  expect(await label(ui)).toBeUndefined()
})

test('indicator: a surface that does not draw the switch gets no label and no timer', async ($, on) => {
  const disk = setup(on, away(null))
  const ui = await mount($, 'vscode')
  for (let i = 0; i < 6; i += 1) await submit($)
  expect(await ui.drawn()).toMatchObject(BASE)
  await disk.clock.advance(20000)
  expect(await ui.drawn()).toMatchObject(BASE)
})

test('indicator: it sits outside the border, leaves the button alone, and yields to a failed press', async ($, on) => {
  setup(on, away('sleep'))
  const calls: string[] = []
  on('command.run', ($, e) => {
    calls.push(e.command)
    throw new Error('synthetic command failure')
  })
  const ui = await mount($)
  const border = (await ui.findAll({ type: 'Box' })).find(box => (box.props as { borderStyle?: string })?.borderStyle === 'single')
  expect(JSON.stringify(border)).not.toContain('sleeping')
  expect((await ui.find({ key: 'afkswitch-toggle' }))?.props).toMatchObject({ label: ' AFK  ■□ ' })
  await ui.press({ key: 'afkswitch-toggle' })
  expect(calls).toEqual(['afkswitch:back'])
  expect(await ui.find({ type: 'Text', text: /not switched/ })).toBeDefined()
  expect(await label(ui)).toBeUndefined()
})

test('idle labels: about one pick in twenty comes from the rare list', () => {
  const rare = IDLE_LABELS.slice(-3)
  const common = IDLE_LABELS.slice(0, -3)
  expect(rare).toContain(pickIdle(0.049, 0))
  expect(rare).toContain(pickIdle(0, 0.99))
  expect(common).toContain(pickIdle(0.05, 0))
  expect(common).toContain(pickIdle(0.99, 0.99))
  // Every label of each pool can come out.
  expect(new Set(rare.map((_, i) => pickIdle(0, i / rare.length)))).toEqual(new Set(rare))
  expect(new Set(common.map((_, i) => pickIdle(1, i / common.length)))).toEqual(new Set(common))
})
