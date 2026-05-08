<script setup lang="ts">
  import { onMounted, onBeforeUnmount, ref, watch } from 'vue'
  import { useRoute } from 'vue-router'
  import { useSourcesStore } from '@/stores/sources'
  import { useWatchedStore } from '@/stores/watched'
  import SourceSidebarPanel from '@/components/SourceSidebarPanel.vue'
  import WatchedSidebarContent from '@/components/WatchedSidebarContent.vue'
  import logoUrl from '@/assets/logo.svg'

  const sourcesStore = useSourcesStore()
  const watchedStore = useWatchedStore()
  const route = useRoute()
  const drawerOpen = ref(false)
  const sidebarTab = ref<'repos' | 'watched'>('repos')

  // ----- Sidebar drag-to-resize --------------------------------------------

  const SIDEBAR_WIDTH_KEY = 'libreta:sidebar-width'
  const DEFAULT_WIDTH = 340
  const MIN_WIDTH = 160
  const MAX_WIDTH = 480

  function loadSidebarWidth(): number {
    try {
      const raw = localStorage.getItem(SIDEBAR_WIDTH_KEY)
      if (raw) {
        const n = parseInt(raw, 10)
        if (!Number.isNaN(n) && n >= MIN_WIDTH && n <= MAX_WIDTH) return n
      }
    } catch {
      /* ignore */
    }
    return DEFAULT_WIDTH
  }

  const sidebarWidth = ref(loadSidebarWidth())
  const dragging = ref(false)

  function saveWidth(w: number): void {
    try {
      localStorage.setItem(SIDEBAR_WIDTH_KEY, String(w))
    } catch {
      /* ignore */
    }
  }

  function onDragStart(e: MouseEvent): void {
    e.preventDefault()
    dragging.value = true
    document.addEventListener('mousemove', onDragMove)
    document.addEventListener('mouseup', onDragEnd)
  }

  function onDragMove(e: MouseEvent): void {
    if (!dragging.value) return
    sidebarWidth.value = Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, e.clientX))
  }

  function onDragEnd(): void {
    dragging.value = false
    saveWidth(sidebarWidth.value)
    document.removeEventListener('mousemove', onDragMove)
    document.removeEventListener('mouseup', onDragEnd)
  }

  onBeforeUnmount(() => {
    document.removeEventListener('mousemove', onDragMove)
    document.removeEventListener('mouseup', onDragEnd)
  })

  onMounted(() => {
    sourcesStore.loadSources()
    watchedStore.loadFolders()
  })

  // Adaptive poll for the sources list. The `pending_count` field changes
  // independently of any user action — the background push worker drains it
  // ~1 s after each commit, and external git activity (other clients) can
  // move it too. We use two cadences so the dot feels live during a push
  // without hammering the API at rest:
  //
  //   - Any source has pending commits → poll every 3 s. Catches the
  //     post-push transition to 0 within ~3 s of the worker finishing.
  //   - All sources are clean         → poll every 30 s. Catches external
  //     pushes from other clients, drift, etc., without burning API calls.
  //
  // Tab-hidden visits don't fire (re-checked inside the tick). Tab refocus
  // forces an immediate refresh so the dot doesn't lag a poll interval.
  const FAST_POLL_MS = 3000
  const SLOW_POLL_MS = 30000
  let pollHandle: number | null = null
  let currentInterval = SLOW_POLL_MS

  function shouldPollFast(): boolean {
    return sourcesStore.sources.some((s) => s.pending_count > 0)
  }

  function scheduleNextPoll(): void {
    if (pollHandle !== null) {
      window.clearTimeout(pollHandle)
    }
    currentInterval = shouldPollFast() ? FAST_POLL_MS : SLOW_POLL_MS
    pollHandle = window.setTimeout(async () => {
      if (document.visibilityState === 'visible') {
        await sourcesStore.loadSources()
      }
      scheduleNextPoll()
    }, currentInterval)
  }

  function startPoll(): void {
    if (pollHandle === null) scheduleNextPoll()
  }

  function stopPoll(): void {
    if (pollHandle !== null) {
      window.clearTimeout(pollHandle)
      pollHandle = null
    }
  }
  onMounted(() => {
    startPoll()
    document.addEventListener('visibilitychange', async () => {
      if (document.visibilityState === 'visible') {
        // Refresh immediately on tab refocus so the dot doesn't lag a poll
        // interval after the user comes back, and reschedule the next tick
        // since the cadence may need to flip (e.g. visited a stale tab,
        // pending count is now > 0).
        await sourcesStore.loadSources()
        scheduleNextPoll()
      }
    })
  })

  // When something other than the poll itself triggers a sources refresh
  // (post-save, manual sync, tab refocus), the appropriate cadence may
  // have flipped — e.g. a save just bumped a clean source to pending=1.
  // Re-evaluate after every store update.
  watch(
    () => sourcesStore.sources.map((s) => s.pending_count).join(','),
    (now, prev) => {
      if (now === prev) return
      const wantFast = shouldPollFast()
      const inFast = currentInterval === FAST_POLL_MS
      if (wantFast !== inFast) scheduleNextPoll()
    },
  )
  onBeforeUnmount(stopPoll)

  // Auto-close drawer on navigation (mobile UX)
  watch(
    () => route.fullPath,
    () => {
      drawerOpen.value = false
    },
  )
</script>

<template>
  <div class="flex flex-col h-full md:flex-row overflow-x-hidden w-full max-w-full">
    <!-- Mobile top bar -->
    <header
      class="md:hidden flex items-center gap-3 border-b border-slate-200 bg-slate-50 px-4 py-3"
    >
      <button
        type="button"
        class="p-2 -ml-2 rounded hover:bg-slate-200"
        :aria-expanded="drawerOpen"
        aria-label="Toggle navigation"
        @click="drawerOpen = !drawerOpen"
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          class="w-5 h-5"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          stroke-linecap="round"
          stroke-linejoin="round"
        >
          <line x1="3" y1="6" x2="21" y2="6" />
          <line x1="3" y1="12" x2="21" y2="12" />
          <line x1="3" y1="18" x2="21" y2="18" />
        </svg>
      </button>
      <RouterLink to="/" class="hover:underline flex items-center gap-2">
        <img :src="logoUrl" alt="" class="w-6 h-6" />
        <h1 class="text-base font-semibold">Libreta</h1>
      </RouterLink>
    </header>

    <!-- Drawer backdrop (mobile only) -->
    <div
      v-if="drawerOpen"
      class="md:hidden fixed inset-0 bg-black/30 z-30"
      aria-hidden="true"
      @click="drawerOpen = false"
    />

    <!-- Sidebar / drawer -->
    <aside
      :style="{ width: sidebarWidth + 'px' }"
      class="bg-slate-50 border-slate-200 overflow-y-auto overflow-x-hidden p-4 z-40 fixed inset-y-0 left-0 border-r transition-transform duration-200 md:relative md:shrink-0 md:border-r md:block md:translate-x-0 md:inset-auto"
      :class="[
        drawerOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0',
        dragging ? 'select-none' : '',
      ]"
    >
      <!-- Logo + nav links -->
      <RouterLink to="/" class="hover:underline flex items-center gap-2 mb-4">
        <img :src="logoUrl" alt="" class="w-7 h-7 hidden md:block" />
        <h1 class="text-lg font-semibold hidden md:block">Libreta</h1>
      </RouterLink>
      <div class="flex gap-2 mb-3">
        <RouterLink
          to="/search"
          class="flex-1 flex items-center gap-2 px-2 py-1.5 rounded text-sm text-slate-600 hover:bg-slate-200 transition-colors"
          :class="{ 'bg-slate-200 font-medium': $route.path === '/search' }"
        >
          <svg
            class="w-4 h-4 shrink-0"
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <circle cx="11" cy="11" r="8" />
            <line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
          Search
        </RouterLink>
        <RouterLink
          to="/-/admin"
          class="flex items-center gap-1.5 px-2 py-1.5 rounded text-sm text-slate-600 hover:bg-slate-200 transition-colors"
          :class="{ 'bg-slate-200 font-medium': $route.path.startsWith('/-/admin') }"
          title="Admin"
        >
          <svg
            class="w-4 h-4 shrink-0"
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <circle cx="12" cy="12" r="3" />
            <path
              d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"
            />
          </svg>
        </RouterLink>
      </div>

      <!-- Sidebar tabs -->
      <div class="flex border-b border-slate-200 mb-3">
        <button
          type="button"
          class="flex-1 text-xs font-medium px-2 py-1.5 rounded-t transition-colors"
          :class="
            sidebarTab === 'repos'
              ? 'text-blue-700 border-b-2 border-blue-600 bg-white'
              : 'text-slate-500 hover:text-slate-700'
          "
          @click="sidebarTab = 'repos'"
        >
          Repos
        </button>
        <button
          type="button"
          class="flex-1 text-xs font-medium px-2 py-1.5 rounded-t transition-colors"
          :class="
            sidebarTab === 'watched'
              ? 'text-blue-700 border-b-2 border-blue-600 bg-white'
              : 'text-slate-500 hover:text-slate-700'
          "
          @click="sidebarTab = 'watched'"
        >
          Watched
        </button>
      </div>

      <!-- Git source panels (one per source, stacked) -->
      <div v-if="sidebarTab === 'repos' && sourcesStore.sources.length" class="mb-2">
        <SourceSidebarPanel v-for="src in sourcesStore.sources" :key="src.id" :source="src" />
      </div>

      <p
        v-if="sidebarTab === 'repos' && sourcesStore.loaded && !sourcesStore.sources.length"
        class="text-xs text-slate-400 mb-3"
      >
        No git sources configured.
        <RouterLink to="/-/admin" class="underline hover:text-blue-600">Add one</RouterLink>
      </p>

      <!-- Watched section -->
      <WatchedSidebarContent v-if="sidebarTab === 'watched'" />

      <!-- Drag handle: only interactive on desktop -->
      <div
        class="hidden md:block absolute top-0 right-0 w-2 h-full cursor-col-resize hover:bg-blue-400/30 transition-colors -mr-1 z-10"
        @mousedown="onDragStart"
      />
    </aside>

    <main class="flex-1 overflow-y-auto overflow-x-hidden min-w-0">
      <RouterView />
    </main>
  </div>
</template>
