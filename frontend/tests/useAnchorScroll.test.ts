import { describe, it, expect, beforeEach } from 'vitest'
import {
  setPendingAnchor,
  takePendingAnchor,
  type ScrollAnchor,
} from '@/composables/useAnchorScroll'

// The geometry (captureAnchor/restoreAnchor) depends on real layout — bounding
// rects, scrollTop, scrollHeight — which jsdom doesn't implement, so it's
// exercised in the browser rather than here. What this file locks down is the
// module-scoped pending-anchor handoff and its key guard, which is where the
// stale-anchor correctness edge case lives.

function anchor(key: string): ScrollAnchor {
  return { headingIndex: 0, headingText: 'Intro', offsetPx: 10, fraction: 0.1, key }
}

describe('pending anchor handoff', () => {
  beforeEach(() => {
    // Drain any anchor a prior test left behind.
    takePendingAnchor()
  })

  it('returns null when nothing is pending', () => {
    expect(takePendingAnchor()).toBeNull()
    expect(takePendingAnchor('source/s1/foo')).toBeNull()
  })

  it('hands the anchor to a keyless consumer and clears it (single-shot)', () => {
    const a = anchor('source/s1/foo')
    setPendingAnchor(a)
    expect(takePendingAnchor()).toBe(a)
    expect(takePendingAnchor()).toBeNull()
  })

  it('gives the anchor to a consumer whose key matches, then clears it', () => {
    setPendingAnchor(anchor('source/s1/foo'))
    expect(takePendingAnchor('source/s1/foo')).not.toBeNull()
    expect(takePendingAnchor('source/s1/foo')).toBeNull()
  })

  it('leaves a mismatched-key anchor untouched so it cannot mis-scroll', () => {
    setPendingAnchor(anchor('source/s1/foo'))
    // A different page must not consume it...
    expect(takePendingAnchor('source/s1/other')).toBeNull()
    // ...and it is still available for the page it belongs to.
    expect(takePendingAnchor('source/s1/foo')).not.toBeNull()
  })

  it('setPendingAnchor(null) clears a stored anchor', () => {
    setPendingAnchor(anchor('watch/w1/foo'))
    setPendingAnchor(null)
    expect(takePendingAnchor('watch/w1/foo')).toBeNull()
  })
})
