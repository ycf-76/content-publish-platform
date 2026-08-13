<template>
  <div class="wf-trend-chart">
    <div class="wf-trend-chart-header" @click="chartOpen = !chartOpen">
      <span class="wf-trend-chart-title">趋势图</span>
      <span class="wf-trend-chart-toggle" :class="{ 'is-collapsed': !chartOpen }">▾</span>
    </div>

    <div v-show="chartOpen" class="wf-trend-chart-body">
      <div v-if="!hasAnyData" class="wf-trend-chart-empty">暂无数据</div>

      <template v-else>
        <!-- 爆点分趋势 -->
        <div v-if="hasNotesData" class="wf-trend-section">
          <div class="wf-trend-section-label">
            <span class="wf-trend-dot-indicator" style="background:#FF2442;"></span>
            爆点分趋势
          </div>
          <div class="wf-trend-chart-canvas" ref="viralCanvasRef">
            <svg :viewBox="`0 0 ${svgW} ${svgH}`" class="wf-trend-svg" preserveAspectRatio="xMidYMid meet">
              <defs>
                <linearGradient id="grad-viral" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stop-color="#FF2442" stop-opacity="0.3" />
                  <stop offset="100%" stop-color="#FF2442" stop-opacity="0.02" />
                </linearGradient>
              </defs>
              <g class="wf-trend-grid">
                <line v-for="i in gridLines" :key="'vg-' + i" x1="0" :y1="i * gridStep" :x2="svgW" :y2="i * gridStep" stroke="#F0F0F0" stroke-width="1" />
              </g>
              <g class="wf-trend-y-labels">
                <text v-for="(label, i) in viralYLabels" :key="'vyl-' + i" x="-4" :y="i * gridStep + 4" text-anchor="end" fill="#9CA3AF" font-size="10">{{ label }}</text>
              </g>
              <path v-if="viralAreaPath" :d="viralAreaPath" fill="url(#grad-viral)" class="wf-trend-area" />
              <path v-if="viralLinePath" :d="viralLinePath" fill="none" stroke="#FF2442" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" class="wf-trend-line" />
              <g class="wf-trend-dots">
                <circle v-for="(pt, i) in viralPoints" :key="'vd-' + i" :cx="pt.x" :cy="pt.y" r="4" fill="#FF2442" stroke="#fff" stroke-width="2" class="wf-trend-dot" :style="{ animationDelay: `${i * 80}ms` }" />
              </g>
              <g class="wf-trend-x-labels">
                <text v-for="(pt, i) in viralPoints" :key="'vxl-' + i" :x="pt.x" :y="svgH + 14" text-anchor="middle" fill="#9CA3AF" font-size="10">{{ pt.label }}</text>
              </g>
            </svg>
          </div>
        </div>

        <!-- 互动量趋势 -->
        <div v-if="hasNotesData" class="wf-trend-section">
          <div class="wf-trend-section-label">
            <span class="wf-trend-dot-indicator" style="background:#6366F1;"></span>
            互动量趋势
          </div>
          <div class="wf-trend-chart-canvas" ref="engCanvasRef">
            <svg :viewBox="`0 0 ${svgW} ${svgH}`" class="wf-trend-svg" preserveAspectRatio="xMidYMid meet">
              <defs>
                <linearGradient id="grad-eng" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stop-color="#6366F1" stop-opacity="0.3" />
                  <stop offset="100%" stop-color="#6366F1" stop-opacity="0.02" />
                </linearGradient>
              </defs>
              <g class="wf-trend-grid">
                <line v-for="i in gridLines" :key="'eg-' + i" x1="0" :y1="i * gridStep" :x2="svgW" :y2="i * gridStep" stroke="#F0F0F0" stroke-width="1" />
              </g>
              <g class="wf-trend-y-labels">
                <text v-for="(label, i) in engYLabels" :key="'eyl-' + i" x="-4" :y="i * gridStep + 4" text-anchor="end" fill="#9CA3AF" font-size="10">{{ label }}</text>
              </g>
              <path v-if="engAreaPath" :d="engAreaPath" fill="url(#grad-eng)" class="wf-trend-area" />
              <path v-if="engLinePath" :d="engLinePath" fill="none" stroke="#6366F1" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" class="wf-trend-line" />
              <g class="wf-trend-dots">
                <circle v-for="(pt, i) in engPoints" :key="'ed-' + i" :cx="pt.x" :cy="pt.y" r="4" fill="#6366F1" stroke="#fff" stroke-width="2" class="wf-trend-dot" :style="{ animationDelay: `${i * 80}ms` }" />
              </g>
              <g class="wf-trend-x-labels">
                <text v-for="(pt, i) in engPoints" :key="'exl-' + i" :x="pt.x" :y="svgH + 14" text-anchor="middle" fill="#9CA3AF" font-size="10">{{ pt.label }}</text>
              </g>
            </svg>
          </div>
        </div>

        <!-- 类型分布 -->
        <div v-if="hasDistData" class="wf-trend-section">
          <div class="wf-trend-section-label">
            <span class="wf-trend-dot-indicator" style="background:#F59E0B;"></span>
            类型分布
          </div>
          <div class="wf-trend-dist-bars">
            <div v-for="(item, i) in distBars" :key="'db-' + i" class="wf-trend-dist-row">
              <span class="wf-trend-dist-label">{{ item.label }}</span>
              <div class="wf-trend-dist-track">
                <div class="wf-trend-dist-fill" :style="{ width: item.pct + '%', background: item.color, animationDelay: `${i * 120}ms` }"></div>
              </div>
              <span class="wf-trend-dist-count">{{ item.count }}</span>
            </div>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted } from 'vue'

interface TrendData {
  results?: any[]
  layer1_stats?: {
    total?: number
    type_distribution?: Record<string, number>
    signal_distribution?: Record<string, number>
    top_viral_score?: number
    classification_method?: string
  }
  insights?: {
    trend_signals?: {
      is_topic_trend?: boolean
      trend_strength?: string
      trend_basis?: string
    }
  }
}

const props = defineProps<{
  data: TrendData | null | undefined
}>()

const chartOpen = ref(true)
const viralCanvasRef = ref<HTMLElement | null>(null)
const engCanvasRef = ref<HTMLElement | null>(null)

const svgW = 280
const svgH = 140
const padTop = 10
const padBottom = 20
const chartH = svgH - padTop - padBottom
const gridLines = 4
const gridStep = chartH / gridLines

const hasNotesData = computed(() => (props.data?.results || []).length > 0)
const hasDistData = computed(() => Object.keys(props.data?.layer1_stats?.type_distribution || {}).length > 0)
const hasAnyData = computed(() => hasNotesData.value || hasDistData.value)

const topNotes = computed(() => (props.data?.results || []).slice(0, 8))

function buildChartValues(notes: any[], mode: 'viral' | 'engagement') {
  if (!notes.length) return []
  return notes.map((n: any, i: number) => ({
    label: `#${i + 1}`,
    value: mode === 'viral'
      ? (n.viral_score || 0)
      : (n.likes || 0) + (n.comments || 0),
    raw: n,
  }))
}

function buildYLabels(maxVal: number) {
  const labels: string[] = []
  for (let i = gridLines; i >= 0; i--) {
    const v = (maxVal * i) / gridLines
    labels.push(v >= 1000 ? (v / 1000).toFixed(1) + 'k' : v.toFixed(v < 10 ? 2 : 0))
  }
  return labels
}

interface ChartPoint { x: number; y: number; label: string; value: number; raw: any }

function buildPoints(vals: { label: string; value: number; raw: any }[], maxVal: number): ChartPoint[] {
  if (!vals.length) return []
  const mx = maxVal || 1
  const step = vals.length > 1 ? svgW / (vals.length - 1) : svgW / 2
  return vals.map((v, i) => ({
    x: vals.length > 1 ? i * step : svgW / 2,
    y: padTop + chartH - (v.value / mx) * chartH,
    label: v.label,
    value: v.value,
    raw: v.raw,
  }))
}

function buildLinePath(pts: ChartPoint[]) {
  if (pts.length < 2) return pts.length === 1 ? `M${pts[0].x},${pts[0].y}` : ''
  let d = `M${pts[0].x},${pts[0].y}`
  for (let i = 1; i < pts.length; i++) {
    const prev = pts[i - 1]
    const curr = pts[i]
    const cpx1 = prev.x + (curr.x - prev.x) * 0.4
    const cpx2 = prev.x + (curr.x - prev.x) * 0.6
    d += ` C${cpx1},${prev.y} ${cpx2},${curr.y} ${curr.x},${curr.y}`
  }
  return d
}

function buildAreaPath(line: string, pts: ChartPoint[]) {
  if (!line || !pts.length) return ''
  const last = pts[pts.length - 1]
  const first = pts[0]
  return `${line} L${last.x},${svgH - padBottom} L${first.x},${svgH - padBottom} Z`
}

const viralValues = computed(() => buildChartValues(topNotes.value, 'viral'))
const viralMax = computed(() => {
  const vals = viralValues.value.map(v => v.value)
  return vals.length ? Math.max(...vals) : 1
})
const viralYLabels = computed(() => buildYLabels(viralMax.value))
const viralPoints = computed(() => buildPoints(viralValues.value, viralMax.value))
const viralLinePath = computed(() => buildLinePath(viralPoints.value))
const viralAreaPath = computed(() => buildAreaPath(viralLinePath.value, viralPoints.value))

const engValues = computed(() => buildChartValues(topNotes.value, 'engagement'))
const engMax = computed(() => {
  const vals = engValues.value.map(v => v.value)
  return vals.length ? Math.max(...vals) : 1
})
const engYLabels = computed(() => buildYLabels(engMax.value))
const engPoints = computed(() => buildPoints(engValues.value, engMax.value))
const engLinePath = computed(() => buildLinePath(engPoints.value))
const engAreaPath = computed(() => buildAreaPath(engLinePath.value, engPoints.value))

const distBars = computed(() => {
  const dist = props.data?.layer1_stats?.type_distribution || {}
  const colorMap: Record<string, string> = {
    '内容型': '#FF2442',
    '粉丝型': '#8B5CF6',
    '互动型': '#F59E0B',
    '双重型': '#10B981',
    '普通': '#9CA3AF',
  }
  const entries = Object.entries(dist)
  const maxCount = Math.max(...entries.map(([, c]) => c), 1)
  return entries.map(([label, count]) => ({
    label,
    count,
    pct: (count / maxCount) * 100,
    color: colorMap[label] || '#6B7280',
  }))
})

function animateIn() {
  const refs = [viralCanvasRef.value, engCanvasRef.value].filter(Boolean) as HTMLElement[]
  refs.forEach(el => {
    el.classList.remove('wf-trend-animate')
    void el.offsetWidth
    el.classList.add('wf-trend-animate')
  })
}

onMounted(() => {
  if (hasAnyData.value) nextTick(() => animateIn())
})

watch(() => props.data, () => {
  if (hasAnyData.value) nextTick(() => animateIn())
}, { deep: true })
</script>

<style scoped>
.wf-trend-chart {
  display: flex;
  flex-direction: column;
  background: #fff;
  border-radius: 8px;
  overflow: hidden;
}
.wf-trend-chart-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  cursor: pointer;
  user-select: none;
  border-bottom: 1px solid #F0F0F0;
}
.wf-trend-chart-title {
  font-size: 15px;
  font-weight: 600;
  color: #9CA3AF;
}
.wf-trend-chart-toggle {
  font-size: 16px;
  color: #9CA3AF;
  transition: transform 0.2s;
  line-height: 1;
}
.wf-trend-chart-toggle.is-collapsed {
  transform: rotate(-90deg);
}
.wf-trend-chart-body {
  padding: 10px 12px 8px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.wf-trend-chart-empty {
  text-align: center;
  color: #9CA3AF;
  font-size: 14px;
  padding: 20px 0;
}

.wf-trend-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.wf-trend-section-label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 600;
  color: #475569;
}
.wf-trend-dot-indicator {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.wf-trend-chart-canvas {
  position: relative;
  overflow: hidden;
}
.wf-trend-svg {
  display: block;
  width: 100%;
  height: auto;
}

.wf-trend-line {
  stroke-dasharray: 1000;
  stroke-dashoffset: 1000;
  animation: wf-draw-line 1.2s ease-out forwards;
}
.wf-trend-area {
  opacity: 0;
  animation: wf-fade-in 0.6s ease-out 0.8s forwards;
}
.wf-trend-dot {
  opacity: 0;
  transform-origin: center;
  animation: wf-pop-in 0.35s cubic-bezier(0.34, 1.56, 0.64, 1) forwards;
}
.wf-trend-animate .wf-trend-line {
  stroke-dasharray: 1000;
  stroke-dashoffset: 1000;
  animation: wf-draw-line 1.2s ease-out forwards;
}
.wf-trend-animate .wf-trend-area {
  opacity: 0;
  animation: wf-fade-in 0.6s ease-out 0.8s forwards;
}
.wf-trend-animate .wf-trend-dot {
  opacity: 0;
  animation: wf-pop-in 0.35s cubic-bezier(0.34, 1.56, 0.64, 1) forwards;
}

@keyframes wf-draw-line {
  to { stroke-dashoffset: 0; }
}
@keyframes wf-fade-in {
  to { opacity: 1; }
}
@keyframes wf-pop-in {
  0% { opacity: 0; transform: scale(0); }
  100% { opacity: 1; transform: scale(1); }
}

.wf-trend-dist-bars {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.wf-trend-dist-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.wf-trend-dist-label {
  font-size: 13px;
  color: #475569;
  min-width: 48px;
  text-align: right;
}
.wf-trend-dist-track {
  flex: 1;
  height: 18px;
  background: #F3F4F6;
  border-radius: 9px;
  overflow: hidden;
}
.wf-trend-dist-fill {
  height: 100%;
  border-radius: 9px;
  transform-origin: left;
  animation: wf-bar-grow 0.7s cubic-bezier(0.22, 1, 0.36, 1) forwards;
  transform: scaleX(0);
}
@keyframes wf-bar-grow {
  to { transform: scaleX(1); }
}
.wf-trend-dist-count {
  font-size: 13px;
  color: #6B7280;
  font-weight: 600;
  min-width: 24px;
}
</style>