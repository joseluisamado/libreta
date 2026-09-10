<script setup lang="ts">
  import { computed, nextTick, ref, watch } from 'vue'
  import { useRoute, useRouter } from 'vue-router'
  import { getWatchedPage, saveWatchedPage } from '@/api/client'
  import type { PageRead } from '@/api/types'
  import { useViewMode } from '@/composables/useViewMode'
  import { useDraft } from '@/composables/useDraft'
  import {
    captureAnchor,
    restoreAnchor,
    setPendingAnchor,
    takePendingAnchor,
  } from '@/composables/useAnchorScroll'
  import Editor from '@/components/Editor/Editor.vue'
  import EditorToolbar from '@/components/Editor/EditorToolbar.vue'
  import DraftRecoveryModal from '@/components/DraftRecoveryModal.vue'

  const route = useRoute()
  const router = useRouter()
  const editorRef = ref<InstanceType<typeof Editor> | null>(null)
  const scrollEl = ref<HTMLElement | null>(null)
  const page = ref<PageRead | null>(null)
  const error = ref<string | null>(null)
  const isDirty = ref(false)
  const saving = ref(false)
  const saveError = ref<string | null>(null)

  const { mode, toggle: toggleViewMode } = useViewMode()

  const sourceText = ref('')
  const editorKey = ref(0)

  watch(mode, async (newMode) => {
    // Capture the current pane's position before Vue swaps the DOM, so the
    // rendered ↔ source toggle keeps the user on the same section.
    const anchor = scrollEl.value
      ? captureAnchor(scrollEl.value, scrollEl.value, anchorKey.value)
      : null
    if (newMode === 'source') {
      sourceText.value = editorRef.value?.getMarkdown() ?? sourceText.value
    } else {
      editorKey.value++
    }
    if (anchor) {
      await nextTick()
      if (scrollEl.value) await restoreAnchor(scrollEl.value, scrollEl.value, anchor)
    }
  })

  const label = computed(() => String(route.params.label))
  const path = computed(() => {
    const raw = route.params.path
    if (Array.isArray(raw)) return raw.join('/')
    return String(raw ?? '')
  })

  const readPagePath = computed(() => `/watch/${label.value}/${path.value}`)
  // Same identity the viewer uses, so a captured anchor is only consumed on
  // the matching page.
  const anchorKey = computed(() => `watch/${label.value}/${path.value}`)

  const draft = useDraft(() => `watch/${label.value}/${path.value}`)

  async function load(): Promise<void> {
    page.value = null
    error.value = null
    isDirty.value = false
    try {
      page.value = await getWatchedPage(label.value, path.value)
      sourceText.value = page.value.body
      // Surface any recoverable draft for this page. Deciding whether to
      // restore it is deferred to the recovery banner (continue vs. discard).
      draft.check(page.value.body)
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e)
    }
  }

  watch([label, path], load, { immediate: true })

  // Region-preserving scroll across viewer ↔ editor. The editor scrolls in its
  // own container (scrollEl); headings live inside it in both WYSIWYG (the
  // ProseMirror DOM) and — where present — the source view. Capture on the way
  // back to the viewer; consume any anchor the viewer set on the way in.
  function captureForViewer(): void {
    if (scrollEl.value)
      setPendingAnchor(captureAnchor(scrollEl.value, scrollEl.value, anchorKey.value))
  }

  watch(
    page,
    async (p) => {
      if (!p) return
      const anchor = takePendingAnchor(anchorKey.value)
      if (!anchor) return
      // Wait for the editor/source pane to render its headings before restoring.
      await nextTick()
      await nextTick()
      if (scrollEl.value) await restoreAnchor(scrollEl.value, scrollEl.value, anchor)
    },
    { flush: 'post' },
  )

  function restoreDraft(): void {
    const d = draft.pending.value
    if (!d) return
    sourceText.value = d.body
    editorKey.value++ // force the WYSIWYG editor to re-init from the draft body
    isDirty.value = true
    draft.pending.value = null // keep the stored draft; only dismiss the banner
  }

  function discardDraft(): void {
    draft.clear()
  }

  function onUpdate(markdown: string): void {
    isDirty.value = true
    draft.save(markdown)
  }

  function onSourceInput(): void {
    isDirty.value = true
    draft.save(sourceText.value)
  }

  async function onUploadFiles(files: File[]): Promise<void> {
    // Watched pages have no git-source attachment home; the editor's
    // uploadAndInsert surfaces a clear message rather than silently doing
    // nothing.
    const ed = editorRef.value
    if (!ed) return
    for (const file of files) {
      await ed.uploadAndInsert(file)
    }
  }

  function onInsertDiagram(): void {
    editorRef.value?.openInsertDiagram()
  }

  function onOpenLink(): void {
    editorRef.value?.openLinkDialog()
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
        draft.clear()
        captureForViewer()
        router.push(readPagePath.value)
        return
      }
      await saveWatchedPage(label.value, path.value, { body: md })
      draft.clear()
      captureForViewer()
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
      // Discarding means abandoning the edit; drop the recovery draft too so it
      // does not re-prompt on the next open.
      draft.clear()
    }
    captureForViewer()
    router.push(readPagePath.value)
  }
</script>

<template>
  <div class="flex flex-col h-full">
    <div class="flex items-center justify-between border-b border-slate-200 bg-white px-4 py-2">
      <div class="flex items-center gap-3">
        <span class="text-sm text-slate-400">Editing: {{ label }}/{{ path }}</span>
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

    <div ref="scrollEl" class="flex-1 overflow-y-auto">
      <p v-if="error" class="p-6 text-red-600">
        {{ error }}
        <RouterLink :to="readPagePath" class="underline ml-2">Back to page</RouterLink>
      </p>
      <template v-else-if="page">
        <DraftRecoveryModal
          :open="draft.pending.value !== null"
          :age-label="draft.pendingAgeLabel.value"
          :stale="draft.pendingIsStale.value"
          @continue="restoreDraft"
          @discard="discardDraft"
        />
        <template v-if="mode === 'rendered'">
          <EditorToolbar
            :editor="editorRef?.editor ?? null"
            @upload-files="onUploadFiles"
            @insert-diagram="onInsertDiagram"
            @open-link="onOpenLink"
          />
          <Editor
            ref="editorRef"
            :key="editorKey"
            :content="sourceText"
            :path="page.path"
            @update="onUpdate"
            @diagram-saved="onDiagramSaved"
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
