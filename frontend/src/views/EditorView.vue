<script setup lang="ts">
  import { computed, ref, watch } from 'vue'
  import { useRoute, useRouter } from 'vue-router'
  import { getPage, savePage } from '@/api/client'
  import type { PageRead } from '@/api/types'
  import Editor from '@/components/Editor/Editor.vue'
  import EditorToolbar from '@/components/Editor/EditorToolbar.vue'

  const route = useRoute()
  const router = useRouter()
  const editorRef = ref<InstanceType<typeof Editor> | null>(null)
  const page = ref<PageRead | null>(null)
  const error = ref<string | null>(null)
  const isDirty = ref(false)
  const saving = ref(false)
  const saveError = ref<string | null>(null)

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

  async function save(): Promise<void> {
    saving.value = true
    saveError.value = null
    try {
      const md = editorRef.value?.getMarkdown()
      if (md === undefined) {
        throw new Error('Editor is not ready')
      }
      await savePage(path.value, { body: md })
      router.push(readPagePath.value)
    } catch (e) {
      saveError.value = e instanceof Error ? e.message : String(e)
      saving.value = false
    }
  }

  function cancel(): void {
    if (isDirty.value) {
      const ok = window.confirm('You have unsaved changes. Discard them?')
      if (!ok) return
    }
    router.push(readPagePath.value)
  }
</script>

<template>
  <div class="flex flex-col h-full">
    <!-- Top bar -->
    <div class="flex items-center justify-between border-b border-slate-200 bg-white px-4 py-2">
      <span class="text-sm text-slate-400">Editing: {{ path }}</span>
      <div class="flex items-center gap-2">
        <p v-if="saveError" class="text-xs text-red-600">{{ saveError }}</p>
        <button
          type="button"
          class="px-3 py-1 text-sm rounded-md transition-colors border border-slate-300 text-slate-600 hover:bg-slate-50 cursor-pointer"
          @click="cancel"
        >
          Cancel
        </button>
        <button
          type="button"
          :class="[
            'px-3 py-1 text-sm rounded-md transition-colors',
            saving
              ? 'bg-slate-200 text-slate-400 cursor-wait'
              : isDirty
                ? 'bg-blue-600 text-white hover:bg-blue-700 cursor-pointer'
                : 'bg-slate-200 text-slate-400 cursor-default',
          ]"
          :disabled="!isDirty || saving"
          @click="save"
        >
          <span v-if="saving" class="flex items-center gap-1">
            <svg
              class="w-3.5 h-3.5 animate-spin"
              xmlns="http://www.w3.org/2000/svg"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
              stroke-linejoin="round"
            >
              <path d="M21 12a9 9 0 1 1-6.219-8.56" />
            </svg>
            Saving…
          </span>
          <span v-else>Save</span>
        </button>
      </div>
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
