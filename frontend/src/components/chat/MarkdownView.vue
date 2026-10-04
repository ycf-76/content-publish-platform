<template>
  <div class="md-view">
    <div class="md-view-header" v-if="title">
      <h3 class="md-view-title">{{ title }}</h3>
      <span class="md-view-meta" v-if="meta">{{ meta }}</span>
    </div>
    <div class="md-view-body" v-html="renderedHtml"></div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { renderMarkdown } from './markdown-renderer'

const props = defineProps<{
  content: string
  title?: string
  meta?: string
}>()

const renderedHtml = computed(() => {
  if (!props.content) return '<p style="color:#aaa">暂无内容</p>'
  return renderMarkdown(props.content)
})
</script>

<style scoped>
.md-view {
  display: flex;
  flex-direction: column;
  min-height: 100%;
  overflow-y: auto;
  scrollbar-width: thin;
  scrollbar-color: rgba(0,0,0,0.12) transparent;
}
.md-view::-webkit-scrollbar { width: 4px; }
.md-view::-webkit-scrollbar-thumb { background: rgba(0,0,0,0.12); border-radius: 2px; }

.md-view-header {
  padding: 12px;
  border-bottom: 1px solid rgba(0,0,0,0.06);
  flex-shrink: 0;
}
.md-view-title {
  font-size: 15px;
  font-weight: 600;
  color: #1a1a1a;
  margin: 0;
}
.md-view-meta {
  font-size: 11px;
  color: #888;
  margin-top: 4px;
  display: block;
}

.md-view-body {
  padding: 12px;
  font-size: 13px;
  line-height: 1.7;
  color: #333;
}
.md-view-body :deep(h1) { font-size: 18px; margin: 16px 0 8px; }
.md-view-body :deep(h2) { font-size: 16px; margin: 14px 0 6px; }
.md-view-body :deep(h3) { font-size: 14px; margin: 12px 0 4px; }
.md-view-body :deep(p) { margin: 0 0 8px; }
.md-view-body :deep(ul), .md-view-body :deep(ol) { padding-left: 20px; margin: 0 0 8px; }
.md-view-body :deep(code) {
  background: rgba(0,0,0,0.05);
  padding: 1px 4px;
  border-radius: 3px;
  font-size: 12px;
}
.md-view-body :deep(pre) {
  background: rgba(0,0,0,0.04);
  padding: 8px 12px;
  border-radius: 6px;
  overflow-x: auto;
  margin: 0 0 8px;
}
.md-view-body :deep(blockquote) {
  border-left: 3px solid rgba(0,0,0,0.12);
  padding-left: 12px;
  color: #666;
  margin: 0 0 8px;
}
</style>