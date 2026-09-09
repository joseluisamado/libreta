<script setup lang="ts">
  // Blocking recovery prompt shown when a page opens with an unsaved draft in
  // the browser (see composables/useDraft.ts). Deliberately NOT dismissible by
  // a backdrop click or Esc — the only exits are the two explicit choices, so a
  // stray click can never silently discard recovered work.
  defineProps<{
    open: boolean
    // Human-readable age of the draft, e.g. "3 minutes ago".
    ageLabel: string
    // True when the on-disk page changed since the draft was made; continuing
    // will overwrite those newer changes on save.
    stale: boolean
  }>()

  const emit = defineEmits<{
    continue: []
    discard: []
  }>()
</script>

<template>
  <Teleport to="body">
    <div
      v-if="open"
      class="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4"
    >
      <div
        class="w-full max-w-md rounded-lg bg-white p-5 shadow-xl"
        role="dialog"
        aria-modal="true"
      >
        <h2 class="mb-2 text-base font-semibold text-slate-800">Unsaved changes found</h2>
        <p class="text-sm text-slate-600">
          You have unsaved edits to this page from <strong>{{ ageLabel }}</strong
          >, kept in this browser. Continue where you left off, or start from the saved version?
        </p>
        <p
          v-if="stale"
          class="mt-3 rounded border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-800"
        >
          <strong>Note:</strong> the saved page has changed since these edits were made. If you
          continue, saving will overwrite those newer changes.
        </p>
        <div class="mt-5 flex justify-end gap-2">
          <button
            type="button"
            class="rounded px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-100 cursor-pointer"
            @click="emit('discard')"
          >
            Start from scratch
          </button>
          <button
            type="button"
            class="rounded bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700 cursor-pointer"
            @click="emit('continue')"
          >
            Continue where I left off
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>
