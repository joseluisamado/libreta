<script setup lang="ts">
  import { useReadingWidth } from '@/composables/usePrefs'

  const { width, toggle } = useReadingWidth()
</script>

<template>
  <div class="flex items-center gap-1 fixed top-3 right-3 z-20">
    <button
      type="button"
      class="bg-white/90 backdrop-blur border border-slate-200 rounded-md p-2 hover:bg-slate-50 shadow-sm"
      :title="width === 'standard' ? 'Expand to full width' : 'Use standard width'"
      :aria-label="width === 'standard' ? 'Expand to full width' : 'Use standard width'"
      @click="toggle"
    >
      <svg
        v-if="width === 'standard'"
        xmlns="http://www.w3.org/2000/svg"
        class="w-4 h-4 text-slate-600"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
        stroke-linecap="round"
        stroke-linejoin="round"
      >
        <polyline points="9 4 4 4 4 9" />
        <polyline points="15 4 20 4 20 9" />
        <polyline points="9 20 4 20 4 15" />
        <polyline points="15 20 20 20 20 15" />
      </svg>
      <svg
        v-else
        xmlns="http://www.w3.org/2000/svg"
        class="w-4 h-4 text-slate-600"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
        stroke-linecap="round"
        stroke-linejoin="round"
      >
        <polyline points="4 9 9 9 9 4" />
        <polyline points="20 9 15 9 15 4" />
        <polyline points="4 15 9 15 9 20" />
        <polyline points="20 15 15 15 15 20" />
      </svg>
    </button>
  </div>
</template>
