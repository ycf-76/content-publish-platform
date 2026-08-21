<template>
  <div
    class="custom-node"
    :class="[`node-${data.category}`, { selected, executing: data.executing }]"
    @click="$emit('click')"
  >
    <div class="node-header">
      <span class="node-icon">{{ data.icon || '📦' }}</span>
      <span class="node-title">{{ data.label || '未命名' }}</span>
      <div class="node-actions">
        <button class="action-btn" @click.stop="$emit('configure', id)" title="配置">
          <i data-lucide="settings-2"></i>
        </button>
        <button class="action-btn danger" @click.stop="$emit('delete', id)" title="删除">
          <i data-lucide="trash-2"></i>
        </button>
      </div>
    </div>

    <div class="node-body">
      <div v-if="data.status" class="node-status" :class="data.status">
        <i :data-lucide="statusIcon(data.status)"></i>
        {{ statusText(data.status) }}
      </div>
      <div v-else class="node-type-line">{{ data.nodeType }}</div>

      <div v-if="hasConfigSummary" class="config-summary">
        <div v-for="(value, key) in configSummary" :key="key" class="config-item">
          <span class="config-key">{{ key }}</span>
          <span class="config-value">{{ truncate(value, 15) }}</span>
        </div>
      </div>
    </div>

    <Handle type="target" :position="Position.Left" class="handle handle-input" />
    <Handle type="source" :position="Position.Right" class="handle handle-output" />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Handle, Position } from '@vue-flow/core'

const props = defineProps<{
  id: string
  data: {
    label?: string
    icon?: string
    nodeType?: string
    category?: string
    config?: Record<string, any>
    status?: 'pending' | 'running' | 'completed' | 'failed' | 'skipped'
    executing?: boolean
    [key: string]: any
  }
  selected?: boolean
}>()

defineEmits<{
  (e: 'configure', nodeId: string): void
  (e: 'delete', nodeId: string): void
  (e: 'click'): void
}>()

const hasConfigSummary = computed(() => {
  const config = props.data.config || {}
  return Object.keys(config).length > 0
})

const configSummary = computed(() => {
  const config = props.data.config || {}
  const summary: Record<string, any> = {}
  Object.entries(config).forEach(([key, value]) => {
    if (
      value !== undefined &&
      value !== null &&
      value !== '' &&
      typeof value !== 'object' &&
      !key.startsWith('_') &&
      Object.keys(summary).length < 3
    ) {
      summary[key] = value
    }
  })
  return summary
})

function statusIcon(status: string): string {
  const icons: Record<string, string> = {
    pending: 'clock',
    running: 'loader',
    completed: 'check-circle',
    failed: 'x-circle',
    skipped: 'fast-forward',
  }
  return icons[status] || 'help-circle'
}

function statusText(status: string): string {
  const texts: Record<string, string> = {
    pending: '等待中',
    running: '执行中...',
    completed: '已完成',
    failed: '失败',
    skipped: '已跳过',
  }
  return texts[status] || status
}

function truncate(text: any, maxLength: number): string {
  if (typeof text !== 'string') return String(text).substring(0, maxLength)
  return text.length > maxLength ? text.substring(0, maxLength) + '...' : text
}
</script>

<style scoped>
.custom-node {
  min-width: 220px;
  max-width: 280px;
  background: #ffffff;
  border: 1px solid #ededed;
  border-radius: 8px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06);
  transition: border-color 0.2s ease, box-shadow 0.2s ease, transform 0.2s ease;
  position: relative;
}

.custom-node:hover {
  border-color: #ff2442;
  box-shadow: 0 6px 16px rgba(255, 36, 66, 0.1);
}

.custom-node.selected {
  border-color: #ff2442;
  box-shadow: 0 0 0 3px rgba(255, 36, 66, 0.12), 0 6px 18px rgba(0, 0, 0, 0.08);
}

.node-datasource { --node-accent: #10b981; }
.node-analysis { --node-accent: #3b6cf6; }
.node-creation { --node-accent: #f59e0b; }
.node-review { --node-accent: #ef4444; }
.node-publish { --node-accent: #8b5cf6; }
.node-utility,
.node-custom { --node-accent: #6b7280; }

.node-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  border-bottom: 1px solid #f3f4f6;
  border-radius: 8px 8px 0 0;
  background: #fafafa;
}

.node-icon {
  font-size: 18px;
  line-height: 1;
}

.node-title {
  flex: 1;
  min-width: 0;
  font-size: 13px;
  font-weight: 600;
  color: #1a1a1a;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.node-actions {
  display: flex;
  gap: 2px;
  opacity: 0;
  transition: opacity 0.2s;
}

.custom-node:hover .node-actions { opacity: 1; }

.action-btn {
  width: 24px;
  height: 24px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 0;
  background: transparent;
  cursor: pointer;
  border-radius: 6px;
  color: #6b7280;
  padding: 0;
}

.action-btn:hover { background: #fff1f3; color: #ff2442; }
.action-btn.danger:hover { background: #fee2e2; color: #ef4444; }
.action-btn svg { width: 14px; height: 14px; }

.node-body {
  padding: 10px 12px;
  min-height: 38px;
}

.node-type-line {
  font-family: var(--ma-font-mono);
  font-size: 11px;
  color: #9a9a9a;
}

.node-status {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 8px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 500;
  margin-bottom: 8px;
}

.node-status.pending { background: #f3f4f6; color: #6b7280; }
.node-status.running { background: #fff1f3; color: #ff2442; animation: pulse 1.4s infinite; }
.node-status.completed { background: #ecfdf5; color: #059669; }
.node-status.failed { background: #fef2f2; color: #dc2626; }
.node-status.skipped { background: #f9fafb; color: #6b7280; }
.node-status svg { width: 13px; height: 13px; }

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.55; }
}

.config-summary {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.config-item {
  display: flex;
  gap: 6px;
  font-size: 11px;
  line-height: 1.4;
}

.config-key { color: #9a9a9a; min-width: fit-content; }
.config-value { color: #4b4b4b; font-family: var(--ma-font-mono); word-break: break-all; }

.handle {
  width: 12px !important;
  height: 12px !important;
  border: 2px solid #cbd5e1 !important;
  background: #ffffff !important;
  border-radius: 50% !important;
  transition: all 0.2s !important;
  z-index: 2;
}

.handle:hover {
  border-color: #ff2442 !important;
  background: #ff2442 !important;
  transform: scale(1.3);
}

.handle-input { left: -6px !important; }
.handle-output { right: -6px !important; }

.custom-node.executing {
  animation: nodeExecuting 2s ease-in-out infinite;
}

@keyframes nodeExecuting {
  0%, 100% { box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06), 0 0 0 0 rgba(255, 36, 66, 0.35); }
  50% { box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06), 0 0 0 7px rgba(255, 36, 66, 0); }
}
</style>
