import { describe, it, expect } from 'vitest'
import { mergeChildren, mergeReloadedTree } from '@/utils/pageTree'
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
