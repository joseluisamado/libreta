<script setup lang="ts">
  import { computed, nextTick, ref, watch } from 'vue'
  import { useRoute, useRouter } from 'vue-router'
  import Breadcrumbs from '@/components/Breadcrumbs.vue'
  import PageToolbar from '@/components/PageToolbar.vue'
  import { useReadingWidth } from '@/composables/usePrefs'
  import { EXT_LANG } from '@/textFiles'
  import hljs from 'highlight.js'
  import 'highlight.js/styles/github.css'

  const { width } = useReadingWidth()
  const route = useRoute()
  const router = useRouter()

  // #L42 selects a single line; #L42-L51 selects an inclusive range.
  const lineRange = computed<{ start: number; end: number } | null>(() => {
    const m = /^#L(\d+)(?:-L?(\d+))?$/.exec(route.hash)
    if (!m) return null
    const start = Number(m[1])
    const end = m[2] ? Number(m[2]) : start
    if (!start) return null
    return start <= end ? { start, end } : { start: end, end: start }
  })

  function isLineSelected(idx: number): boolean {
    const r = lineRange.value
    if (!r) return false
    const n = idx + 1
    return n >= r.start && n <= r.end
  }

  function onLineClick(idx: number, event: MouseEvent): void {
    const n = idx + 1
    let hash = `#L${n}`
    if (event.shiftKey && lineRange.value) {
      const anchor = lineRange.value.start
      const lo = Math.min(anchor, n)
      const hi = Math.max(anchor, n)
      hash = lo === hi ? `#L${lo}` : `#L${lo}-L${hi}`
    }
    router.replace({ hash })
  }

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

  const fileExt = computed(() => {
    const last = title.value.toLowerCase()
    // Special filenames without extension
    if (last === 'dockerfile') return 'dockerfile'
    if (last === 'makefile') return 'makefile'
    if (last === '.env') return 'env'
    // Multiple extensions: .drawio.svg → .svg, .test.ts → .ts
    const dot = last.lastIndexOf('.')
    return dot === -1 ? '' : last.slice(dot + 1)
  })

  const language = computed(() => {
    const ext = fileExt.value
    const cand = ext ? EXT_LANG[ext] : undefined
    if (cand && hljs.getLanguage(cand)) return cand
    return ''
  })

  const error = ref<string | null>(null)
  const loading = ref(true)
  const rawContent = ref('')

  const highlighted = computed(() => {
    if (!rawContent.value) return ''
    if (language.value) {
      return hljs.highlight(rawContent.value, { language: language.value }).value
    }
    const result = hljs.highlightAuto(rawContent.value)
    return result.value
  })

  const lines = computed(() => {
    const raw = rawContent.value
    if (!raw) return []
    // Split preserving empty last line but not a single trailing empty
    const parts = raw.split('\n')
    if (parts.length > 1 && parts[parts.length - 1] === '') {
      parts.pop()
    }
    return parts
  })

  const fileSize = computed(() => new TextEncoder().encode(rawContent.value).length)

  async function load(): Promise<void> {
    error.value = null
    loading.value = true
    rawContent.value = ''
    try {
      const r = await fetch(assetUrl.value)
      if (!r.ok) {
        const detail = (await r.json().catch(() => ({}))) as { detail?: string }
        throw new Error(detail.detail ?? `HTTP ${r.status}`)
      }
      rawContent.value = await r.text()
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e)
    } finally {
      loading.value = false
    }
  }

  watch([path, sourceId, watchedLabel], load, { immediate: true })

  async function scrollToHash(): Promise<void> {
    const r = lineRange.value
    if (!r) return
    await nextTick()
    const el = document.getElementById(`L${r.start}`)
    if (el) el.scrollIntoView({ block: 'center', behavior: 'auto' })
  }

  watch([rawContent, lineRange], scrollToHash)
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

  <article class="mx-auto py-6" :class="width === 'wide' ? 'max-w-none px-12' : 'max-w-3xl px-8'">
    <header class="flex items-center justify-between mb-4">
      <Breadcrumbs
        :path="path"
        :source-id="sourceId || undefined"
        :watched-label="watchedLabel || undefined"
      />
    </header>
    <h1 class="text-xl font-mono font-bold mb-2 text-slate-800">{{ title }}</h1>
    <p v-if="language" class="text-xs text-slate-400 mb-4">{{ language }}</p>

    <p v-if="error" class="text-red-600">Failed to load file: {{ error }}</p>
    <p v-else-if="loading" class="text-slate-400">Loading…</p>

    <div v-else class="bg-white rounded-md border border-slate-200 overflow-auto">
      <table class="w-full text-sm leading-relaxed border-collapse">
        <tbody>
          <tr
            v-for="(line, idx) in lines"
            :id="`L${idx + 1}`"
            :key="idx"
            :class="isLineSelected(idx) ? 'bg-yellow-100' : ''"
          >
            <td
              class="select-none cursor-pointer text-right text-slate-400 hover:text-slate-700 border-r border-slate-200 px-3 py-px align-top font-mono text-xs w-12"
              :class="isLineSelected(idx) ? 'bg-yellow-200' : 'bg-slate-50'"
              :title="`Link to line ${idx + 1} (shift-click to extend)`"
              @click="onLineClick(idx, $event)"
            >
              {{ idx + 1 }}
            </td>
            <td class="px-3 py-px align-top">
              <!-- eslint-disable vue/no-v-html -- sanitized: hljs highlight output, input HTML-escaped -->
              <code
                class="hljs"
                :class="language ? `language-${language}` : ''"
                v-html="
                  line
                    ? language
                      ? hljs.highlight(line, { language }).value
                      : hljs.highlightAuto(line).value
                    : ''
                "
              />
              <!-- eslint-enable vue/no-v-html -->
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <p v-if="!loading && !error" class="mt-4 text-xs text-slate-400">
      {{ lines.length }} lines &middot; {{ fileSize.toLocaleString() }} bytes
    </p>
  </article>
</template>
