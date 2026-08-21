<template>
  <div class="mint-wf-card wf-node-card wf-node-image-review" id="card-image_review" :class="`wf-state-${nodeStatus}`">
    <div class="mint-wf-header">
      <div class="mint-wf-title-row">
        <div class="mint-wf-step">06</div>
        <div class="wf-node-title-block">
          <div class="mint-wf-title">
            <i data-lucide="eye" class="wf-node-icon"></i>
            图片确认
            <code class="wf-node-key">image_review</code>
          </div>
          <div class="wf-node-subtitle">确认图片样式与质量</div>
        </div>
      </div>
      <span class="mint-badge wf-status-badge" :style="statusBadgeStyle">
        <span class="mint-status-dot" :style="{ background: statusColor }"></span>
        {{ statusLabel }}
      </span>
    </div>
    <div class="wf-node-summary" v-if="nodeStatus === 'completed' && result">
      {{ reviewStatusLabel }}
    </div>
    <div class="wf-node-body">
      <div v-if="nodeStatus === 'idle' || nodeStatus === 'pending'" class="wf-empty-hint">
        <i data-lucide="info" style="width:14px;height:14px;"></i>
        等待图片生成后进行确认
      </div>
      <div v-else-if="nodeStatus === 'awaiting_review'" class="wf-review-container">
        <!-- 顶部提示 -->
        <div class="wf-review-header">
          <div class="wf-review-header-icon"><i data-lucide="clock" style="width:20px;height:20px;"></i></div>
          <div class="wf-review-header-text">
            <div class="wf-review-header-title">请确认图片样式与质量</div>
            <div class="wf-review-header-desc">查看下方图片，满意则通过，不满意可调优重做</div>
          </div>
        </div>

        <!-- 图片展示区 -->
        <div class="wf-review-images-area">
          <div v-if="imagesLoading" class="wf-copywrite-loading">
            <div class="mint-loader"><div class="mint-loader-ball"></div></div>
            <div class="wf-copywrite-loading-text">加载图片中...</div>
          </div>
          <div v-else-if="imagesError" class="mint-search-error">
            <i data-lucide="alert-circle" style="width:20px;height:20px;"></i>
            <span>{{ imagesError }}</span>
          </div>
          <div v-else-if="reviewImages.length" class="wf-image-grid">
            <div v-for="(img, i) in reviewImages" :key="i" class="wf-image-thumb">
              <img :src="imageDataUrl(img)" :alt="'图片 ' + (Number(i) + 1)" loading="lazy" />
              <div class="wf-image-overlay"><span class="wf-image-role">第 {{ Number(i) + 1 }} 页</span></div>
            </div>
          </div>
          <div v-else class="wf-empty-hint">
            <i data-lucide="image-off" style="width:14px;height:14px;"></i>
            未找到图片数据
          </div>
        </div>

        <!-- 审核按钮 -->
        <div v-if="!imagesLoading && reviewImages.length" class="wf-review-actions">
          <button class="wf-review-btn wf-review-pass" @click="submitReviewAction('pass')" :disabled="submitting">
            <i data-lucide="check" style="width:16px;height:16px;"></i>
            {{ submitting ? '提交中...' : '确认通过' }}
          </button>
          <button class="wf-review-btn wf-review-reject" @click="submitReviewAction('reject')" :disabled="submitting">
            <i data-lucide="rotate-ccw" style="width:16px;height:16px;"></i>
            {{ submitting ? '提交中...' : '调优重做' }}
          </button>
        </div>
      </div>

      <div v-else-if="nodeStatus === 'running'" class="wf-copywrite-loading">
        <div class="mint-loader"><div class="mint-loader-ball"></div></div>
        <div class="wf-copywrite-loading-text">图片确认处理中...</div>
      </div>
      <div v-else-if="nodeStatus === 'error'" class="mint-search-error">
        <i data-lucide="alert-circle" style="width:20px;height:20px;"></i>
        <span>{{ errorMessage || '图片确认失败' }}</span>
      </div>
      <template v-else-if="result">
        <div class="wf-plan-summary" :style="{ background: reviewBgColor }">
          <i :data-lucide="reviewIcon" style="width:16px;height:16px;" :style="{ color: reviewIconColor }"></i>
          <span :style="{ color: reviewTextColor, fontWeight: 600, fontSize: '14px' }">{{ reviewStatusLabel }}</span>
          <span v-if="result.image_count" class="wf-plan-count" style="margin-left:auto;">共 {{ result.image_count }} 张</span>
        </div>
        <div v-if="result.feedback" class="wf-copywrite-feedback">
          <i data-lucide="message-square-warning" style="width:12px;height:12px;"></i>
          <span>{{ result.feedback }}</span>
        </div>
        <div v-if="result.images_base64 && result.images_base64.length" class="wf-review-images-area">
          <div class="wf-image-grid">
            <div v-for="(img, i) in result.images_base64" :key="i" class="wf-image-thumb">
              <img :src="imageDataUrl(img)" :alt="'图片 ' + (Number(i) + 1)" loading="lazy" />
              <div class="wf-image-overlay"><span class="wf-image-role">第 {{ Number(i) + 1 }} 页</span></div>
            </div>
          </div>
        </div>
        <div v-if="result.card_draft_summary" class="wf-plan-summary" style="background:#F8FAFC;font-size: 15px;color:#64748B;">
          <span>模板：{{ templateLabel(result.card_draft_summary.final_template || result.card_draft_summary.original_template) }}</span>
          <span v-if="result.card_draft_summary.template_changed" style="color:#D97706;margin-left:8px;">（已修改）</span>
        </div>
      </template>
      <div v-else class="wf-empty-hint">
        <i data-lucide="check-circle" style="width:14px; height:14px; color:#60A5FA;"></i>
        图片确认已完成（详细数据不可用）
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
import { workflowApi } from '@/api/workflow'
import { useWorkflowStore } from '@/stores/workflow'

const props = defineProps<{
  nodeStatus: string
  nodeMeta: { duration: string; model: string; tokens: string } | null
  result: any
  errorMessage?: string
  /** 当前工作流 ID */
  workflowId?: string
}>()

watch(() => props.nodeStatus, () => nextTick(() => createIcons({ icons })))
watch(() => props.result, () => nextTick(() => createIcons({ icons })), { deep: true })

const workflowStore = useWorkflowStore()

// ===== awaiting_review 阶段的图片加载 =====
const reviewImages = ref<string[]>([])
const imagesLoading = ref(false)
const imagesError = ref('')
const submitting = ref(false)

// 当节点进入 awaiting_review 状态时，从后端拉取 image_gen 的图片
watch(() => props.nodeStatus, async (status) => {
  if (status === 'awaiting_review' && props.workflowId) {
    await fetchReviewImages()
  }
}, { immediate: true })

async function fetchReviewImages() {
  if (!props.workflowId) {
    imagesError.value = '缺少工作流 ID'
    return
  }

  imagesLoading.value = true
  imagesError.value = ''
  reviewImages.value = []

  try {
    // 先尝试从 SSE store 中获取 image_gen 的 images_base64
    // node_completed 事件会包含 images_base64（如果 SSE 正常工作）
    const imageGenNode = workflowStore.nodes.find(n => n.node_id === 'image_gen') as any
    const sseImages = imageGenNode?.images_base64 || imageGenNode?.output?.images_base64

    if (sseImages && Array.isArray(sseImages) && sseImages.length > 0) {
      reviewImages.value = sseImages
    } else {
      const resp: any = await workflowApi.getNodeImages(props.workflowId, 'image_gen')
      const images = resp?.images_base64 || resp?.data?.images_base64 || []
      if (images.length > 0) {
        reviewImages.value = images
      } else {
        imagesError.value = 'image_gen 节点没有图片数据'
      }
    }
  } catch (e: any) {
    const errMsg = e?.response?.data?.detail || e?.message || String(e)
    imagesError.value = '加载图片失败：' + errMsg
    console.error('[ImageReviewCard] fetchReviewImages error:', e)
  } finally {
    imagesLoading.value = false
    nextTick(() => createIcons({ icons }))
  }
}

async function submitReviewAction(action: 'pass' | 'reject') {
  if (!props.workflowId) {
    alert('缺少工作流 ID')
    return
  }

  submitting.value = true
  try {
    await workflowStore.submitReview('image_review', action)
  } catch (e: any) {
    const errMsg = e?.response?.data?.message || e?.message || String(e)
    alert('提交失败：' + errMsg)
  } finally {
    submitting.value = false
  }
}

const statusColor = computed(() => {
  const map: Record<string, string> = { idle: '#9CA3AF', pending: '#9CA3AF', running: '#FF2442', awaiting_review: '#F59E0B', passed: '#10B981', rejected: '#EF4444', completed: '#60A5FA', error: '#EF4444' }
  return map[props.nodeStatus] || '#9CA3AF'
})
const statusLabel = computed(() => {
  const map: Record<string, string> = { idle: '待执行', pending: '待执行', running: '执行中', awaiting_review: '请确认图片', passed: '已通过', rejected: '已调优', completed: '已完成', error: '失败' }
  return map[props.nodeStatus] || '待执行'
})
const statusBadgeStyle = computed(() => {
  if (props.nodeStatus === 'error' || props.nodeStatus === 'rejected') return { background: '#FEE2E2', color: '#DC2626' }
  if (props.nodeStatus === 'passed') return { background: '#D1FAE5', color: '#059669' }
  if (props.nodeStatus === 'awaiting_review') return { background: '#FFFBEB', color: '#D97706' }
  if (props.nodeStatus === 'completed') return { background: '#DBEAFE', color: '#2563EB' }
  if (props.nodeStatus === 'running') return { background: '#FEE2E2', color: '#DC2626' }
  return { background: '#F1F5F9', color: '#64748B' }
})
function imageDataUrl(b64: string): string {
  if (b64.startsWith('data:')) return b64
  const prefix = b64.startsWith('/9j/') ? 'data:image/jpeg;base64,' : 'data:image/png;base64,'
  return prefix + b64
}
const reviewStatus = computed(() => props.result?.review_status || props.nodeStatus)
const reviewStatusLabel = computed(() => {
  if (reviewStatus.value === 'passed') return '确认通过'
  if (reviewStatus.value === 'rejected') return '调优重做'
  return '确认中'
})
const reviewBgColor = computed(() => {
  if (reviewStatus.value === 'passed') return '#F0FDF4'
  if (reviewStatus.value === 'rejected') return '#FEF2F2'
  return '#FFFBEB'
})
const reviewIconColor = computed(() => {
  if (reviewStatus.value === 'passed') return '#059669'
  if (reviewStatus.value === 'rejected') return '#DC2626'
  return '#D97706'
})
const reviewIcon = computed(() => {
  if (reviewStatus.value === 'passed') return 'check-circle'
  if (reviewStatus.value === 'rejected') return 'x-circle'
  return 'clock'
})
const reviewTextColor = computed(() => {
  if (reviewStatus.value === 'passed') return '#059669'
  if (reviewStatus.value === 'rejected') return '#DC2626'
  return '#D97706'
})
function templateLabel(template: string): string {
  const map: Record<string, string> = { minimal_white: '极简白', warm_card: '暖色卡片', dark_tech: '暗色科技' }
  return map[template] || template || '默认'
}
</script>

<style scoped>
.wf-review-container {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.wf-review-header {
  display: flex;
  align-items: center;
  gap: 12px;
}

.wf-review-header-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: #FFFBEB;
  color: #D97706;
  flex-shrink: 0;
}

.wf-review-header-text {
  flex: 1;
}

.wf-review-header-title {
  font-size: 15px;
  font-weight: 600;
  color: #1F2937;
}

.wf-review-header-desc {
  font-size: 13px;
  color: #9CA3AF;
  margin-top: 2px;
}

.wf-review-images-area {
  background: #F3F4F6;
  border-radius: 12px;
  padding: 12px;
}

.wf-review-actions {
  display: flex;
  justify-content: center;
  gap: 12px;
  padding-top: 4px;
}

.wf-review-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 10px 24px;
  border: none;
  border-radius: 20px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: opacity 0.15s, background 0.15s;
}

.wf-review-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.wf-review-pass {
  background: #FF2442;
  color: #fff;
}

.wf-review-pass:hover:not(:disabled) {
  background: #E01F3B;
}

.wf-review-reject {
  background: #F3F4F6;
  color: #6B7280;
}

.wf-review-reject:hover:not(:disabled) {
  background: #E5E7EB;
  color: #6B7280;
}
</style>
