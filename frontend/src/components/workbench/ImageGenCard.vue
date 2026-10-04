<template>
  <div class="mint-wf-card wf-node-card wf-node-image-gen" id="card-image_gen" :class="`wf-state-${nodeStatus}`">
    <div class="mint-wf-header">
      <div class="mint-wf-title-row">
        <div class="mint-wf-step">05</div>
        <div class="wf-node-title-block">
          <div class="mint-wf-title">
            <Image class="wf-node-icon" :size="16" />
            卡片编辑器
            <code class="wf-node-key">image_gen</code>
          </div>
          <div class="wf-node-subtitle">生成并编辑卡片图片</div>
        </div>
      </div>
      <span class="mint-badge wf-status-badge" :style="statusBadgeStyle">
        <span class="mint-status-dot" :style="{ background: statusColor }"></span>
        {{ statusLabel }}
      </span>
    </div>

    <div class="wf-node-summary" v-if="nodeStatus === 'completed'">
      图片已生成并注入
    </div>

    <div class="wf-node-body">
      <!-- idle/pending 状态：等待 image_plan 完成 -->
      <div v-if="(nodeStatus === 'idle' || nodeStatus === 'pending') && !cardDraft" class="wf-empty-hint">
        <Info :size="14" />
        等待图片规划完成后，在卡片编辑器中调整并生成图片
      </div>

      <!-- idle/pending/awaiting_review 状态 + cardDraft 可用：显示卡片编辑器（工作流在 image_gen 前 interrupt 暂停） -->
      <div v-else-if="(nodeStatus === 'idle' || nodeStatus === 'pending' || nodeStatus === 'awaiting_review') && cardDraft" class="wf-card-editor-wrapper">
        <button type="button" class="wf-open-image-workspace" @click="$emit('open-workspace')">
          <LayoutTemplate :size="16" />
          在图片工作区编辑
        </button>
      </div>

      <!-- running 状态 + cardDraft 可用：从历史恢复时后端可能暂时返回 running，但实际在等用户编辑 -->
      <div v-else-if="nodeStatus === 'running' && cardDraft" class="wf-card-editor-wrapper">
        <button type="button" class="wf-open-image-workspace" @click="$emit('open-workspace')">
          <LayoutTemplate :size="16" />
          在图片工作区编辑
        </button>
      </div>

      <!-- running 状态，无 cardDraft -->
      <div v-else-if="nodeStatus === 'running'" class="wf-copywrite-loading">
        <div class="mint-loader"><div class="mint-loader-ball"></div></div>
        <div class="wf-copywrite-loading-text">等待前端注入图片...</div>
      </div>

      <!-- error 状态 -->
      <div v-else-if="nodeStatus === 'error'" class="mint-search-error">
        <AlertCircle :size="20" />
        <span>{{ errorMessage || '图片生成失败' }}</span>
      </div>

      <!-- completed 状态 -->
      <div v-else-if="nodeStatus === 'completed'" class="wf-inject-success">
        <CheckCircle :size="18" style="color:#059669" />
        <span>图片注入成功，已进入下一环节</span>
      </div>
    </div>

    <div class="wf-node-meta" v-if="nodeMeta">
      <span class="wf-meta-item"><Clock :size="12" />{{ nodeMeta.duration }}</span>
      <span class="wf-meta-item"><Cpu :size="12" />{{ nodeMeta.model }}</span>
      <span class="wf-meta-item"><Zap :size="12" />{{ nodeMeta.tokens }} tokens</span>
    </div>

  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
import {
  AlertCircle,
  CheckCircle,
  Clock,
  Cpu,
  Image,
  Info,
  LayoutTemplate,
  Zap,
} from 'lucide-vue-next'
const props = defineProps<{
  nodeStatus: string
  nodeMeta: { duration: string; model: string; tokens: string } | null
  result: any
  errorMessage?: string
  /** image_plan 生成的 card_draft */
  cardDraft?: any
  /** 当前工作流 ID */
  workflowId?: string
}>()

defineEmits<{
  'open-workspace': []
}>()

watch(() => props.nodeStatus, () => {
  
})
watch(() => props.result, () => {}, { deep: true })
watch(() => props.cardDraft, () => {}, { deep: true })

const statusColor = computed(() => {
  const map: Record<string, string> = { idle: '#9CA3AF', pending: '#9CA3AF', awaiting_review: '#F59E0B', running: '#FF2442', completed: '#60A5FA', error: '#EF4444' }
  return map[props.nodeStatus] || '#9CA3AF'
})

const statusLabel = computed(() => {
  const map: Record<string, string> = { idle: '待编辑', pending: '待编辑', awaiting_review: '请编辑卡片', running: '执行中', completed: '已完成', error: '失败' }
  return map[props.nodeStatus] || '待执行'
})

const statusBadgeStyle = computed(() => {
  if (props.nodeStatus === 'error') return { background: '#FEE2E2', color: '#DC2626' }
  if (props.nodeStatus === 'completed') return { background: '#DBEAFE', color: '#2563EB' }
  if (props.nodeStatus === 'running') return { background: '#FEE2E2', color: '#DC2626' }
  if (props.nodeStatus === 'awaiting_review') return { background: '#FFFBEB', color: '#D97706' }
  return { background: '#F1F5F9', color: '#64748B' }
})

/** 从 axios 错误中提取可读信息 */
</script>

<style scoped>
.wf-card-editor-wrapper {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px 16px;
}

.wf-open-image-workspace {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  border: 0;
  border-radius: 8px;
  background: #2563eb;
  color: #fff;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
}

.wf-inject-notice {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  background: #EFF6FF;
  border: 1px solid #BFDBFE;
  border-radius: 8px;
  font-size: 15px;
  color: #1E40AF;
  flex-shrink: 0;
}

.wf-inject-success {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  background: #F0FDF4;
  border: 1px solid #BBF7D0;
  border-radius: 8px;
  font-size: 14px;
  color: #166534;
}

.wf-inject-notice i {
  flex-shrink: 0;
}

</style>