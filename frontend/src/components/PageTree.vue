<script setup lang="ts">
import type { PageNode } from '@/api/types'

defineProps<{ nodes: PageNode[] }>()
</script>

<template>
  <ul class="text-sm">
    <li v-for="node in nodes" :key="node.path" class="my-1">
      <RouterLink
        v-if="!node.is_directory"
        :to="`/w/${node.path}`"
        class="text-slate-700 hover:text-blue-600"
        active-class="text-blue-700 font-semibold"
      >
        {{ node.title }}
      </RouterLink>
      <span v-else class="text-slate-500 uppercase tracking-wide text-xs">{{ node.title }}</span>
      <PageTree v-if="node.children.length" :nodes="node.children" class="ml-3 border-l border-slate-200 pl-2" />
    </li>
  </ul>
</template>
