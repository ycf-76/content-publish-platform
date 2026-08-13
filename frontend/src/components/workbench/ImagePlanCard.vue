<template>
  <div class="mint-wf-card wf-node-card wf-node-image-plan" id="card-image_plan" :class="`wf-state-${nodeStatus}`">
    <div class="mint-wf-header">
      <div class="mint-wf-title-row">
        <div class="mint-wf-step">04</div>
        <div class="wf-node-title-block">
          <div class="mint-wf-title">
            <i data-lucide="layout-template" class="wf-node-icon"></i>
            图片规划
            <code class="wf-node-key">image_plan</code>
          </div>
        </div>
      </div>
      <span class="mint-badge wf-status-badge" :style="statusBadgeStyle">
        <span class="mint-status-dot" :style="{ background: statusColor }"></span>
        {{ statusLabel }}
      </span>
    </div>

    <div class="wf-node-body">
      <div v-if="nodeStatus === 'idle'" class="wf-plan-empty">
        <i data-lucide="image" style="width:20px;height:20px;color:#D1D5DB;"></i>
        <span>等待文案撰写完成后自动进入图片规划</span>
      </div>

      <div v-else-if="nodeStatus === 'running'" class="wf-plan-loading">
        <div class="mint-loader">
          <div class="mint-loader-ball"></div>
        </div>
        <span>正在规划卡片布局...</span>
      </div>

      <div v-else-if="nodeStatus === 'error'" class="wf-plan-error">
        <i data-lucide="alert-circle" style="width:18px;height:18px;"></i>
        <span>{{ errorMessage || '图片规划失败' }}</span>
      </div>

      <div v-else-if="nodeStatus === 'completed' && result" class="wf-plan-content">
        <div class="wf-plan-overview">
          <div class="wf-plan-overview-item" v-if="result.card_draft">
            <i data-lucide="palette" style="width:14px;height:14px;"></i>
            <span class="wf-plan-overview-label">模板</span>
            <span class="wf-plan-overview-value">{{ templateLabel(result.card_draft.suggested_template) }}</span>
          </div>
          <div class="wf-plan-overview-item" v-if="result.card_draft?.custom_accent">
            <i data-lucide="droplets" style="width:14px;height:14px;"></i>
            <span class="wf-plan-overview-label">主题色</span>
            <span class="wf-plan-accent-dot" :style="{ background: result.card_draft.custom_accent }"></span>
            <span class="wf-plan-overview-value">{{ result.card_draft.custom_accent }}</span>
          </div>
          <div class="wf-plan-overview-item" v-if="result.card_draft?.suggested_decoration?.type">
            <i data-lucide="sparkles" style="width:14px;height:14px;"></i>
            <span class="wf-plan-overview-label">装饰</span>
            <span class="wf-plan-overview-value">{{ decorationLabel(result.card_draft.suggested_decoration.type) }}</span>
          </div>
          <div class="wf-plan-overview-item">
            <i data-lucide="layers" style="width:14px;height:14px;"></i>
            <span class="wf-plan-overview-label">页数</span>
            <span class="wf-plan-overview-value">{{ pageCount }} 页</span>
          </div>
        </div>

        <div v-if="pages.length > 0" class="wf-plan-pages">
          <div
            v-for="(page, i) in pages"
            :key="i"
            class="wf-plan-page"
          >
            <div class="wf-plan-page-index">{{ i + 1 }}</div>
            <div class="wf-plan-page-body">
              <div class="wf-plan-page-head">
                <span class="wf-plan-page-type" :class="`wf-type-${page.type}`">{{ pageTypeLabel(page.type) }}</span>
                <span class="wf-plan-page-title">{{ page.title || '第 ' + (i + 1) + ' 页' }}</span>
              </div>
              <div v-if="page.subtitle" class="wf-plan-page-sub">{{ page.subtitle }}</div>
              <div v-if="page.content" class="wf-plan-page-desc">{{ truncateContent(page.content) }}</div>
              <div v-if="page.listItems?.length" class="wf-plan-page-tags">
                <span v-for="(item, j) in page.listItems.slice(0, 3)" :key="j" class="wf-plan-page-tag">{{ item }}</span>
                <span v-if="page.listItems.length > 3" class="wf-plan-page-tag wf-plan-page-tag-more">+{{ page.listItems.length - 3 }}</span>
              </div>
              <div v-if="page.footer" class="wf-plan-page-footer">{{ page.footer }}</div>
            </div>
          </div>
        </div>

        <div v-if="result._model_used" class="wf-plan-model">
          <i data-lucide="cpu" style="width:11px;height:11px;"></i>
          {{ result._model_used }}
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
import { computed, watch, nextTick } from 'vue'
import { createIcons, icons } from 'lucide'

const props = defineProps<{
  nodeStatus: string
  nodeMeta: { duration: string; model: string; tokens: string } | null
  result: any
  errorMessage?: string
}>()

watch(() => props.nodeStatus, () => nextTick(() => createIcons({ icons })))
watch(() => props.result, () => nextTick(() => createIcons({ icons })), { deep: true })

const statusColor = computed(() => {
  const map: Record<string, string> = {
    idle: '#9CA3AF',
    running: '#FF2442',
    completed: '#60A5FA',
    error: '#EF4444',
  }
  return map[props.nodeStatus] || '#9CA3AF'
})

const statusLabel = computed(() => {
  const map: Record<string, string> = {
    idle: '待执行',
    running: '执行中',
    completed: '已完成',
    error: '失败',
  }
  return map[props.nodeStatus] || '待执行'
})

const statusBadgeStyle = computed(() => {
  if (props.nodeStatus === 'error') return { background: '#FEE2E2', color: '#DC2626' }
  if (props.nodeStatus === 'completed') return { background: '#DBEAFE', color: '#2563EB' }
  if (props.nodeStatus === 'running') return { background: '#FEE2E2', color: '#DC2626' }
  return { background: '#F1F5F9', color: '#64748B' }
})

const pages = computed(() => {
  return props.result?.card_draft?.pages || []
})

const pageCount = computed(() => {
  return pages.value.length || 0
})

function templateLabel(template: string): string {
  const map: Record<string, string> = {
    minimal_white: '极简白',
    warm_card: '暖色卡片',
    dark_tech: '暗色科技',
  }
  return map[template] || template || '默认'
}

function pageTypeLabel(type: string): string {
  const map: Record<string, string> = {
    cover: '封面',
    content: '正文',
    quote: '金句',
    list: '清单',
  }
  return map[type] || type
}

function decorationLabel(type: string): string {
  const map: Record<string, string> = {
    gradient_orbs: '暖光斑',
    noise: '纸张纹理',
    grid_lines: '网格线',
    geometric: '几何色块',
    dots: '波点',
    wave: '波浪',
    none: '无',
  }
  return map[type] || type
}

function truncateContent(content: string): string {
  if (!content) return ''
  return content.length > 60 ? content.slice(0, 60) + '...' : content
}
</script>

<style scoped>
.wf-plan-empty {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 12px;
  font-size: 14px;
  color: #64748B;
  background: #F8FAFC;
  border-radius: 8px;
}
.wf-plan-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 24px 0;
  color: #9CA3AF;
  font-size: 14px;
}
.wf-plan-error {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 16px;
  color: #DC2626;
  font-size: 14px;
  background: #FEF2F2;
  border-radius: 8px;
}

.wf-plan-content {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.wf-plan-overview {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.wf-plan-overview-item {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 5px 10px;
  background: #F8FAFC;
  border-radius: 12px;
  font-size: 13px;
  color: #64748B;
}
.wf-plan-overview-item i {
  color: #94A3B8;
}
.wf-plan-overview-label {
  color: #94A3AF;
}
.wf-plan-overview-value {
  font-weight: 600;
  color: #334155;
}
.wf-plan-accent-dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  border: 2px solid #fff;
  box-shadow: 0 0 0 1px #E2E8F0;
}

.wf-plan-pages {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.wf-plan-page {
  display: flex;
  gap: 10px;
  padding: 10px 12px;
  background: #FAFAFA;
  border-radius: 10px;
  transition: background 0.15s;
}
.wf-plan-page:hover {
  background: #F1F5F9;
}
.wf-plan-page-index {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  color: #94A3B8;
  font-size: 12px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  margin-top: 1px;
}
.wf-plan-page-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.wf-plan-page-head {
  display: flex;
  align-items: center;
  gap: 8px;
}
.wf-plan-page-type {
  display: inline-block;
  padding: 1px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 600;
  color: #fff;
  background: #94A3B8;
  flex-shrink: 0;
}
.wf-type-cover { background: #FF2442; }
.wf-type-content { background: #3B6CF6; }
.wf-type-quote { background: #8B5CF6; }
.wf-type-list { background: #10B981; }
.wf-type-flow { background: #3B6CF6; }
.wf-type-timeline { background: #8B5CF6; }
.wf-type-background { background: #F59E0B; }
.wf-type-photo { background: #6B7280; }

.wf-plan-page-title {
  font-size: 14px;
  font-weight: 600;
  color: #334155;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.wf-plan-page-sub {
  font-size: 13px;
  color: #64748B;
  line-height: 1.4;
}
.wf-plan-page-desc {
  font-size: 13px;
  color: #94A3B8;
  line-height: 1.4;
}
.wf-plan-page-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 2px;
}
.wf-plan-page-tag {
  padding: 1px 7px;
  background: #F1F5F9;
  border-radius: 4px;
  font-size: 11px;
  color: #64748B;
}
.wf-plan-page-tag-more {
  background: #E0E7FF;
  color: #4F46E5;
  font-weight: 600;
}
.wf-plan-page-footer {
  font-size: 12px;
  color: #CBD5E1;
  margin-top: 2px;
}

.wf-plan-model {
  display: flex;
  align-items: center;
  gap: 4px;
  justify-content: flex-end;
  font-size: 12px;
  color: #CBD5E1;
}
.wf-node-image-plan.mint-wf-card {
  height: auto;
  min-height: 120px;
  max-height: none;
  overflow: hidden;
}
.wf-node-image-plan .wf-node-body {
  flex: 0 0 auto;
  max-height: none;
  overflow: visible;
}
</style>