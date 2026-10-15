<template>
  <div class="mr-video-thumb">
    <template v-if="progress && progress.percent < 100">
      <div class="mr-video-icon">⏳</div>
      <span class="mr-video-label">{{ progress.label || '视频生成中' }}</span>
      <div class="mr-video-progress-bar">
        <div
          class="mr-video-progress-fill"
          :style="{ width: `${progress.percent}%` }"
        />
      </div>
      <span class="mr-video-percent">{{ progress.percent }}%</span>
      <span v-if="progress.detail" class="mr-video-detail">{{ progress.detail }}</span>
    </template>
    <template v-else-if="page.videoUrl">
      <video
        class="mr-video-preview"
        :src="page.videoUrl"
        muted
        preload="metadata"
        @mouseenter="($event.target as HTMLVideoElement)?.play()"
        @mouseleave="($event.target as HTMLVideoElement)?.pause()"
      />
      <span class="mr-video-label">{{ page.title || '视频' }}</span>
    </template>
    <template v-else>
      <div class="mr-video-icon">🎬</div>
      <span class="mr-video-label">{{ page.title || '视频' }}</span>
    </template>
  </div>
</template>

<script setup lang="ts">
import type { MediaPage } from '@/types/media-content'

const props = defineProps<{
  page: MediaPage
  progress?: {
    skill: string
    step?: number
    total?: number
    label?: string
    detail?: string
    percent: number
    provider?: string
    mode?: string
    elapsed?: number
    status?: string
  }
}>()
</script>

<style scoped>
.mr-video-thumb {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #ede9fe 0%, #ddd6fe 100%);
  border-radius: 6px;
  gap: 6px;
  overflow: hidden;
}
.mr-video-icon {
  font-size: 28px;
}
.mr-video-label {
  font-size: 12px;
  color: #5b21b6;
  font-weight: 500;
}
.mr-video-progress-bar {
  width: 80%;
  height: 4px;
  background: rgba(91, 33, 182, 0.15);
  border-radius: 2px;
  overflow: hidden;
}
.mr-video-progress-fill {
  height: 100%;
  background: #7c3aed;
  border-radius: 2px;
  transition: width 0.3s ease;
}
.mr-video-percent {
  font-size: 11px;
  color: #7c3aed;
  font-weight: 600;
}
.mr-video-detail {
  font-size: 10px;
  color: #6d28d9;
  opacity: 0.7;
}
.mr-video-preview {
  width: 100%;
  height: 100%;
  object-fit: cover;
  border-radius: 6px;
}
</style>