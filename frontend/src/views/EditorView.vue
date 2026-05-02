<script setup lang="ts">
  import { computed, ref, watch } from 'vue'
  import { useRoute, RouterLink } from 'vue-router'
  import { getPage } from '@/api/client'
  import type { PageRead } from '@/api/types'
  import Editor from '@/components/Editor/Editor.vue'
  import EditorToolbar from '@/components/Editor/EditorToolbar.vue'

  const route = useRoute()
  const editorRef = ref<InstanceType<typeof Editor> | null>(null)
  const page = ref<PageRead | null>(null)
  const error = ref<string | null>(null)
  const isDirty = ref(false)

  const path = computed(() => {
    const raw = route.params.path
    if (Array.isArray(raw)) return raw.join('/')
    return String(raw ?? 'index')
  })

  const readPagePath = computed(() => `/w/${path.value}`)

  async function load(): Promise<void> {
    page.value = null
    error.value = null
    isDirty.value = false
    try {
      page.value = await getPage(path.value)
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e)
    }
  }

  watch(path, load, { immediate: true })

  function onUpdate(_markdown: string): void {
    isDirty.value = true
  }
</script>

<template>
  <div class="flex flex-col h-full">
    <!-- Top bar -->
    <div class="flex items-center justify-between border-b border-slate-200 bg-white px-4 py-2">
      <RouterLink
        :to="readPagePath"
        class="text-sm text-slate-500 hover:text-slate-700 flex items-center gap-1"
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          class="w-4 h-4"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          stroke-linecap="round"
          stroke-linejoin="round"
        >
          <line x1="18" y1="6" x2="6" y2="18" />
          <line x1="6" y1="6" x2="18" y2="18" />
        </svg>
        Cancel
      </RouterLink>
      <button
        type="button"
        class="px-3 py-1 text-sm rounded-md bg-slate-200 text-slate-400 cursor-not-allowed"
        disabled
        title="Save is not yet implemented"
      >
        Save
      </button>
    </div>

    <!-- Content area -->
    <div class="flex-1 overflow-y-auto">
      <p v-if="error" class="p-6 text-red-600">
        {{ error }}
        <RouterLink :to="readPagePath" class="underline ml-2">Back to page</RouterLink>
      </p>
      <template v-else-if="page">
        <EditorToolbar :editor="editorRef?.editor ?? null" />
        <Editor
          ref="editorRef"
          :content="page.body"
          :path="page.path"
          @update="onUpdate"
          class="px-8 py-6"
        />
      </template>
      <p v-else class="p-6 text-slate-400">Loading...</p>
    </div>
  </div>
</template>
