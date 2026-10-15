<template>
  <img
    :src="page.imageUrl"
    class="mr-thumb-img"
    loading="lazy"
    @error="onError"
  />
</template>

<script setup lang="ts">
import type { MediaPage } from '@/types/media-content'

defineProps<{ page: MediaPage }>()
const emit = defineEmits<{ error: [e: Event] }>()

function onError(e: Event) {
  emit('error', e)
  const img = e.target as HTMLImageElement
  if (img && img.src && !img.src.includes('/api/proxy/image') && img.src.startsWith('http')) {
    img.src = '/api/proxy/image?url=' + encodeURIComponent(img.src)
    return
  }
  if (img) img.style.display = 'none'
}
</script>

<style scoped>
.mr-thumb-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  border-radius: 6px;
}
</style>