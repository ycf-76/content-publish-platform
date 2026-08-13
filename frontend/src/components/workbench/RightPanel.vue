<template>
  <!-- 可拖拽分割线 -->
  <div class="mint-resize-handle"
       @mousedown="startResize"
       v-show="!isRightPanelCollapsed">
    <div class="mint-resize-line"></div>
  </div>

  <!-- 右侧面板收起按钮（收起态独立悬浮，展开态嵌入卡片头部） -->
  <button v-if="isRightPanelCollapsed" class="mint-right-toggle mint-right-toggle-floating" @click="toggleRightPanel" title="展开右侧面板" aria-label="展开右侧面板">
    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <rect width="18" height="18" x="3" y="3" rx="2"/><path d="M9 3v18"/>
    </svg>
  </button>

  <aside class="mint-config" v-show="!isRightPanelCollapsed">
    <!-- 单张卡片包裹全部配置项 -->
    <div class="mint-card mint-config-card">
      <!-- 卡片头部：标题 + 收起按钮 -->
      <div class="mint-config-card-header">
        <div class="mint-config-card-title">
          <i data-lucide="sliders-horizontal" style="width:16px; height:16px; color:#FF2442;"></i>
          配置中心
        </div>
        <button class="mint-config-collapse-btn" @click="toggleRightPanel" title="收起右侧面板" aria-label="收起右侧面板">
          <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <line x1="5" y1="12" x2="19" y2="12"/><polyline points="9 5 5 12 9 19"/>
          </svg>
        </button>
      </div>

      <!-- Section 1: 模型选择 -->
      <section class="mint-config-section">
        <div class="mint-config-section-title">
          <i data-lucide="cpu" style="width:15px; height:15px; color:#FF2442;"></i>
          模型选择
        </div>
        <div class="mint-config-row">
          <label class="mint-config-label">文本生成模型</label>
          <select class="mint-select" v-model="selectedTextModel">
            <option v-for="m in TEXT_MODEL_OPTIONS" :key="m.value" :value="m.value">{{ m.label }}</option>
          </select>
        </div>
        <div class="mint-config-row">
          <label class="mint-config-label">图片生成模型</label>
          <select class="mint-select" v-model="selectedImageModel">
            <option v-for="m in IMAGE_MODEL_OPTIONS" :key="m.value" :value="m.value">{{ m.label }}</option>
          </select>
        </div>
        <div class="mint-config-row">
          <label class="mint-config-label">温度参数</label>
          <div class="mint-slider-row">
            <input type="range" class="mint-slider" min="0" max="100" step="1" v-model.number="temperature">
            <span class="mint-slider-val">{{ temperatureDisplay }}</span>
          </div>
        </div>
        <div class="mint-config-row">
          <label class="mint-config-label">搜索结果数量</label>
          <select class="mint-select" v-model.number="selectedSearchLimit">
            <option v-for="n in SEARCH_LIMIT_OPTIONS" :key="n" :value="n">{{ n }} 条</option>
          </select>
        </div>
      </section>

      <!-- Section 2: 风格参数 -->
      <section class="mint-config-section">
        <div class="mint-config-section-title">
          <i data-lucide="palette" style="width:15px; height:15px; color:#7C3AED;"></i>
          风格参数
          <span style="margin-left:auto; font-size: 15px; color:#6B7280; cursor:pointer;" @click="refreshSkills" title="刷新 Skill 列表（用于加载新装入的第三方插件）">
            <i data-lucide="refresh-cw" style="width:12px; height:12px;"></i>
          </span>
        </div>
        <div class="mint-config-row">
          <label class="mint-config-label">分析 Skill</label>
          <select class="mint-select" v-model="selectedAnalyzeSkill" :disabled="skillsLoading">
            <option v-for="s in analyzeSkills" :key="s.name" :value="s.name" :title="s.description">{{ s.display_name }}</option>
          </select>
        </div>
        <div class="mint-config-row">
          <label class="mint-config-label">图片 Skill</label>
          <select class="mint-select" v-model="selectedImageGenSkill" :disabled="skillsLoading">
            <option v-for="s in imageGenSkills" :key="s.name" :value="s.name" :title="s.description">{{ s.display_name }}</option>
          </select>
        </div>
        <div class="mint-config-row">
          <label class="mint-config-label">文案 Skill</label>
          <select class="mint-select" v-model="selectedCopywriteSkill" :disabled="skillsLoading">
            <option v-for="s in copywriteSkills" :key="s.name" :value="s.name" :title="s.description">{{ s.display_name }}</option>
          </select>
        </div>
        <div class="mint-config-row">
          <label class="mint-config-label">审核 Skill</label>
          <select class="mint-select" v-model="selectedAuditSkill" :disabled="skillsLoading">
            <option v-for="s in auditSkills" :key="s.name" :value="s.name" :title="s.description">{{ s.display_name }}</option>
          </select>
        </div>
        <div class="mint-config-row">
          <label class="mint-config-label">文案长度</label>
          <div class="mint-slider-row">
            <input type="range" class="mint-slider" min="100" max="500" step="50" v-model.number="contentLength">
            <span class="mint-slider-val">{{ contentLength }}</span>
          </div>
        </div>
        <div class="mint-config-row">
          <div class="mint-toggle">
            <span class="mint-config-label">自动添加 Emoji</span>
            <div class="mint-switch" :class="{ active: autoEmoji }" @click="autoEmoji = !autoEmoji"></div>
          </div>
        </div>
        <div class="mint-config-row">
          <div class="mint-toggle">
            <span class="mint-config-label">自动生成标签</span>
            <div class="mint-switch" :class="{ active: autoTags }" @click="autoTags = !autoTags"></div>
          </div>
        </div>
      </section>

      <!-- Section 3: 发布设置 -->
      <section class="mint-config-section">
        <div class="mint-config-section-title">
          <i data-lucide="rocket" style="width:15px; height:15px; color:#D97706;"></i>
          发布设置
        </div>
        <div class="mint-config-row">
          <label class="mint-config-label">发布账号</label>
          <select class="mint-select">
            <option>@夏日穿搭日记</option>
            <option>@生活美学研究所</option>
            <option>@好物分享家</option>
          </select>
        </div>
        <div class="mint-config-row">
          <label class="mint-config-label">定时发布</label>
          <input type="text" class="mint-input" value="2026-07-28 18:00" placeholder="选择发布时间">
        </div>
        <div class="mint-config-row">
          <div class="mint-toggle">
            <span class="mint-config-label">终审通过后自动发布</span>
            <div class="mint-switch" :class="{ active: autoPublish }" @click="autoPublish = !autoPublish"></div>
          </div>
        </div>
      </section>

      <!-- Section 4: 本周数据 -->
      <section class="mint-config-section">
        <div class="mint-config-section-title">
          <i data-lucide="trending-up" style="width:15px; height:15px; color:#2563EB;"></i>
          本周数据
        </div>
        <div class="mint-config-stats">
          <div class="mint-config-stat-row">
            <span class="mint-config-stat-label">发布篇数</span>
            <span class="mint-config-stat-val">12</span>
          </div>
          <div class="mint-config-stat-row">
            <span class="mint-config-stat-label">总曝光量</span>
            <span class="mint-config-stat-val">23.4w</span>
          </div>
          <div class="mint-config-stat-row">
            <span class="mint-config-stat-label">平均互动率</span>
            <span class="mint-config-stat-val">8.7%</span>
          </div>
          <div class="mint-config-stat-row">
            <span class="mint-config-stat-label">新增粉丝</span>
            <span class="mint-config-stat-val">+347</span>
          </div>
        </div>
      </section>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { workflowApi, type SkillMeta } from '@/api/workflow'

const props = defineProps<{
  isSidebarCollapsed: boolean
  selectedPlatform: string
  initialCollapsed?: boolean
}>()

const emit = defineEmits<{
  'update:width': [value: number]
  'update:isCollapsed': [value: boolean]
  'update:modelSettings': [value: Record<string, any>]
}>()

// ===== 右侧面板宽度调整 =====
const MIN_RIGHT_WIDTH = 200
const MAX_RIGHT_WIDTH = 600
const DEFAULT_RIGHT_WIDTH = 280

const rightPanelWidth = ref(DEFAULT_RIGHT_WIDTH)
// 默认隐藏：未点开时不遮挡工作卡片
const isRightPanelCollapsed = ref(props.initialCollapsed ?? true)

function toggleRightPanel() {
  isRightPanelCollapsed.value = !isRightPanelCollapsed.value
  emit('update:isCollapsed', isRightPanelCollapsed.value)
}

let isResizing = false
let resizeStartX = 0
let resizeStartWidth = 0

function startResize(e: MouseEvent) {
  isResizing = true
  resizeStartX = e.clientX
  resizeStartWidth = rightPanelWidth.value
  document.addEventListener('mousemove', onResize)
  document.addEventListener('mouseup', stopResize)
  document.body.style.cursor = 'col-resize'
  document.body.style.userSelect = 'none'
}

function onResize(e: MouseEvent) {
  if (!isResizing) return

  const deltaX = resizeStartX - e.clientX
  let newWidth = resizeStartWidth + deltaX

  newWidth = Math.max(MIN_RIGHT_WIDTH, Math.min(newWidth, MAX_RIGHT_WIDTH))

  const shellWidth = window.innerWidth > 1600 ? 1600 : window.innerWidth
  const minMiddleWidth = 400

  const leftSidebarWidth = props.isSidebarCollapsed ? 0 : 192
  const maxRightWidth = shellWidth - leftSidebarWidth - 20 - minMiddleWidth - 20 - 20

  if (newWidth > maxRightWidth) {
    newWidth = maxRightWidth
  }

  rightPanelWidth.value = newWidth
  emit('update:width', newWidth)
}

function stopResize() {
  isResizing = false
  document.removeEventListener('mousemove', onResize)
  document.removeEventListener('mouseup', stopResize)
  document.body.style.cursor = ''
  document.body.style.userSelect = ''
}

// ===== 右侧工作区：模型/温度/风格配置（用户可调） =====
const TEXT_MODEL_OPTIONS = [
  { label: 'DeepSeek Chat（deepseek-chat）', value: 'deepseek-chat' },
  { label: 'DeepSeek R1（deepseek-reasoner）', value: 'deepseek-reasoner' },
  { label: '测试模式 · 不消耗 token（mock-chat）', value: 'mock-chat' },
  { label: '测试模式 · R1（mock-reasoner）', value: 'mock-reasoner' },
] as const
const IMAGE_MODEL_OPTIONS = [
  { label: '通义万相 wanx-v1', value: 'wanx-v1' },
  { label: '测试模式 · 不消耗 token（mock-image）', value: 'mock-image' },
] as const
const SEARCH_LIMIT_OPTIONS = [5, 10, 15, 20] as const

const copywriteSkills = ref<SkillMeta[]>([])
const imageGenSkills = ref<SkillMeta[]>([])
const analyzeSkills = ref<SkillMeta[]>([])
const auditSkills = ref<SkillMeta[]>([])
const skillsLoading = ref(false)

const selectedTextModel = ref<string>('deepseek-chat')
const selectedImageModel = ref<string>('wanx-v1')
const selectedSearchLimit = ref<number>(10)
const temperature = ref<number>(70)
const selectedCopywriteSkill = ref<string>('lively_girl')
const selectedImageGenSkill = ref<string>('xhs_blueprint')
const selectedAnalyzeSkill = ref<string>('standard')
const selectedAuditSkill = ref<string>('standard')
// 风格开关（与后端 model_settings 对齐）
const contentLength = ref<number>(300)
const autoEmoji = ref<boolean>(true)
const autoTags = ref<boolean>(true)
const autoPublish = ref<boolean>(true)

const temperatureDisplay = computed(() => (temperature.value / 100).toFixed(2))

const modelSettings = computed(() => {
  const cwSkill = copywriteSkills.value.find(s => s.name === selectedCopywriteSkill.value)
  const imgSkill = imageGenSkills.value.find(s => s.name === selectedImageGenSkill.value)
  return {
    text_model: selectedTextModel.value,
    image_model: selectedImageModel.value,
    temperature: temperature.value / 100,
    search_limit: selectedSearchLimit.value,
    search_platform: props.selectedPlatform,
    copywrite_skill: selectedCopywriteSkill.value,
    image_gen_skill: selectedImageGenSkill.value,
    analyze_skill: selectedAnalyzeSkill.value,
    audit_skill: selectedAuditSkill.value,
    writing_style: cwSkill?.display_name || '',
    image_style: imgSkill?.display_name || '',
    content_length: contentLength.value,
    auto_emoji: autoEmoji.value,
    auto_tags: autoTags.value,
    auto_publish: autoPublish.value,
  }
})

watch(modelSettings, (val) => {
  emit('update:modelSettings', val)
}, { immediate: true, deep: true })

async function loadSkills() {
  skillsLoading.value = true
  try {
    const allSkills = await workflowApi.listSkills()
    copywriteSkills.value = allSkills.copywrite || []
    imageGenSkills.value = allSkills.image_gen || []
    analyzeSkills.value = allSkills.analyze || []
    auditSkills.value = allSkills.audit || []
    if (copywriteSkills.value.length === 0) {
      copywriteSkills.value = [
        { node_type: 'copywrite', name: 'lively_girl', display_name: '活泼少女风', description: '默认', default_config: {} },
      ]
    }
    if (imageGenSkills.value.length === 0) {
      imageGenSkills.value = [
        { node_type: 'image_gen', name: 'xhs_blueprint', display_name: '动态布局生成', description: 'LLM 根据用户意图输出结构化蓝图，动态渲染4张卡片', default_config: {} },
      ]
    }
    if (analyzeSkills.value.length === 0) {
      analyzeSkills.value = [
        { node_type: 'analyze', name: 'standard', display_name: '标准三层分析', description: '默认', default_config: {} },
      ]
    }
    if (auditSkills.value.length === 0) {
      auditSkills.value = [
        { node_type: 'audit', name: 'standard', display_name: '标准四维度审核', description: '默认', default_config: {} },
      ]
    }
    if (!copywriteSkills.value.find(s => s.name === selectedCopywriteSkill.value)) {
      selectedCopywriteSkill.value = copywriteSkills.value[0]?.name || 'lively_girl'
    }
    if (!imageGenSkills.value.find(s => s.name === selectedImageGenSkill.value)) {
      selectedImageGenSkill.value = imageGenSkills.value[0]?.name || 'xhs_blueprint'
    }
    if (!analyzeSkills.value.find(s => s.name === selectedAnalyzeSkill.value)) {
      selectedAnalyzeSkill.value = analyzeSkills.value[0]?.name || 'standard'
    }
    if (!auditSkills.value.find(s => s.name === selectedAuditSkill.value)) {
      selectedAuditSkill.value = auditSkills.value[0]?.name || 'standard'
    }
  } catch (e: any) {
    console.error('[Workbench] load skills failed:', e)
    copywriteSkills.value = [
      { node_type: 'copywrite', name: 'lively_girl', display_name: '活泼少女风', description: '默认', default_config: {} },
    ]
    imageGenSkills.value = [
      { node_type: 'image_gen', name: 'xhs_blueprint', display_name: '动态布局生成', description: 'LLM 根据用户意图输出结构化蓝图，动态渲染4张卡片', default_config: {} },
    ]
    analyzeSkills.value = [
      { node_type: 'analyze', name: 'standard', display_name: '标准三层分析', description: '默认', default_config: {} },
    ]
    auditSkills.value = [
      { node_type: 'audit', name: 'standard', display_name: '标准四维度审核', description: '默认', default_config: {} },
    ]
  } finally {
    skillsLoading.value = false
  }
}

async function refreshSkills() {
  await loadSkills()
}

function toggleSwitchClass(e: Event) {
  ;(e.currentTarget as HTMLElement).classList.toggle('active')
}

onMounted(() => {
  loadSkills()
})
</script>