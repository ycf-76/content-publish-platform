<script setup lang="ts">
import CardRenderer from '@/components/CardRenderer.vue'
import EstherCardRenderer from '@/components/EstherCardRenderer.vue'
import { type CardPage, type DecorationConfig, type TemplateTheme } from '@/card-editor/templates'
import { FULL_PAGE_TYPE_LABELS, isEstherTemplate, type EstherCardPage, type FullPageType } from '@/card-editor/esther-templates'

const props = defineProps<{
  pages: EstherCardPage[]
  selectedPageId: string
  currentTemplateId: string
  effectiveTheme: TemplateTheme
  currentDecoration: DecorationConfig
  previewScale: number
  boxWidth: number
  boxHeight: number
  setGridRef?: (el: HTMLElement | null) => void
}>()

const emit = defineEmits<{
  select: [id: string]
}>()
</script>

<template>
  <div class="canvas-preview" :ref="(el: any) => props.setGridRef?.(el)">
    <div
      v-for="(page, i) in pages"
      :key="page.id"
      class="preview-card"
      :class="{ active: page.id === selectedPageId }"
      @click="emit('select', page.id)"
    >
      <div class="preview-box" :style="{ width: boxWidth + 'px', height: boxHeight + 'px' }">
        <div class="preview-inner" :style="{ transform: `scale(${previewScale})` }">
          <EstherCardRenderer v-if="isEstherTemplate(currentTemplateId)" :page="page" :theme="effectiveTheme" :decoration="currentDecoration" />
          <CardRenderer v-else :page="page as CardPage" :theme="effectiveTheme" :decoration="currentDecoration" />
        </div>
      </div>
      <div class="preview-label">{{ i + 1 }} · {{ FULL_PAGE_TYPE_LABELS[page.type as FullPageType] || page.type }}</div>
    </div>
  </div>
</template>

<style scoped>
.canvas-preview {
  display: flex;
  gap: 12px;
  overflow-x: auto;
  overflow-y: hidden;
  padding: 4px 2px 12px 2px;
  width: 100%;
  scroll-behavior: smooth;
  -webkit-overflow-scrolling: touch;
  justify-content: safe center;
}
.canvas-preview::-webkit-scrollbar { height: 6px; }
.canvas-preview::-webkit-scrollbar-track { background: rgba(255,255,255,0.04); border-radius: 3px; }
.canvas-preview::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.12); border-radius: 3px; }
.canvas-preview::-webkit-scrollbar-thumb:hover { background: rgba(255,255,255,0.2); }
.preview-card {
  display: flex; flex-direction: column; align-items: center; gap: 6px;
  padding: 8px; border: 2px solid transparent; border-radius: 8px; cursor: pointer;
  flex-shrink: 0;
  transition: all 0.15s;
}
.preview-card:hover { border-color: rgba(255,255,255,0.1); }
.preview-card.active { border-color: #2563eb; }
.preview-box {
  position: relative;
  overflow: hidden;
  border-radius: 6px;
  background: #fff;
  box-shadow: 0 4px 16px rgba(0,0,0,0.3);
}
.preview-inner {
  position: absolute;
  top: 0;
  left: 0;
  width: 1080px;
  height: 1440px;
  transform-origin: top left;
  pointer-events: none;
}
.preview-inner :deep(.card-canvas) { box-shadow: none; }
.preview-label { font-size: 11px; color: #94a3b8; white-space: nowrap; }
</style>
