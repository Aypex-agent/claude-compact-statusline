/** Context window fill, 0 to 100, as the status line reports it. */
export type ContextPercent = number

/** The turn in progress, or the last one once it completes. */
export type Turn = {
  working: boolean
  startedAt: number
  endedAt: number
  tools: number
  lastTool: string
}

/** What the mascot is saying, where it came from, and the turn it was said on. */
export type Bubble = {
  text: string
  source: 'quip' | 'nudge' | 'capture' | 'note' | 'ask' | 'headsup' | 'explain'
  turn: number
  /** Showing the whole message (the `more` button) rather than its first lines. */
  expanded?: boolean
}

/** One message of the side chat in the clawd pane. */
export type ChatLine = { who: 'clawd' | 'you'; text: string }

declare module 'claude-code' {
  interface PluginState {
    'clawd-meter': {
      percent: ContextPercent
      history: ContextPercent[]
      turn: Turn
      bubble: Bubble
      tick: number
      seen: string[]
      chat: ChatLine[]
      chatBusy: boolean
    }
  }
}
