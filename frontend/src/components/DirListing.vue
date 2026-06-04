<script setup lang="ts">
  import { ref, watch } from 'vue'
  import type { OtherFile, PageNode } from '@/api/types'
  import PreviewTile from './PreviewTile.vue'

  const props = defineProps<{
    children: PageNode[]
    basePath: string
    getChildUrl: (childPath: string) => string
    otherFiles?: OtherFile[]
    getOtherFileUrl?: (filePath: string) => string
    getTextFileUrl?: (filePath: string) => string
    // Raw-content URL for a child page (markdown) or pdf, used by the
    // preview tiles to fetch a snippet / embed the document.
    getChildRawUrl?: (childPath: string) => string
    // Source context for the markdown thumbnails so relative asset links
    // (images, .drawio.svg) inside a page resolve to the right /assets URL,
    // exactly as the full viewer does. Exactly one of these is set.
    sourceId?: string
    watchedLabel?: string
    uploading?: boolean
  }>()

  const emit = defineEmits<{
    createPage: []
    createFolder: []
    rename: [childPath: string]
    delete: [childPath: string]
    upload: [files: File[]]
  }>()

  // Files at or above this size trigger a confirmation step before upload.
  // There is no hard cap — uploads stream to disk server-side — but a large
  // file is worth a deliberate confirm (it lands in git history).
  const LARGE_FILE_BYTES = 50 * 1024 * 1024

  // View mode + tile size persist across navigation so the user's choice
  // sticks while browsing the tree. Plain localStorage, no store needed.
  type ViewMode = 'list' | 'preview'
  const VIEW_KEY = 'libreta.dirView'
  const SIZE_KEY = 'libreta.dirTileSize'

  function loadView(): ViewMode {
    return localStorage.getItem(VIEW_KEY) === 'preview' ? 'preview' : 'list'
  }
  function loadSize(): number {
    const n = Number(localStorage.getItem(SIZE_KEY))
    return Number.isFinite(n) && n >= 120 && n <= 360 ? n : 260
  }

  const viewMode = ref<ViewMode>(loadView())
  const tileSize = ref<number>(loadSize())

  watch(viewMode, (v) => localStorage.setItem(VIEW_KEY, v))
  watch(tileSize, (v) => localStorage.setItem(SIZE_KEY, String(v)))

  const fileInput = ref<HTMLInputElement | null>(null)
  // Files awaiting confirmation because at least one exceeds LARGE_FILE_BYTES.
  const pendingLarge = ref<File[] | null>(null)

  function formatSize(bytes: number): string {
    if (bytes >= 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024 / 1024).toFixed(1)} GB`
    if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`
    return `${(bytes / 1024).toFixed(0)} KB`
  }

  function pickFiles(): void {
    fileInput.value?.click()
  }

  function onFilesChosen(e: Event): void {
    const input = e.target as HTMLInputElement
    const files = input.files ? Array.from(input.files) : []
    // Reset so choosing the same file again re-triggers change.
    input.value = ''
    if (files.length === 0) return
    if (files.some((f) => f.size >= LARGE_FILE_BYTES)) {
      pendingLarge.value = files
      return
    }
    emit('upload', files)
  }

  function confirmLargeUpload(): void {
    const files = pendingLarge.value
    pendingLarge.value = null
    if (files) emit('upload', files)
  }

  function cancelLargeUpload(): void {
    pendingLarge.value = null
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

  // Is this child a folder? (mirrors the list-view test)
  function isFolder(child: PageNode): boolean {
    return child.is_directory || child.children.length > 0
  }

  // Best-effort kind for a child node, for preview routing.
  function childKind(child: PageNode): 'folder' | 'pdf' | 'page' {
    if (isFolder(child)) return 'folder'
    if (child.kind === 'pdf') return 'pdf'
    return 'page'
  }

  // Whichever URL helper applies to an "other file" for opening/downloading.
  function otherFileHref(file: OtherFile): string {
    if (file.kind === 'text' && props.getTextFileUrl) return props.getTextFileUrl(file.path)
    return props.getOtherFileUrl ? props.getOtherFileUrl(file.path) : '#'
  }

  // For previews we want the raw bytes (text/image), not the viewer route.
  function otherFileRawUrl(file: OtherFile): string | undefined {
    return props.getOtherFileUrl ? props.getOtherFileUrl(file.path) : undefined
  }
</script>

<template>
  <section class="mt-8 border-t border-slate-200 pt-4">
    <div class="flex items-center justify-between mb-2">
      <h2 class="text-sm font-semibold uppercase tracking-wide text-slate-500">In this folder</h2>

      <!-- View-mode selector + size slider -->
      <div class="flex items-center gap-3">
        <div v-if="viewMode === 'preview'" class="flex items-center gap-1.5">
          <span class="text-[11px] text-slate-400">Size</span>
          <input
            v-model.number="tileSize"
            type="range"
            min="120"
            max="360"
            step="20"
            class="size-slider w-24 cursor-pointer"
            aria-label="Preview size"
          />
        </div>
        <div class="inline-flex rounded border border-slate-300 overflow-hidden">
          <button
            type="button"
            class="px-2 py-1 cursor-pointer"
            :class="
              viewMode === 'list' ? 'bg-blue-600 text-white' : 'text-slate-500 hover:bg-slate-50'
            "
            title="List view"
            aria-label="List view"
            @click="viewMode = 'list'"
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
              <line x1="8" y1="6" x2="21" y2="6" />
              <line x1="8" y1="12" x2="21" y2="12" />
              <line x1="8" y1="18" x2="21" y2="18" />
              <line x1="3" y1="6" x2="3.01" y2="6" />
              <line x1="3" y1="12" x2="3.01" y2="12" />
              <line x1="3" y1="18" x2="3.01" y2="18" />
            </svg>
          </button>
          <button
            type="button"
            class="px-2 py-1 cursor-pointer border-l border-slate-300"
            :class="
              viewMode === 'preview' ? 'bg-blue-600 text-white' : 'text-slate-500 hover:bg-slate-50'
            "
            title="Preview view"
            aria-label="Preview view"
            @click="viewMode = 'preview'"
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
              <rect x="3" y="3" width="7" height="7" />
              <rect x="14" y="3" width="7" height="7" />
              <rect x="14" y="14" width="7" height="7" />
              <rect x="3" y="14" width="7" height="7" />
            </svg>
          </button>
        </div>
      </div>
    </div>

    <div class="flex gap-2 mb-3">
      <button
        type="button"
        class="text-xs px-3 py-1 rounded border border-slate-300 text-slate-600 hover:bg-slate-50 hover:text-blue-600 cursor-pointer"
        @click="emit('createPage')"
      >
        + New page
      </button>
      <button
        type="button"
        class="text-xs px-3 py-1 rounded border border-slate-300 text-slate-600 hover:bg-slate-50 hover:text-blue-600 cursor-pointer"
        @click="emit('createFolder')"
      >
        + New folder
      </button>
      <button
        type="button"
        class="text-xs px-3 py-1 rounded border border-slate-300 text-slate-600 hover:bg-slate-50 hover:text-blue-600 cursor-pointer disabled:opacity-50"
        :disabled="uploading"
        @click="pickFiles"
      >
        {{ uploading ? 'Uploading…' : '↑ Upload files' }}
      </button>
      <input ref="fileInput" type="file" multiple class="hidden" @change="onFilesChosen" />
    </div>

    <!-- Large-file confirmation -->
    <div
      v-if="pendingLarge"
      class="mb-3 rounded border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900"
    >
      <p class="font-medium mb-1">Large file{{ pendingLarge.length > 1 ? 's' : '' }}</p>
      <ul class="mb-2 list-disc pl-5 space-y-0.5">
        <li v-for="f in pendingLarge" :key="f.name">
          {{ f.name }} — <span class="font-medium">{{ formatSize(f.size) }}</span>
        </li>
      </ul>
      <p class="mb-2 text-xs">
        Files over 50&nbsp;MB are committed into the repository as-is. This can bloat git history.
        Upload anyway?
      </p>
      <div class="flex gap-2">
        <button
          type="button"
          class="text-xs px-3 py-1 rounded bg-amber-600 text-white hover:bg-amber-700 cursor-pointer"
          @click="confirmLargeUpload"
        >
          Upload anyway
        </button>
        <button
          type="button"
          class="text-xs px-3 py-1 rounded border border-slate-300 text-slate-600 hover:bg-slate-50 cursor-pointer"
          @click="cancelLargeUpload"
        >
          Cancel
        </button>
      </div>
    </div>

    <!-- ── List view ───────────────────────────────────────────── -->
    <template v-if="viewMode === 'list'">
      <ul v-if="children.length" class="text-sm space-y-1">
        <li v-for="child in children" :key="child.path" class="flex items-center gap-1 group">
          <RouterLink
            :to="getChildUrl(child.path)"
            class="flex items-center min-w-0 text-slate-700 hover:text-blue-600 hover:underline"
          >
            <!-- Folder icon -->
            <svg
              v-if="isFolder(child)"
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
            <span class="truncate">{{ child.filename }}</span>
          </RouterLink>
          <button
            type="button"
            class="shrink-0 opacity-30 group-hover:opacity-100 text-slate-400 hover:text-slate-600 p-0.5 rounded transition-opacity cursor-pointer"
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
            class="shrink-0 opacity-30 group-hover:opacity-100 text-slate-400 hover:text-red-600 p-0.5 rounded transition-opacity cursor-pointer"
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
    </template>

    <!-- ── Preview view ────────────────────────────────────────── -->
    <template v-else>
      <div
        v-if="children.length"
        class="grid gap-3"
        :style="{ gridTemplateColumns: `repeat(auto-fill, minmax(${tileSize}px, 1fr))` }"
      >
        <PreviewTile
          v-for="child in children"
          :key="child.path"
          :to="getChildUrl(child.path)"
          :label="child.filename"
          :kind="childKind(child)"
          :raw-url="getChildRawUrl ? getChildRawUrl(child.path) : undefined"
          :page-path="child.path"
          :source-id="sourceId"
          :watched-label="watchedLabel"
          :size="tileSize"
          @rename="emit('rename', child.path)"
          @delete="emit('delete', child.path)"
        />
      </div>
      <p v-else class="text-sm text-slate-400 italic">Empty folder</p>
    </template>
  </section>

  <!-- Other files -->
  <section v-if="otherFiles && otherFiles.length" class="mt-6 border-t border-slate-200 pt-4">
    <h2 class="text-sm font-semibold uppercase tracking-wide text-slate-500 mb-2">Other files</h2>

    <!-- List view -->
    <ul v-if="viewMode === 'list'" class="text-sm space-y-1">
      <li v-for="file in otherFiles" :key="file.path" class="flex items-center gap-1 group">
        <RouterLink
          v-if="file.kind === 'text' && getTextFileUrl"
          :to="getTextFileUrl(file.path)"
          class="flex items-center flex-1 min-w-0 text-slate-600 hover:text-blue-600 hover:underline"
        >
          <span
            class="w-6 shrink-0 mr-0.5 text-[10px] font-semibold text-center"
            :class="kindColor(file.kind)"
            >{{ kindBadge(file.kind) }}</span
          >
          <span class="truncate">{{ file.name }}</span>
        </RouterLink>
        <a
          v-else-if="getOtherFileUrl"
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

    <!-- Preview view -->
    <div
      v-else
      class="grid gap-3"
      :style="{ gridTemplateColumns: `repeat(auto-fill, minmax(${tileSize}px, 1fr))` }"
    >
      <PreviewTile
        v-for="file in otherFiles"
        :key="file.path"
        :to="otherFileHref(file)"
        :external="file.kind !== 'text'"
        :download-name="file.kind !== 'text' ? file.name : undefined"
        :label="file.name"
        :kind="file.kind"
        :raw-url="otherFileRawUrl(file)"
        :size="tileSize"
      />
    </div>
  </section>
</template>

<style scoped>
  /* Explicit cross-browser slider styling. The native range thumb renders
     inconsistently across platforms and at non-integer device-pixel ratios
     (it looked "funky" on non-retina), so we draw a flat track + round thumb
     ourselves at integer pixel sizes. */
  .size-slider {
    -webkit-appearance: none;
    appearance: none;
    height: 4px;
    border-radius: 9999px;
    background: theme('colors.slate.200');
    outline: none;
  }

  .size-slider::-webkit-slider-thumb {
    -webkit-appearance: none;
    appearance: none;
    width: 14px;
    height: 14px;
    border-radius: 9999px;
    background: theme('colors.blue.600');
    border: 2px solid white;
    box-shadow: 0 0 0 1px theme('colors.slate.300');
    cursor: pointer;
  }

  .size-slider::-moz-range-thumb {
    width: 14px;
    height: 14px;
    border-radius: 9999px;
    background: theme('colors.blue.600');
    border: 2px solid white;
    box-shadow: 0 0 0 1px theme('colors.slate.300');
    cursor: pointer;
  }

  .size-slider::-moz-range-track {
    height: 4px;
    border-radius: 9999px;
    background: theme('colors.slate.200');
  }
</style>
