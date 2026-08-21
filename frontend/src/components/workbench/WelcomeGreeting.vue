<template>
  <Transition name="greeting-slide">
    <div v-if="visible" class="welcome-bar">
      <div class="welcome-left">
        <span class="welcome-title">
          <span class="streamed-text">{{ displayedGreeting }}</span><span v-if="isStreaming" class="stream-cursor">|</span>
        </span>
        <span v-if="subtitleVisible" class="welcome-subtitle">系统已准备就绪，你今天的第一条创作灵感是什么？</span>
      </div>
      <div class="welcome-right">
        <span class="welcome-time">{{ formattedTime }}</span>
        <button class="welcome-close" @click="close" title="收起">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
        </button>
      </div>
    </div>
  </Transition>
</template>

<script setup lang="ts">
import { ref, computed, watch, onUnmounted } from 'vue'

interface Props {
  nickname?: string
  showTodayOnly?: boolean
}
const props = withDefaults(defineProps<Props>(), {
  showTodayOnly: true
})
const emit = defineEmits<{ (e: 'close'): void }>()

const visible = ref(false)
const displayedGreeting = ref('')
const isStreaming = ref(false)
const subtitleVisible = ref(false)
let streamTimer: ReturnType<typeof setTimeout> | null = null

function todayKey(): string {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`
}

function getGreetingPrefix(): string {
  const h = new Date().getHours()
  if (h < 5) return '凌晨好'
  if (h < 9) return '早上好'
  if (h < 11) return '上午好'
  if (h < 13) return '中午好'
  if (h < 18) return '下午好'
  if (h < 22) return '晚上好'
  return '夜深了'
}

const fullGreeting = computed(() => {
  const name = props.nickname?.trim() || '创作者'
  return `${getGreetingPrefix()}，${name}。`
})

function startStreaming() {
  displayedGreeting.value = ''
  isStreaming.value = true
  subtitleVisible.value = false
  const text = fullGreeting.value
  let idx = 0

  function tick() {
    if (idx < text.length) {
      const char = text[idx]
      const isPunctuation = '，。！？、；：'.includes(char)
      displayedGreeting.value += char
      idx++
      const delay = isPunctuation ? 120 : 55
      streamTimer = setTimeout(tick, delay)
    } else {
      isStreaming.value = false
      subtitleVisible.value = true
    }
  }

  streamTimer = setTimeout(tick, 300)
}

watch(fullGreeting, () => {
  if (visible.value) {
    startStreaming()
  }
})

const formattedTime = computed(() => {
  const d = new Date()
  const weekdayMap = ['星期日','星期一','星期二','星期三','星期四','星期五','星期六']
  const datePart = `${d.getMonth()+1}月${d.getDate()}日`
  const timePart = `${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`
  return `${datePart} ${weekdayMap[d.getDay()]} ${timePart}`
})

function close() {
  visible.value = false
  if (streamTimer) {
    clearTimeout(streamTimer)
    streamTimer = null
  }
  isStreaming.value = false
  emit('close')
}

function trigger() {
  const key = `welcome_greeted_${todayKey()}`
  if (props.showTodayOnly && localStorage.getItem(key) === '1') {
    return
  }
  visible.value = true
  if (props.showTodayOnly) {
    localStorage.setItem(key, '1')
  }
  startStreaming()
}

onUnmounted(() => {
  if (streamTimer) {
    clearTimeout(streamTimer)
  }
})

defineExpose({ trigger, close })
</script>

<style scoped>
.welcome-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 10px 18px;
  margin-top: 0;
  margin-bottom: 0;
  background: linear-gradient(90deg, rgba(33, 112, 214, 0.06), rgba(33, 112, 214, 0.02));
  border: 1px solid #e3ecf7;
  border-radius: 10px;
  flex-wrap: wrap;
}

.welcome-left {
  display: flex;
  align-items: baseline;
  gap: 14px;
  flex-wrap: wrap;
  min-width: 0;
}

.welcome-title {
  font-size: 16px;
  font-weight: 700;
  color: #102445;
  letter-spacing: 0.2px;
  white-space: nowrap;
}

.stream-cursor {
  display: inline-block;
  animation: cursor-blink 0.6s step-end infinite;
  color: #2170d6;
  font-weight: 400;
  margin-left: 1px;
}

@keyframes cursor-blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}

.welcome-subtitle {
  font-size: 15px;
  color: #6b7a93;
  line-height: 1.5;
  animation: subtitle-fade-in 0.5s ease both;
}

@keyframes subtitle-fade-in {
  from { opacity: 0; transform: translateY(4px); }
  to { opacity: 1; transform: translateY(0); }
}

.welcome-right {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}

.welcome-time {
  font-size: 14px;
  color: #8a99b3;
  letter-spacing: 0.3px;
  white-space: nowrap;
}

.welcome-close {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: #9aa8c0;
  cursor: pointer;
  transition: background 0.15s ease, color 0.15s ease;
}
.welcome-close:hover {
  background: rgba(33, 112, 214, 0.08);
  color: #2170d6;
}

/* 淡入 + 轻微下移 */
.greeting-slide-enter-active,
.greeting-slide-leave-active {
  transition: opacity 0.3s ease, transform 0.3s ease, max-height 0.3s ease, margin-bottom 0.3s ease;
  overflow: hidden;
  max-height: 60px;
}
.greeting-slide-enter-from,
.greeting-slide-leave-to {
  opacity: 0;
  transform: translateY(-8px);
  max-height: 0;
  margin-bottom: 0;
}
</style>