<script setup lang="ts">
  import { computed, ref, watch } from 'vue'
  import { useRoute } from 'vue-router'
  import { getPage } from '@/api/client'
  import type { PageNode, PageRead } from '@/api/types'
  import { renderMarkdown } from '@/markdown'
  import { useTreeStore } from '@/stores/tree'
  import { useReadingWidth } from '@/composables/usePrefs'
  import Breadcrumbs from '@/components/Breadcrumbs.vue'
  import PageToolbar from '@/components/PageToolbar.vue'
  import PageToc from '@/components/PageToc.vue'

  const { width } = useReadingWidth()

  const route = useRoute()
  const tree = useTreeStore()
  const page = ref<PageRead | null>(null)
  const error = ref<string | null>(null)

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

  const path = computed(() => {
    const raw = route.params.path
    if (Array.isArray(raw)) return raw.join('/')
    return String(raw ?? 'index')
  })

  async function load(): Promise<void> {
    page.value = null
    error.value = null
    try {
      page.value = await getPage(path.value)
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e)
    }
  }

  watch(path, load, { immediate: true })

  // If the body already starts with an H1 matching the frontmatter title,
  // skip rendering a chrome H1 above it to avoid the duplicated heading.
  const bodyHasMatchingH1 = computed(() => {
    if (!page.value) return false
    const firstLine = page.value.body.trimStart().split('\n', 1)[0] ?? ''
    if (!firstLine.startsWith('# ')) return false
    return firstLine.slice(2).trim() === page.value.meta.title
  })

  const html = computed(() =>
    page.value ? renderMarkdown(page.value.body, page.value.path, page.value.is_index) : '',
  )
</script>

<template>
  <PageToolbar />
  <PageToc v-if="page" :html="html" />
  <article class="mx-auto px-8 py-6" :class="width === 'wide' ? 'max-w-none' : 'max-w-3xl'">
    <p v-if="error" class="text-red-600">{{ error }}</p>
    <template v-else-if="page">
      <Breadcrumbs :path="page.path" />
      <header v-if="!bodyHasMatchingH1 || page.meta.tags.length" class="mb-4">
        <h1 v-if="!bodyHasMatchingH1" class="text-3xl font-bold">{{ page.meta.title }}</h1>
        <p v-if="page.meta.tags.length" class="mt-2 text-xs text-slate-500">
          <span v-for="t in page.meta.tags" :key="t" class="mr-2">#{{ t }}</span>
        </p>
      </header>
      <div class="prose" v-html="html" />
      <section v-if="directoryChildren.length" class="mt-8 border-t border-slate-200 pt-4">
        <h2 class="text-sm font-semibold uppercase tracking-wide text-slate-500 mb-2">
          In this folder
        </h2>
        <ul class="text-sm space-y-1">
          <li v-for="child in directoryChildren" :key="child.path">
            <RouterLink
              :to="`/w/${child.path}`"
              class="flex items-center text-slate-700 hover:text-blue-600 hover:underline"
            >
              <span class="inline-block w-6 shrink-0 text-slate-400">
                <span v-if="child.children.length">📁</span>
              </span>
              {{ child.title }}
            </RouterLink>
          </li>
        </ul>
      </section>
    </template>
    <p v-else class="text-slate-400">Loading…</p>
  </article>
</template>
