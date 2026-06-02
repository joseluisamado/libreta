<script setup lang="ts">
  import { computed, ref, watch, nextTick } from 'vue'
  import { useRoute, useRouter } from 'vue-router'
  import { getPage, savePage, deletePage, movePage, uploadFolderFile } from '@/api/client'
  import type { OtherFile, PageNode, PageRead } from '@/api/types'
  import { renderMarkdown, renderMermaidIn } from '@/markdown'
  import { useTreeStore } from '@/stores/tree'
  import { useReadingWidth } from '@/composables/usePrefs'
  import { useViewMode } from '@/composables/useViewMode'
  import Breadcrumbs from '@/components/Breadcrumbs.vue'
  import DirListing from '@/components/DirListing.vue'
  import PageToolbar from '@/components/PageToolbar.vue'
  import PageToc from '@/components/PageToc.vue'
  import NameDialog from '@/components/NameDialog.vue'
  import { useNameDialog } from '@/composables/useNameDialog'
  import { pageNameToSlug } from '@/utils/pageName'
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

  function getChildUrl(childPath: string): string {
    return `${childPath.toLowerCase().endsWith('.pdf') ? '/pdf' : '/w'}/${childPath}`
  }

  const uploading = ref(false)

  async function uploadFiles(files: File[]): Promise<void> {
    const folder = path.value === 'index' ? '' : path.value
    uploading.value = true
    try {
      for (const file of files) {
        await uploadFolderFile(folder, file)
      }
      await tree.load()
    } catch (e) {
      window.alert(`Failed to upload: ${e instanceof Error ? e.message : String(e)}`)
    } finally {
      uploading.value = false
    }
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

  const nameDialog = useNameDialog()

  async function createPage(): Promise<void> {
    const name = await nameDialog.prompt({
      title: 'New page',
      label: 'Page name',
      placeholder: 'my_new_page',
    })
    if (!name) return
    const slug = pageNameToSlug(name)
    if (!slug) return
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
    const name = await nameDialog.prompt({
      title: 'New folder',
      label: 'Folder name',
      placeholder: 'my_folder',
    })
    if (!name) return
    const slug = pageNameToSlug(name)
    if (!slug) return
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
    const newName = await nameDialog.prompt({
      title: 'Rename',
      label: 'New path',
      initial: childPath,
      confirmLabel: 'Rename',
      slugPreview: false,
    })
    if (!newName || newName === childPath) return
    try {
      await movePage(childPath, { new_path: newName })
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
      <DirListing
        v-if="isDirectory"
        :children="directoryChildren"
        :base-path="path === 'index' ? '' : path"
        :get-child-url="getChildUrl"
        :other-files="directoryOtherFiles"
        :get-other-file-url="getOtherFileUrl"
        :get-text-file-url="getTextFileUrl"
        :uploading="uploading"
        @create-page="createPage"
        @create-folder="createFolder"
        @rename="renameChild"
        @delete="deleteChild"
        @upload="uploadFiles"
      />
    </template>
    <p v-else class="text-slate-400">Loading…</p>
  </article>
  <NameDialog
    :open="nameDialog.state.open"
    :title="nameDialog.state.title"
    :label="nameDialog.state.label"
    :placeholder="nameDialog.state.placeholder"
    :initial="nameDialog.state.initial"
    :confirm-label="nameDialog.state.confirmLabel"
    :slug-preview="nameDialog.state.slugPreview"
    @confirm="nameDialog.onConfirm"
    @cancel="nameDialog.onCancel"
  />
</template>
