<template>
  <main class="eco-page" :class="{ 'dark-theme': darkTheme }">
    <!-- 粒子背景层 -->
    <canvas class="magic-particles" ref="particlesCanvas" aria-hidden="true"></canvas>

    <!-- 顶部标题栏 -->
    <header class="eco-header">
      <button class="eco-back" @click="goBack" aria-label="返回工作台">
        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/>
        </svg>
        <span>返回工作台</span>
      </button>
      <div class="eco-title-block">
        <h1 class="eco-title">Pulse Studio</h1>
        <p class="eco-subtitle">覆盖主流社媒与浏览器 · 一站式内容分发网络</p>
      </div>
      <div class="eco-header-actions">
        <button class="eco-like-btn" :class="{ 'liked': liked }" @click="toggleLike" aria-label="点赞">
          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" :fill="liked ? 'currentColor' : 'none'" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.29 1.51 4.04 3 5.5l7 7Z"/>
          </svg>
          <span class="eco-like-count">{{ likeCount }}</span>
        </button>
        <button class="eco-theme-toggle" @click="toggleTheme" title="切换星空主题">
          <svg v-if="!darkTheme" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/>
          </svg>
          <svg v-else xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="4"/><path d="M12 2v2"/><path d="M12 20v2"/><path d="m4.93 4.93 1.41 1.41"/><path d="m17.66 17.66 1.41 1.41"/><path d="M2 12h2"/><path d="M20 12h2"/><path d="m6.34 17.66-1.41 1.41"/><path d="m19.07 4.93-1.41 1.41"/>
          </svg>
        </button>
      </div>
    </header>

    <!-- 球体舞台 -->
    <div class="eco-stage">
      <IconCloud />
    </div>

    <!-- 底部提示 -->
    <footer class="eco-footer">
      <span>移动鼠标控制旋转方向 · 球体自动公转</span>
    </footer>

  </main>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import IconCloud from '@/components/IconCloud.vue'

const router = useRouter()

/* ============ 主题切换（与工作台共用 localStorage key） ============ */
const SK_DARK = 'mint_dark_theme'
const darkTheme = ref(localStorage.getItem(SK_DARK) === '1')
function toggleTheme() {
  darkTheme.value = !darkTheme.value
  localStorage.setItem(SK_DARK, darkTheme.value ? '1' : '0')
  applyThemeState()
  pInitParticles()
}

function goBack() {
  router.push('/workbench')
}
function goWorkbench() {
  router.push('/workbench')
}


/* ============ 粒子背景 ============ */
const particlesCanvas = ref<HTMLCanvasElement | null>(null)
const P_CONFIG = {
  color: '16, 185, 129',
  dotAlpha: 0.55,
  linkAlphaMax: 0.35,
  density: 12000,
  linkDistance: 130,
  maxSpeed: 0.45,
  minRadius: 1.1,
  maxRadius: 2.4,
  mouseRadius: 130,
  mouseForce: 0.9
}
let pParticles: any[] = []
let pCtx: CanvasRenderingContext2D | null = null
let pWidth = 0, pHeight = 0
let pMouseX = -9999, pMouseY = -9999
let pRafId = 0
let pLastResize = 0

function applyThemeState() {
  if (darkTheme.value) {
    P_CONFIG.color = '255, 255, 255'
    P_CONFIG.dotAlpha = 0.85
    P_CONFIG.linkAlphaMax = 0.25
    P_CONFIG.density = 8000
  } else {
    P_CONFIG.color = '16, 185, 129'
    P_CONFIG.dotAlpha = 0.55
    P_CONFIG.linkAlphaMax = 0.35
    P_CONFIG.density = 12000
  }
}

function pResize() {
  const now = performance.now()
  if (now - pLastResize < 100) return
  pLastResize = now
  if (!particlesCanvas.value) return
  const dpr = Math.min(window.devicePixelRatio || 1, 2)
  pWidth = window.innerWidth
  pHeight = window.innerHeight
  particlesCanvas.value.width = pWidth * dpr
  particlesCanvas.value.height = pHeight * dpr
  particlesCanvas.value.style.width = pWidth + 'px'
  particlesCanvas.value.style.height = pHeight + 'px'
  if (pCtx) pCtx.setTransform(dpr, 0, 0, dpr, 0, 0)
  pInitParticles()
}

function pInitParticles() {
  if (!pCtx) return
  const count = Math.max(20, Math.floor((pWidth * pHeight) / P_CONFIG.density))
  pParticles = []
  for (let i = 0; i < count; i++) {
    pParticles.push({
      x: Math.random() * pWidth,
      y: Math.random() * pHeight,
      vx: (Math.random() - 0.5) * P_CONFIG.maxSpeed * 2,
      vy: (Math.random() - 0.5) * P_CONFIG.maxSpeed * 2,
      r: P_CONFIG.minRadius + Math.random() * (P_CONFIG.maxRadius - P_CONFIG.minRadius)
    })
  }
}

function pDraw() {
  pRafId = requestAnimationFrame(pDraw)
  if (!pCtx) return
  pCtx.clearRect(0, 0, pWidth, pHeight)

  for (const p of pParticles) {
    const dx = p.x - pMouseX
    const dy = p.y - pMouseY
    const dist = Math.sqrt(dx * dx + dy * dy)
    if (dist < P_CONFIG.mouseRadius && dist > 0.01) {
      const force = (1 - dist / P_CONFIG.mouseRadius) * P_CONFIG.mouseForce
      p.vx += (dx / dist) * force * 0.05
      p.vy += (dy / dist) * force * 0.05
    }
    p.vx *= 0.985
    p.vy *= 0.985
    p.x += p.vx
    p.y += p.vy
    if (p.x < 0) p.x = pWidth
    if (p.x > pWidth) p.x = 0
    if (p.y < 0) p.y = pHeight
    if (p.y > pHeight) p.y = 0
  }

  const ld = P_CONFIG.linkDistance
  for (let i = 0; i < pParticles.length; i++) {
    for (let j = i + 1; j < pParticles.length; j++) {
      const a = pParticles[i]
      const b = pParticles[j]
      const dx = a.x - b.x
      const dy = a.y - b.y
      const d2 = dx * dx + dy * dy
      if (d2 < ld * ld) {
        const alpha = (1 - Math.sqrt(d2) / ld) * P_CONFIG.linkAlphaMax
        pCtx.strokeStyle = `rgba(${P_CONFIG.color}, ${alpha})`
        pCtx.lineWidth = 1
        pCtx.beginPath()
        pCtx.moveTo(a.x, a.y)
        pCtx.lineTo(b.x, b.y)
        pCtx.stroke()
      }
    }
  }

  pCtx.fillStyle = `rgba(${P_CONFIG.color}, ${P_CONFIG.dotAlpha})`
  for (const p of pParticles) {
    pCtx.beginPath()
    pCtx.arc(p.x, p.y, p.r, 0, Math.PI * 2)
    pCtx.fill()
  }
}

function pOnMouseMove(e: MouseEvent) {
  pMouseX = e.clientX
  pMouseY = e.clientY
}
function pOnMouseLeave() {
  pMouseX = -9999
  pMouseY = -9999
}

onMounted(async () => {
  await nextTick()
  applyThemeState()
  if (particlesCanvas.value) {
    pCtx = particlesCanvas.value.getContext('2d')
    pResize()
    pDraw()
    window.addEventListener('resize', pResize)
    window.addEventListener('pointermove', pOnMouseMove)
    window.addEventListener('pointerleave', pOnMouseLeave)
  }
})

onBeforeUnmount(() => {
  cancelAnimationFrame(pRafId)
  window.removeEventListener('resize', pResize)
  window.removeEventListener('pointermove', pOnMouseMove)
  window.removeEventListener('pointerleave', pOnMouseLeave)
})
</script>

<style scoped>
.eco-page {
  position: fixed;
  inset: 0;
  width: 100vw;
  height: 100vh;
  overflow: hidden;
  background: #FFFFFF;
  transition: background 0.5s ease;
}
.eco-page.dark-theme {
  background: #0a0e1a;
}

/* 粒子背景 */
.magic-particles {
  position: fixed;
  inset: 0;
  width: 100%;
  height: 100%;
  z-index: 0;
  pointer-events: none;
}
.eco-page.dark-theme .magic-particles {
  filter: drop-shadow(0 0 2px rgba(255, 255, 255, 0.4));
}

/* 顶部标题栏 */
.eco-header {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  z-index: 10;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 32px;
  pointer-events: none;
}
.eco-header > * { pointer-events: auto; }
.eco-back {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  border: 1px solid #E5E7EB;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.8);
  color: #6B7280;
  font-size: 13px;
  cursor: pointer;
  backdrop-filter: blur(8px);
  transition: all 0.2s ease;
}
.eco-back:hover {
  border-color: #FF2442;
  color: #FF2442;
}
.dark-theme .eco-back {
  background: rgba(30, 41, 59, 0.7);
  border-color: rgba(148, 163, 184, 0.2);
  color: #CBD5E1;
}
.dark-theme .eco-back:hover {
  border-color: #60A5FA;
  color: #60A5FA;
}
.eco-title-block {
  text-align: center;
}
.eco-title {
  font-size: 22px;
  font-weight: 600;
  color: #111827;
  letter-spacing: -0.01em;
  margin: 0;
}
.eco-subtitle {
  margin: 4px 0 0;
  font-size: 13px;
  color: #6B7280;
}
.dark-theme .eco-title { color: #F1F5F9; }
.dark-theme .eco-subtitle { color: #94A3B8; }
.eco-theme-toggle {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: 12px;
  border: 1px solid #E5E7EB;
  background: rgba(255, 255, 255, 0.8);
  color: #6B7280;
  cursor: pointer;
  backdrop-filter: blur(8px);
  transition: all 0.2s ease;
}
.eco-theme-toggle:hover {
  border-color: #FF2442;
  color: #FF2442;
}
.dark-theme .eco-theme-toggle {
  background: rgba(30, 41, 59, 0.7);
  border-color: rgba(148, 163, 184, 0.2);
  color: #CBD5E1;
}

/* 球体舞台：居中铺满 */
.eco-stage {
  position: absolute;
  inset: 0;
  z-index: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}

/* 底部提示 */
.eco-footer {
  position: absolute;
  bottom: 24px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 10;
  padding: 8px 18px;
  background: rgba(255, 255, 255, 0.85);
  border: 1px solid #E5E7EB;
  border-radius: 999px;
  backdrop-filter: blur(8px);
  font-size: 12px;
  color: #6B7280;
}
.dark-theme .eco-footer {
  background: rgba(30, 41, 59, 0.75);
  border-color: rgba(148, 163, 184, 0.15);
  color: #94A3B8;
}

/* ============ 小红书风格组件 ============ */

/* 顶部操作组 */
.eco-header-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

/* 点赞按钮（小红书红心） */
.eco-like-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  border: 1px solid #E5E7EB;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.9);
  color: #6B7280;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  backdrop-filter: blur(8px);
  transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1);
}
.eco-like-btn:hover {
  border-color: #FF2442;
  color: #FF2442;
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(255, 36, 66, 0.15);
}
.eco-like-btn.liked {
  background: linear-gradient(135deg, #FF2442 0%, #FF2442 100%);
  border-color: transparent;
  color: #fff;
  box-shadow: 0 4px 14px rgba(255, 36, 66, 0.35);
}
.eco-like-btn.liked:hover {
  transform: translateY(-1px) scale(1.02);
  box-shadow: 0 6px 18px rgba(255, 36, 66, 0.45);
}
.eco-like-count {
  font-variant-numeric: tabular-nums;
  font-weight: 600;
}
.dark-theme .eco-like-btn {
  background: rgba(30, 41, 59, 0.7);
  border-color: rgba(148, 163, 184, 0.2);
  color: #CBD5E1;
}
.dark-theme .eco-like-btn:hover {
  border-color: #FF2442;
  color: #FF2442;
}
.dark-theme .eco-like-btn.liked {
  background: linear-gradient(135deg, #FF2442 0%, #FF2442 100%);
  color: #fff;
}

/* 返回按钮 hover 改小红书红 */
.eco-back:hover {
  border-color: #FF2442;
  color: #FF2442;
}
.dark-theme .eco-back:hover {
  border-color: #FF2442;
  color: #FF2442;
}

/* 主题切换 hover 改粉色 */
.eco-theme-toggle:hover {
  border-color: #FF2442;
  color: #FF2442;
}

/* 右下角 CTA 卡片（小红书风格） */
.eco-cta-card {
  position: absolute;
  right: 32px;
  bottom: 80px;
  z-index: 10;
  width: 240px;
  padding: 18px 20px;
  background: rgba(255, 255, 255, 0.95);
  border: 1px solid rgba(255, 36, 66, 0.12);
  border-radius: 16px;
  backdrop-filter: blur(12px);
  box-shadow: 0 8px 32px rgba(255, 36, 66, 0.10), 0 2px 8px rgba(0, 0, 0, 0.04);
  animation: eco-cta-in 0.6s cubic-bezier(0.16, 1, 0.3, 1) 0.3s both;
}
@keyframes eco-cta-in {
  from { opacity: 0; transform: translateY(20px) scale(0.95); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}
.eco-cta-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}
.eco-cta-tag {
  display: inline-block;
  padding: 3px 10px;
  background: linear-gradient(135deg, #FF2442 0%, #FF2442 100%);
  color: #fff;
  font-size: 11px;
  font-weight: 600;
  border-radius: 999px;
  letter-spacing: 0.02em;
}
.eco-cta-live {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: #FF2442;
  font-weight: 500;
}
.eco-cta-live::before {
  content: '';
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #FF2442;
  box-shadow: 0 0 6px #FF2442;
  animation: eco-live-pulse 1.5s ease-in-out infinite;
}
@keyframes eco-live-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}
.eco-cta-title {
  font-size: 16px;
  font-weight: 700;
  color: #111827;
  margin-bottom: 4px;
  letter-spacing: -0.01em;
}
.eco-cta-desc {
  font-size: 12px;
  color: #6B7280;
  margin-bottom: 14px;
}
.eco-cta-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  width: 100%;
  padding: 10px 16px;
  background: linear-gradient(135deg, #FF2442 0%, #FF2442 100%);
  color: #fff;
  border: none;
  border-radius: 999px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1);
  box-shadow: 0 4px 14px rgba(255, 36, 66, 0.30);
}
.eco-cta-btn:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 22px rgba(255, 36, 66, 0.40);
}
.eco-cta-btn:active {
  transform: translateY(0);
}

.dark-theme .eco-cta-card {
  background: rgba(30, 41, 59, 0.92);
  border-color: rgba(255, 107, 122, 0.20);
  box-shadow: 0 8px 32px rgba(255, 36, 66, 0.15), 0 2px 8px rgba(0, 0, 0, 0.3);
}
.dark-theme .eco-cta-title { color: #F1F5F9; }
.dark-theme .eco-cta-desc { color: #94A3B8; }

@media (max-width: 1024px) {
  .eco-cta-card { right: 16px; bottom: 70px; width: 200px; padding: 14px 16px; }
}
</style>