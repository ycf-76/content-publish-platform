<script setup lang="ts">
import { useTemplateStore } from '@/stores/templates'
import { computed, onMounted } from 'vue'
import type { TemplateManifest } from '@/api/templates'

const props = defineProps<{
  currentTemplateId: string
  selectedPlatform: string
}>()

const emit = defineEmits<{
  select: [templateId: string]
}>()

const store = useTemplateStore()

onMounted(() => {
  store.ensureLoaded()
})

const filteredTemplates = computed(() => {
  return store.templates.filter((t: TemplateManifest) => {
    if (props.selectedPlatform && t.platforms) {
      return props.selectedPlatform in t.platforms
    }
    return true
  })
})
</script>

<template>
  <div class="template-gallery">
    <div v-if="store.loading" class="gallery-loading">加载中...</div>
    <div v-else-if="store.error" class="gallery-error">{{ store.error }}</div>
    <div v-else class="gallery-grid">
      <div
        v-for="tpl in filteredTemplates"
        :key="tpl.id"
        class="gallery-card"
        :class="{ active: tpl.id === currentTemplateId }"
        @click="emit('select', tpl.id)"
      >
        <div class="gallery-preview" :style="{ background: tpl.theme?.bg || '#fff' }">
          <div class="gallery-accent-bar" :style="{ background: tpl.theme?.accent || '#2563eb' }"></div>
          <div class="gallery-text-line" :style="{ background: tpl.theme?.text || '#1a1a1a', width: '60%' }"></div>
          <div class="gallery-text-line" :style="{ background: tpl.theme?.subtext || '#6b7280', width: '80%' }"></div>
          <div class="gallery-text-line" :style="{ background: tpl.theme?.subtext || '#6b7280', width: '45%' }"></div>
        </div>
        <div class="gallery-info">
          <span class="gallery-name">{{ tpl.name }}</span>
          <span class="gallery-desc">{{ tpl.description }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.template-gallery {
  display: flex;
  flex-direction: column;
  gap: 8px;
  height: 100%;
}
.gallery-loading, .gallery-error {
  font-size: 12px;
  color: #94a3b8;
  text-align: center;
  padding: 20px 0;
}
.gallery-grid {
  display: flex;
  flex-direction: column;
  gap: 6px;
  overflow-y: auto;
  flex: 1;
  min-height: 0;
}
.gallery-card {
  display: flex;
  gap: 10px;
  padding: 8px;
  border-radius: 8px;
  cursor: pointer;
  border: 2px solid transparent;
  transition: all 0.15s;
}
.gallery-card:hover { background: rgba(255,255,255,0.05); border-color: rgba(255,255,255,0.08); }
.gallery-card.active { border-color: #2563eb; background: rgba(37,99,235,0.1); }
.gallery-preview {
  width: 48px;
  height: 64px;
  border-radius: 4px;
  flex-shrink: 0;
  padding: 6px 5px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  overflow: hidden;
}
.gallery-accent-bar {
  height: 3px;
  border-radius: 2px;
  width: 100%;
}
.gallery-text-line {
  height: 3px;
  border-radius: 2px;
  opacity: 0.6;
}
.gallery-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.gallery-name {
  font-size: 12px;
  font-weight: 600;
  color: #e2e8f0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.gallery-card.active .gallery-name { color: #93c5fd; }
.gallery-desc {
  font-size: 10px;
  color: #64748b;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>