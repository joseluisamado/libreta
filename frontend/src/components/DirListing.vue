<script setup lang="ts">
  import type { OtherFile, PageNode } from '@/api/types'

  defineProps<{
    children: PageNode[]
    basePath: string
    getChildUrl: (childPath: string) => string
    otherFiles?: OtherFile[]
    getOtherFileUrl?: (filePath: string) => string
  }>()

  const emit = defineEmits<{
    createPage: [name: string]
    createFolder: [name: string]
    rename: [childPath: string]
    delete: [childPath: string]
  }>()

  function onCreatePage(): void {
    const name = window.prompt('Page name:')
    if (!name || !name.trim()) return
    emit('createPage', name.trim())
  }

  function onCreateFolder(): void {
    const name = window.prompt('Folder name:')
    if (!name || !name.trim()) return
    emit('createFolder', name.trim())
  }

  function kindBadge(kind: string): string {
    switch (kind) {
      case 'image':
        return 'IMG'
      case 'drawio':
        return 'DRAW'
      case 'text':
        return 'TXT'
      default:
        return 'BIN'
    }
  }

  function kindColor(kind: string): string {
    switch (kind) {
      case 'image':
        return 'text-emerald-500'
      case 'drawio':
        return 'text-orange-500'
      case 'text':
        return 'text-violet-500'
      default:
        return 'text-slate-500'
    }
  }
</script>

<template>
  <section class="mt-8 border-t border-slate-200 pt-4">
    <h2 class="text-sm font-semibold uppercase tracking-wide text-slate-500 mb-2">
      In this folder
    </h2>
    <div class="flex gap-2 mb-3">
      <button
        type="button"
        class="text-xs px-3 py-1 rounded border border-slate-300 text-slate-600 hover:bg-slate-50 hover:text-blue-600 cursor-pointer"
        @click="onCreatePage"
      >
        + New page
      </button>
      <button
        type="button"
        class="text-xs px-3 py-1 rounded border border-slate-300 text-slate-600 hover:bg-slate-50 hover:text-blue-600 cursor-pointer"
        @click="onCreateFolder"
      >
        + New folder
      </button>
    </div>

    <ul v-if="children.length" class="text-sm space-y-1">
      <li v-for="child in children" :key="child.path" class="flex items-center gap-1 group">
        <RouterLink
          :to="getChildUrl(child.path)"
          class="flex items-center flex-1 min-w-0 text-slate-700 hover:text-blue-600 hover:underline"
        >
          <!-- Folder icon -->
          <svg
            v-if="child.is_directory || child.children.length"
            xmlns="http://www.w3.org/2000/svg"
            class="w-4 h-4 shrink-0 mr-1.5 text-amber-500"
            viewBox="0 0 24 24"
            fill="currentColor"
            stroke="none"
          >
            <path
              d="M2 6a2 2 0 0 1 2-2h5l2 2h9a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V6z"
            />
          </svg>
          <!-- PDF / MD badge -->
          <span
            v-else-if="child.kind === 'pdf'"
            class="w-4 shrink-0 mr-1.5 text-[10px] font-semibold text-rose-500 text-center"
            >PDF</span
          >
          <span
            v-else
            class="w-4 shrink-0 mr-1.5 text-[10px] font-semibold text-sky-500 text-center"
            >MD</span
          >
          <span class="truncate">{{ child.title }}</span>
        </RouterLink>
        <button
          type="button"
          class="shrink-0 opacity-0 group-hover:opacity-100 text-slate-400 hover:text-slate-600 p-0.5 rounded transition-opacity cursor-pointer"
          title="Rename"
          aria-label="Rename"
          @click="emit('rename', child.path)"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            class="w-3.5 h-3.5"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <path d="M12 20h9" />
            <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z" />
          </svg>
        </button>
        <button
          type="button"
          class="shrink-0 opacity-0 group-hover:opacity-100 text-slate-400 hover:text-red-600 p-0.5 rounded transition-opacity cursor-pointer"
          title="Delete"
          aria-label="Delete"
          @click="emit('delete', child.path)"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            class="w-3.5 h-3.5"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <polyline points="3 6 5 6 21 6" />
            <path
              d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"
            />
            <line x1="10" y1="11" x2="10" y2="17" />
            <line x1="14" y1="11" x2="14" y2="17" />
          </svg>
        </button>
      </li>
    </ul>
    <p v-else class="text-sm text-slate-400 italic">Empty folder</p>
  </section>

  <!-- Other files -->
  <section v-if="otherFiles && otherFiles.length" class="mt-6 border-t border-slate-200 pt-4">
    <h2 class="text-sm font-semibold uppercase tracking-wide text-slate-500 mb-2">Other files</h2>
    <ul class="text-sm space-y-1">
      <li v-for="file in otherFiles" :key="file.path" class="flex items-center gap-1 group">
        <a
          v-if="getOtherFileUrl"
          :href="getOtherFileUrl(file.path)"
          :download="file.name"
          class="flex items-center flex-1 min-w-0 text-slate-600 hover:text-blue-600 hover:underline"
        >
          <span
            class="w-6 shrink-0 mr-0.5 text-[10px] font-semibold text-center"
            :class="kindColor(file.kind)"
            >{{ kindBadge(file.kind) }}</span
          >
          <span class="truncate">{{ file.name }}</span>
        </a>
        <span v-else class="flex items-center flex-1 min-w-0 text-slate-600">
          <span
            class="w-6 shrink-0 mr-0.5 text-[10px] font-semibold text-center"
            :class="kindColor(file.kind)"
            >{{ kindBadge(file.kind) }}</span
          >
          <span class="truncate">{{ file.name }}</span>
        </span>
      </li>
    </ul>
  </section>
</template>
