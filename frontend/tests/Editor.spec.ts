import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import Editor from '@/components/Editor/Editor.vue'

function createWrapper(content = '# Hello\n\nSome text.') {
  return mount(Editor, {
    props: {
      content,
      path: 'test/page',
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
})
