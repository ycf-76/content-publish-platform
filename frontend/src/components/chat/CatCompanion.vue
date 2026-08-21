<template>
  <div
    class="cat-companion"
    :class="{
      'cat-visible': visible,
      'cat-hiding': isHiding,
      'cat-dragging': isDragging,
      'cat-yawning': isYawning,
      'cat-stretching': isStretching,
    }"
    :style="catStyle"
    @mousedown.prevent="onDragStart"
    @touchstart.prevent="onTouchStart"
    @mouseenter="onMouseEnter"
    @mouseleave="onMouseLeave"
    @click="onCatClick"
  >
    <svg class="cat-svg" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 180">
      <defs>
        <filter id="cat-shadow" x="-10%" y="-10%" width="120%" height="130%">
          <feDropShadow dx="0" dy="1" stdDeviation="1.5" flood-color="#000" flood-opacity="0.08"/>
        </filter>
      </defs>

      <g class="cat-body" filter="url(#cat-shadow)">
        <ellipse cx="100" cy="120" rx="55" ry="45" fill="#F5A623"/>
        <ellipse cx="100" cy="130" rx="40" ry="30" fill="#FDEBD0"/>

        <path d="M55,90 L45,55 L70,80 Z" fill="#F5A623"/>
        <path d="M145,90 L155,55 L130,80 Z" fill="#F5A623"/>
        <path d="M57,87 L49,60 L68,82 Z" fill="#FFD89B"/>
        <path d="M143,87 L151,60 L132,82 Z" fill="#FFD89B"/>

        <path d="M30,115 Q20,105 15,95" stroke="#F5A623" stroke-width="8" stroke-linecap="round" fill="none"/>
        <path d="M170,115 Q180,105 185,95" stroke="#F5A623" stroke-width="8" stroke-linecap="round" fill="none"/>

        <path d="M65,155 Q55,165 45,170" stroke="#F5A623" stroke-width="7" stroke-linecap="round" fill="none"/>
        <path d="M135,155 Q145,165 155,170" stroke="#F5A623" stroke-width="7" stroke-linecap="round" fill="none"/>

        <ellipse cx="78" cy="95" rx="14" ry="16" fill="white"/>
        <ellipse cx="122" cy="95" rx="14" ry="16" fill="white"/>

        <g class="cat-pupil-left" :style="leftPupilStyle">
          <ellipse cx="80" cy="95" rx="6" ry="9" fill="#2D2D2D"/>
          <circle cx="82" cy="91" r="2.5" fill="white"/>
        </g>
        <g class="cat-pupil-right" :style="rightPupilStyle">
          <ellipse cx="120" cy="95" rx="6" ry="9" fill="#2D2D2D"/>
          <circle cx="122" cy="91" r="2.5" fill="white"/>
        </g>

        <path d="M95,108 Q100,114 105,108" stroke="#D4956A" stroke-width="2" fill="none" stroke-linecap="round"/>
        <path d="M92,112 L88,118" stroke="#D4956A" stroke-width="1.5" stroke-linecap="round"/>
        <path d="M108,112 L112,118" stroke="#D4956A" stroke-width="1.5" stroke-linecap="round"/>

        <line x1="60" y1="100" x2="35" y2="96" stroke="#D4956A" stroke-width="1.2" stroke-linecap="round"/>
        <line x1="60" y1="106" x2="35" y2="108" stroke="#D4956A" stroke-width="1.2" stroke-linecap="round"/>
        <line x1="140" y1="100" x2="165" y2="96" stroke="#D4956A" stroke-width="1.2" stroke-linecap="round"/>
        <line x1="140" y1="106" x2="165" y2="108" stroke="#D4956A" stroke-width="1.2" stroke-linecap="round"/>
      </g>

      <g class="cat-blink" v-if="isBlinking">
        <ellipse cx="78" cy="95" rx="14" ry="2" fill="#F5A623"/>
        <ellipse cx="122" cy="95" rx="14" ry="2" fill="#F5A623"/>
      </g>

      <g class="cat-yawn-mouth" v-if="isYawning">
        <ellipse cx="100" cy="115" rx="8" ry="10" fill="#E87B7B"/>
        <ellipse cx="100" cy="112" rx="5" ry="3" fill="#FF9999"/>
      </g>
    </svg>

    <div class="cat-speech-bubble" v-if="speechText" @click.stop="dismissSpeech">
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
const isYawning = ref(false)
const isStretching = ref(false)
const isDragging = ref(false)
const speechText = ref('')
const clickCount = ref(0)

const mouseX = ref(0)
const mouseY = ref(0)

const CAT_SIZE = 52

const dragX = ref<number | null>(null)
const dragY = ref<number | null>(null)
const isSnapped = ref(true)

let dragOffsetX = 0
let dragOffsetY = 0
let hasDragged = false

const catStyle = computed(() => {
  if (!props.show) return { display: 'none' }

  const size = CAT_SIZE
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
  const { dx, dy } = calcEyeOffset(78, 95)
  return { transform: `translate(${dx}px, ${dy}px)` }
})

const rightPupilStyle = computed(() => {
  const { dx, dy } = calcEyeOffset(122, 95)
  return { transform: `translate(${dx}px, ${dy}px)` }
})

function getCatScreenPos() {
  if (!isSnapped.value && dragX.value !== null && dragY.value !== null) {
    return { x: dragX.value, y: dragY.value }
  }
  if (!props.inputRect) return { x: 0, y: 0 }
  const rect = props.inputRect
  return {
    x: rect.left + rect.width / 2 - CAT_SIZE / 2,
    y: rect.top - CAT_SIZE * 0.9 * 0.45,
  }
}

function calcEyeOffset(eyeCx: number, eyeCy: number) {
  const pos = getCatScreenPos()
  const scale = CAT_SIZE / 200
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
  const pos = getCatScreenPos()
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

function onDragEnd() {
  isDragging.value = false
  document.removeEventListener('mousemove', onDragMove)
  document.removeEventListener('mouseup', onDragEnd)
  if (hasDragged) snapIfNearInput()
}

function onTouchStart(e: TouchEvent) {
  hasDragged = false
  const touch = e.touches[0]
  isDragging.value = true
  isSnapped.value = false
  const pos = getCatScreenPos()
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
  if (hasDragged) snapIfNearInput()
}

function snapIfNearInput() {
  if (!props.inputRect || dragX.value === null || dragY.value === null) return
  const rect = props.inputRect
  const catCenterX = dragX.value + CAT_SIZE / 2
  const catCenterY = dragY.value + CAT_SIZE * 0.9 / 2
  const inputCenterX = rect.left + rect.width / 2
  const inputTopY = rect.top

  const dx = Math.abs(catCenterX - inputCenterX)
  const dy = Math.abs(catCenterY - inputTopY)

  if (dx < 120 && dy < 120) {
    isSnapped.value = true
    dragX.value = null
    dragY.value = null
    showSpeech('到家了喵~')
  }
}

let blinkTimer: ReturnType<typeof setInterval> | null = null
let yawnTimer: ReturnType<typeof setTimeout> | null = null
let speechTimer: ReturnType<typeof setTimeout> | null = null
let hideTimer: ReturnType<typeof setTimeout> | null = null

function startBlinking() {
  blinkTimer = setInterval(() => {
    if (Math.random() < 0.25) {
      isBlinking.value = true
      setTimeout(() => { isBlinking.value = false }, 180)
    }
  }, 2500)
}

function stopBlinking() {
  if (blinkTimer) { clearInterval(blinkTimer); blinkTimer = null }
}

function startYawning() {
  const doYawn = () => {
    if (!visible.value || isDragging.value) {
      yawnTimer = setTimeout(doYawn, 8000 + Math.random() * 12000)
      return
    }
    isYawning.value = true
    showSpeech('哈~~~')
    setTimeout(() => {
      isYawning.value = false
      isStretching.value = true
      setTimeout(() => { isStretching.value = false }, 1200)
      yawnTimer = setTimeout(doYawn, 8000 + Math.random() * 12000)
    }, 1500)
  }
  yawnTimer = setTimeout(doYawn, 5000 + Math.random() * 8000)
}

function stopYawning() {
  if (yawnTimer) { clearTimeout(yawnTimer); yawnTimer = null }
  isYawning.value = false
  isStretching.value = false
}

const hoverPhrases = [
  '喵~别碰我',
  '我在睡觉呢...',
  '呼噜呼噜...',
  '你手好暖~',
  '别摸！我会掉毛的！',
  '嗯...再摸一下...',
]

const clickPhrases = [
  '喵！',
  '嗷！别戳！',
  '你戳我干嘛喵？',
  '我要挠你了！',
  '哼！',
  '再戳就咬你！',
  '呼噜呼噜~',
]

const dragPhrases = [
  '放开我喵！',
  '我要回输入框！',
  '你把我拖去哪？',
  '我腿短跑不快喵...',
]

function onMouseEnter() {
  isHovered.value = true
  const msg = hoverPhrases[Math.floor(Math.random() * hoverPhrases.length)]
  showSpeech(msg)
}

function onMouseLeave() {
  isHovered.value = false
}

function onCatClick() {
  if (hasDragged) { hasDragged = false; return }
  clickCount.value++
  if (clickCount.value >= 5) {
    showSpeech('够了！我走了喵！')
    setTimeout(() => {
      visible.value = false
      isHiding.value = true
      setTimeout(() => {
        visible.value = true
        isHiding.value = false
        clickCount.value = 0
        showSpeech('...我回来了喵')
      }, 2500)
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
  '喵~开始聊天啦',
  '我来监督你打字喵',
  '呼噜呼噜...',
  '有什么想说的喵？',
  '趴着看你聊天~',
]

function onInputFocus() {
  if (Math.random() < 0.35) {
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
    startYawning()
  } else {
    hideTimer = setTimeout(() => {
      if (!props.show) {
        isHiding.value = true
        stopBlinking()
        stopYawning()
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
  stopYawning()
  if (speechTimer) clearTimeout(speechTimer)
  if (hideTimer) clearTimeout(hideTimer)
})
</script>

<style scoped>
.cat-companion {
  pointer-events: none;
  opacity: 0;
  transform: translateY(8px) scale(0.7);
  transition: opacity 0.5s cubic-bezier(0.2, 0.8, 0.2, 1),
              transform 0.5s cubic-bezier(0.2, 0.8, 0.2, 1);
  filter: drop-shadow(0 2px 6px rgba(0,0,0,0.1));
}

.cat-visible {
  opacity: 1;
  transform: translateY(0) scale(1);
  pointer-events: auto;
  cursor: grab;
}

.cat-visible:active { cursor: grabbing; }

.cat-hiding {
  opacity: 0;
  transform: translateY(6px) scale(0.8);
}

.cat-dragging {
  z-index: 9999 !important;
  transform: scale(1.1) rotate(-3deg);
  filter: drop-shadow(0 4px 12px rgba(0,0,0,0.2));
  transition: transform 0.15s ease, filter 0.15s ease;
}

.cat-yawning {
  animation: cat-yawn 1.5s ease-in-out;
}

@keyframes cat-yawn {
  0%   { transform: translateY(0) scale(1); }
  30%  { transform: translateY(-4px) scale(1.03); }
  70%  { transform: translateY(-4px) scale(1.03); }
  100% { transform: translateY(0) scale(1); }
}

.cat-stretching {
  animation: cat-stretch 1.2s ease-in-out;
}

@keyframes cat-stretch {
  0%   { transform: translateY(0) scaleX(1); }
  40%  { transform: translateY(-2px) scaleX(1.08); }
  100% { transform: translateY(0) scaleX(1); }
}

.cat-svg { width: 100%; height: 100%; overflow: visible; }
.cat-eyes { transition: transform 0.12s ease-out; }
.cat-blink { transition: none; }

.cat-speech-bubble {
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
  animation: cat-bubble-in 0.3s cubic-bezier(0.2, 0.8, 0.2, 1);
}

@keyframes cat-bubble-in {
  from { opacity: 0; transform: translateX(-50%) translateY(4px) scale(0.85); }
  to   { opacity: 1; transform: translateX(-50%) translateY(-6px) scale(1); }
}
</style>