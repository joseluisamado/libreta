<script setup lang="ts">
  import { ref } from 'vue'
  import { useWatchedStore } from '@/stores/watched'
  import PageTree from '@/components/PageTree.vue'

  const store = useWatchedStore()

  const labelInput = ref('')
  const pathInput = ref('')
  const addError = ref<string | null>(null)
  const expanded = ref<Record<string, boolean>>({})
  const showAddForm = ref(false)

  store.loadFolders()

  function toggleExpand(label: string): void {
    if (expanded.value[label]) {
      expanded.value = { ...expanded.value, [label]: false }
    } else {
      expanded.value = { ...expanded.value, [label]: true }
      store.loadTree(label)
    }
  }

  async function submit(): Promise<void> {
    addError.value = null
    const lbl = labelInput.value.trim()
    const pth = pathInput.value.trim()
    if (!lbl || !pth) {
      addError.value = 'Label and path are required.'
      return
    }
    try {
      await store.addFolder(lbl, pth)
      labelInput.value = ''
      pathInput.value = ''
      expanded.value = { ...expanded.value, [lbl]: true }
      showAddForm.value = false
    } catch (e) {
      addError.value = e instanceof Error ? e.message : String(e)
    }
  }

  async function remove(label: string): Promise<void> {
    if (!window.confirm(`Remove watched folder "${label}"?`)) return
    await store.removeFolder(label)
    expanded.value = { ...expanded.value, [label]: false }
  }
</script>

<template>
  <div class="text-sm">
    <p v-if="store.error" class="text-red-600 mb-2">{{ store.error }}</p>

    <ul v-if="store.folders.length" class="mb-3">
      <li v-for="f in store.folders" :key="f.label" class="mb-1">
        <div class="flex items-start gap-1">
          <button
            type="button"
            class="shrink-0 w-4 h-4 mt-0.5 flex items-center justify-center text-slate-400 hover:text-slate-700"
            :aria-expanded="!!expanded[f.label]"
            :aria-label="expanded[f.label] ? 'Collapse folder' : 'Expand folder'"
            @click="toggleExpand(f.label)"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              class="w-3 h-3 transition-transform"
              :class="{ 'rotate-90': expanded[f.label] }"
              viewBox="0 0 12 12"
              fill="currentColor"
            >
              <path d="M4 2 L8 6 L4 10 Z" />
            </svg>
          </button>
          <RouterLink
            :to="`/watch/${f.label}/`"
            class="flex-1 truncate text-slate-700 hover:text-blue-600 font-medium"
          >
            {{ f.label }}
          </RouterLink>
          <button
            type="button"
            class="shrink-0 text-slate-400 hover:text-red-600 p-0.5 rounded"
            title="Remove watched folder"
            aria-label="Remove"
            @click="remove(f.label)"
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
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>
        <p class="text-[11px] text-slate-400 ml-5 truncate" :title="f.path">
          {{ f.path }}
        </p>
        <PageTree
          v-if="expanded[f.label] && store.trees[f.label]"
          :nodes="store.trees[f.label]!"
          :link-prefix="'/watch/' + f.label"
          class="ml-3 border-l-2 border-slate-200 pl-2 mt-0.5"
        />
      </li>
    </ul>

    <p v-if="store.loaded && !store.folders.length" class="text-slate-400 text-xs mb-3">
      No watched folders.
    </p>

    <!-- Add button / form -->
    <div class="border-t border-slate-200 pt-3 mt-2">
      <template v-if="showAddForm">
        <p v-if="addError" class="text-red-600 text-xs mb-1">{{ addError }}</p>
        <input
          v-model.trim="labelInput"
          type="text"
          placeholder="label"
          class="w-full border border-slate-300 rounded px-2 py-1 text-xs mb-1.5 focus:outline-none focus:ring-1 focus:ring-blue-400"
          @keyup.enter="submit"
        />
        <input
          v-model.trim="pathInput"
          type="text"
          placeholder="/absolute/path/to/folder"
          class="w-full border border-slate-300 rounded px-2 py-1 text-xs mb-1.5 focus:outline-none focus:ring-1 focus:ring-blue-400"
          @keyup.enter="submit"
        />
        <div class="flex gap-1">
          <button
            type="button"
            class="flex-1 text-xs px-2 py-1 rounded bg-blue-600 text-white hover:bg-blue-700 cursor-pointer"
            @click="submit"
          >
            Add
          </button>
          <button
            type="button"
            class="text-xs px-2 py-1 rounded border border-slate-300 text-slate-500 hover:bg-slate-50 cursor-pointer"
            @click="showAddForm = false"
          >
            Cancel
          </button>
        </div>
      </template>
      <button
        v-else
        type="button"
        class="w-full text-xs px-2 py-1 rounded border border-slate-300 text-slate-500 hover:bg-slate-50 cursor-pointer"
        @click="showAddForm = true"
      >
        + Add watch
      </button>
    </div>
  </div>
</template>
