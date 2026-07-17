// Shared helpers for maintaining the lazily-loaded sidebar page tree.
//
// The tree endpoint is depth-limited: folders below the cutoff arrive as
// truncation stubs (`has_more: true, children: []`) and are filled in on demand
// via the children endpoint. These helpers keep that structure coherent across
// merges and reloads. Used by both the sources and watched stores.

import type { OtherFile, PageNode } from '@/api/types'

// Splice freshly-fetched children into the node at *parentPath*, clearing its
// truncation stub. Returns true once the parent is found. Mutates *nodes*.
//
// The incoming *children* are a depth-1 fetch, so any grandchild folder comes
// back as a fresh stub — even if the user had it expanded. Before overwriting,
// graft the parent's previously-loaded grandchildren back onto matching stubs,
// so re-fetching a folder (e.g. ensurePathExpanded on navigation) doesn't
// collapse everything below it.
export function mergeChildren(
  nodes: PageNode[],
  parentPath: string,
  children: PageNode[],
  otherFiles: OtherFile[],
): boolean {
  for (const n of nodes) {
    if (n.path === parentPath) {
      if (n.children?.length) {
        const loaded = new Map<string, PageNode>()
        indexLoaded(n.children, loaded)
        preserveLoadedChildren(children, loaded)
      }
      n.children = children
      n.has_more = false
      n.other_files = otherFiles
      return true
    }
    if (n.children?.length && mergeChildren(n.children, parentPath, children, otherFiles)) {
      return true
    }
  }
  return false
}

// Index every already-loaded subtree of a tree by path. A node counts as
// "loaded" when it isn't a truncation stub — i.e. it has real children or was
// explicitly emptied (has_more === false). Truncation stubs (has_more) carry no
// loaded data and are skipped, so they never mask a genuinely-loaded parent.
function indexLoaded(nodes: PageNode[], out: Map<string, PageNode>): void {
  for (const n of nodes) {
    if (!n.has_more && (n.children?.length || n.is_directory)) {
      out.set(n.path, n)
    }
    if (n.children?.length) indexLoaded(n.children, out)
  }
}

// Graft previously-loaded children back onto matching truncation stubs in
// *fresh*. A plain reload of the depth-limited tree returns every folder the
// user had lazily expanded past the cutoff as a bare stub, which would collapse
// them (and flicker as ensurePathExpanded refills only the active path). Mutates
// *fresh* in place.
function preserveLoadedChildren(fresh: PageNode[], prevLoaded: Map<string, PageNode>): void {
  for (const n of fresh) {
    if (n.has_more && !n.children?.length) {
      const prev = prevLoaded.get(n.path)
      if (prev && !prev.has_more) {
        n.children = prev.children
        n.has_more = false
        if (prev.other_files) n.other_files = prev.other_files
      }
    }
    if (n.children?.length) preserveLoadedChildren(n.children, prevLoaded)
  }
}

// Reconcile a freshly-fetched (depth-limited) tree against the previous one,
// preserving the expanded shape the user had built up. Returns *fresh* (mutated)
// so callers can assign it directly. Pass `undefined` for *prev* on first load.
export function mergeReloadedTree(fresh: PageNode[], prev: PageNode[] | undefined): PageNode[] {
  if (prev) {
    const loaded = new Map<string, PageNode>()
    indexLoaded(prev, loaded)
    preserveLoadedChildren(fresh, loaded)
  }
  return fresh
}

// True when *path*'s node exists in *nodes* and its children are already loaded
// (it isn't a truncation stub). Lets callers skip a redundant children fetch —
// which would otherwise reassign the tree and cause a visible re-render — when
// the folder is already populated.
export function isPathLoaded(nodes: PageNode[], path: string): boolean {
  for (const n of nodes) {
    if (n.path === path) return !n.has_more
    if (n.children?.length && path.startsWith(`${n.path}/`)) {
      return isPathLoaded(n.children, path)
    }
  }
  return false
}
