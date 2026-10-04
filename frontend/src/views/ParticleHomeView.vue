<template>
  <div class="ph" ref="phRoot">
    <canvas ref="canvas" class="ph-canvas"></canvas>

    <header class="ph-header">
      <div class="ph-header-inner">
        <div class="ph-logo" @click="router.push('/')">
          <span class="ph-logo-main">Pulse</span><span class="ph-logo-accent">Studio</span>
        </div>
        <nav class="ph-nav">
          <a href="#features" class="ph-nav-link">功能</a>
          <a href="#workflow" class="ph-nav-link">工作流</a>
          <a href="#pricing" class="ph-nav-link">定价</a>
        </nav>
        <div class="ph-header-actions">
          <button class="ph-btn-ghost" @click="router.push('/login?force=true')">登录</button>
          <button class="ph-btn-primary" @click="router.push('/login?register=true&force=true')">开始创作</button>
        </div>
      </div>
    </header>

    <section class="ph-hero">
      <p class="ph-tagline">A THREAD THROUGH THE MAZE OF CONTENT</p>
      <h1 class="ph-title">Pulse<span class="ph-title-glow">Studio</span></h1>
      <p class="ph-desc-zh">多智能体内容创作与发布平台</p>
      <p class="ph-desc-en">Multi-Agent Content Orchestration · Purpose-driven Publishing Pipeline</p>

      <div class="ph-pills">
        <span class="ph-pill">Agent 对话创作</span>
        <span class="ph-pill">DAG 工作流引擎</span>
        <span class="ph-pill">HotRank 热点追踪</span>
        <span class="ph-pill">MCP 平台接入</span>
      </div>

      <div class="ph-actions">
        <button class="ph-btn-primary ph-btn-xl" @click="router.push('/login?register=true&force=true')">
          免费开始创作
        </button>
        <button class="ph-btn-ghost ph-btn-xl" @click="scrollDown">向下滚动探索</button>
      </div>
    </section>

    <div class="ph-scroll-hint" @click="scrollDown">
      <div class="ph-scroll-arrow">↓</div>
      <span>向下滚动探索架构</span>
      <p class="ph-scroll-sub">移动鼠标与粒子互动 · 滚轮缩放 · 拖拽旋转</p>
    </div>

    <section id="features" class="ph-section ph-section-dark">
      <div class="ph-container">
        <h2 class="ph-section-title">核心能力</h2>
        <div class="ph-grid">
          <div class="ph-card" v-for="(f, i) in features" :key="i">
            <div class="ph-card-icon" :style="{ background: f.grad }">{{ f.icon }}</div>
            <h3>{{ f.title }}</h3>
            <p>{{ f.desc }}</p>
          </div>
        </div>
      </div>
    </section>

    <section id="workflow" class="ph-section">
      <div class="ph-container">
        <h2 class="ph-section-title">创作工作流</h2>
        <p class="ph-section-sub">从灵感到发布，五个阶段零摩擦衔接</p>
        <div class="ph-pipeline">
          <div class="ph-step" v-for="(s, i) in steps" :key="i">
            <div class="ph-step-num">{{ String(i+1).padStart(2,'0') }}</div>
            <div class="ph-step-dot"></div>
            <strong>{{ s.name }}</strong>
            <span>{{ s.desc }}</span>
          </div>
          <div class="ph-line-track"><div class="ph-line-fill"></div></div>
        </div>
      </div>
    </section>

    <footer class="ph-footer">
      <p>&copy; 2026 Pulse Studio. All rights reserved.</p>
    </footer>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()
const canvas = ref<HTMLCanvasElement | null>(null)

const features = [
  { icon: '💬', title: 'AI 对话式创作', desc: '像聊天一样自然地指挥 AI 团队完成创作', grad: 'linear-gradient(135deg,#A78BFA,#818CF8)' },
  { icon: '🤖', title: '多智能体协作', desc: '洞察、文案、视觉、审核各司其职无缝衔接', grad: 'linear-gradient(135deg,#818CF8,#6366F1)' },
  { icon: '🔗', title: '可视化工作流', desc: '拖拽连接搭建你的创作流水线', grad: 'linear-gradient(135deg,#6EE7B7,#34D399)' },
  { icon: '🚀', title: '一键发布', desc: '定时或即时发布到内容平台', grad: 'linear-gradient(135deg,#34D399,#10B981)' },
]

const steps = [
  { name: '洞察', desc: '热点发现 & 角度推荐' },
  { name: '视觉', desc: 'AI 图片生成 & 批量输出' },
  { name: '撰写', desc: '多风格文案 & 标签生成' },
  { name: '审核', desc: '合规检查 & 质量评分' },
  { name: '发布', desc: '定时发布 & 格式适配' },
]

function scrollDown() {
  document.getElementById('features')?.scrollIntoView({ behavior: 'smooth' })
}

interface V3 { x: number; y: number; z: number }

interface Particle {
  x: number; y: number; z: number
  vx: number; vy: number; vz: number
  ox: number; oy: number; oz: number
  r: number
  color: string
  phase: number
}

const PALETTE = [
  '#A78BFA','#8B5CF6','#818CF8','#6366F1',
  '#6EE7B7','#34D399','#10B981',
  '#06B6D4','#22D3EE','#67E8F9',
  '#EC4899','#F472B6','#FB7185',
]

let pts: Particle[] = []
let rafId = 0
let W = 0
let H = 0
let time = 0

const mouse = { sx: -9999, sy: -9999, active: false }
const cam = { rx: 0.18, ry: 0, zoom: 1, px: 0, py: 0 }
let dragging = false
let dragBtn = -1
let prevMx = 0
let prevMy = 0

function init(w: number, h: number) {
  W = w; H = h
  pts = []
  const n = Math.min(Math.floor(w * h / 5500), 160)
  for (let i = 0; i < n; i++) {
    const x = (Math.random() - 0.5) * w * 1.5
    const y = (Math.random() - 0.5) * h * 1.5
    const z = (Math.random() - 0.5) * 800
    const speed = 0.15 + Math.random() * 0.35
    const angle = Math.random() * Math.PI * 2
    const angleV = (Math.random() - 0.5) * 0.2
    pts.push({
      x, y, z,
      vx: Math.cos(angle) * speed,
      vy: Math.sin(angle) * speed,
      vz: Math.sin(angleV) * speed * 0.3,
      ox: x, oy: y, oz: z,
      r: 3 + Math.pow(Math.random(), 0.4) * 16,
      color: PALETTE[Math.floor(Math.random() * PALETTE.length)],
      phase: Math.random() * Math.PI * 2,
    })
  }
}

function rot3(p: V3): V3 {
  let { x, y, z } = p
  x -= cam.px; y -= cam.py
  const cx = Math.cos(cam.rx), sx = Math.sin(cam.rx)
  const cy = Math.cos(cam.ry), sy = Math.sin(cam.ry)
  const y1 = y * cx - z * sx
  const z1 = y * sx + z * cx
  const x1 = x * cy + z1 * sy
  const z2 = -x * sy + z1 * cy
  return { x: x1, y: y1, z: z2 }
}

function proj(p: V3): { sx: number; sy: number; sc: number; a: number } | null {
  const r = rot3(p)
  const d = 900
  const sc = d / (d + r.z) * cam.zoom
  if (sc < 0.01) return null
  return {
    sx: W / 2 + r.x * sc,
    sy: H / 2 + r.y * sc,
    sc,
    a: Math.max(0, Math.min(1, (r.z + 700) / 1400)),
  }
}

function unproj(sx: number, sy: number): V3 {
  const nx = (sx - W / 2) / cam.zoom
  const ny = (sy - H / 2) / cam.zoom
  const cy = Math.cos(-cam.ry), sY = Math.sin(-cam.ry)
  const cx = Math.cos(-cam.rx), sX = Math.sin(-cam.rx)
  const x1 = nx * cy
  const z1 = -nx * sY
  const y = ny * cx - z1 * sX
  const z = ny * sX + z1 * cx
  return { x: x1 + cam.px, y: y + cam.py, z }
}

function physics() {
  time += 0.016
  const mw = mouse.active ? unproj(mouse.sx, mouse.sy) : null
  const MOUSE_R = 220
  const MOUSE_STRENGTH = 0.6
  const BROWNIAN = 0.04
  const DRIFT = 0.003
  const DAMPING = 0.985
  const BOUND = 700
  const BOUND_Z = 450
  const BOUND_FORCE = 0.08

  for (const p of pts) {
    if (mw) {
      const dx = mw.x - p.x
      const dy = mw.y - p.y
      const dz = mw.z * 0.3 - p.z * 0.3
      const dist = Math.sqrt(dx * dx + dy * dy + dz * dz)
      if (dist < MOUSE_R && dist > 1) {
        const t = 1 - dist / MOUSE_R
        const f = t * t * MOUSE_STRENGTH
        const inv = 1 / dist
        p.vx += dx * inv * f
        p.vy += dy * inv * f
        p.vz += dz * inv * f * 0.3
      }
    }

    p.vx += (Math.random() - 0.5) * BROWNIAN
    p.vy += (Math.random() - 0.5) * BROWNIAN
    p.vz += (Math.random() - 0.5) * BROWNIAN * 0.3

    p.vx += Math.sin(time * 0.7 + p.phase) * DRIFT
    p.vy += Math.cos(time * 0.5 + p.phase * 1.3) * DRIFT
    p.vz += Math.sin(time * 0.3 + p.phase * 0.7) * DRIFT * 0.3

    p.vx += (p.ox - p.x) * 0.0008
    p.vy += (p.oy - p.y) * 0.0008
    p.vz += (p.oz - p.z) * 0.0004

    if (p.x > BOUND) p.vx -= BOUND_FORCE * ((p.x - BOUND) / 100)
    if (p.x < -BOUND) p.vx -= BOUND_FORCE * ((p.x + BOUND) / 100)
    if (p.y > BOUND) p.vy -= BOUND_FORCE * ((p.y - BOUND) / 100)
    if (p.y < -BOUND) p.vy -= BOUND_FORCE * ((p.y + BOUND) / 100)
    if (p.z > BOUND_Z) p.vz -= BOUND_FORCE * ((p.z - BOUND_Z) / 100)
    if (p.z < -BOUND_Z) p.vz -= BOUND_FORCE * ((p.z + BOUND_Z) / 100)

    p.vx *= DAMPING
    p.vy *= DAMPING
    p.vz *= DAMPING

    p.x += p.vx
    p.y += p.vy
    p.z += p.vz
  }
}

function render(ctx: CanvasRenderingContext2D) {
  ctx.fillStyle = '#09080F'
  ctx.fillRect(0, 0, W, H)

  const items = pts
    .map(p => ({ p, pr: proj({ x: p.x, y: p.y, z: p.z }) }))
    .filter(x => x.pr !== null) as { p: Particle; pr: NonNullable<ReturnType<typeof proj>> }[]

  items.sort((a, b) => rot3({ x: b.p.x, y: b.p.y, z: b.p.z }).z - rot3({ x: a.p.x, y: a.p.y, z: a.p.z }).z)

  const LINK = 180
  for (let i = 0; i < items.length; i++) {
    const pi = items[i]
    for (let j = i + 1; j < items.length; j++) {
      const pj = items[j]
      const dx = pi.pr.sx - pj.pr.sx
      const dy = pi.pr.sy - pj.pr.sy
      const d = Math.sqrt(dx * dx + dy * dy)
      if (d < LINK) {
        const a = (1 - d / LINK) * 0.12 * Math.min(pi.pr.a, pj.pr.a)
        ctx.strokeStyle = `rgba(130,120,175,${a})`
        ctx.lineWidth = 0.8
        ctx.beginPath()
        ctx.moveTo(pi.pr.sx, pi.pr.sy)
        ctx.lineTo(pj.pr.sx, pj.pr.sy)
        ctx.stroke()
      }
    }
  }

  for (const { p, pr } of items) {
    const radius = p.r * pr.sc
    if (radius < 0.4 || pr.a < 0.02) continue

    const hex = p.color
    const rr = parseInt(hex.slice(1, 3), 16)
    const gg = parseInt(hex.slice(3, 5), 16)
    const bb = parseInt(hex.slice(5, 7), 16)

    const grd = ctx.createRadialGradient(pr.sx, pr.sy, 0, pr.sx, pr.sy, radius)
    grd.addColorStop(0, `rgba(${rr},${gg},${bb},${pr.a * 0.92})`)
    grd.addColorStop(0.5, `rgba(${rr},${gg},${bb},${pr.a * 0.4})`)
    grd.addColorStop(1, `rgba(${rr},${gg},${bb},0)`)

    ctx.beginPath()
    ctx.arc(pr.sx, pr.sy, radius, 0, Math.PI * 2)
    ctx.fillStyle = grd
    ctx.fill()
  }
}

function frame(ctx: CanvasRenderingContext2D) {
  physics()
  render(ctx)
  rafId = requestAnimationFrame(() => frame(ctx))
}

onMounted(() => {
  const c = canvas.value
  if (!c) return
  const ctx = c.getContext('2d')
  if (!ctx) return

  function resize() {
    const dpr = window.devicePixelRatio || 1
    W = window.innerWidth
    H = window.innerHeight
    c!.width = W * dpr
    c!.height = H * dpr
    c!.style.width = W + 'px'
    c!.style.height = H + 'px'
    ctx!.setTransform(dpr, 0, 0, dpr, 0, 0)
    init(W, H)
  }
  resize()
  window.addEventListener('resize', resize)

  window.addEventListener('mousemove', e => {
    mouse.sx = e.clientX
    mouse.sy = e.clientY
    mouse.active = true

    if (dragging) {
      const dx = e.clientX - prevMx
      const dy = e.clientY - prevMy
      if (dragBtn === 0) {
        cam.ry += dx * 0.004
        cam.rx += dy * 0.004
        cam.rx = Math.max(-1.2, Math.min(1.2, cam.rx))
      } else if (dragBtn === 2) {
        cam.px -= dx / cam.zoom
        cam.py -= dy / cam.zoom
      }
      prevMx = e.clientX
      prevMy = e.clientY
    }
  })

  window.addEventListener('mousedown', e => {
    if (e.target === c) {
      dragging = true
      dragBtn = e.button
      prevMx = e.clientX
      prevMy = e.clientY
    }
  })
  window.addEventListener('mouseup', () => { dragging = false })
  window.addEventListener('mouseleave', () => { mouse.active = false; dragging = false })

  c.addEventListener('contextmenu', e => e.preventDefault())
  c.addEventListener('wheel', e => {
    e.preventDefault()
    cam.zoom *= e.deltaY > 0 ? 0.94 : 1.065
    cam.zoom = Math.max(0.25, Math.min(3.5, cam.zoom))
  }, { passive: false })

  frame(ctx)

  onUnmounted(() => {
    cancelAnimationFrame(rafId)
    window.removeEventListener('resize', resize)
  })
})
</script>

<style scoped>
.ph {
  min-height: 100vh;
  background: #09080F;
  color: #E8E6F0;
  position: relative;
  overflow-x: hidden;
}
.ph-canvas {
  position: fixed;
  inset: 0;
  width: 100%;
  height: 100%;
  z-index: 0;
}

.ph-header {
  position: fixed;
  top: 0; left: 0; right: 0;
  z-index: 100;
  padding: 16px 40px;
  background: rgba(9,8,15,0.55);
  backdrop-filter: blur(24px);
  border-bottom: 1px solid rgba(140,130,180,0.06);
}
.ph-header-inner {
  max-width: 1320px;
  margin: 0 auto;
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.ph-logo { cursor: pointer; display: flex; align-items: baseline; gap: 2px; }
.ph-logo-main {
  font-size: 20px;
  font-weight: 800;
  color: #fff;
  letter-spacing: -0.02em;
}
.ph-logo-accent {
  font-size: 20px;
  font-weight: 800;
  background: linear-gradient(135deg,#A78BFA 0%,#6EE7B7 50%,#22D3EE 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}
.ph-nav { display: flex; gap: 32px; }
.ph-nav-link {
  font-size: 14px;
  color: rgba(232,230,240,0.45);
  text-decoration: none;
  transition: color 0.25s;
}
.ph-nav-link:hover { color: #A78BFA; }
.ph-header-actions { display: flex; gap: 12px; }

.ph-btn-primary {
  padding: 9px 24px;
  border-radius: 9999px;
  border: none;
  background: linear-gradient(135deg,#A78BFA,#818CF8);
  color: #fff;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.25s;
}
.ph-btn-primary:hover {
  box-shadow: 0 0 32px rgba(167,139,250,0.4);
  transform: translateY(-1px);
}
.ph-btn-outline {
  padding: 9px 24px;
  border-radius: 9999px;
  border: 1px solid rgba(140,130,180,0.18);
  background: transparent;
  color: #E8E6F0;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.25s;
}
.ph-btn-outline:hover {
  border-color: rgba(167,139,250,0.35);
  background: rgba(167,139,250,0.05);
}
.ph-btn-ghost {
  padding: 9px 20px;
  border-radius: 9999px;
  border: none;
  background: transparent;
  color: rgba(232,230,240,0.5);
  font-size: 14px;
  cursor: pointer;
  transition: color 0.25s;
}
.ph-btn-ghost:hover { color: #A78BFA; }
.ph-btn-xl { padding: 14px 36px; font-size: 15px; }

.ph-hero {
  position: relative;
  z-index: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  text-align: center;
  padding: 0 28px;
  padding-top: 80px;
  pointer-events: none;
}
.ph-hero > * { pointer-events: auto; }
.ph-tagline {
  font-size: 11px;
  letter-spacing: 0.38em;
  text-transform: uppercase;
  color: #6EE7B7;
  margin-bottom: 28px;
  opacity: 0.85;
  font-weight: 500;
}
.ph-title {
  font-size: clamp(56px, 12vw, 120px);
  font-weight: 800;
  letter-spacing: -0.045em;
  line-height: 1;
  margin-bottom: 26px;
  color: #fff;
}
.ph-title-glow {
  background: linear-gradient(135deg,#A78BFA 0%,#6EE7B7 50%,#22D3EE 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}
.ph-desc-zh {
  font-size: 17px;
  color: rgba(232,230,240,0.55);
  margin-bottom: 6px;
  font-weight: 400;
}
.ph-desc-en {
  font-size: 13px;
  color: rgba(232,230,240,0.3);
  margin-bottom: 44px;
  font-weight: 300;
  letter-spacing: 0.02em;
}

.ph-pills {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  justify-content: center;
  margin-bottom: 48px;
}
.ph-pill {
  padding: 8px 22px;
  border-radius: 9999px;
  border: 1px solid rgba(140,130,180,0.12);
  background: rgba(140,130,180,0.03);
  backdrop-filter: blur(10px);
  font-size: 13px;
  color: rgba(232,230,240,0.65);
}
.ph-actions {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
  justify-content: center;
}

.ph-scroll-hint {
  position: absolute;
  bottom: 32px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 2;
  text-align: center;
  cursor: pointer;
  opacity: 0.4;
  transition: opacity 0.3s;
  pointer-events: auto;
}
.ph-scroll-hint:hover { opacity: 0.75; }
.ph-scroll-arrow {
  font-size: 18px;
  color: rgba(232,230,240,0.5);
  margin-bottom: 4px;
  animation: bounce 2s ease-in-out infinite;
}
@keyframes bounce {
  0%,100% { transform: translateY(0); }
  50% { transform: translateY(6px); }
}
.ph-scroll-hint > span {
  display: block;
  font-size: 13px;
  color: rgba(232,230,240,0.5);
  margin-bottom: 4px;
}
.ph-scroll-sub {
  font-size: 11px;
  color: rgba(232,230,240,0.25);
  margin: 0;
}

.ph-section {
  position: relative;
  z-index: 1;
  padding: 110px 40px;
}
.ph-section-dark {
  background: rgba(9,8,15,0.7);
  backdrop-filter: blur(20px);
}
.ph-container {
  max-width: 1100px;
  margin: 0 auto;
}
.ph-section-title {
  font-size: 38px;
  font-weight: 700;
  text-align: center;
  color: #fff;
  margin-bottom: 60px;
}
.ph-section-sub {
  font-size: 15px;
  text-align: center;
  color: rgba(232,230,240,0.45);
  margin-top: -44px;
  margin-bottom: 56px;
}

.ph-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit,minmax(240px,1fr));
  gap: 20px;
}
.ph-card {
  padding: 30px 24px;
  border-radius: 18px;
  background: rgba(140,130,180,0.025);
  border: 1px solid rgba(140,130,180,0.07);
  backdrop-filter: blur(10px);
  transition: all 0.3s;
}
.ph-card:hover {
  border-color: rgba(167,139,250,0.2);
  background: rgba(140,130,180,0.05);
  transform: translateY(-3px);
}
.ph-card-icon {
  width: 46px; height: 46px;
  border-radius: 13px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 21px;
  margin-bottom: 18px;
}
.ph-card h3 {
  font-size: 17px;
  font-weight: 600;
  color: #E8E6F0;
  margin-bottom: 8px;
}
.ph-card p {
  font-size: 13px;
  color: rgba(232,230,240,0.45);
  line-height: 1.65;
}

.ph-pipeline {
  position: relative;
  display: flex;
  justify-content: space-between;
  padding: 34px 0 56px;
}
.ph-step {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  width: 130px;
  z-index: 2;
}
.ph-step-num {
  font-size: 11px;
  font-weight: 600;
  color: rgba(167,139,250,0.45);
  margin-bottom: 10px;
  letter-spacing: 0.12em;
}
.ph-step-dot {
  width: 15px; height: 15px;
  border-radius: 50%;
  background: linear-gradient(135deg,#A78BFA,#6EE7B7);
  margin-bottom: 16px;
  box-shadow: 0 0 20px rgba(167,139,250,0.35);
}
.ph-step strong {
  display: block;
  font-size: 15px;
  font-weight: 600;
  color: #E8E6F0;
  margin-bottom: 4px;
}
.ph-step span {
  font-size: 12px;
  color: rgba(232,230,240,0.38);
}
.ph-line-track {
  position: absolute;
  top: 54px;
  left: 70px;
  right: 70px;
  height: 2px;
  background: rgba(140,130,180,0.08);
  overflow: hidden;
  border-radius: 1px;
}
.ph-line-fill {
  width: 70px;
  height: 100%;
  background: linear-gradient(90deg,transparent,#A78BFA,#6EE7B7,transparent);
  border-radius: 1px;
  animation: flow 3.5s linear infinite;
}
@keyframes flow {
  0% { transform: translateX(-70px); }
  100% { transform: translateX(calc(100% + 70px)); }
}

.ph-footer {
  position: relative;
  z-index: 1;
  text-align: center;
  padding: 48px 24px;
  border-top: 1px solid rgba(140,130,180,0.05);
}
.ph-footer p {
  font-size: 13px;
  color: rgba(232,230,240,0.25);
}

@media (max-width: 768px) {
  .ph-nav { display: none; }
  .ph-title { font-size: 42px; }
  .ph-section { padding: 70px 20px; }
  .ph-pipeline { flex-wrap: wrap; gap: 24px; justify-content: center; }
  .ph-line-track { display: none; }
  .ph-header { padding: 12px 20px; }
}
</style>