<script setup lang="ts">
  import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

  // Renders a "On this page" navigation as a collapsed-by-default slide-in
  // panel anchored to the right edge of the viewport. Reads h2/h3 headings
  // out of the rendered article HTML, highlights the heading the user is
  // currently scrolled to, and scrolls back via click.
  const props = defineProps<{
    /** Rendered HTML of the page body. ToC re-derives whenever this changes. */
    html: string
  }>()

  interface Item {
    id: string
    text: string
    level: 2 | 3
  }

  const items = ref<Item[]>([])
  const activeId = ref<string | null>(null)
  const open = ref(false)

  function extract(html: string): Item[] {
    const out: Item[] = []
    if (!html) return out
    const doc = new DOMParser().parseFromString(html, 'text/html')
    doc.querySelectorAll('h2[id], h3[id]').forEach((el) => {
      const tag = el.tagName.toLowerCase()
      const level = tag === 'h2' ? 2 : 3
      out.push({
        id: el.id,
        text: el.textContent?.trim() ?? el.id,
        level: level as 2 | 3,
      })
    })
    return out
  }

  let scroller: HTMLElement | null = null

  function findScroller(): HTMLElement | null {
    let el: HTMLElement | null = document.querySelector('main.overflow-y-auto')
    if (!el) el = document.scrollingElement as HTMLElement | null
    return el
  }

  function scrollToHeading(id: string): void {
    const target = document.getElementById(id)
    if (!target || !scroller) return
    const scrollerTop = scroller.getBoundingClientRect().top
    const targetTop = target.getBoundingClientRect().top
    scroller.scrollBy({ top: targetTop - scrollerTop - 16, behavior: 'smooth' })
    activeId.value = id
    // Close the panel after navigating so the user sees the content they
    // jumped to.
    open.value = false
  }

  function onScroll(): void {
    if (!scroller || items.value.length === 0) return
    const scrollerTop = scroller.getBoundingClientRect().top
    let current: string | null = null
    for (const it of items.value) {
      const el = document.getElementById(it.id)
      if (!el) continue
      const top = el.getBoundingClientRect().top - scrollerTop
      if (top - 80 <= 0) {
        current = it.id
      } else {
        break
      }
    }
    activeId.value = current ?? items.value[0]?.id ?? null
  }

  function onKeydown(e: KeyboardEvent): void {
    if (e.key === 'Escape' && open.value) open.value = false
  }

  // Re-extract whenever the rendered HTML changes (page navigation), then
  // wait a tick for the DOM to update so getElementById finds the new headings.
  watch(
    () => props.html,
    async (h) => {
      items.value = extract(h)
      // Close on navigation so the panel doesn't linger between pages.
      open.value = false
      await new Promise((r) => requestAnimationFrame(() => r(null)))
      onScroll()
    },
    { immediate: true },
  )

  onMounted(() => {
    scroller = findScroller()
    scroller?.addEventListener('scroll', onScroll, { passive: true })
    window.addEventListener('keydown', onKeydown)
    onScroll()
  })

  onBeforeUnmount(() => {
    scroller?.removeEventListener('scroll', onScroll)
    window.removeEventListener('keydown', onKeydown)
  })

  const hasToc = computed(() => items.value.length >= 2)
</script>

<template>
  <template v-if="hasToc">
    <!-- Trigger: a small button. Positioned to sit just to the left of
         PageToolbar's button cluster (which lives at top-3 right-3). -->
    <button
      type="button"
      class="fixed top-3 right-28 z-30 bg-white/90 backdrop-blur border border-slate-200 rounded-md p-2 shadow-sm hover:bg-slate-50"
      :title="open ? 'Hide table of contents' : 'Show table of contents'"
      :aria-label="open ? 'Hide table of contents' : 'Show table of contents'"
      :aria-expanded="open"
      @click="open = !open"
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
        <line x1="3" y1="6" x2="21" y2="6" />
        <line x1="3" y1="12" x2="21" y2="12" />
        <line x1="3" y1="18" x2="15" y2="18" />
      </svg>
    </button>

    <!-- Backdrop dims the page while the panel is open and dismisses it on click. -->
    <div
      v-if="open"
      class="fixed inset-0 bg-black/20 z-30"
      aria-hidden="true"
      @click="open = false"
    />

    <!-- Slide-in panel. Opaque background, sits above content, scrollable. -->
    <aside
      class="fixed top-0 right-0 h-full w-80 max-w-[85vw] bg-white border-l border-slate-200 shadow-xl z-40 transform transition-transform duration-200 ease-out flex flex-col"
      :class="open ? 'translate-x-0' : 'translate-x-full'"
      aria-label="On this page"
    >
      <header class="flex items-center justify-between px-4 py-3 border-b border-slate-200">
        <h2 class="text-xs font-semibold uppercase tracking-wide text-slate-500">On this page</h2>
        <button
          type="button"
          class="p-1 -mr-1 rounded hover:bg-slate-100"
          aria-label="Close table of contents"
          @click="open = false"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            class="w-4 h-4 text-slate-500"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>
      </header>
      <ul class="flex-1 overflow-y-auto py-2 text-sm">
        <li v-for="item in items" :key="item.id">
          <button
            type="button"
            class="block w-full text-left truncate border-l-2 py-1 pr-3 transition-colors"
            :class="[
              item.level === 3 ? 'pl-8 text-slate-500' : 'pl-4 text-slate-700',
              activeId === item.id
                ? 'border-blue-500 text-blue-700 font-medium bg-blue-50/60'
                : 'border-transparent hover:bg-slate-50 hover:text-slate-900',
            ]"
            @click="scrollToHeading(item.id)"
          >
            {{ item.text }}
          </button>
        </li>
      </ul>
    </aside>
  </template>
</template>
