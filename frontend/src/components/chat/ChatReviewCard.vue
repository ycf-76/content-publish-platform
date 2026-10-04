<template>
  <div class="crc-card" :class="{ 'crc-processed': isProcessed }">
    <div class="crc-header">
      <span class="crc-badge" :class="badgeClass">{{ badgeText }}</span>
      <span class="crc-type">{{ reviewType === 'image' ? '图片审核' : '发布终审' }}</span>
    </div>

    <div v-if="reviewType === 'image' && images?.length" class="crc-images">
      <img
        v-for="(url, i) in images"
        :key="i"
        :src="url"
        class="crc-thumb"
        loading="lazy"
        @click="previewImage(url)"
      />
    </div>

    <div v-if="reviewType === 'final' && content" class="crc-preview">
      <h4 class="crc-title">{{ content.title }}</h4>
      <p class="crc-body">{{ content.body?.slice(0, 200) }}{{ (content.body?.length ?? 0) > 200 ? '…' : '' }}</p>
      <div v-if="content.tags?.length" class="crc-tags">
        <span v-for="tag in content.tags" :key="tag" class="crc-tag">#{{ tag }}</span>
      </div>
    </div>

    <div v-if="!isProcessed" class="crc-actions">
      <button class="crc-btn crc-btn-pass" @click="submitReview('pass')" :disabled="submitting">
        {{ submitting ? '提交中…' : (reviewType === 'image' ? '图片可以' : '通过并发布') }}
      </button>
      <button class="crc-btn crc-btn-reject" @click="submitReview('reject')" :disabled="submitting">
        {{ submitting ? '提交中…' : (reviewType === 'image' ? '重新生成' : '打回修改') }}
      </button>
    </div>

    <div v-else class="crc-result">
      <span class="crc-result-icon">{{ lastAction === 'pass' ? '✓' : '✕' }}</span>
      <span class="crc-result-text">{{ lastAction === 'pass' ? '已通过' : '已打回' }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { authFetch } from '@/api/client'

const props = defineProps<{
  workflowId: string
  reviewType: 'image' | 'final'
  images?: string[]
  content?: { title: string; body: string; tags: string[] }
}>()

const emit = defineEmits<{
  reviewed: [action: string]
}>()

const submitting = ref(false)
const isProcessed = ref(false)
const lastAction = ref('')

const badgeClass = props.reviewType === 'image' ? 'crc-badge-image' : 'crc-badge-final'
const badgeText = '待审核'

async function submitReview(action: 'pass' | 'reject') {
  if (submitting.value) return
  submitting.value = true

  try {
    const res = await authFetch(`/api/workflows/${props.workflowId}/review`, {
      method: 'POST',
      body: JSON.stringify({ action, feedback: '' }),
    })

    if (!res.ok) {
      const err = await res.text()
      console.error('[ChatReviewCard] review failed:', err)
      return
    }

    lastAction.value = action
    isProcessed.value = true
    emit('reviewed', action)
  } catch (e) {
    console.error('[ChatReviewCard] review error:', e)
  } finally {
    submitting.value = false
  }
}

function previewImage(url: string) {
  window.open(url, '_blank')
}
</script>

<style scoped>
.crc-card {
  background: #fffbeb;
  border: 1px solid #fbbf24;
  border-radius: 10px;
  padding: 10px 12px;
  margin-top: 6px;
  transition: all 0.3s ease;
}

.crc-processed {
  background: #f0fdf4;
  border-color: #86efac;
}

.crc-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.crc-badge {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 4px;
  color: #fff;
}

.crc-badge-image {
  background: #8b5cf6;
}

.crc-badge-final {
  background: #f59e0b;
}

.crc-type {
  font-size: 13px;
  font-weight: 500;
  color: #334155;
}

.crc-images {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}

.crc-thumb {
  width: 72px;
  height: 72px;
  object-fit: cover;
  border-radius: 6px;
  border: 1px solid #e2e8f0;
  cursor: pointer;
  transition: transform 0.15s;
}

.crc-thumb:hover {
  transform: scale(1.05);
}

.crc-preview {
  margin-bottom: 8px;
}

.crc-title {
  font-size: 14px;
  font-weight: 600;
  color: #1e293b;
  margin: 0 0 4px;
}

.crc-body {
  font-size: 12px;
  color: #64748b;
  margin: 0 0 6px;
  line-height: 1.5;
}

.crc-tags {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}

.crc-tag {
  font-size: 11px;
  color: #3b82f6;
  background: #eff6ff;
  padding: 1px 6px;
  border-radius: 3px;
}

.crc-actions {
  display: flex;
  gap: 8px;
}

.crc-btn {
  flex: 1;
  padding: 6px 12px;
  border-radius: 6px;
  border: none;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
}

.crc-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.crc-btn-pass {
  background: #22c55e;
  color: #fff;
}

.crc-btn-pass:hover:not(:disabled) {
  background: #16a34a;
}

.crc-btn-reject {
  background: #f1f5f9;
  color: #64748b;
  border: 1px solid #e2e8f0;
}

.crc-btn-reject:hover:not(:disabled) {
  background: #e2e8f0;
  color: #475569;
}

.crc-result {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: #16a34a;
}

.crc-result-icon {
  font-weight: 700;
}
</style>