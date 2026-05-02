<script setup lang="ts">
  import { watch, ref, computed, onBeforeUnmount } from 'vue'
  import { useEditor, EditorContent } from '@tiptap/vue-3'
  import StarterKit from '@tiptap/starter-kit'
  import TaskList from '@tiptap/extension-task-list'
  import TaskItem from '@tiptap/extension-task-item'
  import Link from '@tiptap/extension-link'
  import { Table, TableRow, TableHeader, TableCell } from '@tiptap/extension-table'
  import { Markdown } from 'tiptap-markdown'
  import type { Editor as TiptapEditor } from '@tiptap/core'
  import { getMarkdownFromStorage } from '@/markdownStorage'

  const props = defineProps<{
    content: string
    path: string
  }>()

  const emit = defineEmits<{
    update: [markdown: string]
  }>()

  const hasBeenSet = ref(false)

  const editor = useEditor({
    extensions: [
      StarterKit.configure({
        heading: { levels: [1, 2, 3] },
        // Exclude built-in link so we configure @tiptap/extension-link explicitly
        link: false,
      }),
      TaskList,
      TaskItem.configure({
        nested: true,
      }),
      Link.configure({
        openOnClick: false,
        autolink: true,
      }),
      Table.configure({
        resizable: false,
      }),
      TableRow,
      TableHeader,
      TableCell,
      Markdown.configure({
        html: false,
      }),
    ],
    content: props.content,
    onUpdate: () => {
      if (!hasBeenSet.value) return
      if (!editor.value || editor.value.isDestroyed) return
      const md = getMarkdownFromStorage(editor.value)
      if (md) {
        emit('update', md)
      }
    },
  })

  // Watch for page navigation: load new content without marking dirty
  watch(
    () => props.content,
    (newContent) => {
      if (!editor.value || editor.value.isDestroyed) return
      hasBeenSet.value = false
      editor.value.commands.setContent(newContent)
      // Mark as set after a tick so that onUpdate does not fire for the initial load
      requestAnimationFrame(() => {
        hasBeenSet.value = true
      })
    },
  )

  // After initial mount, mark as set
  watch(
    editor,
    (ed) => {
      if (ed) {
        requestAnimationFrame(() => {
          hasBeenSet.value = true
        })
      }
    },
    { immediate: true },
  )

  onBeforeUnmount(() => {
    editor.value?.destroy()
  })

  function getMarkdown(): string {
    if (!editor.value || editor.value.isDestroyed) return props.content
    return getMarkdownFromStorage(editor.value) || props.content
  }

  const editorInstance = computed(() => editor.value ?? null)

  defineExpose({ getMarkdown, editor: editorInstance })
</script>

<template>
  <div class="libreta-editor prose max-w-none">
    <EditorContent :editor="editor" />
  </div>
</template>

<style scoped>
  .libreta-editor :deep(.ProseMirror) {
    min-height: 20rem;
    outline: none;
    padding: 0;
  }

  .libreta-editor :deep(.ProseMirror p.is-editor-empty:first-child::before) {
    content: attr(data-placeholder);
    float: left;
    color: #94a3b8;
    pointer-events: none;
    height: 0;
  }

  .libreta-editor :deep(h1) {
    font-size: 1.875rem;
    font-weight: 700;
    margin-top: 1.5rem;
    margin-bottom: 0.5rem;
  }

  .libreta-editor :deep(h2) {
    font-size: 1.5rem;
    font-weight: 600;
    margin-top: 1.25rem;
    margin-bottom: 0.5rem;
  }

  .libreta-editor :deep(h3) {
    font-size: 1.25rem;
    font-weight: 600;
    margin-top: 1rem;
    margin-bottom: 0.5rem;
  }

  .libreta-editor :deep(p) {
    margin-top: 0.5rem;
    margin-bottom: 0.5rem;
  }

  .libreta-editor :deep(ul),
  .libreta-editor :deep(ol) {
    padding-left: 1.5rem;
  }

  .libreta-editor :deep(blockquote) {
    border-left: 3px solid #e2e8f0;
    padding-left: 1rem;
    color: #475569;
  }

  .libreta-editor :deep(pre) {
    background-color: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 0.375rem;
    padding: 0.75rem 1rem;
    overflow-x: auto;
  }

  .libreta-editor :deep(code) {
    background-color: #f1f5f9;
    border-radius: 0.25rem;
    padding: 0.125rem 0.25rem;
    font-size: 0.875em;
  }

  .libreta-editor :deep(pre code) {
    background-color: transparent;
    padding: 0;
  }

  .libreta-editor :deep(hr) {
    border: none;
    border-top: 1px solid #e2e8f0;
    margin: 1.5rem 0;
  }

  .libreta-editor :deep(a) {
    color: #2563eb;
    text-decoration: underline;
  }

  .libreta-editor :deep(s) {
    text-decoration: line-through;
  }

  .libreta-editor :deep(ul[data-type='taskList']) {
    list-style: none;
    padding-left: 0;
  }

  .libreta-editor :deep(ul[data-type='taskList'] li) {
    display: flex;
    align-items: flex-start;
    gap: 0.5rem;
  }

  .libreta-editor :deep(ul[data-type='taskList'] li label) {
    margin-top: 0.25rem;
  }

  .libreta-editor :deep(table) {
    border-collapse: collapse;
    margin: 0.75rem 0;
    width: auto;
    table-layout: fixed;
    overflow: hidden;
  }

  .libreta-editor :deep(table td),
  .libreta-editor :deep(table th) {
    border: 1px solid #cbd5e1;
    padding: 0.4rem 0.6rem;
    vertical-align: top;
    min-width: 4rem;
  }

  .libreta-editor :deep(table th) {
    background-color: #f1f5f9;
    font-weight: 600;
    text-align: left;
  }

  .libreta-editor :deep(.tableWrapper) {
    overflow-x: auto;
  }

  .libreta-editor :deep(.selectedCell::after) {
    content: '';
    position: absolute;
    inset: 0;
    background: rgba(37, 99, 235, 0.12);
    pointer-events: none;
  }

  .libreta-editor :deep(table .selectedCell) {
    position: relative;
  }
</style>
