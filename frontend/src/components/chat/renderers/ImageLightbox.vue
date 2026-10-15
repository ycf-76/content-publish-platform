<template>
  <img
    :src="page.imageUrl"
    class="mr-lb-img"
    @error="onError"
  />
</template>

<script setup lang="ts">
import type { MediaPage } from '@/types/media-content'

const props = defineProps<{ page: MediaPage }>()

function onError(e: Event) {
  const img = e.target as HTMLImageElement
  if (img && !img.src.includes('/api/proxy/image') && props.page.imageUrl?.startsWith('http')) {
    img.src = '/api/proxy/image?url=' + encodeURIComponent(props.page.imageUrl)
    return
  }
}
</script>

<style scoped>
.mr-lb-img {
  max-width: min(85vw, 540px);
  max-height: 85vh;
  object-fit: contain;
  border-radius: 12px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.12);
}
</style>