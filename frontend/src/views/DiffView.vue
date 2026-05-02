<script setup lang="ts">
  import { computed, ref, watch } from 'vue'
  import { useRoute } from 'vue-router'
  import { getPageDiff } from '@/api/client'
  import type { DiffEntry } from '@/api/types'

  type Line = { kind: 'context' | 'add' | 'del' | 'hunk' | 'meta'; text: string }

  const route = useRoute()
  const diff = ref<DiffEntry | null>(null)
  const error = ref<string | null>(null)

  const path = computed(() => {
    const raw = route.params.path
    if (Array.isArray(raw)) return raw.join('/')
    return String(raw ?? 'index')
  })

  const a = computed(() => String(route.query.a ?? ''))
  const b = computed(() => String(route.query.b ?? ''))

  async function load(): Promise<void> {
    diff.value = null
    error.value = null
    if (!a.value || !b.value) {
      error.value = 'Missing revision parameters (a, b).'
      return
    }
    try {
      diff.value = await getPageDiff(path.value, a.value, b.value)
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e)
    }
  }

  watch([path, a, b], load, { immediate: true })

  function classify(line: string): Line {
    if (line.startsWith('+++') || line.startsWith('---')) return { kind: 'meta', text: line }
    if (line.startsWith('@@')) return { kind: 'hunk', text: line }
    if (line.startsWith('+')) return { kind: 'add', text: line }
    if (line.startsWith('-')) return { kind: 'del', text: line }
    return { kind: 'context', text: line }
  }

  const lines = computed<Line[]>(() => {
    if (!diff.value || !diff.value.patch) return []
    return diff.value.patch
      .split('\n')
      .filter((l, i, arr) => !(i === arr.length - 1 && l === ''))
      .map(classify)
  })
</script>

<template>
  <article class="mx-auto max-w-5xl px-8 py-6">
    <header class="mb-6">
      <RouterLink :to="`/history/${path}`" class="text-sm text-blue-600 hover:underline">
        &larr; Back to history
      </RouterLink>
      <h1 class="text-2xl font-bold mt-2">Diff</h1>
      <p class="text-sm text-slate-500">
        {{ path }}
        <span v-if="a && b"
          >— <code>{{ a }}</code> &rarr; <code>{{ b }}</code></span
        >
      </p>
    </header>

    <p v-if="error" class="text-red-600">{{ error }}</p>

    <p v-else-if="diff === null" class="text-slate-400">Loading&hellip;</p>

    <p v-else-if="!diff.patch" class="text-slate-400">No differences between these revisions.</p>

    <div
      v-else
      class="diff-view text-xs font-mono border border-slate-200 rounded-lg overflow-x-auto whitespace-pre"
    >
      <div
        v-for="(line, i) in lines"
        :key="i"
        :class="{
          'px-3 py-px': true,
          'bg-green-50 text-green-900': line.kind === 'add',
          'bg-red-50 text-red-900': line.kind === 'del',
          'bg-blue-50 text-blue-900 font-semibold': line.kind === 'hunk',
          'text-slate-500': line.kind === 'meta',
          'text-slate-800': line.kind === 'context',
        }"
      >
        {{ line.text || ' ' }}
      </div>
    </div>
  </article>
</template>

<style scoped>
  .diff-view {
    background: #fafafa;
    line-height: 1.5;
  }
</style>
