<script setup lang="ts">
  import { ref, watch } from 'vue'
  import type { PageNode } from '@/api/types'

  // The recursive component takes the tree to render, plus an optional
  // ``hue`` (0–360) picked by the root instance from the *position* of the
  // first-level folder among its siblings, so consecutive first-level folders
  // get contiguous hues along the spectrum. The hue is threaded down through
  // every recursion so the colored rail rails and the subtree background tint
  // all share one hue per first-level namespace. ``depth`` counts recursion
  // levels below the first level so the rails can get stronger the deeper we go.
  //
  // openState is owned by the root instance and passed down to children so
  // localStorage is only read/written once per tree, not once per recursive level.
  const props = defineProps<{
    nodes: PageNode[]
    hue?: number | null
    depth?: number
    linkPrefix?: string
    storageKey?: string
    openState?: Record<string, boolean>
    onToggle?: (path: string, node?: PageNode) => void
    onExpand?: (node: PageNode) => Promise<void>
    loadingPaths?: Set<string>
    defaultOpenDepth?: number
    // Selection mode: instead of navigating via RouterLink, clicking a leaf
    // calls onSelect. Used by the editor's link picker.
    selectMode?: boolean
    onSelect?: (node: PageNode) => void
    selectedPath?: string | null
  }>()

  // ----- Open/closed state ---------------------------------------------------
  // Only the root instance (no openState prop) owns the state and persists it.
  // Children receive openState + onToggle from the root.
  //
  // We store only *open* paths. Default is closed. Closing a folder removes its
  // key rather than setting it to false, keeping the stored object small.

  const STORAGE_KEY = props.storageKey ?? 'libreta:tree-open'

  function loadState(): Record<string, boolean> {
    try {
      const raw = window.localStorage.getItem(STORAGE_KEY)
      if (!raw) return {}
      const parsed = JSON.parse(raw) as Record<string, boolean>
      return typeof parsed === 'object' && parsed ? parsed : {}
    } catch {
      return {}
    }
  }

  const isRoot = props.openState === undefined
  const ownState = isRoot ? ref<Record<string, boolean>>(loadState()) : null

  if (isRoot && ownState) {
    watch(
      ownState,
      (s) => {
        try {
          window.localStorage.setItem(STORAGE_KEY, JSON.stringify(s))
        } catch {
          /* ignore quota / private mode */
        }
      },
      { deep: true },
    )
  }

  function getState(): Record<string, boolean> {
    return props.openState ?? ownState?.value ?? {}
  }

  function pathDepth(path: string): number {
    if (!path) return 0
    let count = 1
    for (let i = 0; i < path.length; i++) {
      if (path[i] === '/') count++
    }
    return count
  }

  function isOpen(path: string): boolean {
    const state = getState()
    if (path in state) return state[path] !== false
    // No saved preference — use default based on depth
    const maxOpen = props.defaultOpenDepth ?? 1
    return pathDepth(path) <= maxOpen
  }

  async function toggle(path: string, node?: PageNode): Promise<void> {
    const currentlyOpen = isOpen(path)

    // Lazy-load children before expanding a stub node
    if (node?.has_more && props.onExpand && !currentlyOpen) {
      await props.onExpand(node)
    }

    if (props.onToggle) {
      props.onToggle(path, node)
      return
    }
    if (!ownState) return
    const next = { ...ownState.value }
    if (currentlyOpen) {
      next[path] = false
    } else {
      next[path] = true // force open (important after lazy load)
    }
    ownState.value = next
  }

  function childOpenState(): Record<string, boolean> {
    return props.openState ?? ownState?.value ?? {}
  }

  function childOnToggle(): (path: string, node?: PageNode) => void {
    const fn = props.onToggle ?? toggle
    return (p: string, n?: PageNode) => {
      fn(p, n)
    }
  }

  function childLoadingPaths(): Set<string> | undefined {
    return props.loadingPaths
  }

  function childOnExpand(): ((node: PageNode) => Promise<void>) | undefined {
    return props.onExpand
  }

  // ----- Namespace spectrum --------------------------------------------------
  //
  // Each first-level folder is coloured by its *position* among its siblings,
  // walking the hue wheel in even steps so consecutive folders land on
  // contiguous hues. The hue is then reused for two things per namespace:
  //   • a very subtle background wash behind the whole first-level subtree, and
  //   • the vertical rail borders, which get progressively stronger with depth.
  //
  // The root instance owns the mapping (it's the only one that sees the whole
  // list of first-level folders); children just receive the resolved hue.

  const isRootTree = props.hue == null && (props.depth ?? 0) === 0

  // Golden-angle-ish even spacing keyed off the sibling count so N folders fan
  // out across the wheel without clustering. Offset 25° nudges folder #1 away
  // from pure red into a friendlier warm tone.
  function hueForIndex(index: number, count: number): number {
    const span = 300 // leave a gap so first and last don't collide as similar reds
    const step = count > 1 ? span / count : 0
    return (25 + index * step) % 360
  }

  // Which hue this node's subtree should use. Root: derived from position.
  // Deeper: inherited from the prop.
  function hueFor(index: number): number | null {
    if (props.hue != null) return props.hue
    if (isRootTree) return hueForIndex(index, props.nodes.length)
    return null
  }

  // Very subtle wash behind a first-level subtree. Only applied once, at the
  // top of a namespace (root instance), so nested subtrees don't stack tints.
  function backgroundStyle(index: number): Record<string, string> {
    if (!isRootTree) return {}
    const h = hueForIndex(index, props.nodes.length)
    return { backgroundColor: `hsl(${h} 55% 55% / 0.06)` }
  }

  // Rail border for a child subtree. Same hue as the namespace; saturation and
  // darkness climb with depth so deeper rails read as "stronger". Falls back to
  // a neutral slate rail when there's no hue (shouldn't happen in practice).
  function railStyle(node: PageNode): Record<string, string> {
    const h = hueResolved(node)
    if (h == null) return { borderColor: 'rgb(226 232 240)' } // slate-200
    const d = childDepth() // 1-based depth of the child rail we're drawing
    const sat = Math.min(70, 45 + d * 8)
    const light = Math.max(38, 62 - d * 7)
    return { borderColor: `hsl(${h} ${sat}% ${light}%)` }
  }

  // The hue to pass to a child subtree of ``node`` and to colour its rail.
  function hueResolved(node: PageNode): number | null {
    if (props.hue != null) return props.hue
    if (isRootTree) {
      const idx = props.nodes.indexOf(node)
      return hueForIndex(idx, props.nodes.length)
    }
    return null
  }

  function childDepth(): number {
    return (props.depth ?? 0) + 1
  }

  // Build the link target for a node, accounting for pdf nodes whose viewer
  // route depends on context (main wiki vs. source vs. watched-not-supported).
  function nodeLink(node: PageNode): string {
    const prefix = props.linkPrefix ?? '/w'
    // Non-page kinds with a dedicated viewer route. The viewer slug differs
    // from the kind for a couple ("pdf"→pdf, "ebook"→ebook), so map explicitly.
    const viewerSlug = node.kind === 'pdf' ? 'pdf' : node.kind === 'ebook' ? 'ebook' : null
    if (viewerSlug) {
      const sourceMatch = /^\/source\/([^/]+)$/.exec(prefix)
      if (sourceMatch) return `/${viewerSlug}-source/${sourceMatch[1]}/${node.path}`
      if (prefix === '/w') return `/${viewerSlug}/${node.path}`
      const watchedMatch = /^\/watch\/([^/]+)$/.exec(prefix)
      if (watchedMatch) {
        return `/${viewerSlug}-watch/${watchedMatch[1]}/${node.path}`
      }
    }
    return `${prefix}/${node.path}`
  }

  // A .webloc node opens its external target in a new tab, so it renders as a
  // plain <a> rather than a RouterLink. Falls back to in-app handling when the
  // target couldn't be resolved (null).
  function isWeblink(node: PageNode): boolean {
    return node.kind === 'weblink' && !!node.target
  }
</script>

<template>
  <ul class="text-sm">
    <li
      v-for="(node, index) in nodes"
      :key="node.path"
      class="my-0.5"
      :class="{ 'rounded-sm': isRootTree }"
      :style="backgroundStyle(index)"
    >
      <div class="flex items-start gap-1">
        <button
          v-if="node.is_directory || node.children.length || node.has_more"
          type="button"
          class="shrink-0 w-4 h-4 mt-0.5 flex items-center justify-center text-slate-400 hover:text-slate-700"
          :aria-expanded="isOpen(node.path)"
          :aria-label="isOpen(node.path) ? 'Collapse folder' : 'Expand folder'"
          @click="toggle(node.path, node)"
        >
          <svg
            v-if="!loadingPaths?.has(node.path)"
            xmlns="http://www.w3.org/2000/svg"
            class="w-3 h-3 transition-transform"
            :class="{ 'rotate-90': isOpen(node.path) }"
            viewBox="0 0 12 12"
            fill="currentColor"
          >
            <path d="M4 2 L8 6 L4 10 Z" />
          </svg>
          <svg v-else class="w-3 h-3 animate-spin" viewBox="0 0 24 24" fill="none">
            <circle
              class="opacity-25"
              cx="12"
              cy="12"
              r="10"
              stroke="currentColor"
              stroke-width="4"
            />
            <path
              class="opacity-75"
              fill="currentColor"
              d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
            />
          </svg>
        </button>
        <span v-else class="shrink-0 w-4 h-4" aria-hidden="true" />
        <!-- Selection mode (link picker): clicking selects rather than navigates. -->
        <button
          v-if="selectMode"
          type="button"
          class="flex-1 truncate flex items-center gap-1 text-left"
          :class="[
            node.is_directory || node.children.length || node.has_more
              ? 'text-slate-800 font-medium hover:text-blue-600'
              : 'text-slate-700 hover:text-blue-600',
            selectedPath === node.path ? 'text-blue-700 font-semibold' : '',
          ]"
          @click="
            node.is_directory || node.children.length || node.has_more
              ? toggle(node.path, node)
              : onSelect?.(node)
          "
        >
          <span v-if="node.kind === 'pdf'" class="text-[10px] font-semibold text-rose-500 shrink-0"
            >PDF</span
          >
          <span
            v-else-if="node.kind === 'ebook'"
            class="text-[10px] font-semibold text-teal-500 shrink-0"
            >BOOK</span
          >
          <span
            v-else-if="node.kind === 'weblink'"
            class="text-[10px] font-semibold text-blue-500 shrink-0"
            >LINK</span
          >
          <span
            v-else-if="!node.is_directory && !node.children.length && !node.has_more"
            class="text-[10px] font-semibold text-sky-500 shrink-0"
            >MD</span
          >
          <span
            v-if="node.weight != null"
            class="text-[10px] font-medium text-slate-400 shrink-0 tabular-nums"
            :title="`Sidebar weight: ${node.weight}`"
            >{{ node.weight }}</span
          >
          <span class="truncate">{{ node.filename }}</span>
        </button>
        <!-- weblinks (.webloc) open their external target in a new tab; all
             other nodes navigate in-app via RouterLink. -->
        <component
          :is="isWeblink(node) ? 'a' : 'RouterLink'"
          v-else
          :to="isWeblink(node) ? undefined : nodeLink(node)"
          :href="isWeblink(node) ? node.target : undefined"
          :target="isWeblink(node) ? '_blank' : undefined"
          :rel="isWeblink(node) ? 'noopener noreferrer' : undefined"
          class="flex-1 truncate flex items-center gap-1"
          :class="
            node.is_directory || node.children.length || node.has_more
              ? 'text-slate-800 font-medium hover:text-blue-600'
              : 'text-slate-700 hover:text-blue-600'
          "
          active-class="text-blue-700 font-semibold"
        >
          <span v-if="node.kind === 'pdf'" class="text-[10px] font-semibold text-rose-500 shrink-0"
            >PDF</span
          >
          <span
            v-else-if="node.kind === 'ebook'"
            class="text-[10px] font-semibold text-teal-500 shrink-0"
            >BOOK</span
          >
          <span
            v-else-if="node.kind === 'weblink'"
            class="text-[10px] font-semibold text-blue-500 shrink-0"
            >LINK</span
          >
          <span
            v-else-if="!node.is_directory && !node.children.length && !node.has_more"
            class="text-[10px] font-semibold text-sky-500 shrink-0"
            >MD</span
          >
          <span
            v-if="node.weight != null"
            class="text-[10px] font-medium text-slate-400 shrink-0 tabular-nums"
            :title="`Sidebar weight: ${node.weight}`"
            >{{ node.weight }}</span
          >
          <span class="truncate">{{ node.filename }}</span>
        </component>
      </div>
      <PageTree
        v-if="(node.is_directory || node.children.length || node.has_more) && isOpen(node.path)"
        :nodes="node.children"
        :hue="hueResolved(node)"
        :depth="childDepth()"
        :link-prefix="linkPrefix"
        :storage-key="storageKey"
        :open-state="childOpenState()"
        :on-toggle="childOnToggle()"
        :on-expand="childOnExpand()"
        :loading-paths="childLoadingPaths()"
        :default-open-depth="props.defaultOpenDepth"
        :select-mode="selectMode"
        :on-select="onSelect"
        :selected-path="selectedPath"
        class="ml-3 border-l-2 pl-2"
        :style="railStyle(node)"
      />
    </li>
  </ul>
</template>
