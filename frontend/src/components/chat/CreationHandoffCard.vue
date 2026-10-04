<script setup lang="ts">
/**
 * CreationHandoffCard —— 分析到创作的沉浸式承接卡（P2）
 *
 * 作品分析联动后，不再只是顶部一条「分析已联动」提示，而是给用户一个
 * 可参与的创作承接卡：保留原作品缩略图、已验证模式、避坑模式、置信度，
 * 让用户先选「创作方向」，再预览建议分镜结构，最后一键开启创作。
 *
 * 这样分析结论真正转化为下一次创作的起点，而不是被压平成一段 prompt。
 */
import { computed, ref } from 'vue'
import { Sparkles, RefreshCw, Wand2, Layers, X, ArrowRight } from 'lucide-vue-next'
import { FULL_PAGE_TYPE_LABELS, type FullPageType } from '@/card-editor/templates'
import PhoneFrame from './PhoneFrame.vue'

const props = defineProps<{
  analysis: Record<string, any> | null
}>()

const emit = defineEmits<{
  (e: 'start', payload: { direction: string; proposedStructure: string[]; analysis: Record<string, any> | null }): void
  (e: 'close'): void
}>()

type Direction = 'reuse' | 'remix' | 'fresh'
const direction = ref<Direction | ''>('')

const confidenceLabel = computed(() => {
  const c = props.analysis?.confidence
  return ({ low: '低', medium: '中', high: '高' } as Record<string, string>)[c] || c || '—'
})

const bestPattern = computed(
  () => props.analysis?.writing_prescription?.best_patterns?.[0]?.name || '—',
)
const avoidPattern = computed(
  () => props.analysis?.writing_prescription?.avoid_patterns?.[0]?.name || '—',
)
const total = computed(() => props.analysis?.overview?.total || 0)

const sourceThumb = computed(() => {
  const top = props.analysis?.top_performers?.[0]
  return top?.cover || top?.thumbnail || props.analysis?.thumbnail || ''
})

// 三种方向对应的「建议分镜结构」（仅预览，真实生成时由 ContentPlanner 细化）
const DIRECTION_PLANS: Record<Direction, { label: string; desc: string; structure: string[] }> = {
  reuse: {
    label: '沿用结构',
    desc: '复用已验证的爆款骨架，最稳，适合同主题续作',
    structure: ['cover', 'list', 'content', 'quote', 'end_page'],
  },
  remix: {
    label: '改造结构',
    desc: '保留模式但换组件与节奏，避免审美疲劳',
    structure: ['cover', 'compare', 'steps', 'list', 'quote'],
  },
  fresh: {
    label: '全新表达',
    desc: '抛开原结构，用更丰富的组件重新表达',
    structure: ['cover', 'dark_panel', 'numbered_cards', 'icon_text', 'big_quote'],
  },
}

// 转成数组便于模板遍历，避免模板里的 as 断言
const directionList = computed(() =>
  (Object.keys(DIRECTION_PLANS) as Direction[]).map((key) => ({
    key,
    ...DIRECTION_PLANS[key],
  })),
)

const proposedStructure = computed<string[]>(() =>
  direction.value ? DIRECTION_PLANS[direction.value].structure : [],
)

function labelOf(t: string): string {
  return FULL_PAGE_TYPE_LABELS[t as FullPageType] || t || '页面'
}

function choose(dir: string) {
  direction.value = dir as Direction
}

function startCreation() {
  if (!direction.value) return
  emit('start', {
    direction: direction.value,
    proposedStructure: proposedStructure.value,
    analysis: props.analysis,
  })
}
</script>

<template>
  <div class="chc-card">
    <div class="chc-head">
      <div class="chc-title">
        <Sparkles :size="15" />
        基于分析开启创作
      </div>
      <button class="chc-close" @click="emit('close')" title="收起">
        <X :size="14" />
      </button>
    </div>

    <div class="chc-body">
      <!-- 左侧：原作品快照 -->
      <div class="chc-source">
        <div class="chc-thumb" :class="{ 'chc-thumb-empty': !sourceThumb }">
          <img v-if="sourceThumb" :src="sourceThumb" alt="原作品" />
          <span v-else>原作品</span>
        </div>
        <div class="chc-source-meta">
          <div class="chc-meta-row">
            <span class="chc-meta-k">已验证模式</span>
            <span class="chc-meta-v chc-ok">{{ bestPattern }}</span>
          </div>
          <div class="chc-meta-row">
            <span class="chc-meta-k">避坑模式</span>
            <span class="chc-meta-v chc-warn">{{ avoidPattern }}</span>
          </div>
          <div class="chc-meta-row">
            <span class="chc-meta-k">置信度</span>
            <span class="chc-meta-v">{{ confidenceLabel }} · {{ total }}篇</span>
          </div>
        </div>
      </div>

      <!-- 右侧：方向选择 -->
      <div class="chc-dirs">
        <button
          v-for="d in directionList"
          :key="d.key"
          class="chc-dir"
          :class="{ 'chc-dir-active': direction === d.key }"
          @click="choose(d.key)"
        >
          <component
            :is="d.key === 'reuse' ? Layers : d.key === 'remix' ? RefreshCw : Wand2"
            :size="16"
          />
          <div class="chc-dir-label">{{ d.label }}</div>
          <div class="chc-dir-desc">{{ d.desc }}</div>
        </button>
      </div>
    </div>

    <!-- 分镜预览：选了方向后出现 -->
    <div v-if="direction" class="chc-story">
      <div class="chc-story-head">
        <span>建议分镜</span>
        <span class="chc-story-hint">预览结构，真实生成会过质量门禁细化</span>
      </div>
      <div class="chc-story-strip">
        <div v-for="(t, i) in proposedStructure" :key="i" class="chc-page">
          <PhoneFrame variant="mini" class="chc-phone">{{ labelOf(t) }}</PhoneFrame>
          <span class="chc-page-idx">{{ i + 1 }}</span>
        </div>
      </div>
    </div>

    <div class="chc-foot">
      <button class="chc-btn-ghost" @click="emit('close')">稍后</button>
      <button
        class="chc-btn-primary"
        :disabled="!direction"
        @click="startCreation"
      >
        开始创作
        <ArrowRight :size="14" />
      </button>
    </div>
  </div>
</template>

<style scoped>
.chc-card {
  border: 1px solid #E5E7EB;
  border-radius: 14px;
  background: linear-gradient(180deg, #FFFDF7 0%, #FFFFFF 100%);
  padding: 12px 14px;
  margin: 10px 0 4px;
  box-shadow: 0 6px 18px rgba(43, 127, 216, 0.08);
}
.chc-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}
.chc-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 700;
  font-size: 14px;
  color: #1A1A2E;
}
.chc-close,
.chc-btn-ghost {
  border: none;
  background: transparent;
  color: #6B7280;
  cursor: pointer;
  border-radius: 8px;
  padding: 4px 6px;
}
.chc-close:hover { background: #F3F4F6; }
.chc-body {
  display: flex;
  gap: 14px;
}
.chc-source {
  display: flex;
  gap: 10px;
  width: 220px;
  flex-shrink: 0;
}
.chc-thumb {
  width: 64px;
  height: 86px;
  border-radius: 10px;
  overflow: hidden;
  background: #F1F5F9;
  display: grid;
  place-items: center;
  flex-shrink: 0;
}
.chc-thumb img { width: 100%; height: 100%; object-fit: cover; }
.chc-thumb-empty { color: #94A3B8; font-size: 11px; }
.chc-source-meta { flex: 1; display: flex; flex-direction: column; gap: 6px; }
.chc-meta-row { display: flex; flex-direction: column; gap: 1px; }
.chc-meta-k { font-size: 11px; color: #9CA3AF; }
.chc-meta-v { font-size: 12.5px; font-weight: 600; color: #374151; }
.chc-ok { color: #059669; }
.chc-warn { color: #D97706; }
.chc-dirs { display: flex; gap: 8px; flex: 1; }
.chc-dir {
  flex: 1;
  border: 1px solid #E5E7EB;
  border-radius: 10px;
  background: #fff;
  padding: 10px 8px;
  cursor: pointer;
  text-align: left;
  display: flex;
  flex-direction: column;
  gap: 4px;
  color: #374151;
  transition: all 0.15s;
}
.chc-dir:hover { border-color: #93C5FD; }
.chc-dir-active {
  border-color: #2B7FD8;
  background: #EFF6FF;
  box-shadow: 0 0 0 2px rgba(43, 127, 216, 0.15);
}
.chc-dir-label { font-weight: 700; font-size: 13px; display: flex; align-items: center; gap: 5px; }
.chc-dir-desc { font-size: 11px; color: #6B7280; line-height: 1.35; }
.chc-story { margin-top: 12px; }
.chc-story-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  font-size: 12.5px;
  font-weight: 600;
  color: #374151;
  margin-bottom: 8px;
}
.chc-story-hint { font-size: 10.5px; color: #9CA3AF; font-weight: 400; }
.chc-story-strip { display: flex; gap: 8px; overflow-x: auto; padding-bottom: 4px; }
.chc-page { position: relative; flex-shrink: 0; }
.chc-phone :deep(.pf-mini-screen) {
  font-size: 10.5px;
  font-weight: 600;
  color: #64748B;
  line-height: 1.25;
}
.chc-page-idx {
  position: absolute;
  top: -6px;
  left: -6px;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: #2B7FD8;
  color: #fff;
  font-size: 10px;
  font-weight: 700;
  display: grid;
  place-items: center;
}
.chc-foot { display: flex; justify-content: flex-end; gap: 8px; margin-top: 12px; }
.chc-btn-primary {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  border: none;
  background: #2B7FD8;
  color: #fff;
  font-weight: 600;
  font-size: 13px;
  padding: 7px 14px;
  border-radius: 9px;
  cursor: pointer;
}
.chc-btn-primary:disabled { background: #C7D2E5; cursor: not-allowed; }
.chc-btn-ghost:hover { background: #F3F4F6; }
</style>