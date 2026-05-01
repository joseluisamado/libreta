<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { getPage } from '@/api/client'
import type { PageRead } from '@/api/types'
import { renderMarkdown } from '@/markdown'

const route = useRoute()
const page = ref<PageRead | null>(null)
const error = ref<string | null>(null)

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

const html = computed(() => (page.value ? renderMarkdown(page.value.body) : ''))
</script>

<template>
  <article class="max-w-3xl mx-auto px-8 py-6">
    <p v-if="error" class="text-red-600">{{ error }}</p>
    <template v-else-if="page">
      <header class="mb-4">
        <h1 class="text-3xl font-bold">{{ page.meta.title }}</h1>
        <p v-if="page.meta.tags.length" class="mt-2 text-xs text-slate-500">
          <span v-for="t in page.meta.tags" :key="t" class="mr-2">#{{ t }}</span>
        </p>
      </header>
      <div class="prose" v-html="html" />
    </template>
    <p v-else class="text-slate-400">Loading…</p>
  </article>
</template>
