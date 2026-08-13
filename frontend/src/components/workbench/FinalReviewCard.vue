<template>
  <div class="mint-wf-card wf-node-card wf-node-final-review" id="card-final_review" :class="`wf-state-${nodeStatus}`">
    <div class="mint-wf-header">
      <div class="mint-wf-title-row">
        <div class="mint-wf-step">08</div>
        <div class="wf-node-title-block">
          <div class="mint-wf-title">
            <i data-lucide="smartphone" class="wf-node-icon"></i>
            发布预览
            <code class="wf-node-key">final_review</code>
          </div>
        </div>
      </div>
      <span class="mint-badge wf-status-badge" :style="statusBadgeStyle">
        <span class="mint-status-dot" :style="{ background: statusColor }"></span>
        {{ statusLabel }}
      </span>
    </div>
    <div class="wf-node-body">
      <!-- idle/pending -->
      <div v-if="nodeStatus === 'idle' || nodeStatus === 'pending'" class="wf-empty-hint">
        <i data-lucide="info" style="width:14px;height:14px;"></i>
        等待合规审核完成后进行终审
      </div>

      <!-- awaiting_review：手机预览 + 审核按钮 -->
      <div v-else-if="nodeStatus === 'awaiting_review'" class="wf-phone-review">
        <div class="wf-phone-layout">
          <div class="wf-iphone">
            <div class="wf-iphone-screen">
              <!-- 状态栏 -->
              <div class="wf-iphone-statusbar">
                <span class="wf-iphone-time">9:41</span>
                <div class="wf-iphone-notch"></div>
                <div class="wf-iphone-status-icons">
                  <svg width="13" height="10" viewBox="0 0 16 12"><rect x="0" y="5" width="3" height="7" rx="1" fill="#1a1a1a"/><rect x="4.5" y="3" width="3" height="9" rx="1" fill="#1a1a1a"/><rect x="9" y="1" width="3" height="11" rx="1" fill="#1a1a1a"/><rect x="13" y="0" width="3" height="12" rx="1" fill="#1a1a1a" opacity="0.3"/></svg>
                  <svg width="13" height="10" viewBox="0 0 16 12"><path d="M8 2C5.5 2 3.2 3 1.5 4.7L0 3.2C2.1 1.1 4.9 0 8 0s5.9 1.1 8 3.2L14.5 4.7C12.8 3 10.5 2 8 2z" fill="#1a1a1a"/><path d="M8 5.5c-1.7 0-3.2.7-4.3 1.8L2.2 5.8C3.7 4.3 5.7 3.5 8 3.5s4.3.8 5.8 2.3L12.3 7.3C11.2 6.2 9.7 5.5 8 5.5z" fill="#1a1a1a"/><path d="M8 9c-.8 0-1.6.3-2.1.9L8 12l2.1-2.1C9.6 9.3 8.8 9 8 9z" fill="#1a1a1a"/></svg>
                  <svg width="22" height="10" viewBox="0 0 27 13"><rect x="0" y="1" width="23" height="11" rx="3.5" stroke="#1a1a1a" stroke-width="1" fill="none"/><rect x="24" y="4" width="2" height="5" rx="1" fill="#1a1a1a" opacity="0.4"/><rect x="2" y="3" width="17" height="7" rx="1.5" fill="#1a1a1a"/></svg>
                </div>
              </div>

              <!-- 可滚动内容区 -->
              <div class="wf-xhs-content-scroll">
                <!-- 小红书导航栏：返回 | 头像+昵称 | 关注 -->
                <div class="wf-xhs-navbar">
                  <svg class="wf-xhs-nav-back" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#333" stroke-width="2"><path d="M15 18l-6-6 6-6"/></svg>
                  <div class="wf-xhs-nav-user">
                  <div class="wf-xhs-nav-avatar">
                    <img v-if="accountAvatar" :src="accountAvatar" class="wf-xhs-nav-avatar-img" />
                    <span v-else>{{ accountNickname.charAt(0) }}</span>
                  </div>
                  <span class="wf-xhs-nav-name">{{ accountNickname }}</span>
                </div>
                  <div class="wf-xhs-follow-btn">关注</div>
                </div>

                <!-- 图片区 -->
                <div class="wf-xhs-images" v-if="reviewImages.length">
                  <img :src="'data:image/png;base64,' + reviewImages[currentImageIndex]" class="wf-xhs-image" />
                  <div v-if="reviewImages.length > 1" class="wf-xhs-dots">
                    <span v-for="(_, i) in reviewImages" :key="i" class="wf-xhs-dot" :class="{ active: i === currentImageIndex }" @click="currentImageIndex = i"></span>
                  </div>
                  <div v-if="reviewImages.length > 1" class="wf-xhs-counter">{{ currentImageIndex + 1 }}/{{ reviewImages.length }}</div>
                </div>
                <div v-else class="wf-xhs-images wf-xhs-images-empty">
                  <span>暂无图片</span>
                </div>

                <!-- 文案区 -->
                <div class="wf-xhs-body">
                  <div v-if="reviewTitle" class="wf-xhs-title">{{ reviewTitle }}</div>
                  <div v-if="reviewContent" class="wf-xhs-content">
                    <span>{{ reviewContent }}</span>
                    <span class="wf-xhs-expand">展开</span>
                  </div>
                  <div v-if="reviewTags.length" class="wf-xhs-tags">
                    <span v-for="(t, i) in reviewTags" :key="i" class="wf-xhs-tag">#{{ t }}</span>
                  </div>
                  <div class="wf-xhs-date">编辑于刚刚</div>
                </div>
              </div>

              <!-- 底部互动栏：输入框 | ❤️⭐💬 -->
              <div class="wf-xhs-footer">
                <div class="wf-xhs-input">说点什么...</div>
                <div class="wf-xhs-actions-right">
                  <div class="wf-xhs-action">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#333" stroke-width="1.8"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/></svg>
                    <span>点赞</span>
                  </div>
                  <div class="wf-xhs-action">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#333" stroke-width="1.8"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/></svg>
                    <span>收藏</span>
                  </div>
                  <div class="wf-xhs-action">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#333" stroke-width="1.8"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
                    <span>评论</span>
                  </div>
                </div>
              </div>

              <!-- Home Indicator -->
              <div class="wf-iphone-home-bar"></div>
            </div>
          </div>
        </div>

        <!-- 审核按钮 -->
        <div class="wf-review-actions">
          <button class="wf-review-btn wf-review-pass" @click="submitReviewAction('pass')" :disabled="submitting">
            <i data-lucide="check" style="width:16px;height:16px;"></i>
            {{ submitting ? '提交中...' : '通过，进入发布' }}
          </button>
          <button class="wf-review-btn wf-review-reject" @click="submitReviewAction('reject')" :disabled="submitting">
            <i data-lucide="rotate-ccw" style="width:16px;height:16px;"></i>
            {{ submitting ? '提交中...' : '打回重写' }}
          </button>
        </div>
      </div>

      <!-- running -->
      <div v-else-if="nodeStatus === 'running'" class="wf-copywrite-loading">
        <div class="mint-loader"><div class="mint-loader-ball"></div></div>
        <div class="wf-copywrite-loading-text">终审处理中...</div>
      </div>

      <!-- error -->
      <div v-else-if="nodeStatus === 'error'" class="mint-search-error">
        <i data-lucide="alert-circle" style="width:20px;height:20px;"></i>
        <span>{{ errorMessage || '终审失败' }}</span>
      </div>

      <!-- completed / passed / rejected -->
      <div v-else-if="result" class="wf-phone-review-result">
        <div class="wf-plan-summary" :style="{ background: reviewBgColor }">
          <i :data-lucide="reviewIcon" style="width:16px;height:16px;" :style="{ color: reviewIconColor }"></i>
          <span :style="{ color: reviewTextColor, fontWeight: 600, fontSize: '14px' }">{{ reviewStatusLabel }}</span>
        </div>
        <div v-if="result.feedback" class="wf-copywrite-feedback">
          <i data-lucide="message-square-warning" style="width:12px;height:12px;"></i>
          <span>{{ result.feedback }}</span>
        </div>
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
import { useAccountStore } from '@/stores/account'

const props = defineProps<{
  nodeStatus: string
  nodeMeta: { duration: string; model: string; tokens: string } | null
  result: any
  errorMessage?: string
  workflowId?: string
}>()

watch(() => props.nodeStatus, () => nextTick(() => createIcons({ icons })))
watch(() => props.result, () => nextTick(() => createIcons({ icons })), { deep: true })

const workflowStore = useWorkflowStore()
const accountStore = useAccountStore()
const submitting = ref(false)
const currentImageIndex = ref(0)

const accountNickname = computed(() => accountStore.currentAccount?.xhs_nickname || '创作者')
const accountAvatar = computed(() => accountStore.currentAccount?.xhs_avatar_url || '')
const reviewImages = ref<string[]>([])

const reviewTitle = computed(() => props.result?.title || '')
const reviewContent = computed(() => props.result?.content || '')
const reviewTags = computed(() => props.result?.tags || [])

watch(() => props.nodeStatus, async (status) => {
  if (status === 'awaiting_review' && props.workflowId) {
    currentImageIndex.value = 0
    await fetchReviewImages()
  }
}, { immediate: true })

async function fetchReviewImages() {
  if (!props.workflowId) return
  try {
    const imageGenNode = workflowStore.nodes.find(n => n.node_id === 'image_gen') as any
    const sseImages = imageGenNode?.images_base64 || imageGenNode?.output?.images_base64
    if (sseImages && Array.isArray(sseImages) && sseImages.length > 0) {
      reviewImages.value = sseImages
    } else {
      const resp: any = await workflowApi.getNodeImages(props.workflowId, 'image_gen')
      const images = resp?.images_base64 || resp?.data?.images_base64 || []
      reviewImages.value = images
    }
  } catch (e: any) {
    console.error('[FinalReviewCard] fetchReviewImages error:', e)
  } finally {
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
    await workflowStore.submitReview('final_review', action)
  } catch (e: any) {
    const errMsg = e?.response?.data?.message || e?.message || String(e)
    alert('终审提交失败：' + errMsg)
  } finally {
    submitting.value = false
  }
}

const statusColor = computed(() => {
  const map: Record<string, string> = { idle: '#9CA3AF', pending: '#9CA3AF', running: '#FF2442', awaiting_review: '#F59E0B', passed: '#10B981', rejected: '#EF4444', completed: '#60A5FA', error: '#EF4444' }
  return map[props.nodeStatus] || '#9CA3AF'
})
const statusLabel = computed(() => {
  const map: Record<string, string> = { idle: '待执行', pending: '待执行', running: '执行中', awaiting_review: '待审核', passed: '已通过', rejected: '已打回', completed: '已完成', error: '失败' }
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
const reviewStatus = computed(() => props.result?.review_status || props.nodeStatus)
const reviewStatusLabel = computed(() => {
  if (reviewStatus.value === 'passed') return '终审通过'
  if (reviewStatus.value === 'rejected') return '终审打回'
  return '审核中'
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
</script>

<style scoped>
.wf-phone-review {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
}

.wf-phone-layout {
  display: flex;
  justify-content: center;
  width: 100%;
  padding: 12px 0 0;
}

/* ===== iPhone 外壳 ===== */
.wf-iphone {
  width: 325px;
  background: #1a1a1a;
  border-radius: 44px;
  padding: 3px;
  position: relative;
  border: 2.5px solid #1a1a1a;
  box-shadow:
    0 2px 8px rgba(0,0,0,0.06),
    0 12px 40px rgba(0,0,0,0.12);
  flex-shrink: 0;
}

.wf-iphone-screen {
  border-radius: 41px;
  overflow: hidden;
  background: #FFFFFF;
  position: relative;
  height: 656px;
  display: flex;
  flex-direction: column;
}

.wf-iphone-screen .wf-xhs-content-scroll {
  flex: 1;
  overflow-y: auto;
  scrollbar-width: none;
}

.wf-iphone-screen .wf-xhs-content-scroll::-webkit-scrollbar {
  display: none;
}

/* 状态栏 */
.wf-iphone-statusbar {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  padding: 0 20px 0;
  background: #FFFFFF;
  height: 44px;
  position: relative;
}
.wf-iphone-time {
  font-size: 14px;
  font-weight: 600;
  color: #1a1a1a;
  width: 44px;
  padding-top: 14px;
  z-index: 1;
}
.wf-iphone-notch {
  width: 120px;
  height: 26px;
  background: #1a1a1a;
  border-radius: 0 0 16px 16px;
  position: absolute;
  left: 50%;
  transform: translateX(-50%);
  top: 0;
}
.wf-iphone-status-icons {
  display: flex;
  align-items: center;
  gap: 4px;
  width: 72px;
  justify-content: flex-end;
  padding-top: 14px;
  z-index: 1;
}

/* 小红书导航栏 */
.wf-xhs-navbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 12px;
  margin-top: 0;
  background: #FFFFFF;
  border-bottom: 0.5px solid #EFEFEF;
}
.wf-xhs-nav-back {
  flex-shrink: 0;
}
.wf-xhs-nav-user {
  display: flex;
  align-items: center;
  gap: 6px;
  flex: 1;
}
.wf-xhs-nav-avatar {
  width: 26px;
  height: 26px;
  border-radius: 50%;
  background: linear-gradient(135deg, #FF2442, #FF6B81);
  flex-shrink: 0;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  color: #fff;
  font-weight: 500;
}
.wf-xhs-nav-avatar-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.wf-xhs-nav-name {
  font-size: 14px;
  font-weight: 500;
  color: #333;
}
.wf-xhs-follow-btn {
  padding: 3px 12px;
  background: #FF2442;
  color: #fff;
  border-radius: 12px;
  font-size: 11px;
  font-weight: 500;
  flex-shrink: 0;
}

/* 图片区 */
.wf-xhs-images {
  position: relative;
  width: 100%;
  background: #F5F5F5;
  overflow: hidden;
  margin-top: 6px;
}
.wf-xhs-images-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 200px;
  color: #999;
  font-size: 13px;
}
.wf-xhs-image {
  width: 100%;
  height: auto;
  display: block;
}
.wf-xhs-dots {
  position: absolute;
  bottom: 10px;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  gap: 5px;
}
.wf-xhs-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: rgba(255,255,255,0.45);
  cursor: pointer;
  transition: all 0.2s;
}
.wf-xhs-dot.active {
  background: #fff;
  box-shadow: 0 0 4px rgba(0,0,0,0.15);
}
.wf-xhs-counter {
  position: absolute;
  top: 10px;
  right: 10px;
  background: rgba(0,0,0,0.4);
  color: #fff;
  font-size: 10px;
  padding: 2px 7px;
  border-radius: 10px;
  backdrop-filter: blur(4px);
}

/* 文案区 */
.wf-xhs-body {
  padding: 10px 12px 4px;
  background: #FFFFFF;
}
.wf-xhs-title {
  font-size: 13px;
  font-weight: 600;
  color: #1a1a1a;
  line-height: 1.4;
  margin-bottom: 2px;
}
.wf-xhs-content {
  font-size: 11px;
  color: #333;
  line-height: 1.6;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.wf-xhs-expand {
  color: #999;
  font-size: 11px;
  margin-left: 2px;
}
.wf-xhs-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 2px;
  margin-top: 4px;
}
.wf-xhs-tag {
  font-size: 10px;
  color: #3378EA;
  line-height: 1.5;
}
.wf-xhs-date {
  font-size: 10px;
  color: #B8B8B8;
  margin-top: 4px;
}

/* 底部互动栏 */
.wf-xhs-footer {
  display: flex;
  align-items: center;
  padding: 8px 12px;
  background: #FFFFFF;
  border-top: 0.5px solid #F0F0F0;
  gap: 8px;
}
.wf-xhs-input {
  flex: 1;
  background: #F5F5F5;
  border-radius: 14px;
  padding: 4px 10px;
  font-size: 11px;
  color: #999;
  min-height: 24px;
  display: flex;
  align-items: center;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.wf-xhs-actions-right {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-shrink: 0;
}
.wf-xhs-action {
  display: flex;
  align-items: center;
  gap: 3px;
  font-size: 12px;
  color: #333;
  cursor: pointer;
}

/* Home Indicator */
.wf-iphone-home-bar {
  width: 120px;
  height: 4px;
  background: #1a1a1a;
  border-radius: 2px;
  margin: 6px auto 6px;
  opacity: 0.18;
}

/* 审核按钮 */
.wf-review-actions {
  display: flex;
  gap: 10px;
  padding-top: 4px;
}
.wf-review-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 18px;
  border: none;
  border-radius: 8px;
  font-size: 15px;
  font-weight: 500;
  cursor: pointer;
  transition: opacity 0.15s;
}
.wf-review-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.wf-review-pass {
  background: #10B981;
  color: #fff;
}
.wf-review-pass:hover:not(:disabled) {
  background: #059669;
}
.wf-review-reject {
  background: #F3F4F6;
  color: #DC2626;
}
.wf-review-reject:hover:not(:disabled) {
  background: #FEE2E2;
}

/* 审核结果 */
.wf-phone-review-result {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
</style>