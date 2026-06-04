import { describe, it, expect, beforeAll } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import DirListing from '@/components/DirListing.vue'
import type { OtherFile, PageNode } from '@/api/types'

// jsdom in this setup doesn't expose a working localStorage; DirListing reads
// it for the view-mode/size prefs. A minimal in-memory shim is enough.
beforeAll(() => {
  const store = new Map<string, string>()
  Object.defineProperty(globalThis, 'localStorage', {
    configurable: true,
    value: {
      getItem: (k: string) => store.get(k) ?? null,
      setItem: (k: string, v: string) => void store.set(k, v),
      removeItem: (k: string) => void store.delete(k),
      clear: () => store.clear(),
    },
  })
})

function makeChildren(n: number): PageNode[] {
  return Array.from({ length: n }, (_, i) => ({
    path: `f${i}`,
    title: `f${i}`,
    filename: `f${i}.md`,
    is_directory: false,
    children: [],
  }))
}

function makeOther(n: number): OtherFile[] {
  // Images are now first-class children, so "other files" are non-previewable
  // kinds (binaries, etc.).
  return Array.from({ length: n }, (_, i) => ({
    name: `o${i}.zip`,
    path: `o${i}.zip`,
    kind: 'binary' as const,
  }))
}

function mountListing(children: PageNode[], otherFiles: OtherFile[] = []) {
  return mount(DirListing, {
    props: {
      children,
      basePath: '',
      getChildUrl: (p: string) => `/source/s/${p}`,
      otherFiles,
      getOtherFileUrl: (p: string) => `/api/v1/sources/s/assets/${p}`,
    },
    global: {
      stubs: { RouterLink: { template: '<a><slot /></a>' }, PreviewTile: true },
    },
  })
}

const PAGER = 'nav[aria-label="Folder pagination"]'

describe('DirListing pagination (50 per page, combined + alphabetical)', () => {
  it('shows no pager when children + other files total ≤ 50', () => {
    const w = mountListing(makeChildren(30), makeOther(20))
    expect(w.find(PAGER).exists()).toBe(false)
    expect(w.findAll('li').length).toBe(50)
  })

  it('counts both sections against one budget; 51 total ⇒ 2 pages', () => {
    const w = mountListing(makeChildren(40), makeOther(11))
    const pager = w.find(PAGER)
    expect(pager.exists()).toBe(true)
    expect(pager.text()).toContain('Page 1 of 2')
    // Page 1: all 40 children + first 10 other files = 50 rows.
    expect(w.findAll('li').length).toBe(50)
  })

  it('spills the remainder onto page 2 across the section boundary', async () => {
    const w = mountListing(makeChildren(40), makeOther(11))
    await w.findAll(`${PAGER} button`)[1]!.trigger('click')
    await nextTick()
    expect(w.find(PAGER).text()).toContain('Page 2 of 2')
    // Page 2: the 11th other file only (40 children + 10 others filled page 1).
    expect(w.findAll('li').length).toBe(1)
  })

  it('shows only one pager (single shared budget)', () => {
    const w = mountListing(makeChildren(60), makeOther(60))
    expect(w.findAll(PAGER).length).toBe(1)
    expect(w.find(PAGER).text()).toContain('Page 1 of 3') // 120 / 50 → 3
  })

  it('lists previewable children (image/text/video) in-folder with badges', () => {
    const mk = (filename: string, kind?: PageNode['kind']): PageNode => ({
      path: filename,
      title: filename,
      filename,
      is_directory: false,
      children: [],
      kind,
    })
    const children: PageNode[] = [
      mk('a.md'),
      mk('pic.png', 'image'),
      mk('notes.txt', 'text'),
      mk('clip.mp4', 'video'),
    ]
    const w = mountListing(children)
    const rows = w.findAll('li').map((li) => li.text())
    expect(rows.some((t) => t.includes('pic.png') && t.includes('IMG'))).toBe(true)
    expect(rows.some((t) => t.includes('notes.txt') && t.includes('TXT'))).toBe(true)
    expect(rows.some((t) => t.includes('clip.mp4') && t.includes('VID'))).toBe(true)
  })

  it('renders a .webloc child as an external new-tab link to its target', () => {
    const children: PageNode[] = [
      {
        path: 'site.webloc',
        title: 'site',
        filename: 'site.webloc',
        is_directory: false,
        children: [],
        kind: 'weblink',
        target: 'https://example.com',
      },
    ]
    const w = mountListing(children)
    const rows = w.findAll('li').map((li) => li.text())
    expect(rows.some((t) => t.includes('site.webloc') && t.includes('LINK'))).toBe(true)
    // A real <a> to the external target, opening in a new tab (not a stubbed
    // RouterLink — those carry no href here).
    const ext = w.find('a[href="https://example.com"]')
    expect(ext.exists()).toBe(true)
    expect(ext.attributes('target')).toBe('_blank')
    expect(ext.attributes('rel')).toContain('noopener')
  })

  it('sorts children alphabetically (case-insensitive, numeric)', () => {
    const children: PageNode[] = ['banana.md', 'Apple.md', 'cherry.md'].map((f) => ({
      path: f,
      title: f,
      filename: f,
      is_directory: false,
      children: [],
    }))
    const w = mountListing(children)
    const text = w.findAll('li').map((li) => li.text())
    expect(text[0]).toContain('Apple.md')
    expect(text[1]).toContain('banana.md')
    expect(text[2]).toContain('cherry.md')
  })
})
