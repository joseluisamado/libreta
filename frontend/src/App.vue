<script setup lang="ts">
import { onMounted } from 'vue'
import { useTreeStore } from '@/stores/tree'
import PageTree from '@/components/PageTree.vue'

const tree = useTreeStore()
onMounted(() => tree.load())
</script>

<template>
  <div class="flex h-full">
    <aside class="w-64 shrink-0 border-r border-slate-200 bg-slate-50 p-4 overflow-y-auto">
      <h1 class="text-lg font-semibold mb-4">Libreta</h1>
      <p v-if="tree.error" class="text-red-600 text-sm">{{ tree.error }}</p>
      <PageTree :nodes="tree.nodes" />
    </aside>
    <main class="flex-1 overflow-y-auto">
      <RouterView />
    </main>
  </div>
</template>
