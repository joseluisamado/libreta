<script setup lang="ts">
  import { ref } from 'vue'
  import type { Editor } from '@tiptap/core'


  const props = defineProps<{
    editor: Editor | null
  }>()



  const emit = defineEmits<{
    'upload-files': [files: File[]]
  }>()

  const imageInput = ref<HTMLInputElement | null>(null)
  const fileInput = ref<HTMLInputElement | null>(null)

  function run(editor: Editor | null, fn: (ed: Editor) => void): void {
    if (!editor || editor.isDestroyed) return
    fn(editor)
  }

  function setLink(editor: Editor | null): void {
    if (!editor || editor.isDestroyed) return
    const url = window.prompt('URL:')
    if (url) {
      editor.commands.setLink({ href: url })
    } else if (url === '') {
      editor.commands.unsetLink()
    }
  }

  function pickImage(): void {
    imageInput.value?.click()
  }

  function pickFile(): void {
    fileInput.value?.click()
  }

  function onImagePicked(e: Event): void {
    const target = e.target as HTMLInputElement
    const files = Array.from(target.files ?? []).filter((f) => f.type.startsWith('image/'))
    if (files.length > 0) emit('upload-files', files)
    target.value = ''
  }

  function onFilePicked(e: Event): void {
    const target = e.target as HTMLInputElement
    const files = Array.from(target.files ?? [])
    if (files.length > 0) emit('upload-files', files)
    target.value = ''
  }
</script>

<template>
  <div
    class="sticky top-0 z-10 flex items-center gap-0.5 overflow-x-auto border-b border-slate-200 bg-white px-2 py-1.5"
  >
    <!-- Undo / Redo -->
    <button
      type="button"
      class="p-1.5 rounded hover:bg-slate-100 text-slate-600"
      title="Undo (Ctrl+Z)"
      @click="run(editor, (e) => e.commands.undo())"
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
        <polyline points="1 4 1 10 7 10" />
        <path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10" />
      </svg>
    </button>
    <button
      type="button"
      class="p-1.5 rounded hover:bg-slate-100 text-slate-600"
      title="Redo (Ctrl+Shift+Z)"
      @click="run(editor, (e) => e.commands.redo())"
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
        <polyline points="23 4 23 10 17 10" />
        <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
      </svg>
    </button>

    <!-- Separator -->
    <span class="w-px h-5 bg-slate-200 mx-1" />

    <!-- Bold, Italic, Strike, Code, Link -->
    <button
      type="button"
      class="p-1.5 rounded hover:bg-slate-100 text-slate-600"
      :class="{ 'bg-slate-200 text-slate-900': editor?.isActive('bold') }"
      title="Bold (Ctrl+B)"
      @click="run(editor, (e) => e.commands.toggleBold())"
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
        <path d="M6 4h8a4 4 0 0 1 4 4 4 4 0 0 1-4 4H6z" />
        <path d="M6 12h9a4 4 0 0 1 4 4 4 4 0 0 1-4 4H6z" />
      </svg>
    </button>
    <button
      type="button"
      class="p-1.5 rounded hover:bg-slate-100 text-slate-600"
      :class="{ 'bg-slate-200 text-slate-900': editor?.isActive('italic') }"
      title="Italic (Ctrl+I)"
      @click="run(editor, (e) => e.commands.toggleItalic())"
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
        <line x1="19" y1="4" x2="10" y2="4" />
        <line x1="14" y1="20" x2="5" y2="20" />
        <line x1="15" y1="4" x2="9" y2="20" />
      </svg>
    </button>
    <button
      type="button"
      class="p-1.5 rounded hover:bg-slate-100 text-slate-600"
      :class="{ 'bg-slate-200 text-slate-900': editor?.isActive('strike') }"
      title="Strikethrough (Ctrl+Shift+S)"
      @click="run(editor, (e) => e.commands.toggleStrike())"
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
        <line x1="4" y1="12" x2="20" y2="12" />
        <path d="M6.34 6.34A5 5 0 0 1 9 4h6a5 5 0 0 1 3.66 8.34" />
        <path d="M17.66 17.66A5 5 0 0 1 15 20H9a5 5 0 0 1-3.66-8.34" />
      </svg>
    </button>
    <button
      type="button"
      class="p-1.5 rounded hover:bg-slate-100 text-slate-600"
      :class="{ 'bg-slate-200 text-slate-900': editor?.isActive('code') }"
      title="Inline code (Ctrl+E)"
      @click="run(editor, (e) => e.commands.toggleCode())"
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
        <polyline points="16 18 22 12 16 6" />
        <polyline points="8 6 2 12 8 18" />
      </svg>
    </button>
    <button
      type="button"
      class="p-1.5 rounded hover:bg-slate-100 text-slate-600"
      :class="{ 'bg-slate-200 text-slate-900': editor?.isActive('codeBlock') }"
      title="Code block"
      @click="run(editor, (e) => e.commands.toggleCodeBlock())"
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
        <polyline points="4 7 4 4 20 4 20 7" />
        <line x1="9" y1="20" x2="15" y2="20" />
        <line x1="12" y1="4" x2="12" y2="20" />
      </svg>
    </button>

    <button
      type="button"
      class="p-1.5 rounded hover:bg-slate-100 text-slate-600"
      :class="{ 'bg-slate-200 text-slate-900': editor?.isActive('link') }"
      title="Link (Ctrl+K)"
      @click="setLink(editor)"
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
        <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
        <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
      </svg>
    </button>
    <button
      type="button"
      class="p-1.5 rounded hover:bg-slate-100 text-slate-600"
      title="Insert image"
      @click="pickImage"
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
        <rect x="3" y="5" width="18" height="14" rx="2" />
        <circle cx="8.5" cy="10.5" r="1.5" />
        <path d="M21 17l-5-5-9 9" />
      </svg>
    </button>
    <button
      type="button"
      class="p-1.5 rounded hover:bg-slate-100 text-slate-600"
      title="Attach file"
      @click="pickFile"
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
        <path
          d="M21 12.5l-8.5 8.5a5 5 0 0 1-7-7l8.5-8.5a3.5 3.5 0 0 1 5 5L10.5 19a2 2 0 0 1-3-3l8-8"
        />
      </svg>
    </button>
    <input
      ref="imageInput"
      type="file"
      accept="image/*"
      multiple
      class="hidden"
      @change="onImagePicked"
    />
    <input ref="fileInput" type="file" multiple class="hidden" @change="onFilePicked" />

    <!-- Separator -->
    <span class="w-px h-5 bg-slate-200 mx-1" />

    <!-- H1, H2, H3 -->
    <button
      type="button"
      class="p-1.5 rounded hover:bg-slate-100 text-slate-600"
      :class="{ 'bg-slate-200 text-slate-900': editor?.isActive('heading', { level: 1 }) }"
      title="Heading 1"
      @click="run(editor, (e) => e.commands.toggleHeading({ level: 1 }))"
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
        <text x="4" y="18" font-size="16" font-weight="bold" fill="currentColor" stroke="none">
          H1
        </text>
      </svg>
    </button>
    <button
      type="button"
      class="p-1.5 rounded hover:bg-slate-100 text-slate-600"
      :class="{ 'bg-slate-200 text-slate-900': editor?.isActive('heading', { level: 2 }) }"
      title="Heading 2"
      @click="run(editor, (e) => e.commands.toggleHeading({ level: 2 }))"
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
        <text x="4" y="18" font-size="14" font-weight="bold" fill="currentColor" stroke="none">
          H2
        </text>
      </svg>
    </button>
    <button
      type="button"
      class="p-1.5 rounded hover:bg-slate-100 text-slate-600"
      :class="{ 'bg-slate-200 text-slate-900': editor?.isActive('heading', { level: 3 }) }"
      title="Heading 3"
      @click="run(editor, (e) => e.commands.toggleHeading({ level: 3 }))"
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
        <text x="4" y="18" font-size="12" font-weight="bold" fill="currentColor" stroke="none">
          H3
        </text>
      </svg>
    </button>

    <!-- Separator -->
    <span class="w-px h-5 bg-slate-200 mx-1" />

    <!-- Blockquote, Bullet list, Ordered list, Task list, HR -->
    <button
      type="button"
      class="p-1.5 rounded hover:bg-slate-100 text-slate-600"
      :class="{ 'bg-slate-200 text-slate-900': editor?.isActive('blockquote') }"
      title="Blockquote (Ctrl+Shift+B)"
      @click="run(editor, (e) => e.commands.toggleBlockquote())"
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
        <rect x="4" y="6" width="3" height="14" />
        <line x1="11" y1="10" x2="20" y2="10" />
        <line x1="11" y1="14" x2="16" y2="14" />
      </svg>
    </button>
    <button
      type="button"
      class="p-1.5 rounded hover:bg-slate-100 text-slate-600"
      :class="{ 'bg-slate-200 text-slate-900': editor?.isActive('bulletList') }"
      title="Bullet list"
      @click="run(editor, (e) => e.commands.toggleBulletList())"
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
        <line x1="9" y1="6" x2="20" y2="6" />
        <line x1="9" y1="12" x2="20" y2="12" />
        <line x1="9" y1="18" x2="20" y2="18" />
        <circle cx="5" cy="6" r="1.5" fill="currentColor" stroke="none" />
        <circle cx="5" cy="12" r="1.5" fill="currentColor" stroke="none" />
        <circle cx="5" cy="18" r="1.5" fill="currentColor" stroke="none" />
      </svg>
    </button>
    <button
      type="button"
      class="p-1.5 rounded hover:bg-slate-100 text-slate-600"
      :class="{ 'bg-slate-200 text-slate-900': editor?.isActive('orderedList') }"
      title="Ordered list"
      @click="run(editor, (e) => e.commands.toggleOrderedList())"
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
        <line x1="10" y1="6" x2="20" y2="6" />
        <line x1="10" y1="12" x2="20" y2="12" />
        <line x1="10" y1="18" x2="20" y2="18" />
        <text x="3" y="10" font-size="10" fill="currentColor" stroke="none">1</text>
        <text x="3" y="16" font-size="10" fill="currentColor" stroke="none">2</text>
        <text x="3" y="22" font-size="10" fill="currentColor" stroke="none">3</text>
      </svg>
    </button>
    <button
      type="button"
      class="p-1.5 rounded hover:bg-slate-100 text-slate-600"
      :class="{ 'bg-slate-200 text-slate-900': editor?.isActive('taskList') }"
      title="Task list"
      @click="run(editor, (e) => e.commands.toggleTaskList())"
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
        <rect x="3" y="5" width="3" height="3" rx="0.5" />
        <line x1="9" y1="6.5" x2="20" y2="6.5" />
        <rect x="3" y="11" width="3" height="3" rx="0.5" />
        <line x1="9" y1="12.5" x2="20" y2="12.5" />
        <rect x="3" y="17" width="3" height="3" rx="0.5" />
        <line x1="9" y1="18.5" x2="20" y2="18.5" />
      </svg>
    </button>
    <button
      type="button"
      class="p-1.5 rounded hover:bg-slate-100 text-slate-600"
      title="Horizontal rule"
      @click="run(editor, (e) => e.commands.setHorizontalRule())"
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
        <line x1="4" y1="12" x2="20" y2="12" />
      </svg>
    </button>

    <!-- Separator -->
    <span class="w-px h-5 bg-slate-200 mx-1" />

    <!-- Table controls -->
    <button
      type="button"
      class="p-1.5 rounded hover:bg-slate-100 text-slate-600"
      title="Insert table"
      @click="run(editor, (e) => e.commands.insertTable({ rows: 3, cols: 2, withHeaderRow: true }))"
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
        <rect x="3" y="4" width="18" height="16" rx="1" />
        <line x1="3" y1="10" x2="21" y2="10" />
        <line x1="12" y1="4" x2="12" y2="20" />
      </svg>
    </button>
    <button
      type="button"
      class="p-1.5 rounded hover:bg-slate-100 text-slate-600 disabled:opacity-40 disabled:cursor-not-allowed"
      title="Add column"
      :disabled="!editor?.isActive('table')"
      @click="run(editor, (e) => e.commands.addColumnAfter())"
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
        <rect x="3" y="4" width="10" height="16" rx="1" />
        <line x1="18" y1="9" x2="18" y2="15" />
        <line x1="15" y1="12" x2="21" y2="12" />
      </svg>
    </button>
    <button
      type="button"
      class="p-1.5 rounded hover:bg-slate-100 text-slate-600 disabled:opacity-40 disabled:cursor-not-allowed"
      title="Add row"
      :disabled="!editor?.isActive('table')"
      @click="run(editor, (e) => e.commands.addRowAfter())"
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
        <rect x="3" y="4" width="18" height="10" rx="1" />
        <line x1="9" y1="19" x2="15" y2="19" />
        <line x1="12" y1="16" x2="12" y2="22" />
      </svg>
    </button>
    <button
      type="button"
      class="p-1.5 rounded hover:bg-slate-100 text-slate-600 disabled:opacity-40 disabled:cursor-not-allowed"
      title="Delete column"
      :disabled="!editor?.isActive('table')"
      @click="run(editor, (e) => e.commands.deleteColumn())"
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
        <rect x="3" y="4" width="10" height="16" rx="1" />
        <line x1="16" y1="9" x2="20" y2="13" />
        <line x1="20" y1="9" x2="16" y2="13" />
      </svg>
    </button>
    <button
      type="button"
      class="p-1.5 rounded hover:bg-slate-100 text-slate-600 disabled:opacity-40 disabled:cursor-not-allowed"
      title="Delete row"
      :disabled="!editor?.isActive('table')"
      @click="run(editor, (e) => e.commands.deleteRow())"
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
        <rect x="3" y="4" width="18" height="10" rx="1" />
        <line x1="9" y1="18" x2="13" y2="22" />
        <line x1="13" y1="18" x2="9" y2="22" />
      </svg>
    </button>
    <button
      type="button"
      class="p-1.5 rounded hover:bg-slate-100 text-slate-600 disabled:opacity-40 disabled:cursor-not-allowed"
      title="Delete table"
      :disabled="!editor?.isActive('table')"
      @click="run(editor, (e) => e.commands.deleteTable())"
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
        <rect x="3" y="4" width="18" height="16" rx="1" />
        <line x1="3" y1="10" x2="21" y2="10" />
        <line x1="12" y1="4" x2="12" y2="20" />
        <line x1="6" y1="2" x2="18" y2="22" stroke="#dc2626" />
      </svg>
    </button>
  </div>
</template>
