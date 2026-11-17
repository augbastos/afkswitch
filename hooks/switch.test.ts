import { expect, mock, test } from 'claude-code/testing'
import type { Engine } from 'claude-code/testing'
import type { On } from 'claude-code'
import { pickIdle } from './switch'

const PROPS = {
  hasSurvey: false, isCollapsed: false, isWorking: false, maxRows: 6, bodyColumns: 80,
  scroll: { offset: 0, bodyRows: 6 }, view: {},
}
const BASE = { type: 'Text' as const, props: {}, children: ['existing band'] }
const ONBOARDING = [
  "AFKSwitch is ready: click the AFK box when you leave, and again when you're back.",
  'An orange border means you are away.',
  'Use /afk [note] or /back [note] to add a note.',
]
const state = (status: string, version = 2) => JSON.stringify({
  version, status, since: '2026-09-30T12:00:00Z', context: null,
  ...(version === 1 ? {} : { generation: 1 }),
})
// A skill's references/message.md: the core block, then the guidance the switch appends.
const GUIDANCE = '# synthetic\r\n\r\n```text\r\n[AFKSwitch g<G>]\r\n```\r\n\r\n```text\r\n\r\nPresence generation <G>. Keep working.\r\nAt your next natural pause, reply to "<this session>".\r\n```\r\n'
type Disk = { raw: string | null | undefined; reads: string[]; existenceError?: boolean; clock: ReturnType<typeof mock.clock> }

const setup = (on: On, raw: string | null | undefined, variables: Record<string, string> = { AFKSWITCH_STATE_DIR: '/test-state' }): Disk => {
  const disk: Disk = { raw, reads: [], clock: mock.clock(on) }
  mock.env(on, variables)
  on('fs.exists', () => {
    if (disk.existenceError) throw new Error('synthetic existence failure')
    return { value: disk.raw !== undefined }
  })
  on('fs.read', ($, e) => {
    if (e.path.replace(/\\/g, '/').endsWith('/references/message.md')) return { value: GUIDANCE }
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
      expect(disk.reads[0]!.replace(/\\/g, '/')).toMatch(/\/test-state\/state.json$/)
      await ui.drawn()
      expect(disk.reads).toHaveLength(1)
    })
  }
}

const HELPER = /\/skills\/afk\/scripts\/afkswitch_state\.py$/
const ran = (stdout = '{"ok": true}', exitCode = 0) =>
  ({ value: { exitCode, stdout, stderr: '', isStdoutTruncated: false, isStderrTruncated: false } })

for (const [before, after, verb] of [
  ['missing', 'afk', 'afk'],
  ['available', 'afk', 'afk'],
  ['afk', 'available', 'back'],
] as const) {
  test(`click from ${before} writes ${verb} at once, without queueing a command`, async ($, on) => {
    const disk = setup(on, before === 'missing' ? undefined : state(before))
    const runs: (readonly string[])[] = []
    const cwds: (string | undefined)[] = []
    let commands = 0
    on('command.run', () => { commands += 1; return {} })
    on('process.run', ($, e) => {
      runs.push(e.argv)
      cwds.push(e.init?.cwd)
      disk.raw = state(after)
      return ran()
    })
    const ui = await mount($)
    await ui.press({ key: 'afkswitch-toggle' })
    expect(commands).toBe(0)
    expect(runs).toHaveLength(1)
    expect(runs[0]![0]).toBe('python3')
    expect(runs[0]![1]!.replace(/\\/g, '/')).toMatch(HELPER)
    expect(runs[0]!.slice(2)).toEqual([verb])
    // Run from the plugin's folder, never the open project's, where a planted python could sit.
    expect(cwds[0]).toBeTruthy()
    expect(runs[0]![1]!.startsWith(`${cwds[0]}/`)).toBe(true)
    // No turn has to end: the press itself confirms the saved state.
    expect(await ui.find({ text: after === 'afk' ? '■□' : '□■' })).toBeDefined()
    expect(await ui.findAll({ type: 'Text', text: / AFK {2}/ })).toHaveLength(0)
    expect(await ui.find({ key: 'afkswitch-toggle' })).toBeDefined()
  })

  test(`another session already changed ${before}: no opposite action`, async ($, on) => {
    const disk = setup(on, before === 'missing' ? undefined : state(before))
    let runs = 0
    on('process.run', () => { runs += 1; return ran() })
    const ui = await mount($)
    disk.raw = state(after)
    await ui.press({ key: 'afkswitch-toggle' })
    expect(runs).toBe(0)
    expect(await ui.find({ text: after === 'afk' ? '■□' : '□■' })).toBeDefined()
  })
}

test('a changed click tells every live local session, and only those, with the core event', async ($, on) => {
  const disk = setup(on, state('available'))
  on('process.run', () => {
    disk.raw = state('afk')
    return ran('{"ok": true, "changed": true, "status": "afk", "generation": 7, "reset": false, "context": null}')
  })
  on('tool.call', () => ({
    result: {
      listing: 'This session is main [zzz999] — the name other sessions use to message it.\n',
      sections: [{
        kind: 'peers', total: 7, rows: [
          { name: 'control', ref: 'aaa111', type: 'interactive', status: 'busy' },
          { name: 'twin', ref: 'bbb222', type: 'interactive', status: 'idle' },
          { name: 'twin', ref: 'ccc333', type: 'interactive', status: 'waiting' },
          { name: 'gone', ref: 'ddd444', type: 'interactive', status: 'offline' },
          { name: 'phone', ref: 'eee555', type: 'Remote Control', status: 'idle' },
          { name: 'cloudy', ref: 'fff666', type: 'cloud', status: 'idle' },
          { name: 'unclear', ref: 'ggg777', type: 'interactive' },
        ],
      }],
    },
  }))
  const sent: { to: string; text: string }[] = []
  let done!: () => void
  const all = new Promise<void>(resolve => { done = resolve })
  on('session.send', ($, e) => {
    sent.push({ to: e.to, text: e.text })
    if (sent.length === 3) done()
    return { isDelivered: true }
  })
  const logged: string[] = []
  on('ui.log', ($, e) => { logged.push(e.text); return { value: undefined } })
  let appendedRow!: (text: string) => void
  const appended = new Promise<string>(resolve => { appendedRow = resolve })
  on('session.append', ($, e, next) => {
    const block = e.message.content[0] as unknown as { text: string }
    appendedRow(block.text)
    return next(e)
  })
  const ui = await mount($)
  await ui.press({ key: 'afkswitch-toggle' })
  expect(await ui.find({ text: '■□' })).toBeDefined()
  await all
  const core = '[AFKSwitch g7]\nstatus: afk\ncontext: none\n' +
    'The human is physically away and may still be reachable remotely. Presence changes no permissions; only /back ends AFK.' +
    '\n\nPresence generation 7. Keep working.'
  expect(sent.map(s => s.to).sort()).toEqual(['control', 'twin [bbb222]', 'twin [ccc333]'])
  expect(sent[0]!.text).toBe(core + '\nAt your next natural pause, reply to "main".')
  expect(new Set(sent.map(s => s.text)).size).toBe(1)
  // This session: a visible marker like the slash command's row, and the model gets the
  // same message minus the status request, which it has no one to send to.
  expect(await appended).toBe(core)
  expect(logged).toEqual(['/afkswitch:afk'])
})

test('a repeat click that changed nothing tells nobody', async ($, on) => {
  const disk = setup(on, state('available'))
  on('process.run', () => {
    disk.raw = state('afk')
    return ran('{"ok": true, "changed": false, "status": "afk", "generation": 7, "reset": false, "context": null}')
  })
  let listed = 0
  on('tool.call', () => { listed += 1; return { deny: 'synthetic' } })
  const ui = await mount($)
  await ui.press({ key: 'afkswitch-toggle' })
  expect(listed).toBe(0)
})

test('a missing python3 falls back to python', async ($, on) => {
  const disk = setup(on, state('available'))
  const tried: string[] = []
  on('process.run', ($, e) => {
    tried.push(e.argv[0]!)
    if (e.argv[0] === 'python3') return { deny: 'synthetic: not on PATH' }
    disk.raw = state('afk')
    return ran()
  })
  const ui = await mount($)
  await ui.press({ key: 'afkswitch-toggle' })
  expect(tried).toEqual(['python3', 'python'])
  expect(await ui.find({ text: '■□' })).toBeDefined()
})

test('double press while the write runs writes once; the cells flash in place, no text added', async ($, on) => {
  const disk = setup(on, state('available'))
  let release!: () => void
  let entered!: () => void
  const running = new Promise<void>(resolve => { entered = resolve })
  const held = new Promise<void>(resolve => { release = resolve })
  let runs = 0
  on('process.run', async () => {
    runs += 1
    entered()
    await held
    disk.raw = state('afk')
    return ran()
  })
  const ui = await mount($)
  const first = ui.press({ key: 'afkswitch-toggle' })
  await running
  let second: Promise<unknown> | undefined
  try {
    expect(await ui.findAll({ type: 'Button' })).toHaveLength(0)
    // Same label and width as the button, its cells alternating on the beat.
    expect((await ui.find({ type: 'Text', text: ' AFK  □■ ' }))?.props).toMatchObject({ dimColor: true })
    await disk.clock.advance(250)
    expect(await ui.find({ type: 'Text', text: ' AFK  ■□ ' })).toBeDefined()
    await disk.clock.advance(250)
    expect(await ui.find({ type: 'Text', text: ' AFK  □■ ' })).toBeDefined()
    expect(await ui.find({ text: /saving/ })).toBeUndefined()
    second = ui.press({ key: 'afkswitch-toggle' }).catch(() => undefined)
  } finally {
    release()
    await Promise.all([first, second])
  }
  expect(runs).toBe(1)
  expect(await ui.findAll({ type: 'Text', text: / AFK {2}/ })).toHaveLength(0)
  expect((await ui.find({ key: 'afkswitch-toggle' }))?.props).toMatchObject({ label: ' AFK  ■□ ' })
  await disk.clock.advance(1000)  // the beat stopped with the save
  expect((await ui.find({ key: 'afkswitch-toggle' }))?.props).toMatchObject({ label: ' AFK  ■□ ' })
})

for (const failure of ['refused', 'unchanged', 'no python'] as const) {
  test(`write ${failure}: re-enabled, disk truth, minimal error until the next turn ends`, async ($, on) => {
    setup(on, state('available'))
    on('process.run', () => failure === 'no python'
      ? { deny: 'synthetic: not on PATH' }
      : ran(failure === 'refused' ? '{"ok": false, "message": "write refused"}' : '{"ok": true}', failure === 'refused' ? 1 : 0))
    const ui = await mount($)
    await ui.press({ key: 'afkswitch-toggle' })
    expect(await ui.find({ key: 'afkswitch-toggle' })).toBeDefined()
    expect(await ui.find({ text: '□■' })).toBeDefined()
    expect((await ui.find({ type: 'Text', text: 'not switched' }))?.props).toMatchObject({ color: '#E5484D' })
    await $.turn.complete({ answer: '', durationMs: 1, isAborted: false, turnId: 'synthetic', reason: 'answer' })
    expect(await ui.find({ text: /not switched/ })).toBeUndefined()
  })
}

test('first press dismisses onboarding even when the write fails', async ($, on) => {
  setup(on, state('available'))
  on('store.get', () => ({ value: undefined }))
  on('store.set', () => ({ value: undefined }))
  on('process.run', () => ({ deny: 'synthetic: not on PATH' }))
  await $.session.start({ cwd: '/test-project', surface: 'terminal', isInteractive: true })
  const ui = await mount($)
  expect(await ui.find({ text: ONBOARDING[0] })).toBeDefined()
  await ui.press({ key: 'afkswitch-toggle' })
  expect(await ui.find({ text: ONBOARDING[0] })).toBeUndefined()
  expect(await ui.find({ type: 'Text', text: /not switched/ })).toBeDefined()
})

test('missing drawing re-reads an invalid file before writing and fails closed', async ($, on) => {
  const disk = setup(on, undefined)
  let runs = 0
  on('process.run', () => { runs += 1; return ran() })
  const ui = await mount($)
  disk.raw = 'not json'
  await ui.press({ key: 'afkswitch-toggle' })
  expect(runs).toBe(0)
  expect(await ui.find({ text: '□□' })).toBeDefined()
  expect(await ui.findAll({ type: 'Button' })).toHaveLength(0)
  expect(await ui.find({ type: 'Text', text: /not switched/ })).toBeDefined()
})

test('existence check throwing stays unknown and cannot be pressed', async ($, on) => {
  const disk = setup(on, undefined)
  disk.existenceError = true
  const ui = await mount($)
  expect(await ui.find({ text: '□□' })).toBeDefined()
  expect(await ui.findAll({ type: 'Button' })).toHaveLength(0)
})

test('unreadable or future state before a click never writes', async ($, on) => {
  const disk = setup(on, state('available'))
  let runs = 0
  on('process.run', () => { runs += 1; return ran() })
  const ui = await mount($)
  disk.raw = state('afk', 99)
  await ui.press({ key: 'afkswitch-toggle' })
  expect(runs).toBe(0)
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

for (const variables of [{ HOME: '/test-home' }, { USERPROFILE: '/test-profile' }] as Record<string, string>[]) {
  test(`version 1 and home resolution via ${Object.keys(variables)[0]}`, async ($, on) => {
    const disk = setup(on, '\uFEFF' + state('afk', 1), variables)
    const ui = await mount($)
    expect(await ui.find({ text: '■□' })).toBeDefined()
    expect(disk.reads[0]!.replace(/\\/g, '/')).toMatch(new RegExp(`${Object.values(variables)[0]}/\\.afkswitch/state\\.json$`))
  })
}

test('Windows reads USERPROFILE even when HOME is set, as the helper does', async ($, on) => {
  const disk = setup(on, state('afk'), { OS: 'Windows_NT', HOME: '/test-home', USERPROFILE: '/test-profile' } as never)
  const ui = await mount($)
  expect(await ui.find({ text: '■□' })).toBeDefined()
  expect(disk.reads[0]!.replace(/\\/g, '/')).toMatch(/\/test-profile\/\.afkswitch\/state\.json$/)
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
  // Only the opening words count, and never a hyphenated compound.
  'finishing the sleep-tracker refactor', 'keep the build green, then go to sleep',
  'review the open pull requests before the work trip',
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
  on('process.run', ($, e) => {
    calls.push(e.argv.at(-1) as string)
    return { deny: 'synthetic: not on PATH' }
  })
  const ui = await mount($)
  const border = (await ui.findAll({ type: 'Box' })).find(box => (box.props as { borderStyle?: string })?.borderStyle === 'single')
  expect(JSON.stringify(border)).not.toContain('sleeping')
  expect((await ui.find({ key: 'afkswitch-toggle' }))?.props).toMatchObject({ label: ' AFK  ■□ ' })
  await ui.press({ key: 'afkswitch-toggle' })
  expect(calls).toEqual(['back', 'back', 'back'])  // python3, python, py -3
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
