<script setup lang="ts">
  import { onBeforeUnmount, onMounted, ref } from 'vue'

  const props = defineProps<{
    drawioUrl: string
    initialXml?: string
  }>()

  const emit = defineEmits<{
    save: [svg: string]
    cancel: []
  }>()

  const iframeRef = ref<HTMLIFrameElement | null>(null)

  // The drawio embed contract (proto=json): on init, post {action:'load', xml}.
  // On user save, drawio posts {event:'save', xml}; we reply with
  // {action:'export', format:'xmlsvg'} to get an SVG containing the editable
  // XML in a metadata tag. drawio responds with {event:'export', data:<dataURI>}
  // and we resolve that to plain SVG bytes.
  // 'saveAndExit=1' makes the editor's primary button save+close.
  // 'noExitBtn=1' hides the bare exit; users dismiss with our overlay close.
  const embedSrc = `${props.drawioUrl}?embed=1&proto=json&spin=1&saveAndExit=1&ui=atlas&noSaveBtn=0`

  function postToFrame(message: unknown): void {
    iframeRef.value?.contentWindow?.postMessage(JSON.stringify(message), '*')
  }

  function dataUriToString(uri: string): string {
    const comma = uri.indexOf(',')
    if (comma < 0) return ''
    const meta = uri.slice(0, comma)
    const payload = uri.slice(comma + 1)
    if (meta.includes(';base64')) {
      const binary = atob(payload)
      // SVG is utf-8; decode bytes through TextDecoder.
      const bytes = new Uint8Array(binary.length)
      for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i)
      return new TextDecoder('utf-8').decode(bytes)
    }
    return decodeURIComponent(payload)
  }

  function onMessage(event: MessageEvent): void {
    if (!iframeRef.value) return
    if (event.source !== iframeRef.value.contentWindow) return
    if (typeof event.data !== 'string') return
    let msg: { event?: string; xml?: string; data?: string }
    try {
      msg = JSON.parse(event.data) as { event?: string; xml?: string; data?: string }
    } catch {
      return
    }
    switch (msg.event) {
      case 'init':
        postToFrame({
          action: 'load',
          autosave: 0,
          xml: props.initialXml ?? '',
        })
        break
      case 'save':
        // Ask drawio to export an SVG that embeds the editable XML.
        postToFrame({ action: 'export', format: 'xmlsvg', spinKey: 'saving' })
        break
      case 'export':
        if (msg.data) {
          const svg = dataUriToString(msg.data)
          if (svg) emit('save', svg)
        }
        break
      case 'exit':
        emit('cancel')
        break
      default:
        break
    }
  }

  function onBackdropClick(e: MouseEvent): void {
    if (e.target === e.currentTarget) emit('cancel')
  }

  function onKeydown(e: KeyboardEvent): void {
    if (e.key === 'Escape') emit('cancel')
  }

  onMounted(() => {
    window.addEventListener('message', onMessage)
    window.addEventListener('keydown', onKeydown)
  })

  onBeforeUnmount(() => {
    window.removeEventListener('message', onMessage)
    window.removeEventListener('keydown', onKeydown)
  })
</script>

<template>
  <div
    class="fixed inset-0 z-50 flex items-stretch justify-center bg-black/40 p-4"
    @click="onBackdropClick"
  >
    <div class="relative flex h-full w-full max-w-7xl flex-col rounded-lg bg-white shadow-xl">
      <div class="flex items-center justify-between border-b border-slate-200 px-3 py-2">
        <span class="text-sm font-medium text-slate-700">Edit diagram</span>
        <button
          type="button"
          class="rounded px-2 py-1 text-xs text-slate-500 hover:bg-slate-100"
          @click="emit('cancel')"
        >
          Close
        </button>
      </div>
      <iframe
        ref="iframeRef"
        :src="embedSrc"
        class="flex-1 w-full border-0"
        title="Diagram editor"
      />
    </div>
  </div>
</template>
