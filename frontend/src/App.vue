<script setup lang="ts">
  import { onMounted, onBeforeUnmount, ref, watch } from 'vue'
  import { useRoute } from 'vue-router'
  import { useTreeStore } from '@/stores/tree'
  import PageTree from '@/components/PageTree.vue'
  import logoUrl from '@/assets/logo.svg'

  const tree = useTreeStore()
  const route = useRoute()
  const drawerOpen = ref(false)

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

  onMounted(() => tree.load())

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
      :class="[drawerOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0', dragging ? 'select-none' : '']"
    >
      <RouterLink to="/" class="hover:underline flex items-center gap-2 mb-4">
        <img :src="logoUrl" alt="" class="w-7 h-7 hidden md:block" />
        <h1 class="text-lg font-semibold hidden md:block">Libreta</h1>
      </RouterLink>
      <RouterLink
        to="/search"
        class="flex items-center gap-2 mb-3 px-2 py-1.5 rounded text-sm text-slate-600 hover:bg-slate-200 transition-colors"
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
      <p v-if="tree.error" class="text-red-600 text-sm">{{ tree.error }}</p>
      <PageTree :nodes="tree.nodes" />
      <!-- Drag handle: only interactive on desktop (hidden on mobile) -->
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
