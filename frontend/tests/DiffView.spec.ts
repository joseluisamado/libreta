import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { createRouter, createMemoryHistory } from 'vue-router'
import DiffView from '@/views/DiffView.vue'

vi.mock('@/api/client', () => ({
  getPageDiff: vi.fn(),
}))

import { getPageDiff } from '@/api/client'

async function createWrapper(path = 'recipes/tiramisu', a = '1111111', b = '2222222') {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/diff/:path(.*)*', component: DiffView }],
  })
  await router.push({ path: `/diff/${path}`, query: { a, b } })
  await router.isReady()

  return mount(DiffView, { global: { plugins: [router] } })
}

describe('DiffView', () => {
  beforeEach(() => {
    vi.resetAllMocks()
  })

  it('renders an empty-state when patch is empty', async () => {
    ;(getPageDiff as ReturnType<typeof vi.fn>).mockResolvedValue({
      old_sha: '1111111',
      new_sha: '2222222',
      old_path: 'pages/recipes/tiramisu.md',
      new_path: 'pages/recipes/tiramisu.md',
      patch: '',
    })
    const wrapper = await createWrapper()
    await nextTick()
    await nextTick()
    expect(wrapper.text()).toContain('No differences')
  })

  it('renders added and removed lines with classes', async () => {
    ;(getPageDiff as ReturnType<typeof vi.fn>).mockResolvedValue({
      old_sha: '1111111',
      new_sha: '2222222',
      old_path: 'pages/recipes/tiramisu.md',
      new_path: 'pages/recipes/tiramisu.md',
      patch: [
        '--- a/pages/recipes/tiramisu.md',
        '+++ b/pages/recipes/tiramisu.md',
        '@@ -1,2 +1,2 @@',
        '-old line',
        '+new line',
        ' context',
      ].join('\n'),
    })
    const wrapper = await createWrapper()
    await nextTick()
    await nextTick()

    const html = wrapper.html()
    expect(html).toContain('bg-green-50')
    expect(html).toContain('bg-red-50')
    expect(html).toContain('bg-blue-50')
    expect(wrapper.text()).toContain('+new line')
    expect(wrapper.text()).toContain('-old line')
  })

  it('renders error when revisions are missing', async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/diff/:path(.*)*', component: DiffView }],
    })
    await router.push('/diff/foo')
    await router.isReady()
    const wrapper = mount(DiffView, { global: { plugins: [router] } })
    await nextTick()
    await nextTick()
    expect(wrapper.text()).toContain('Missing revision parameters')
  })

  it('renders error when API fails', async () => {
    ;(getPageDiff as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('boom'))
    const wrapper = await createWrapper()
    await nextTick()
    await nextTick()
    expect(wrapper.text()).toContain('boom')
  })
})
