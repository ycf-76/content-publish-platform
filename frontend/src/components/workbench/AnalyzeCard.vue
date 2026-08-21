<template>
  <div class="mint-wf-card wf-node-card wf-node-analyze" id="card-analyze" :class="`wf-state-${nodeStatus}`">
    <div class="mint-wf-header">
      <div class="mint-wf-title-row">
        <div class="mint-wf-step">02</div>
        <div class="wf-node-title-block">
          <div class="mint-wf-title">
            <i data-lucide="trending-up" class="wf-node-icon"></i>
            趋势分析
            <code class="wf-node-key">analyze</code>
          </div>
          <div class="wf-node-subtitle">三层分析，提炼爆款方向</div>
        </div>
      </div>
      <span class="mint-badge wf-status-badge" :style="statusBadgeStyle">
        <span class="mint-status-dot" :style="{ background: statusColor }"></span>
        {{ statusLabel }}
      </span>
    </div>

    <div class="wf-node-summary" v-if="nodeStatus === 'completed' && result">
      发现 {{ summaryHotspots }} 个热点{{ summaryDirections ? ' · 推荐 ' + summaryDirections + ' 个方向' : '' }}
    </div>

    <div class="wf-node-body">
      <!-- idle 状态 -->
      <div v-if="nodeStatus === 'idle'" class="wf-empty-hint">
        <i data-lucide="info" style="width:14px; height:14px;"></i>
        等待搜索节点完成后自动进入分析
      </div>

      <!-- loading 状态 -->
      <div v-else-if="nodeStatus === 'running'" class="wf-analyze-loading">
        <div class="wf-analyze-loading-step" :class="{ 'is-active': currentLayer >= 1 }">
          <span class="wf-layer-tag wf-layer-tag-rule">Layer 1</span>
          <span class="wf-analyze-loading-text">规则层：派生指标 + 爆点分类</span>
          <i v-if="currentLayer >= 1" data-lucide="check" style="width:14px;height:14px;color:#10B981;"></i>
        </div>
        <div class="wf-analyze-loading-step" :class="{ 'is-active': currentLayer >= 2 }">
          <span class="wf-layer-tag wf-layer-tag-llm">Layer 2</span>
          <span class="wf-analyze-loading-text">LLM 粗分析：标题钩子 / 内容结构 / 情绪触发</span>
          <i v-if="currentLayer >= 2" data-lucide="check" style="width:14px;height:14px;color:#10B981;"></i>
        </div>
        <div class="wf-analyze-loading-step" :class="{ 'is-active': currentLayer >= 3 }">
          <span class="wf-layer-tag wf-layer-tag-deep">Layer 3</span>
          <span class="wf-analyze-loading-text">LLM 深度归因：趋势信号 + 选题建议</span>
          <i v-if="currentLayer >= 3" data-lucide="check" style="width:14px;height:14px;color:#10B981;"></i>
        </div>
        <!-- 流式输出文本区域：打字机逐字打印 + 光标 -->
        <div v-show="typedText" ref="streamBoxRef" class="wf-analyze-stream-text">
          <span>{{ typedText }}</span><span class="wf-analyze-cursor">▌</span>
        </div>
      </div>

      <!-- error 状态 -->
      <div v-else-if="nodeStatus === 'error'" class="mint-search-error">
        <i data-lucide="alert-circle" style="width:20px; height:20px;"></i>
        <span>{{ errorMessage }}</span>
      </div>

      <!-- completed 状态：结论摘要 + 三层 Tab -->
      <div v-else-if="nodeStatus === 'completed' && result" class="wf-analyze-layout">
        <div class="wf-analyze-main">
        <div class="wf-analyze-summary">
          <span class="wf-analyze-summary-primary">发现 {{ summaryHotspots }} 个热点</span>
          <span v-if="summaryDirections" class="wf-analyze-summary-secondary">推荐 {{ summaryDirections }} 个方向</span>
        </div>
        <div class="wf-analyze-tabs">
          <button
            v-for="tab in layerTabs"
            :key="tab.id"
            class="wf-analyze-tab"
            :class="{ 'is-active': activeLayer === tab.id }"
            @click="activeLayer = tab.id"
          >{{ tab.label }}</button>
        </div>
        <!-- Layer 1：规则层 -->
        <div class="wf-layer" v-show="activeLayer === 1">
          <div class="wf-layer-header">
            <span class="wf-layer-tag wf-layer-tag-rule">Layer 1 · 规则层</span>
            <span class="wf-layer-method">{{ result.layer1_stats?.classification_method || '-' }}</span>
          </div>
          <div class="wf-layer-body">
            <!-- 类型分布条 -->
            <div v-if="Object.keys(filteredTypeDistribution).length > 0" class="wf-type-distribution">
              <div
                v-for="(count, type) in filteredTypeDistribution"
                :key="type"
                class="wf-type-bar"
                :style="{ background: typeColor(type as string) }"
                :title="`${type}: ${count}`"
              >
                <span class="wf-type-bar-count">{{ count }}</span>
                <span class="wf-type-bar-label">{{ type }}</span>
              </div>
            </div>

            <!-- Top 5 爆点列表（彩色渲染，每条不同色） -->
            <div v-if="topNotes.length > 0" class="wf-trending-list">
              <div
                v-for="(note, i) in topNotes"
                :key="note.content_id || i"
                class="wf-trending-item"
                :style="{ '--rank-color': rankColor(Number(i)) }"
              >
                <div class="wf-trending-rank">Top {{ Number(i) + 1 }}</div>
                <div class="wf-trending-content">
                  <div class="wf-trending-title">{{ note.title || '无标题' }}</div>
                  <div class="wf-trending-meta">
                    <span v-if="note.platform" class="wf-trending-platform">{{ note.platform }}</span>
                    <span class="wf-trending-likes"><i data-lucide="heart" style="width:11px;height:11px;"></i>{{ note.likes || 0 }}</span>
                    <span v-if="note.comments" class="wf-trending-comments"><i data-lucide="message-circle" style="width:11px;height:11px;"></i>{{ note.comments }}</span>
                    <span v-if="note.viral_score" class="wf-trending-score">爆点分 {{ note.viral_score.toFixed(2) }}</span>
                    <span v-if="note.viral_type" class="wf-trending-type">{{ note.viral_type }}</span>
                  </div>
                </div>
              </div>
            </div>
            <div class="wf-layer-chart">
              <TrendChart :data="result" />
            </div>
          </div>
        </div>

        <!-- Layer 2：LLM 粗分析 -->
        <div class="wf-layer" v-show="activeLayer === 2">
          <div class="wf-layer-header">
            <span class="wf-layer-tag wf-layer-tag-llm">Layer 2 · LLM 模式识别</span>
            <span class="wf-layer-method">{{ result._model_used || '-' }}</span>
          </div>
          <div class="wf-layer-body">
            <div v-if="isSkipped(result.patterns)" class="wf-layer-skipped">
              <i data-lucide="minus-circle" style="width:14px;height:14px;color:#94A3B8;"></i>
              <span class="wf-layer-skipped-text">LLM 不可用，跳过 Layer 2</span>
            </div>
            <template v-else-if="result.patterns">
              <!-- 标题钩子 -->
              <div v-if="result.patterns.title_patterns?.length" class="wf-pattern-group">
                <div class="wf-pattern-label"><i data-lucide="hash" style="width:12px;height:12px;"></i>标题钩子</div>
                <div class="wf-pattern-chips">
                  <div v-for="(p, i) in result.patterns.title_patterns" :key="`tp-${i}`" class="wf-chip wf-chip-title">
                    <span class="wf-chip-type">{{ p.type }}</span>
                    <span class="wf-chip-template">{{ p.template }}</span>
                  </div>
                </div>
              </div>
              <!-- 内容结构 -->
              <div v-if="result.patterns.content_structures?.length" class="wf-pattern-group">
                <div class="wf-pattern-label"><i data-lucide="layout-list" style="width:12px;height:12px;"></i>内容结构</div>
                <div class="wf-pattern-chips">
                  <div v-for="(s, i) in result.patterns.content_structures" :key="`cs-${i}`" class="wf-chip wf-chip-structure">
                    <span class="wf-chip-main">{{ s.structure }}</span>
                    <span v-if="s.description" class="wf-chip-desc">{{ s.description }}</span>
                  </div>
                </div>
              </div>
              <!-- 情绪触发点 -->
              <div v-if="result.patterns.emotion_triggers?.length" class="wf-pattern-group">
                <div class="wf-pattern-label"><i data-lucide="zap" style="width:12px;height:12px;"></i>情绪触发点</div>
                <div class="wf-pattern-chips">
                  <div v-for="(e, i) in result.patterns.emotion_triggers" :key="`et-${i}`" class="wf-chip wf-chip-emotion">
                    <span class="wf-chip-main">{{ e.emotion }}</span>
                    <span v-if="e.reason" class="wf-chip-desc">{{ e.reason }}</span>
                  </div>
                </div>
              </div>
            </template>
          </div>
        </div>

        <!-- Layer 3：LLM 深度归因 -->
        <div class="wf-layer" v-show="activeLayer === 3">
          <div class="wf-layer-header">
            <span class="wf-layer-tag wf-layer-tag-deep">Layer 3 · LLM 深度归因</span>
            <span class="wf-layer-method">{{ result._model_used || '-' }}</span>
          </div>
          <div class="wf-layer-body">
            <div v-if="isSkipped(result.insights)" class="wf-layer-skipped">
              <i data-lucide="minus-circle" style="width:14px;height:14px;color:#94A3B8;"></i>
              <span class="wf-layer-skipped-text">LLM 不可用，跳过 Layer 3</span>
            </div>
            <template v-else-if="result.insights">
              <!-- 趋势信号 -->
              <div v-if="result.insights.trend_signals" class="wf-insight-signals">
                <div class="wf-insight-signal-row">
                  <span class="wf-insight-signal-label">话题型趋势</span>
                  <span class="wf-insight-signal-value" :class="result.insights.trend_signals.is_topic_trend ? 'is-yes' : 'is-no'">
                    {{ result.insights.trend_signals.is_topic_trend ? '是' : '否' }}
                  </span>
                </div>
                <div class="wf-insight-signal-row">
                  <span class="wf-insight-signal-label">趋势强度</span>
                  <span class="wf-insight-signal-value" :class="`strength-${strengthClass(result.insights.trend_signals.trend_strength)}`">
                    {{ result.insights.trend_signals.trend_strength || '-' }}
                  </span>
                </div>
                <div v-if="result.insights.trend_signals.trend_basis" class="wf-insight-signal-basis">
                  {{ result.insights.trend_signals.trend_basis }}
                </div>
              </div>

              <!-- 选题建议 -->
              <div v-if="result.insights.recommendations?.length" class="wf-recommendations">
                <div
                  v-for="(rec, i) in result.insights.recommendations"
                  :key="`rec-${i}`"
                  class="wf-recommendation"
                >
                  <div class="wf-recommendation-header">
                    <span class="wf-recommendation-index">#{{ Number(i) + 1 }}</span>
                    <span class="wf-recommendation-direction">{{ rec.topic_direction }}</span>
                  </div>
                  <div class="wf-recommendation-body">
                    <div v-if="rec.title_template" class="wf-recommendation-row">
                      <span class="wf-rec-label">标题模板</span>
                      <span class="wf-rec-value">{{ rec.title_template }}</span>
                    </div>
                    <div v-if="rec.content_structure" class="wf-recommendation-row">
                      <span class="wf-rec-label">内容结构</span>
                      <span class="wf-rec-value">{{ rec.content_structure }}</span>
                    </div>
                    <div v-if="rec.emotion_hook" class="wf-recommendation-row">
                      <span class="wf-rec-label">情绪钩子</span>
                      <span class="wf-rec-value">{{ rec.emotion_hook }}</span>
                    </div>
                    <div v-if="rec.reason" class="wf-recommendation-reason">
                      <i data-lucide="quote" style="width:11px;height:11px;color:#9CA3AF;"></i>
                      {{ rec.reason }}
                    </div>
                    <!-- 执行指令 -->
                    <div v-if="rec.execution_brief" class="wf-execution-brief">
                      <div class="wf-execution-brief-title">执行指令（下游节点硬约束）</div>
                      <div class="wf-execution-brief-grid">
                        <div v-if="rec.execution_brief.content_type" class="wf-brief-item">
                          <span class="wf-brief-label">内容类型</span>
                          <span class="wf-brief-value">{{ rec.execution_brief.content_type }}</span>
                        </div>
                        <div v-if="rec.execution_brief.title_style" class="wf-brief-item">
                          <span class="wf-brief-label">标题类型</span>
                          <span class="wf-brief-value">{{ rec.execution_brief.title_style }}</span>
                        </div>
                        <div v-if="rec.execution_brief.tone" class="wf-brief-item">
                          <span class="wf-brief-label">语气风格</span>
                          <span class="wf-brief-value">{{ rec.execution_brief.tone }}</span>
                        </div>
                        <div v-if="rec.execution_brief.visual_suggestion" class="wf-brief-item wf-brief-full">
                          <span class="wf-brief-label">配图风格</span>
                          <span class="wf-brief-value">{{ rec.execution_brief.visual_suggestion }}</span>
                        </div>
                        <div v-if="rec.execution_brief.recommended_structure?.length" class="wf-brief-item wf-brief-full">
                          <span class="wf-brief-label">正文结构</span>
                          <span class="wf-brief-value">{{ rec.execution_brief.recommended_structure.join(' → ') }}</span>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </template>
          </div>
        </div>
        </div>
      </div>

      <!-- completed 状态但无数据（checkpoint 丢失时二次兜底） -->
      <div v-else-if="nodeStatus === 'completed'" class="wf-empty-hint">
        <i data-lucide="check-circle" style="width:14px; height:14px; color:#60A5FA;"></i>
        分析已完成（详细数据不可用，服务重启后历史数据需重新执行查看）
      </div>

      <!-- awaiting_review 状态：analyze 完成后等待用户选方向 -->
      <div v-else-if="nodeStatus === 'awaiting_review'" class="wf-analyze-awaiting">
        <div class="wf-analyze-awaiting-hint">
          <i data-lucide="mouse-pointer-click" style="width:16px;height:16px;color:#FF2442;"></i>
          <span>分析完成，请选择创作方向后继续</span>
        </div>
        <button class="wf-continue-btn" @click="$emit('enter-copywrite')">
          <i data-lucide="arrow-right" style="width:16px;height:16px;"></i>
          开始创作
        </button>
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
import { computed, watch, nextTick, ref } from 'vue'
import { createIcons, icons } from 'lucide'
import TrendChart from './TrendChart.vue'
import { useTypewriter } from '@/composables/useTypewriter'

const props = defineProps<{
  nodeStatus: string
  nodeMeta: { duration: string; model: string; tokens: string } | null
  result: any
  currentLayer?: number
  errorMessage?: string
  /** 流式输出文本（running 状态时逐字追加） */
  streamingText?: string
}>()

// 打字机：把流式文本渲染成逐字打印效果
const streamTarget = computed(() => props.streamingText || '')
const { displayed: typedText } = useTypewriter(streamTarget)

// 流式文本自动滚动到底部（内容超出可视高度时）
const streamBoxRef = ref<HTMLElement | null>(null)
watch(typedText, () => {
  nextTick(() => {
    const el = streamBoxRef.value
    if (el) el.scrollTop = el.scrollHeight
  })
})

defineEmits<{
  'enter-copywrite': []
}>()

// 三层结果 Tab 切换（默认停在 Layer 3，也就是结论最接近的深度归因层）
const activeLayer = ref(3)
const layerTabs = [
  { id: 1, label: 'Layer 1 · 规则层' },
  { id: 2, label: 'Layer 2 · 模式识别' },
  { id: 3, label: 'Layer 3 · 深度归因' },
]

// 结论摘要：热点数量 + 推荐方向数量
const summaryHotspots = computed(() => props.result?.results?.length || 0)
const summaryDirections = computed(() => props.result?.insights?.recommendations?.length || 0)

// 重建图标（状态变化时）
watch(() => props.nodeStatus, () => nextTick(() => createIcons({ icons })))
watch(() => props.result, () => nextTick(() => createIcons({ icons })), { deep: true })

const statusColor = computed(() => {
  const map: Record<string, string> = {
    idle: '#9CA3AF',
    running: '#FF2442',
    completed: '#60A5FA',
    awaiting_review: '#FF2442',
    error: '#EF4444',
  }
  return map[props.nodeStatus] || '#9CA3AF'
})

const statusLabel = computed(() => {
  const map: Record<string, string> = {
    idle: '待执行',
    running: '执行中',
    completed: '已完成',
    awaiting_review: '请选择方向',
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

// Top 5 爆点笔记
const topNotes = computed(() => {
  if (!props.result?.results) return []
  return props.result.results.slice(0, 5)
})

// 当前执行到第几层（从 progress 事件推断，简化为：running 时显示全部进行中）
const currentLayer = computed(() => props.currentLayer || 0)

const filteredTypeDistribution = computed(() => {
  const dist = props.result?.layer1_stats?.type_distribution
  if (!dist) return {}
  const hidden = new Set(['内容型', '普通'])
  return Object.fromEntries(
    Object.entries(dist).filter(([type]) => !hidden.has(type))
  )
})

// 类型颜色
function typeColor(type: string): string {
  const map: Record<string, string> = {
    '粉丝型': '#8B5CF6',
    '互动型': '#F59E0B',
  }
  return map[type] || '#6B7280'
}

// Top 排名颜色
function rankColor(index: number): string {
  const colors = ['#EF4444', '#F97316', '#EAB308', '#6366F1', '#14B8A6']
  return colors[index] || '#6B7280'
}

// 趋势强度样式类
function strengthClass(strength?: string): string {
  if (!strength) return 'unknown'
  if (strength.includes('强')) return 'strong'
  if (strength.includes('中')) return 'medium'
  if (strength.includes('弱')) return 'weak'
  return 'unknown'
}

// 是否跳过（LLM 不可用）
function isSkipped(obj: any): boolean {
  if (!obj) return true
  return obj._skipped === 'no_llm' || obj._error !== undefined
}
</script>

<style scoped>
/* awaiting_review 创作点 */
.wf-analyze-awaiting {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
  padding: 24px 16px;
}
.wf-analyze-awaiting-hint {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  color: #666;
}
.wf-continue-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 24px;
  background: #FF2442;
  color: #fff;
  border: none;
  border-radius: 20px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.2s;
}
.wf-continue-btn:hover {
  background: #E0203A;
}

/* 左右分栏布局 */
.wf-analyze-layout {
  display: flex;
  gap: 16px;
  align-items: flex-start;
  width: 100%;
}
.wf-analyze-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.wf-analyze-side {
  flex: 0 0 320px;
  position: sticky;
  top: 12px;
  max-height: calc(100vh - 80px);
  overflow-y: auto;
}

/* 结论摘要 */
.wf-analyze-summary {
  display: flex;
  align-items: baseline;
  gap: 12px;
  flex-wrap: wrap;
}
.wf-analyze-summary-primary {
  font-size: 18px;
  font-weight: 700;
  color: #111827;
}
.wf-analyze-summary-secondary {
  font-size: 13px;
  font-weight: 500;
  color: #6B7280;
}

/* 三层 Tab 切换 */
.wf-analyze-tabs {
  display: flex;
  gap: 4px;
  padding: 4px;
  background: #F1F5F9;
  border-radius: 10px;
  width: fit-content;
}
.wf-analyze-tab {
  padding: 6px 12px;
  border: none;
  background: transparent;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 500;
  color: #64748B;
  cursor: pointer;
  transition: all 0.15s;
  font-family: inherit;
  white-space: nowrap;
}
.wf-analyze-tab:hover { color: #334155; }
.wf-analyze-tab.is-active {
  background: #FFFFFF;
  color: #111827;
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.08);
}

/* 趋势图嵌在 Layer 1 内容区 */
.wf-layer-chart {
  margin-top: 12px;
  border-top: 1px solid #EEF2FF;
  padding-top: 12px;
}

.wf-empty-hint {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 20px;
  color: #9CA3AF;
  font-size: 15px;
  justify-content: center;
}

/* loading 三层进度（Codex 风格） */
.wf-analyze-loading {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 14px 10px;
}
.wf-analyze-loading-step {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  background: linear-gradient(135deg, #F8F9FB 0%, #EEF0F4 100%);
  border-radius: 8px;
  border: 1px solid #E8EAED;
  opacity: 0.5;
  transition: all 0.3s ease;
}
.wf-analyze-loading-step.is-active {
  opacity: 1;
  border-color: #3B82F6;
  box-shadow: 0 2px 8px rgba(59,130,246,0.08);
}
.wf-analyze-loading-text {
  flex: 1;
  font-size: 13.5px;
  color: #374151;
  font-weight: 500;
}

/* Codex 风格流式输出 */
.wf-analyze-stream-text {
  margin-top: 10px;
  padding: 18px 22px;
  background: linear-gradient(135deg, #F5F5F7 0%, #EEEEEF 100%);
  border-radius: 10px;
  border: 1px solid #E2E5E9;
  font-size: 14px;
  color: #1a1a1a;
  line-height: 1.85;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 260px;
  overflow-y: auto;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  box-shadow: inset 0 1px 3px rgba(0,0,0,0.02);
}

/* Codex 风格光标：呼吸脉动（蓝色主题） */
.wf-analyze-cursor {
  display: inline-block;
  color: #3B82F6;
  font-weight: 300;
  margin-left: 1px;
  animation: analyzeCursorPulse 1s ease-in-out infinite;
}

@keyframes analyzeCursorPulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.2; }
}

.mint-search-error {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 16px;
  color: #EF4444;
  font-size: 15px;
}

/* Top 5 爆点列表：每条用不同颜色渲染（左侧色条 + 渐变背景 + 排名变色） */
.wf-trending-list {
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.wf-trending-item {
  display: flex;
  gap: 6px;
  padding: 3px 8px;
  border-radius: 4px;
  border-left: 3px solid var(--rank-color, #6B7280);
  background: color-mix(in srgb, var(--rank-color, #6B7280) 8%, #FFFFFF);
  transition: transform 0.15s, box-shadow 0.15s;
  line-height: 1.25;
}
.wf-trending-item:hover {
  transform: translateX(2px);
  box-shadow: 0 2px 8px rgba(0,0,0,0.08);
}
.wf-trending-item:nth-child(1) { --rank-color: #EF4444; }
.wf-trending-item:nth-child(2) { --rank-color: #F97316; }
.wf-trending-item:nth-child(3) { --rank-color: #EAB308; }
.wf-trending-item:nth-child(4) { --rank-color: #6366F1; }
.wf-trending-item:nth-child(5) { --rank-color: #14B8A6; }
.wf-trending-rank {
  font-size: 12px;
  font-weight: 700;
  color: var(--rank-color, #6B7280);
  flex-shrink: 0;
  width: 26px;
  line-height: 1.3;
}
.wf-trending-content {
  flex: 1;
  min-width: 0;
}
.wf-trending-title {
  font-size: 12px;
  font-weight: 500;
  color: #333333;
  line-height: 1.3;
  margin-bottom: 1px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.wf-trending-meta {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 11px;
  color: #64748B;
  flex-wrap: nowrap;
  overflow: hidden;
}
.wf-trending-platform {
  color: #3B6CF6;
  font-weight: 500;
}
.wf-trending-likes,
.wf-trending-comments {
  display: inline-flex;
  align-items: center;
  gap: 2px;
}
.wf-trending-score {
  color: #FF2442;
  font-weight: 600;
}
.wf-trending-type {
  padding: 1px 5px;
  background: #F3F4F6;
  border-radius: 3px;
  font-size: 14px;
}

/* Layer 2 模式组 */
.wf-pattern-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.wf-pattern-label {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 15px;
  font-weight: 600;
  color: #475569;
}
.wf-pattern-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.wf-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 8px;
  border-radius: 4px;
  font-size: 15px;
  line-height: 1.4;
}
.wf-chip-title {
  background: #FEF3C7;
  color: #92400E;
}
.wf-chip-structure {
  background: #DBEAFE;
  color: #1E40AF;
}
.wf-chip-emotion {
  background: #FCE7F3;
  color: #9D174D;
}
.wf-chip-type {
  font-weight: 600;
}
.wf-chip-main {
  font-weight: 500;
}
.wf-chip-desc,
.wf-chip-template {
  opacity: 0.85;
}

/* Layer 3 趋势信号 */
.wf-insight-signals {
  padding: 8px 10px;
  background: #EEF0F4;
  border-radius: 6px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.wf-insight-signal-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
}
.wf-insight-signal-label {
  color: #64748B;
  min-width: 70px;
}
.wf-insight-signal-value {
  font-weight: 600;
}
.wf-insight-signal-value.is-yes { color: #10B981; }
.wf-insight-signal-value.is-no { color: #EF4444; }
.wf-insight-signal-value.strength-strong { color: #FF2442; }
.wf-insight-signal-value.strength-medium { color: #F59E0B; }
.wf-insight-signal-value.strength-weak { color: #6B7280; }
.wf-insight-signal-value.strength-unknown { color: #6B7280; }
.wf-insight-signal-basis {
  font-size: 15px;
  color: #475569;
  line-height: 1.5;
  padding-top: 4px;
  border-top: 1px solid #E2E8F0;
}

/* Layer 3 选题建议 */
.wf-recommendations {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.wf-recommendation {
  background: #FFFFFF;
  border: 1px solid #E5E7EB;
  border-radius: 6px;
  overflow: hidden;
}
.wf-recommendation-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  background: #FFFBEB;
  border-bottom: 1px solid #FDE68A;
}
.wf-recommendation-index {
  font-size: 15px;
  font-weight: 700;
  color: #D97706;
}
.wf-recommendation-direction {
  font-size: 15px;
  font-weight: 600;
  color: #333333;
}
.wf-recommendation-body {
  padding: 8px 10px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.wf-recommendation-row {
  display: flex;
  gap: 8px;
  font-size: 14px;
  line-height: 1.5;
}
.wf-rec-label {
  color: #64748B;
  min-width: 60px;
  flex-shrink: 0;
}
.wf-rec-value {
  color: #333333;
  flex: 1;
}
.wf-recommendation-reason {
  display: flex;
  align-items: flex-start;
  gap: 4px;
  font-size: 15px;
  color: #64748B;
  font-style: italic;
  padding-top: 4px;
  border-top: 1px dashed #E5E7EB;
}

/* 执行指令 */
.wf-execution-brief {
  margin-top: 6px;
  padding: 8px;
  background: #F0F9FF;
  border: 1px solid #BAE6FD;
  border-radius: 4px;
}
.wf-execution-brief-title {
  font-size: 15px;
  font-weight: 600;
  color: #0369A1;
  margin-bottom: 6px;
}
.wf-execution-brief-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 4px 8px;
}
.wf-brief-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.wf-brief-full {
  grid-column: 1 / -1;
}
.wf-brief-label {
  font-size: 14px;
  color: #0369A1;
  font-weight: 500;
}
.wf-brief-value {
  font-size: 15px;
  color: #333333;
  line-height: 1.4;
}
</style>
