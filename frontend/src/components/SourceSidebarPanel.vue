<script setup lang="ts">
  import { computed, ref, watch } from 'vue'
  import { useSourcesStore } from '@/stores/sources'
  import PageTree from '@/components/PageTree.vue'
  import PendingChangesPopover from '@/components/PendingChangesPopover.vue'
  import type { GitSource, PageNode, PendingCommit } from '@/api/types'
  import { getPendingCommits } from '@/api/client'
  import { displaySourceLabel } from '@/utils/sourceLabel'

  const props = defineProps<{ source: GitSource }>()

  const store = useSourcesStore()

  function loadStoredExpanded(): boolean {
    try {
      const raw = window.localStorage.getItem(`libreta:source-expanded-${props.source.id}`)
      if (raw === null) return true
      return raw === 'true'
    } catch {
      return true
    }
  }

  const expanded = ref(loadStoredExpanded())
  const syncing = ref(false)
  const syncMessage = ref<string | null>(null)
  const loadingPaths = ref<Set<string>>(new Set())

  // Load the tree, then re-expand any folders the user had open past the
  // shallow fetch depth. The tree endpoint returns only depth=2, so deep
  // folders arrive as truncation stubs; without this, a folder marked open in
  // localStorage renders nothing (its children were never fetched) and — since
  // isOpen() returns true without going through the toggle/expand path — no
  // expand event fires to fill it. Fetch those children up front instead.
  async function loadTreeAndRestore(): Promise<void> {
    await store.loadTree(props.source.id)
    await store.expandOpenPaths(
      props.source.id,
      readOpenPaths(`libreta:tree-source-${props.source.id}`),
    )
  }

  watch(
    expanded,
    (v) => {
      if (v && !store.trees[props.source.id]) {
        loadTreeAndRestore()
      }
    },
    { immediate: true },
  )

  // A freshly-added source is cloned in the background. The first tree fetch
  // (at mount) hits a still-empty working tree and caches []; the `!trees[id]`
  // guard above then prevents any reload, so the sidebar stays empty until a
  // full page refresh. Watch the `cloned` flag — flipped false→true by the
  // App-level sources poll once the clone lands — and reload the tree then, so
  // content appears without a manual refresh.
  watch(
    () => props.source.cloned,
    (isCloned, was) => {
      if (isCloned && !was && expanded.value) {
        loadTreeAndRestore()
      }
    },
  )

  watch(expanded, (v) => {
    try {
      window.localStorage.setItem(`libreta:source-expanded-${props.source.id}`, String(v))
    } catch {
      // localStorage full or disabled — ignore
    }
  })

  async function handleExpand(node: PageNode): Promise<void> {
    loadingPaths.value = new Set([...loadingPaths.value, node.path])
    try {
      await store.loadTreeChildren(props.source.id, node.path)
    } finally {
      const next = new Set(loadingPaths.value)
      next.delete(node.path)
      loadingPaths.value = next
    }
  }

  function readOpenPaths(storageKey: string): string[] {
    try {
      const raw = window.localStorage.getItem(storageKey)
      if (!raw) return []
      const parsed = JSON.parse(raw) as Record<string, boolean>
      if (typeof parsed !== 'object' || !parsed) return []
      return Object.entries(parsed)
        .filter(([, open]) => open !== false)
        .map(([path]) => path)
    } catch {
      return []
    }
  }

  async function handleSync(): Promise<void> {
    syncing.value = true
    syncMessage.value = null
    try {
      await store.syncSource(props.source.id)
      await new Promise((r) => setTimeout(r, 1500))
      await store.loadSources()
      if (expanded.value) {
        // Refetch the shallow tree, then re-expand the folders the user had
        // open past the fetch depth so new files added upstream appear and
        // deep-open folders don't collapse. Same restore as the initial load.
        await loadTreeAndRestore()
      }
      if (props.source.last_sync_error) {
        syncMessage.value = 'Sync failed'
      } else {
        syncMessage.value = 'Synced'
      }
    } finally {
      syncing.value = false
      setTimeout(() => {
        syncMessage.value = null
      }, 3000)
    }
  }

  function statusDot(src: GitSource): string {
    if (src.cloning) return 'bg-sky-400 animate-pulse'
    if (!src.cloned) return 'bg-slate-300'
    if (src.last_sync_error) return 'bg-red-500'
    if (src.pending_count > 0) return 'bg-amber-400'
    return 'bg-emerald-400'
  }

  function statusTitle(src: GitSource): string {
    if (src.cloning) return 'Cloning… (large repos can take a few minutes)'
    if (!src.cloned)
      return src.last_sync_error ? `Clone failed: ${src.last_sync_error}` : 'Not cloned yet'
    if (src.last_sync_error) return `Sync error: ${src.last_sync_error}`
    if (src.pending_count > 0) {
      return `${src.pending_count} local commit(s) not yet pushed`
    }
    if (src.last_synced_at) return `Last synced: ${new Date(src.last_synced_at).toLocaleString()}`
    return 'Never synced'
  }

  // Pending-changes popover
  const pendingOpen = ref(false)
  const pendingCommits = ref<PendingCommit[]>([])
  const pendingLoading = ref(false)
  const pendingError = ref<string | null>(null)
  const hasPending = computed(() => props.source.pending_count > 0)

  async function togglePendingPopover(): Promise<void> {
    if (pendingOpen.value) {
      pendingOpen.value = false
      return
    }
    pendingOpen.value = true
    pendingLoading.value = true
    pendingError.value = null
    try {
      pendingCommits.value = await getPendingCommits(props.source.id)
    } catch (e) {
      pendingError.value = e instanceof Error ? e.message : String(e)
    } finally {
      pendingLoading.value = false
    }
  }
</script>

<template>
  <div class="mb-1">
    <!-- Header row -->
    <div class="flex items-center gap-1">
      <button
        type="button"
        class="shrink-0 w-4 h-4 flex items-center justify-center text-slate-400 hover:text-slate-700"
        :aria-expanded="expanded"
        @click="expanded = !expanded"
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          class="w-3 h-3 transition-transform"
          :class="{ 'rotate-90': expanded }"
          viewBox="0 0 12 12"
          fill="currentColor"
        >
          <path d="M4 2 L8 6 L4 10 Z" />
        </svg>
      </button>

      <!-- Sync status dot -->
      <span
        class="shrink-0 w-2 h-2 rounded-full"
        :class="statusDot(source)"
        :title="statusTitle(source)"
      />

      <button
        type="button"
        class="flex-1 min-w-0 truncate text-left text-sm font-medium text-slate-700 hover:text-blue-600"
        :title="`Open ${displaySourceLabel(source.label)}`"
        @click="expanded = !expanded"
      >
        {{ displaySourceLabel(source.label) }}
      </button>

      <!-- Pending-changes link: only shown when local is ahead of remote. -->
      <button
        v-if="hasPending"
        type="button"
        class="shrink-0 text-[11px] font-medium px-1.5 py-0.5 rounded text-amber-700 bg-amber-100 hover:bg-amber-200 whitespace-nowrap"
        :title="`${source.pending_count} unpushed commit(s) — click to view`"
        @click.prevent="togglePendingPopover"
      >
        ↑{{ source.pending_count }}
      </button>

      <!-- Inline sync status -->
      <span
        v-if="syncing || syncMessage"
        class="text-[10px] whitespace-nowrap"
        :class="syncMessage === 'Synced' ? 'text-emerald-500' : 'text-blue-400'"
      >
        {{ syncing ? 'push & pull…' : syncMessage!.toLowerCase() }}
      </span>
      <span
        v-else-if="source.last_sync_error"
        class="text-[10px] whitespace-nowrap text-amber-500"
        :title="source.last_sync_error"
      >
        error
      </span>

      <!-- Sync button -->
      <button
        type="button"
        class="shrink-0 text-slate-400 hover:text-blue-600 p-0.5 rounded"
        title="Push & pull"
        :disabled="syncing"
        @click.prevent="handleSync"
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          class="w-3.5 h-3.5"
          :class="{ 'animate-spin': syncing }"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          stroke-linecap="round"
          stroke-linejoin="round"
        >
          <polyline points="23 4 23 10 17 10" />
          <polyline points="1 20 1 14 7 14" />
          <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
        </svg>
      </button>
    </div>

    <!-- Pending-changes popover -->
    <PendingChangesPopover
      v-if="pendingOpen"
      :source-id="source.id"
      :commits="pendingCommits"
      :loading="pendingLoading"
      :error="pendingError"
      @close="pendingOpen = false"
    />

    <!-- Tree -->
    <PageTree
      v-if="expanded && store.trees[source.id]"
      :nodes="store.trees[source.id]!"
      :link-prefix="`/source/${source.id}`"
      :storage-key="`libreta:tree-source-${source.id}`"
      :on-expand="handleExpand"
      :loading-paths="loadingPaths"
      :default-open-depth="1"
      class="ml-3 border-l-2 border-slate-200 pl-2 mt-0.5"
    />
  </div>
</template>
