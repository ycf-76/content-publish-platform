<script setup lang="ts">
import { ref, watch, onBeforeUnmount } from 'vue'
import { useEditor, EditorContent } from '@tiptap/vue-3'
import StarterKit from '@tiptap/starter-kit'
import Underline from '@tiptap/extension-underline'
import TextAlign from '@tiptap/extension-text-align'
import Placeholder from '@tiptap/extension-placeholder'
import CharacterCount from '@tiptap/extension-character-count'
import Highlight from '@tiptap/extension-highlight'
import Link from '@tiptap/extension-link'

const props = defineProps<{
  modelValue: string
  placeholder?: string
  maxLength?: number
  editable?: boolean
  showToolbar?: boolean
  showCharCount?: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

const editor = useEditor({
  extensions: [
    StarterKit.configure({
      heading: { levels: [1, 2, 3] },
      bulletList: { keepMarks: true },
      orderedList: { keepMarks: true },
    }),
    Underline,
    TextAlign.configure({
      types: ['heading', 'paragraph'],
    }),
    Placeholder.configure({
      placeholder: props.placeholder || '开始输入...',
    }),
    CharacterCount.configure({
      limit: props.maxLength,
    }),
    Highlight.configure({
      multicolor: true,
    }),
    Link.configure({
      openOnClick: false,
      HTMLAttributes: {
        class: 'text-blue-600 underline cursor-pointer',
      },
    }),
  ],
  content: props.modelValue,
  editable: props.editable !== false,
  onUpdate: ({ editor }) => {
    emit('update:modelValue', editor.getHTML())
  },
})

watch(() => props.modelValue, (newValue) => {
  if (editor.value && newValue !== editor.value.getHTML()) {
    editor.value.commands.setContent(newValue)
  }
})

const charCount = ref(0)
watch(() => editor.value?.storage.characterCount.characters(), (val) => {
  if (val !== undefined) charCount.value = val
}, { immediate: true })

onBeforeUnmount(() => {
  editor.value?.destroy()
})

function setLink() {
  const previousUrl = editor.value?.getAttributes('link').href
  const url = window.prompt('输入链接地址', previousUrl)

  if (url === null) return

  if (url === '') {
    editor.value?.chain().focus().extendMarkRange('link').unsetLink().run()
    return
  }

  editor.value?.chain().focus().extendMarkRange('link').setLink({ href: url }).run()
}

function insertTopic(topic: string) {
  editor.value?.chain().focus().insertContent(`#${topic} `).run()
}
</script>

<template>
  <div class="tiptap-editor" :class="{ 'readonly': !editable }">
    <div v-if="showToolbar && editable" class="toolbar">
      <button
        type="button"
        @click="editor?.chain().focus().toggleBold().run()"
        :class="{ 'is-active': editor?.isActive('bold') }"
        title="粗体"
      >
        <strong>B</strong>
      </button>
      <button
        type="button"
        @click="editor?.chain().focus().toggleItalic().run()"
        :class="{ 'is-active': editor?.isActive('italic') }"
        title="斜体"
      >
        <em>I</em>
      </button>
      <button
        type="button"
        @click="editor?.chain().focus().toggleUnderline().run()"
        :class="{ 'is-active': editor?.isActive('underline') }"
        title="下划线"
      >
        <u>U</u>
      </button>
      <button
        type="button"
        @click="editor?.chain().focus().toggleStrike().run()"
        :class="{ 'is-active': editor?.isActive('strike') }"
        title="删除线"
      >
        <s>S</s>
      </button>
      <span class="divider"></span>
      <button
        type="button"
        @click="editor?.chain().focus().toggleHeading({ level: 1 }).run()"
        :class="{ 'is-active': editor?.isActive('heading', { level: 1 }) }"
        title="标题1"
      >
        H1
      </button>
      <button
        type="button"
        @click="editor?.chain().focus().toggleHeading({ level: 2 }).run()"
        :class="{ 'is-active': editor?.isActive('heading', { level: 2 }) }"
        title="标题2"
      >
        H2
      </button>
      <button
        type="button"
        @click="editor?.chain().focus().toggleHeading({ level: 3 }).run()"
        :class="{ 'is-active': editor?.isActive('heading', { level: 3 }) }"
        title="标题3"
      >
        H3
      </button>
      <span class="divider"></span>
      <button
        type="button"
        @click="editor?.chain().focus().toggleBulletList().run()"
        :class="{ 'is-active': editor?.isActive('bulletList') }"
        title="无序列表"
      >
        • List
      </button>
      <button
        type="button"
        @click="editor?.chain().focus().toggleOrderedList().run()"
        :class="{ 'is-active': editor?.isActive('orderedList') }"
        title="有序列表"
      >
        1. List
      </button>
      <span class="divider"></span>
      <button
        type="button"
        @click="editor?.chain().focus().setTextAlign('left').run()"
        :class="{ 'is-active': editor?.isActive({ textAlign: 'left' }) }"
        title="左对齐"
      >
        ←
      </button>
      <button
        type="button"
        @click="editor?.chain().focus().setTextAlign('center').run()"
        :class="{ 'is-active': editor?.isActive({ textAlign: 'center' }) }"
        title="居中"
      >
        ↔
      </button>
      <button
        type="button"
        @click="setLink()"
        :class="{ 'is-active': editor?.isActive('link') }"
        title="插入链接"
      >
        🔗
      </button>
      <button
        type="button"
        @click="editor?.chain().focus().toggleHighlight().run()"
        :class="{ 'is-active': editor?.isActive('highlight') }"
        title="高亮"
      >
        🖍️
      </button>
    </div>

    <EditorContent :editor="editor" class="editor-content" />

    <div v-if="showCharCount && maxLength" class="char-count" :class="{ 'warning': charCount > maxLength * 0.9, 'error': charCount >= maxLength }">
      {{ charCount }} / {{ maxLength }}
    </div>
  </div>
</template>

<style scoped>
.tiptap-editor {
  border: 1px solid #E5E7EB;
  border-radius: 8px;
  overflow: hidden;
  background: #fff;
}
.tiptap-editor.readonly {
  background: #FAFAFA;
  border-color: #F0F0F0;
}

.toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  padding: 8px 12px;
  background: #F9FAFB;
  border-bottom: 1px solid #E5E7EB;
  align-items: center;
}

.toolbar button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: 1px solid transparent;
  border-radius: 6px;
  background: transparent;
  color: #374151;
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  transition: all 0.15s;
}
.toolbar button:hover {
  background: #E5E7EB;
  border-color: #D1D5DB;
}
.toolbar button.is-active {
  background: #EFF6FF;
  border-color: #3B82F6;
  color: #2563EB;
}

.divider {
  width: 1px;
  height: 20px;
  background: #E5E7EB;
  margin: 0 4px;
}

.editor-content {
  padding: 16px;
  min-height: 120px;
}
.editor-content :deep(.tiptap) {
  outline: none;
  min-height: 100px;
  font-size: 15px;
  line-height: 1.75;
  color: #111827;
}
.editor-content :deep(.tiptap p.is-editor-empty:first-child::before) {
  content: attr(data-placeholder);
  float: left;
  color: #9CA3AF;
  pointer-events: none;
  height: 0;
}
.editor-content :deep(.tiptap h1) {
  font-size: 20px;
  font-weight: 700;
  margin: 12px 0 8px;
  line-height: 1.4;
}
.editor-content :deep(.tiptap h2) {
  font-size: 18px;
  font-weight: 600;
  margin: 10px 0 6px;
  line-height: 1.4;
}
.editor-content :deep(.tiptap h3) {
  font-size: 16px;
  font-weight: 600;
  margin: 8px 0 4px;
  line-height: 1.4;
}
.editor-content :deep(.tiptap ul),
.editor-content :deep(.tiptap ol) {
  padding-left: 20px;
  margin: 8px 0;
}
.editor-content :deep(.tiptap li) {
  margin: 4px 0;
}
.editor-content :deep(.tiptap mark) {
  background-color: #FEF08A;
  border-radius: 2px;
  padding: 0 2px;
}
.editor-content :deep(.tiptap a) {
  color: #2563EB;
  text-decoration: underline;
  cursor: pointer;
}
.tiptap-editor.readonly .editor-content :deep(.tiptap) {
  color: #374151;
}

.char-count {
  padding: 6px 16px;
  font-size: 12px;
  color: #9CA3AF;
  text-align: right;
  background: #F9FAFB;
  border-top: 1px solid #E5E7EB;
  font-variant-numeric: tabular-nums;
}
.char-count.warning {
  color: #F59E0B;
  background: #FFFBEB;
}
.char-count.error {
  color: #EF4444;
  background: #FEF2F2;
  font-weight: 600;
}
</style>