<script setup lang="ts">
  import { computed, ref, watch } from 'vue'
  import { useRoute } from 'vue-router'
  import { getPage } from '@/api/client'
  import type { PageNode, PageRead } from '@/api/types'
  import { renderMarkdown } from '@/markdown'
  import { useTreeStore } from '@/stores/tree'
  import Breadcrumbs from '@/components/Breadcrumbs.vue'

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

  const html = computed(() => (page.value ? renderMarkdown(page.value.body, page.value.path) : ''))
</script>

<template>
  <article class="max-w-3xl mx-auto px-8 py-6">
    <p v-if="error" class="text-red-600">{{ error }}</p>
    <template v-else-if="page">
      <Breadcrumbs :path="page.path" />
      <header class="mb-4">
        <h1 class="text-3xl font-bold">{{ page.meta.title }}</h1>
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
              class="text-slate-700 hover:text-blue-600 hover:underline"
            >
              <span v-if="child.is_directory" class="text-slate-400 mr-1">📁</span>
              {{ child.title }}
            </RouterLink>
          </li>
        </ul>
      </section>
    </template>
    <p v-else class="text-slate-400">Loading…</p>
  </article>
</template>
