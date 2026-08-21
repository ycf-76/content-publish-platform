<template>
  <div
    class="spongebob-companion"
    :class="{
      'sb-visible': visible,
      'sb-hiding': isHiding,
      'sb-dragging': isDragging,
      'sb-waving': isWaving,
      'sb-happy': currentMood === 'happy',
      'sb-sad': currentMood === 'sad',
      'sb-surprised': currentMood === 'surprised',
      'sb-laugh': currentMood === 'laugh',
      'sb-blink': isBlinking,
      'sb-float': floatEnabled,
    }"
    :style="spongeStyle"
    @mousedown.prevent="onDragStart"
    @touchstart.prevent="onTouchStart"
    @mouseenter="onMouseEnter"
    @mouseleave="onMouseLeave"
    @click="onSpongeClick"
  >
    <svg class="sb-svg" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 280">
      <defs>
        <filter id="sb-shadow" x="-10%" y="-5%" width="120%" height="115%">
          <feDropShadow dx="0" dy="2" stdDeviation="2" flood-color="#000" flood-opacity="0.1"/>
        </filter>
        <linearGradient id="sb-body-grad" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stop-color="#FFF44F"/>
          <stop offset="50%" stop-color="#FFE135"/>
          <stop offset="100%" stop-color="#FFD700"/>
        </linearGradient>
        <linearGradient id="sb-hole-grad" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stop-color="#D4A800"/>
          <stop offset="100%" stop-color="#C8A800"/>
        </linearGradient>
      </defs>

      <g class="sb-body-group" filter="url(#sb-shadow)">
        <!-- Body -->
        <rect x="20" y="10" width="160" height="180" rx="18" ry="18" fill="url(#sb-body-grad)" stroke="#C8A800" stroke-width="2.5"/>

        <!-- Holes -->
        <ellipse cx="55" cy="40" rx="9" ry="8" fill="url(#sb-hole-grad)" opacity="0.7"/>
        <ellipse cx="100" cy="35" rx="7" ry="6" fill="url(#sb-hole-grad)" opacity="0.7"/>
        <ellipse cx="148" cy="42" rx="8" ry="7" fill="url(#sb-hole-grad)" opacity="0.7"/>
        <ellipse cx="60" cy="75" rx="6" ry="5" fill="url(#sb-hole-grad)" opacity="0.7"/>
        <ellipse cx="140" cy="72" rx="7" ry="6" fill="url(#sb-hole-grad)" opacity="0.7"/>
        <ellipse cx="100" cy="105" rx="5" ry="4.5" fill="url(#sb-hole-grad)" opacity="0.7"/>

        <!-- Eyes -->
        <ellipse cx="75" cy="80" rx="22" ry="24" fill="white" stroke="#333" stroke-width="2"/>
        <ellipse cx="125" cy="80" rx="22" ry="24" fill="white" stroke="#333" stroke-width="2"/>

        <!-- Pupils -->
        <g class="sb-pupil-left" :style="leftPupilStyle">
          <circle cx="77" cy="80" r="9" fill="#42A5F5" stroke="#1E88E5" stroke-width="1.5"/>
          <circle cx="80" cy="76" r="3" fill="white"/>
        </g>
        <g class="sb-pupil-right" :style="rightPupilStyle">
          <circle cx="123" cy="80" r="9" fill="#42A5F5" stroke="#1E88E5" stroke-width="1.5"/>
          <circle cx="126" cy="76" r="3" fill="white"/>
        </g>

        <!-- Blink overlay -->
        <g class="sb-blink-overlay" v-if="isBlinking">
          <ellipse cx="75" cy="80" rx="22" ry="3" fill="url(#sb-body-grad)" stroke="#C8A800" stroke-width="1"/>
          <ellipse cx="125" cy="80" rx="22" ry="3" fill="url(#sb-body-grad)" stroke="#C8A800" stroke-width="1"/>
        </g>

        <!-- Nose -->
        <ellipse cx="100" cy="108" rx="10" ry="14" fill="url(#sb-body-grad)" stroke="#C8A800" stroke-width="1.5"/>

        <!-- Cheeks -->
        <ellipse cx="48" cy="118" rx="12" ry="8" fill="rgba(255,138,128,0.4)" class="sb-cheek"/>
        <ellipse cx="152" cy="118" rx="12" ry="8" fill="rgba(255,138,128,0.4)" class="sb-cheek"/>

        <!-- Mouth - happy -->
        <g v-if="currentMood === 'happy' || currentMood === 'laugh'">
          <path d="M65,130 Q100,165 135,130" fill="#333" stroke="#222" stroke-width="1.5"/>
          <rect x="88" y="130" width="10" height="8" rx="1" fill="white" stroke="#ddd" stroke-width="0.5"/>
          <rect x="102" y="130" width="10" height="8" rx="1" fill="white" stroke="#ddd" stroke-width="0.5"/>
          <ellipse cx="100" cy="150" rx="14" ry="8" fill="#E57373"/>
        </g>

        <!-- Mouth - sad -->
        <g v-if="currentMood === 'sad'">
          <path d="M70,145 Q100,125 130,145" fill="none" stroke="#333" stroke-width="2.5" stroke-linecap="round"/>
        </g>

        <!-- Mouth - surprised -->
        <g v-if="currentMood === 'surprised'">
          <ellipse cx="100" cy="138" rx="14" ry="18" fill="#333" stroke="#222" stroke-width="1.5"/>
          <ellipse cx="100" cy="145" rx="8" ry="5" fill="#E57373"/>
        </g>

        <!-- Clothes - Shirt -->
        <rect x="20" y="160" width="160" height="30" fill="white" stroke="#ddd" stroke-width="0.5"/>

        <!-- Tie -->
        <rect x="94" y="162" width="12" height="8" rx="2" fill="#E53935"/>
        <polygon points="88,170 112,170 100,192" fill="#E53935"/>

        <!-- Belt -->
        <rect x="20" y="188" width="160" height="6" fill="#333"/>
        <rect x="93" y="186" width="14" height="10" rx="2" fill="#FFD700" stroke="#C8A800" stroke-width="0.5"/>

        <!-- Pants -->
        <rect x="20" y="194" width="160" height="30" fill="#8D6E23" stroke="#6D4C23" stroke-width="0.5"/>

        <!-- Arms -->
        <g class="sb-arm-left">
          <rect x="2" y="140" width="16" height="55" rx="8" fill="url(#sb-body-grad)" stroke="#C8A800" stroke-width="1.5"/>
        </g>
        <g class="sb-arm-right" :class="{ 'sb-arm-wave': isWaving }">
          <rect x="182" y="140" width="16" height="55" rx="8" fill="url(#sb-body-grad)" stroke="#C8A800" stroke-width="1.5"/>
        </g>

        <!-- Legs -->
        <rect x="55" y="224" width="16" height="24" rx="3" fill="white" stroke="#ddd" stroke-width="1"/>
        <rect x="129" y="224" width="16" height="24" rx="3" fill="white" stroke="#ddd" stroke-width="1"/>
        <rect x="57" y="240" width="4" height="4" rx="1" fill="#E53935"/>
        <rect x="131" y="240" width="4" height="4" rx="1" fill="#E53935"/>

        <!-- Shoes -->
        <ellipse cx="63" cy="254" rx="16" ry="7" fill="#333"/>
        <ellipse cx="137" cy="254" rx="16" ry="7" fill="#333"/>
      </g>
    </svg>

    <div class="sb-speech-bubble" v-if="speechText" @click.stop="dismissSpeech">
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
const isWaving = ref(false)
const speechText = ref('')
const clickCount = ref(0)
const currentMood = ref<'happy' | 'sad' | 'surprised' | 'laugh'>('happy')

const mouseX = ref(0)
const mouseY = ref(0)

const SPONGE_SIZE = 72
const floatEnabled = ref(true)

const dragX = ref<number | null>(null)
const dragY = ref<number | null>(null)
const isSnapped = ref(true)

let dragOffsetX = 0
let dragOffsetY = 0
let hasDragged = false

const spongeStyle = computed(() => {
  if (!props.show) return { display: 'none' }

  const size = SPONGE_SIZE
  const h = size * 1.4

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
  const top = rect.top - h * 0.55

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
  const { dx, dy } = calcEyeOffset(75, 80)
  return { transform: `translate(${dx}px, ${dy}px)` }
})

const rightPupilStyle = computed(() => {
  const { dx, dy } = calcEyeOffset(125, 80)
  return { transform: `translate(${dx}px, ${dy}px)` }
})

function getSpongeScreenPos() {
  if (!isSnapped.value && dragX.value !== null && dragY.value !== null) {
    return { x: dragX.value, y: dragY.value }
  }
  if (!props.inputRect) return { x: 0, y: 0 }
  const rect = props.inputRect
  return {
    x: rect.left + rect.width / 2 - SPONGE_SIZE / 2,
    y: rect.top - SPONGE_SIZE * 1.4 * 0.55,
  }
}

function calcEyeOffset(eyeCx: number, eyeCy: number) {
  const pos = getSpongeScreenPos()
  const scale = SPONGE_SIZE / 200
  const eyeScreenX = pos.x + eyeCx * scale
  const eyeScreenY = pos.y + eyeCy * scale

  const diffX = mouseX.value - eyeScreenX
  const diffY = mouseY.value - eyeScreenY
  const dist = Math.sqrt(diffX * diffX + diffY * diffY)
  const maxShift = 5

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
  const pos = getSpongeScreenPos()
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
  const pos = getSpongeScreenPos()
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
  const centerX = dragX.value + SPONGE_SIZE / 2
  const centerY = dragY.value + SPONGE_SIZE * 1.4 / 2
  const inputCenterX = rect.left + rect.width / 2
  const inputTopY = rect.top

  const dx = Math.abs(centerX - inputCenterX)
  const dy = Math.abs(centerY - inputTopY)

  if (dx < 140 && dy < 140) {
    isSnapped.value = true
    dragX.value = null
    dragY.value = null
    showSpeech('我回到菠萝屋啦！')
  }
}

let blinkTimer: ReturnType<typeof setInterval> | null = null
let speechTimer: ReturnType<typeof setTimeout> | null = null
let hideTimer: ReturnType<typeof setTimeout> | null = null
let moodTimer: ReturnType<typeof setTimeout> | null = null
let waveTimer: ReturnType<typeof setTimeout> | null = null

function startBlinking() {
  blinkTimer = setInterval(() => {
    if (Math.random() < 0.3) {
      isBlinking.value = true
      setTimeout(() => { isBlinking.value = false }, 150)
    }
  }, 3500)
}

function stopBlinking() {
  if (blinkTimer) { clearInterval(blinkTimer); blinkTimer = null }
}

const greetings = [
  '你好呀！我是海绵宝宝！',
  '我准备好了！我准备好了！',
  '谁住在深海的大菠萝里？',
  '今天是个好日子！',
  '蟹黄堡是世界上最好吃的！',
]

const hoverPhrases = [
  '嘿嘿~别碰我！',
  '我住在菠萝屋里~',
  '派大星是我最好的朋友！',
  'F 是不会吹口哨的...',
  '我在看着你呢！',
]

const clickPhrases = [
  '哈哈！',
  '哎哟！',
  '嘻嘻~',
  '干嘛戳我！',
  '痒！',
  '我准备好了！',
  '别挠啦！',
]

const dragPhrases = [
  '放开我！我要回菠萝屋！',
  '你把我拖去哪？',
  '派大星！救命啊！',
  '我要去蟹堡王上班！',
]

const happyPhrases = [
  '太棒啦！今天真是美好的一天！',
  '嘻嘻嘻~我好开心呀！',
  '我要去做蟹黄堡！',
]

const sadPhrases = [
  '呜呜...章鱼哥又不理我了...',
  '珊迪回德克萨斯了...',
  '我连泡泡都吹不好了...',
]

const surprisedPhrases = [
  '天哪！！不会吧？！',
  '章鱼哥笑了？！',
  '蟹老板给我涨工资了？！',
]

const laughPhrases = [
  '哈哈哈哈！！',
  '嘻嘻嘻嘻~停不下来啦！',
  '派大星你太搞笑了！',
]

const moodPhrases: Record<string, string[]> = {
  happy: happyPhrases,
  sad: sadPhrases,
  surprised: surprisedPhrases,
  laugh: laughPhrases,
}

function onMouseEnter() {
  isHovered.value = true
  const msg = hoverPhrases[Math.floor(Math.random() * hoverPhrases.length)]
  showSpeech(msg)
}

function onMouseLeave() {
  isHovered.value = false
}

function onSpongeClick() {
  if (hasDragged) { hasDragged = false; return }
  clickCount.value++

  if (clickCount.value >= 8) {
    showSpeech('够了！我要回菠萝屋了！')
    currentMood.value = 'sad'
    setTimeout(() => {
      visible.value = false
      isHiding.value = true
      setTimeout(() => {
        visible.value = true
        isHiding.value = false
        clickCount.value = 0
        currentMood.value = 'happy'
        showSpeech('...我回来了！我想你了！')
      }, 2500)
    }, 800)
  } else if (clickCount.value % 5 === 0) {
    showSpeech(`你已经戳了我 ${clickCount.value} 次啦！痒痒的~`)
  } else {
    const msg = clickPhrases[Math.floor(Math.random() * clickPhrases.length)]
    showSpeech(msg)
    if (Math.random() < 0.3) {
      triggerWave()
    }
  }
}

function triggerWave() {
  isWaving.value = true
  if (waveTimer) clearTimeout(waveTimer)
  waveTimer = setTimeout(() => { isWaving.value = false }, 1600)
}

function triggerMood(mood: 'happy' | 'sad' | 'surprised' | 'laugh') {
  currentMood.value = mood
  const phrases = moodPhrases[mood]
  const msg = phrases[Math.floor(Math.random() * phrases.length)]
  showSpeech(msg)
  triggerWave()

  if (moodTimer) clearTimeout(moodTimer)
  moodTimer = setTimeout(() => {
    currentMood.value = 'happy'
  }, 4000)
}

function showSpeech(text: string) {
  speechText.value = text
  if (speechTimer) clearTimeout(speechTimer)
  speechTimer = setTimeout(() => { speechText.value = '' }, 3000)
}

function dismissSpeech() {
  speechText.value = ''
}

function onMouseMove(e: MouseEvent) {
  mouseX.value = e.clientX
  mouseY.value = e.clientY
}

function onInputFocus() {
  if (Math.random() < 0.4) {
    const msg = greetings[Math.floor(Math.random() * greetings.length)]
    showSpeech(msg)
    triggerWave()
  }
}

watch(() => props.show, (newVal) => {
  if (newVal) {
    hideTimer && clearTimeout(hideTimer)
    hideTimer = null
    isHiding.value = false
    setTimeout(() => {
      visible.value = true
      if (Math.random() < 0.6) {
        showSpeech(greetings[Math.floor(Math.random() * greetings.length)])
        triggerWave()
      }
    }, 50)
    startBlinking()
  } else {
    hideTimer = setTimeout(() => {
      if (!props.show) {
        isHiding.value = true
        stopBlinking()
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
  if (speechTimer) clearTimeout(speechTimer)
  if (hideTimer) clearTimeout(hideTimer)
  if (moodTimer) clearTimeout(moodTimer)
  if (waveTimer) clearTimeout(waveTimer)
})
</script>

<style scoped>
.spongebob-companion {
  pointer-events: none;
  opacity: 0;
  transform: translateY(8px) scale(0.7);
  transition: opacity 0.5s cubic-bezier(0.2, 0.8, 0.2, 1),
              transform 0.5s cubic-bezier(0.2, 0.8, 0.2, 1);
  filter: drop-shadow(0 2px 6px rgba(0,0,0,0.1));
}

.sb-visible {
  opacity: 1;
  transform: translateY(0) scale(1);
  pointer-events: auto;
  cursor: grab;
}

.sb-visible:active { cursor: grabbing; }

.sb-hiding {
  opacity: 0;
  transform: translateY(6px) scale(0.8);
}

.sb-dragging {
  z-index: 9999 !important;
  transform: scale(1.1) rotate(-3deg);
  filter: drop-shadow(0 4px 12px rgba(0,0,0,0.2));
  transition: transform 0.15s ease, filter 0.15s ease;
}

.sb-float {
  animation: sb-float 3s ease-in-out infinite;
}

@keyframes sb-float {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-10px); }
}

.sb-dragging.sb-float,
.sb-hiding.sb-float {
  animation: none;
}

.sb-arm-right {
  transform-origin: 190px 165px;
  transition: transform 0.15s ease;
}

.sb-arm-wave .sb-arm-right {
  animation: sb-wave 0.5s ease-in-out 3;
}

@keyframes sb-wave {
  0%, 100% { transform: rotate(0deg); }
  50% { transform: rotate(-55deg); }
}

.sb-happy .sb-cheek { fill: rgba(255, 138, 128, 0.6); }

.sb-sad .sb-cheek { fill: rgba(150, 180, 255, 0.3); }

.sb-surprised .sb-cheek { fill: rgba(255, 200, 100, 0.5); }

.sb-laugh {
  animation: sb-shake 0.3s ease-in-out 3;
}

@keyframes sb-shake {
  0%, 100% { transform: rotate(0deg); }
  25% { transform: rotate(-3deg); }
  75% { transform: rotate(3deg); }
}

.sb-svg {
  width: 100%;
  height: 100%;
  overflow: visible;
}

.sb-speech-bubble {
  position: absolute;
  bottom: 100%;
  left: 50%;
  transform: translateX(-50%) translateY(-8px);
  background: var(--dsh-bg, #fff);
  color: var(--dsh-text-1, #1a1a1a);
  border: 2px solid #FFE135;
  border-radius: 12px;
  padding: 6px 14px;
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
  pointer-events: auto;
  cursor: pointer;
  box-shadow: 0 3px 12px rgba(255, 225, 53, 0.2);
  animation: sb-bubble-in 0.3s cubic-bezier(0.2, 0.8, 0.2, 1);
}

.sb-speech-bubble::after {
  content: '';
  position: absolute;
  top: 100%;
  left: 50%;
  transform: translateX(-50%);
  border: 6px solid transparent;
  border-top-color: #FFE135;
}

.sb-speech-bubble::before {
  content: '';
  position: absolute;
  top: 100%;
  left: 50%;
  transform: translateX(-50%);
  border: 5px solid transparent;
  border-top-color: var(--dsh-bg, #fff);
  z-index: 1;
}

@keyframes sb-bubble-in {
  from {
    opacity: 0;
    transform: translateX(-50%) translateY(4px) scale(0.85);
  }
  to {
    opacity: 1;
    transform: translateX(-50%) translateY(-8px) scale(1);
  }
}
</style>