<script setup lang="ts">
  import type { Editor } from '@tiptap/core'

  defineProps<{
    editor: Editor | null
  }>()

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
</script>

<template>
  <div
    class="flex items-center gap-0.5 overflow-x-auto border-b border-slate-200 bg-white px-2 py-1.5"
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
  </div>
</template>
