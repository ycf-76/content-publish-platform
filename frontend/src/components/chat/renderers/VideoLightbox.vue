<template>
  <div class="mr-video-lb">
    <video
      v-if="page.videoUrl"
      :src="page.videoUrl"
      controls
      preload="metadata"
      class="mr-video-lb-player"
    ></video>
    <div v-if="page.videoMeta" class="mr-video-lb-meta">
      <span
        v-if="page.videoMeta.publishStatus"
        class="mr-video-status"
        :class="'mr-vs-' + page.videoMeta.publishStatus"
      >
        {{ statusLabel(page.videoMeta.publishStatus) }}
      </span>
      <a
        v-if="page.videoMeta.postId"
        class="mr-video-link"
        :href="'https://www.xiaohongshu.com/explore/' + page.videoMeta.postId"
        target="_blank"
        rel="noopener"
      >查看笔记</a>
      <span v-if="page.videoMeta.message" class="mr-video-msg">{{ page.videoMeta.message }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { MediaPage } from '@/types/media-content'

defineProps<{ page: MediaPage }>()

function statusLabel(s?: string): string {
  const map: Record<string, string> = { published: '已发布', failed: '发布失败', pending: '发布中', unknown: '未知' }
  return map[s || 'unknown'] || s || ''
}
</script>

<style scoped>
.mr-video-lb {
  width: 100%;
  max-width: 800px;
  background: #fff;
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.12);
}
.mr-video-lb-player {
  width: 100%;
  max-height: 70vh;
  display: block;
}
.mr-video-lb-meta {
  padding: 12px 16px;
  background: #f9fafb;
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.mr-video-status {
  font-size: 13px;
  padding: 2px 8px;
  border-radius: 4px;
  font-weight: 500;
}
.mr-vs-published { background: #065f46; color: #a7f3d0; }
.mr-vs-failed { background: #7f1d1d; color: #fca5a5; }
.mr-vs-pending { background: #78350f; color: #fde68a; }
.mr-vs-unknown { background: #374151; color: #d1d5db; }
.mr-video-link {
  font-size: 13px;
  color: #60a5fa;
  text-decoration: none;
}
.mr-video-link:hover { text-decoration: underline; }
.mr-video-msg {
  font-size: 12px;
  color: #9ca3af;
}
</style>