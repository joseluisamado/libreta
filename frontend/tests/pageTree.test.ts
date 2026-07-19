import { describe, it, expect, beforeAll } from 'vitest'
import { mount } from '@vue/test-utils'
import PageTreeComponent from '@/components/PageTree.vue'
import {
  collectFolderPaths,
  expandOpenPaths,
  isPathLoaded,
  mergeChildren,
  mergeReloadedTree,
} from '@/utils/pageTree'
import type { PageNode } from '@/api/types'

// Minimal PageNode factory: only the fields the tree helpers touch.
function node(partial: Partial<PageNode> & { path: string }): PageNode {
  return {
    title: partial.path.split('/').pop() ?? partial.path,
    filename: `${partial.path.split('/').pop()}.md`,
    is_directory: false,
    children: [],
    ...partial,
  }
}

// Index-access helper: asserts presence so tests read cleanly under
// noUncheckedIndexedAccess.
function at<T>(arr: readonly T[], i: number): T {
  const v = arr[i]
  if (v === undefined) throw new Error(`expected element at index ${i}`)
  return v
}

describe('mergeChildren', () => {
  it('fills a stub in place and clears has_more', () => {
    const tree = [node({ path: 'a', is_directory: true, has_more: true })]
    const filled = mergeChildren(tree, 'a', [node({ path: 'a/x' })], [])
    expect(filled).toBe(true)
    expect(at(tree, 0).has_more).toBe(false)
    expect(at(tree, 0).children.map((c) => c.path)).toEqual(['a/x'])
  })

  it('recurses into nested folders', () => {
    const tree = [
      node({
        path: 'a',
        is_directory: true,
        children: [node({ path: 'a/b', is_directory: true, has_more: true })],
      }),
    ]
    expect(mergeChildren(tree, 'a/b', [node({ path: 'a/b/c' })], [])).toBe(true)
    expect(at(at(tree, 0).children, 0).children.map((c) => c.path)).toEqual(['a/b/c'])
  })

  it('returns false when the parent path is absent', () => {
    const tree = [node({ path: 'a', is_directory: true })]
    expect(mergeChildren(tree, 'nope', [], [])).toBe(false)
  })

  it('preserves already-loaded grandchildren when re-fetching a parent', () => {
    // Parent "a" already loaded, with sub-folder "a/b" expanded (loaded).
    const tree = [
      node({
        path: 'a',
        is_directory: true,
        has_more: false,
        children: [
          node({
            path: 'a/b',
            is_directory: true,
            has_more: false,
            children: [node({ path: 'a/b/leaf' })],
          }),
        ],
      }),
    ]
    // A depth-1 re-fetch of "a" returns "a/b" as a fresh stub.
    const fresh = [node({ path: 'a/b', is_directory: true, has_more: true })]
    mergeChildren(tree, 'a', fresh, [])
    const b = at(at(tree, 0).children, 0)
    expect(b.path).toBe('a/b')
    expect(b.has_more).toBe(false)
    expect(b.children.map((c) => c.path)).toEqual(['a/b/leaf'])
  })
})

describe('isPathLoaded', () => {
  const tree = [
    node({
      path: 'a',
      is_directory: true,
      has_more: false,
      children: [
        node({ path: 'a/loaded', is_directory: true, has_more: false, children: [] }),
        node({ path: 'a/stub', is_directory: true, has_more: true }),
      ],
    }),
  ]

  it('is true for a loaded folder', () => {
    expect(isPathLoaded(tree, 'a')).toBe(true)
    expect(isPathLoaded(tree, 'a/loaded')).toBe(true)
  })

  it('is false for a truncation stub', () => {
    expect(isPathLoaded(tree, 'a/stub')).toBe(false)
  })

  it('is false for an unknown path', () => {
    expect(isPathLoaded(tree, 'a/missing')).toBe(false)
    expect(isPathLoaded(tree, 'nope')).toBe(false)
  })
})

describe('collectFolderPaths', () => {
  it('collects folder paths (children or stub), skipping leaves', () => {
    const tree = [
      node({
        path: 'a',
        is_directory: true,
        children: [
          node({ path: 'a/b', is_directory: true, children: [node({ path: 'a/b/leaf' })] }),
          node({ path: 'a/stub', is_directory: true, has_more: true }),
          node({ path: 'a/file' }),
        ],
      }),
    ]
    const out = new Set<string>()
    collectFolderPaths(tree, out)
    expect([...out].sort()).toEqual(['a', 'a/b', 'a/stub'])
  })
})

describe('expandOpenPaths', () => {
  it('is a no-op when nothing is open', async () => {
    const fetched: string[] = []
    await expandOpenPaths(
      [],
      () => [node({ path: 'a', is_directory: true, has_more: true })],
      async (p) => void fetched.push(p),
    )
    expect(fetched).toEqual([])
  })

  it('fetches an open deep folder present only as a stub', async () => {
    const tree = [
      node({
        path: 'a',
        is_directory: true,
        children: [node({ path: 'a/b', is_directory: true, has_more: true })],
      }),
    ]
    const fetched: string[] = []
    await expandOpenPaths(
      ['a/b'],
      () => tree,
      async (p) => {
        fetched.push(p)
        // Simulate the fetch clearing the stub so it isn't re-fetched.
        at(at(tree, 0).children, 0).has_more = false
      },
    )
    expect(fetched).toEqual(['a/b'])
  })

  it('walks shallow→deep, fetching grandchildren revealed by the parent', async () => {
    // Only "a" is present initially; fetching it reveals stub "a/b", also open.
    const tree = [node({ path: 'a', is_directory: true, has_more: true })]
    const fetched: string[] = []
    await expandOpenPaths(
      ['a/b', 'a'],
      () => tree,
      async (p) => {
        fetched.push(p)
        if (p === 'a') {
          at(tree, 0).has_more = false
          at(tree, 0).children = [node({ path: 'a/b', is_directory: true, has_more: true })]
        } else if (p === 'a/b') {
          at(at(tree, 0).children, 0).has_more = false
        }
      },
    )
    // Parent first, then the grandchild it revealed.
    expect(fetched).toEqual(['a', 'a/b'])
  })

  it('skips folders whose children are already loaded', async () => {
    const tree = [node({ path: 'a', is_directory: true, has_more: false, children: [] })]
    const fetched: string[] = []
    await expandOpenPaths(
      ['a'],
      () => tree,
      async (p) => void fetched.push(p),
    )
    // "a" is a folder but not a stub; collectFolderPaths only reports it when it
    // has children or has_more. With neither, it's absent → nothing to fetch.
    expect(fetched).toEqual([])
  })
})

describe('mergeReloadedTree', () => {
  it('grafts previously-loaded children onto a fresh truncation stub', () => {
    // Previous tree had folder "a/deep" expanded (loaded children).
    const prev = [
      node({
        path: 'a',
        is_directory: true,
        children: [
          node({
            path: 'a/deep',
            is_directory: true,
            has_more: false,
            children: [node({ path: 'a/deep/leaf' })],
          }),
        ],
      }),
    ]
    // A fresh depth-limited reload returns "a/deep" as a bare stub.
    const fresh = [
      node({
        path: 'a',
        is_directory: true,
        children: [node({ path: 'a/deep', is_directory: true, has_more: true })],
      }),
    ]
    const merged = mergeReloadedTree(fresh, prev)
    const deep = at(at(merged, 0).children, 0)
    expect(deep.has_more).toBe(false)
    expect(deep.children.map((c) => c.path)).toEqual(['a/deep/leaf'])
  })

  it('leaves a stub collapsed when it was never loaded before', () => {
    const prev = [node({ path: 'a', is_directory: true, has_more: true })]
    const fresh = [node({ path: 'a', is_directory: true, has_more: true })]
    const merged = mergeReloadedTree(fresh, prev)
    expect(at(merged, 0).has_more).toBe(true)
    expect(at(merged, 0).children).toEqual([])
  })

  it('does not resurrect a folder that was deleted upstream', () => {
    // "gone" existed (loaded) before but is absent from the fresh tree.
    const prev = [
      node({
        path: 'gone',
        is_directory: true,
        has_more: false,
        children: [node({ path: 'gone/x' })],
      }),
    ]
    const fresh = [node({ path: 'kept', is_directory: true, has_more: true })]
    const merged = mergeReloadedTree(fresh, prev)
    expect(merged.map((n) => n.path)).toEqual(['kept'])
  })

  it('is a no-op on first load (no previous tree)', () => {
    const fresh = [node({ path: 'a', is_directory: true, has_more: true })]
    expect(mergeReloadedTree(fresh, undefined)).toBe(fresh)
    expect(at(fresh, 0).has_more).toBe(true)
  })

  it('preserves a deeply-nested expanded shape across reload', () => {
    const prev = [
      node({
        path: 'a',
        is_directory: true,
        children: [
          node({
            path: 'a/b',
            is_directory: true,
            has_more: false,
            children: [
              node({
                path: 'a/b/c',
                is_directory: true,
                has_more: false,
                children: [node({ path: 'a/b/c/leaf' })],
              }),
            ],
          }),
        ],
      }),
    ]
    // Fresh tree truncates at "a/b".
    const fresh = [
      node({
        path: 'a',
        is_directory: true,
        children: [node({ path: 'a/b', is_directory: true, has_more: true })],
      }),
    ]
    const merged = mergeReloadedTree(fresh, prev)
    const c = at(at(at(merged, 0).children, 0).children, 0)
    expect(c.path).toBe('a/b/c')
    expect(c.children.map((n) => n.path)).toEqual(['a/b/c/leaf'])
  })
})

// PageTree owns open/closed state in localStorage; jsdom here has none.
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

function mountTree(nodes: PageNode[]) {
  return mount(PageTreeComponent, {
    props: { nodes },
    global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } },
  })
}

// The three folder states the sidebar must distinguish:
//   populated  → caret + normal (slate-800) label
//   stub       → caret (unknown contents, has_more)
//   empty      → no caret + dimmed (slate-400) label
describe('PageTree — empty folders', () => {
  it('renders a confirmed-empty folder dimmed and caret-less', () => {
    const w = mountTree([node({ path: 'empty', is_directory: true })])
    // No expand caret: the row uses the leaf spacer instead.
    expect(w.find('button[aria-label]').exists()).toBe(false)
    expect(w.find('a').classes()).toContain('text-slate-400')
  })

  it('keeps the caret and normal label for a populated folder', () => {
    const w = mountTree([
      node({ path: 'full', is_directory: true, children: [node({ path: 'full/a' })] }),
    ])
    expect(w.find('button[aria-label]').exists()).toBe(true)
    const label = at(w.findAll('a'), 0)
    expect(label.classes()).toContain('text-slate-800')
    expect(label.classes()).not.toContain('text-slate-400')
  })

  it('keeps the caret for a truncation stub (unknown contents)', () => {
    const w = mountTree([node({ path: 'stub', is_directory: true, has_more: true })])
    expect(w.find('button[aria-label]').exists()).toBe(true)
    expect(w.find('a').classes()).not.toContain('text-slate-400')
  })

  it('does not render a child subtree under an empty folder', () => {
    const w = mountTree([node({ path: 'empty', is_directory: true })])
    // The only <ul> is the root list; no nested rail/list for the empty dir.
    expect(w.findAll('ul')).toHaveLength(1)
  })
})
