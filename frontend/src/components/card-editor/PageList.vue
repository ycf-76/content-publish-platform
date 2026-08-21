<script setup lang="ts">
import { ref } from 'vue'
import { FULL_PAGE_TYPE_LABELS, type FullPageType, type EstherCardPage } from '@/card-editor/esther-templates'

const props = defineProps<{
  pages: EstherCardPage[]
  selectedPageId: string
}>()

const emit = defineEmits<{
  select: [id: string]
  move: [id: string, direction: 'up' | 'down']
  delete: [id: string]
  duplicate: [id: string]
  add: [type: FullPageType]
  reorder: [fromIndex: number, toIndex: number]
}>()

const dragIndex = ref<number | null>(null)
const dropTargetIndex = ref<number | null>(null)

function onDragStart(index: number) {
  dragIndex.value = index
}

function onDragOver(e: DragEvent, index: number) {
  e.preventDefault()
  dropTargetIndex.value = index
}

function onDragLeave() {
  dropTargetIndex.value = null
}

function onDrop(e: DragEvent, index: number) {
  e.preventDefault()
  if (dragIndex.value !== null && dragIndex.value !== index) {
    emit('reorder', dragIndex.value, index)
  }
  dragIndex.value = null
  dropTargetIndex.value = null
}

function onDragEnd() {
  dragIndex.value = null
  dropTargetIndex.value = null
}

function pageCharCount(page: any): number {
  const parts = [page.title || '', page.subtitle || '', page.content || '', ...(page.listItems || [])]
  return parts.join('').length
}
</script>

<template>
  <div class="page-list-panel">
    <div class="page-list-items">
      <div
        v-for="(page, i) in pages"
        :key="page.id"
        class="page-item"
        :class="{
          active: page.id === selectedPageId,
          'drag-over': dropTargetIndex === i && dragIndex !== i,
          'dragging': dragIndex === i
        }"
        draggable
        @click="emit('select', page.id)"
        @dragstart="onDragStart(i)"
        @dragover="onDragOver($event, i)"
        @dragleave="onDragLeave"
        @drop="onDrop($event, i)"
        @dragend="onDragEnd"
      >
        <span class="drag-handle" title="拖拽排序">⠿</span>
        <span class="page-num">{{ i + 1 }}</span>
        <span class="page-type">{{ FULL_PAGE_TYPE_LABELS[page.type as FullPageType] || page.type }}</span>
        <span class="page-title">{{ page.title || (page.content || '').slice(0, 10) }}</span>
        <span class="page-chars">{{ pageCharCount(page) }}字</span>
        <div class="page-actions">
          <button class="icon-btn" @click.stop="emit('duplicate', page.id)" title="复制">⧉</button>
          <button class="icon-btn icon-btn-danger" :disabled="pages.length <= 1" @click.stop="emit('delete', page.id)" title="删除">×</button>
        </div>
      </div>
    </div>
    <div class="page-add">
      <button v-for="(label, key) in FULL_PAGE_TYPE_LABELS" :key="key" class="add-btn" @click="emit('add', key as FullPageType)">
        + {{ label }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.page-list-panel {
  display: flex;
  flex-direction: column;
  gap: 8px;
  height: 100%;
}
.page-list-items {
  display: flex;
  flex-direction: column;
  gap: 2px;
  overflow-y: auto;
  flex: 1;
  min-height: 0;
}
.page-item {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 6px 6px;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.12s;
}
.page-item:hover { background: rgba(255,255,255,0.06); }
.page-item.active { background: rgba(37, 99, 235, 0.18); }
.page-item.dragging { opacity: 0.4; }
.page-item.drag-over { border-top: 2px solid #2563eb; }
.drag-handle {
  cursor: grab;
  font-size: 12px;
  color: #475569;
  flex-shrink: 0;
  padding: 0 2px;
  user-select: none;
}
.drag-handle:active { cursor: grabbing; }
.page-num { font-size: 11px; font-weight: 700; color: #94a3b8; min-width: 16px; flex-shrink: 0; }
.page-type {
  font-size: 9px;
  padding: 1px 5px;
  background: rgba(255,255,255,0.08);
  border-radius: 3px;
  color: #94a3b8;
  flex-shrink: 0;
  white-space: nowrap;
}
.page-item.active .page-type { background: #2563eb; color: #fff; }
.page-title {
  flex: 1;
  font-size: 11px;
  color: #cbd5e1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}
.page-chars { font-size: 9px; color: #64748b; flex-shrink: 0; white-space: nowrap; }
.page-actions { display: flex; gap: 1px; flex-shrink: 0; }
.icon-btn {
  width: 20px; height: 20px;
  display: flex; align-items: center; justify-content: center;
  background: transparent; border: none; border-radius: 4px;
  color: #64748b; cursor: pointer; font-size: 11px;
  transition: all 0.12s;
}
.icon-btn:hover:not(:disabled) { background: rgba(255,255,255,0.1); color: #e2e8f0; }
.icon-btn:disabled { opacity: 0.25; cursor: not-allowed; }
.icon-btn-danger:hover:not(:disabled) { background: rgba(239,68,68,0.2); color: #f87171; }
.page-add {
  display: flex;
  flex-wrap: wrap;
  gap: 3px;
  padding-top: 8px;
  border-top: 1px solid rgba(255,255,255,0.06);
}
.add-btn {
  padding: 3px 7px;
  background: rgba(255,255,255,0.05);
  border: none;
  border-radius: 4px;
  color: #64748b;
  font-size: 10px;
  cursor: pointer;
  white-space: nowrap;
  transition: all 0.12s;
}
.add-btn:hover { color: #93c5fd; background: rgba(37,99,235,0.15); }
</style>