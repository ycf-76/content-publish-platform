<script setup>
import { computed, nextTick, ref } from 'vue'

defineOptions({ name: 'FishWidget' })

/**
 * DeepSeek 动态鱼（fish-plugin 前端组件）
 * 按平台规范，UI 主题插件的前端需手动集成到前端代码：
 * 在输入框所在组件中引入本组件并置于输入框旁，定位由父级布局决定；
 * size/speed/bubble/placement 由父组件从插件配置读取后传入。
 *
 * props:
 *  - size      鱼的宽度（px），48~200，越界自动收敛
 *  - speed     动画速度倍率，0.5~2，越界自动收敛
 *  - bubble    是否显示气泡
 *  - placement 挂载侧：'right'（输入框右侧，鱼头朝左看向输入框）| 'left'
 *  - state     'idle' 待机 | 'active' AI 生成中（摆尾与浮动加快），由父组件传入
 *
 * emit:
 *  - interact  点击鱼时触发，父组件可挂彩蛋逻辑
 */
const props = defineProps({
  size: { type: Number, default: 96 },
  speed: { type: Number, default: 1 },
  bubble: { type: Boolean, default: true },
  placement: {
    type: String,
    default: 'right',
    validator: (v) => ['left', 'right'].includes(v),
  },
  state: {
    type: String,
    default: 'idle',
    validator: (v) => ['idle', 'active'].includes(v),
  },
})

const emit = defineEmits(['interact'])

const clamp = (value, min, max, fallback) => {
  const n = Number(value)
  if (!Number.isFinite(n)) return fallback
  return Math.min(max, Math.max(min, n))
}

// 收敛后的尺寸与速度：无论宿主传入什么，渲染始终稳定
const px = computed(() => Math.round(clamp(props.size, 48, 200, 96)))
const svgHeight = computed(() => Math.round(px.value * 0.7))
const speedFactor = computed(() => clamp(props.speed, 0.5, 2, 1))
const facing = computed(() => (props.placement === 'right' ? -1 : 1))

// 动画时长统一经 CSS 变量下发，active 状态整体提速
const durationVars = computed(() => {
  const active = props.state === 'active'
  const base = active
    ? { float: 1.6, tail: 0.45, bubble: 2.2 }
    : { float: 3.4, tail: 1.3, bubble: 3.6 }
  const s = speedFactor.value
  return {
    '--facing': String(facing.value),
    '--dur-float': `${(base.float / s).toFixed(2)}s`,
    '--dur-tail': `${(base.tail / s).toFixed(2)}s`,
    '--dur-bubble': `${(base.bubble / s).toFixed(2)}s`,
  }
})

// clipPath 唯一 id：组件被多实例挂载时不互相污染
const clipId = `fish-body-clip-${Math.random().toString(36).slice(2, 8)}`

// 点击摆尾：先移除类再等一次渲染后加回，保证动画可靠重启；
// 不持有定时器，组件卸载无需清理
const wiggling = ref(false)
const handleFishClick = async () => {
  emit('interact')
  wiggling.value = false
  await nextTick()
  wiggling.value = true
}
</script>

<template>
  <div
    class="fish-plugin"
    :class="`is-${state}`"
    :style="{ width: `${px}px`, height: `${Math.round(px * 0.72)}px`, ...durationVars }"
    role="img"
    aria-label="DeepSeek 蓝色动态鱼"
    @click="handleFishClick"
  >
    <!-- 水面投影：随浮动缩放，强化“悬浮”感 -->
    <div class="fish-shadow" aria-hidden="true"></div>

    <div class="fish-flip">
      <div class="fish-wiggle" :class="{ wiggling }">
        <div class="fish-float">
          <svg
            class="fish-svg"
            :width="px"
            :height="svgHeight"
            viewBox="0 0 200 140"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
          >
            <defs>
              <clipPath :id="clipId">
                <path
                  d="M55 70 C62 44 92 26 125 26 C158 26 182 44 182 66 C182 90 160 110 124 110 C92 110 62 94 55 70 Z"
                />
              </clipPath>
            </defs>

            <!-- 尾鳍（左右摆动） -->
            <g class="fish-tail">
              <path d="M60 66 C42 60 26 50 18 34 C34 42 52 54 63 64 Z" fill="#3B5BE8" />
              <path d="M60 76 C42 82 26 92 18 108 C34 100 52 88 63 78 Z" fill="#3B5BE8" />
            </g>

            <!-- 背鳍 -->
            <path d="M104 30 Q110 12 128 10 Q120 22 118 30 Z" fill="#3B5BE8" />

            <!-- 身体 -->
            <path
              d="M55 70 C62 44 92 26 125 26 C158 26 182 44 182 66 C182 90 160 110 124 110 C92 110 62 94 55 70 Z"
              fill="#4D6BFE"
            />

            <!-- 肚皮（裁剪在身体轮廓内） -->
            <ellipse
              cx="128"
              cy="124"
              rx="66"
              ry="34"
              fill="#BFD0FF"
              :clip-path="`url(#${clipId})`"
            />

            <!-- 胸鳍（轻拍） -->
            <g class="fish-fin">
              <path d="M118 88 Q110 108 120 120 Q134 110 134 92 Q126 98 118 88 Z" fill="#3B5BE8" />
            </g>

            <!-- 眼睛（偶尔眨眼） -->
            <g class="fish-eye">
              <circle cx="152" cy="56" r="9" fill="#FFFFFF" />
              <circle cx="154.5" cy="58" r="4.5" fill="#1E2A66" />
              <circle cx="156" cy="55" r="1.6" fill="#FFFFFF" />
            </g>

            <!-- 嘴巴 -->
            <path
              d="M148 78 Q158 86 168 76"
              stroke="#2E4BD8"
              stroke-width="3"
              stroke-linecap="round"
            />
          </svg>
        </div>
      </div>

      <!-- 气泡（跟随鱼头方向镜像） -->
      <div v-if="bubble" class="fish-bubbles" aria-hidden="true">
        <span class="fish-bubble b1"></span>
        <span class="fish-bubble b2"></span>
        <span class="fish-bubble b3"></span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.fish-plugin {
  position: relative;
  display: inline-block;
  flex: none;
  overflow: visible;
  cursor: pointer;
  user-select: none;
  transition: transform 0.25s ease;
}

/* 悬停：克制的轻微上浮 */
.fish-plugin:hover {
  transform: translateY(-2px);
}

/* 朝向：placement 为 right 时镜像，鱼头朝向输入框 */
.fish-flip {
  width: 100%;
  height: 100%;
  transform: scaleX(var(--facing, 1));
  transform-origin: center;
}

/* 点击摆尾 */
.fish-wiggle.wiggling {
  animation: fish-wiggle 0.7s ease;
}

/* 待机浮动 */
.fish-float {
  animation: fish-float var(--dur-float, 3.4s) ease-in-out infinite;
}

.fish-svg {
  display: block;
}

/* 尾鳍：绕与身体连接处摆动 */
.fish-tail {
  transform-box: fill-box;
  transform-origin: 100% 50%;
  animation: fish-tail var(--dur-tail, 1.3s) ease-in-out infinite;
}

/* 胸鳍：绕根部轻拍 */
.fish-fin {
  transform-box: fill-box;
  transform-origin: 50% 8%;
  animation: fish-fin var(--dur-tail, 1.3s) ease-in-out infinite;
}

/* 眨眼：长周期里短暂压扁一次 */
.fish-eye {
  transform-box: fill-box;
  transform-origin: 50% 50%;
  animation: fish-blink 5.2s infinite;
}

/* 投影：鱼上浮时缩小变淡 */
.fish-shadow {
  position: absolute;
  left: 50%;
  bottom: -2px;
  width: 58%;
  height: 9px;
  border-radius: 50%;
  background: rgba(77, 107, 254, 0.14);
  filter: blur(2px);
  transform: translateX(-50%);
  animation: fish-shadow var(--dur-float, 3.4s) ease-in-out infinite;
}

/* 气泡：从鱼嘴附近升起消散 */
.fish-bubbles {
  position: absolute;
  top: 10%;
  right: 4%;
  width: 26px;
  height: 30px;
  pointer-events: none;
}

.fish-bubble {
  position: absolute;
  bottom: 0;
  border-radius: 50%;
  background: rgba(77, 107, 254, 0.25);
  border: 1px solid rgba(77, 107, 254, 0.45);
  animation: fish-bubble var(--dur-bubble, 3.6s) ease-out infinite;
}

.fish-bubble.b1 {
  width: 6px;
  height: 6px;
  right: 2px;
}

.fish-bubble.b2 {
  width: 4px;
  height: 4px;
  right: 14px;
  animation-delay: calc(var(--dur-bubble, 3.6s) * 0.33);
}

.fish-bubble.b3 {
  width: 7px;
  height: 7px;
  right: -6px;
  animation-delay: calc(var(--dur-bubble, 3.6s) * 0.66);
}

@keyframes fish-float {
  0%,
  100% {
    transform: translateY(0) rotate(0deg);
  }
  50% {
    transform: translateY(-7px) rotate(1.5deg);
  }
}

@keyframes fish-tail {
  0%,
  100% {
    transform: rotate(-9deg);
  }
  50% {
    transform: rotate(9deg);
  }
}

@keyframes fish-fin {
  0%,
  100% {
    transform: rotate(0deg);
  }
  50% {
    transform: rotate(-7deg);
  }
}

@keyframes fish-blink {
  0%,
  90.5%,
  94.5%,
  100% {
    transform: scaleY(1);
  }
  92.5% {
    transform: scaleY(0.08);
  }
}

@keyframes fish-shadow {
  0%,
  100% {
    transform: translateX(-50%) scaleX(1);
    opacity: 1;
  }
  50% {
    transform: translateX(-50%) scaleX(0.78);
    opacity: 0.5;
  }
}

@keyframes fish-bubble {
  0% {
    transform: translate(0, 0) scale(0.5);
    opacity: 0;
  }
  12% {
    opacity: 0.9;
  }
  100% {
    transform: translate(-8px, -34px) scale(1);
    opacity: 0;
  }
}

@keyframes fish-wiggle {
  0% {
    transform: rotate(0deg);
  }
  25% {
    transform: rotate(-7deg);
  }
  55% {
    transform: rotate(5deg);
  }
  80% {
    transform: rotate(-2deg);
  }
  100% {
    transform: rotate(0deg);
  }
}

/* 无障碍：用户偏好减少动效时关闭全部动画 */
@media (prefers-reduced-motion: reduce) {
  .fish-plugin,
  .fish-plugin * {
    animation: none !important;
    transition: none !important;
  }
}
</style>
