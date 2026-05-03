<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useTreeStore } from '@/stores/tree'
import { getRecentChanges, savePage } from '@/api/client'
import type { PageNode, RecentChange } from '@/api/types'
import logoUrl from '@/assets/logo.svg'

const router = useRouter()
const tree = useTreeStore()

// ── Search ────────────────────────────────────────────────────────────

const searchQuery = ref('')

function doSearch(): void {
  const q = searchQuery.value.trim()
  if (q) {
    router.push({ path: '/search', query: { q } })
  } else {
    router.push('/search')
  }
}

// ── Stats ─────────────────────────────────────────────────────────────

function countPages(nodes: PageNode[]): number {
  let n = 0
  for (const node of nodes) {
    if (!node.is_directory) n++
    if (node.children.length) n += countPages(node.children)
  }
  return n
}

const pageCount = computed(() => countPages(tree.nodes))

const namespaceCount = computed(
  () => tree.nodes.filter((n) => n.is_directory).length,
)

// ── Recent changes ────────────────────────────────────────────────────

const recentChanges = ref<RecentChange[]>([])
const recentLoading = ref(true)
const recentError = ref<string | null>(null)

onMounted(async () => {
  if (!tree.loaded) await tree.load()
  try {
    recentChanges.value = await getRecentChanges(20)
  } catch (e) {
    recentError.value = e instanceof Error ? e.message : String(e)
  } finally {
    recentLoading.value = false
  }
})

// ── Quick-create ──────────────────────────────────────────────────────

const newPageName = ref('')
const creating = ref(false)
const createError = ref<string | null>(null)
const createSuccess = ref<string | null>(null)

async function quickCreate(): Promise<void> {
  const name = newPageName.value.trim()
  if (!name) return
  creating.value = true
  createError.value = null
  createSuccess.value = null
  try {
    await savePage(name, { body: `# ${name}\n` })
    createSuccess.value = name
    newPageName.value = ''
    tree.load()
    recentChanges.value = await getRecentChanges(20)
  } catch (e) {
    createError.value = e instanceof Error ? e.message : String(e)
  } finally {
    creating.value = false
  }
}

// ── Helpers ───────────────────────────────────────────────────────────

function timeAgo(ts: string): string {
  const diff = Date.now() - new Date(ts).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  const days = Math.floor(hrs / 24)
  return `${days}d ago`
}
</script>

<template>
  <div class="max-w-3xl mx-auto px-6 py-12 md:py-20">
    <!-- ── Hero ─────────────────────────────────────────────────────── -->
    <div class="text-center mb-12">
      <img :src="logoUrl" alt="" class="w-16 h-16 mx-auto mb-4" />
      <h1 class="text-3xl font-bold text-slate-800 mb-3">Libreta</h1>
      <p class="text-slate-500 mb-8">
        Your wiki, backed by a git repository of markdown files.
      </p>

      <form @submit.prevent="doSearch" class="max-w-lg mx-auto">
        <div class="flex gap-2">
          <input
            v-model="searchQuery"
            type="text"
            placeholder="Search pages..."
            class="flex-1 px-4 py-3 rounded-lg border border-slate-300 bg-white text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-400 focus:border-transparent"
          />
          <button
            type="submit"
            class="px-5 py-3 rounded-lg bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 transition-colors"
          >
            Search
          </button>
        </div>
      </form>
    </div>

    <!-- ── Stats cards ──────────────────────────────────────────────── -->
    <div class="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-12">
      <div class="rounded-lg border border-slate-200 bg-white p-5 text-center">
        <p class="text-3xl font-bold text-blue-600">{{ pageCount }}</p>
        <p class="text-sm text-slate-500">pages</p>
      </div>
      <div class="rounded-lg border border-slate-200 bg-white p-5 text-center">
        <p class="text-3xl font-bold text-blue-600">{{ namespaceCount }}</p>
        <p class="text-sm text-slate-500">namespaces</p>
      </div>
    </div>

    <!-- ── Quick-create ─────────────────────────────────────────────── -->
    <section class="mb-12">
      <h2 class="text-lg font-semibold text-slate-800 mb-4">Create a page</h2>

      <form @submit.prevent="quickCreate" class="flex gap-2 max-w-md">
        <input
          v-model="newPageName"
          type="text"
          placeholder="page-name"
          class="flex-1 px-3 py-2 rounded-lg border border-slate-300 bg-white text-sm focus:outline-none focus:ring-2 focus:ring-blue-400 focus:border-transparent"
        />
        <button
          type="submit"
          :disabled="creating || !newPageName.trim()"
          class="px-4 py-2 rounded-lg bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {{ creating ? 'Creating...' : 'Create' }}
        </button>
      </form>

      <p v-if="createError" class="text-sm text-red-600 mt-2">{{ createError }}</p>
      <p v-if="createSuccess" class="text-sm text-green-600 mt-2">
        Page created:
        <RouterLink :to="`/w/${createSuccess}`" class="text-blue-600 hover:underline">
          {{ createSuccess }}
        </RouterLink>
        &middot;
        <RouterLink :to="`/edit/${createSuccess}`" class="text-blue-600 hover:underline">
          edit
        </RouterLink>
      </p>
    </section>

    <!-- ── Recent changes ───────────────────────────────────────────── -->
    <section>
      <h2 class="text-lg font-semibold text-slate-800 mb-4">Recent changes</h2>

      <p v-if="recentLoading" class="text-sm text-slate-400">Loading...</p>
      <p v-else-if="recentError" class="text-sm text-red-600">{{ recentError }}</p>

      <ul v-else-if="recentChanges.length" class="divide-y divide-slate-100 border border-slate-200 rounded-lg bg-white">
        <li
          v-for="change in recentChanges"
          :key="`${change.sha}-${change.path}`"
          class="px-4 py-3 flex items-center gap-3 text-sm"
        >
          <span class="text-slate-400 text-xs w-14 shrink-0">{{ timeAgo(change.timestamp) }}</span>
          <RouterLink
            :to="`/w/${change.path}`"
            class="text-blue-600 hover:underline font-medium truncate flex-1 min-w-0"
          >
            {{ change.path || '(index)' }}
          </RouterLink>
          <span class="text-slate-400 hidden sm:inline truncate max-w-[12rem]">{{ change.message }}</span>
        </li>
      </ul>
      <p v-else class="text-sm text-slate-400">No changes yet.</p>
    </section>
  </div>
</template>
