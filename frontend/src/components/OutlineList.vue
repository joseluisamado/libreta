<script setup lang="ts">
  import { ref } from 'vue'

  interface OutlineEntry {
    title: string
    pageIndex: number | null
    children: OutlineEntry[]
  }

  const props = defineProps<{
    entries: OutlineEntry[]
    onJump: (n: number) => void
    currentPage: number
    depth?: number
  }>()

  const open = ref<Record<number, boolean>>({})

  function isActive(entry: OutlineEntry): boolean {
    if (entry.pageIndex == null) return false
    return entry.pageIndex + 1 === props.currentPage
  }
</script>

<template>
  <ul class="text-sm">
    <li v-for="(entry, i) in entries" :key="i">
      <div class="flex items-center">
        <button
          v-if="entry.children.length"
          type="button"
          class="shrink-0 w-4 h-4 flex items-center justify-center text-slate-400 hover:text-slate-700"
          :class="(depth ?? 0) > 0 ? 'ml-4' : 'ml-1'"
          @click="open[i] = !open[i]"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            class="w-3 h-3 transition-transform"
            :class="{ 'rotate-90': open[i] }"
            viewBox="0 0 12 12"
            fill="currentColor"
          >
            <path d="M4 2 L8 6 L4 10 Z" />
          </svg>
        </button>
        <span v-else class="shrink-0 w-4 h-4" :class="(depth ?? 0) > 0 ? 'ml-4' : 'ml-1'" />
        <button
          v-if="entry.pageIndex != null"
          type="button"
          class="flex-1 text-left truncate border-l-2 py-1 pr-3 transition-colors"
          :class="[
            (depth ?? 0) > 0 ? 'pl-4 text-slate-500' : 'pl-3 text-slate-700',
            isActive(entry)
              ? 'border-blue-500 text-blue-700 font-medium bg-blue-50/60'
              : 'border-transparent hover:bg-slate-50 hover:text-slate-900',
          ]"
          @click="onJump(entry.pageIndex! + 1)"
        >
          {{ entry.title }}
        </button>
        <span
          v-else
          class="flex-1 text-left truncate border-l-2 border-transparent py-1 pr-3 text-slate-400 italic"
          :class="(depth ?? 0) > 0 ? 'pl-4' : 'pl-3'"
        >
          {{ entry.title }}
        </span>
      </div>
      <OutlineList
        v-if="entry.children.length && open[i]"
        :entries="entry.children"
        :on-jump="onJump"
        :current-page="currentPage"
        :depth="(depth ?? 0) + 1"
      />
    </li>
  </ul>
</template>
