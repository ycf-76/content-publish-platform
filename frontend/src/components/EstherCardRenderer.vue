<script setup lang="ts">
import { computed } from 'vue'
import type { TemplateTheme, DecorationConfig } from '../card-editor/templates'
import { createDefaultDecoration } from '../card-editor/templates'
import type { EstherCardPage } from '../card-editor/esther-templates'
import { ESTHER_BRAND } from '../card-editor/esther-templates'

const props = defineProps<{
  page: EstherCardPage
  theme: TemplateTheme
  decoration?: DecorationConfig
}>()

const deco = computed(() => props.decoration || createDefaultDecoration())

/** 自适应字号：根据当前页全部文本长度动态调整基准字号
 *  Esther 模板基准 36px，按内容量缩放
 */
const adaptiveScale = computed(() => {
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
  if (len < 50) return 1.1
  if (len < 150) return 1.0
  if (len < 300) return 0.82
  return 0.65
})

const cssVars = computed(() => ({
  '--card-bg': props.theme.bg,
  '--card-surface': props.theme.surface,
  '--card-text': props.theme.text,
  '--card-subtext': props.theme.subtext,
  '--card-accent': props.theme.accent,
  '--card-accent-soft': props.theme.accentSoft,
  '--esther-blue': ESTHER_BRAND.blue,
  '--esther-yellow': ESTHER_BRAND.yellow,
  '--esther-red': ESTHER_BRAND.red,
  '--esther-cream': ESTHER_BRAND.cream,
  '--esther-cream-dark': ESTHER_BRAND.creamDark,
  '--esther-ink': ESTHER_BRAND.ink,
  '--esther-ink-light': ESTHER_BRAND.inkLight,
  '--esther-ink-faint': ESTHER_BRAND.inkFaint,
  '--esther-font-scale': adaptiveScale.value,
}))

const contentParagraphs = computed(() => {
  return (props.page.content || '').split('\n').filter(p => p.trim())
})

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

const stepColors = [ESTHER_BRAND.blue, ESTHER_BRAND.yellow, ESTHER_BRAND.red]
</script>

<template>
  <div class="card-canvas" :style="cssVars">
    <!-- 装饰层 -->
    <div v-if="deco.type !== 'none'" class="card-decoration" :style="{ opacity: deco.opacity }">
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
      <svg v-else-if="deco.type === 'grid_lines'" class="deco-svg" xmlns="http://www.w3.org/2000/svg">
        <defs>
          <pattern id="esther-grid-pat" :width="deco.param1 ?? 80" :height="deco.param1 ?? 80" patternUnits="userSpaceOnUse">
            <path :d="`M ${(deco.param1 ?? 80)} 0 L 0 0 0 ${(deco.param1 ?? 80)}`" fill="none" :stroke="deco.color1" :stroke-width="deco.param2 ?? 1"/>
          </pattern>
        </defs>
        <rect width="100%" height="100%" fill="url(#esther-grid-pat)" />
      </svg>
      <svg v-else-if="deco.type === 'dots'" class="deco-svg" xmlns="http://www.w3.org/2000/svg">
        <defs>
          <pattern id="esther-dots-pat" :width="deco.param1 ?? 48" :height="deco.param1 ?? 48" patternUnits="userSpaceOnUse">
            <circle :cx="(deco.param1 ?? 48) / 2" :cy="(deco.param1 ?? 48) / 2" :r="deco.param2 ?? 6" :fill="deco.color1"/>
          </pattern>
        </defs>
        <rect width="100%" height="100%" fill="url(#esther-dots-pat)" />
      </svg>
      <svg v-else-if="deco.type === 'wave'" class="deco-svg" xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="none">
        <template v-for="i in Math.round(deco.param1 ?? 3)" :key="i">
          <path :d="wavePath(i)" :fill="i % 2 === 1 ? deco.color1 : deco.color2" fill-opacity="0.6" />
        </template>
      </svg>
      <div v-else-if="deco.type === 'noise'" class="deco-noise" :style="{
        filter: `contrast(${(deco.param1 ?? 0.5) * 2}) brightness(1.5)`,
        backgroundSize: `${Math.max(1, Math.round(4 / (deco.param2 ?? 1)))}px ${Math.max(1, Math.round(4 / (deco.param2 ?? 1)))}px`,
        '--noise-c1': deco.color1,
        '--noise-c2': deco.color2,
      }"></div>
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

    <!-- ===== P1 封面 ===== -->
    <div v-if="page.type === 'cover'" class="card-layout p-cover">
      <div class="deco-top"></div>
      <span class="cover-tag">{{ page.tag || '笔记 · 精选' }}</span>
      <h1 class="cover-title">
        <template v-if="page.highlight">
          {{ page.title.replace(page.highlight, '') }}<span class="cover-highlight">{{ page.highlight }}</span>
        </template>
        <template v-else>{{ page.title }}</template>
      </h1>
      <p class="cover-subtitle">{{ page.subtitle }}</p>
      <div class="cover-author-row">
        <div class="cover-avatar-ring">
          <div class="cover-avatar-placeholder">{{ (page.footer || '@').replace('@', '').charAt(0) || 'E' }}</div>
        </div>
        <div>
          <div class="cover-author-name">{{ (page.footer || '@灵犀工坊').replace('@', '') }}</div>
          <div class="cover-author-desc">用设计让知识更好看</div>
        </div>
      </div>
      <div class="cover-grid-texture"></div>
    </div>

    <!-- ===== P2 深色面板页 ===== -->
    <div v-else-if="page.type === 'dark_panel'" class="card-layout p-dark">
      <span class="dark-page-num">{{ page.decoNumber || '02' }}</span>
      <h2 class="dark-title">{{ page.title }}</h2>
      <p class="dark-sub">{{ page.emoji || '' }}</p>
      <div class="dark-items">
        <div v-for="(item, i) in page.listItems" :key="i" class="dark-item">
          <span class="dark-item-icon">{{ ['💡','⚡','🔥','🎯','🚀'][i % 5] }}</span>
          <span class="dark-item-text">{{ item }}</span>
        </div>
      </div>
      <div class="dark-deco-line"></div>
    </div>

    <!-- ===== 正文页 ===== -->
    <div v-else-if="page.type === 'content'" class="card-layout p-list">
      <span class="list-page-num">{{ page.decoNumber || '03' }}</span>
      <h2 class="list-title">{{ page.title }}</h2>
      <div class="list-content-area">
        <p v-for="(p, i) in contentParagraphs" :key="i" class="list-paragraph">{{ p }}</p>
      </div>
      <div v-if="page.footer" class="list-footer">{{ page.footer }}</div>
    </div>

    <!-- ===== 金句页 ===== -->
    <div v-else-if="page.type === 'quote'" class="card-layout p-quote">
      <div class="quote-deco-top"></div>
      <div class="quote-mark">"</div>
      <p class="quote-text">{{ page.content }}</p>
      <p class="quote-attr">{{ page.footer }}</p>
      <div class="quote-deco-bottom"></div>
    </div>

    <!-- ===== 清单页 ===== -->
    <div v-else-if="page.type === 'list'" class="card-layout p-list">
      <span class="list-page-num">{{ page.decoNumber || '04' }}</span>
      <h2 class="list-title">{{ page.title }}</h2>
      <div class="list-content-area">
        <div v-for="(item, i) in page.listItems" :key="i" class="list-row" :class="{ 'list-row-alt': i % 2 === 1 }">
          <span class="list-row-num">{{ String(i + 1).padStart(2, '0') }}</span>
          <span class="list-row-text">{{ item }}</span>
        </div>
      </div>
      <div v-if="page.footer" class="list-footer">{{ page.footer }}</div>
    </div>

    <!-- ===== 尾页 ===== -->
    <div v-else-if="page.type === 'end_page'" class="card-layout p-end">
      <div class="end-deco-bottom"></div>
      <div class="end-quote-mark">{{ page.decoNumber || '"' }}</div>
      <p class="end-quote">{{ page.content }}</p>
      <div class="end-avatar-ring">
        <div class="end-avatar-placeholder">{{ (page.footer || '@').replace('@', '').charAt(0) || 'E' }}</div>
      </div>
      <p class="end-author-name">{{ (page.footer || '@灵犀工坊').replace('@', '') }}</p>
      <p class="end-cta">{{ page.ctaText || '关注我，获取更多' }}</p>
      <p class="end-tagline">用设计让知识更好看<br>Design makes knowledge beautiful</p>
    </div>

    <!-- ===== 对比页 ===== -->
    <div v-else-if="page.type === 'compare'" class="card-layout p-compare">
      <span class="compare-page-num">{{ page.decoNumber || '05' }}</span>
      <h2 class="compare-title">{{ page.title }}</h2>
      <div class="compare-columns">
        <div class="compare-col compare-col-left">
          <div class="compare-col-head">
            <span class="compare-icon compare-icon-x">✕</span>
            <span class="compare-col-label">{{ page.compareLeftTitle || '问题' }}</span>
          </div>
          <div v-for="(item, i) in page.compareLeftItems" :key="'l' + i" class="compare-row compare-row-left">
            {{ item }}
          </div>
        </div>
        <div class="compare-col compare-col-right">
          <div class="compare-col-head">
            <span class="compare-icon compare-icon-check">✓</span>
            <span class="compare-col-label">{{ page.compareRightTitle || '解法' }}</span>
          </div>
          <div v-for="(item, i) in page.compareRightItems" :key="'r' + i" class="compare-row compare-row-right">
            {{ item }}
          </div>
        </div>
      </div>
    </div>

    <!-- ===== 图标文字页 ===== -->
    <div v-else-if="page.type === 'icon_text'" class="card-layout p-icon-text">
      <span class="icontext-page-num">{{ page.decoNumber || '06' }}</span>
      <h2 class="icontext-title">{{ page.title }}</h2>
      <div class="icontext-grid">
        <div v-for="(pair, i) in page.iconTextPairs" :key="i" class="icontext-card">
          <div class="icontext-icon-area" :class="['icontext-icon-blue', 'icontext-icon-yellow', 'icontext-icon-red'][i % 3]">
            {{ pair.icon }}
          </div>
          <div class="icontext-card-title">{{ pair.text }}</div>
        </div>
      </div>
    </div>

    <!-- ===== 步骤流程页 — esther #7 横向Step连接线 ===== -->
    <div v-else-if="page.type === 'steps'" class="card-layout p-steps">
      <div class="deco-top"></div>
      <span class="steps-page-num">{{ page.decoNumber || '01' }}</span>
      <h2 class="steps-title">{{ page.title }}</h2>
      <div class="steps-flow">
        <div v-for="(step, i) in page.steps" :key="i" class="step-block">
          <div class="step-arrow-head" :style="{ background: stepColors[i % 3] }"></div>
          <div class="step-content">
            <span class="step-num">{{ String(i + 1).padStart(2, '0') }}</span>
            <h3 class="step-name">{{ step.title }}</h3>
            <p class="step-desc">{{ step.desc }}</p>
          </div>
        </div>
      </div>
      <div class="steps-grid-texture"></div>
    </div>

    <!-- ===== 代码面板页 — esther #5 深色代码面板 ===== -->
    <div v-else-if="page.type === 'code_panel'" class="card-layout p-code">
      <div class="deco-top"></div>
      <span class="code-page-num">{{ page.decoNumber || '02' }}</span>
      <h2 class="code-title">{{ page.title }}</h2>
      <div class="code-panel">
        <div class="code-title-bar">
          <span class="code-dot code-dot-red"></span>
          <span class="code-dot code-dot-yellow"></span>
          <span class="code-dot code-dot-green"></span>
          <span class="code-lang">{{ page.codeLang || 'code' }}</span>
        </div>
        <pre class="code-body"><code>{{ page.codeContent || '// code here' }}</code></pre>
      </div>
      <div class="code-grid-texture"></div>
    </div>

    <!-- ===== 编号卡片网格页 — esther #34 ===== -->
    <div v-else-if="page.type === 'numbered_cards'" class="card-layout p-numcards">
      <div class="deco-top"></div>
      <span class="numcards-page-num">{{ page.decoNumber || '03' }}</span>
      <h2 class="numcards-title">{{ page.title }}</h2>
      <div class="numcards-grid">
        <div v-for="(item, i) in page.numberedItems" :key="i" class="numcard-item">
          <span class="numcard-num" :style="{ color: stepColors[i % 3] }">{{ String(i + 1).padStart(2, '0') }}</span>
          <div class="numcard-body">
            <h3 class="numcard-name">{{ item.title }}</h3>
            <p class="numcard-desc">{{ item.desc }}</p>
          </div>
        </div>
      </div>
      <div class="numcards-grid-texture"></div>
    </div>

    <!-- ===== 报纸多栏页 — esther #23 ===== -->
    <div v-else-if="page.type === 'newspaper'" class="card-layout p-newspaper">
      <div class="deco-top"></div>
      <div class="newspaper-masthead">{{ page.masthead || 'THE DAILY BRIEF' }}</div>
      <div class="newspaper-divider"></div>
      <div class="newspaper-columns">
        <div v-for="(col, i) in page.newspaperCols" :key="i" class="newspaper-col" :class="{ 'newspaper-col-border': i < (page.newspaperCols?.length || 0) - 1 }">
          <h3 class="newspaper-headline">{{ col.headline }}</h3>
          <p class="newspaper-body">{{ col.body }}</p>
        </div>
      </div>
      <div class="newspaper-footer-bar"></div>
    </div>

    <!-- ===== 大字金句页 — esther #38 ===== -->
    <div v-else-if="page.type === 'big_quote'" class="card-layout p-bigquote">
      <div class="bigquote-deco-top"></div>
      <div class="bigquote-mark">{{ page.decoNumber || '"' }}</div>
      <p class="bigquote-text">{{ page.content }}</p>
      <p class="bigquote-attr">{{ page.footer }}</p>
      <div class="bigquote-deco-bottom"></div>
      <div class="bigquote-grid-texture"></div>
    </div>
  </div>
</template>

<style scoped>
/* ===== 基础画布 ===== */
.card-canvas {
  width: 1080px;
  height: 1440px;
  background: var(--card-bg);
  color: var(--card-text);
  font-family: 'Noto Sans SC', 'PingFang SC', 'Microsoft YaHei', sans-serif;
  font-size: 36px;
  position: relative;
  overflow: hidden;
  box-sizing: border-box;
  zoom: var(--esther-font-scale, 1);
}

.card-decoration {
  position: absolute;
  top: 0; left: 0;
  width: 100%; height: 100%;
  z-index: 1;
  pointer-events: none;
  overflow: hidden;
}
.card-layout {
  position: relative;
  z-index: 2;
  width: 100%; height: 100%;
  padding: 72px 64px;
  display: flex;
  flex-direction: column;
  box-sizing: border-box;
  overflow: hidden;
}

.deco-orb {
  position: absolute;
  width: 70%; height: 50%;
  border-radius: 50%;
  filter: blur(80px);
  transform: translate(-50%, -50%);
}
.deco-orb-1 { width: 65%; height: 45%; }
.deco-orb-2 { width: 55%; height: 40%; }
.deco-svg { position: absolute; top: 0; left: 0; width: 100%; height: 100%; }
.deco-noise {
  position: absolute;
  top: -50%; left: -50%;
  width: 200%; height: 200%;
  background: repeating-conic-gradient(var(--noise-c1) 0%, var(--noise-c2) 0.5%, transparent 1%);
  mix-blend-mode: multiply;
}

/* ===== 通用品牌装饰 ===== */
.deco-top {
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 8px;
  background: linear-gradient(90deg, var(--esther-blue) 60%, var(--esther-yellow) 80%, var(--esther-red) 100%);
  z-index: 3;
}

/* ============================================================
   P1 封面
   ============================================================ */
.p-cover {
  background: var(--esther-cream);
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  padding: 72px 80px;
  position: relative;
}

.p-cover .cover-tag {
  font-size: 28px;
  font-weight: 700;
  color: #fff;
  background: var(--esther-blue);
  display: inline-block;
  padding: 8px 24px;
  border-radius: 6px;
  margin-bottom: 0;
  letter-spacing: 2px;
  align-self: flex-start;
}

.p-cover .cover-title {
  font-family: 'Noto Serif SC', 'Songti SC', 'Huiwen Mincho', serif;
  font-weight: 900;
  font-size: 88px;
  line-height: 1.2;
  color: var(--esther-ink);
  margin: 0 0 20px 0;
  word-break: break-word;
}

.p-cover .cover-highlight {
  color: var(--esther-blue);
}

.p-cover .cover-subtitle {
  font-size: 42px;
  color: var(--esther-ink-light);
  font-weight: 500;
  line-height: 1.6;
  margin: 0 0 40px 0;
}

.p-cover .cover-author-row {
  display: flex;
  align-items: center;
  gap: 24px;
}

.p-cover .cover-avatar-ring {
  width: 88px;
  height: 88px;
  border-radius: 50%;
  border: 4px solid var(--esther-yellow);
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  flex-shrink: 0;
}

.p-cover .cover-avatar-placeholder {
  width: 100%;
  height: 100%;
  background: var(--esther-blue);
  color: #fff;
  font-size: 36px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  font-family: 'Noto Serif SC', serif;
}

.p-cover .cover-author-name {
  font-size: 36px;
  font-weight: 700;
  color: var(--esther-ink);
}

.p-cover .cover-author-desc {
  font-size: 24px;
  color: var(--esther-ink-light);
  margin-top: 4px;
}

.p-cover .cover-grid-texture {
  position: absolute;
  top: 0; left: 0; right: 0; bottom: 0;
  background-image:
    linear-gradient(rgba(0,0,0,0.03) 1px, transparent 1px),
    linear-gradient(90deg, rgba(0,0,0,0.03) 1px, transparent 1px);
  background-size: 40px 40px;
  z-index: 0;
  pointer-events: none;
}

/* ============================================================
   P2 深色面板页
   ============================================================ */
.p-dark {
  background: var(--esther-ink);
  display: flex;
  flex-direction: column;
  justify-content: space-evenly;
  padding: 72px 80px;
  position: relative;
  color: #e8e4de;
}

.p-dark .dark-page-num {
  font-family: 'Fraunces', 'Georgia', serif;
  font-style: italic;
  font-size: 120px;
  color: var(--esther-yellow);
  opacity: 0.15;
  position: absolute;
  top: 40px;
  right: 80px;
  font-weight: 700;
  line-height: 1;
  user-select: none;
}

.p-dark .dark-title {
  font-family: 'Noto Serif SC', 'Songti SC', serif;
  font-weight: 900;
  font-size: 52px;
  color: var(--esther-cream);
  margin-bottom: 12px;
}

.p-dark .dark-sub {
  font-size: 48px;
  color: var(--esther-yellow);
  margin-bottom: 32px;
  font-weight: 500;
}

.p-dark .dark-items {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: space-evenly;
  gap: 0;
}

.p-dark .dark-item {
  display: flex;
  align-items: flex-start;
  gap: 24px;
}

.p-dark .dark-item-icon {
  font-size: 40px;
  flex-shrink: 0;
  width: 56px;
  text-align: center;
}

.p-dark .dark-item-text {
  font-size: 38px;
  color: #e8e4de;
  line-height: 1.5;
  font-weight: 500;
}

.p-dark .dark-deco-line {
  position: absolute;
  bottom: 80px;
  left: 80px;
  right: 80px;
  height: 4px;
  background: linear-gradient(90deg, var(--esther-blue) 50%, var(--esther-yellow) 75%, var(--esther-red) 100%);
  border-radius: 2px;
  opacity: 0.6;
}

/* ============================================================
   浅色列表/正文页
   ============================================================ */
.p-list {
  background: var(--esther-cream);
  display: flex;
  flex-direction: column;
  justify-content: space-evenly;
  padding: 72px 80px;
  position: relative;
}

.p-list .list-page-num {
  font-family: 'Fraunces', 'Georgia', serif;
  font-style: italic;
  font-size: 120px;
  color: var(--esther-blue);
  opacity: 0.12;
  position: absolute;
  top: 40px;
  right: 80px;
  font-weight: 700;
  line-height: 1;
  user-select: none;
}
.p-list .list-title {
  font-family: 'Noto Serif SC', 'Songti SC', serif;
  font-weight: 900;
  font-size: 52px;
  margin-bottom: 24px;
  color: var(--esther-ink);
  position: relative;
}

.p-list .list-title::after {
  content: '';
  display: block;
  width: 80px;
  height: 6px;
  background: var(--esther-yellow);
  margin-top: 16px;
  border-radius: 3px;
}

.p-list .list-content-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: space-evenly;
  gap: 0;
}

.p-list .list-paragraph {
  font-size: 38px;
  line-height: 1.6;
  color: var(--esther-ink);
  margin: 0;
  word-break: break-word;
}

.p-list .list-row {
  display: flex;
  align-items: flex-start;
  gap: 24px;
  padding: 24px 28px;
  border-radius: 12px;
}

.p-list .list-row-alt {
  background: var(--esther-cream-dark);
}

.p-list .list-row-num {
  font-family: 'Fraunces', 'Georgia', serif;
  font-size: 36px;
  font-weight: 700;
  color: var(--esther-blue);
  flex-shrink: 0;
  min-width: 56px;
}

.p-list .list-row-text {
  font-size: 38px;
  line-height: 1.6;
  color: var(--esther-ink);
  word-break: break-word;
}

.p-list .list-footer {
  font-size: 28px;
  color: var(--esther-ink-light);
  padding-top: 24px;
  border-top: 2px solid var(--esther-cream-dark);
}

/* ============================================================
   金句页
   ============================================================ */
.p-quote {
  background: var(--esther-cream);
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  padding: 80px 90px;
  text-align: center;
  position: relative;
}

.p-quote .quote-deco-top {
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 8px;
  background: linear-gradient(90deg, var(--esther-blue) 60%, var(--esther-yellow) 80%, var(--esther-red) 100%);
  z-index: 3;
}

.p-quote .quote-mark {
  font-family: 'Fraunces', 'Georgia', serif;
  font-style: italic;
  font-size: 200px;
  color: var(--esther-blue);
  opacity: 0.15;
  line-height: 0.6;
  margin-bottom: -20px;
  user-select: none;
}

.p-quote .quote-text {
  font-family: 'Noto Serif SC', 'Songti SC', serif;
  font-weight: 900;
  font-size: 60px;
  line-height: 1.5;
  color: var(--esther-ink);
  margin: 0 0 32px 0;
  max-width: 900px;
  word-break: break-word;
}

.p-quote .quote-attr {
  font-size: 32px;
  color: var(--esther-ink-light);
  font-weight: 500;
}

.p-quote .quote-deco-bottom {
  position: absolute;
  bottom: 0; left: 0; right: 0;
  height: 8px;
  background: linear-gradient(90deg, var(--esther-blue) 60%, var(--esther-yellow) 80%, var(--esther-red) 100%);
  z-index: 3;
}

/* ============================================================
   尾页
   ============================================================ */
.p-end {
  background: var(--esther-cream);
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  padding: 80px 90px;
  text-align: center;
  position: relative;
}

.p-end .end-deco-bottom {
  position: absolute;
  bottom: 0; left: 0; right: 0;
  height: 8px;
  background: linear-gradient(90deg, var(--esther-blue) 60%, var(--esther-yellow) 80%, var(--esther-red) 100%);
  z-index: 3;
}

.p-end .end-quote-mark {
  font-family: 'Fraunces', 'Georgia', serif;
  font-style: italic;
  font-size: 200px;
  color: var(--esther-blue);
  opacity: 0.15;
  line-height: 0.6;
  margin-bottom: -20px;
  user-select: none;
}

.p-end .end-quote {
  font-family: 'Noto Serif SC', 'Songti SC', serif;
  font-weight: 900;
  font-size: 60px;
  line-height: 1.5;
  color: var(--esther-ink);
  margin: 0 0 32px 0;
  max-width: 900px;
  word-break: break-word;
}

.p-end .end-avatar-ring {
  width: 100px;
  height: 100px;
  border-radius: 50%;
  border: 3px solid var(--esther-yellow);
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  flex-shrink: 0;
  margin-bottom: 20px;
}

.p-end .end-avatar-placeholder {
  width: 100%;
  height: 100%;
  background: var(--esther-blue);
  color: #fff;
  font-size: 40px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  font-family: 'Noto Serif SC', serif;
}

.p-end .end-author-name {
  font-size: 40px;
  font-weight: 700;
  color: var(--esther-ink);
  margin-bottom: 8px;
}

.p-end .end-cta {
  font-size: 32px;
  color: var(--esther-blue);
  font-weight: 600;
  margin-bottom: 48px;
}

.p-end .end-tagline {
  font-size: 26px;
  color: var(--esther-ink-light);
  letter-spacing: 2px;
  line-height: 1.6;
}

/* ============================================================
   对比页
   ============================================================ */
.p-compare {
  background: var(--esther-cream);
  display: flex;
  flex-direction: column;
  justify-content: space-evenly;
  padding: 72px 80px;
  position: relative;
}

.p-compare .compare-page-num {
  font-family: 'Fraunces', 'Georgia', serif;
  font-style: italic;
  font-size: 120px;
  color: var(--esther-blue);
  opacity: 0.12;
  position: absolute;
  top: 40px;
  right: 80px;
  font-weight: 700;
  line-height: 1;
  user-select: none;
}

.p-compare .compare-title {
  font-family: 'Noto Serif SC', 'Songti SC', serif;
  font-weight: 900;
  font-size: 52px;
  color: var(--esther-ink);
  margin: 0 0 16px 0;
}

.p-compare .compare-title::after {
  content: '';
  display: block;
  width: 80px;
  height: 6px;
  background: var(--esther-yellow);
  margin-top: 16px;
  border-radius: 3px;
}

.p-compare .compare-columns {
  flex: 1;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 24px;
  margin-top: 40px;
  align-content: center;
}

.p-compare .compare-col {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 32px 28px;
  border-radius: 16px;
}

.p-compare .compare-col-left {
  background: rgba(232, 74, 95, 0.06);
  border: 2px solid rgba(232, 74, 95, 0.15);
}

.p-compare .compare-col-right {
  background: rgba(43, 127, 216, 0.06);
  border: 2px solid rgba(43, 127, 216, 0.15);
}

.p-compare .compare-col-head {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}

.p-compare .compare-icon {
  width: 44px;
  height: 44px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 22px;
  font-weight: 700;
  flex-shrink: 0;
}

.p-compare .compare-icon-x {
  background: var(--esther-red);
  color: #fff;
}

.p-compare .compare-icon-check {
  background: var(--esther-blue);
  color: #fff;
}

.p-compare .compare-col-label {
  font-size: 36px;
  font-weight: 700;
  color: var(--esther-ink);
}

.p-compare .compare-row {
  font-size: 34px;
  line-height: 1.5;
  padding: 14px 18px;
  border-radius: 10px;
}

.p-compare .compare-row-left {
  background: rgba(232, 74, 95, 0.06);
  color: #8B3A3A;
}

.p-compare .compare-row-right {
  background: rgba(43, 127, 216, 0.06);
  color: #1A4A7A;
}

/* ============================================================
   图标文字页
   ============================================================ */
.p-icon-text {
  background: var(--esther-cream);
  display: flex;
  flex-direction: column;
  justify-content: space-evenly;
  padding: 72px 80px;
  position: relative;
}

.p-icon-text .icontext-page-num {
  font-family: 'Fraunces', 'Georgia', serif;
  font-style: italic;
  font-size: 120px;
  color: var(--esther-blue);
  opacity: 0.12;
  position: absolute;
  top: 40px;
  right: 80px;
  font-weight: 700;
  line-height: 1;
  user-select: none;
}

.p-icon-text .icontext-title {
  font-family: 'Noto Serif SC', 'Songti SC', serif;
  font-weight: 900;
  font-size: 52px;
  color: var(--esther-ink);
  margin: 0 0 16px 0;
}

.p-icon-text .icontext-title::after {
  content: '';
  display: block;
  width: 80px;
  height: 6px;
  background: var(--esther-yellow);
  margin-top: 16px;
  border-radius: 3px;
}

.p-icon-text .icontext-grid {
  flex: 1;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 24px;
  align-content: center;
  margin-top: 40px;
}

.p-icon-text .icontext-card {
  position: relative;
  padding: 36px 28px 28px;
  background: #fff;
  border-radius: 16px;
  overflow: hidden;
  box-shadow: 0 2px 8px rgba(0,0,0,0.04);
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  gap: 16px;
}

.p-icon-text .icontext-icon-area {
  width: 80px;
  height: 80px;
  border-radius: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 40px;
}

.p-icon-text .icontext-icon-blue {
  background: rgba(43, 127, 216, 0.1);
}

.p-icon-text .icontext-icon-yellow {
  background: rgba(244, 215, 88, 0.25);
}

.p-icon-text .icontext-icon-red {
  background: rgba(232, 74, 95, 0.1);
}

.p-icon-text .icontext-card-title {
  font-family: 'Noto Serif SC', 'Songti SC', serif;
  font-size: 32px;
  font-weight: 700;
  color: var(--esther-ink);
  line-height: 1.4;
}

/* ============================================================
   步骤流程页 — esther #7 横向Step连接线
   蓝色箭头(48px)连接流程块，编号三色轮换
   ============================================================ */
.p-steps {
  background: var(--esther-cream);
  display: flex;
  flex-direction: column;
  justify-content: space-evenly;
  padding: 72px 80px;
  position: relative;
}

.p-steps .steps-page-num {
  font-family: 'Fraunces', 'Georgia', serif;
  font-style: italic;
  font-size: 120px;
  color: var(--esther-blue);
  opacity: 0.12;
  position: absolute;
  top: 40px;
  right: 80px;
  font-weight: 700;
  line-height: 1;
  user-select: none;
}

.p-steps .steps-title {
  font-family: 'Noto Serif SC', 'Songti SC', serif;
  font-weight: 900;
  font-size: 52px;
  color: var(--esther-ink);
  margin: 0 0 16px 0;
}

.p-steps .steps-title::after {
  content: '';
  display: block;
  width: 80px;
  height: 6px;
  background: var(--esther-yellow);
  margin-top: 16px;
  border-radius: 3px;
}

.p-steps .steps-flow {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: space-evenly;
  gap: 0;
  margin-top: 24px;
}

.p-steps .step-block {
  position: relative;
  display: flex;
  align-items: stretch;
  gap: 0;
}

.p-steps .step-arrow-head {
  width: 48px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
}

.p-steps .step-arrow-head::after {
  content: '';
  position: absolute;
  top: 0;
  bottom: 0;
  right: 0;
  width: 0;
  height: 0;
  border-top: 14px solid transparent;
  border-bottom: 14px solid transparent;
  border-left: 12px solid var(--esther-cream);
}

.p-steps .step-content {
  flex: 1;
  background: #fff;
  border-radius: 16px;
  padding: 32px 36px;
  margin: 8px 0;
  box-shadow: 0 2px 8px rgba(0,0,0,0.04);
  display: flex;
  align-items: center;
  gap: 28px;
}

.p-steps .step-num {
  font-family: 'Fraunces', 'Georgia', serif;
  font-size: 56px;
  font-weight: 900;
  line-height: 1;
  flex-shrink: 0;
  opacity: 0.8;
}

.p-steps .step-name {
  font-family: 'Noto Serif SC', 'Songti SC', serif;
  font-size: 40px;
  font-weight: 900;
  color: var(--esther-ink);
  margin: 0 0 8px 0;
}

.p-steps .step-desc {
  font-size: 32px;
  color: var(--esther-ink-light);
  line-height: 1.5;
  margin: 0;
}

.p-steps .steps-grid-texture {
  position: absolute;
  top: 0; left: 0; right: 0; bottom: 0;
  background-image:
    linear-gradient(rgba(0,0,0,0.03) 1px, transparent 1px),
    linear-gradient(90deg, rgba(0,0,0,0.03) 1px, transparent 1px);
  background-size: 40px 40px;
  z-index: 0;
  pointer-events: none;
}

/* ============================================================
   代码面板页 — esther #5 深色代码面板
   深色底+Fira Code+三色圆点title bar
   ============================================================ */
.p-code {
  background: var(--esther-cream);
  display: flex;
  flex-direction: column;
  justify-content: space-evenly;
  padding: 72px 80px;
  position: relative;
}

.p-code .code-page-num {
  font-family: 'Fraunces', 'Georgia', serif;
  font-style: italic;
  font-size: 120px;
  color: var(--esther-blue);
  opacity: 0.12;
  position: absolute;
  top: 40px;
  right: 80px;
  font-weight: 700;
  line-height: 1;
  user-select: none;
}

.p-code .code-title {
  font-family: 'Noto Serif SC', 'Songti SC', serif;
  font-weight: 900;
  font-size: 52px;
  color: var(--esther-ink);
  margin: 0 0 16px 0;
}

.p-code .code-title::after {
  content: '';
  display: block;
  width: 80px;
  height: 6px;
  background: var(--esther-yellow);
  margin-top: 16px;
  border-radius: 3px;
}

.p-code .code-panel {
  flex: 1;
  background: #1a1a2e;
  border-radius: 16px;
  overflow: hidden;
  margin-top: 40px;
  display: flex;
  flex-direction: column;
  box-shadow: 0 8px 32px rgba(0,0,0,0.15);
}

.p-code .code-title-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 20px 28px;
  background: #151821;
  border-bottom: 1px solid rgba(255,255,255,0.08);
}

.p-code .code-dot {
  width: 16px;
  height: 16px;
  border-radius: 50%;
}

.p-code .code-dot-red {
  background: #E84A5F;
}

.p-code .code-dot-yellow {
  background: #F4D758;
}

.p-code .code-dot-green {
  background: #4ade80;
}

.p-code .code-lang {
  font-family: 'Fira Code', 'Consolas', monospace;
  font-size: 22px;
  color: #8A8A9A;
  margin-left: auto;
  text-transform: uppercase;
  letter-spacing: 1px;
}

.p-code .code-body {
  flex: 1;
  margin: 0;
  padding: 32px 36px;
  font-family: 'Fira Code', 'Consolas', 'Courier New', monospace;
  font-size: 30px;
  line-height: 1.7;
  color: #e8e4de;
  overflow: hidden;
  white-space: pre;
  tab-size: 4;
}

.p-code .code-grid-texture {
  position: absolute;
  top: 0; left: 0; right: 0; bottom: 0;
  background-image:
    linear-gradient(rgba(0,0,0,0.03) 1px, transparent 1px),
    linear-gradient(90deg, rgba(0,0,0,0.03) 1px, transparent 1px);
  background-size: 40px 40px;
  z-index: 0;
  pointer-events: none;
}

/* ============================================================
   编号卡片网格页 — esther #34
   编号三色轮换(蓝/黄/红)+白底圆角卡片
   ============================================================ */
.p-numcards {
  background: var(--esther-cream);
  display: flex;
  flex-direction: column;
  justify-content: space-evenly;
  padding: 72px 80px;
  position: relative;
}

.p-numcards .numcards-page-num {
  font-family: 'Fraunces', 'Georgia', serif;
  font-style: italic;
  font-size: 120px;
  color: var(--esther-blue);
  opacity: 0.12;
  position: absolute;
  top: 40px;
  right: 80px;
  font-weight: 700;
  line-height: 1;
  user-select: none;
}

.p-numcards .numcards-title {
  font-family: 'Noto Serif SC', 'Songti SC', serif;
  font-weight: 900;
  font-size: 52px;
  color: var(--esther-ink);
  margin: 0 0 16px 0;
}

.p-numcards .numcards-title::after {
  content: '';
  display: block;
  width: 80px;
  height: 6px;
  background: var(--esther-yellow);
  margin-top: 16px;
  border-radius: 3px;
}

.p-numcards .numcards-grid {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: space-evenly;
  gap: 0;
  margin-top: 24px;
}

.p-numcards .numcard-item {
  display: flex;
  align-items: flex-start;
  gap: 28px;
  background: #fff;
  border-radius: 16px;
  padding: 36px 32px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.04);
}

.p-numcards .numcard-num {
  font-family: 'Fraunces', 'Georgia', serif;
  font-size: 64px;
  font-weight: 900;
  line-height: 1;
  flex-shrink: 0;
  opacity: 0.7;
}

.p-numcards .numcard-body {
  flex: 1;
}

.p-numcards .numcard-name {
  font-family: 'Noto Serif SC', 'Songti SC', serif;
  font-size: 38px;
  font-weight: 900;
  color: var(--esther-ink);
  margin: 0 0 8px 0;
  line-height: 1.3;
}

.p-numcards .numcard-desc {
  font-size: 30px;
  color: var(--esther-ink-light);
  line-height: 1.5;
  margin: 0;
}

.p-numcards .numcards-grid-texture {
  position: absolute;
  top: 0; left: 0; right: 0; bottom: 0;
  background-image:
    linear-gradient(rgba(0,0,0,0.03) 1px, transparent 1px),
    linear-gradient(90deg, rgba(0,0,0,0.03) 1px, transparent 1px);
  background-size: 40px 40px;
  z-index: 0;
  pointer-events: none;
}

/* ============================================================
   报纸多栏页 — esther #23
   Fraunces 大标题+多栏分隔线+衬线标题+紧凑正文
   ============================================================ */
.p-newspaper {
  background: var(--esther-cream);
  display: flex;
  flex-direction: column;
  justify-content: space-evenly;
  padding: 72px 80px;
  position: relative;
}

.p-newspaper .newspaper-masthead {
  font-family: 'Fraunces', 'Georgia', serif;
  font-weight: 900;
  font-size: 56px;
  letter-spacing: 8px;
  text-align: center;
  color: var(--esther-ink);
  border-top: 4px solid var(--esther-ink);
  border-bottom: 4px solid var(--esther-ink);
  padding: 20px 0;
  margin-bottom: 0;
}

.p-newspaper .newspaper-divider {
  height: 2px;
  background: linear-gradient(90deg, var(--esther-blue) 60%, var(--esther-yellow) 80%, var(--esther-red) 100%);
  margin: 0;
}

.p-newspaper .newspaper-columns {
  flex: 1;
  display: flex;
  gap: 0;
  align-items: stretch;
}

.p-newspaper .newspaper-col {
  flex: 1;
  padding: 32px 28px;
  display: flex;
  flex-direction: column;
}

.p-newspaper .newspaper-col-border {
  border-right: 1px solid rgba(26, 26, 46, 0.15);
}

.p-newspaper .newspaper-headline {
  font-family: 'Noto Serif SC', 'Songti SC', serif;
  font-weight: 900;
  font-size: 36px;
  line-height: 1.3;
  color: var(--esther-ink);
  margin: 0 0 16px 0;
  border-bottom: 2px solid var(--esther-yellow);
  padding-bottom: 12px;
}

.p-newspaper .newspaper-body {
  font-size: 28px;
  line-height: 1.7;
  color: var(--esther-ink-light);
  margin: 0;
}

.p-newspaper .newspaper-footer-bar {
  height: 4px;
  background: linear-gradient(90deg, var(--esther-blue) 60%, var(--esther-yellow) 80%, var(--esther-red) 100%);
  margin-top: auto;
  border-radius: 2px;
}

/* ============================================================
   大字金句页 — esther #38
   Fraunces 200px 引号+衬线超大字+居中+三色条
   ============================================================ */
.p-bigquote {
  background: var(--esther-cream);
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  padding: 80px 90px;
  text-align: center;
  position: relative;
}

.p-bigquote .bigquote-deco-top {
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 8px;
  background: linear-gradient(90deg, var(--esther-blue) 60%, var(--esther-yellow) 80%, var(--esther-red) 100%);
  z-index: 3;
}

.p-bigquote .bigquote-mark {
  font-family: 'Fraunces', 'Georgia', serif;
  font-style: italic;
  font-size: 260px;
  color: var(--esther-blue);
  opacity: 0.12;
  line-height: 0.5;
  margin-bottom: -40px;
  user-select: none;
}

.p-bigquote .bigquote-text {
  font-family: 'Noto Serif SC', 'Songti SC', serif;
  font-weight: 900;
  font-size: 72px;
  line-height: 1.4;
  color: var(--esther-ink);
  margin: 0 0 40px 0;
  max-width: 900px;
  word-break: break-word;
}

.p-bigquote .bigquote-attr {
  font-family: 'Fraunces', 'Georgia', serif;
  font-style: italic;
  font-size: 32px;
  color: var(--esther-blue);
  font-weight: 500;
}

.p-bigquote .bigquote-deco-bottom {
  position: absolute;
  bottom: 0; left: 0; right: 0;
  height: 8px;
  background: linear-gradient(90deg, var(--esther-blue) 60%, var(--esther-yellow) 80%, var(--esther-red) 100%);
  z-index: 3;
}

.p-bigquote .bigquote-grid-texture {
  position: absolute;
  top: 0; left: 0; right: 0; bottom: 0;
  background-image:
    linear-gradient(rgba(0,0,0,0.03) 1px, transparent 1px),
    linear-gradient(90deg, rgba(0,0,0,0.03) 1px, transparent 1px);
  background-size: 40px 40px;
  z-index: 0;
  pointer-events: none;
}
</style>