<script setup lang="ts">
  import { computed, ref, watch } from 'vue'
  import { useRoute } from 'vue-router'
  import Breadcrumbs from '@/components/Breadcrumbs.vue'
  import PageToolbar from '@/components/PageToolbar.vue'
  import { useReadingWidth } from '@/composables/usePrefs'

  // Viewer for video files in a repo. Plays via the browser's native <video>
  // element — no library; codec support is the browser's call (mp4/webm/ogg
  // are broadly supported). Same scaffold as ImageView.

  const { width } = useReadingWidth()
  const route = useRoute()

  const path = computed(() => {
    const raw = route.params.path
    if (Array.isArray(raw)) return raw.join('/')
    return String(raw ?? '')
  })

  const sourceId = computed(() => {
    const raw = route.params.sourceId
    return Array.isArray(raw) ? raw[0] : (raw ?? '')
  })

  const watchedLabel = computed(() => {
    const raw = route.params.label
    return Array.isArray(raw) ? raw[0] : (raw ?? '')
  })

  const assetUrl = computed(() => {
    const segments = path.value.split('/').map(encodeURIComponent).join('/')
    if (watchedLabel.value) {
      return `/api/v1/watch/${encodeURIComponent(watchedLabel.value)}/assets/${segments}`
    }
    if (sourceId.value) {
      return `/api/v1/sources/${encodeURIComponent(sourceId.value)}/assets/${segments}`
    }
    return `/api/v1/assets/pages/${segments}`
  })

  const title = computed(() => {
    const parts = path.value.split('/')
    return parts[parts.length - 1] ?? path.value
  })

  // Vue binds `muted` as a property and doesn't always apply it reliably on
  // the initial render, which would make the browser block autoplay. Set it
  // imperatively whenever the element/source changes, as belt-and-braces.
  const videoEl = ref<HTMLVideoElement | null>(null)
  watch([videoEl, assetUrl], () => {
    if (videoEl.value) videoEl.value.muted = true
  })
</script>

<template>
  <PageToolbar />
  <a
    :href="assetUrl"
    download
    class="fixed top-3 right-[68px] z-20 bg-white/90 backdrop-blur border border-slate-200 rounded-md p-2 hover:bg-slate-50 shadow-sm"
    title="Download file"
    aria-label="Download file"
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
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
      <polyline points="7 10 12 15 17 10" />
      <line x1="12" y1="15" x2="12" y2="3" />
    </svg>
  </a>

  <article class="mx-auto py-6" :class="width === 'wide' ? 'max-w-none px-12' : 'max-w-4xl px-8'">
    <header class="mb-4">
      <Breadcrumbs
        :path="path"
        :source-id="sourceId || undefined"
        :watched-label="watchedLabel || undefined"
      />
    </header>
    <h1 class="text-xl font-mono font-bold mb-4 text-slate-800">{{ title }}</h1>

    <div class="bg-slate-900 rounded-md border border-slate-200 flex justify-center">
      <!-- The user clicked through from the listing, so start playing. Browsers
           only honour autoplay when muted; the user can unmute via controls.
           key forces a reload when navigating between videos. -->
      <video
        :key="assetUrl"
        ref="videoEl"
        controls
        autoplay
        muted
        playsinline
        preload="metadata"
        class="max-w-full max-h-[80vh]"
      >
        <source :src="assetUrl" />
        Your browser can’t play this video format.
      </video>
    </div>
  </article>
</template>
