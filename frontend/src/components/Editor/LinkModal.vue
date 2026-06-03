<script setup lang="ts">
  import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
  import PageTree from '@/components/PageTree.vue'
  import { useSourcesStore } from '@/stores/sources'
  import { getSourceChildren } from '@/api/client'
  import { displaySourceLabel } from '@/utils/sourceLabel'
  import type { PageNode } from '@/api/types'

  // The link modal is opened from the editor toolbar. It produces an
  // {href, text} pair that the editor turns into a link mark.
  //
  // Internal links are resolved against where the editor currently sits:
  //   - same source repo → a relative path to the target `.md` (portable, round-trips)
  //   - another source   → an app-route URL (`/source/<id>/...`), the only thing
  //                         that resolves across repositories in-app.
  const props = defineProps<{
    // The path of the page being edited (e.g. "guide/setup.md").
    pagePath: string
    // The id of the git source being edited, if any.
    sourceId?: string
    // Text currently selected in the editor — pre-fills the link-text field.
    initialText?: string
    // If the cursor is on an existing link, its current href.
    initialHref?: string
  }>()

  const emit = defineEmits<{
    submit: [payload: { href: string; text: string }]
    cancel: []
  }>()

  function isExternalHref(href: string): boolean {
    return /^[a-z][a-z0-9+.-]*:\/\//i.test(href) || href.startsWith('mailto:')
  }

  type Mode = 'external' | 'internal'
  // Open in whichever mode matches an existing link; default to external.
  const startExternal = !props.initialHref || isExternalHref(props.initialHref)
  const mode = ref<Mode>(startExternal ? 'external' : 'internal')

  const linkText = ref(props.initialText ?? '')
  const externalUrl = ref(startExternal ? (props.initialHref ?? '') : '')

  // ── Repo selection ────────────────────────────────────────────────────────
  const sourcesStore = useSourcesStore()

  interface RepoOption {
    id: string
    label: string
  }
  const repoOptions = computed<RepoOption[]>(() =>
    sourcesStore.sources
      .filter((s) => s.cloned)
      .map((s) => ({ id: s.id, label: displaySourceLabel(s.label) })),
  )

  // Default the picker to the source we're editing in (same-repo links are the
  // common case). When editing outside a source (a watched folder), fall back
  // to the first available source.
  const selectedRepo = ref<string>(props.sourceId ?? repoOptions.value[0]?.id ?? '')

  // Per-repo tree state. We keep our own copy (rather than reusing the sidebar
  // store's trees) so toggling folders here doesn't disturb the sidebar, and so
  // we can lazy-expand independently.
  const trees = ref<Record<string, PageNode[]>>({})
  const loadingTree = ref(false)
  const loadingPaths = ref<Set<string>>(new Set())
  const treeError = ref<string | null>(null)

  // Deep-copy the store's tree into our own state. We can't use structuredClone
  // here: the arrays come out of Pinia wrapped in Vue reactive Proxies, which
  // structuredClone rejects with "The object can not be cloned." A JSON round-
  // trip is safe — PageNode is plain serialisable data.
  function cloneNodes(nodes: PageNode[]): PageNode[] {
    return JSON.parse(JSON.stringify(nodes)) as PageNode[]
  }

  async function loadRepoTree(repo: string): Promise<void> {
    if (!repo || trees.value[repo]) return
    loadingTree.value = true
    treeError.value = null
    try {
      if (!sourcesStore.trees[repo]) await sourcesStore.loadTree(repo)
      trees.value = { ...trees.value, [repo]: cloneNodes(sourcesStore.trees[repo] ?? []) }
    } catch (e) {
      treeError.value = e instanceof Error ? e.message : String(e)
    } finally {
      loadingTree.value = false
    }
  }

  watch(
    [mode, selectedRepo],
    () => {
      if (mode.value === 'internal') void loadRepoTree(selectedRepo.value)
    },
    { immediate: true },
  )

  // Lazy-expand a stub folder (the tree endpoints are shallow). Mirrors the
  // sidebar's handleExpand, but writes into our local `trees` copy.
  function mergeChildren(nodes: PageNode[], parentPath: string, children: PageNode[]): boolean {
    for (const n of nodes) {
      if (n.path === parentPath) {
        n.children = children
        n.has_more = false
        return true
      }
      if (n.children?.length && mergeChildren(n.children, parentPath, children)) return true
    }
    return false
  }

  // The source tree endpoint is shallow; lazy-expand stub folders on demand.
  async function handleExpand(node: PageNode): Promise<void> {
    const repo = selectedRepo.value
    loadingPaths.value = new Set([...loadingPaths.value, node.path])
    try {
      const result = await getSourceChildren(repo, node.path)
      const tree = trees.value[repo]
      if (tree) {
        mergeChildren(tree, node.path, result.children)
        trees.value = { ...trees.value, [repo]: [...tree] }
      }
    } catch (e) {
      treeError.value = e instanceof Error ? e.message : String(e)
    } finally {
      const next = new Set(loadingPaths.value)
      next.delete(node.path)
      loadingPaths.value = next
    }
  }

  // ── Search filter ─────────────────────────────────────────────────────────
  const search = ref('')

  // Filter the loaded tree to nodes (and their ancestors) whose filename or
  // title matches the query. Folders with a surviving child are kept so the
  // path to a match stays visible. Empty query → the tree unchanged.
  function filterNodes(nodes: PageNode[], q: string): PageNode[] {
    const needle = q.trim().toLowerCase()
    if (!needle) return nodes
    const out: PageNode[] = []
    for (const n of nodes) {
      const selfMatch =
        n.filename.toLowerCase().includes(needle) || n.title.toLowerCase().includes(needle)
      const kids = n.children?.length ? filterNodes(n.children, q) : []
      if (selfMatch || kids.length) {
        out.push({ ...n, children: selfMatch ? n.children : kids })
      }
    }
    return out
  }

  const visibleNodes = computed<PageNode[]>(() => {
    const tree = trees.value[selectedRepo.value] ?? []
    return filterNodes(tree, search.value)
  })

  // ── Selecting a page from the tree ────────────────────────────────────────
  // The tree's nodes navigate via RouterLink; here we want a click to *select*
  // a target instead. We intercept via the onToggle/onSelect hook by wrapping
  // each leaf — PageTree emits navigation through RouterLink, so we instead
  // pass a `selectMode` flag that swaps the link for a button.
  const selectedNode = ref<PageNode | null>(null)

  function onSelectNode(node: PageNode): void {
    if (node.is_directory) return
    selectedNode.value = node
    if (!linkText.value.trim()) {
      linkText.value = node.title || node.filename.replace(/\.md$/i, '')
    }
  }

  // ── href computation ──────────────────────────────────────────────────────

  // Build a path relative to the directory containing the page being edited.
  // Both paths are repo-root-relative (e.g. "guide/setup.md", "ref/api.md").
  function relativePath(fromPagePath: string, toTargetPath: string): string {
    const fromDir = fromPagePath.split('/').slice(0, -1)
    const toParts = toTargetPath.split('/')
    // Drop the common prefix.
    let i = 0
    while (i < fromDir.length && i < toParts.length - 1 && fromDir[i] === toParts[i]) i++
    const up = fromDir.slice(i).map(() => '..')
    const down = toParts.slice(i)
    const rel = [...up, ...down].join('/')
    // A target in the same directory ("./foo.md") reads clearer than bare "foo.md".
    return up.length === 0 ? `./${rel}` : rel
  }

  function encodePath(p: string): string {
    return p.split('/').map(encodeURIComponent).join('/')
  }

  const computedHref = computed<string>(() => {
    if (mode.value === 'external') return externalUrl.value.trim()
    const node = selectedNode.value
    if (!node) return ''
    // Same source repo: a relative path to the .md file — portable and
    // round-trips byte-identically.
    if (props.sourceId && selectedRepo.value === props.sourceId) {
      return encodePath(relativePath(props.pagePath, node.path))
    }
    // Cross-repo (or linking from a non-source editor): app-route URL is the
    // only thing that resolves across repositories in-app.
    return `/source/${selectedRepo.value}/${encodePath(node.path).replace(/\.md$/i, '')}`
  })

  const canSubmit = computed<boolean>(() => computedHref.value.length > 0)

  function submit(): void {
    if (!canSubmit.value) return
    const text = linkText.value.trim() || computedHref.value
    emit('submit', { href: computedHref.value, text })
  }

  function onKeydown(e: KeyboardEvent): void {
    if (e.key === 'Escape') emit('cancel')
  }
  onMounted(() => window.addEventListener('keydown', onKeydown))
  onBeforeUnmount(() => window.removeEventListener('keydown', onKeydown))

  function onBackdropClick(e: MouseEvent): void {
    if (e.target === e.currentTarget) emit('cancel')
  }
</script>

<template>
  <div
    class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
    @click="onBackdropClick"
  >
    <div class="flex max-h-[85vh] w-full max-w-lg flex-col rounded-lg bg-white shadow-xl">
      <!-- Header -->
      <div class="flex items-center justify-between border-b border-slate-200 px-4 py-2.5">
        <span class="text-sm font-medium text-slate-700">Insert link</span>
        <button
          type="button"
          class="rounded px-2 py-1 text-xs text-slate-500 hover:bg-slate-100"
          @click="emit('cancel')"
        >
          Close
        </button>
      </div>

      <!-- Body -->
      <div class="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto px-4 py-3">
        <!-- Mode toggle -->
        <div class="inline-flex w-fit rounded-md border border-slate-200 p-0.5 text-sm">
          <button
            type="button"
            class="rounded px-3 py-1"
            :class="
              mode === 'external' ? 'bg-blue-600 text-white' : 'text-slate-600 hover:bg-slate-100'
            "
            @click="mode = 'external'"
          >
            External URL
          </button>
          <button
            type="button"
            class="rounded px-3 py-1"
            :class="
              mode === 'internal' ? 'bg-blue-600 text-white' : 'text-slate-600 hover:bg-slate-100'
            "
            @click="mode = 'internal'"
          >
            Internal document
          </button>
        </div>

        <!-- External: URL field -->
        <div v-if="mode === 'external'">
          <label class="mb-1 block text-xs font-medium text-slate-500">URL</label>
          <input
            v-model="externalUrl"
            type="url"
            placeholder="https://example.com"
            class="w-full rounded border border-slate-300 px-2 py-1.5 text-sm focus:border-blue-500 focus:outline-none"
            @keydown.enter.prevent="submit"
          />
        </div>

        <!-- Internal: repo selector + tree -->
        <template v-else>
          <div>
            <label class="mb-1 block text-xs font-medium text-slate-500">Repository</label>
            <select
              v-model="selectedRepo"
              class="w-full rounded border border-slate-300 px-2 py-1.5 text-sm focus:border-blue-500 focus:outline-none"
            >
              <option v-for="opt in repoOptions" :key="opt.id" :value="opt.id">
                {{ opt.label }}
              </option>
            </select>
          </div>

          <div>
            <label class="mb-1 block text-xs font-medium text-slate-500">Find document</label>
            <input
              v-model="search"
              type="text"
              placeholder="Filter by name…"
              class="w-full rounded border border-slate-300 px-2 py-1.5 text-sm focus:border-blue-500 focus:outline-none"
            />
          </div>

          <div
            class="min-h-[8rem] flex-1 overflow-y-auto rounded border border-slate-200 bg-slate-50 px-2 py-1.5"
          >
            <p v-if="treeError" class="text-xs text-red-600">{{ treeError }}</p>
            <p v-else-if="loadingTree" class="text-xs text-slate-400">Loading…</p>
            <p v-else-if="!visibleNodes.length" class="text-xs text-slate-400">
              No matching documents.
            </p>
            <PageTree
              v-else
              :nodes="visibleNodes"
              :on-expand="handleExpand"
              :on-select="onSelectNode"
              :selected-path="selectedNode?.path ?? null"
              :loading-paths="loadingPaths"
              :default-open-depth="search.trim() ? 99 : 1"
              select-mode
            />
          </div>

          <p v-if="selectedNode" class="text-xs text-slate-500">
            Selected: <span class="font-medium text-slate-700">{{ selectedNode.path }}</span>
          </p>
        </template>

        <!-- Link text (both modes) -->
        <div>
          <label class="mb-1 block text-xs font-medium text-slate-500">Text to show</label>
          <input
            v-model="linkText"
            type="text"
            placeholder="Link text"
            class="w-full rounded border border-slate-300 px-2 py-1.5 text-sm focus:border-blue-500 focus:outline-none"
            @keydown.enter.prevent="submit"
          />
        </div>
      </div>

      <!-- Footer -->
      <div class="flex items-center justify-end gap-2 border-t border-slate-200 px-4 py-2.5">
        <button
          type="button"
          class="rounded-md border border-slate-300 px-3 py-1 text-sm text-slate-600 hover:bg-slate-50"
          @click="emit('cancel')"
        >
          Cancel
        </button>
        <button
          type="button"
          :class="[
            'rounded-md px-3 py-1 text-sm',
            canSubmit
              ? 'bg-blue-600 text-white hover:bg-blue-700'
              : 'cursor-not-allowed bg-slate-200 text-slate-400',
          ]"
          :disabled="!canSubmit"
          @click="submit"
        >
          Insert
        </button>
      </div>
    </div>
  </div>
</template>
