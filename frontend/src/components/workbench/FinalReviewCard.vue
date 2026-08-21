<template>
  <div class="mint-wf-card wf-node-card wf-node-final-review" id="card-final_review" :class="[`wf-state-${combinedStatus}`, { 'wf-final-hero': finalReviewStatus === 'awaiting_review' }]">
    <div class="mint-wf-header">
      <div class="mint-wf-title-row">
        <div class="mint-wf-step">07</div>
        <div class="wf-node-title-block">
          <div class="mint-wf-title">
            <i data-lucide="smartphone" class="wf-node-icon"></i>
            发布预览
          </div>
          <div class="wf-node-subtitle">合规审核 · 终审 · 发布</div>
        </div>
      </div>
      <span class="mint-badge wf-status-badge" :style="statusBadgeStyle">
        <span class="mint-status-dot" :style="{ background: statusColor }"></span>
        {{ statusLabel }}
      </span>
    </div>
    <div class="wf-node-summary" v-if="combinedStatus === 'completed' || combinedStatus === 'passed' || combinedStatus === 'rejected'">
      {{ publishResult ? publishResultLabel : statusLabel }}
    </div>
    <div class="wf-node-body">

      <!-- ===== 全 idle ===== -->
      <div v-if="combinedStatus === 'idle'" class="wf-empty-hint">
        <i data-lucide="info" style="width:14px;height:14px;"></i>
        等待图片确认后进行合规审核与发布
      </div>

      <!-- ===== 合规审核区域 ===== -->
      <div class="wf-section wf-section-audit" v-if="auditStatus !== 'idle' && auditStatus !== 'pending'">
        <div class="wf-section-header">
          <i data-lucide="shield-check" style="width:14px;height:14px;"></i>
          <span class="wf-section-title">合规审核</span>
          <span class="wf-section-badge" :style="auditBadgeStyle">{{ auditStatusLabel }}</span>
        </div>

        <!-- running -->
        <div v-if="auditStatus === 'running'" class="wf-copywrite-loading" style="padding:8px 0;">
          <div class="mint-loader"><div class="mint-loader-ball"></div></div>
          <div class="wf-copywrite-loading-text">AI 正在审核文案合规性...</div>
        </div>

        <!-- error -->
        <div v-else-if="auditStatus === 'error'" class="mint-search-error">
          <i data-lucide="alert-circle" style="width:16px;height:16px;"></i>
          <span>{{ auditError || '合规审核失败' }}</span>
        </div>

        <!-- completed -->
        <template v-else-if="auditStatus === 'completed' && auditResult">
          <div class="wf-audit-summary" :style="{ background: auditResult.passed ? '#F0FDF4' : '#FEF2F2' }">
            <i :data-lucide="auditResult.passed ? 'check-circle' : 'x-circle'" style="width:14px;height:14px;" :style="{ color: auditResult.passed ? '#059669' : '#DC2626' }"></i>
            <span :style="{ color: auditResult.passed ? '#059669' : '#DC2626', fontWeight: 600, fontSize: '13px' }">{{ auditResult.passed ? '审核通过' : '发现问题' }}</span>
          </div>
          <div v-if="auditResult.issues && auditResult.issues.length" class="wf-compact-list">
            <div v-for="(issue, i) in auditResult.issues" :key="'issue-'+i" class="wf-compact-item wf-compact-warn">
              <i data-lucide="alert-triangle" style="width:11px;height:11px;flex-shrink:0;"></i>
              <span>{{ formatIssueItem(issue) }}</span>
              <span v-if="getIssueSeverity(issue)" class="wf-severity-tag" :class="'wf-severity-' + getIssueSeverity(issue)">{{ severityLabel(getIssueSeverity(issue)) }}</span>
            </div>
          </div>
          <div v-if="auditResult.suggestions && auditResult.suggestions.length" class="wf-compact-list">
            <div v-for="(sug, i) in auditResult.suggestions" :key="'sug-'+i" class="wf-compact-item wf-compact-sug">
              <i data-lucide="lightbulb" style="width:11px;height:11px;flex-shrink:0;color:#3B6CF6;"></i>
              <span>{{ formatSuggestionItem(sug) }}</span>
            </div>
          </div>
          <div v-if="auditResult.passed && !(auditResult.issues && auditResult.issues.length) && !(auditResult.suggestions && auditResult.suggestions.length)" class="wf-audit-all-pass">
            <i data-lucide="check-circle" style="width:12px;height:12px;"></i>
            所有审核项均已通过
          </div>
        </template>
        <div v-else-if="auditStatus === 'completed'" class="wf-empty-hint" style="font-size:13px;">
          <i data-lucide="check-circle" style="width:12px;height:12px;color:#60A5FA;"></i>
          合规审核已完成（详细数据不可用）
        </div>
      </div>

      <!-- ===== 终审预览区域 ===== -->
      <div class="wf-section wf-section-review" v-if="finalReviewStatus !== 'idle' && finalReviewStatus !== 'pending'">
        <div class="wf-section-header">
          <i data-lucide="eye" style="width:14px;height:14px;"></i>
          <span class="wf-section-title">终审预览</span>
          <span class="wf-section-badge" :style="reviewBadgeStyle">{{ reviewStatusLabel }}</span>
        </div>

        <!-- running -->
        <div v-if="finalReviewStatus === 'running'" class="wf-copywrite-loading" style="padding:8px 0;">
          <div class="mint-loader"><div class="mint-loader-ball"></div></div>
          <div class="wf-copywrite-loading-text">终审处理中...</div>
        </div>

        <!-- error -->
        <div v-else-if="finalReviewStatus === 'error'" class="mint-search-error">
          <i data-lucide="alert-circle" style="width:16px;height:16px;"></i>
          <span>{{ finalReviewError || '终审失败' }}</span>
        </div>

        <!-- awaiting_review：手机预览 + 审核按钮 -->
        <div v-else-if="finalReviewStatus === 'awaiting_review'" class="wf-phone-review">
          <div class="wf-phone-layout">
            <div class="wf-iphone">
              <div class="wf-iphone-screen">
                <div class="wf-iphone-statusbar">
                  <span class="wf-iphone-time">9:41</span>
                  <div class="wf-iphone-notch"></div>
                  <div class="wf-iphone-status-icons">
                    <svg width="13" height="10" viewBox="0 0 16 12"><rect x="0" y="5" width="3" height="7" rx="1" fill="#1a1a1a"/><rect x="4.5" y="3" width="3" height="9" rx="1" fill="#1a1a1a"/><rect x="9" y="1" width="3" height="11" rx="1" fill="#1a1a1a"/><rect x="13" y="0" width="3" height="12" rx="1" fill="#1a1a1a" opacity="0.3"/></svg>
                    <svg width="13" height="10" viewBox="0 0 16 12"><path d="M8 2C5.5 2 3.2 3 1.5 4.7L0 3.2C2.1 1.1 4.9 0 8 0s5.9 1.1 8 3.2L14.5 4.7C12.8 3 10.5 2 8 2z" fill="#1a1a1a"/><path d="M8 5.5c-1.7 0-3.2.7-4.3 1.8L2.2 5.8C3.7 4.3 5.7 3.5 8 3.5s4.3.8 5.8 2.3L12.3 7.3C11.2 6.2 9.7 5.5 8 5.5z" fill="#1a1a1a"/><path d="M8 9c-.8 0-1.6.3-2.1.9L8 12l2.1-2.1C9.6 9.3 8.8 9 8 9z" fill="#1a1a1a"/></svg>
                    <svg width="22" height="10" viewBox="0 0 27 13"><rect x="0" y="1" width="23" height="11" rx="3.5" stroke="#1a1a1a" stroke-width="1" fill="none"/><rect x="24" y="4" width="2" height="5" rx="1" fill="#1a1a1a" opacity="0.4"/><rect x="2" y="3" width="17" height="7" rx="1.5" fill="#1a1a1a"/></svg>
                  </div>
                </div>
                <div class="wf-xhs-content-scroll">
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
                  <div class="wf-xhs-images" v-if="reviewImages.length">
                    <img :src="imageDataUrl(reviewImages[currentImageIndex])" class="wf-xhs-image" />
                    <div v-if="reviewImages.length > 1" class="wf-xhs-dots">
                      <span v-for="(_, i) in reviewImages" :key="i" class="wf-xhs-dot" :class="{ active: i === currentImageIndex }" @click="currentImageIndex = i"></span>
                    </div>
                    <div v-if="reviewImages.length > 1" class="wf-xhs-counter">{{ currentImageIndex + 1 }}/{{ reviewImages.length }}</div>
                  </div>
                  <div v-else class="wf-xhs-images wf-xhs-images-empty"><span>暂无图片</span></div>
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
                <div class="wf-iphone-home-bar"></div>
              </div>
            </div>
          </div>
          <div class="wf-review-actions">
            <button class="wf-review-btn wf-review-pass" @click="submitReviewAction('pass')" :disabled="submitting">
              <i data-lucide="check" style="width:16px;height:16px;"></i>
              {{ submitting ? '提交中...' : '确认，进入发布' }}
            </button>
            <button class="wf-review-btn wf-review-reject" @click="submitReviewAction('reject')" :disabled="submitting">
              <i data-lucide="rotate-ccw" style="width:16px;height:16px;"></i>
              {{ submitting ? '提交中...' : '调优重做' }}
            </button>
          </div>
        </div>

        <!-- completed (passed/rejected) -->
        <div v-else-if="finalReviewStatus === 'completed' || finalReviewStatus === 'passed' || finalReviewStatus === 'rejected'" class="wf-review-result-row">
          <div class="wf-audit-summary" :style="{ background: finalReviewPassed ? '#F0FDF4' : '#FEF2F2' }">
            <i :data-lucide="finalReviewPassed ? 'check-circle' : 'x-circle'" style="width:14px;height:14px;" :style="{ color: finalReviewPassed ? '#059669' : '#DC2626' }"></i>
            <span :style="{ color: finalReviewPassed ? '#059669' : '#DC2626', fontWeight: 600, fontSize: '13px' }">{{ finalReviewPassed ? '确认通过' : '调优重做' }}</span>
          </div>
          <div v-if="finalReviewResult?.feedback" class="wf-compact-item wf-compact-sug" style="margin-top:4px;">
            <i data-lucide="message-square-warning" style="width:11px;height:11px;flex-shrink:0;color:#D97706;"></i>
            <span>{{ finalReviewResult.feedback }}</span>
          </div>
        </div>
      </div>

      <!-- ===== 发布区域 ===== -->
      <div class="wf-section wf-section-publish" v-if="publishStatus !== 'idle' && publishStatus !== 'pending'">
        <div class="wf-section-header">
          <i data-lucide="send" style="width:14px;height:14px;"></i>
          <span class="wf-section-title">发布</span>
          <span class="wf-section-badge" :style="publishBadgeStyle">{{ publishStatusLabel }}</span>
        </div>

        <!-- awaiting_review：手动确认发布 -->
        <div v-if="publishNodeStatus === 'awaiting_review'" class="wf-publish-manual">
          <div class="wf-publish-manual-hint">
            <i data-lucide="check-circle" style="width:14px;height:14px;color:#10B981;"></i>
            <span>终审已通过，确认发布到小红书？</span>
          </div>
          <div v-if="publishResult?.title" class="wf-publish-manual-title">{{ publishResult.title }}</div>
          <button class="wf-publish-confirm-btn" @click="confirmPublish" :disabled="publishing">
            <i data-lucide="send" style="width:14px;height:14px;"></i>
            {{ publishing ? "发布中..." : "确认发布" }}
          </button>
        </div>

        <!-- running -->
        <div v-else-if="publishNodeStatus === 'running'" class="wf-copywrite-loading" style="padding:8px 0;">
          <div class="mint-loader"><div class="mint-loader-ball"></div></div>
          <div class="wf-copywrite-loading-text">
            {{ publishResult && publishResult.status === 'awaiting_manual' ? '内容已填好，请在浏览器窗口手动点击发布按钮' : '正在发布中...' }}
          </div>
        </div>

        <!-- error -->
        <div v-else-if="publishNodeStatus === 'error'" class="mint-search-error">
          <i data-lucide="alert-circle" style="width:16px;height:16px;"></i>
          <span>{{ publishError || '发布失败' }}</span>
        </div>

        <!-- completed -->
        <template v-else-if="publishNodeStatus === 'completed' && publishResult">
          <div class="wf-audit-summary" :style="{ background: publishBgColor }">
            <i :data-lucide="publishIcon" style="width:14px;height:14px;" :style="{ color: publishIconColor }"></i>
            <span :style="{ color: publishTextColor, fontWeight: 600, fontSize: '13px' }">{{ publishResultLabel }}</span>
          </div>
          <div v-if="publishResult.post_id" class="wf-compact-item" style="margin-top:4px;">
            <i data-lucide="link" style="width:11px;height:11px;flex-shrink:0;"></i>
            <span style="font-family:monospace;font-size:13px;">{{ publishResult.post_id }}</span>
          </div>
          <div v-if="publishResult.message" class="wf-compact-item" style="margin-top:2px;">
            <i data-lucide="message-circle" style="width:11px;height:11px;flex-shrink:0;"></i>
            <span>{{ publishResult.message }}</span>
          </div>
          <div v-if="publishResult.status === 'awaiting_manual'" class="wf-manual-hint">
            <i data-lucide="mouse-pointer-click" style="width:12px;height:12px;color:#D97706;"></i>
            <span>内容已填好，请在浏览器窗口手动点击「发布」按钮完成发布</span>
          </div>
          <button class="wf-push-wechat-btn" @click="pushToWechat" :disabled="pushingToWechat" v-if="publishNodeStatus === 'completed' || finalReviewStatus === 'completed'">
            <i data-lucide="send" style="width:12px;height:12px;"></i>
            {{ pushingToWechat ? '推送中...' : '推送到微信' }}
          </button>
        </template>
        <div v-else-if="publishNodeStatus === 'completed'" class="wf-empty-hint" style="font-size:13px;">
          <i data-lucide="check-circle" style="width:12px;height:12px;color:#60A5FA;"></i>
          发布已完成（详细数据不可用）
        </div>
      </div>

    </div>
    <div class="wf-node-meta" v-if="combinedMeta">
      <span class="wf-meta-item"><i data-lucide="clock" style="width:12px;height:12px;"></i>{{ combinedMeta.duration }}</span>
      <span class="wf-meta-item"><i data-lucide="cpu" style="width:12px;height:12px;"></i>{{ combinedMeta.model }}</span>
      <span class="wf-meta-item"><i data-lucide="zap" style="width:12px;height:12px;"></i>{{ combinedMeta.tokens }} tokens</span>
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
  auditStatus: string
  auditMeta: { duration: string; model: string; tokens: string } | null
  auditResult: any
  auditError?: string

  finalReviewStatus: string
  finalReviewMeta: { duration: string; model: string; tokens: string } | null
  finalReviewResult: any
  finalReviewError?: string

  publishStatus: string
  publishMeta: { duration: string; model: string; tokens: string } | null
  publishResult: any
  publishError?: string

  copywriteResult?: any
  imageGenResult?: any

  workflowId?: string
}>()

watch([
  () => props.auditStatus,
  () => props.finalReviewStatus,
  () => props.publishStatus,
  () => props.auditResult,
  () => props.finalReviewResult,
  () => props.publishResult,
], () => nextTick(() => createIcons({ icons })), { deep: true })

const workflowStore = useWorkflowStore()
const accountStore = useAccountStore()
const submitting = ref(false)
const publishing = ref(false)
const pushingToWechat = ref(false)
const currentImageIndex = ref(0)

const accountNickname = computed(() => accountStore.currentAccount?.xhs_nickname || '创作者')
const accountAvatar = computed(() => accountStore.currentAccount?.xhs_avatar_url || '')

function imageDataUrl(b64: string): string {
  if (b64.startsWith('data:')) return b64
  const prefix = b64.startsWith('/9j/') ? 'data:image/jpeg;base64,' : 'data:image/png;base64,'
  return prefix + b64
}
const reviewImages = ref<string[]>([])
const reviewTitle = computed(() => props.finalReviewResult?.title || '')
const reviewContent = computed(() => props.finalReviewResult?.content || '')
const reviewTags = computed(() => props.finalReviewResult?.tags || [])

// ===== combined status for card border =====
const combinedStatus = computed<string>(() => {
  const active = [props.auditStatus, props.finalReviewStatus, props.publishStatus]
  if (active.includes('error')) return 'error'
  if (active.includes('running')) return 'running'
  if (active.includes('awaiting_review')) return 'awaiting_review'
  if (active.includes('completed') || active.includes('passed')) return 'completed'
  if (active.includes('rejected')) return 'rejected'
  return 'idle'
})

const publishNodeStatus = computed(() => props.publishStatus)

const statusColor = computed(() => {
  const map: Record<string, string> = { idle: '#9CA3AF', running: '#FF2442', awaiting_review: '#F59E0B', completed: '#60A5FA', error: '#EF4444', passed: '#10B981', rejected: '#EF4444' }
  return map[combinedStatus.value] || '#9CA3AF'
})
const statusLabel = computed(() => {
  const map: Record<string, string> = { idle: '待执行', running: '执行中', awaiting_review: '请确认', completed: '已完成', error: '失败', passed: '已通过', rejected: '已调优' }
  return map[combinedStatus.value] || '待执行'
})
const statusBadgeStyle = computed(() => {
  if (combinedStatus.value === 'error' || combinedStatus.value === 'rejected') return { background: '#FEE2E2', color: '#DC2626' }
  if (combinedStatus.value === 'passed') return { background: '#D1FAE5', color: '#059669' }
  if (combinedStatus.value === 'awaiting_review') return { background: '#FFFBEB', color: '#D97706' }
  if (combinedStatus.value === 'completed') return { background: '#DBEAFE', color: '#2563EB' }
  if (combinedStatus.value === 'running') return { background: '#FEE2E2', color: '#DC2626' }
  return { background: '#F1F5F9', color: '#64748B' }
})

// ===== audit section =====
const auditStatusLabel = computed(() => {
  const map: Record<string, string> = { idle: '待执行', pending: '待执行', running: '审核中', completed: '已完成', error: '失败' }
  return map[props.auditStatus] || '待执行'
})
const auditBadgeStyle = computed(() => {
  if (props.auditStatus === 'error') return { background: '#FEE2E2', color: '#DC2626' }
  if (props.auditStatus === 'completed') return { background: '#DBEAFE', color: '#2563EB' }
  if (props.auditStatus === 'running') return { background: '#FEE2E2', color: '#DC2626' }
  return { background: '#F1F5F9', color: '#64748B' }
})

// ===== final review section =====
const finalReviewPassed = computed(() => {
  const rs = props.finalReviewResult?.review_status || props.finalReviewStatus
  return rs === 'passed'
})
const reviewStatusLabel = computed(() => {
  const rs = props.finalReviewResult?.review_status || props.finalReviewStatus
  if (rs === 'passed') return '已通过'
  if (rs === 'rejected') return '已调优'
  if (props.finalReviewStatus === 'awaiting_review') return '请确认'
  if (props.finalReviewStatus === 'running') return '确认中'
  return '待执行'
})
const reviewBadgeStyle = computed(() => {
  const rs = props.finalReviewResult?.review_status || props.finalReviewStatus
  if (rs === 'passed') return { background: '#D1FAE5', color: '#059669' }
  if (rs === 'rejected') return { background: '#FEE2E2', color: '#DC2626' }
  if (props.finalReviewStatus === 'awaiting_review') return { background: '#FFFBEB', color: '#D97706' }
  if (props.finalReviewStatus === 'running') return { background: '#FEE2E2', color: '#DC2626' }
  return { background: '#F1F5F9', color: '#64748B' }
})

// ===== publish section =====
const publishStatusLabel = computed(() => {
  if (props.publishStatus === 'awaiting_review') return '待发布'
  if (props.publishStatus === 'running') return '发布中'
  if (props.publishStatus === 'completed') return '已完成'
  if (props.publishStatus === 'error') return '失败'
  return '待执行'
})
const publishBadgeStyle = computed(() => {
  if (props.publishStatus === 'error') return { background: '#FEE2E2', color: '#DC2626' }
  if (props.publishStatus === 'completed') return { background: '#DBEAFE', color: '#2563EB' }
  if (props.publishStatus === 'running') return { background: '#FEE2E2', color: '#DC2626' }
  if (props.publishStatus === 'awaiting_review') return { background: '#FFFBEB', color: '#D97706' }
  return { background: '#F1F5F9', color: '#64748B' }
})
const publishBgColor = computed(() => {
  const s = props.publishResult?.status
  if (s === 'success') return '#F0FDF4'
  if (s === 'awaiting_manual') return '#FFFBEB'
  if (s === 'failed') return '#FEF2F2'
  return '#F8FAFC'
})
const publishIconColor = computed(() => {
  const s = props.publishResult?.status
  if (s === 'success') return '#059669'
  if (s === 'awaiting_manual') return '#D97706'
  if (s === 'failed') return '#DC2626'
  return '#9CA3AF'
})
const publishIcon = computed(() => {
  const s = props.publishResult?.status
  if (s === 'success') return 'check-circle'
  if (s === 'awaiting_manual') return 'clock'
  if (s === 'failed') return 'x-circle'
  return 'send'
})
const publishTextColor = computed(() => {
  const s = props.publishResult?.status
  if (s === 'success') return '#059669'
  if (s === 'awaiting_manual') return '#D97706'
  if (s === 'failed') return '#DC2626'
  return '#64748B'
})
const publishResultLabel = computed(() => {
  const s = props.publishResult?.status
  if (s === 'success') return '发布成功'
  if (s === 'awaiting_manual') return '等待手动确认'
  if (s === 'failed') return '发布失败'
  return '发布中'
})

// ===== combined meta =====
const combinedMeta = computed(() => {
  const parts = [props.auditMeta, props.finalReviewMeta, props.publishMeta].filter(Boolean)
  if (!parts.length) return null
  const totalTokens = parts.reduce((sum, m) => sum + (parseInt(m!.tokens) || 0), 0)
  return {
    duration: parts.map(m => m!.duration).filter(d => d !== '-').join(' + ') || '-',
    model: parts.map(m => m!.model).filter(m => m !== '-').join(' / ') || '-',
    tokens: String(totalTokens),
  }
})

// ===== fetch review images =====
watch(() => props.finalReviewStatus, async (status) => {
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

// ===== submit review =====
async function submitReviewAction(action: 'pass' | 'reject') {
  if (!props.workflowId) { alert('缺少工作流 ID'); return }
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

// ===== confirm publish =====
async function confirmPublish() {
  if (publishing.value || !props.workflowId) return
  publishing.value = true
  try {
    await workflowStore.resumeWorkflow()
  } catch (e: any) {
    console.error('[FinalReviewCard] confirmPublish failed:', e)
  } finally {
    publishing.value = false
  }
}

// ===== push to wechat =====
function wechatAuthHeaders(): Record<string, string> {
  const token = localStorage.getItem('token')
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }
  return headers
}

async function pushToWechat() {
  if (pushingToWechat.value) return
  pushingToWechat.value = true
  try {
    const statusRes = await fetch('/api/wechat/status', { headers: wechatAuthHeaders() })
    const statusData = await statusRes.json()
    if (!statusData.success || statusData.data?.status !== 'logged_in') {
      alert('微信机器人未连接，请先在设置中连接微信')
      return
    }
    const msgRes = await fetch('/api/wechat/messages?limit=1', { headers: wechatAuthHeaders() })
    const msgData = await msgRes.json()
    const lastIncoming = msgData.success && msgData.data?.messages
      ? [...msgData.data.messages].reverse().find((m: any) => m.from_user_id !== 'bot')
      : null
    if (!lastIncoming) {
      alert('请先在微信上给机器人发一条消息，建立会话')
      return
    }

    // 聚合整个工作流的输出
    const cw = props.copywriteResult || {}
    const fr = props.finalReviewResult || {}
    const ig = props.imageGenResult || {}

    const title = fr.title || cw.title || ''
    const content = fr.content || cw.content || ''
    const tags = fr.tags || cw.tags || []
    // 图片优先从 reviewImages ref 取（已加载的图片），再从 props 取
    const imagesBase64: string[] = reviewImages.value.length > 0
      ? reviewImages.value
      : (fr.images_base64 || ig.images_base64 || [])

    if (!title && !content && imagesBase64.length === 0) {
      alert('没有可推送的内容（请先完成文案生成步骤）')
      return
    }

    // 组装完整推送内容：标题 + 正文 + 标签
    let fullContent = content
    if (tags && tags.length > 0) {
      fullContent += '\n\n' + tags.map((t: string) => `#${t}`).join(' ')
    }

    const pushRes = await fetch('/api/wechat/push', {
      method: 'POST',
      headers: wechatAuthHeaders(),
      body: JSON.stringify({
        to_user_id: lastIncoming.from_user_id,
        title,
        text: fullContent,
        images_base64: imagesBase64,
        context_token: lastIncoming.context_token || '',
      }),
    })
    const pushData = await pushRes.json()
    if (pushData.success) {
      alert('✅ 工作流内容已推送到微信')
    } else {
      alert('推送失败: ' + (pushData.detail || pushData.message || '未知错误'))
    }
  } catch (e: any) {
    alert('推送失败: ' + (e.message || '网络错误'))
  } finally {
    pushingToWechat.value = false
  }
}

// ===== format helpers =====
function formatIssueItem(issue: any): string {
  if (typeof issue === 'string') return issue
  return issue.description || issue.dimension || issue.title || '未知问题'
}
function getIssueSeverity(issue: any): string {
  if (typeof issue === 'string') return ''
  return issue.severity || issue.level || ''
}
function severityLabel(s: string): string {
  const map: Record<string, string> = { high: '严重', medium: '中等', low: '轻微', critical: '严重', warning: '警告', info: '提示' }
  return map[s] || s
}
function formatSuggestionItem(sug: any): string {
  if (typeof sug === 'string') return sug
  return sug.suggestion || sug.description || sug.title || ''
}
</script>

<style scoped>
/* ===== section 分区 ===== */
.wf-section {
  padding: 10px 0;
  border-top: 1px solid #F1F5F9;
}
.wf-section:first-child {
  border-top: none;
  padding-top: 0;
}
.wf-section-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 8px;
  color: #6B7280;
}
.wf-section-title {
  font-weight: 600;
  font-size: 13px;
}
.wf-section-badge {
  display: inline-flex;
  align-items: center;
  padding: 1px 8px;
  border-radius: 10px;
  font-size: 12px;
  font-weight: 500;
  margin-left: auto;
}

/* ===== audit ===== */
.wf-audit-summary {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  border-radius: 8px;
}
.wf-audit-all-pass {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: #059669;
  background: #F0FDF4;
  padding: 4px 8px;
  border-radius: 6px;
}
.wf-compact-list {
  display: flex;
  flex-direction: column;
  gap: 3px;
  margin-top: 4px;
}
.wf-compact-item {
  display: flex;
  align-items: flex-start;
  gap: 5px;
  font-size: 12px;
  color: #6B7280;
  line-height: 1.5;
  padding: 2px 0;
}
.wf-compact-warn { color: #B45309; }
.wf-compact-warn i { color: #EF4444; }
.wf-compact-sug i { color: #3B6CF6; }

.wf-severity-tag {
  display: inline-flex;
  align-items: center;
  padding: 0 5px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 500;
  flex-shrink: 0;
  margin-left: 4px;
}
.wf-severity-critical, .wf-severity-high { background: #FEE2E2; color: #DC2626; }
.wf-severity-medium, .wf-severity-warning { background: #FFFBEB; color: #D97706; }
.wf-severity-low, .wf-severity-info { background: #EFF6FF; color: #3B6CF6; }

/* ===== phone review ===== */
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
  padding: 8px 0 0;
}
.wf-iphone {
  width: 325px;
  background: #1a1a1a;
  border-radius: 44px;
  padding: 3px;
  position: relative;
  border: 2.5px solid #1a1a1a;
  box-shadow: 0 2px 8px rgba(0,0,0,0.06), 0 12px 40px rgba(0,0,0,0.12);
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
.wf-iphone-screen .wf-xhs-content-scroll::-webkit-scrollbar { display: none; }
.wf-iphone-statusbar {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  padding: 0 20px;
  background: #FFFFFF;
  height: 44px;
  position: relative;
}
.wf-iphone-time { font-size: 14px; font-weight: 600; color: #1a1a1a; width: 44px; padding-top: 14px; z-index: 1; }
.wf-iphone-notch { width: 120px; height: 26px; background: #1a1a1a; border-radius: 0 0 16px 16px; position: absolute; left: 50%; transform: translateX(-50%); top: 0; }
.wf-iphone-status-icons { display: flex; align-items: center; gap: 4px; width: 72px; justify-content: flex-end; padding-top: 14px; z-index: 1; }

.wf-xhs-navbar { display: flex; align-items: center; justify-content: space-between; padding: 0 12px; background: #FFFFFF; border-bottom: 0.5px solid #EFEFEF; }
.wf-xhs-nav-back { flex-shrink: 0; }
.wf-xhs-nav-user { display: flex; align-items: center; gap: 6px; flex: 1; }
.wf-xhs-nav-avatar { width: 26px; height: 26px; border-radius: 50%; background: linear-gradient(135deg, #FF2442, #FF6B81); flex-shrink: 0; overflow: hidden; display: flex; align-items: center; justify-content: center; font-size: 12px; color: #fff; font-weight: 500; }
.wf-xhs-nav-avatar-img { width: 100%; height: 100%; object-fit: cover; }
.wf-xhs-nav-name { font-size: 14px; font-weight: 500; color: #333; }
.wf-xhs-follow-btn { padding: 3px 12px; background: #FF2442; color: #fff; border-radius: 12px; font-size: 11px; font-weight: 500; flex-shrink: 0; }

.wf-xhs-images { position: relative; width: 100%; background: #F5F5F5; overflow: hidden; margin-top: 6px; }
.wf-xhs-images-empty { display: flex; align-items: center; justify-content: center; height: 200px; color: #999; font-size: 13px; }
.wf-xhs-image { width: 100%; height: auto; display: block; }
.wf-xhs-dots { position: absolute; bottom: 10px; left: 50%; transform: translateX(-50%); display: flex; gap: 5px; }
.wf-xhs-dot { width: 6px; height: 6px; border-radius: 50%; background: rgba(255,255,255,0.45); cursor: pointer; transition: all 0.2s; }
.wf-xhs-dot.active { background: #fff; box-shadow: 0 0 4px rgba(0,0,0,0.15); }
.wf-xhs-counter { position: absolute; top: 10px; right: 10px; background: rgba(0,0,0,0.4); color: #fff; font-size: 10px; padding: 2px 7px; border-radius: 10px; backdrop-filter: blur(4px); }

.wf-xhs-body { padding: 10px 12px 4px; background: #FFFFFF; }
.wf-xhs-title { font-size: 13px; font-weight: 600; color: #1a1a1a; line-height: 1.4; margin-bottom: 2px; }
.wf-xhs-content { font-size: 11px; color: #333; line-height: 1.6; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
.wf-xhs-expand { color: #999; font-size: 11px; margin-left: 2px; }
.wf-xhs-tags { display: flex; flex-wrap: wrap; gap: 2px; margin-top: 4px; }
.wf-xhs-tag { font-size: 10px; color: #3378EA; line-height: 1.5; }
.wf-xhs-date { font-size: 10px; color: #B8B8B8; margin-top: 4px; }

.wf-xhs-footer { display: flex; align-items: center; padding: 8px 12px; background: #FFFFFF; border-top: 0.5px solid #F0F0F0; gap: 8px; }
.wf-xhs-input { flex: 1; background: #F5F5F5; border-radius: 14px; padding: 4px 10px; font-size: 11px; color: #999; min-height: 24px; display: flex; align-items: center; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.wf-xhs-actions-right { display: flex; align-items: center; gap: 14px; flex-shrink: 0; }
.wf-xhs-action { display: flex; align-items: center; gap: 3px; font-size: 12px; color: #333; cursor: pointer; }
.wf-iphone-home-bar { width: 120px; height: 4px; background: #1a1a1a; border-radius: 2px; margin: 6px auto 6px; opacity: 0.18; }

.wf-review-actions { display: flex; gap: 10px; padding-top: 4px; }
.wf-review-btn { display: inline-flex; align-items: center; gap: 6px; padding: 8px 18px; border: none; border-radius: 8px; font-size: 15px; font-weight: 500; cursor: pointer; transition: opacity 0.15s; }
.wf-review-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.wf-review-pass { background: #10B981; color: #fff; }
.wf-review-pass:hover:not(:disabled) { background: #059669; }
.wf-review-reject { background: #F3F4F6; color: #DC2626; }
.wf-review-reject:hover:not(:disabled) { background: #FEE2E2; }

.wf-review-result-row { display: flex; flex-direction: column; gap: 4px; }

/* ===== publish ===== */
.wf-publish-manual { padding: 4px 0; display: flex; flex-direction: column; gap: 8px; }
.wf-publish-manual-hint { display: flex; align-items: center; gap: 6px; font-size: 13px; color: #6B7280; font-weight: 500; }
.wf-publish-manual-title { font-size: 13px; color: #6B7280; padding: 4px 8px; background: #F8FAFC; border-radius: 6px; border-left: 3px solid #FF2442; }
.wf-publish-confirm-btn { padding: 8px 16px; border: none; border-radius: 8px; font-size: 13px; font-weight: 600; cursor: pointer; display: inline-flex; align-items: center; justify-content: center; gap: 6px; background: #FF2442; color: #FFFFFF; transition: opacity 0.2s; }
.wf-publish-confirm-btn:disabled { opacity: 0.6; cursor: not-allowed; }
.wf-publish-confirm-btn:hover:not(:disabled) { background: #E01E3A; }

.wf-push-wechat-btn { margin-top: 8px; padding: 6px 14px; border: 1px solid #07C160; border-radius: 8px; font-size: 12px; font-weight: 600; cursor: pointer; display: inline-flex; align-items: center; justify-content: center; gap: 6px; background: #fff; color: #07C160; transition: all 0.2s; }
.wf-push-wechat-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.wf-push-wechat-btn:hover:not(:disabled) { background: #07C160; color: #fff; }

.wf-manual-hint { display: flex; align-items: center; gap: 6px; font-size: 12px; background: #FFFBEB; border: 1px solid #F59E0B; color: #92400E; padding: 6px 10px; border-radius: 6px; margin-top: 4px; }

/* ===== Hero layout：左结论 / 中预览 / 下操作 ===== */
.wf-final-hero .wf-node-body {
  display: grid;
  grid-template-columns: 230px minmax(0, 1fr);
  grid-template-areas:
    "audit review"
    "publish publish";
  gap: 16px;
  align-items: start;
}
.wf-final-hero .wf-section-audit {
  grid-area: audit;
  align-self: stretch;
  border-top: none;
  padding-top: 0;
  border-right: 1px solid #F1F5F9;
  padding-right: 16px;
}
.wf-final-hero .wf-section-review {
  grid-area: review;
  border-top: none;
  padding-top: 0;
}
.wf-final-hero .wf-section-publish {
  grid-area: publish;
  border-top: 1px solid #F1F5F9;
  padding-top: 12px;
}
.wf-final-hero .wf-phone-review {
  gap: 14px;
}
.wf-final-hero .wf-iphone {
  width: 300px;
}
.wf-final-hero .wf-iphone-screen {
  height: 600px;
}

@media (max-width: 720px) {
  .wf-final-hero .wf-node-body {
    grid-template-columns: 1fr;
    grid-template-areas:
      "audit"
      "review"
      "publish";
  }
  .wf-final-hero .wf-section-audit {
    border-right: none;
    border-bottom: 1px solid #F1F5F9;
    padding-right: 0;
    padding-bottom: 12px;
  }
}
</style>
