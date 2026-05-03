<script setup lang="ts">
  import { computed, ref, watch } from 'vue'
  import { useRoute, useRouter } from 'vue-router'
  import { getPage, savePage } from '@/api/client'
  import type { PageRead } from '@/api/types'
  import { useViewMode } from '@/composables/useViewMode'
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

  const { mode, toggle: toggleViewMode } = useViewMode()

  // Source-mode textarea content — kept in sync with page load
  const sourceText = ref('')
  // Force-remount the Tiptap editor when switching back from source mode
  const editorKey = ref(0)

  // Sync content when switching modes
  watch(mode, (newMode) => {
    if (newMode === 'source') {
      // Pull latest markdown from Tiptap before showing source
      sourceText.value = editorRef.value?.getMarkdown() ?? sourceText.value
    } else {
      // Force Editor remount with updated source content
      editorKey.value++
    }
  })

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
      sourceText.value = page.value.body
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e)
    }
  }

  watch(path, load, { immediate: true })

  function onUpdate(_markdown: string): void {
    isDirty.value = true
  }

  function onSourceInput(): void {
    isDirty.value = true
  }

  async function onUploadFiles(files: File[]): Promise<void> {
    const ed = editorRef.value
    if (!ed) return
    for (const f of files) {
      await ed.uploadAndInsert(f)
    }
  }

  async function save(): Promise<void> {
    saving.value = true
    saveError.value = null
    try {
      const md = mode.value === 'source' ? sourceText.value : editorRef.value?.getMarkdown()
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
      <div class="flex items-center gap-3">
        <span class="text-sm text-slate-400">Editing: {{ path }}</span>
        <button
          type="button"
          class="text-xs px-2 py-1 rounded border border-slate-200 text-slate-500 hover:bg-slate-50 cursor-pointer"
          :title="mode === 'rendered' ? 'Edit markdown source' : 'Use WYSIWYG editor'"
          @click="toggleViewMode"
        >
          {{ mode === 'rendered' ? 'Source' : 'WYSIWYG' }}
        </button>
      </div>
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
        <template v-if="mode === 'rendered'">
          <EditorToolbar :editor="editorRef?.editor ?? null" @upload-files="onUploadFiles" />
          <Editor
            ref="editorRef"
            :key="editorKey"
            :content="sourceText"
            :path="page.path"
            :is-index="page.is_index"
            @update="onUpdate"
            class="px-8 py-6"
          />
        </template>
        <textarea
          v-else
          v-model="sourceText"
          class="w-full h-full min-h-[60vh] p-6 font-mono text-sm leading-relaxed resize-none focus:outline-none border-0 bg-[#f6f8fa] text-slate-800"
          spellcheck="false"
          @input="onSourceInput"
        />
      </template>
      <p v-else class="p-6 text-slate-400">Loading...</p>
    </div>
  </div>
</template>
