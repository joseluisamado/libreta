import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { createRouter, createMemoryHistory } from 'vue-router'
import HistoryView from '@/views/HistoryView.vue'

vi.mock('@/api/client', () => ({
  getPageHistory: vi.fn(),
}))

import { getPageHistory } from '@/api/client'
import type { HistoryEntry } from '@/api/types'

function makeEntry(overrides: Partial<HistoryEntry> = {}): HistoryEntry {
  return {
    sha: 'abc1234',
    message: 'create pages/test.md',
    author: 'Libreta',
    timestamp: '2026-05-01T10:00:00Z',
    ...overrides,
  }
}

async function createWrapper(path = 'test/page') {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/history/:path(.*)*', component: HistoryView }],
  })
  await router.push(`/history/${path}`)
  await router.isReady()

  return mount(HistoryView, {
    global: {
      plugins: [router],
    },
  })
}

describe('HistoryView', () => {
  beforeEach(() => {
    vi.resetAllMocks()
  })

  it('renders loading state initially', async () => {
    ;(getPageHistory as ReturnType<typeof vi.fn>).mockReturnValue(
      new Promise(() => {}),
    )
    const wrapper = await createWrapper()
    await nextTick()

    expect(wrapper.text()).toContain('Loading')
  })

  it('renders empty state when no history', async () => {
    ;(getPageHistory as ReturnType<typeof vi.fn>).mockResolvedValue([])
    const wrapper = await createWrapper()
    await nextTick()
    await nextTick()

    expect(wrapper.text()).toContain('No history available')
  })

  it('renders error state', async () => {
    ;(getPageHistory as ReturnType<typeof vi.fn>).mockRejectedValue(
      new Error('Server error'),
    )
    const wrapper = await createWrapper()
    await nextTick()
    await nextTick()

    expect(wrapper.text()).toContain('Server error')
  })

  it('renders history entries', async () => {
    ;(getPageHistory as ReturnType<typeof vi.fn>).mockResolvedValue([
      makeEntry({ sha: '1111111', message: 'create page' }),
      makeEntry({ sha: '2222222', message: 'update page' }),
    ])
    const wrapper = await createWrapper()
    await nextTick()
    await nextTick()

    expect(wrapper.text()).toContain('1111111')
    expect(wrapper.text()).toContain('2222222')
    expect(wrapper.text()).toContain('create page')
    expect(wrapper.text()).toContain('update page')
  })

  it('renders back link to wiki page', async () => {
    ;(getPageHistory as ReturnType<typeof vi.fn>).mockResolvedValue([])
    const wrapper = await createWrapper('some/page')
    await nextTick()
    await nextTick()

    const link = wrapper.find('a[href="/w/some/page"]')
    expect(link.exists()).toBe(true)
  })
})
