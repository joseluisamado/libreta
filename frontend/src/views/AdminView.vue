<script setup lang="ts">
  import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
  import { useSourcesStore } from '@/stores/sources'
  import { useWatchedStore } from '@/stores/watched'
  import type { GitSource, GitSourceCreate, GiteaRepo, GiteaServerCreate } from '@/api/types'

  const store = useSourcesStore()
  const watched = useWatchedStore()

  // ---- Add source form ------------------------------------------------
  const showSourceForm = ref(false)
  const sourceForm = ref<GitSourceCreate>({
    id: '',
    label: '',
    remote_url: '',
    branch: 'main',
    ssh_key_id: null,
    http_username: null,
    http_password: null,
    sync_interval_minutes: 5,
  })
  const sourceError = ref<string | null>(null)
  const sourceAdding = ref(false)

  async function submitSource(): Promise<void> {
    sourceError.value = null
    const { id, label, remote_url } = sourceForm.value
    if (!id || !label || !remote_url) {
      sourceError.value = 'ID, label and remote URL are required.'
      return
    }
    if (!/^[a-z0-9][a-z0-9_-]*$/.test(id)) {
      sourceError.value =
        'ID must be lowercase letters, numbers, hyphens, or underscores (no spaces).'
      return
    }
    sourceAdding.value = true
    try {
      await store.addSource({
        ...sourceForm.value,
        ssh_key_id: sourceForm.value.ssh_key_id || null,
      })
      showSourceForm.value = false
      sourceForm.value = {
        id: '',
        label: '',
        remote_url: '',
        branch: 'main',
        ssh_key_id: null,
        http_username: null,
        http_password: null,
        sync_interval_minutes: 5,
      }
    } catch (e) {
      sourceError.value = e instanceof Error ? e.message : String(e)
    } finally {
      sourceAdding.value = false
    }
  }

  async function removeSource(id: string, label: string): Promise<void> {
    if (!window.confirm(`Remove git source "${label}"? The local clone will NOT be deleted.`))
      return
    await store.removeSource(id)
  }

  async function syncSource(id: string): Promise<void> {
    await store.syncSource(id)
  }

  // ---- Add watch form -------------------------------------------------
  const showWatchForm = ref(false)
  const watchLabel = ref('')
  const watchPath = ref('')
  const watchError = ref<string | null>(null)
  const watchAdding = ref(false)

  async function submitWatch(): Promise<void> {
    watchError.value = null
    const lbl = watchLabel.value.trim()
    const pth = watchPath.value.trim()
    if (!lbl || !pth) {
      watchError.value = 'Label and path are required.'
      return
    }
    watchAdding.value = true
    try {
      await watched.addFolder(lbl, pth)
      showWatchForm.value = false
      watchLabel.value = ''
      watchPath.value = ''
    } catch (e) {
      watchError.value = e instanceof Error ? e.message : String(e)
    } finally {
      watchAdding.value = false
    }
  }

  async function removeWatch(label: string): Promise<void> {
    if (!window.confirm(`Remove watched folder "${label}"?`)) return
    await watched.removeFolder(label)
  }

  // ---- Add SSH key form -----------------------------------------------
  const showKeyForm = ref(false)
  const keyLabel = ref('')
  const keyPem = ref('')
  const keyError = ref<string | null>(null)
  const keyAdding = ref(false)

  async function submitKey(): Promise<void> {
    keyError.value = null
    if (!keyLabel.value.trim() || !keyPem.value.trim()) {
      keyError.value = 'Label and private key are required.'
      return
    }
    keyAdding.value = true
    try {
      await store.addSshKey({ label: keyLabel.value.trim(), private_key: keyPem.value.trim() })
      showKeyForm.value = false
      keyLabel.value = ''
      keyPem.value = ''
    } catch (e) {
      keyError.value = e instanceof Error ? e.message : String(e)
    } finally {
      keyAdding.value = false
    }
  }

  async function removeKey(id: string, label: string): Promise<void> {
    if (!window.confirm(`Remove SSH key "${label}"?`)) return
    await store.removeSshKey(id)
  }

  // ---- Gitea servers + bulk import ------------------------------------
  const showGiteaForm = ref(false)
  const giteaForm = ref<GiteaServerCreate>({
    label: '',
    base_url: '',
    username: '',
    token: '',
  })
  const giteaError = ref<string | null>(null)
  const giteaAdding = ref(false)

  async function submitGiteaServer(): Promise<void> {
    giteaError.value = null
    const { label, base_url, username, token } = giteaForm.value
    if (!label || !base_url || !username || !token) {
      giteaError.value = 'Label, base URL, username and token are all required.'
      return
    }
    giteaAdding.value = true
    try {
      await store.addGiteaServer({ ...giteaForm.value })
      showGiteaForm.value = false
      giteaForm.value = { label: '', base_url: '', username: '', token: '' }
    } catch (e) {
      giteaError.value = e instanceof Error ? e.message : String(e)
    } finally {
      giteaAdding.value = false
    }
  }

  async function removeGiteaServer(id: string, label: string): Promise<void> {
    if (
      !window.confirm(
        `Remove Gitea server "${label}"? Sources imported from it will lose their ` +
          `stored credential and stop syncing until re-pointed.`,
      )
    )
      return
    await store.removeGiteaServer(id)
  }

  // Discovery/import state is keyed by the server being browsed. Only one
  // server's picker is open at a time.
  const discoverServerId = ref<string | null>(null)
  const discoverOwner = ref('')
  const discoverBusy = ref(false)
  const discoverError = ref<string | null>(null)
  const discoveredRepos = ref<GiteaRepo[]>([])
  const selectedRepos = ref<Set<string>>(new Set())
  const importBusy = ref(false)

  function toggleDiscover(serverId: string, username: string): void {
    if (discoverServerId.value === serverId) {
      discoverServerId.value = null
      return
    }
    discoverServerId.value = serverId
    // Default to the server's own account — the most common owner to browse.
    // The user can still overwrite it to list another org/user's repos.
    discoverOwner.value = username
    discoveredRepos.value = []
    selectedRepos.value = new Set()
    discoverError.value = null
  }

  async function runDiscover(serverId: string): Promise<void> {
    discoverError.value = null
    const owner = discoverOwner.value.trim()
    if (!owner) {
      discoverError.value = 'Enter an org or user to list its repos.'
      return
    }
    discoverBusy.value = true
    try {
      discoveredRepos.value = await store.discoverGiteaRepos(serverId, owner)
      // Pre-select every importable (not-yet-added, non-empty) repo.
      selectedRepos.value = new Set(
        discoveredRepos.value.filter((r) => !r.already_added && !r.empty).map((r) => r.full_name),
      )
    } catch (e) {
      discoverError.value = e instanceof Error ? e.message : String(e)
      discoveredRepos.value = []
    } finally {
      discoverBusy.value = false
    }
  }

  function toggleRepo(fullName: string): void {
    const next = new Set(selectedRepos.value)
    if (next.has(fullName)) next.delete(fullName)
    else next.add(fullName)
    selectedRepos.value = next
  }

  // Repos that can actually be selected (not already-added).
  const selectableRepos = computed(() => discoveredRepos.value.filter((r) => !r.already_added))
  const allSelectableSelected = computed(
    () =>
      selectableRepos.value.length > 0 &&
      selectableRepos.value.every((r) => selectedRepos.value.has(r.full_name)),
  )

  function toggleSelectAll(): void {
    if (allSelectableSelected.value) {
      selectedRepos.value = new Set()
    } else {
      selectedRepos.value = new Set(selectableRepos.value.map((r) => r.full_name))
    }
  }

  async function runImport(serverId: string): Promise<void> {
    if (!selectedRepos.value.size) return
    importBusy.value = true
    discoverError.value = null
    try {
      await store.importGiteaRepos(serverId, discoverOwner.value.trim(), [...selectedRepos.value])
      discoverServerId.value = null
      discoveredRepos.value = []
      selectedRepos.value = new Set()
    } catch (e) {
      discoverError.value = e instanceof Error ? e.message : String(e)
    } finally {
      importBusy.value = false
    }
  }

  // The source (if any) tracking a discovered repo's clone_url. Lets the
  // browse-repos list remove an already-imported repo in place.
  function sourceForRepo(cloneUrl: string): GitSource | undefined {
    return store.sources.find((s) => s.remote_url === cloneUrl)
  }

  async function removeRepoSource(repo: GiteaRepo): Promise<void> {
    const src = sourceForRepo(repo.clone_url)
    if (!src) return
    if (!window.confirm(`Remove git source "${src.label}"? The local clone will NOT be deleted.`))
      return
    await store.removeSource(src.id)
    // Reflect the removal in the picker: the row is no longer "already added".
    const match = discoveredRepos.value.find((r) => r.full_name === repo.full_name)
    if (match) match.already_added = false
  }

  // ---- Edit: git source ------------------------------------------------
  // Only the safely-mutable fields are exposed (id and remote_url are the
  // source's identity / clone target — changing them is a remove + re-add).
  const editSourceId = ref<string | null>(null)
  const editSourceForm = ref({ label: '', branch: '', sync_interval_minutes: 5 })
  const editSourceError = ref<string | null>(null)

  function startEditSource(src: GitSource): void {
    editSourceId.value = src.id
    editSourceForm.value = {
      label: src.label,
      branch: src.branch,
      sync_interval_minutes: src.sync_interval_minutes,
    }
    editSourceError.value = null
  }

  async function saveEditSource(): Promise<void> {
    if (!editSourceId.value) return
    editSourceError.value = null
    try {
      await store.updateSource(editSourceId.value, { ...editSourceForm.value })
      editSourceId.value = null
    } catch (e) {
      editSourceError.value = e instanceof Error ? e.message : String(e)
    }
  }

  // ---- Edit: watched folder -------------------------------------------
  const editWatchLabel = ref<string | null>(null)
  const editWatchForm = ref({ label: '', path: '' })
  const editWatchError = ref<string | null>(null)

  function startEditWatch(label: string, path: string): void {
    editWatchLabel.value = label
    editWatchForm.value = { label, path }
    editWatchError.value = null
  }

  async function saveEditWatch(): Promise<void> {
    if (editWatchLabel.value === null) return
    editWatchError.value = null
    const { label, path } = editWatchForm.value
    if (!label.trim() || !path.trim()) {
      editWatchError.value = 'Label and path are required.'
      return
    }
    try {
      await watched.updateFolder(editWatchLabel.value, label.trim(), path.trim())
      editWatchLabel.value = null
    } catch (e) {
      editWatchError.value = e instanceof Error ? e.message : String(e)
    }
  }

  // ---- Edit: SSH key (label only) -------------------------------------
  const editKeyId = ref<string | null>(null)
  const editKeyLabel = ref('')
  const editKeyError = ref<string | null>(null)

  function startEditKey(id: string, label: string): void {
    editKeyId.value = id
    editKeyLabel.value = label
    editKeyError.value = null
  }

  async function saveEditKey(): Promise<void> {
    if (!editKeyId.value) return
    editKeyError.value = null
    if (!editKeyLabel.value.trim()) {
      editKeyError.value = 'Label is required.'
      return
    }
    try {
      await store.updateSshKey(editKeyId.value, editKeyLabel.value.trim())
      editKeyId.value = null
    } catch (e) {
      editKeyError.value = e instanceof Error ? e.message : String(e)
    }
  }

  // ---- Edit: Gitea server (token optional — blank keeps current) ------
  const editGiteaId = ref<string | null>(null)
  const editGiteaForm = ref({ label: '', base_url: '', username: '', token: '' })
  const editGiteaError = ref<string | null>(null)

  function startEditGitea(id: string, label: string, baseUrl: string, username: string): void {
    editGiteaId.value = id
    editGiteaForm.value = { label, base_url: baseUrl, username, token: '' }
    editGiteaError.value = null
  }

  async function saveEditGitea(): Promise<void> {
    if (!editGiteaId.value) return
    editGiteaError.value = null
    const { label, base_url, username, token } = editGiteaForm.value
    if (!label.trim() || !base_url.trim() || !username.trim()) {
      editGiteaError.value = 'Label, base URL and username are required.'
      return
    }
    try {
      await store.updateGiteaServer(editGiteaId.value, {
        label: label.trim(),
        base_url: base_url.trim(),
        username: username.trim(),
        // Blank token => keep the stored one.
        token: token.trim() || null,
      })
      editGiteaId.value = null
    } catch (e) {
      editGiteaError.value = e instanceof Error ? e.message : String(e)
    }
  }

  function loadAll(): void {
    store.loadSources()
    store.loadSshKeys()
    store.loadGiteaServers()
    watched.loadFolders()
  }

  // Refetch when the tab/page becomes visible again. Without this, a list
  // that failed to load while the api was momentarily down (e.g. a container
  // restart with the Admin page already open) stays empty until a manual
  // reload — which looks like "my server disappeared" even though it's still
  // persisted on disk. The store swallows load errors, so a visible empty
  // list and a fetch failure are otherwise indistinguishable.
  function onVisible(): void {
    if (document.visibilityState === 'visible') loadAll()
  }

  onMounted(() => {
    loadAll()
    document.addEventListener('visibilitychange', onVisible)
    window.addEventListener('focus', loadAll)
  })

  onBeforeUnmount(() => {
    document.removeEventListener('visibilitychange', onVisible)
    window.removeEventListener('focus', loadAll)
  })
</script>

<template>
  <div class="max-w-3xl mx-auto px-8 py-8">
    <h1 class="text-2xl font-bold mb-8">Admin</h1>

    <!-- A failed list fetch (e.g. api momentarily down) would otherwise leave
         the lists silently empty. Surface it so it's not mistaken for data
         loss; it clears on the next successful load (mount / tab refocus). -->
    <div
      v-if="store.error || watched.error"
      class="mb-6 p-3 rounded-lg border border-amber-200 bg-amber-50 text-sm text-amber-700"
    >
      Couldn't load some settings: {{ store.error || watched.error }}. Retrying when the tab
      regains focus.
    </div>

    <!-- ==================== Git Sources ==================== -->
    <section class="mb-10">
      <div class="flex items-center justify-between mb-4">
        <h2 class="text-lg font-semibold">Git Sources</h2>
        <button
          type="button"
          class="text-sm px-3 py-1 rounded bg-blue-600 text-white hover:bg-blue-700 cursor-pointer"
          @click="showSourceForm = !showSourceForm"
        >
          {{ showSourceForm ? 'Cancel' : '+ Add source' }}
        </button>
      </div>

      <!-- Add form -->
      <div v-if="showSourceForm" class="mb-4 p-4 border border-slate-200 rounded-lg bg-slate-50">
        <p v-if="sourceError" class="text-red-600 text-sm mb-2">{{ sourceError }}</p>
        <div class="grid grid-cols-2 gap-3 mb-3">
          <div>
            <label class="block text-xs text-slate-500 mb-1">ID (slug)</label>
            <input
              v-model.trim="sourceForm.id"
              type="text"
              placeholder="my-wiki"
              pattern="^[a-z0-9][a-z0-9_-]*$"
              class="w-full border border-slate-300 rounded px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-blue-400"
            />
            <p class="text-xs text-slate-400 mt-0.5">
              Lowercase letters, numbers, hyphens, underscores only.
            </p>
          </div>
          <div>
            <label class="block text-xs text-slate-500 mb-1">Label</label>
            <input
              v-model.trim="sourceForm.label"
              type="text"
              placeholder="My Wiki"
              class="w-full border border-slate-300 rounded px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-blue-400"
            />
          </div>
          <div class="col-span-2">
            <label class="block text-xs text-slate-500 mb-1">Remote URL</label>
            <input
              v-model.trim="sourceForm.remote_url"
              type="text"
              placeholder="ssh://git@git.example.com:3333/my-org/libreta-data.git"
              class="w-full border border-slate-300 rounded px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-blue-400"
            />
            <p class="text-xs text-slate-400 mt-0.5">
              For SSH on a non-standard port use
              <code class="font-mono">ssh://git@host:PORT/path.git</code>
            </p>
          </div>
          <div>
            <label class="block text-xs text-slate-500 mb-1">Branch</label>
            <input
              v-model.trim="sourceForm.branch"
              type="text"
              placeholder="main"
              class="w-full border border-slate-300 rounded px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-blue-400"
            />
          </div>
          <div>
            <label class="block text-xs text-slate-500 mb-1">Sync interval (minutes)</label>
            <input
              v-model.number="sourceForm.sync_interval_minutes"
              type="number"
              min="1"
              max="1440"
              class="w-full border border-slate-300 rounded px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-blue-400"
            />
          </div>
          <div class="col-span-2">
            <label class="block text-xs text-slate-500 mb-1">SSH key (optional)</label>
            <select
              v-model="sourceForm.ssh_key_id"
              class="w-full border border-slate-300 rounded px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-blue-400 bg-white"
              :disabled="!!(sourceForm.http_username || sourceForm.http_password)"
            >
              <option :value="null">— none —</option>
              <option v-for="k in store.sshKeys" :key="k.id" :value="k.id">
                {{ k.label }} ({{ k.fingerprint }})
              </option>
            </select>
          </div>
          <div>
            <label class="block text-xs text-slate-500 mb-1">HTTP username (optional)</label>
            <input
              v-model.trim="sourceForm.http_username"
              type="text"
              placeholder="git or token username"
              class="w-full border border-slate-300 rounded px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-blue-400"
              :disabled="!!sourceForm.ssh_key_id"
              @input="sourceForm.ssh_key_id = null"
            />
          </div>
          <div>
            <label class="block text-xs text-slate-500 mb-1"
              >HTTP password / token (optional)</label
            >
            <input
              v-model="sourceForm.http_password"
              type="password"
              placeholder="password or access token"
              class="w-full border border-slate-300 rounded px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-blue-400"
              :disabled="!!sourceForm.ssh_key_id"
              @input="sourceForm.ssh_key_id = null"
            />
          </div>
        </div>
        <button
          type="button"
          :disabled="sourceAdding"
          class="px-4 py-1.5 text-sm rounded bg-blue-600 text-white hover:bg-blue-700 cursor-pointer disabled:opacity-50"
          @click="submitSource"
        >
          {{ sourceAdding ? 'Adding…' : 'Add source' }}
        </button>
      </div>

      <!-- Source list -->
      <div v-if="store.sources.length" class="space-y-3">
        <div
          v-for="src in store.sources"
          :key="src.id"
          class="p-4 border border-slate-200 rounded-lg"
        >
          <!-- Edit mode -->
          <div v-if="editSourceId === src.id">
            <p v-if="editSourceError" class="text-red-600 text-sm mb-2">{{ editSourceError }}</p>
            <p class="text-xs text-slate-400 mb-2 font-mono">{{ src.remote_url }}</p>
            <div class="grid grid-cols-2 gap-3 mb-3">
              <div class="col-span-2">
                <label class="block text-xs text-slate-500 mb-1">Label</label>
                <input
                  v-model.trim="editSourceForm.label"
                  type="text"
                  class="w-full border border-slate-300 rounded px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-blue-400"
                />
              </div>
              <div>
                <label class="block text-xs text-slate-500 mb-1">Branch</label>
                <input
                  v-model.trim="editSourceForm.branch"
                  type="text"
                  class="w-full border border-slate-300 rounded px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-blue-400"
                />
              </div>
              <div>
                <label class="block text-xs text-slate-500 mb-1">Sync interval (minutes)</label>
                <input
                  v-model.number="editSourceForm.sync_interval_minutes"
                  type="number"
                  min="1"
                  max="1440"
                  class="w-full border border-slate-300 rounded px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-blue-400"
                />
              </div>
            </div>
            <div class="flex gap-2">
              <button
                type="button"
                class="px-4 py-1.5 text-sm rounded bg-blue-600 text-white hover:bg-blue-700 cursor-pointer"
                @click="saveEditSource"
              >
                Save
              </button>
              <button
                type="button"
                class="px-4 py-1.5 text-sm rounded border border-slate-300 text-slate-600 hover:bg-slate-50 cursor-pointer"
                @click="editSourceId = null"
              >
                Cancel
              </button>
            </div>
          </div>

          <!-- Read mode -->
          <div v-else class="flex items-start justify-between">
            <div>
              <p class="font-medium text-sm">{{ src.label }}</p>
              <p class="text-xs text-slate-500 mt-0.5">{{ src.remote_url }}</p>
              <p class="text-xs text-slate-400 mt-0.5">
                branch: {{ src.branch }} &bull; sync every {{ src.sync_interval_minutes }} min
              </p>
              <p
                class="text-xs mt-1"
                :class="src.last_sync_error ? 'text-amber-600' : 'text-emerald-600'"
              >
                <template v-if="src.last_sync_error"> Error: {{ src.last_sync_error }} </template>
                <template v-else-if="src.last_synced_at">
                  Synced: {{ new Date(src.last_synced_at).toLocaleString() }}
                </template>
                <template v-else> Not synced yet </template>
              </p>
              <p v-if="src.cloning" class="text-xs text-sky-600 mt-0.5 italic flex items-center gap-1">
                <span class="inline-block w-2 h-2 rounded-full bg-sky-400 animate-pulse"></span>
                Cloning… large repos can take a few minutes — no need to re-add.
              </p>
              <p
                v-else-if="!src.cloned && !src.last_sync_error"
                class="text-xs text-slate-400 mt-0.5 italic"
              >
                Not cloned yet — will start on the next sync.
              </p>
            </div>
            <div class="flex gap-2 shrink-0 ml-4">
              <button
                type="button"
                class="text-xs px-2 py-1 rounded border border-slate-300 text-slate-600 hover:bg-slate-50 cursor-pointer"
                title="Sync now"
                @click="syncSource(src.id)"
              >
                Sync
              </button>
              <button
                type="button"
                class="text-xs px-2 py-1 rounded border border-slate-300 text-slate-600 hover:bg-slate-50 cursor-pointer"
                @click="startEditSource(src)"
              >
                Edit
              </button>
              <button
                type="button"
                class="text-xs px-2 py-1 rounded border border-red-200 text-red-600 hover:bg-red-50 cursor-pointer"
                @click="removeSource(src.id, src.label)"
              >
                Remove
              </button>
            </div>
          </div>
        </div>
      </div>
      <p v-else-if="store.loaded" class="text-sm text-slate-400">No git sources configured yet.</p>
    </section>

    <!-- ==================== Gitea Servers ==================== -->
    <section class="mb-10">
      <div class="flex items-center justify-between mb-4">
        <h2 class="text-lg font-semibold">Gitea Servers</h2>
        <button
          type="button"
          class="text-sm px-3 py-1 rounded bg-blue-600 text-white hover:bg-blue-700 cursor-pointer"
          @click="showGiteaForm = !showGiteaForm"
        >
          {{ showGiteaForm ? 'Cancel' : '+ Add server' }}
        </button>
      </div>

      <p class="text-sm text-slate-500 mb-4">
        Store a server's access token once, then bulk-import every repo under an org or user.
        Imported sources share the stored token, so rotating it here updates them all.
      </p>

      <!-- Add server form -->
      <div v-if="showGiteaForm" class="mb-4 p-4 border border-slate-200 rounded-lg bg-slate-50">
        <p v-if="giteaError" class="text-red-600 text-sm mb-2">{{ giteaError }}</p>
        <div class="grid grid-cols-2 gap-3 mb-3">
          <div>
            <label class="block text-xs text-slate-500 mb-1">Label</label>
            <input
              v-model.trim="giteaForm.label"
              type="text"
              placeholder="Home Gitea"
              class="w-full border border-slate-300 rounded px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-blue-400"
            />
          </div>
          <div>
            <label class="block text-xs text-slate-500 mb-1">Base URL</label>
            <input
              v-model.trim="giteaForm.base_url"
              type="text"
              placeholder="https://git.example.com"
              class="w-full border border-slate-300 rounded px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-blue-400"
            />
          </div>
          <div>
            <label class="block text-xs text-slate-500 mb-1">Username</label>
            <input
              v-model.trim="giteaForm.username"
              type="text"
              placeholder="alice"
              class="w-full border border-slate-300 rounded px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-blue-400"
            />
          </div>
          <div>
            <label class="block text-xs text-slate-500 mb-1">Access token</label>
            <input
              v-model="giteaForm.token"
              type="password"
              placeholder="personal access token"
              class="w-full border border-slate-300 rounded px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-blue-400"
            />
          </div>
        </div>
        <button
          type="button"
          :disabled="giteaAdding"
          class="px-4 py-1.5 text-sm rounded bg-blue-600 text-white hover:bg-blue-700 cursor-pointer disabled:opacity-50"
          @click="submitGiteaServer"
        >
          {{ giteaAdding ? 'Adding…' : 'Add server' }}
        </button>
      </div>

      <!-- Server list -->
      <div v-if="store.giteaServers.length" class="space-y-3">
        <div
          v-for="gs in store.giteaServers"
          :key="gs.id"
          class="p-4 border border-slate-200 rounded-lg"
        >
          <!-- Edit mode -->
          <div v-if="editGiteaId === gs.id">
            <p v-if="editGiteaError" class="text-red-600 text-sm mb-2">{{ editGiteaError }}</p>
            <div class="grid grid-cols-2 gap-3 mb-3">
              <div>
                <label class="block text-xs text-slate-500 mb-1">Label</label>
                <input
                  v-model.trim="editGiteaForm.label"
                  type="text"
                  class="w-full border border-slate-300 rounded px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-blue-400"
                />
              </div>
              <div>
                <label class="block text-xs text-slate-500 mb-1">Base URL</label>
                <input
                  v-model.trim="editGiteaForm.base_url"
                  type="text"
                  class="w-full border border-slate-300 rounded px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-blue-400"
                />
              </div>
              <div>
                <label class="block text-xs text-slate-500 mb-1">Username</label>
                <input
                  v-model.trim="editGiteaForm.username"
                  type="text"
                  class="w-full border border-slate-300 rounded px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-blue-400"
                />
              </div>
              <div>
                <label class="block text-xs text-slate-500 mb-1">Access token</label>
                <input
                  v-model="editGiteaForm.token"
                  type="password"
                  placeholder="leave blank to keep current"
                  class="w-full border border-slate-300 rounded px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-blue-400"
                />
              </div>
            </div>
            <div class="flex gap-2">
              <button
                type="button"
                class="px-4 py-1.5 text-sm rounded bg-blue-600 text-white hover:bg-blue-700 cursor-pointer"
                @click="saveEditGitea"
              >
                Save
              </button>
              <button
                type="button"
                class="px-4 py-1.5 text-sm rounded border border-slate-300 text-slate-600 hover:bg-slate-50 cursor-pointer"
                @click="editGiteaId = null"
              >
                Cancel
              </button>
            </div>
          </div>

          <!-- Read mode -->
          <div v-else class="flex items-start justify-between">
            <div>
              <p class="font-medium text-sm">{{ gs.label }}</p>
              <p class="text-xs text-slate-500 mt-0.5">{{ gs.base_url }}</p>
              <p class="text-xs text-slate-400 mt-0.5">user: {{ gs.username }}</p>
            </div>
            <div class="flex gap-2 shrink-0 ml-4">
              <button
                type="button"
                class="text-xs px-2 py-1 rounded border border-slate-300 text-slate-600 hover:bg-slate-50 cursor-pointer"
                @click="toggleDiscover(gs.id, gs.username)"
              >
                {{ discoverServerId === gs.id ? 'Close' : 'Browse repos' }}
              </button>
              <button
                type="button"
                class="text-xs px-2 py-1 rounded border border-slate-300 text-slate-600 hover:bg-slate-50 cursor-pointer"
                @click="startEditGitea(gs.id, gs.label, gs.base_url, gs.username)"
              >
                Edit
              </button>
              <button
                type="button"
                class="text-xs px-2 py-1 rounded border border-red-200 text-red-600 hover:bg-red-50 cursor-pointer"
                @click="removeGiteaServer(gs.id, gs.label)"
              >
                Remove
              </button>
            </div>
          </div>

          <!-- Discover + import picker -->
          <div v-if="discoverServerId === gs.id" class="mt-4 pt-4 border-t border-slate-200">
            <p v-if="discoverError" class="text-red-600 text-sm mb-2">{{ discoverError }}</p>
            <div class="flex gap-2 items-end mb-3">
              <div class="flex-1">
                <label class="block text-xs text-slate-500 mb-1">Org or user</label>
                <input
                  v-model.trim="discoverOwner"
                  type="text"
                  placeholder="team-name"
                  class="w-full border border-slate-300 rounded px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-blue-400"
                  @keyup.enter="runDiscover(gs.id)"
                />
              </div>
              <button
                type="button"
                :disabled="discoverBusy"
                class="px-3 py-1.5 text-sm rounded bg-slate-700 text-white hover:bg-slate-800 cursor-pointer disabled:opacity-50"
                @click="runDiscover(gs.id)"
              >
                {{ discoverBusy ? 'Listing…' : 'List repos' }}
              </button>
            </div>

            <div
              v-if="discoveredRepos.length"
              class="flex items-center justify-between mb-2 pb-2 border-b border-slate-100"
            >
              <button
                type="button"
                :disabled="!selectableRepos.length"
                class="text-xs px-2 py-1 rounded border border-slate-300 text-slate-600 hover:bg-slate-50 cursor-pointer disabled:opacity-50"
                @click="toggleSelectAll"
              >
                {{ allSelectableSelected ? 'Deselect all' : 'Select all' }}
              </button>
              <span class="text-xs text-slate-400">
                {{ selectedRepos.size }} of {{ selectableRepos.length }} selected
              </span>
            </div>

            <div v-if="discoveredRepos.length" class="space-y-1 mb-3 max-h-72 overflow-y-auto">
              <div
                v-for="repo in discoveredRepos"
                :key="repo.full_name"
                class="flex items-center gap-2 px-2 py-1 rounded hover:bg-slate-50"
              >
                <label class="flex items-center gap-2 flex-1 min-w-0 cursor-pointer">
                  <input
                    type="checkbox"
                    :checked="selectedRepos.has(repo.full_name)"
                    :disabled="repo.already_added"
                    @change="toggleRepo(repo.full_name)"
                  />
                  <span class="text-sm font-mono" :class="{ 'text-slate-400': repo.already_added }">
                    {{ repo.full_name }}
                  </span>
                  <span v-if="repo.already_added" class="text-xs text-slate-400">added</span>
                  <span v-else-if="repo.empty" class="text-xs text-amber-600">empty</span>
                  <span v-if="repo.description" class="text-xs text-slate-400 truncate">
                    — {{ repo.description }}
                  </span>
                </label>
                <button
                  v-if="repo.already_added && sourceForRepo(repo.clone_url)"
                  type="button"
                  class="text-xs px-2 py-0.5 rounded border border-red-200 text-red-600 hover:bg-red-50 cursor-pointer shrink-0"
                  @click="removeRepoSource(repo)"
                >
                  Remove
                </button>
              </div>
            </div>

            <button
              v-if="discoveredRepos.length"
              type="button"
              :disabled="importBusy || !selectedRepos.size"
              class="px-4 py-1.5 text-sm rounded bg-blue-600 text-white hover:bg-blue-700 cursor-pointer disabled:opacity-50"
              @click="runImport(gs.id)"
            >
              {{ importBusy ? 'Importing…' : `Import ${selectedRepos.size} selected` }}
            </button>
          </div>
        </div>
      </div>
      <p v-else-if="store.loaded" class="text-sm text-slate-400">No Gitea servers configured.</p>
    </section>

    <!-- ==================== Watched Folders ==================== -->
    <section class="mb-10">
      <div class="flex items-center justify-between mb-4">
        <h2 class="text-lg font-semibold">Watched Folders</h2>
        <button
          type="button"
          class="text-sm px-3 py-1 rounded bg-blue-600 text-white hover:bg-blue-700 cursor-pointer"
          @click="showWatchForm = !showWatchForm"
        >
          {{ showWatchForm ? 'Cancel' : '+ Add watch' }}
        </button>
      </div>

      <!-- Add form -->
      <div v-if="showWatchForm" class="mb-4 p-4 border border-slate-200 rounded-lg bg-slate-50">
        <p v-if="watchError" class="text-red-600 text-sm mb-2">{{ watchError }}</p>
        <div class="grid grid-cols-2 gap-3 mb-3">
          <div>
            <label class="block text-xs text-slate-500 mb-1">Label</label>
            <input
              v-model.trim="watchLabel"
              type="text"
              placeholder="My Notes"
              class="w-full border border-slate-300 rounded px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-blue-400"
            />
            <p class="text-xs text-slate-400 mt-0.5">
              Letters, numbers, hyphens, underscores only.
            </p>
          </div>
          <div class="col-span-2">
            <label class="block text-xs text-slate-500 mb-1">Path</label>
            <input
              v-model.trim="watchPath"
              type="text"
              placeholder="/absolute/path/to/folder"
              class="w-full border border-slate-300 rounded px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-blue-400"
            />
          </div>
        </div>
        <button
          type="button"
          :disabled="watchAdding"
          class="px-4 py-1.5 text-sm rounded bg-blue-600 text-white hover:bg-blue-700 cursor-pointer disabled:opacity-50"
          @click="submitWatch"
        >
          {{ watchAdding ? 'Adding…' : 'Add watch' }}
        </button>
      </div>

      <!-- Watch list -->
      <div v-if="watched.folders.length" class="space-y-3">
        <div
          v-for="f in watched.folders"
          :key="f.label"
          class="p-4 border border-slate-200 rounded-lg"
        >
          <!-- Edit mode -->
          <div v-if="editWatchLabel === f.label">
            <p v-if="editWatchError" class="text-red-600 text-sm mb-2">{{ editWatchError }}</p>
            <div class="grid grid-cols-2 gap-3 mb-3">
              <div>
                <label class="block text-xs text-slate-500 mb-1">Label</label>
                <input
                  v-model.trim="editWatchForm.label"
                  type="text"
                  class="w-full border border-slate-300 rounded px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-blue-400"
                />
              </div>
              <div class="col-span-2">
                <label class="block text-xs text-slate-500 mb-1">Path</label>
                <input
                  v-model.trim="editWatchForm.path"
                  type="text"
                  class="w-full border border-slate-300 rounded px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-blue-400"
                />
              </div>
            </div>
            <div class="flex gap-2">
              <button
                type="button"
                class="px-4 py-1.5 text-sm rounded bg-blue-600 text-white hover:bg-blue-700 cursor-pointer"
                @click="saveEditWatch"
              >
                Save
              </button>
              <button
                type="button"
                class="px-4 py-1.5 text-sm rounded border border-slate-300 text-slate-600 hover:bg-slate-50 cursor-pointer"
                @click="editWatchLabel = null"
              >
                Cancel
              </button>
            </div>
          </div>

          <!-- Read mode -->
          <div v-else class="flex items-center justify-between">
            <div>
              <p class="font-medium text-sm">{{ f.label }}</p>
              <p class="text-xs text-slate-400 mt-0.5 truncate max-w-lg" :title="f.path">
                {{ f.path }}
              </p>
            </div>
            <div class="flex gap-2 shrink-0 ml-4">
              <button
                type="button"
                class="text-xs px-2 py-1 rounded border border-slate-300 text-slate-600 hover:bg-slate-50 cursor-pointer"
                @click="startEditWatch(f.label, f.path)"
              >
                Edit
              </button>
              <button
                type="button"
                class="text-xs px-2 py-1 rounded border border-red-200 text-red-600 hover:bg-red-50 cursor-pointer"
                @click="removeWatch(f.label)"
              >
                Remove
              </button>
            </div>
          </div>
        </div>
      </div>
      <p v-else class="text-sm text-slate-400">No watched folders configured yet.</p>
    </section>

    <!-- ==================== SSH Keys ==================== -->
    <section>
      <div class="flex items-center justify-between mb-4">
        <h2 class="text-lg font-semibold">SSH Keys</h2>
        <button
          type="button"
          class="text-sm px-3 py-1 rounded bg-blue-600 text-white hover:bg-blue-700 cursor-pointer"
          @click="showKeyForm = !showKeyForm"
        >
          {{ showKeyForm ? 'Cancel' : '+ Add key' }}
        </button>
      </div>

      <!-- Add form -->
      <div v-if="showKeyForm" class="mb-4 p-4 border border-slate-200 rounded-lg bg-slate-50">
        <p v-if="keyError" class="text-red-600 text-sm mb-2">{{ keyError }}</p>
        <div class="mb-3">
          <label class="block text-xs text-slate-500 mb-1">Label</label>
          <input
            v-model.trim="keyLabel"
            type="text"
            placeholder="Personal GitHub key"
            class="w-full border border-slate-300 rounded px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-blue-400"
          />
        </div>
        <div class="mb-3">
          <label class="block text-xs text-slate-500 mb-1">Private key (PEM)</label>
          <textarea
            v-model="keyPem"
            rows="8"
            placeholder="-----BEGIN OPENSSH PRIVATE KEY-----&#10;..."
            class="w-full border border-slate-300 rounded px-2 py-1 text-xs font-mono focus:outline-none focus:ring-1 focus:ring-blue-400 resize-y"
            spellcheck="false"
          />
        </div>
        <button
          type="button"
          :disabled="keyAdding"
          class="px-4 py-1.5 text-sm rounded bg-blue-600 text-white hover:bg-blue-700 cursor-pointer disabled:opacity-50"
          @click="submitKey"
        >
          {{ keyAdding ? 'Adding…' : 'Add key' }}
        </button>
      </div>

      <!-- Key list -->
      <div v-if="store.sshKeys.length" class="space-y-2">
        <div v-for="k in store.sshKeys" :key="k.id" class="p-3 border border-slate-200 rounded-lg">
          <!-- Edit mode (label only) -->
          <div v-if="editKeyId === k.id">
            <p v-if="editKeyError" class="text-red-600 text-sm mb-2">{{ editKeyError }}</p>
            <div class="flex gap-2 items-end">
              <div class="flex-1">
                <label class="block text-xs text-slate-500 mb-1">Label</label>
                <input
                  v-model.trim="editKeyLabel"
                  type="text"
                  class="w-full border border-slate-300 rounded px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-blue-400"
                  @keyup.enter="saveEditKey"
                />
              </div>
              <button
                type="button"
                class="px-4 py-1.5 text-sm rounded bg-blue-600 text-white hover:bg-blue-700 cursor-pointer"
                @click="saveEditKey"
              >
                Save
              </button>
              <button
                type="button"
                class="px-4 py-1.5 text-sm rounded border border-slate-300 text-slate-600 hover:bg-slate-50 cursor-pointer"
                @click="editKeyId = null"
              >
                Cancel
              </button>
            </div>
          </div>

          <!-- Read mode -->
          <div v-else class="flex items-center justify-between">
            <div>
              <p class="text-sm font-medium">{{ k.label }}</p>
              <p class="text-xs text-slate-400 font-mono">{{ k.fingerprint }}</p>
            </div>
            <div class="flex gap-2 shrink-0 ml-4">
              <button
                type="button"
                class="text-xs px-2 py-1 rounded border border-slate-300 text-slate-600 hover:bg-slate-50 cursor-pointer"
                @click="startEditKey(k.id, k.label)"
              >
                Edit
              </button>
              <button
                type="button"
                class="text-xs px-2 py-1 rounded border border-red-200 text-red-600 hover:bg-red-50 cursor-pointer"
                @click="removeKey(k.id, k.label)"
              >
                Remove
              </button>
            </div>
          </div>
        </div>
      </div>
      <p v-else class="text-sm text-slate-400">No SSH keys configured.</p>
    </section>
  </div>
</template>
