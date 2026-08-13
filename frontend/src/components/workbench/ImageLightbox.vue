<template>
  <Teleport to="body">
    <div v-if="visible" class="wf-preview-overlay" @click="$emit('close')">
      <div class="wf-preview-container" @click.stop>
        <button class="wf-preview-close" @click="$emit('close')" aria-label="关闭">×</button>
        <button v-if="list.length > 1" class="wf-preview-nav wf-preview-prev" @click="$emit('prev')" aria-label="上一张">‹</button>
        <img :src="currentUrl" class="wf-preview-img" alt="预览大图">
        <button v-if="list.length > 1" class="wf-preview-nav wf-preview-next" @click="$emit('next')" aria-label="下一张">›</button>
        <div v-if="list.length > 1" class="wf-preview-counter">{{ currentIndex + 1 }} / {{ list.length }}</div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
defineProps<{
  visible: boolean
  currentUrl: string
  list: { dataUrl: string }[]
  currentIndex: number
}>()

defineEmits<{
  close: []
  prev: []
  next: []
}>()
</script>