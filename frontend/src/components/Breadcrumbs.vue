<script setup lang="ts">
  import { computed } from 'vue'
  import { useTreeStore } from '@/stores/tree'
  import type { PageNode } from '@/api/types'

  const props = defineProps<{
    path: string
    watchedLabel?: string
    sourceId?: string
  }>()
  const tree = useTreeStore()

  interface Crumb {
    label: string
    to: string | null
  }

  function findTitle(nodes: PageNode[], target: string): string | null {
    for (const n of nodes) {
      if (n.path === target) return n.title
      if (n.children.length) {
        const hit = findTitle(n.children, target)
        if (hit) return hit
      }
    }
    return null
  }

  function humanise(segment: string): string {
    return segment.replace(/[-_]/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
  }

  const crumbs = computed<Crumb[]>(() => {
    const segments = props.path.split('/').filter(Boolean)
    const out: Crumb[] = [{ label: 'Home', to: '/' }]

    if (props.watchedLabel) {
      out.push({
        label: props.watchedLabel,
        to: `/watch/${props.watchedLabel}/`,
      })
    }

    let acc = ''
    segments.forEach((seg, i) => {
      acc = acc ? `${acc}/${seg}` : seg
      const isLast = i === segments.length - 1
      const title = findTitle(tree.nodes, acc) ?? humanise(seg)
      if (props.watchedLabel) {
        out.push({
          label: title,
          to: isLast ? null : `/watch/${props.watchedLabel}/${acc}`,
        })
      } else if (props.sourceId) {
        out.push({
          label: title,
          to: isLast ? null : `/source/${props.sourceId}/${acc}`,
        })
      } else {
        out.push({ label: title, to: isLast ? null : `/w/${acc}` })
      }
    })
    return out
  })
</script>

<template>
  <nav aria-label="Breadcrumb" class="text-sm text-slate-500 mb-4">
    <ol class="flex flex-wrap items-center gap-1">
      <li v-for="(c, i) in crumbs" :key="i" class="flex items-center gap-1">
        <span v-if="i > 0" class="text-slate-300">/</span>
        <RouterLink v-if="c.to" :to="c.to" class="hover:text-blue-600 hover:underline">
          {{ c.label }}
        </RouterLink>
        <span v-else class="text-slate-700 font-medium">{{ c.label }}</span>
      </li>
    </ol>
  </nav>
</template>
