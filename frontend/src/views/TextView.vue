<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import Breadcrumbs from '@/components/Breadcrumbs.vue'
import PageToolbar from '@/components/PageToolbar.vue'
import { useReadingWidth } from '@/composables/usePrefs'
import hljs from 'highlight.js'
import 'highlight.js/styles/github.css'

const EXT_LANG: Record<string, string> = {
  py: 'python',
  js: 'javascript',
  mjs: 'javascript',
  cjs: 'javascript',
  ts: 'typescript',
  tsx: 'typescript',
  jsx: 'javascript',
  json: 'json',
  yaml: 'yaml',
  yml: 'yaml',
  toml: 'ini',
  ini: 'ini',
  cfg: 'ini',
  conf: 'ini',
  xml: 'xml',
  html: 'xml',
  htm: 'xml',
  css: 'css',
  scss: 'scss',
  less: 'less',
  csv: 'plaintext',
  txt: 'plaintext',
  log: 'plaintext',
  md: 'markdown',
  rs: 'rust',
  go: 'go',
  java: 'java',
  c: 'c',
  h: 'c',
  cpp: 'cpp',
  hpp: 'cpp',
  cc: 'cpp',
  sh: 'bash',
  bash: 'bash',
  zsh: 'bash',
  fish: 'fish',
  env: 'bash',
  dockerfile: 'dockerfile',
  makefile: 'makefile',
  sql: 'sql',
  rb: 'ruby',
  php: 'php',
  lua: 'lua',
  pl: 'perl',
  r: 'r',
  swift: 'swift',
  kt: 'kotlin',
  scala: 'scala',
  dart: 'dart',
  ex: 'elixir',
  exs: 'elixir',
  erl: 'erlang',
  hs: 'haskell',
  clj: 'clojure',
  edn: 'clojure',
  el: 'elisp',
}

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

  <article
    class="mx-auto py-6"
    :class="width === 'wide' ? 'max-w-none px-12' : 'max-w-3xl px-8'"
  >
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

    <div
      v-else
      class="bg-white rounded-md border border-slate-200 overflow-auto"
    >
      <table class="w-full text-sm leading-relaxed border-collapse">
        <tbody>
          <tr v-for="(line, idx) in lines" :key="idx">
            <td
              class="select-none text-right text-slate-400 border-r border-slate-200 px-3 py-px align-top font-mono text-xs w-12 bg-slate-50"
            >
              {{ idx + 1 }}
            </td>
            <td class="px-3 py-px align-top">
              <code
                class="hljs"
                :class="language ? `language-${language}` : ''"
                v-html="
                  line
                    ? (language
                        ? hljs.highlight(line, { language }).value
                        : hljs.highlightAuto(line).value)
                    : ''
                "
              />
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
