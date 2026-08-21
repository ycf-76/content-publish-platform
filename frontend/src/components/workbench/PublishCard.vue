<template>
  <div class="mint-wf-card wf-node-card wf-node-publish" id="card-publish" :class="`wf-state-${nodeStatus}`">
    <div class="mint-wf-header">
      <div class="mint-wf-title-row">
        <div class="mint-wf-step">09</div>
        <div class="wf-node-title-block">
          <div class="mint-wf-title">
            <i data-lucide="send" class="wf-node-icon"></i>
            发布
            <code class="wf-node-key">publish</code>
          </div>

        </div>
      </div>
      <span class="mint-badge wf-status-badge" :style="statusBadgeStyle">
        <span class="mint-status-dot" :style="{ background: statusColor }"></span>
        {{ statusLabel }}
      </span>
    </div>
    <div class="wf-node-body">
      <div v-if="nodeStatus === 'idle' || nodeStatus === 'pending'" class="wf-empty-hint">
        <i data-lucide="info" style="width:14px;height:14px;"></i>
        等待终审通过后自动发布
      </div>
      <!-- awaiting_review：auto_publish=False 时，终审通过后等待用户手动确认发布 -->
      <div v-else-if="nodeStatus === 'awaiting_review'" class="wf-publish-manual">
        <div class="wf-publish-manual-hint">
          <i data-lucide="check-circle" style="width:16px;height:16px;color:#10B981;"></i>
          <span>终审已通过，确认发布到小红书？</span>
        </div>
        <div v-if="result?.title" class="wf-publish-manual-title">{{ result.title }}</div>
        <div class="wf-publish-actions">
          <button class="wf-publish-btn wf-publish-confirm" @click="confirmPublish" :disabled="publishing">
            <i data-lucide="send" style="width:14px;height:14px;"></i>
            {{ publishing ? "发布中..." : "确认发布" }}
          </button>
        </div>
      </div>
      <div v-else-if="nodeStatus === 'running'" class="wf-copywrite-loading">
        <div class="mint-loader"><div class="mint-loader-ball"></div></div>
        <div class="wf-copywrite-loading-text">
          {{ result && result.status === 'awaiting_manual' ? '内容已填好，请在浏览器窗口手动点击发布按钮' : '正在发布中...' }}
        </div>
      </div>
      <div v-else-if="nodeStatus === 'error'" class="mint-search-error">
        <i data-lucide="alert-circle" style="width:20px;height:20px;"></i>
        <span>{{ errorMessage || '发布失败' }}</span>
      </div>
      <template v-else-if="nodeStatus === 'completed' && result">
        <div class="wf-plan-summary" :style="{ background: publishBgColor }">
          <i :data-lucide="publishIcon" style="width:16px;height:16px;" :style="{ color: publishIconColor }"></i>
          <span :style="{ color: publishTextColor, fontWeight: 600, fontSize: '14px' }">{{ publishStatusLabel }}</span>
        </div>
        <div v-if="result.post_id" class="wf-copywrite-section">
          <div class="wf-copywrite-label"><i data-lucide="link" style="width:12px;height:12px;"></i>帖子 ID</div>
          <div class="wf-copywrite-content" style="max-height:none;padding:6px 10px;font-family:monospace;font-size: 14px;">{{ result.post_id }}</div>
        </div>
        <div v-if="result.message" class="wf-copywrite-section">
          <div class="wf-copywrite-label"><i data-lucide="message-circle" style="width:12px;height:12px;"></i>发布信息</div>
          <div class="wf-copywrite-content" style="max-height:none;">{{ result.message }}</div>
        </div>
        <div v-if="result.status === 'awaiting_manual'" class="wf-card-editor-hint" style="background:#FFFBEB;border-color:#F59E0B;color:#92400E;">
          <i data-lucide="mouse-pointer-click" style="width:14px;height:14px;color:#D97706;"></i>
          <span>内容已填好，请在浏览器窗口手动点击「发布」按钮完成发布</span>
        </div>
      </template>
      <div v-else-if="nodeStatus === 'completed'" class="wf-empty-hint">
        <i data-lucide="check-circle" style="width:14px; height:14px; color:#60A5FA;"></i>
        发布已完成（详细数据不可用）
      </div>
    </div>
    <div class="wf-node-meta" v-if="nodeMeta">
      <span class="wf-meta-item"><i data-lucide="clock" style="width:12px;height:12px;"></i>{{ nodeMeta.duration }}</span>
      <span class="wf-meta-item"><i data-lucide="cpu" style="width:12px;height:12px;"></i>{{ nodeMeta.model }}</span>
      <span class="wf-meta-item"><i data-lucide="zap" style="width:12px;height:12px;"></i>{{ nodeMeta.tokens }} tokens</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, watch, nextTick } from 'vue'
import { createIcons, icons } from 'lucide'

const props = defineProps<{
  nodeStatus: string
  nodeMeta: { duration: string; model: string; tokens: string } | null
  result: any
  errorMessage?: string
  workflowId?: string
}>()

watch(() => props.nodeStatus, () => nextTick(() => createIcons({ icons })))
watch(() => props.result, () => nextTick(() => createIcons({ icons })), { deep: true })

import { ref } from 'vue'
import { useWorkflowStore } from '@/stores/workflow'
const publishing = ref(false)
async function confirmPublish() {
  if (publishing.value || !props.workflowId) return
  publishing.value = true
  try {
    const store = useWorkflowStore()
    await store.resumeWorkflow()
  } catch (e: any) {
    console.error('[PublishCard] confirmPublish failed:', e)
  } finally {
    publishing.value = false
  }
}

const statusColor = computed(() => {
  const map: Record<string, string> = { idle: '#9CA3AF', pending: '#9CA3AF', running: '#FF2442', awaiting_review: '#F59E0B', completed: '#60A5FA', error: '#EF4444' }
  return map[props.nodeStatus] || '#9CA3AF'
})
const statusLabel = computed(() => {
  const map: Record<string, string> = { idle: '待执行', pending: '待执行', running: '执行中', awaiting_review: '待发布', completed: '已完成', error: '失败' }
  return map[props.nodeStatus] || '待执行'
})
const statusBadgeStyle = computed(() => {
  if (props.nodeStatus === 'error') return { background: '#FEE2E2', color: '#DC2626' }
  if (props.nodeStatus === 'completed') return { background: '#DBEAFE', color: '#2563EB' }
  if (props.nodeStatus === 'running') return { background: '#FEE2E2', color: '#DC2626' }
  if (props.nodeStatus === 'awaiting_review') return { background: '#FFFBEB', color: '#D97706' }
  return { background: '#F1F5F9', color: '#64748B' }
})
const publishStatus = computed(() => props.result?.status || 'unknown')
const publishStatusLabel = computed(() => {
  if (publishStatus.value === 'success') return '发布成功'
  if (publishStatus.value === 'awaiting_manual') return '等待手动确认'
  if (publishStatus.value === 'failed') return '发布失败'
  return '发布中'
})
const publishBgColor = computed(() => {
  if (publishStatus.value === 'success') return '#F0FDF4'
  if (publishStatus.value === 'awaiting_manual') return '#FFFBEB'
  if (publishStatus.value === 'failed') return '#FEF2F2'
  return '#F8FAFC'
})
const publishIconColor = computed(() => {
  if (publishStatus.value === 'success') return '#059669'
  if (publishStatus.value === 'awaiting_manual') return '#D97706'
  if (publishStatus.value === 'failed') return '#DC2626'
  return '#9CA3AF'
})
const publishIcon = computed(() => {
  if (publishStatus.value === 'success') return 'check-circle'
  if (publishStatus.value === 'awaiting_manual') return 'clock'
  if (publishStatus.value === 'failed') return 'x-circle'
  return 'send'
})
const publishTextColor = computed(() => {
  if (publishStatus.value === 'success') return '#059669'
  if (publishStatus.value === 'awaiting_manual') return '#D97706'
  if (publishStatus.value === 'failed') return '#DC2626'
  return '#64748B'
})
</script>

<style scoped>
.wf-publish-manual {
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.wf-publish-manual-hint {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  color: #6B7280;
  font-weight: 500;
}
.wf-publish-manual-title {
  font-size: 14px;
  color: #6B7280;
  padding: 6px 10px;
  background: #F8FAFC;
  border-radius: 6px;
  border-left: 3px solid #FF2442;
}
.wf-publish-actions {
  display: flex;
  gap: 8px;
}
.wf-publish-btn {
  flex: 1;
  padding: 8px 16px;
  border: none;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  transition: opacity 0.2s;
}
.wf-publish-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.wf-publish-confirm {
  background: #FF2442;
  color: #FFFFFF;
}
.wf-publish-confirm:hover:not(:disabled) {
  background: #E01E3A;
}
</style>