<script setup lang="ts">
  import { onMounted, ref, watch } from 'vue'
  import { useRoute } from 'vue-router'
  import { useTreeStore } from '@/stores/tree'
  import PageTree from '@/components/PageTree.vue'

  const tree = useTreeStore()
  const route = useRoute()
  const drawerOpen = ref(false)

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
  <div class="flex flex-col h-full md:flex-row">
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
      <h1 class="text-base font-semibold">Libreta</h1>
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
      class="bg-slate-50 border-slate-200 overflow-y-auto p-4 z-40 md:static md:w-64 md:shrink-0 md:border-r md:block fixed inset-y-0 left-0 w-72 border-r transition-transform duration-200 md:translate-x-0"
      :class="drawerOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0'"
    >
      <h1 class="text-lg font-semibold mb-4 hidden md:block">Libreta</h1>
      <p v-if="tree.error" class="text-red-600 text-sm">{{ tree.error }}</p>
      <PageTree :nodes="tree.nodes" />
    </aside>

    <main class="flex-1 overflow-y-auto">
      <RouterView />
    </main>
  </div>
</template>
