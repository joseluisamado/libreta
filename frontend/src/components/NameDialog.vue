<script setup lang="ts">
  import { computed, nextTick, ref, watch } from 'vue'
  import { NAME_HINT, pageNameToSlug } from '@/utils/pageName'

  const props = withDefaults(
    defineProps<{
      open: boolean
      title: string
      label?: string
      placeholder?: string
      initial?: string
      confirmLabel?: string
      // When true, show the slugified preview + char hint (create flows).
      // When false, treat the value as a raw path (rename flow).
      slugPreview?: boolean
    }>(),
    {
      label: 'Name',
      placeholder: '',
      initial: '',
      confirmLabel: 'Create',
      slugPreview: true,
    },
  )

  const emit = defineEmits<{
    confirm: [value: string]
    cancel: []
  }>()

  const value = ref(props.initial)
  const inputEl = ref<HTMLInputElement | null>(null)

  const preview = computed(() =>
    props.slugPreview ? pageNameToSlug(value.value) : value.value.trim(),
  )
  const canConfirm = computed(() => preview.value.length > 0)

  watch(
    () => props.open,
    async (open) => {
      if (open) {
        value.value = props.initial
        await nextTick()
        inputEl.value?.focus()
        inputEl.value?.select()
      }
    },
  )

  function onConfirm(): void {
    if (!canConfirm.value) return
    emit('confirm', props.slugPreview ? value.value : value.value.trim())
  }
</script>

<template>
  <Teleport to="body">
    <div
      v-if="open"
      class="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4"
      @click.self="emit('cancel')"
      @keydown.esc="emit('cancel')"
    >
      <div
        class="w-full max-w-sm rounded-lg bg-white p-5 shadow-xl"
        role="dialog"
        aria-modal="true"
      >
        <h2 class="text-base font-semibold text-slate-800 mb-3">{{ title }}</h2>
        <form @submit.prevent="onConfirm">
          <label class="block text-xs font-medium text-slate-500 mb-1" :for="'name-dialog-input'">
            {{ label }}
          </label>
          <input
            id="name-dialog-input"
            ref="inputEl"
            v-model="value"
            type="text"
            :placeholder="placeholder"
            class="w-full rounded border border-slate-300 px-3 py-2 text-sm text-slate-800 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            autocomplete="off"
          />
          <p v-if="slugPreview" class="mt-1.5 text-xs text-slate-400">{{ NAME_HINT }}</p>
          <p v-if="slugPreview && value.trim()" class="mt-1 text-xs text-slate-500">
            Will be saved as
            <code class="rounded bg-slate-100 px-1 py-0.5 text-slate-700">{{
              preview || '—'
            }}</code>
          </p>
          <div class="mt-4 flex justify-end gap-2">
            <button
              type="button"
              class="rounded px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-100 cursor-pointer"
              @click="emit('cancel')"
            >
              Cancel
            </button>
            <button
              type="submit"
              :disabled="!canConfirm"
              class="rounded bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
            >
              {{ confirmLabel }}
            </button>
          </div>
        </form>
      </div>
    </div>
  </Teleport>
</template>
