import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { createRouter, createMemoryHistory } from 'vue-router'
import EditorView from '@/views/EditorView.vue'

// Mock the API client
vi.mock('@/api/client', () => ({
  getPage: vi.fn(),
  savePage: vi.fn(),
}))

import { getPage, savePage } from '@/api/client'
import type { PageRead } from '@/api/types'

function makePage(overrides: Partial<PageRead> = {}): PageRead {
  return {
    path: 'test/page',
    meta: {
      title: 'Test Page',
      created: '2026-05-01T10:00:00Z',
      updated: '2026-05-01T10:00:00Z',
      tags: [],
    },
    body: '# Test\n\nHello.',
    ...overrides,
  }
}

async function createWrapper(path = 'test/page') {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/edit/:path(.*)*', component: EditorView },
      { path: '/w/:path(.*)*', component: { template: '<div>read</div>' } },
    ],
  })
  await router.push(`/edit/${path}`)
  await router.isReady()

  return mount(EditorView, {
    global: {
      plugins: [router],
      stubs: {
        Editor: true,
        EditorToolbar: true,
      },
    },
  })
}

function findSave(wrapper: ReturnType<typeof mount>) {
  const btns = wrapper.findAll('button')
  for (const b of btns) {
    if (b.text().includes('Save')) return b!
  }
  return btns.at(-1)!
}

function findCancel(wrapper: ReturnType<typeof mount>) {
  const btns = wrapper.findAll('button')
  for (const b of btns) {
    if (b.text() === 'Cancel') return b!
  }
  return btns.at(0)!
}

describe('EditorView save', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    ;(getPage as ReturnType<typeof vi.fn>).mockResolvedValue(makePage())
    ;(savePage as ReturnType<typeof vi.fn>).mockResolvedValue(makePage())
  })

  it('renders both Cancel and Save buttons', async () => {
    const wrapper = await createWrapper()
    await nextTick()
    await nextTick()

    expect(findSave(wrapper).exists()).toBe(true)
    expect(findCancel(wrapper).exists()).toBe(true)
  })

  it('shows the editing path in the top bar', async () => {
    const wrapper = await createWrapper('foo/bar')
    await nextTick()
    await nextTick()

    expect(wrapper.text()).toContain('Editing:')
    expect(wrapper.text()).toContain('foo/bar')
  })

  it('save button is disabled when not dirty', async () => {
    const wrapper = await createWrapper()
    await nextTick()
    await nextTick()

    expect(findSave(wrapper).attributes('disabled')).toBeDefined()
  })

  it('renders loading state', async () => {
    ;(getPage as ReturnType<typeof vi.fn>).mockReturnValue(
      new Promise(() => {}), // never resolves
    )
    const wrapper = await createWrapper()
    await nextTick()

    expect(wrapper.text()).toContain('Loading')
  })

  it('renders error state', async () => {
    ;(getPage as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('Not found'))
    const wrapper = await createWrapper()
    await nextTick()
    await nextTick()

    expect(wrapper.text()).toContain('Not found')
  })
})
