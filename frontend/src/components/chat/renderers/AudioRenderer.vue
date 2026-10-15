<template>
  <div class="mr-audio-thumb">
    <div class="mr-audio-icon">🎵</div>
    <span class="mr-audio-label">{{ page.title || '音频' }}</span>
  </div>
</template>

<script setup lang="ts">
import type { MediaPage } from '@/types/media-content'

defineProps<{ page: MediaPage }>()
</script>

<style scoped>
.mr-audio-thumb {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%);
  border-radius: 6px;
  gap: 6px;
}
.mr-audio-icon {
  font-size: 28px;
}
.mr-audio-label {
  font-size: 12px;
  color: #92400e;
  font-weight: 500;
}
</style>