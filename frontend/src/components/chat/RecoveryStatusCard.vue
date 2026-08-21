<template>
  <div class="recovery-status-card" :class="`is-${status}`">
    <span class="recovery-status-icon">{{ icon }}</span>
    <span class="recovery-status-text">{{ text }}</span>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { RecoveryStatus } from './cell-types'

const props = defineProps<{
  status: RecoveryStatus
  strategy?: string
  attempt?: number
  message?: string
}>()

const icon = computed(() => {
  switch (props.status) {
    case 'retrying':
      return '⟳'
    case 'failed':
      return '✕'
    case 'success':
      return '✓'
    case 'circuit_open':
      return '⚠'
    default:
      return '•'
  }
})

const text = computed(() => {
  switch (props.status) {
    case 'retrying':
      return [
        '正在重试',
        props.strategy ? `（策略：${props.strategy}）` : '',
        props.attempt ? ` · 第 ${props.attempt} 次` : '',
        '…',
      ].join('')
    case 'failed':
      return props.message || '重试失败'
    case 'success':
      return '已恢复正常'
    case 'circuit_open':
      return '服务暂时过载，已暂停重试'
    default:
      return ''
  }
})
</script>

<style scoped>
.recovery-status-card {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  border-radius: 8px;
  font-size: 13px;
  line-height: 1.4;
  border: 1px solid transparent;
}

.recovery-status-icon {
  flex-shrink: 0;
  font-weight: 600;
}

.is-retrying {
  background: #eff6ff;
  border-color: #bfdbfe;
  color: #1d4ed8;
}

.is-failed {
  background: #fef2f2;
  border-color: #fecaca;
  color: #b91c1c;
}

.is-success {
  background: #f0fdf4;
  border-color: #bbf7d0;
  color: #15803d;
}

.is-circuit_open {
  background: #fffbeb;
  border-color: #fde68a;
  color: #b45309;
}
</style>
