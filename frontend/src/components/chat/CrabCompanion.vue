<template>
  <div
    class="crab-companion"
    :class="{
      'crab-visible': visible,
      'crab-hiding': isHiding,
      'crab-dragging': isDragging,
      'crab-peeks': isPeeking,
    }"
    :style="crabStyle"
    @mousedown.prevent="onDragStart"
    @touchstart.prevent="onTouchStart"
    @mouseenter="onMouseEnter"
    @mouseleave="onMouseLeave"
    @click="onCrabClick"
  >
    <svg
      class="crab-svg"
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 200 180"
    >
      <defs>
        <filter id="cc-shadow" x="-10%" y="-10%" width="120%" height="130%">
          <feDropShadow dx="0" dy="1" stdDeviation="1.5" flood-color="#000" flood-opacity="0.08"/>
        </filter>
      </defs>

      <g class="crab-body" filter="url(#cc-shadow)">
        <path d="M52,86 Q36,76 30,68" stroke="#D94F44" stroke-width="11" stroke-linecap="round" fill="none"/>
        <path d="M148,86 Q164,76 170,68" stroke="#D94F44" stroke-width="11" stroke-linecap="round" fill="none"/>
        <g>
          <ellipse cx="26" cy="56" rx="18" ry="11" transform="rotate(-45 26 56)" fill="#E8655A"/>
          <ellipse cx="42" cy="80" rx="16" ry="10" transform="rotate(15 42 80)" fill="#E8655A"/>
        </g>
        <g>
          <ellipse cx="174" cy="56" rx="18" ry="11" transform="rotate(45 174 56)" fill="#E8655A"/>
          <ellipse cx="158" cy="80" rx="16" ry="10" transform="rotate(-15 158 80)" fill="#E8655A"/>
        </g>
        <ellipse cx="100" cy="105" rx="58" ry="48" fill="#E8655A"/>
        <path d="M55,110 Q30,118 22,134" stroke="#E8655A" stroke-width="7" stroke-linecap="round" fill="none"/>
        <path d="M52,125 Q28,136 18,154" stroke="#E8655A" stroke-width="7" stroke-linecap="round" fill="none"/>
        <path d="M62,138 Q48,152 42,170" stroke="#E8655A" stroke-width="7" stroke-linecap="round" fill="none"/>
        <path d="M145,110 Q170,118 178,134" stroke="#E8655A" stroke-width="7" stroke-linecap="round" fill="none"/>
        <path d="M148,125 Q172,136 182,154" stroke="#E8655A" stroke-width="7" stroke-linecap="round" fill="none"/>
        <path d="M138,138 Q152,152 158,170" stroke="#E8655A" stroke-width="7" stroke-linecap="round" fill="none"/>
        <circle cx="30" cy="68" r="8" fill="#D94F44"/>
        <circle cx="170" cy="68" r="8" fill="#D94F44"/>
      </g>

      <g class="crab-eyes">
        <circle cx="78" cy="62" r="16" fill="white"/>
        <circle cx="122" cy="62" r="16" fill="white"/>
        <g class="crab-pupil-left" :style="leftPupilStyle">
          <circle cx="80" cy="62" r="8" fill="#1a1a1a"/>
          <circle cx="83" cy="59" r="3" fill="white"/>
        </g>
        <g class="crab-pupil-right" :style="rightPupilStyle">
          <circle cx="120" cy="62" r="8" fill="#1a1a1a"/>
          <circle cx="123" cy="59" r="3" fill="white"/>
        </g>
      </g>

      <g class="crab-blink" v-if="isBlinking">
        <ellipse cx="78" cy="62" rx="16" ry="2" fill="#E8655A"/>
        <ellipse cx="122" cy="62" rx="16" ry="2" fill="#E8655A"/>
      </g>
    </svg>

    <div class="crab-speech-bubble" v-if="speechText" @click.stop="dismissSpeech">
      <span>{{ speechText }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'

const props = defineProps<{
  show: boolean
  inputRect: DOMRect | null
}>()

const visible = ref(false)
const isHiding = ref(false)
const isHovered = ref(false)
const isBlinking = ref(false)
const isDragging = ref(false)
const isPeeking = ref(false)
const speechText = ref('')
const clickCount = ref(0)

const mouseX = ref(0)
const mouseY = ref(0)

const CRAB_SIZE = 52

const dragX = ref<number | null>(null)
const dragY = ref<number | null>(null)
const isSnapped = ref(true)

let dragOffsetX = 0
let dragOffsetY = 0
let hasDragged = false

const crabStyle = computed(() => {
  if (!props.show) return { display: 'none' }

  const size = CRAB_SIZE
  const h = size * 0.9

  if (!isSnapped.value && dragX.value !== null && dragY.value !== null) {
    return {
      position: 'fixed' as const,
      left: `${dragX.value}px`,
      top: `${dragY.value}px`,
      width: `${size}px`,
      height: `${h}px`,
      zIndex: 9999,
      overflow: 'visible' as const,
      clipPath: undefined,
    }
  }

  if (!props.inputRect) return { display: 'none' }

  const rect = props.inputRect
  const left = rect.left + rect.width / 2 - size / 2
  const top = rect.top - h * 0.45

  return {
    position: 'fixed' as const,
    left: `${left}px`,
    top: `${top}px`,
    width: `${size}px`,
    height: `${h}px`,
    zIndex: 1,
    overflow: 'visible' as const,
  }
})

const leftPupilStyle = computed(() => {
  const { dx, dy } = calcEyeOffset(78, 62)
  return { transform: `translate(${dx}px, ${dy}px)` }
})

const rightPupilStyle = computed(() => {
  const { dx, dy } = calcEyeOffset(122, 62)
  return { transform: `translate(${dx}px, ${dy}px)` }
})

function getCrabScreenPos() {
  if (!isSnapped.value && dragX.value !== null && dragY.value !== null) {
    return { x: dragX.value, y: dragY.value }
  }
  if (!props.inputRect) return { x: 0, y: 0 }
  const rect = props.inputRect
  return {
    x: rect.left + rect.width / 2 - CRAB_SIZE / 2,
    y: rect.top - CRAB_SIZE * 0.9 * 0.45,
  }
}

function calcEyeOffset(eyeCx: number, eyeCy: number) {
  const pos = getCrabScreenPos()
  const scale = CRAB_SIZE / 200
  const eyeScreenX = pos.x + eyeCx * scale
  const eyeScreenY = pos.y + eyeCy * scale

  const diffX = mouseX.value - eyeScreenX
  const diffY = mouseY.value - eyeScreenY
  const dist = Math.sqrt(diffX * diffX + diffY * diffY)
  const maxShift = 4.5

  if (dist < 1) return { dx: 0, dy: 0 }

  const shift = Math.min(maxShift, dist * 0.025)
  const dx = (diffX / dist) * shift
  const dy = (diffY / dist) * shift

  return { dx, dy }
}

function onDragStart(e: MouseEvent) {
  hasDragged = false
  isDragging.value = true
  isSnapped.value = false
  const pos = getCrabScreenPos()
  dragOffsetX = e.clientX - pos.x
  dragOffsetY = e.clientY - pos.y
  dragX.value = pos.x
  dragY.value = pos.y
  document.addEventListener('mousemove', onDragMove)
  document.addEventListener('mouseup', onDragEnd)
}

function onDragMove(e: MouseEvent) {
  if (!isDragging.value) return
  hasDragged = true
  dragX.value = e.clientX - dragOffsetX
  dragY.value = e.clientY - dragOffsetY
}

function onDragEnd(e: MouseEvent) {
  isDragging.value = false
  document.removeEventListener('mousemove', onDragMove)
  document.removeEventListener('mouseup', onDragEnd)
  if (hasDragged) {
    snapIfNearInput()
  }
}

function onTouchStart(e: TouchEvent) {
  hasDragged = false
  const touch = e.touches[0]
  isDragging.value = true
  isSnapped.value = false
  const pos = getCrabScreenPos()
  dragOffsetX = touch.clientX - pos.x
  dragOffsetY = touch.clientY - pos.y
  dragX.value = pos.x
  dragY.value = pos.y
  document.addEventListener('touchmove', onTouchMove, { passive: false })
  document.addEventListener('touchend', onTouchEnd)
}

function onTouchMove(e: TouchEvent) {
  e.preventDefault()
  if (!isDragging.value) return
  hasDragged = true
  const touch = e.touches[0]
  dragX.value = touch.clientX - dragOffsetX
  dragY.value = touch.clientY - dragOffsetY
}

function onTouchEnd() {
  isDragging.value = false
  document.removeEventListener('touchmove', onTouchMove)
  document.removeEventListener('touchend', onTouchEnd)
  if (hasDragged) {
    snapIfNearInput()
  }
}

function snapIfNearInput() {
  if (!props.inputRect || dragX.value === null || dragY.value === null) {
    console.log('[crab] snap skip: inputRect=', !!props.inputRect, 'dragX=', dragX.value, 'dragY=', dragY.value)
    return
  }
  const rect = props.inputRect
  const crabCenterX = dragX.value + CRAB_SIZE / 2
  const crabCenterY = dragY.value + CRAB_SIZE * 0.9 / 2
  const inputCenterX = rect.left + rect.width / 2
  const inputTopY = rect.top

  const dx = Math.abs(crabCenterX - inputCenterX)
  const dy = Math.abs(crabCenterY - inputTopY)

  console.log('[crab] snap check: dx=', dx, 'dy=', dy, 'threshold=120')

  if (dx < 120 && dy < 120) {
    isSnapped.value = true
    dragX.value = null
    dragY.value = null
    showSpeech('到家了~')
  }
}

let blinkTimer: ReturnType<typeof setInterval> | null = null
let speechTimer: ReturnType<typeof setTimeout> | null = null
let peekTimer: ReturnType<typeof setTimeout> | null = null
let hideTimer: ReturnType<typeof setTimeout> | null = null

function startBlinking() {
  blinkTimer = setInterval(() => {
    if (Math.random() < 0.3) {
      isBlinking.value = true
      setTimeout(() => { isBlinking.value = false }, 150)
    }
  }, 2000)
}

function stopBlinking() {
  if (blinkTimer) {
    clearInterval(blinkTimer)
    blinkTimer = null
  }
}

function startPeeking() {
  const doPeek = () => {
    if (!visible.value || isDragging.value) {
      scheduleNext()
      return
    }
    isPeeking.value = true
    peekTimer = setTimeout(() => {
      isPeeking.value = false
      scheduleNext()
    }, 1500 + Math.random() * 2000)
  }
  const scheduleNext = () => {
    peekTimer = setTimeout(doPeek, 4000 + Math.random() * 6000)
  }
  scheduleNext()
}

function stopPeeking() {
  if (peekTimer) {
    clearTimeout(peekTimer)
    peekTimer = null
  }
  isPeeking.value = false
}

const hoverPhrases = [
  '嘿！别碰我~',
  '我在看着你呢！',
  '躲好了，别拉我出来~',
  '嘘，我在偷听你打字...',
  '别看我，看输入框！',
  '你拖我干嘛！',
]

const clickPhrases = [
  '别戳了！',
  '好痛！',
  '你再戳我就走了！',
  '我可是有钳子的！',
  '咔咔咔！',
  '我躲得好好的你干嘛！',
  '拖我可以，戳我不行！',
]

const dragPhrases = [
  '放开我！',
  '我要回家！',
  '你把我拖哪去？',
  '我腿多但跑不快啊！',
]

function onMouseEnter() {
  isHovered.value = true
  const msg = hoverPhrases[Math.floor(Math.random() * hoverPhrases.length)]
  showSpeech(msg)
}

function onMouseLeave() {
  isHovered.value = false
}

function onCrabClick() {
  if (hasDragged) {
    hasDragged = false
    return
  }
  clickCount.value++
  if (clickCount.value >= 5) {
    showSpeech('够了够了！我走了！')
    setTimeout(() => {
      visible.value = false
      isHiding.value = true
      setTimeout(() => {
        visible.value = true
        isHiding.value = false
        clickCount.value = 0
        showSpeech('...我回来了')
      }, 2000)
    }, 800)
  } else {
    const msg = clickPhrases[Math.floor(Math.random() * clickPhrases.length)]
    showSpeech(msg)
  }
}

function showSpeech(text: string) {
  speechText.value = text
  if (speechTimer) clearTimeout(speechTimer)
  speechTimer = setTimeout(() => { speechText.value = '' }, 2500)
}

function dismissSpeech() {
  speechText.value = ''
}

function onMouseMove(e: MouseEvent) {
  mouseX.value = e.clientX
  mouseY.value = e.clientY
}

const greetings = [
  '开始聊天啦~',
  '我来帮你盯着输入框！',
  '有什么想说的？',
  '我在这儿呢~',
  '悄悄冒个头~',
]

function onInputFocus() {
  if (Math.random() < 0.4) {
    const msg = greetings[Math.floor(Math.random() * greetings.length)]
    showSpeech(msg)
  }
}

watch(() => props.show, (newVal) => {
  if (newVal) {
    hideTimer && clearTimeout(hideTimer)
    hideTimer = null
    isHiding.value = false
    setTimeout(() => { visible.value = true }, 50)
    startBlinking()
    startPeeking()
  } else {
    hideTimer = setTimeout(() => {
      if (!props.show) {
        isHiding.value = true
        stopBlinking()
        stopPeeking()
        setTimeout(() => {
          visible.value = false
          isHiding.value = false
        }, 400)
      }
    }, 3000)
  }
}, { immediate: true })

watch(isDragging, (val) => {
  if (val) {
    const msg = dragPhrases[Math.floor(Math.random() * dragPhrases.length)]
    showSpeech(msg)
  }
})

onMounted(() => {
  window.addEventListener('mousemove', onMouseMove)
  window.addEventListener('focusin', (e: FocusEvent) => {
    const target = e.target as HTMLElement
    if (target?.tagName === 'TEXTAREA' || target?.tagName === 'INPUT') {
      onInputFocus()
    }
  })
})

onUnmounted(() => {
  window.removeEventListener('mousemove', onMouseMove)
  stopBlinking()
  stopPeeking()
  if (speechTimer) clearTimeout(speechTimer)
  if (hideTimer) clearTimeout(hideTimer)
})
</script>

<style scoped>
.crab-companion {
  pointer-events: none;
  opacity: 0;
  transform: translateY(8px) scale(0.7);
  transition: opacity 0.5s cubic-bezier(0.2, 0.8, 0.2, 1),
              transform 0.5s cubic-bezier(0.2, 0.8, 0.2, 1);
  filter: drop-shadow(0 2px 6px rgba(0,0,0,0.1));
}

.crab-visible {
  opacity: 1;
  transform: translateY(0) scale(1);
  pointer-events: auto;
  cursor: grab;
}

.crab-visible:active {
  cursor: grabbing;
}

.crab-hiding {
  opacity: 0;
  transform: translateY(6px) scale(0.8);
}

.crab-dragging {
  z-index: 9999 !important;
  transform: scale(1.1) rotate(-3deg);
  filter: drop-shadow(0 4px 12px rgba(0,0,0,0.2));
  transition: transform 0.15s ease, filter 0.15s ease;
}

.crab-peeks {
  animation: crab-peek 1.5s ease-in-out;
}

@keyframes crab-peek {
  0%   { transform: translateY(0) scale(1); }
  30%  { transform: translateY(-6px) scale(1.05); }
  70%  { transform: translateY(-6px) scale(1.05); }
  100% { transform: translateY(0) scale(1); }
}

.crab-svg {
  width: 100%;
  height: 100%;
  overflow: visible;
}

.crab-eyes {
  transition: transform 0.12s ease-out;
}

.crab-blink {
  transition: none;
}

.crab-speech-bubble {
  position: absolute;
  bottom: 100%;
  left: 50%;
  transform: translateX(-50%) translateY(-6px);
  background: var(--dsh-bg, #fff);
  color: var(--dsh-text-1, #1a1a1a);
  border: 1px solid var(--dsh-border, #e5e5e5);
  border-radius: 10px;
  padding: 5px 12px;
  font-size: 12px;
  font-weight: 500;
  white-space: nowrap;
  pointer-events: auto;
  cursor: pointer;
  box-shadow: 0 2px 10px rgba(0,0,0,0.08);
  animation: crab-bubble-in 0.3s cubic-bezier(0.2, 0.8, 0.2, 1);
  z-index: 100;
}

.crab-speech-bubble::after {
  content: '';
  position: absolute;
  top: 100%;
  left: 50%;
  transform: translateX(-50%);
  border: 5px solid transparent;
  border-top-color: var(--dsh-bg, #fff);
}

.crab-speech-bubble::before {
  content: '';
  position: absolute;
  top: 100%;
  left: 50%;
  transform: translateX(-50%);
  border: 6px solid transparent;
  border-top-color: var(--dsh-border, #e5e5e5);
}

@keyframes crab-bubble-in {
  from {
    opacity: 0;
    transform: translateX(-50%) translateY(4px) scale(0.85);
  }
  to {
    opacity: 1;
    transform: translateX(-50%) translateY(-6px) scale(1);
  }
}
</style>