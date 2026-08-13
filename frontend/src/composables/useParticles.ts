import { ref, type Ref } from 'vue'

// 粒子结构：位置 / 速度 / 半径
interface PParticle { x: number; y: number; vx: number; vy: number; r: number }

/**
 * Magic UI Particles 背景：canvas 粒子 + 连线 + 鼠标交互
 *
 * 从 WorkbenchView.vue 中抽出的 915 行粒子动画逻辑。
 * 接收 darkTheme ref 实现主题联动，返回 canvas ref 和生命周期函数。
 */
export function useParticles(darkTheme: Ref<boolean>) {
  const particlesCanvas = ref<HTMLCanvasElement | null>(null)
  let pCtx: CanvasRenderingContext2D | null = null
  let pRafId = 0
  let pWidth = 0
  let pHeight = 0
  let pDpr = 1
  let pMouseX = -9999
  let pMouseY = -9999
  let pParticles: PParticle[] = []

  // 可调参数
  const P_CONFIG = {
    density: 12000,      // 每多少平方像素一个粒子（越小越密）
    maxSpeed: 0.35,      // 初始最大速度
    minRadius: 0.6,      // 最小半径
    maxRadius: 1.8,      // 最大半径
    linkDistance: 130,   // 连线最大距离
    mouseRadius: 160,    // 鼠标影响半径
    mouseForce: 0.6,     // 鼠标排斥力度
    color: '16, 185, 129', // mint 主色 rgb
    dotAlpha: 0.55,      // 粒子透明度
    linkAlphaMax: 0.35,  // 连线最大透明度
  }

  /** 同步粒子颜色配置（绘制函数每帧读取 P_CONFIG） */
  function applyThemeState() {
    if (darkTheme.value) {
      P_CONFIG.color = '255, 255, 255'   // 星光白
      P_CONFIG.dotAlpha = 0.85           // 提亮
      P_CONFIG.linkAlphaMax = 0.25       // 连线淡白
      P_CONFIG.density = 8000            // 增加密度造星空
    } else {
      P_CONFIG.color = '16, 185, 129'    // mint 主色
      P_CONFIG.dotAlpha = 0.55
      P_CONFIG.linkAlphaMax = 0.35
      P_CONFIG.density = 12000
    }
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
        r: P_CONFIG.minRadius + Math.random() * (P_CONFIG.maxRadius - P_CONFIG.minRadius),
      })
    }
  }

  function pResize() {
    if (!particlesCanvas.value) return
    const parent = particlesCanvas.value.parentElement
    if (!parent) return
    const rect = parent.getBoundingClientRect()
    pDpr = Math.min(window.devicePixelRatio || 1, 2)
    pWidth = rect.width
    pHeight = rect.height
    particlesCanvas.value.width = pWidth * pDpr
    particlesCanvas.value.height = pHeight * pDpr
    particlesCanvas.value.style.width = pWidth + 'px'
    particlesCanvas.value.style.height = pHeight + 'px'
    if (pCtx) pCtx.setTransform(pDpr, 0, 0, pDpr, 0, 0)
    pInitParticles()
  }

  function pStep() {
    if (!pCtx) return
    pCtx.clearRect(0, 0, pWidth, pHeight)

    // 更新粒子位置 + 鼠标排斥
    for (let i = 0; i < pParticles.length; i++) {
      const p = pParticles[i]
      // 鼠标交互：在 mouseRadius 内的粒子被排斥
      const dx = p.x - pMouseX
      const dy = p.y - pMouseY
      const dist2 = dx * dx + dy * dy
      if (dist2 < P_CONFIG.mouseRadius * P_CONFIG.mouseRadius && dist2 > 0.01) {
        const dist = Math.sqrt(dist2)
        const force = (1 - dist / P_CONFIG.mouseRadius) * P_CONFIG.mouseForce
        p.vx += (dx / dist) * force
        p.vy += (dy / dist) * force
      }
      // 轻微阻尼，避免越来越快
      p.vx *= 0.985
      p.vy *= 0.985
      p.x += p.vx
      p.y += p.vy
      // 边界反弹
      if (p.x < 0) { p.x = 0; p.vx *= -1 }
      else if (p.x > pWidth) { p.x = pWidth; p.vx *= -1 }
      if (p.y < 0) { p.y = 0; p.vy *= -1 }
      else if (p.y > pHeight) { p.y = pHeight; p.vy *= -1 }
    }

    // 画连线（O(n²)，粒子数量受限，可接受）
    const ld = P_CONFIG.linkDistance
    const ld2 = ld * ld
    for (let i = 0; i < pParticles.length; i++) {
      const a = pParticles[i]
      for (let j = i + 1; j < pParticles.length; j++) {
        const b = pParticles[j]
        const dx = a.x - b.x
        const dy = a.y - b.y
        const d2 = dx * dx + dy * dy
        if (d2 < ld2) {
          const alpha = (1 - Math.sqrt(d2) / ld) * P_CONFIG.linkAlphaMax
          pCtx.strokeStyle = `rgba(${P_CONFIG.color}, ${alpha})`
          pCtx.lineWidth = 0.6
          pCtx.beginPath()
          pCtx.moveTo(a.x, a.y)
          pCtx.lineTo(b.x, b.y)
          pCtx.stroke()
        }
      }
    }

    // 画粒子
    pCtx.fillStyle = `rgba(${P_CONFIG.color}, ${P_CONFIG.dotAlpha})`
    for (let i = 0; i < pParticles.length; i++) {
      const p = pParticles[i]
      pCtx.beginPath()
      pCtx.arc(p.x, p.y, p.r, 0, Math.PI * 2)
      pCtx.fill()
    }

    pRafId = requestAnimationFrame(pStep)
  }

  function onParticlesPointerMove(e: PointerEvent) {
    if (!particlesCanvas.value) return
    const rect = particlesCanvas.value.getBoundingClientRect()
    pMouseX = e.clientX - rect.left
    pMouseY = e.clientY - rect.top
  }

  function onParticlesPointerLeave() {
    pMouseX = -9999
    pMouseY = -9999
  }

  /** 在 onMounted 中调用：初始化 canvas + 粒子 + 鼠标/resize 监听 + 启动动画 */
  function initParticles() {
    if (!particlesCanvas.value) return
    pCtx = particlesCanvas.value.getContext('2d')
    pResize()
    // canvas 自身 pointer-events:none 不接收事件，改由 mint-shell 父容器监听冒泡
    // 这样鼠标在卡片上移动时事件也能冒泡上来驱动粒子排斥
    const shell = particlesCanvas.value.parentElement
    if (shell) {
      shell.addEventListener('pointermove', onParticlesPointerMove)
      shell.addEventListener('pointerleave', onParticlesPointerLeave)
    }
    window.addEventListener('resize', pResize)
    pRafId = requestAnimationFrame(pStep)
  }

  /** 在 onUnmounted 中调用：清理 RAF + 事件监听 */
  function destroyParticles() {
    if (pRafId) cancelAnimationFrame(pRafId)
    window.removeEventListener('resize', pResize)
    if (particlesCanvas.value) {
      const shell = particlesCanvas.value.parentElement
      if (shell) {
        shell.removeEventListener('pointermove', onParticlesPointerMove)
        shell.removeEventListener('pointerleave', onParticlesPointerLeave)
      }
    }
  }

  // 初始化时同步粒子配置（须在 P_CONFIG 定义之后）
  applyThemeState()

  return {
    particlesCanvas,
    initParticles,
    destroyParticles,
    applyThemeState,
    reinitParticles: pInitParticles,
  }
}