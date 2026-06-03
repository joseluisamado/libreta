import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import Editor from '@/components/Editor/Editor.vue'

beforeEach(() => {
  setActivePinia(createPinia())
})

function createWrapper(content = '# Hello\n\nSome text.') {
  return mount(Editor, {
    props: {
      content,
      path: 'test/page',
    },
    global: {
      plugins: [createPinia()],
    },
  })
}

// Helper: wait a few ticks for Tiptap to initialize in JSDOM
async function waitForEditor(wrapper: ReturnType<typeof createWrapper>) {
  await nextTick()
  await nextTick()
  // Allow requestAnimationFrame callbacks to fire
  await new Promise((r) => requestAnimationFrame(() => r(null)))
  await nextTick()
  return wrapper
}

describe('Editor.vue', () => {
  it('mounts and renders the editor container', async () => {
    const wrapper = await waitForEditor(createWrapper())
    expect(wrapper.find('.libreta-editor').exists()).toBe(true)
  })

  it('renders ProseMirror DOM', async () => {
    const wrapper = await waitForEditor(createWrapper())
    // Tiptap wraps the editor in a <div class="tiptap"> by default
    // and EditorContent renders the ProseMirror instance
    const editorEl = wrapper.find('.libreta-editor')
    expect(editorEl.exists()).toBe(true)
    // Check that the editor element contains something (the ProseMirror mount)
    expect(editorEl.element.innerHTML.length).toBeGreaterThan(0)
  })

  it('loads initial content into the editor', async () => {
    const wrapper = await waitForEditor(createWrapper('# Test Heading'))
    // Check exposed getMarkdown returns the content
    const md = wrapper.vm.getMarkdown()
    expect(md).toContain('Test Heading')
  })

  it('exposes getMarkdown method', () => {
    const wrapper = createWrapper()
    expect(typeof wrapper.vm.getMarkdown).toBe('function')
  })

  it('getMarkdown returns the editor content', async () => {
    const wrapper = await waitForEditor(createWrapper('# A Page\n\nBody text.'))
    const md = wrapper.vm.getMarkdown()
    expect(md).toContain('# A Page')
    expect(md).toContain('Body text.')
  })

  it('renders content with inline formatting', async () => {
    const wrapper = await waitForEditor(createWrapper('**bold** and *italic*'))
    const md = wrapper.vm.getMarkdown()
    expect(md).toContain('**bold**')
    expect(md).toContain('*italic*')
  })

  it('watches content prop change', async () => {
    const wrapper = await waitForEditor(createWrapper('Initial content'))
    await wrapper.setProps({ content: 'Updated content' })
    await nextTick()
    await nextTick()
    const md = wrapper.vm.getMarkdown()
    expect(md).toContain('Updated content')
  })

  it('exposes editor instance', async () => {
    const wrapper = await waitForEditor(createWrapper('# Test'))
    expect(wrapper.vm.editor).toBeTruthy()
  })

  it('exposes openLinkDialog and opens the link modal', async () => {
    const wrapper = await waitForEditor(createWrapper('Plain text'))
    expect(typeof wrapper.vm.openLinkDialog).toBe('function')
    expect(wrapper.findComponent({ name: 'LinkModal' }).exists()).toBe(false)
    wrapper.vm.openLinkDialog()
    await nextTick()
    expect(wrapper.findComponent({ name: 'LinkModal' }).exists()).toBe(true)
  })

  it('inserts an external link as markdown when the modal submits', async () => {
    const wrapper = await waitForEditor(createWrapper(''))
    wrapper.vm.openLinkDialog()
    await nextTick()
    const modal = wrapper.findComponent({ name: 'LinkModal' })
    modal.vm.$emit('submit', { href: 'https://example.com', text: 'Example' })
    await nextTick()
    await nextTick()
    const md = wrapper.vm.getMarkdown()
    expect(md).toContain('[Example](https://example.com)')
    // Modal closes after submit.
    expect(wrapper.findComponent({ name: 'LinkModal' }).exists()).toBe(false)
  })

  it('inserts a relative internal link that round-trips byte-identically', async () => {
    const wrapper = await waitForEditor(createWrapper(''))
    wrapper.vm.openLinkDialog()
    await nextTick()
    const modal = wrapper.findComponent({ name: 'LinkModal' })
    // A same-repo .md target one directory up from "test/page".
    modal.vm.$emit('submit', { href: '../other/guide.md', text: 'Guide' })
    await nextTick()
    await nextTick()
    const md = wrapper.vm.getMarkdown()
    expect(md).toContain('[Guide](../other/guide.md)')
  })
})
