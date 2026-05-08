<script setup lang="ts">
  import { computed, ref, watch } from 'vue'
  import { useRoute, useRouter } from 'vue-router'
  import { getSourcePage, saveSourcePage } from '@/api/client'
  import type { PageRead } from '@/api/types'
  import { useViewMode } from '@/composables/useViewMode'
  import Editor from '@/components/Editor/Editor.vue'
  import EditorToolbar from '@/components/Editor/EditorToolbar.vue'
  import { useSourcesStore } from '@/stores/sources'

  const sourcesStore = useSourcesStore()

  const route = useRoute()
  const router = useRouter()
  const editorRef = ref<InstanceType<typeof Editor> | null>(null)
  const page = ref<PageRead | null>(null)
  const error = ref<string | null>(null)
  const isDirty = ref(false)
  const saving = ref(false)
  const saveError = ref<string | null>(null)

  const { mode, toggle: toggleViewMode } = useViewMode()

  const sourceText = ref('')
  const editorKey = ref(0)

  watch(mode, (newMode) => {
    if (newMode === 'source') {
      sourceText.value = editorRef.value?.getMarkdown() ?? sourceText.value
    } else {
      editorKey.value++
    }
  })

  const sourceId = computed(() => String(route.params.sourceId))
  const path = computed(() => {
    const raw = route.params.path
    if (Array.isArray(raw)) return raw.join('/')
    return String(raw ?? '')
  })

  const readPagePath = computed(() => `/source/${sourceId.value}/${path.value}`)

  async function load(): Promise<void> {
    page.value = null
    error.value = null
    isDirty.value = false
    try {
      page.value = await getSourcePage(sourceId.value, path.value)
      sourceText.value = page.value.body
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e)
    }
  }

  watch([sourceId, path], load, { immediate: true })

  function onUpdate(_markdown: string): void {
    isDirty.value = true
  }

  function onSourceInput(): void {
    isDirty.value = true
  }

  async function onUploadFiles(files: File[]): Promise<void> {
    // Upload not yet supported for git source pages
    void files
  }

  function onInsertDiagram(): void {
    editorRef.value?.openInsertDiagram()
  }

  function onDiagramSaved(): void {
    isDirty.value = true
  }

  async function save(): Promise<void> {
    saving.value = true
    saveError.value = null
    try {
      const md = mode.value === 'source' ? sourceText.value : editorRef.value?.getMarkdown()
      if (md === undefined) {
        throw new Error('Editor is not ready')
      }
      // no-op save: the body hasn't changed (e.g. only a diagram
      // was re-saved, which committed itself via the asset endpoint).
      // Skip the page write so we don't pile on an empty markdown commit.
      if (page.value && md === page.value.body) {
        isDirty.value = false
        // The diagram-save path committed an asset; refresh the sources
        // list so the sidebar's pending count reflects that new commit.
        void sourcesStore.loadSources()
        router.push(readPagePath.value)
        return
      }
      await saveSourcePage(sourceId.value, path.value, { body: md })
      // Refresh the sources list so the sidebar's pending count picks up
      // the new commit immediately rather than waiting for the next poll.
      void sourcesStore.loadSources()
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
    <div class="flex items-center justify-between border-b border-slate-200 bg-white px-4 py-2">
      <div class="flex items-center gap-3">
        <span class="text-sm text-slate-400">Editing: {{ sourceId }}/{{ path }}</span>
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

    <div class="flex-1 overflow-y-auto">
      <p v-if="error" class="p-6 text-red-600">
        {{ error }}
        <RouterLink :to="readPagePath" class="underline ml-2">Back to page</RouterLink>
      </p>
      <template v-else-if="page">
        <template v-if="mode === 'rendered'">
          <EditorToolbar
            :editor="editorRef?.editor ?? null"
            @upload-files="onUploadFiles"
            @insert-diagram="onInsertDiagram"
          />
          <Editor
            ref="editorRef"
            :key="editorKey"
            :content="sourceText"
            :path="page.path"
            :source-id="sourceId"
            class="px-8 py-6"
            @update="onUpdate"
            @diagram-saved="onDiagramSaved"
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
