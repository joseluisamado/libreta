<script setup lang="ts">
  import { ref, watch } from 'vue'
  import type { PageNode } from '@/api/types'

  // The recursive component takes the tree to render, plus an optional
  // ``rootNamespace`` (the top-level path segment, e.g. "devel" or "hardware").
  // It's set by the parent on the second-and-deeper recursions so the colored
  // border rail is consistent across all nested levels of one namespace.
  //
  // openState is owned by the root instance and passed down to children so
  // localStorage is only read/written once per tree, not once per recursive level.
  const props = defineProps<{
    nodes: PageNode[]
    rootNamespace?: string | null
    linkPrefix?: string
    storageKey?: string
    openState?: Record<string, boolean>
    onToggle?: (path: string) => void
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

  function isOpen(path: string): boolean {
    return getState()[path] !== false
  }

  function toggle(path: string): void {
    if (props.onToggle) {
      props.onToggle(path)
      return
    }
    if (!ownState) return
    const next = { ...ownState.value }
    if (isOpen(path)) {
      next[path] = false  // record the closure
    } else {
      delete next[path]   // back to default-open; remove the entry
    }
    ownState.value = next
  }

  function childOpenState(): Record<string, boolean> {
    return props.openState ?? ownState?.value ?? {}
  }

  function childOnToggle(): (path: string) => void {
    return props.onToggle ?? toggle
  }

  // ----- Namespace palette ---------------------------------------------------

  // Curated palette: each entry is a Tailwind border colour readable on white,
  // distinct in hue, intentionally muted so the sidebar doesn't shout. The
  // exact list is small on purpose — fewer colours = easier to remember which
  // one means what after a few sessions.
  const NAMESPACE_PALETTE = [
    'border-sky-300',
    'border-emerald-300',
    'border-amber-400',
    'border-rose-300',
    'border-violet-300',
    'border-teal-300',
    'border-orange-300',
    'border-indigo-300',
  ] as const

  // Tiny stable hash → palette index. Same namespace always gets same colour.
  function hashNamespace(ns: string): number {
    let h = 0
    for (let i = 0; i < ns.length; i++) {
      h = (h * 31 + ns.charCodeAt(i)) >>> 0
    }
    return h % NAMESPACE_PALETTE.length
  }

  function railClass(node: PageNode): string {
    // The first recursion (top of a namespace) gets coloured by the node's
    // own first path segment; deeper recursions inherit the rootNamespace
    // passed in by the parent.
    const ns = props.rootNamespace ?? node.path.split('/')[0] ?? ''
    if (!ns) return 'border-slate-200'
    return NAMESPACE_PALETTE[hashNamespace(ns)] ?? 'border-slate-200'
  }

  // What we pass to the child <PageTree>: keep the rootNamespace if we already
  // have one (deep recursion), otherwise seed it from the current node's first
  // path segment (entering a namespace from the root).
  function childRootNamespace(node: PageNode): string {
    return props.rootNamespace ?? node.path.split('/')[0] ?? ''
  }
</script>

<template>
  <ul class="text-sm">
    <li v-for="node in nodes" :key="node.path" class="my-0.5">
      <div class="flex items-start gap-1">
        <button
          v-if="node.children.length"
          type="button"
          class="shrink-0 w-4 h-4 mt-0.5 flex items-center justify-center text-slate-400 hover:text-slate-700"
          :aria-expanded="isOpen(node.path)"
          :aria-label="isOpen(node.path) ? 'Collapse folder' : 'Expand folder'"
          @click="toggle(node.path)"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            class="w-3 h-3 transition-transform"
            :class="{ 'rotate-90': isOpen(node.path) }"
            viewBox="0 0 12 12"
            fill="currentColor"
          >
            <path d="M4 2 L8 6 L4 10 Z" />
          </svg>
        </button>
        <span v-else class="shrink-0 w-4 h-4" aria-hidden="true" />
        <RouterLink
          :to="`${linkPrefix ?? '/w'}/${node.path}`"
          class="flex-1 truncate"
          :class="
            node.children.length
              ? 'text-slate-800 font-medium hover:text-blue-600'
              : 'text-slate-700 hover:text-blue-600'
          "
          active-class="text-blue-700 font-semibold"
        >
          {{ node.title }}
        </RouterLink>
      </div>
      <PageTree
        v-if="node.children.length && isOpen(node.path)"
        :nodes="node.children"
        :root-namespace="childRootNamespace(node)"
        :link-prefix="linkPrefix"
        :storage-key="storageKey"
        :open-state="childOpenState()"
        :on-toggle="childOnToggle()"
        class="ml-3 border-l-2 pl-2"
        :class="railClass(node)"
      />
    </li>
  </ul>
</template>
