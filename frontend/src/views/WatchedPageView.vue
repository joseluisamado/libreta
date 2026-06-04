<script setup lang="ts">
  import { computed, ref, watch, nextTick } from 'vue'
  import { useRoute, useRouter } from 'vue-router'
  import {
    getWatchedPage,
    saveWatchedPage,
    createWatchedFolder,
    deleteWatchedPage,
    uploadWatchedFolderFile,
    getWatchedChildren,
  } from '@/api/client'
  import { useWatchedStore } from '@/stores/watched'
  import type { DirChildren, OtherFile, PageNode, PageRead } from '@/api/types'
  import { renderMarkdown, renderMermaidIn } from '@/markdown'
  import { isTextPath } from '@/textFiles'
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
  const watched = useWatchedStore()
  const page = ref<PageRead | null>(null)
  const error = ref<string | null>(null)
  const contentEl = ref<HTMLElement | null>(null)

  const label = computed(() => String(route.params.label))
  const path = computed(() => {
    const raw = route.params.path
    if (Array.isArray(raw)) return raw.join('/')
    return String(raw ?? '')
  })

  async function load(): Promise<void> {
    if (path.value.toLowerCase().endsWith('.pdf')) {
      router.replace(`/pdf-watch/${label.value}/${path.value}`)
      return
    }
    if (isTextPath(path.value)) {
      router.replace({
        path: `/text-watch/${label.value}/${path.value}`,
        hash: route.hash,
      })
      return
    }
    page.value = null
    error.value = null
    rootListing.value = null
    try {
      page.value = await getWatchedPage(label.value, path.value)
      // Load tree so we can detect directory status
      if (!watched.trees[label.value]) {
        await watched.loadTree(label.value)
      }
      // The initial tree is depth-limited; expand each ancestor of the
      // current path so deep directories list their children correctly.
      if (page.value && path.value) {
        await watched.ensurePathExpanded(label.value, path.value)
      } else if (page.value) {
        // Watched root: no tree node for "" — fetch its children directly.
        rootListing.value = await getWatchedChildren(label.value, '')
      }
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e)
    }
  }

  // Populated only when viewing the watched root (path === "").
  const rootListing = ref<DirChildren | null>(null)

  watch([label, path], load, { immediate: true })

  // ----- Directory detection -----------------------------------------------

  function findNode(nodes: PageNode[], target: string): PageNode | null {
    for (const n of nodes) {
      if (n.path === target) return n
      if (n.children?.length || n.has_more) {
        const hit = findNode(n.children, target)
        if (hit) return hit
      }
    }
    return null
  }

  const dirNode = computed<PageNode | null>(() => {
    if (!page.value) return null
    const tree = watched.trees[label.value]
    if (!tree) return null
    return findNode(tree, page.value.path)
  })

  const isDirectory = computed(() => {
    if (path.value === '') return true // watched root is always a directory
    return dirNode.value?.is_directory ?? false
  })

  const dirChildren = computed<PageNode[]>(() => {
    if (path.value === '') return rootListing.value?.children ?? []
    if (!dirNode.value?.is_directory) return []
    return dirNode.value.children
  })

  const dirOtherFiles = computed<OtherFile[]>(() => {
    if (path.value === '') return rootListing.value?.other_files ?? []
    return dirNode.value?.other_files ?? []
  })

  function getOtherFileUrl(filePath: string): string {
    return `/api/v1/watch/${label.value}/assets/${encodeURIComponent(filePath)}`
  }

  function getTextFileUrl(filePath: string): string {
    return `/text-watch/${label.value}/${filePath}`
  }

  function getChildRawUrl(childPath: string): string {
    const segments = childPath.split('/').map(encodeURIComponent).join('/')
    return `/api/v1/watch/${encodeURIComponent(label.value)}/raw/${segments}`
  }

  const basePath = computed(() => (path.value === '' ? '' : path.value))

  function getChildUrl(childPath: string): string {
    if (childPath.toLowerCase().endsWith('.pdf')) {
      return `/pdf-watch/${label.value}/${childPath}`
    }
    return `/watch/${label.value}/${childPath}`
  }

  const nameDialog = useNameDialog()

  // ----- Actions -----------------------------------------------------------

  async function onCreatePage(): Promise<void> {
    const name = await nameDialog.prompt({
      title: 'New page',
      label: 'Page name',
      placeholder: 'my_new_page',
    })
    if (!name) return
    const slug = pageNameToSlug(name)
    if (!slug) return
    const prefix = basePath.value
    const newPath = prefix ? `${prefix}/${slug}` : slug
    try {
      await saveWatchedPage(label.value, newPath, {
        body: `# ${name.trim()}\n\n`,
      })
      await watched.loadTree(label.value)
      router.push(`/edit-watch/${label.value}/${newPath}`)
    } catch (e) {
      window.alert(`Failed to create page: ${e instanceof Error ? e.message : String(e)}`)
    }
  }

  async function onCreateFolder(): Promise<void> {
    const name = await nameDialog.prompt({
      title: 'New folder',
      label: 'Folder name',
      placeholder: 'my_folder',
    })
    if (!name) return
    const slug = pageNameToSlug(name)
    if (!slug) return
    const prefix = basePath.value
    const newPath = prefix ? `${prefix}/${slug}` : slug
    try {
      await createWatchedFolder(label.value, newPath)
      await watched.loadTree(label.value)
    } catch (e) {
      window.alert(`Failed to create folder: ${e instanceof Error ? e.message : String(e)}`)
    }
  }

  async function onDelete(childPath: string): Promise<void> {
    if (!window.confirm(`Delete "${childPath}"?`)) return
    try {
      await deleteWatchedPage(label.value, childPath)
      await watched.loadTree(label.value)
    } catch (e) {
      window.alert(`Failed to delete: ${e instanceof Error ? e.message : String(e)}`)
    }
  }

  const uploading = ref(false)

  async function onUpload(files: File[]): Promise<void> {
    uploading.value = true
    try {
      for (const file of files) {
        await uploadWatchedFolderFile(label.value, basePath.value, file)
      }
      await watched.loadTree(label.value)
      if (path.value === '') {
        rootListing.value = await getWatchedChildren(label.value, '')
      } else {
        await watched.loadTreeChildren(label.value, path.value)
      }
    } catch (e) {
      window.alert(`Failed to upload: ${e instanceof Error ? e.message : String(e)}`)
    } finally {
      uploading.value = false
    }
  }

  // ----- Rendering ----------------------------------------------------------

  // Render the frontmatter title as <h1> only when the body has no H1 of
  // its own. If the markdown begins with `# Heading`, that *is* the page
  // title — surfacing meta.title above it would just duplicate the header.
  const bodyHasH1 = computed(() => {
    if (!page.value) return false
    const firstLine = page.value.body.trimStart().split('\n', 1)[0] ?? ''
    return firstLine.startsWith('# ')
  })

  const html = computed(() => {
    if (!page.value) return ''
    return renderMarkdown(page.value.body, page.value.path, undefined, label.value)
  })

  watch([html, mode], async () => {
    await nextTick()
    if (mode.value === 'rendered' && contentEl.value) await renderMermaidIn(contentEl.value)
  })

  const highlightedSource = computed(() => {
    if (!page.value) return ''
    return hljs.highlight(page.value.body, { language: 'markdown' }).value
  })

  const downloadUrl = computed(() => {
    if (!page.value) return ''
    const segments = page.value.path.split('/').map(encodeURIComponent).join('/')
    return `/api/v1/watch/${encodeURIComponent(label.value)}/raw/${segments}`
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
    :to="`/edit-watch/${label}/${page.path}`"
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
  <a
    v-if="page && !isDirectory"
    :href="downloadUrl"
    download
    class="fixed top-3 right-[156px] z-20 bg-white/90 backdrop-blur border border-slate-200 rounded-md p-2 hover:bg-slate-50 shadow-sm"
    title="Download markdown"
    aria-label="Download markdown"
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
  <PageToc v-if="page" :html="html" />
  <article class="mx-auto px-8 py-6" :class="width === 'wide' ? 'max-w-none' : 'max-w-3xl'">
    <p v-if="error" class="text-red-600">{{ error }}</p>
    <template v-else-if="page">
      <header
        class="flex items-center justify-between mb-4"
        :class="width === 'wide' ? 'pr-48' : ''"
      >
        <Breadcrumbs :path="page.path" :watched-label="label" />
      </header>
      <h1 v-if="!bodyHasH1" class="text-3xl font-bold">{{ page.meta.title }}</h1>

      <!-- Directory listing -->
      <DirListing
        v-if="isDirectory"
        :children="dirChildren"
        :base-path="basePath"
        :get-child-url="getChildUrl"
        :other-files="dirOtherFiles"
        :get-other-file-url="getOtherFileUrl"
        :get-text-file-url="getTextFileUrl"
        :get-child-raw-url="getChildRawUrl"
        :uploading="uploading"
        @create-page="onCreatePage"
        @create-folder="onCreateFolder"
        @delete="onDelete"
        @upload="onUpload"
      />

      <div v-if="mode === 'rendered' && page.body" ref="contentEl" class="prose" v-html="html" />
      <pre
        v-else-if="mode === 'source' && page.body"
        class="bg-[#f6f8fa] rounded-md p-6 overflow-auto text-sm leading-relaxed border border-slate-200"
      ><code class="hljs language-markdown" v-html="highlightedSource" /></pre>
      <p v-if="page.meta.tags.length" class="mt-8 text-xs text-slate-500">
        <span v-for="t in page.meta.tags" :key="t" class="mr-2">#{{ t }}</span>
      </p>
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
