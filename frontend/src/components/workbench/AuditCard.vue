<template>
  <div class="mint-wf-card wf-node-card wf-node-audit" id="card-audit" :class="`wf-state-${nodeStatus}`">
    <div class="mint-wf-header">
      <div class="mint-wf-title-row">
        <div class="mint-wf-step">07</div>
        <div class="wf-node-title-block">
          <div class="mint-wf-title">
            <i data-lucide="shield-check" class="wf-node-icon"></i>
            合规审核
            <code class="wf-node-key">audit</code>
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
        等待图片审核通过后自动进行合规审核
      </div>
      <div v-else-if="nodeStatus === 'running'" class="wf-copywrite-loading">
        <div class="mint-loader"><div class="mint-loader-ball"></div></div>
        <div class="wf-copywrite-loading-text">AI 正在审核文案合规性...</div>
      </div>
      <div v-else-if="nodeStatus === 'error'" class="mint-search-error">
        <i data-lucide="alert-circle" style="width:20px;height:20px;"></i>
        <span>{{ errorMessage || '合规审核失败' }}</span>
      </div>
      <template v-else-if="nodeStatus === 'completed' && result">
        <!-- 审核结果总览 -->
        <div class="wf-plan-summary" :style="{ background: result.passed ? '#F0FDF4' : '#FEF2F2' }">
          <i :data-lucide="result.passed ? 'check-circle' : 'x-circle'" style="width:16px;height:16px;" :style="{ color: result.passed ? '#059669' : '#DC2626' }"></i>
          <span :style="{ color: result.passed ? '#059669' : '#DC2626', fontWeight: 600, fontSize: '14px' }">{{ result.passed ? '审核通过' : '发现问题' }}</span>
          <span v-if="result._skill" class="wf-plan-suggestion" style="margin-left:8px;">技能：{{ result._skill }}</span>
        </div>

        <!-- 问题列表 -->
        <div v-if="result.issues && result.issues.length" class="wf-checklist">
          <div class="wf-pattern-label" style="margin-bottom:4px;">
            <i data-lucide="alert-triangle" style="width:12px;height:12px;color:#EF4444;"></i>
            发现 {{ result.issues.length }} 个问题
          </div>
          <div v-for="(issue, i) in result.issues" :key="i" class="wf-check-item">
            <span class="wf-check-icon wf-check-warn"><i data-lucide="alert-triangle" style="width:12px;height:12px;"></i></span>
            <span class="wf-check-text">{{ formatIssueItem(issue) }}</span>
            <span v-if="getIssueSeverity(issue)" class="wf-severity-tag" :class="'wf-severity-' + getIssueSeverity(issue)">
              {{ severityLabel(getIssueSeverity(issue)) }}
            </span>
          </div>
        </div>

        <!-- 修改建议 -->
        <div v-if="result.suggestions && result.suggestions.length" class="wf-checklist">
          <div class="wf-pattern-label" style="margin-bottom:4px;">
            <i data-lucide="lightbulb" style="width:12px;height:12px;color:#3B6CF6;"></i>
            修改建议（{{ result.suggestions.length }} 条）
          </div>
          <div v-for="(sug, i) in result.suggestions" :key="i" class="wf-check-item">
            <span class="wf-check-icon wf-check-pass"><i data-lucide="check" style="width:12px;height:12px;"></i></span>
            <span class="wf-check-text">{{ formatSuggestionItem(sug) }}</span>
          </div>
        </div>

        <!-- 全部通过 -->
        <div v-if="result.passed && !(result.issues && result.issues.length) && !(result.suggestions && result.suggestions.length)" class="wf-empty-hint" style="color:#059669;background:#F0FDF4;">
          <i data-lucide="check-circle" style="width:14px;height:14px;"></i>
          所有审核项均已通过，内容合规
        </div>

        <!-- 审核方式标识 -->
        <div v-if="result.audit_method" class="wf-plan-summary" style="background:#F8FAFC;justify-content:flex-end;">
          <span class="wf-meta-item" style="font-size: 15px;color:#94A3B8;"><i data-lucide="cpu" style="width:11px;height:11px;"></i>{{ auditMethodLabel(result.audit_method) }}</span>
        </div>
      </template>
      <div v-else-if="nodeStatus === 'completed'" class="wf-empty-hint">
        <i data-lucide="check-circle" style="width:14px; height:14px; color:#60A5FA;"></i>
        合规审核已完成（详细数据不可用）
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
  const map: Record<string, string> = { idle: '#9CA3AF', pending: '#9CA3AF', running: '#FF2442', completed: '#60A5FA', error: '#EF4444' }
  return map[props.nodeStatus] || '#9CA3AF'
})
const statusLabel = computed(() => {
  const map: Record<string, string> = { idle: '待执行', pending: '待执行', running: '执行中', completed: '已完成', error: '失败' }
  return map[props.nodeStatus] || '待执行'
})
const statusBadgeStyle = computed(() => {
  if (props.nodeStatus === 'error') return { background: '#FEE2E2', color: '#DC2626' }
  if (props.nodeStatus === 'completed') return { background: '#DBEAFE', color: '#2563EB' }
  if (props.nodeStatus === 'running') return { background: '#FEE2E2', color: '#DC2626' }
  return { background: '#F1F5F9', color: '#64748B' }
})

/** 格式化问题项 */
function formatIssueItem(issue: any): string {
  if (typeof issue === 'string') return issue
  return issue.description || issue.dimension || issue.title || '未知问题'
}

/** 获取问题严重程度 */
function getIssueSeverity(issue: any): string {
  if (typeof issue === 'string') return ''
  return issue.severity || issue.level || ''
}

function severityLabel(s: string): string {
  const map: Record<string, string> = { high: '严重', medium: '中等', low: '轻微', critical: '严重', warning: '警告', info: '提示' }
  return map[s] || s
}

/** 格式化建议项 */
function formatSuggestionItem(sug: any): string {
  if (typeof sug === 'string') return sug
  return sug.suggestion || sug.description || sug.title || ''
}

/** 审核方式中文标签 */
function auditMethodLabel(method: string): string {
  const map: Record<string, string> = {
    llm: 'LLM 审核',
    rule: '规则审核',
    fallback: '自动通过（降级）',
    unknown: '未知',
  }
  return map[method] || method
}
</script>

<style scoped>
.wf-severity-tag {
  display: inline-flex;
  align-items: center;
  padding: 1px 6px;
  border-radius: 4px;
  font-size: 14px;
  font-weight: 500;
  flex-shrink: 0;
  margin-left: 6px;
}
.wf-severity-critical,
.wf-severity-high {
  background: #FEE2E2;
  color: #DC2626;
}
.wf-severity-medium,
.wf-severity-warning {
  background: #FFFBEB;
  color: #D97706;
}
.wf-severity-low,
.wf-severity-info {
  background: #EFF6FF;
  color: #3B6CF6;
}

.wf-check-text {
  flex: 1;
  min-width: 0;
  word-break: break-word;
}
</style>