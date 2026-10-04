<template>
  <div class="agent-progress-card">
    <div class="agent-progress-header">
      <img :src="statusIconSrc" class="agent-progress-icon" v-if="statusIconSrc" />
      <span class="agent-progress-icon" v-else>{{ statusIcon }}</span>
      <span class="agent-progress-title">{{ statusText }}</span>
      <span v-if="(totalPercent ?? 0) > 0" class="agent-progress-percent">{{ totalPercent ?? 0 }}%</span>
      <button
        v-if="workflowStatus === 'error' && workflowId"
        class="agent-progress-retry"
        @click="emit('retry', workflowId)"
        title="重试工作流"
      >重试</button>
    </div>
    <div class="agent-progress-bar">
      <div
        class="agent-progress-fill"
        :style="{ width: (totalPercent ?? 0) + '%' }"
        :class="barClass"
      ></div>
    </div>
    <div class="agent-progress-steps">
      <div
        v-for="step in steps"
        :key="step.nodeKey"
        class="agent-progress-step"
        :class="`is-${step.status}`"
      >
        <span class="agent-step-indicator">
          <template v-if="step.status === 'completed'">✓</template>
          <template v-else-if="step.status === 'running'">◉</template>
          <template v-else-if="step.status === 'awaiting_review'">⚑</template>
          <template v-else-if="step.status === 'error'">✕</template>
          <template v-else>○</template>
        </span>
        <span class="agent-step-label">{{ step.nodeLabel }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { AgentStep } from './cell-types'

const props = defineProps<{
  steps: AgentStep[]
  workflowStatus?: string
  totalPercent?: number
  workflowId?: string
}>()

const emit = defineEmits<{
  retry: [workflowId: string]
}>()

const statusIcon = computed(() => {
  switch (props.workflowStatus) {
    case 'completed': return '✓'
    case 'error': return '✕'
    case 'awaiting_review': return '⚑'
    case 'suspended': return '⏸'
    default: return '▶'
  }
})

const statusIconSrc = computed(() => {
  switch (props.workflowStatus) {
    case 'completed': return '/icons/发布.svg'
    case 'awaiting_review': return '/icons/分析.svg'
    default: return '/icons/思考过程-深度思考.svg'
  }
})

const statusText = computed(() => {
  switch (props.workflowStatus) {
    case 'completed': return '工作流完成'
    case 'error': return '工作流出错'
    case 'awaiting_review': return '等待审核'
    case 'suspended': return '已暂停'
    default: return '执行中…'
  }
})

const barClass = computed(() => {
  switch (props.workflowStatus) {
    case 'completed': return 'is-completed'
    case 'error': return 'is-error'
    case 'awaiting_review': return 'is-review'
    default: return 'is-running'
  }
})
</script>

<style scoped>
.agent-progress-card {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  padding: 10px 12px;
  margin-top: 6px;
}

.agent-progress-header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 500;
  color: #334155;
  margin-bottom: 6px;
}

.agent-progress-icon {
  font-weight: 700;
  width: 14px !important;
  height: 14px !important;
  max-width: 14px !important;
  max-height: 14px !important;
  object-fit: contain;
  flex-shrink: 0;
}

.agent-progress-percent {
  margin-left: auto;
  font-size: 12px;
  color: #94a3b8;
  font-variant-numeric: tabular-nums;
}

.agent-progress-retry {
  margin-left: 8px;
  padding: 2px 10px;
  border-radius: 4px;
  border: 1px solid #fca5a5;
  background: #fef2f2;
  color: #ef4444;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
}

.agent-progress-retry:hover {
  background: #fee2e2;
  border-color: #ef4444;
}

.agent-progress-bar {
  height: 4px;
  background: #e2e8f0;
  border-radius: 2px;
  overflow: hidden;
  margin-bottom: 8px;
}

.agent-progress-fill {
  height: 100%;
  border-radius: 2px;
  transition: width 0.4s ease;
}

.agent-progress-fill.is-running {
  background: #3b82f6;
}

.agent-progress-fill.is-completed {
  background: #22c55e;
}

.agent-progress-fill.is-error {
  background: #ef4444;
}

.agent-progress-fill.is-review {
  background: #f59e0b;
}

.agent-progress-steps {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 12px;
}

.agent-progress-step {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: #94a3b8;
}

.agent-step-indicator {
  font-size: 11px;
  width: 14px;
  text-align: center;
}

.agent-step-label {
  line-height: 1.4;
}

.agent-progress-step.is-completed {
  color: #22c55e;
}

.agent-progress-step.is-running {
  color: #3b82f6;
  font-weight: 500;
}

.agent-progress-step.is-awaiting_review {
  color: #f59e0b;
  font-weight: 500;
}

.agent-progress-step.is-error {
  color: #ef4444;
}

.agent-progress-step.is-pending {
  color: #cbd5e1;
}
</style>