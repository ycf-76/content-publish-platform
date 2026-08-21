/**
 * 单张卡片渲染组件
 * 接收 page + theme + decoration，渲染出 1080×1440 的卡片 DOM
 * 4 种 page type 各有独立布局
 * 装饰层渲染在背景上方、文字下方（z-index 分层）
 */
<script setup lang="ts">
import { computed } from 'vue'
import type { CardPage, TemplateTheme, DecorationConfig } from '../card-editor/templates'
import { createDefaultDecoration } from '../card-editor/templates'

const props = defineProps<{
  page: CardPage
  theme: TemplateTheme
  decoration?: DecorationConfig
}>()

const deco = computed(() => props.decoration || createDefaultDecoration())

/** 自适应字号：根据当前页全部文本长度动态调整基准字号
 *  - 内容少（< 50 字）→ 放大 1.15x
 *  - 内容适中（50-150 字）→ 保持 1.0x
 *  - 内容多（150-300 字）→ 缩小 0.82x
 *  - 内容极多（> 300 字）→ 缩小 0.65x
 */
const adaptiveFontSize = computed(() => {
  const p = props.page
  const parts: string[] = [
    p.title || '', p.subtitle || '', p.content || '', p.footer || '',
    ...(p.listItems || []),
    ...(p.compareLeftItems || []),
    ...(p.compareRightItems || []),
    ...(p.steps || []).map(s => s.title + s.desc),
    ...(p.numberedItems || []).map(n => n.title + n.desc),
    ...(p.iconTextPairs || []).map(ip => ip.text),
    ...(p.newspaperCols || []).map(c => c.headline + c.body),
  ]
  const len = parts.join('').length
  let scale = 1.0
  if (len < 50) scale = 1.15
  else if (len < 150) scale = 1.0
  else if (len < 300) scale = 0.82
  else scale = 0.65
  return Math.round(props.theme.fontSize * scale)
})

/** CSS 变量对象，绑定到卡片根元素 */
const cssVars = computed(() => ({
  '--card-bg': props.theme.bg,
  '--card-surface': props.theme.surface,
  '--card-text': props.theme.text,
  '--card-subtext': props.theme.subtext,
  '--card-accent': props.theme.accent,
  '--card-accent-soft': props.theme.accentSoft,
  '--card-font-size': `${adaptiveFontSize.value}px`,
  '--card-font-family': props.theme.fontFamily,
}))

/** 正文按换行符分段 */
const contentParagraphs = computed(() => {
  return (props.page.content || '').split('\n').filter(p => p.trim())
})

/** 生成波浪 SVG 路径（正弦曲线填充区域） */
function wavePath(index: number): string {
  const amplitude = deco.value.param2 ?? 40
  const totalWaves = Math.round(deco.value.param1 ?? 3)
  const yBase = (1440 / (totalWaves + 1)) * index
  const points: string[] = []
  const steps = 40
  for (let s = 0; s <= steps; s++) {
    const x = (1080 / steps) * s
    const y = yBase + Math.sin((s / steps) * Math.PI * 2 + index * 0.8) * amplitude
    points.push(`${s === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`)
  }
  points.push(`L1080,1440 L0,1440 Z`)
  return points.join(' ')
}
</script>

<template>
  <div class="card-canvas" :style="cssVars">
    <!-- 装饰层：背景上方、文字下方 -->
    <div v-if="deco.type !== 'none'" class="card-decoration" :style="{ opacity: deco.opacity }">

      <!-- 渐变光斑：两个模糊圆形 -->
      <template v-if="deco.type === 'gradient_orbs'">
        <div class="deco-orb deco-orb-1" :style="{
          background: `radial-gradient(circle, ${deco.color1} 0%, transparent 70%)`,
          left: `${(deco.param1 ?? 0.25) * 100}%`,
          top: '20%',
        }"></div>
        <div class="deco-orb deco-orb-2" :style="{
          background: `radial-gradient(circle, ${deco.color2} 0%, transparent 70%)`,
          left: `${(deco.param2 ?? 0.65) * 100}%`,
          top: '55%',
        }"></div>
      </template>

      <!-- 网格线：SVG 细线 -->
      <svg v-else-if="deco.type === 'grid_lines'" class="deco-svg" xmlns="http://www.w3.org/2000/svg">
        <defs>
          <pattern id="grid-pattern" :width="deco.param1 ?? 80" :height="deco.param1 ?? 80" patternUnits="userSpaceOnUse">
            <path :d="`M ${(deco.param1 ?? 80)} 0 L 0 0 0 ${(deco.param1 ?? 80)}`" fill="none" :stroke="deco.color1" :stroke-width="deco.param2 ?? 1"/>
          </pattern>
        </defs>
        <rect width="100%" height="100%" fill="url(#grid-pattern)" />
      </svg>

      <!-- 波点：SVG 圆点阵列 -->
      <svg v-else-if="deco.type === 'dots'" class="deco-svg" xmlns="http://www.w3.org/2000/svg">
        <defs>
          <pattern id="dots-pattern" :width="deco.param1 ?? 48" :height="deco.param1 ?? 48" patternUnits="userSpaceOnUse">
            <circle :cx="(deco.param1 ?? 48) / 2" :cy="(deco.param1 ?? 48) / 2" :r="deco.param2 ?? 6" :fill="deco.color1"/>
          </pattern>
        </defs>
        <rect width="100%" height="100%" fill="url(#dots-pattern)" />
      </svg>

      <!-- 波浪：SVG 曲线 -->
      <svg v-else-if="deco.type === 'wave'" class="deco-svg" xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="none">
        <template v-for="i in Math.round(deco.param1 ?? 3)" :key="i">
          <path
            :d="wavePath(i)"
            :fill="i % 2 === 1 ? deco.color1 : deco.color2"
            fill-opacity="0.6"
          />
        </template>
      </svg>

      <!-- 噪点纹理：CSS filter + 伪随机背景 -->
      <div v-else-if="deco.type === 'noise'" class="deco-noise" :style="{
        filter: `contrast(${(deco.param1 ?? 0.5) * 2}) brightness(1.5)`,
        backgroundSize: `${Math.max(1, Math.round(4 / (deco.param2 ?? 1)))}px ${Math.max(1, Math.round(4 / (deco.param2 ?? 1)))}px`,
        '--noise-c1': deco.color1,
        '--noise-c2': deco.color2,
      }"></div>

      <!-- 几何色块：大圆弧或三角形 -->
      <svg v-else-if="deco.type === 'geometric'" class="deco-svg" xmlns="http://www.w3.org/2000/svg">
        <template v-if="(deco.param2 ?? 30) >= 0">
          <circle cx="1080" cy="0" :r="1080 * (deco.param1 ?? 0.8)" :fill="deco.color1" fill-opacity="0.5"/>
          <circle cx="0" cy="1440" :r="1080 * (deco.param1 ?? 0.8) * 0.6" :fill="deco.color2" fill-opacity="0.4"/>
        </template>
        <template v-else>
          <polygon :points="`0,0 ${1080 * (deco.param1 ?? 0.6)},0 0,${1440 * (deco.param1 ?? 0.6)}`" :fill="deco.color1" fill-opacity="0.5"/>
          <polygon :points="`1080,1440 ${1080 * (1 - (deco.param1 ?? 0.6))},1440 1080,${1440 * (1 - (deco.param1 ?? 0.6))}`" :fill="deco.color2" fill-opacity="0.4"/>
        </template>
      </svg>

    </div>

    <!-- 封面页：大标题 + 副标题 + 底部署名 -->
    <div v-if="page.type === 'cover'" class="card-layout card-cover">
      <div class="cover-top-bar"></div>
      <div class="cover-body">
        <div class="cover-tag">笔记 · {{ page.subtitle ? 'NO.01' : '精选' }}</div>
        <h1 class="cover-title">{{ page.title }}</h1>
        <p v-if="page.subtitle" class="cover-subtitle">{{ page.subtitle }}</p>
      </div>
      <div class="cover-footer">
        <span class="cover-footer-text">{{ page.footer }}</span>
      </div>
    </div>

    <!-- 正文页：标题 + 段落 -->
    <div v-else-if="page.type === 'content'" class="card-layout card-content">
      <div class="content-header">
        <span class="content-accent-line"></span>
        <h2 class="content-title">{{ page.title }}</h2>
      </div>
      <div class="content-body">
        <p v-for="(p, i) in contentParagraphs" :key="i" class="content-paragraph">{{ p }}</p>
      </div>
      <div v-if="page.footer" class="content-footer">{{ page.footer }}</div>
    </div>

    <!-- 金句页：大字居中 + 引号装饰 -->
    <div v-else-if="page.type === 'quote'" class="card-layout card-quote">
      <div class="quote-mark quote-mark-top">"</div>
      <div class="quote-body">
        <p class="quote-text">{{ page.content }}</p>
      </div>
      <div class="quote-mark quote-mark-bottom">"</div>
      <div v-if="page.footer" class="quote-footer">{{ page.footer }}</div>
    </div>

    <!-- 清单页：标题 + 编号列表 -->
    <div v-else-if="page.type === 'list'" class="card-layout card-list">
      <div class="list-header">
        <h2 class="list-title">{{ page.title }}</h2>
        <span class="list-count">{{ page.listItems?.length || 0 }} 项</span>
      </div>
      <ul class="list-body">
        <li v-for="(item, i) in page.listItems" :key="i" class="list-item">
          <span class="list-item-num">{{ String(i + 1).padStart(2, '0') }}</span>
          <span class="list-item-text">{{ item }}</span>
        </li>
      </ul>
      <div v-if="page.footer" class="list-footer">{{ page.footer }}</div>
    </div>

    <!-- 深色面板页：暗底亮字 + emoji + 关键洞察 -->
    <div v-else-if="page.type === 'dark_panel'" class="card-layout card-dark-panel">
      <div class="dark-panel-header">
        <span class="dark-panel-emoji">{{ page.emoji || '💡' }}</span>
        <span class="dark-panel-num">{{ page.decoNumber || '01' }}</span>
      </div>
      <h2 v-if="page.title" class="dark-panel-title">{{ page.title }}</h2>
      <ul class="dark-panel-list">
        <li v-for="(item, i) in page.listItems" :key="i" class="dark-panel-item">{{ item }}</li>
      </ul>
      <p v-if="page.content" class="dark-panel-content">{{ page.content }}</p>
    </div>

    <!-- 对比页：左 vs 右 -->
    <div v-else-if="page.type === 'compare'" class="card-layout card-compare">
      <h2 v-if="page.title" class="compare-title">{{ page.title }}</h2>
      <div class="compare-body">
        <div class="compare-col compare-left">
          <h3 class="compare-col-title">{{ page.compareLeftTitle || '问题' }}</h3>
          <ul class="compare-col-list">
            <li v-for="(item, i) in page.compareLeftItems" :key="i">{{ item }}</li>
          </ul>
        </div>
        <div class="compare-divider">VS</div>
        <div class="compare-col compare-right">
          <h3 class="compare-col-title">{{ page.compareRightTitle || '解法' }}</h3>
          <ul class="compare-col-list">
            <li v-for="(item, i) in page.compareRightItems" :key="i">{{ item }}</li>
          </ul>
        </div>
      </div>
    </div>

    <!-- 图标文字页：emoji + 文字对 -->
    <div v-else-if="page.type === 'icon_text'" class="card-layout card-icon-text">
      <h2 v-if="page.title" class="icon-text-title">{{ page.title }}</h2>
      <div class="icon-text-grid">
        <div v-for="(pair, i) in page.iconTextPairs" :key="i" class="icon-text-pair">
          <span class="icon-text-icon">{{ pair.icon }}</span>
          <span class="icon-text-desc">{{ pair.text }}</span>
        </div>
      </div>
    </div>

    <!-- 步骤流程页 -->
    <div v-else-if="page.type === 'steps'" class="card-layout card-steps">
      <div class="steps-header">
        <span class="steps-num">{{ page.decoNumber || '01' }}</span>
        <h2 class="steps-title">{{ page.title || '操作步骤' }}</h2>
      </div>
      <div class="steps-body">
        <div v-for="(step, i) in page.steps" :key="i" class="step-item">
          <div class="step-marker">{{ i + 1 }}</div>
          <div class="step-content">
            <h3 class="step-title">{{ step.title }}</h3>
            <p class="step-desc">{{ step.desc }}</p>
          </div>
        </div>
      </div>
    </div>

    <!-- 编号卡片页 -->
    <div v-else-if="page.type === 'numbered_cards'" class="card-layout card-numcards">
      <div class="numcards-header">
        <span class="numcards-num">{{ page.decoNumber || '02' }}</span>
        <h2 class="numcards-title">{{ page.title || '核心要点' }}</h2>
      </div>
      <div class="numcards-body">
        <div v-for="(item, i) in page.numberedItems" :key="i" class="numcard-item">
          <span class="numcard-marker">{{ String(i + 1).padStart(2, '0') }}</span>
          <div class="numcard-content">
            <h3 class="numcard-title">{{ item.title }}</h3>
            <p class="numcard-desc">{{ item.desc }}</p>
          </div>
        </div>
      </div>
    </div>

    <!-- 报纸多栏页 -->
    <div v-else-if="page.type === 'newspaper'" class="card-layout card-newspaper">
      <div class="newspaper-masthead">{{ page.masthead || 'THE DAILY BRIEF' }}</div>
      <div class="newspaper-cols">
        <div v-for="(col, i) in page.newspaperCols" :key="i" class="newspaper-col">
          <h3 class="newspaper-headline">{{ col.headline }}</h3>
          <p class="newspaper-body">{{ col.body }}</p>
        </div>
      </div>
    </div>

    <!-- 大字金句页 -->
    <div v-else-if="page.type === 'big_quote'" class="card-layout card-bigquote">
      <div class="bigquote-mark">{{ page.decoNumber || '"' }}</div>
      <p class="bigquote-text">{{ page.content }}</p>
      <div v-if="page.footer" class="bigquote-footer">{{ page.footer }}</div>
    </div>

    <!-- 尾页 -->
    <div v-else-if="page.type === 'end_page'" class="card-layout card-end">
      <div class="end-body">
        <div class="end-mark">{{ page.decoNumber || '"' }}</div>
        <p class="end-content">{{ page.content }}</p>
      </div>
      <div class="end-footer-area">
        <span v-if="page.ctaText" class="end-cta">{{ page.ctaText }}</span>
        <span class="end-footer">{{ page.footer || '@灵犀工坊' }}</span>
      </div>
    </div>

    <!-- 代码面板页（兜底） -->
    <div v-else-if="page.type === 'code_panel'" class="card-layout card-code">
      <h2 v-if="page.title" class="code-title">{{ page.title }}</h2>
      <pre class="code-block"><code>{{ page.codeContent }}</code></pre>
    </div>
  </div>
</template>

<style scoped>
/* 画布固定 1080×1440，预览时由父组件 scale 缩小 */
.card-canvas {
  width: 1080px;
  height: 1440px;
  background: var(--card-bg);
  color: var(--card-text);
  font-family: var(--card-font-family);
  font-size: var(--card-font-size);
  position: relative;
  overflow: hidden;
  box-sizing: border-box;
  -webkit-font-smoothing: antialiased;
}

/* ===== 装饰层 ===== */
.card-decoration {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  z-index: 1;
  pointer-events: none;
  overflow: hidden;
}
/* 文字层 z-index=2，确保装饰不遮挡文字 */
.card-layout {
  position: relative;
  z-index: 2;
}

/* 渐变光斑 */
.deco-orb {
  position: absolute;
  width: 70%;
  height: 50%;
  border-radius: 50%;
  filter: blur(80px);
  transform: translate(-50%, -50%);
}
.deco-orb-1 { width: 65%; height: 45%; }
.deco-orb-2 { width: 55%; height: 40%; }

/* SVG 装饰通用 */
.deco-svg {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
}

/* 噪点纹理：用 repeating-conic-gradient 模拟随机噪点 */
.deco-noise {
  position: absolute;
  top: -50%;
  left: -50%;
  width: 200%;
  height: 200%;
  background:
    repeating-conic-gradient(
      var(--noise-c1) 0%,
      var(--noise-c2) 0.5%,
      transparent 1%
    );
  mix-blend-mode: multiply;
}

.card-layout {
  width: 100%;
  height: 100%;
  padding: 72px 64px;
  display: flex;
  flex-direction: column;
  box-sizing: border-box;
  overflow: hidden;
}

/* ===== 封面页 ===== */
.card-cover {
  justify-content: space-between;
}
.cover-top-bar {
  width: 100px;
  height: 6px;
  background: var(--card-accent);
  border-radius: 3px;
  flex-shrink: 0;
}
.cover-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: flex-start;
  gap: 24px;
}
.cover-tag {
  font-size: calc(var(--card-font-size) * 0.45);
  color: var(--card-accent);
  letter-spacing: 3px;
  font-weight: 600;
}
.cover-title {
  font-size: calc(var(--card-font-size) * 1.6);
  font-weight: 700;
  line-height: 1.35;
  color: var(--card-text);
  margin: 0;
  word-break: break-word;
}
.cover-subtitle {
  font-size: calc(var(--card-font-size) * 0.65);
  color: var(--card-subtext);
  line-height: 1.5;
  margin: 0;
}
.cover-footer {
  padding-top: 20px;
  border-top: 2px solid var(--card-surface);
  flex-shrink: 0;
}
.cover-footer-text {
  font-size: calc(var(--card-font-size) * 0.45);
  color: var(--card-subtext);
}

/* ===== 正文页 ===== */
.card-content {
  justify-content: space-evenly;
  gap: 0;
}
.content-header {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-shrink: 0;
}
.content-accent-line {
  width: 6px;
  height: 40px;
  background: var(--card-accent);
  border-radius: 3px;
  flex-shrink: 0;
}
.content-title {
  font-size: calc(var(--card-font-size) * 1.15);
  font-weight: 700;
  color: var(--card-text);
  margin: 0;
  line-height: 1.4;
}
.content-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 24px;
  overflow: hidden;
}
.content-paragraph {
  font-size: var(--card-font-size);
  line-height: 1.7;
  color: var(--card-text);
  margin: 0;
  word-break: break-word;
}
.content-footer {
  font-size: calc(var(--card-font-size) * 0.45);
  color: var(--card-subtext);
  padding-top: 16px;
  border-top: 2px solid var(--card-surface);
  flex-shrink: 0;
}

/* ===== 金句页 ===== */
.card-quote {
  justify-content: center;
  align-items: center;
  text-align: center;
  position: relative;
}
.quote-mark {
  font-size: 160px;
  color: var(--card-accent-soft);
  font-family: Georgia, serif;
  line-height: 1;
  user-select: none;
}
.quote-mark-top {
  align-self: flex-start;
  margin-bottom: -32px;
}
.quote-mark-bottom {
  align-self: flex-end;
  margin-top: -32px;
}
.quote-body {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0 32px;
}
.quote-text {
  font-size: calc(var(--card-font-size) * 1.3);
  font-weight: 600;
  line-height: 1.6;
  color: var(--card-text);
  margin: 0;
  word-break: break-word;
}
.quote-footer {
  font-size: calc(var(--card-font-size) * 0.45);
  color: var(--card-subtext);
  margin-top: 32px;
}

/* ===== 清单页 ===== */
.card-list {
  gap: 0;
}
.list-header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  padding-bottom: 20px;
  border-bottom: 3px solid var(--card-accent);
  flex-shrink: 0;
}
.list-title {
  font-size: calc(var(--card-font-size) * 1.15);
  font-weight: 700;
  color: var(--card-text);
  margin: 0;
}
.list-count {
  font-size: calc(var(--card-font-size) * 0.45);
  color: var(--card-subtext);
}
.list-body {
  flex: 1;
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  justify-content: space-evenly;
  overflow: hidden;
}
.list-item {
  display: flex;
  align-items: flex-start;
  gap: 16px;
}
.list-item-num {
  font-size: calc(var(--card-font-size) * 0.65);
  font-weight: 700;
  color: var(--card-accent);
  flex-shrink: 0;
  min-width: 40px;
}
.list-item-text {
  font-size: var(--card-font-size);
  line-height: 1.6;
  color: var(--card-text);
  word-break: break-word;
}
.list-footer {
  font-size: calc(var(--card-font-size) * 0.45);
  color: var(--card-subtext);
  padding-top: 16px;
  border-top: 2px solid var(--card-surface);
  flex-shrink: 0;
}

/* ===== 深色面板页 ===== */
.card-dark-panel {
  justify-content: space-evenly;
  gap: 0;
}
.dark-panel-header {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-shrink: 0;
}
.dark-panel-emoji {
  font-size: calc(var(--card-font-size) * 1.6);
}
.dark-panel-num {
  font-size: calc(var(--card-font-size) * 0.7);
  color: var(--card-accent);
  font-weight: 700;
  letter-spacing: 2px;
}
.dark-panel-title {
  font-size: calc(var(--card-font-size) * 1.15);
  font-weight: 700;
  color: var(--card-text);
  margin: 0;
  flex-shrink: 0;
}
.dark-panel-list {
  flex: 1;
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  justify-content: space-evenly;
  overflow: hidden;
}
.dark-panel-item {
  font-size: var(--card-font-size);
  line-height: 1.6;
  color: var(--card-text);
  word-break: break-word;
  padding-left: 24px;
  position: relative;
}
.dark-panel-item::before {
  content: '→';
  position: absolute;
  left: 0;
  color: var(--card-accent);
  font-weight: 700;
}
.dark-panel-content {
  font-size: var(--card-font-size);
  line-height: 1.6;
  color: var(--card-text);
  word-break: break-word;
}

/* ===== 对比页 ===== */
.card-compare {
  gap: 0;
}
.compare-title {
  font-size: calc(var(--card-font-size) * 1.15);
  font-weight: 700;
  color: var(--card-text);
  margin: 0;
  text-align: center;
  flex-shrink: 0;
}
.compare-body {
  flex: 1;
  display: flex;
  gap: 24px;
  align-items: stretch;
  overflow: hidden;
}
.compare-col {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: space-evenly;
  gap: 0;
}
.compare-col-title {
  font-size: calc(var(--card-font-size) * 0.85);
  font-weight: 700;
  margin: 0;
  padding-bottom: 12px;
  border-bottom: 2px solid var(--card-accent);
  flex-shrink: 0;
}
.compare-left .compare-col-title { color: #EF4444; }
.compare-right .compare-col-title { color: #10B981; }
.compare-col-list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.compare-col-list li {
  font-size: calc(var(--card-font-size) * 0.85);
  line-height: 1.5;
  color: var(--card-text);
  word-break: break-word;
}
.compare-divider {
  display: flex;
  align-items: center;
  font-size: calc(var(--card-font-size) * 1.1);
  font-weight: 900;
  color: var(--card-accent);
  flex-shrink: 0;
}

/* ===== 图标文字页 ===== */
.card-icon-text {
  gap: 0;
}
.icon-text-title {
  font-size: calc(var(--card-font-size) * 1.15);
  font-weight: 700;
  color: var(--card-text);
  margin: 0;
  flex-shrink: 0;
}
.icon-text-grid {
  flex: 1;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
  align-content: space-evenly;
}
.icon-text-pair {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 24px 12px;
  background: var(--card-surface);
  border-radius: 12px;
}
.icon-text-icon {
  font-size: calc(var(--card-font-size) * 2);
}
.icon-text-desc {
  font-size: calc(var(--card-font-size) * 0.85);
  line-height: 1.5;
  color: var(--card-text);
  text-align: center;
  word-break: break-word;
}

/* ===== 步骤流程页 ===== */
.card-steps {
  gap: 0;
}
.steps-header {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-shrink: 0;
}
.steps-num {
  font-size: calc(var(--card-font-size) * 0.7);
  color: var(--card-accent);
  font-weight: 700;
  letter-spacing: 2px;
}
.steps-title {
  font-size: calc(var(--card-font-size) * 1.15);
  font-weight: 700;
  color: var(--card-text);
  margin: 0;
}
.steps-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: space-evenly;
  overflow: hidden;
}
.step-item {
  display: flex;
  gap: 16px;
  align-items: flex-start;
}
.step-marker {
  width: 44px;
  height: 44px;
  border-radius: 50%;
  background: var(--card-accent);
  color: var(--card-bg);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: calc(var(--card-font-size) * 0.8);
  font-weight: 700;
  flex-shrink: 0;
}
.step-content {
  flex: 1;
}
.step-title {
  font-size: calc(var(--card-font-size) * 1.05);
  font-weight: 700;
  color: var(--card-text);
  margin: 0 0 6px;
}
.step-desc {
  font-size: calc(var(--card-font-size) * 0.9);
  line-height: 1.5;
  color: var(--card-text);
  margin: 0;
  word-break: break-word;
}

/* ===== 编号卡片页 ===== */
.card-numcards {
  gap: 0;
}
.numcards-header {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-shrink: 0;
}
.numcards-num {
  font-size: calc(var(--card-font-size) * 0.7);
  color: var(--card-accent);
  font-weight: 700;
  letter-spacing: 2px;
}
.numcards-title {
  font-size: calc(var(--card-font-size) * 1.15);
  font-weight: 700;
  color: var(--card-text);
  margin: 0;
}
.numcards-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: space-evenly;
  overflow: hidden;
}
.numcard-item {
  display: flex;
  gap: 16px;
  align-items: flex-start;
  padding: 16px;
  background: var(--card-surface);
  border-radius: 10px;
}
.numcard-marker {
  font-size: calc(var(--card-font-size) * 1.1);
  font-weight: 900;
  color: var(--card-accent);
  flex-shrink: 0;
}
.numcard-content {
  flex: 1;
}
.numcard-title {
  font-size: calc(var(--card-font-size) * 1.0);
  font-weight: 700;
  color: var(--card-text);
  margin: 0 0 4px;
}
.numcard-desc {
  font-size: calc(var(--card-font-size) * 0.85);
  line-height: 1.5;
  color: var(--card-text);
  margin: 0;
  word-break: break-word;
}

/* ===== 报纸多栏页 ===== */
.card-newspaper {
  gap: 0;
}
.newspaper-masthead {
  font-size: calc(var(--card-font-size) * 1.2);
  font-weight: 900;
  letter-spacing: 6px;
  color: var(--card-text);
  text-align: center;
  padding-bottom: 16px;
  border-bottom: 4px double var(--card-text);
  flex-shrink: 0;
}
.newspaper-cols {
  flex: 1;
  display: flex;
  gap: 24px;
  overflow: hidden;
}
.newspaper-col {
  flex: 1;
}
.newspaper-headline {
  font-size: calc(var(--card-font-size) * 1.0);
  font-weight: 700;
  color: var(--card-text);
  margin: 0 0 12px;
  line-height: 1.3;
}
.newspaper-body {
  font-size: calc(var(--card-font-size) * 0.8);
  line-height: 1.6;
  color: var(--card-text);
  margin: 0;
  word-break: break-word;
}

/* ===== 大字金句页 ===== */
.card-bigquote {
  justify-content: center;
  align-items: center;
  text-align: center;
}
.bigquote-mark {
  font-size: calc(var(--card-font-size) * 4);
  color: var(--card-accent-soft);
  font-family: Georgia, serif;
  line-height: 1;
  user-select: none;
  margin-bottom: -24px;
}
.bigquote-text {
  font-size: calc(var(--card-font-size) * 1.4);
  font-weight: 700;
  line-height: 1.5;
  color: var(--card-text);
  margin: 0;
  word-break: break-word;
  padding: 0 32px;
}
.bigquote-footer {
  font-size: calc(var(--card-font-size) * 0.45);
  color: var(--card-subtext);
  margin-top: 32px;
}

/* ===== 尾页 ===== */
.card-end {
  justify-content: space-between;
}
.end-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 24px;
}
.end-mark {
  font-size: calc(var(--card-font-size) * 3.5);
  color: var(--card-accent-soft);
  font-family: Georgia, serif;
  line-height: 1;
  user-select: none;
}
.end-content {
  font-size: calc(var(--card-font-size) * 1.15);
  font-weight: 600;
  line-height: 1.5;
  color: var(--card-text);
  margin: 0;
  text-align: center;
  word-break: break-word;
}
.end-footer-area {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding-top: 24px;
  border-top: 2px solid var(--card-surface);
}
.end-cta {
  font-size: calc(var(--card-font-size) * 0.75);
  color: var(--card-accent);
  font-weight: 600;
}
.end-footer {
  font-size: calc(var(--card-font-size) * 0.45);
  color: var(--card-subtext);
}

/* ===== 代码面板页 ===== */
.card-code {
  gap: 0;
}
.code-title {
  font-size: calc(var(--card-font-size) * 1.15);
  font-weight: 700;
  color: var(--card-text);
  margin: 0;
  flex-shrink: 0;
}
.code-block {
  flex: 1;
  background: var(--card-surface);
  border-radius: 10px;
  padding: 24px;
  margin: 0;
  overflow: auto;
  font-size: calc(var(--card-font-size) * 0.75);
  line-height: 1.5;
  color: var(--card-text);
  font-family: 'Fira Code', 'Consolas', monospace;
}
</style>