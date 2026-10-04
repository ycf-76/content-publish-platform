<template>
  <div class="error-fallback">
    <AlertCircle :size="20" :stroke-width="1.5" class="ef-icon" />
    <span class="ef-message">{{ message }}</span>
    <button v-if="retryable" class="ef-retry" @click="$emit('retry')">
      <RefreshCw :size="12" /> 重试
    </button>
  </div>
</template>

<script setup lang="ts">
import { AlertCircle, RefreshCw } from 'lucide-vue-next'

defineProps<{
  message: string
  retryable?: boolean
}>()

defineEmits<{
  retry: []
}>()
</script>

<style scoped>
.error-fallback {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 24px;
  text-align: center;
  height: 100%;
}
.ef-icon { color: #e67e22; }
.ef-message { font-size: 13px; color: #888; max-width: 200px; }
.ef-retry {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  font-size: 12px;
  color: #555;
  border: 1px solid rgba(0,0,0,0.1);
  border-radius: 6px;
  background: #fafafa;
  cursor: pointer;
}
.ef-retry:hover { background: #f0f0f0; }
</style>