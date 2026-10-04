<template>
  <div class="script-view">
    <div class="sv-header">
      <h3 class="sv-title">{{ title || '脚本' }}</h3>
      <span class="sv-meta" v-if="meta">{{ meta }}</span>
    </div>
    <div class="sv-body">
      <div v-if="!scriptText" class="sv-empty">暂无脚本内容</div>
      <pre v-else class="sv-script">{{ scriptText }}</pre>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  scriptText: string
  title?: string
  meta?: string
}>()
</script>

<style scoped>
.script-view {
  display: flex;
  flex-direction: column;
  min-height: 100%;
  overflow-y: auto;
  scrollbar-width: thin;
  scrollbar-color: rgba(0,0,0,0.12) transparent;
}
.script-view::-webkit-scrollbar { width: 4px; }
.script-view::-webkit-scrollbar-thumb { background: rgba(0,0,0,0.12); border-radius: 2px; }

.sv-header {
  padding: 12px;
  border-bottom: 1px solid rgba(0,0,0,0.06);
  flex-shrink: 0;
}
.sv-title {
  font-size: 15px;
  font-weight: 600;
  color: #1a1a1a;
  margin: 0;
}
.sv-meta {
  font-size: 11px;
  color: #888;
  margin-top: 4px;
  display: block;
}
.sv-body {
  padding: 12px;
  flex: 1;
}
.sv-empty {
  color: #aaa;
  font-size: 13px;
}
.sv-script {
  font-family: 'Menlo', 'Consolas', monospace;
  font-size: 12px;
  line-height: 1.6;
  color: #333;
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0;
  background: rgba(0,0,0,0.02);
  padding: 12px;
  border-radius: 6px;
}
</style>