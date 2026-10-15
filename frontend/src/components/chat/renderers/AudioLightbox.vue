<template>
  <div class="mr-audio-lb">
    <div class="mr-audio-lb-header">
      <span class="mr-audio-lb-icon">🎵</span>
      <span class="mr-audio-lb-title">{{ page.title || '音频' }}</span>
    </div>
    <audio
      v-if="page.audioUrl"
      :src="page.audioUrl"
      controls
      class="mr-audio-lb-player"
    ></audio>
    <div
      v-else-if="page.htmlContent"
      class="mr-audio-lb-fallback"
      v-html="page.htmlContent"
    ></div>
  </div>
</template>

<script setup lang="ts">
import type { MediaPage } from '@/types/media-content'

defineProps<{ page: MediaPage }>()
</script>

<style scoped>
.mr-audio-lb {
  width: 100%;
  max-width: 600px;
  background: #fff;
  border-radius: 16px;
  padding: 24px;
  box-shadow: 0 4px 24px rgba(0,0,0,.1);
}
.mr-audio-lb-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 16px;
}
.mr-audio-lb-icon {
  font-size: 24px;
}
.mr-audio-lb-title {
  font-size: 16px;
  font-weight: 600;
  color: #211e1a;
}
.mr-audio-lb-player {
  width: 100%;
  border-radius: 8px;
}
.mr-audio-lb-fallback {
  width: 100%;
}
</style>