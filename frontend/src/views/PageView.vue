<script setup lang="ts">
  import { computed, ref, watch, nextTick } from 'vue'
  import { useRoute, useRouter } from 'vue-router'
  import { getPage, savePage, deletePage, movePage } from '@/api/client'
  import type { OtherFile, PageNode, PageRead } from '@/api/types'
  import { renderMarkdown, renderMermaidIn } from '@/markdown'
  import { useTreeStore } from '@/stores/tree'
  import { useReadingWidth } from '@/composables/usePrefs'
  import { useViewMode } from '@/composables/useViewMode'
  import Breadcrumbs from '@/components/Breadcrumbs.vue'
  import PageToolbar from '@/components/PageToolbar.vue'
  import PageToc from '@/components/PageToc.vue'
  import hljs from 'highlight.js'
  import 'highlight.js/styles/github.css'

  const { width } = useReadingWidth()
  const { mode, toggle: toggleViewMode } = useViewMode()

  const route = useRoute()
  const router = useRouter()
  const tree = useTreeStore()
  const page = ref<PageRead | null>(null)
  const error = ref<string | null>(null)
  const contentEl = ref<HTMLElement | null>(null)

  function findNode(nodes: PageNode[], target: string): PageNode | null {
    for (const n of nodes) {
      if (n.path === target) return n
      if (n.children.length) {
        const hit = findNode(n.children, target)
        if (hit) return hit
      }
    }
    return null
  }

  const directoryChildren = computed<PageNode[]>(() => {
    if (!page.value) return []
    const node = findNode(tree.nodes, page.value.path)
    if (!node || !node.is_directory) return []
    return node.children
  })

  const directoryOtherFiles = computed<OtherFile[]>(() => {
    if (!page.value) return []
    const node = findNode(tree.nodes, page.value.path)
    return node?.other_files ?? []
  })

  function getOtherFileUrl(filePath: string): string {
    return `/api/v1/assets/pages/${encodeURIComponent(filePath)}`
  }

  function getTextFileUrl(filePath: string): string {
    return `/text/${filePath}`
  }

  const isDirectory = computed(() => {
    if (!page.value) return false
    const node = findNode(tree.nodes, page.value.path)
    return node?.is_directory ?? false
  })

  const path = computed(() => {
    const raw = route.params.path
    if (Array.isArray(raw)) return raw.join('/')
    return String(raw ?? 'index')
  })

  async function load(): Promise<void> {
    if (path.value.toLowerCase().endsWith('.pdf')) {
      router.replace(`/pdf/${path.value}`)
      return
    }
    page.value = null
    error.value = null
    try {
      page.value = await getPage(path.value)
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e)
    }
  }

  watch(path, load, { immediate: true })

  function slugify(name: string): string {
    return name
      .trim()
      .toLowerCase()
      .replace(/\s+/g, '-')
      .replace(/[^a-z0-9-]/g, '')
  }

  async function createPage(): Promise<void> {
    const name = window.prompt('Page name:')
    if (!name || !name.trim()) return
    const slug = slugify(name)
    const prefix = path.value === 'index' ? '' : path.value
    const newPath = prefix ? `${prefix}/${slug}` : slug
    try {
      await savePage(newPath, { body: `# ${name.trim()}\n\n` })
      await tree.load()
      router.push(`/edit/${newPath}`)
    } catch (e) {
      window.alert(`Failed to create page: ${e instanceof Error ? e.message : String(e)}`)
    }
  }

  async function createFolder(): Promise<void> {
    const name = window.prompt('Folder name:')
    if (!name || !name.trim()) return
    const slug = slugify(name)
    const prefix = path.value === 'index' ? '' : path.value
    const newPath = prefix ? `${prefix}/${slug}` : slug
    try {
      await savePage(newPath, { body: `# ${name.trim()}\n\n` })
      await tree.load()
      router.push(`/w/${newPath}`)
    } catch (e) {
      window.alert(`Failed to create folder: ${e instanceof Error ? e.message : String(e)}`)
    }
  }

  async function deleteChild(childPath: string): Promise<void> {
    if (!window.confirm(`Delete "${childPath}"? This cannot be undone.`)) return
    try {
      await deletePage(childPath)
      await tree.load()
    } catch (e) {
      window.alert(`Failed to delete: ${e instanceof Error ? e.message : String(e)}`)
    }
  }

  async function renameChild(childPath: string): Promise<void> {
    const newName = window.prompt('New path:', childPath)
    if (!newName || !newName.trim() || newName.trim() === childPath) return
    try {
      await movePage(childPath, { new_path: newName.trim() })
      await tree.load()
    } catch (e) {
      window.alert(`Failed to rename: ${e instanceof Error ? e.message : String(e)}`)
    }
  }

  // If the body already starts with an H1 matching the frontmatter title,
  // skip rendering a chrome H1 above it to avoid the duplicated heading.
  // Render the frontmatter title as <h1> only when the body has no H1 of
  // its own. If the markdown begins with `# Heading`, that *is* the page
  // title — surfacing meta.title above it would just duplicate the header.
  const bodyHasH1 = computed(() => {
    if (!page.value) return false
    const firstLine = page.value.body.trimStart().split('\n', 1)[0] ?? ''
    return firstLine.startsWith('# ')
  })

  const html = computed(() => (page.value ? renderMarkdown(page.value.body, page.value.path) : ''))

  watch([html, mode], async () => {
    await nextTick()
    if (mode.value === 'rendered' && contentEl.value) await renderMermaidIn(contentEl.value)
  })

  const highlightedSource = computed(() => {
    if (!page.value) return ''
    return hljs.highlight(page.value.body, { language: 'markdown' }).value
  })
</script>

<template>
  <PageToolbar />
  <button
    v-if="page"
    type="button"
    class="fixed top-3 right-[68px] z-20 bg-white/90 backdrop-blur border border-slate-200 rounded-md p-2 hover:bg-slate-50 shadow-sm"
    :title="mode === 'rendered' ? 'View markdown source' : 'View rendered page'"
    :aria-label="mode === 'rendered' ? 'View markdown source' : 'View rendered page'"
    @click="toggleViewMode"
  >
    <svg
      v-if="mode === 'rendered'"
      xmlns="http://www.w3.org/2000/svg"
      class="w-4 h-4 text-slate-600"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      stroke-width="2"
      stroke-linecap="round"
      stroke-linejoin="round"
    >
      <polyline points="16 18 22 12 16 6" />
      <polyline points="8 6 2 12 8 18" />
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
      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  </button>
  <RouterLink
    v-if="page"
    :to="`/edit/${page.path}`"
    class="fixed top-3 right-[112px] z-30 bg-white/90 backdrop-blur border border-slate-200 rounded-md p-2 hover:bg-slate-50 shadow-sm"
    title="Edit this page"
    aria-label="Edit this page"
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
      <path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z" />
    </svg>
  </RouterLink>
  <PageToc v-if="page" :html="html" />
  <article class="mx-auto py-6" :class="width === 'wide' ? 'max-w-none px-12' : 'max-w-3xl px-8'">
    <p v-if="error" class="text-red-600">{{ error }}</p>
    <template v-else-if="page">
      <header
        class="flex items-center justify-between mb-4"
        :class="width === 'wide' ? 'pr-48' : ''"
      >
        <Breadcrumbs :path="page.path" />
        <RouterLink
          :to="`/history/${page.path}`"
          class="text-xs text-slate-400 hover:text-slate-600 flex items-center gap-1 shrink-0"
          title="Page history"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            class="w-3.5 h-3.5"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <circle cx="12" cy="12" r="10" />
            <polyline points="12 6 12 12 16 14" />
          </svg>
          History
        </RouterLink>
      </header>
      <h1 v-if="!bodyHasH1" class="text-3xl font-bold">{{ page.meta.title }}</h1>
      <div v-if="mode === 'rendered'" ref="contentEl" class="prose" v-html="html" />
      <pre
        v-else
        class="bg-[#f6f8fa] rounded-md p-6 overflow-auto text-sm leading-relaxed border border-slate-200"
      ><code class="hljs language-markdown" v-html="highlightedSource" /></pre>
      <p v-if="page.meta.tags.length" class="mt-8 text-xs text-slate-500">
        <span v-for="t in page.meta.tags" :key="t" class="mr-2">#{{ t }}</span>
      </p>
      <section v-if="isDirectory" class="mt-8 border-t border-slate-200 pt-4">
        <h2 class="text-sm font-semibold uppercase tracking-wide text-slate-500 mb-2">
          In this folder
        </h2>
        <div class="flex gap-2 mb-3">
          <button
            type="button"
            class="text-xs px-3 py-1 rounded border border-slate-300 text-slate-600 hover:bg-slate-50 hover:text-blue-600 cursor-pointer"
            @click="createPage"
          >
            + New page
          </button>
          <button
            type="button"
            class="text-xs px-3 py-1 rounded border border-slate-300 text-slate-600 hover:bg-slate-50 hover:text-blue-600 cursor-pointer"
            @click="createFolder"
          >
            + New folder
          </button>
        </div>
        <ul v-if="directoryChildren.length" class="text-sm space-y-1">
          <li
            v-for="child in directoryChildren"
            :key="child.path"
            class="flex items-center gap-1 group"
          >
            <RouterLink
              :to="`${child.kind === 'pdf' ? '/pdf' : '/w'}/${child.path}`"
              class="flex items-center flex-1 min-w-0 text-slate-700 hover:text-blue-600 hover:underline"
            >
              <span class="inline-block w-6 shrink-0 text-slate-400">
                <span v-if="child.children.length">📁</span>
                <span
                  v-else-if="child.kind === 'pdf'"
                  class="text-[10px] font-semibold text-rose-500"
                  >PDF</span
                >
                <span v-else class="text-[10px] font-semibold text-sky-500">MD</span>
              </span>
              <span class="truncate">{{ child.title }}</span>
            </RouterLink>
            <button
              type="button"
              class="shrink-0 opacity-0 group-hover:opacity-100 text-slate-400 hover:text-slate-600 p-0.5 rounded transition-opacity"
              title="Rename"
              aria-label="Rename"
              @click="renameChild(child.path)"
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                class="w-3.5 h-3.5"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
                stroke-linecap="round"
                stroke-linejoin="round"
              >
                <path d="M12 20h9" />
                <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z" />
              </svg>
            </button>
            <button
              type="button"
              class="shrink-0 opacity-0 group-hover:opacity-100 text-slate-400 hover:text-red-600 p-0.5 rounded transition-opacity"
              title="Delete"
              aria-label="Delete"
              @click="deleteChild(child.path)"
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                class="w-3.5 h-3.5"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
                stroke-linecap="round"
                stroke-linejoin="round"
              >
                <polyline points="3 6 5 6 21 6" />
                <path
                  d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"
                />
                <line x1="10" y1="11" x2="10" y2="17" />
                <line x1="14" y1="11" x2="14" y2="17" />
              </svg>
            </button>
          </li>
        </ul>
      </section>
      <section v-if="directoryOtherFiles.length" class="mt-6 border-t border-slate-200 pt-4">
        <h2 class="text-sm font-semibold uppercase tracking-wide text-slate-500 mb-2">
          Other files
        </h2>
        <ul class="text-sm space-y-1">
          <li
            v-for="file in directoryOtherFiles"
            :key="file.path"
            class="flex items-center gap-1 group"
          >
            <RouterLink
              v-if="file.kind === 'text'"
              :to="getTextFileUrl(file.path)"
              class="flex items-center flex-1 min-w-0 text-slate-600 hover:text-blue-600 hover:underline"
            >
              <span
                class="w-6 shrink-0 mr-0.5 text-[10px] font-semibold text-violet-500 text-center"
                >TXT</span
              >
              <span class="truncate">{{ file.name }}</span>
            </RouterLink>
            <a
              v-else
              :href="getOtherFileUrl(file.path)"
              :download="file.name"
              class="flex items-center flex-1 min-w-0 text-slate-600 hover:text-blue-600 hover:underline"
            >
              <span
                class="w-6 shrink-0 mr-0.5 text-[10px] font-semibold text-center"
                :class="{
                  'text-emerald-500': file.kind === 'image',
                  'text-orange-500': file.kind === 'drawio',
                  'text-slate-500': file.kind === 'binary',
                }"
                >{{ file.kind === 'image' ? 'IMG' : file.kind === 'drawio' ? 'DRAW' : 'BIN' }}</span
              >
              <span class="truncate">{{ file.name }}</span>
            </a>
          </li>
        </ul>
      </section>
    </template>
    <p v-else class="text-slate-400">Loading…</p>
  </article>
</template>
