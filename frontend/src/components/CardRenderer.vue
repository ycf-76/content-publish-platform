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

/** CSS 变量对象，绑定到卡片根元素 */
const cssVars = computed(() => ({
  '--card-bg': props.theme.bg,
  '--card-surface': props.theme.surface,
  '--card-text': props.theme.text,
  '--card-subtext': props.theme.subtext,
  '--card-accent': props.theme.accent,
  '--card-accent-soft': props.theme.accentSoft,
  '--card-font-size': `${props.theme.fontSize}px`,
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
  padding: 96px 88px;
  display: flex;
  flex-direction: column;
  box-sizing: border-box;
}

/* ===== 封面页 ===== */
.card-cover {
  justify-content: space-between;
}
.cover-top-bar {
  width: 120px;
  height: 8px;
  background: var(--card-accent);
  border-radius: 4px;
}
.cover-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 32px;
}
.cover-tag {
  font-size: calc(var(--card-font-size) * 0.5);
  color: var(--card-accent);
  letter-spacing: 4px;
  font-weight: 600;
}
.cover-title {
  font-size: calc(var(--card-font-size) * 1.8);
  font-weight: 700;
  line-height: 1.3;
  color: var(--card-text);
  margin: 0;
  word-break: break-word;
}
.cover-subtitle {
  font-size: calc(var(--card-font-size) * 0.7);
  color: var(--card-subtext);
  line-height: 1.5;
  margin: 0;
}
.cover-footer {
  padding-top: 32px;
  border-top: 2px solid var(--card-surface);
}
.cover-footer-text {
  font-size: calc(var(--card-font-size) * 0.5);
  color: var(--card-subtext);
}

/* ===== 正文页 ===== */
.card-content {
  justify-content: flex-start;
  gap: 56px;
}
.content-header {
  display: flex;
  align-items: center;
  gap: 24px;
}
.content-accent-line {
  width: 8px;
  height: 56px;
  background: var(--card-accent);
  border-radius: 4px;
  flex-shrink: 0;
}
.content-title {
  font-size: calc(var(--card-font-size) * 1.2);
  font-weight: 700;
  color: var(--card-text);
  margin: 0;
  line-height: 1.4;
}
.content-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 32px;
}
.content-paragraph {
  font-size: var(--card-font-size);
  line-height: 1.8;
  color: var(--card-text);
  margin: 0;
  word-break: break-word;
}
.content-footer {
  font-size: calc(var(--card-font-size) * 0.5);
  color: var(--card-subtext);
  padding-top: 24px;
  border-top: 2px solid var(--card-surface);
}

/* ===== 金句页 ===== */
.card-quote {
  justify-content: center;
  align-items: center;
  text-align: center;
  position: relative;
}
.quote-mark {
  font-size: 200px;
  color: var(--card-accent-soft);
  font-family: Georgia, serif;
  line-height: 1;
  user-select: none;
}
.quote-mark-top {
  align-self: flex-start;
  margin-bottom: -40px;
}
.quote-mark-bottom {
  align-self: flex-end;
  margin-top: -40px;
}
.quote-body {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0 40px;
}
.quote-text {
  font-size: calc(var(--card-font-size) * 1.4);
  font-weight: 600;
  line-height: 1.6;
  color: var(--card-text);
  margin: 0;
  word-break: break-word;
}
.quote-footer {
  font-size: calc(var(--card-font-size) * 0.5);
  color: var(--card-subtext);
  margin-top: 48px;
}

/* ===== 清单页 ===== */
.card-list {
  gap: 48px;
}
.list-header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  padding-bottom: 32px;
  border-bottom: 3px solid var(--card-accent);
}
.list-title {
  font-size: calc(var(--card-font-size) * 1.3);
  font-weight: 700;
  color: var(--card-text);
  margin: 0;
}
.list-count {
  font-size: calc(var(--card-font-size) * 0.5);
  color: var(--card-subtext);
}
.list-body {
  flex: 1;
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 32px;
}
.list-item {
  display: flex;
  align-items: flex-start;
  gap: 24px;
}
.list-item-num {
  font-size: calc(var(--card-font-size) * 0.7);
  font-weight: 700;
  color: var(--card-accent);
  flex-shrink: 0;
  min-width: 56px;
}
.list-item-text {
  font-size: var(--card-font-size);
  line-height: 1.6;
  color: var(--card-text);
  word-break: break-word;
}
.list-footer {
  font-size: calc(var(--card-font-size) * 0.5);
  color: var(--card-subtext);
  padding-top: 24px;
  border-top: 2px solid var(--card-surface);
}
</style>