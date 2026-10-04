<template>
  <!-- 可拖拽分割线 -->
  <div class="mint-resize-handle"
       @mousedown="startResize"
       @dblclick.prevent="resetRightPanelWidth"
       v-show="!isRightPanelCollapsed"
       title="拖拽调整面板宽度 · 双击恢复默认">
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
          <span class="mint-config-icon"><SlidersHorizontal :size="16" /></span>
          <div class="mint-config-card-title-text">
            <div class="mint-config-card-title-name">配置中心</div>
            <div class="mint-config-card-title-sub">模型、风格与发布参数</div>
          </div>
        </div>
        <button class="mint-config-collapse-btn" @click="toggleRightPanel" title="收起右侧面板" aria-label="收起右侧面板">
          <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <line x1="5" y1="12" x2="19" y2="12"/><polyline points="9 5 5 12 9 19"/>
          </svg>
        </button>
      </div>

      <!-- 技能模板快选 -->
      <div class="mint-template-bar" v-if="savedSkills.length > 0">
        <div class="mint-template-bar-label">
          <Zap :size="12" />
          <span>技能模板</span>
        </div>
        <div class="mint-template-chips">
          <button
            v-for="t in savedSkills"
            :key="t.id"
            class="mint-template-chip"
            :class="{ 'mint-template-chip-active': activeTemplateId === t.id }"
            @click="applyTemplate(t)"
            :title="t.description || t.name"
          >
            <span class="mint-template-chip-icon">{{ t.icon }}</span>
            <span class="mint-template-chip-name">{{ t.name }}</span>
          </button>
          <button
            v-if="activeTemplateId"
            class="mint-template-chip mint-template-chip-clear"
            @click="clearTemplate"
            title="清除模板，恢复手动配置"
          >
            <X :size="11" />
            <span>清除</span>
          </button>
        </div>
      </div>

      <!-- Section 1: 模型选择 -->
      <section class="mint-config-section">
        <div class="mint-config-section-title">
          <span class="mint-config-section-icon mint-config-section-icon-model"><Cpu :size="14" /></span>
          模型选择
        </div>
        <div class="mint-config-row">
          <label class="mint-config-label">文本生成模型</label>
          <MintSelect v-model="selectedTextModel" :options="textModelOptions" />
        </div>
        <div class="mint-config-row">
          <label class="mint-config-label">图片生成模型</label>
          <MintSelect v-model="selectedImageModel" :options="imageModelOptions" />
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
          <MintSelect v-model="selectedSearchLimit" :options="searchLimitOptions" />
        </div>
      </section>

      <!-- Section 2: 风格参数 -->
      <section class="mint-config-section">
        <div class="mint-config-section-title">
          <span class="mint-config-section-icon mint-config-section-icon-style"><Palette :size="14" /></span>
          风格参数
          <span style="margin-left:auto; font-size: 15px; color:#6B7280; cursor:pointer;" @click="refreshSkills" title="刷新 Skill 列表（用于加载新装入的第三方插件）">
            <RefreshCw :size="12" />
          </span>
        </div>
        <div class="mint-config-row">
          <label class="mint-config-label">分析 Skill</label>
          <MintSelect v-model="selectedAnalyzeSkill" :options="analyzeSkillOptions" :disabled="skillsLoading" />
        </div>
        <div class="mint-config-row">
          <label class="mint-config-label">图片 Skill</label>
          <MintSelect v-model="selectedImageGenSkill" :options="imageGenSkillOptions" :disabled="skillsLoading" />
        </div>
        <div class="mint-config-row">
          <label class="mint-config-label">文案 Skill</label>
          <MintSelect v-model="selectedCopywriteSkill" :options="copywriteSkillOptions" :disabled="skillsLoading" />
        </div>
        <div class="mint-config-row">
          <label class="mint-config-label">审核 Skill</label>
          <MintSelect v-model="selectedAuditSkill" :options="auditSkillOptions" :disabled="skillsLoading" />
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
          <span class="mint-config-section-icon mint-config-section-icon-publish"><Rocket :size="14" /></span>
          发布设置
        </div>
        <div class="mint-config-row">
          <label class="mint-config-label">发布账号</label>
          <MintSelect v-model="selectedAccount" :options="accountOptions" />
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
        <div class="mint-config-row">
          <div class="mint-toggle">
            <span class="mint-config-label">📱 推送到微信</span>
            <div class="mint-switch" :class="{ active: enableWechatPush }" @click="enableWechatPush = !enableWechatPush"></div>
          </div>
        </div>
        <div v-if="enableWechatPush" class="mint-config-row">
          <label class="mint-config-label">微信目标用户ID</label>
          <input
            type="text"
            class="mint-input"
            v-model="wechatTargetUserId"
            placeholder="输入微信用户ID或群ID"
          />
        </div>
        <div class="mint-config-row">
          <div class="mint-toggle">
            <span class="mint-config-label">🚀 推送到飞书</span>
            <div class="mint-switch" :class="{ active: enableFeishuPush }" @click="enableFeishuPush = !enableFeishuPush"></div>
          </div>
        </div>
        <div v-if="enableFeishuPush" class="mint-config-row">
          <label class="mint-config-label">飞书目标群Chat ID</label>
          <input
            type="text"
            class="mint-input"
            v-model="feishuChatId"
            placeholder="输入飞书群聊ID (如 oc_xxxxx)"
          />
        </div>
      </section>

      <!-- Section 4: 本周数据 -->
      <section class="mint-config-section">
        <div class="mint-config-section-title">
          <span class="mint-config-section-icon mint-config-section-icon-stats"><TrendingUp :size="14" /></span>
          本周数据
        </div>
        <div class="mint-config-stats">
          <div class="mint-config-stat-row">
            <span class="mint-config-stat-label">发布篇数</span>
            <span class="mint-config-stat-val">{{ weeklyStats.published_count }}</span>
          </div>
          <div class="mint-config-stat-row">
            <span class="mint-config-stat-label">创建工作流</span>
            <span class="mint-config-stat-val">{{ weeklyStats.total_workflows }}</span>
          </div>
          <div class="mint-config-stat-row">
            <span class="mint-config-stat-label">完成率</span>
            <span class="mint-config-stat-val">{{ weeklyStats.completed_rate }}%</span>
          </div>
          <div class="mint-config-stat-row">
            <span class="mint-config-stat-label">进行中</span>
            <span class="mint-config-stat-val">{{ weeklyStats.active_count }}</span>
          </div>
        </div>
      </section>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import {
  Cpu,
  Palette,
  RefreshCw,
  Rocket,
  SlidersHorizontal,
  TrendingUp,
  X,
  Zap,
} from 'lucide-vue-next'
import { workflowApi, type SkillMeta } from '@/api/workflow'
import { useSkillTemplates, type SavedSkill } from '@/composables/useSkillTemplates'
import MintSelect from './MintSelect.vue'

const { savedSkills, expandToModelSettings } = useSkillTemplates()
const activeTemplateId = ref<string | null>(null)

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
import { useResizeHandle } from '@/composables/useResizeHandle'

const {
  width: rightPanelWidth,
  isResizing: isRightResizing,
  startResize: startResize,
  resetWidth: resetRightPanelWidth,
} = useResizeHandle({
  direction: 'right',
  minWidth: 200,
  maxWidth: 560,
  storageKey: 'mint-right-panel-width-v2',
})

const isRightPanelCollapsed = ref(props.initialCollapsed ?? true)

function toggleRightPanel() {
  isRightPanelCollapsed.value = !isRightPanelCollapsed.value
  emit('update:isCollapsed', isRightPanelCollapsed.value)
}

watch(rightPanelWidth, (w) => {
  emit('update:width', w)
}, { immediate: true })

// ===== 右侧工作区：模型/温度/风格配置（用户可调） =====
const TEXT_MODEL_OPTIONS = [
  { label: 'DeepSeek Chat（deepseek-chat）', value: 'deepseek-chat' },
  { label: 'DeepSeek R1（deepseek-reasoner）', value: 'deepseek-reasoner' },
] as const
const IMAGE_MODEL_OPTIONS = [
  { label: '通义万相 wanx-v1', value: 'wanx-v1' },
] as const
const SEARCH_LIMIT_OPTIONS = [5, 10, 15, 20] as const

const textModelOptions = computed(() => TEXT_MODEL_OPTIONS.map(m => ({ label: m.label, value: m.value })))
const imageModelOptions = computed(() => IMAGE_MODEL_OPTIONS.map(m => ({ label: m.label, value: m.value })))
const searchLimitOptions = computed(() => SEARCH_LIMIT_OPTIONS.map(n => ({ label: `${n} 条`, value: n })))

const selectedAccount = ref('@夏日穿搭日记')
const accountOptions = [
  { label: '@夏日穿搭日记', value: '@夏日穿搭日记' },
  { label: '@生活美学研究所', value: '@生活美学研究所' },
  { label: '@好物分享家', value: '@好物分享家' },
]

const copywriteSkills = ref<SkillMeta[]>([])
const imageGenSkills = ref<SkillMeta[]>([])
const analyzeSkills = ref<SkillMeta[]>([])
const auditSkills = ref<SkillMeta[]>([])
const skillsLoading = ref(false)

const copywriteSkillOptions = computed(() => copywriteSkills.value.map(s => ({ label: s.display_name, value: s.name, title: s.description })))
const imageGenSkillOptions = computed(() => imageGenSkills.value.map(s => ({ label: s.display_name, value: s.name, title: s.description })))
const analyzeSkillOptions = computed(() => analyzeSkills.value.map(s => ({ label: s.display_name, value: s.name, title: s.description })))
const auditSkillOptions = computed(() => auditSkills.value.map(s => ({ label: s.display_name, value: s.name, title: s.description })))

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
   const enableWechatPush = ref<boolean>(false)
const wechatTargetUserId = ref<string>('')
const enableFeishuPush = ref<boolean>(false)
const feishuChatId = ref<string>('')

const weeklyStats = ref({
  published_count: 0,
  total_workflows: 0,
  completed_rate: 0,
  active_count: 0,
})

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
    enable_wechat_push: enableWechatPush.value,
    wechat_target_user_id: wechatTargetUserId.value,
    enable_feishu_push: enableFeishuPush.value,
    feishu_chat_id: feishuChatId.value,
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

function applyTemplate(t: SavedSkill) {
  if (activeTemplateId.value === t.id) {
    clearTemplate()
    return
  }
  activeTemplateId.value = t.id
  const expanded = expandToModelSettings(t)

  if (expanded.copywrite_skill) selectedCopywriteSkill.value = expanded.copywrite_skill
  if (expanded.image_gen_skill) selectedImageGenSkill.value = expanded.image_gen_skill
  if (expanded.analyze_skill) selectedAnalyzeSkill.value = expanded.analyze_skill
  if (expanded.audit_skill) selectedAuditSkill.value = expanded.audit_skill
  if (expanded.temperature !== undefined) temperature.value = Math.round((expanded.temperature as number) * 100)
  if (expanded.content_length !== undefined) contentLength.value = expanded.content_length as number
  if (expanded.auto_emoji !== undefined) autoEmoji.value = expanded.auto_emoji as boolean
  if (expanded.auto_tags !== undefined) autoTags.value = expanded.auto_tags as boolean
  if (expanded.auto_publish !== undefined) autoPublish.value = expanded.auto_publish as boolean
  if (expanded.enable_wechat_push !== undefined) enableWechatPush.value = expanded.enable_wechat_push as boolean
  if (expanded.wechat_target_user_id) wechatTargetUserId.value = expanded.wechat_target_user_id as string
  if (expanded.enable_feishu_push !== undefined) enableFeishuPush.value = expanded.enable_feishu_push as boolean
  if (expanded.feishu_chat_id) feishuChatId.value = expanded.feishu_chat_id as string
  if (expanded.text_model) selectedTextModel.value = expanded.text_model as string
  if (expanded.image_model) selectedImageModel.value = expanded.image_model as string
  if (expanded.search_limit) selectedSearchLimit.value = expanded.search_limit as number

}

function clearTemplate() {
  activeTemplateId.value = null
}

onMounted(() => {
  loadSkills()
  loadWeeklyStats()
})

async function loadWeeklyStats() {
  try {
    const data = await workflowApi.getWeeklyStats()
    weeklyStats.value = {
      published_count: data.published_count ?? 0,
      total_workflows: data.total_workflows ?? 0,
      completed_rate: Math.round((data.completed_rate ?? 0) * 100),
      active_count: data.active_count ?? 0,
    }
  } catch (e: any) {
    console.error('[RightPanel] load weekly stats failed:', e)
  }
}
</script>

<style scoped>
/* ---- 技能模板快选条 ---- */
.mint-template-bar {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px 16px;
  background: linear-gradient(135deg, #FFF7ED 0%, #FEF2F2 100%);
  border-bottom: 1px solid #F3F4F6;
}

.mint-template-bar-label {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 11px;
  font-weight: 600;
  color: #F97316;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.mint-template-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.mint-template-chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 5px 12px;
  border: 1px solid #E5E7EB;
  border-radius: 9999px;
  background: #FFFFFF;
  font-size: 12px;
  color: #374151;
  cursor: pointer;
  transition: all 0.15s ease;
  white-space: nowrap;
}

.mint-template-chip:hover {
  border-color: #F97316;
  background: #FFF7ED;
}

.mint-template-chip-active {
  border-color: #F97316;
  background: linear-gradient(135deg, #FFF7ED, #FFEDD5);
  color: #C2410C;
  font-weight: 500;
  box-shadow: 0 0 0 2px rgba(249, 115, 22, 0.12);
}

.mint-template-chip-icon {
  font-size: 14px;
  line-height: 1;
}

.mint-template-chip-name {
  line-height: 1;
}

.mint-template-chip-clear {
  padding: 5px 10px;
  border-color: #D1D5DB;
  color: #6B7280;
  font-size: 11px;
}

.mint-template-chip-clear:hover {
  border-color: #EF4444;
  background: #FEF2F2;
  color: #EF4444;
}

.mint-config-card {
  position: relative;
  border-radius: 12px;
}

/* 顶部品牌色带，和主工作流卡片外壳一致 */
.mint-config-card::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 3px;
  background: linear-gradient(90deg, #FF2442, #FF6B81, #FF2442);
  border-radius: 12px 12px 0 0;
  z-index: 1;
}

.mint-config-card-title {
  align-items: center;
  gap: 10px;
  letter-spacing: 0;
}

.mint-config-icon {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  background: #FEF2F2;
  color: #FF2442;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.mint-config-card-title-text {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
}

.mint-config-card-title-name {
  font-size: 15px;
  font-weight: 600;
  color: #111827;
  line-height: 1.3;
}

.mint-config-card-title-sub {
  font-size: 12px;
  color: #94A3B8;
  font-weight: 400;
  line-height: 1.35;
}

/* Section 标题图标容器，与工作流节点图标同语言 */
.mint-config-section-title {
  gap: 8px;
}

.mint-config-section-icon {
  width: 24px;
  height: 24px;
  border-radius: 7px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.mint-config-section-icon-model { background: #EFF6FF; color: #3B82F6; }
.mint-config-section-icon-style { background: #F5F3FF; color: #7C3AED; }
.mint-config-section-icon-publish { background: #FFF7ED; color: #D97706; }
.mint-config-section-icon-stats { background: #ECFDF5; color: #10B981; }
</style>