<script setup lang="ts">
  import { onBeforeUnmount, onMounted, ref } from 'vue'
  import { useReadingWidth } from '@/composables/usePrefs'

  const { width, toggle } = useReadingWidth()

  // Show "back to top" only after the user has scrolled at least one viewport.
  // We listen on the <main> element (its overflow-y is what scrolls), which we
  // locate via a closest() lookup at mount time so this component stays decoupled.
  const showBackToTop = ref(false)
  let scroller: HTMLElement | null = null

  function findScroller(): HTMLElement | null {
    // The main content area in App.vue has class "flex-1 overflow-y-auto".
    // It is the nearest scrolling ancestor of this toolbar.
    let el: HTMLElement | null = document.querySelector('main.overflow-y-auto')
    if (!el) el = document.scrollingElement as HTMLElement | null
    return el
  }

  function onScroll(): void {
    if (!scroller) return
    showBackToTop.value = scroller.scrollTop > scroller.clientHeight
  }

  function backToTop(): void {
    scroller?.scrollTo({ top: 0, behavior: 'smooth' })
  }

  onMounted(() => {
    scroller = findScroller()
    scroller?.addEventListener('scroll', onScroll, { passive: true })
    onScroll()
  })

  onBeforeUnmount(() => {
    scroller?.removeEventListener('scroll', onScroll)
  })
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
    <button
      v-if="showBackToTop"
      type="button"
      class="bg-white/90 backdrop-blur border border-slate-200 rounded-md p-2 hover:bg-slate-50 shadow-sm"
      title="Back to top"
      aria-label="Back to top"
      @click="backToTop"
    >
      <svg
        xmlns="http://www.w3.org/2000/svg"
        class="w-4 h-4 text-slate-600"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
        stroke-linecap="round"
        stroke-linejoin="round"
      >
        <line x1="12" y1="19" x2="12" y2="5" />
        <polyline points="5 12 12 5 19 12" />
      </svg>
    </button>
  </div>
</template>
