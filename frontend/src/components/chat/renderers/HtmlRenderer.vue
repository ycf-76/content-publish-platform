<template>
  <div class="mr-thumb-iframe-wrap">
    <iframe
      sandbox="allow-same-origin allow-scripts"
      :srcdoc="page.htmlContent"
      class="mr-thumb-iframe"
      loading="lazy"
      :style="iframeStyle"
    ></iframe>
  </div>
</template>

<script setup lang="ts">
import type { MediaPage } from '@/types/media-content'

defineProps<{
  page: MediaPage
  iframeStyle?: Record<string, unknown>
}>()
</script>

<style scoped>
.mr-thumb-iframe-wrap {
  width: 100%;
  height: 100%;
  overflow: hidden;
  pointer-events: none;
  border-radius: 6px;
}
.mr-thumb-iframe {
  border: none;
}
</style>