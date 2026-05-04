<script setup lang="ts">
  import { ref, onMounted } from 'vue'
  import { useSourcesStore } from '@/stores/sources'
  import type { GitSourceCreate } from '@/api/types'

  const store = useSourcesStore()

  // ---- Add source form ------------------------------------------------
  const showSourceForm = ref(false)
  const sourceForm = ref<GitSourceCreate>({
    id: '',
    label: '',
    remote_url: '',
    branch: 'main',
    ssh_key_id: null,
    sync_interval_minutes: 15,
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
        sync_interval_minutes: 15,
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

  onMounted(() => {
    store.loadSources()
    store.loadSshKeys()
  })
</script>

<template>
  <div class="max-w-3xl mx-auto px-8 py-8">
    <h1 class="text-2xl font-bold mb-8">Admin</h1>

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
              class="w-full border border-slate-300 rounded px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-blue-400"
            />
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
              placeholder="git@github.com:you/wiki.git"
              class="w-full border border-slate-300 rounded px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-blue-400"
            />
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
            >
              <option :value="null">— none (public repo / SSH agent) —</option>
              <option v-for="k in store.sshKeys" :key="k.id" :value="k.id">
                {{ k.label }} ({{ k.fingerprint }})
              </option>
            </select>
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
          <div class="flex items-start justify-between">
            <div>
              <p class="font-medium text-sm">{{ src.label }}</p>
              <p class="text-xs text-slate-500 mt-0.5">{{ src.remote_url }}</p>
              <p class="text-xs text-slate-400 mt-0.5">
                branch: {{ src.branch }} &bull; sync every {{ src.sync_interval_minutes }} min
              </p>
              <p class="text-xs mt-1" :class="src.last_sync_error ? 'text-amber-600' : 'text-emerald-600'">
                <template v-if="src.last_sync_error">
                  Error: {{ src.last_sync_error }}
                </template>
                <template v-else-if="src.last_synced_at">
                  Synced: {{ new Date(src.last_synced_at).toLocaleString() }}
                </template>
                <template v-else>
                  Not synced yet
                </template>
              </p>
              <p v-if="!src.cloned" class="text-xs text-slate-400 mt-0.5 italic">Cloning in progress…</p>
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
        <div
          v-for="k in store.sshKeys"
          :key="k.id"
          class="flex items-center justify-between p-3 border border-slate-200 rounded-lg"
        >
          <div>
            <p class="text-sm font-medium">{{ k.label }}</p>
            <p class="text-xs text-slate-400 font-mono">{{ k.fingerprint }}</p>
          </div>
          <button
            type="button"
            class="text-xs px-2 py-1 rounded border border-red-200 text-red-600 hover:bg-red-50 cursor-pointer"
            @click="removeKey(k.id, k.label)"
          >
            Remove
          </button>
        </div>
      </div>
      <p v-else class="text-sm text-slate-400">No SSH keys configured.</p>
    </section>
  </div>
</template>
