<template>
  <div class="vp-wrap">
    <div class="vp-header">
      <h3 class="vp-title">{{ work.title || '视频' }}</h3>
      <span class="vp-meta" v-if="meta">{{ meta }}</span>
    </div>
    <div class="vp-body">
      <video
        v-if="videoSrc"
        :src="videoSrc"
        controls
        preload="metadata"
        class="vp-player"
      ></video>
      <div v-else class="vp-empty">
        <Video :size="32" :stroke-width="1.2" />
        <span>视频地址不可用</span>
      </div>
    </div>
    <div v-if="work.scriptText" class="vp-script">
      <div class="vp-script-label">脚本</div>
      <pre class="vp-script-text">{{ work.scriptText }}</pre>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Video } from 'lucide-vue-next'
import type { WorkItem } from '@/stores/work'

const props = defineProps<{
  work: WorkItem
  meta?: string
}>()

const videoSrc = computed(() => {
  if (props.work.videoUrl) return props.work.videoUrl
  const pages = props.work.cardDraft?.pages
  if (pages?.length) {
    const videoPage = pages.find((p: any) => p?.mediaType === 'video' && p?.videoUrl)
    if (videoPage) return (videoPage as any).videoUrl
  }
  return ''
})
</script>

<style scoped>
.vp-wrap {
  display: flex;
  flex-direction: column;
  min-height: 100%;
  overflow-y: auto;
  scrollbar-width: thin;
  scrollbar-color: rgba(0,0,0,0.12) transparent;
}
.vp-wrap::-webkit-scrollbar { width: 4px; }
.vp-wrap::-webkit-scrollbar-thumb { background: rgba(0,0,0,0.12); border-radius: 2px; }

.vp-header {
  padding: 12px;
  border-bottom: 1px solid rgba(0,0,0,0.06);
  flex-shrink: 0;
}
.vp-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--rl-text-1);
  margin: 0;
}
.vp-meta {
  font-size: 11px;
  color: var(--rl-text-3);
  margin-top: 4px;
  display: block;
}
.vp-body {
  padding: 12px;
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #f3f4f6;
  border-radius: 8px;
  margin: 0 12px;
  overflow: hidden;
}
.vp-player {
  width: 100%;
  max-height: 70vh;
  display: block;
  border-radius: 8px;
}
.vp-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  color: #888;
  font-size: 13px;
  padding: 40px 0;
}
.vp-script {
  padding: 12px;
  margin-top: 8px;
}
.vp-script-label {
  font-size: 12px;
  font-weight: 500;
  color: #888;
  margin-bottom: 6px;
}
.vp-script-text {
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