<template>
  <div class="mint-wf-card wf-node-card wf-node-image-gen" id="card-image_gen" :class="`wf-state-${nodeStatus}`">
    <div class="mint-wf-header">
      <div class="mint-wf-title-row">
        <div class="mint-wf-step">05</div>
        <div class="wf-node-title-block">
          <div class="mint-wf-title">
            <i data-lucide="image" class="wf-node-icon"></i>
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
        <i data-lucide="info" style="width:14px;height:14px;"></i>
        等待图片规划完成后，在卡片编辑器中调整并生成图片
      </div>

      <!-- idle/pending/awaiting_review 状态 + cardDraft 可用：显示卡片编辑器（工作流在 image_gen 前 interrupt 暂停） -->
      <div v-else-if="(nodeStatus === 'idle' || nodeStatus === 'pending' || nodeStatus === 'awaiting_review') && cardDraft" class="wf-card-editor-wrapper">
        <CardEditorPanel
          :card-draft="cardDraft"
          :injecting="injecting"
          @generate="handleGenerate"
        />
      </div>

      <!-- running 状态 -->
      <div v-else-if="nodeStatus === 'running'" class="wf-copywrite-loading">
        <div class="mint-loader"><div class="mint-loader-ball"></div></div>
        <div class="wf-copywrite-loading-text">{{ injecting ? '正在注入图片到工作流...' : '等待前端注入图片...' }}</div>
      </div>

      <!-- error 状态 -->
      <div v-else-if="nodeStatus === 'error'" class="mint-search-error">
        <i data-lucide="alert-circle" style="width:20px;height:20px;"></i>
        <span>{{ errorMessage || injectError || '图片生成失败' }}</span>
      </div>

      <!-- completed 状态 -->
      <div v-else-if="nodeStatus === 'completed'" class="wf-inject-success">
        <i data-lucide="check-circle" style="width:18px;height:18px;color:#059669;flex-shrink:0;"></i>
        <span>图片注入成功，已进入下一环节</span>
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
import { ref, computed, watch, nextTick } from 'vue'
import { createIcons, icons } from 'lucide'
import CardEditorPanel from '@/components/CardEditorPanel.vue'
import { workflowApi } from '@/api/workflow'

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

watch(() => props.nodeStatus, () => {
  nextTick(() => createIcons({ icons }))
})
watch(() => props.result, () => nextTick(() => createIcons({ icons })), { deep: true })
watch(() => props.cardDraft, () => nextTick(() => createIcons({ icons })), { deep: true })

const injecting = ref(false)
const injectError = ref('')

const statusColor = computed(() => {
  const map: Record<string, string> = { idle: '#9CA3AF', pending: '#9CA3AF', awaiting_review: '#F59E0B', running: '#FF2442', completed: '#60A5FA', error: '#EF4444' }
  return map[props.nodeStatus] || '#9CA3AF'
})

const statusLabel = computed(() => {
  if (injecting.value) return '注入中'
  const map: Record<string, string> = { idle: '待编辑', pending: '待编辑', awaiting_review: '请编辑卡片', running: '执行中', completed: '已完成', error: '失败' }
  return map[props.nodeStatus] || '待执行'
})

const statusBadgeStyle = computed(() => {
  if (injecting.value) return { background: '#FEF3C7', color: '#92400E' }
  if (props.nodeStatus === 'error') return { background: '#FEE2E2', color: '#DC2626' }
  if (props.nodeStatus === 'completed') return { background: '#DBEAFE', color: '#2563EB' }
  if (props.nodeStatus === 'running') return { background: '#FEE2E2', color: '#DC2626' }
  if (props.nodeStatus === 'awaiting_review') return { background: '#FFFBEB', color: '#D97706' }
  return { background: '#F1F5F9', color: '#64748B' }
})

/** 从 axios 错误中提取可读信息 */
function extractAxiosError(e: any): string {
  // axios 错误：e.response.data.detail 或 e.response.data.message
  if (e?.response?.data) {
    const d = e.response.data
    return d.detail || d.message || JSON.stringify(d)
  }
  // 超时
  if (e?.code === 'ECONNABORTED' || e?.message?.includes('timeout')) {
    return '请求超时（图片数据可能过大，请减少卡片页数后重试）'
  }
  return e?.message || String(e)
}

async function handleGenerate(images: string[], planContext: Record<string, any>) {
  if (!props.workflowId) {
    injectError.value = '缺少工作流 ID，无法注入图片'
    console.error('[ImageGenCard] handleGenerate: workflowId is empty')
    return
  }

  injecting.value = true
  injectError.value = ''

  try {
    const resp: any = await workflowApi.injectCardImages(
      props.workflowId,
      images,
      [],           // imageDetails
      '卡片编辑器',  // style
      planContext,
    )

    // axios 拦截器返回 response.data（HTTP body），即 StandardResponse
    // { success: true, data: { success: true, message: "...", image_count: N }, message: "..." }
    const ok = resp?.success || resp?.data?.success
    if (ok) {
      // SSE 事件会推送 image_gen completed，nodeStatus 会自动更新
    } else {
      const msg = resp?.data?.message || resp?.message || '注入失败（未知原因）'
      injectError.value = msg
      console.error('[ImageGenCard] injectCardImages failed:', msg, resp)
      alert('图片注入失败：' + msg)
    }
  } catch (e: any) {
    const errMsg = extractAxiosError(e)
    injectError.value = errMsg
    console.error('[ImageGenCard] injectCardImages error:', e)
    alert('图片注入失败：' + errMsg)
  } finally {
    injecting.value = false
  }
}
</script>

<style scoped>
.wf-card-editor-wrapper {
  display: flex;
  flex-direction: column;
  gap: 10px;
  flex: 1;
  min-height: 0;
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

/* 让 CardEditorPanel 填满剩余空间 */
.wf-card-editor-wrapper :deep(.cep) {
  flex: 1;
  min-height: 0;
}
</style>
