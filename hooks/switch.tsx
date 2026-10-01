import type { EngineInterface, Register } from 'claude-code'

type Status = 'available' | 'afk'
type Cache = {
  initialized: boolean
  lastGood: Status | null
  readable: boolean
  pending: boolean
  failed: boolean
  revision: number
}

const readStatus = async ($: EngineInterface): Promise<Status | null> => {
  const override = await $.env.get('AFKSWITCH_STATE_DIR')
  const home = override ? undefined : (await $.env.get('HOME')) || (await $.env.get('USERPROFILE'))
  const directory = override || (home ? `${home}/.afkswitch` : undefined)
  if (!directory) return null

  try {
    const text = await $.fs.read(`${directory.replace(/[\\/]+$/, '')}/state.json`)
    const value: unknown = JSON.parse(text.replace(/^\uFEFF/, ''))
    if (value === null || typeof value !== 'object' || Array.isArray(value)) return null
    const state = value as { version?: unknown; status?: unknown }
    return (state.version === 1 || state.version === 2) &&
      (state.status === 'afk' || state.status === 'available') ? state.status : null
  } catch {
    // Missing, unreadable, malformed and future state are neutral, never present.
    return null
  }
}

const refresh = async ($: EngineInterface, cache: Cache): Promise<Status | null> => {
  const request = ++cache.revision
  try {
    const status = await readStatus($)
    if (request === cache.revision) {
      cache.initialized = true
      cache.readable = status !== null
      if (status !== null) cache.lastGood = status
    }
    return status
  } catch (error) {
    if (request === cache.revision) {
      cache.initialized = false
      cache.readable = false
    }
    throw error
  }
}

// A drawing cache only: the helper used by the skills remains the single writer.
export const register: Register = on => {
  const cache: Cache = {
    initialized: false, lastGood: null, readable: false,
    pending: false, failed: false, revision: 0,
  }

  on('session.start', async ($, e, next) => {
    await refresh($, cache)
    cache.failed = false
    $.ui.invalidate('ui.render')
    return next(e)
  }).catch(($, e, next) => next(e))

  on('prompt.submit', async ($, e, next) => {
    await refresh($, cache)
    $.ui.invalidate('ui.render')
    return next(e)
  }).catch(($, e, next) => next(e))

  on('turn.complete', async ($, e, next) => {
    await refresh($, cache)
    cache.failed = false
    $.ui.invalidate('ui.render')
    return next(e)
  }).catch(($, e, next) => next(e))

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    // This release advertises the terminal only; remote paint is not verified.
    if (e.surface !== 'terminal') return next(e)
    if (!cache.initialized) await refresh($, cache)

    const status = cache.readable ? cache.lastGood : null
    const cells = status === 'afk' ? '■□' : status === 'available' ? '□■' : '□□'
    // Capture explicit intent from this drawing; never toggle a later disk value.
    const intended: Status | null = status === 'available' ? 'afk' : status === 'afk' ? 'available' : null
    const { Box, Text, Button } = $.ui.resolve(e)
    const original = await next(e)

    const press = async () => {
      // The synchronous guard also covers two presses of an old drawing.
      if (cache.pending || intended === null) return
      cache.pending = true
      cache.failed = false
      try {
        $.ui.invalidate('ui.render')
        const current = await refresh($, cache)
        if (current === intended) return
        // Do not act from a file we cannot currently understand.
        if (current === null) {
          cache.failed = true
          return
        }
        const result = intended === 'afk'
          ? await $.command.run({ command: 'afkswitch:afk' })
          : await $.command.run({ command: 'afkswitch:back' })
        const confirmed = await refresh($, cache)
        cache.failed = (result.exitCode !== undefined && result.exitCode !== 0) || confirmed !== intended
      } catch {
        cache.failed = true
        // Show disk truth even if command dispatch or completion failed.
        try { await refresh($, cache) } catch { cache.readable = false }
      } finally {
        cache.pending = false
        // A redraw error must not escape a button handler into the host.
        try { $.ui.invalidate('ui.render') } catch { /* text commands still work */ }
      }
    }

    return (
      <Box flexDirection="column">
        {original}
        <Box flexDirection="row" alignSelf="flex-start" borderStyle="single" paddingX={1} flexShrink={0}>
          <Text color={status === 'afk' ? '#F28C28' : undefined} dimColor={status !== 'afk'}>AFK</Text>
          <Text>{'  '}</Text>
          {cache.pending || intended === null
            ? <Text dimColor={status !== 'afk'}>{cells}</Text>
            : <Button key="afkswitch-toggle" label={cells} plain onPress={press} />}
          {cache.failed ? <Text color="#F28C28">!</Text> : null}
        </Box>
      </Box>
    )
  }).catch(($, e, next) => next(e))
}
