<template>
  <div class="sk-wrap">
    <!-- 创建技能模板区域 -->
    <div class="sk-create">
      <div class="sk-create-header">
        <div class="sk-create-title">
          <span>创建技能模板</span>
        </div>
        <button @click="showCreateForm = !showCreateForm" class="sk-toggle-btn">
          <ChevronUp v-if="showCreateForm" :size="14" />
          <ChevronDown v-else :size="14" />
        </button>
      </div>

      <transition name="sk-slide">
        <div v-if="showCreateForm" class="sk-form">
          <div class="sk-form-row">
            <label class="sk-label">名称 <span class="sk-required">*</span></label>
            <input v-model="form.name" class="sk-input" placeholder="如：美食爆款" />
          </div>
          <div class="sk-form-row">
            <label class="sk-label">描述</label>
            <input v-model="form.description" class="sk-input" placeholder="如：活泼少女风+清新自然图，美食类高互动" />
          </div>
          <div class="sk-form-row">
            <label class="sk-label">图标</label>
            <div class="sk-icon-picker">
              <button
                v-for="ico in iconOptions"
                :key="ico"
                class="sk-icon-opt"
                :class="{ 'sk-icon-active': form.icon === ico }"
                @click="form.icon = ico"
              >{{ ico }}</button>
            </div>
          </div>
          <div class="sk-form-row">
            <label class="sk-label">选择工具 <span class="sk-required">*</span></label>
            <div class="sk-tool-grid">
              <div
                v-for="(tools, nt) in skillsMap"
                :key="nt"
                class="sk-tool-group"
              >
                <div class="sk-tool-group-label">{{ nodeTypeLabel(nt as string) }}</div>
                <div class="sk-tool-items">
                  <label
                    v-for="t in tools"
                    :key="t.name"
                    class="sk-tool-check"
                    :class="{ 'sk-tool-checked': form.tools.includes(`${nt}/${t.name}`) }"
                  >
                    <input
                      type="checkbox"
                      :value="`${nt}/${t.name}`"
                      v-model="form.tools"
                      class="sk-checkbox"
                    />
                    <span>{{ t.display_name }}</span>
                  </label>
                </div>
              </div>
            </div>
          </div>
          <div class="sk-form-row">
            <label class="sk-label">配置参数</label>
            <div class="sk-config-area">
              <div v-for="(item, idx) in form.configEntries" :key="idx" class="sk-config-row">
                <input v-model="item.key" class="sk-input sk-input-sm" placeholder="参数名" />
                <input v-model="item.value" class="sk-input sk-input-sm" placeholder="值" />
                <button @click="form.configEntries.splice(idx, 1)" class="sk-config-del" title="删除">
                  <X :size="12" />
                </button>
              </div>
              <button @click="form.configEntries.push({ key: '', value: '' })" class="sk-config-add">
                <Plus :size="12" />
                <span>添加参数</span>
              </button>
            </div>
          </div>
          <div class="sk-form-actions">
            <button @click="handleCreate" class="sk-create-btn" :disabled="!canCreate">
              <Check :size="14" />
              <span>创建</span>
            </button>
            <button @click="resetForm" class="sk-cancel-btn">重置</button>
          </div>
        </div>
      </transition>
    </div>

    <div class="sk-divider"></div>

    <!-- 创建提示词型 Skill -->
    <div class="sk-create">
      <div class="sk-create-header">
        <div class="sk-create-title">
          <FileText :size="14" />
          <span>创建提示词型 Skill</span>
          <span class="sk-create-hint">（.md 文件，纯提示词驱动，零代码）</span>
        </div>
        <button @click="showPromptForm = !showPromptForm" class="sk-toggle-btn">
          <ChevronUp v-if="showPromptForm" :size="14" />
          <ChevronDown v-else :size="14" />
        </button>
      </div>

      <transition name="sk-slide">
        <div v-if="showPromptForm" class="sk-form">
          <div class="sk-form-row">
            <label class="sk-label">节点类型 <span class="sk-required">*</span></label>
            <select v-model="promptForm.nodeType" class="sk-input sk-select">
              <option value="">请选择</option>
              <option v-for="nt in promptNodeTypeOptions" :key="nt.value" :value="nt.value">{{ nt.label }}</option>
            </select>
          </div>
          <div class="sk-form-row">
            <label class="sk-label">标识名 <span class="sk-required">*</span></label>
            <input v-model="promptForm.name" class="sk-input" placeholder="英文小写+下划线，如 my_checker" />
          </div>
          <div class="sk-form-row">
            <label class="sk-label">展示名 <span class="sk-required">*</span></label>
            <input v-model="promptForm.displayName" class="sk-input" placeholder="如：我的检查器" />
          </div>
          <div class="sk-form-row">
            <label class="sk-label">描述</label>
            <input v-model="promptForm.description" class="sk-input" placeholder="一句话描述这个 Skill 做什么" />
          </div>
          <div class="sk-form-row">
            <label class="sk-label">触发词</label>
            <input v-model="promptForm.triggerWordsStr" class="sk-input" placeholder="逗号分隔，如：检查,审核,能不能发" />
          </div>
          <div class="sk-form-row">
            <label class="sk-label">提示引导</label>
            <input v-model="promptForm.promptGuidance" class="sk-input" placeholder="给 Agent 的简短提示，说明何时使用此 Skill" />
          </div>
          <div class="sk-form-row">
            <label class="sk-label">Skill 正文 <span class="sk-required">*</span></label>
            <textarea
              v-model="promptForm.skillBody"
              class="sk-input sk-textarea"
              rows="8"
              placeholder="提示词正文（Markdown 格式）&#10;&#10;示例：&#10;# 我的检查器&#10;&#10;你是一个内容检查专家。用户给你一篇内容，你做以下检查：&#10;&#10;## 检查项&#10;1. 可读性检查&#10;2. 合规检查&#10;&#10;## 输出模板&#10;给出通过/修改/拒绝结论。"
            ></textarea>
          </div>
          <div class="sk-form-actions">
            <button @click="handleCreatePromptSkill" class="sk-create-btn" :disabled="!canCreatePromptSkill || promptCreating">
              <Check :size="14" />
              <span>{{ promptCreating ? '创建中...' : '创建' }}</span>
            </button>
            <button @click="resetPromptForm" class="sk-cancel-btn">重置</button>
          </div>
          <div v-if="promptCreateError" class="sk-error" style="margin-top:8px;">
            <AlertCircle :size="14" />
            <span>{{ promptCreateError }}</span>
          </div>
          <div v-if="promptCreateSuccess" class="sk-success-msg">
            <CheckCircle :size="14" />
            <span>{{ promptCreateSuccess }}</span>
          </div>
        </div>
      </transition>
    </div>

    <div class="sk-divider"></div>

    <!-- 已保存的技能模板 -->
    <div v-if="savedSkills.length > 0" class="sk-saved-section">
      <div class="sk-section-header">
        <div class="sk-section-title">
          <Bookmark :size="16" />
          <span>我的技能模板</span>
        </div>
        <span class="sk-section-count">{{ savedSkills.length }} 个</span>
      </div>
      <div class="sk-saved-list">
        <div v-for="s in savedSkills" :key="s.id" class="sk-saved-card">
          <div class="sk-saved-top">
            <span class="sk-saved-icon">{{ s.icon }}</span>
            <div class="sk-saved-info">
              <div class="sk-saved-name">{{ s.name }}</div>
              <div class="sk-saved-desc">{{ s.description || '无描述' }}</div>
            </div>
            <div class="sk-saved-actions">
              <button @click="handleEdit(s)" class="sk-saved-edit" title="编辑">
                <Pencil :size="12" />
              </button>
              <button @click="handleDeleteSaved(s.id)" class="sk-saved-del" title="删除">
                <Trash2 :size="12" />
              </button>
            </div>
          </div>
          <div class="sk-saved-tools">
            <span v-for="tid in s.tools.slice(0, 5)" :key="tid" class="sk-saved-tool-tag">
              {{ toolDisplayName(tid) }}
            </span>
            <span v-if="s.tools.length > 5" class="sk-saved-tool-tag sk-more-tag">
              +{{ s.tools.length - 5 }}
            </span>
          </div>
          <div v-if="Object.keys(s.config).length > 0" class="sk-saved-config">
            <span v-for="(v, k) in s.config" :key="k" class="sk-config-tag">
              {{ k }}={{ v }}
            </span>
          </div>
        </div>
      </div>
    </div>

    <div v-else class="sk-empty-saved">
      <Bookmark :size="24" style="opacity:0.3;" />
      <span>还没有技能模板，点击上方创建</span>
    </div>

    <div class="sk-divider"></div>

    <!-- 可用工具列表（只读参考） -->
    <div class="sk-tools-section">
      <div class="sk-section-header">
        <div class="sk-section-title">
          <Wrench :size="16" />
          <span>可用工具</span>
        </div>
      </div>

      <div v-if="loading" class="sk-loading">
        <div class="sk-spinner"></div>
        <span>加载中...</span>
      </div>

      <div v-else-if="errorMsg" class="sk-error">
        <AlertCircle :size="18" />
        <span>{{ errorMsg }}</span>
        <button @click="loadSkills" class="sk-retry-btn">重试</button>
      </div>

      <div v-else-if="Object.keys(skillsMap).length === 0" class="sk-empty">
        <Sparkles :size="32" style="opacity:0.4;" />
        <p>暂无可用工具</p>
        <p class="sk-empty-hint">请确保后端服务已启动</p>
      </div>

      <div v-else class="sk-groups">
        <div v-for="(skills, nodeType) in skillsMap" :key="nodeType" class="sk-group">
          <div class="sk-group-header">
            <div class="sk-group-icon">
              <component :is="getNodeIcon(nodeType as string)" :size="16" />
            </div>
            <div>
              <div class="sk-group-title">{{ nodeTypeLabel(nodeType as string) }}</div>
              <div class="sk-group-count">{{ skills.length }} 个工具</div>
            </div>
          </div>
          <div class="sk-list">
            <div v-for="skill in skills" :key="skill.name" class="sk-card">
              <div class="sk-card-top">
                <div class="sk-card-name">{{ skill.display_name }}</div>
                <button
                  v-if="skill.is_third_party || skill.is_prompt_skill"
                  class="sk-card-delete"
                  @click="handleDeleteSkill(skill, nodeType as string)"
                  title="删除"
                >
                  <Trash2 :size="12" />
                </button>
              </div>
              <div class="sk-card-desc">{{ skill.description }}</div>
              <div class="sk-card-meta">
                <span class="sk-card-id">{{ skill.name }}</span>
                <span v-if="skill.is_third_party" class="sk-card-tag-tp">第三方</span>
                <span v-if="skill.is_prompt_skill" class="sk-card-tag-prompt">提示词型</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, nextTick, type Component } from 'vue'
import {
  PlusCircle, ChevronUp, ChevronDown, X, Plus, Check,
  Bookmark, Pencil, Trash2, Wrench, AlertCircle, Sparkles,
  PenTool, Image, ScanSearch, ShieldCheck, Palette, Eye,
  Search, CheckCircle, Send, Box, FileText
} from 'lucide-vue-next'
import { workflowApi, type SkillMeta } from '@/api/workflow'
import { useSkillTemplates, type SavedSkill } from '@/composables/useSkillTemplates'

const nodeTypeIconMap: Record<string, Component> = {
  copywrite: PenTool,
  image_gen: Image,
  analyze: ScanSearch,
  audit: ShieldCheck,
  image_plan: Palette,
  image_review: Eye,
  search: Search,
  final_review: CheckCircle,
  publish: Send,
}

function getNodeIcon(nt: string): Component {
  return nodeTypeIconMap[nt] || Box
}

const { savedSkills, addSkill, removeSkill } = useSkillTemplates()

const skillsMap = ref<Record<string, SkillMeta[]>>({})
const loading = ref(true)
const errorMsg = ref('')
const showCreateForm = ref(false)

const iconOptions = ['🔥', '🍜', '👗', '🏠', '💄', '🎮', '📚', '✈️', '🎵', '📸', '🌟', '💡']

const form = ref({
  name: '',
  description: '',
  icon: '🔥',
  tools: [] as string[],
  configEntries: [] as { key: string; value: string }[],
})

const canCreate = computed(() => form.value.name.trim() && form.value.tools.length > 0)

const nodeTypeLabels: Record<string, string> = {
  copywrite: '文案生成',
  image_gen: '图片生成',
  analyze: '内容分析',
  audit: '合规审核',
  image_plan: '图片规划',
  image_review: '图片审核',
  search: '搜索',
  final_review: '终审',
  publish: '发布',
}

function nodeTypeLabel(nt: string) {
  return nodeTypeLabels[nt] || nt
}

function toolDisplayName(toolId: string): string {
  const [nt, name] = toolId.split('/')
  const tools = skillsMap.value[nt]
  if (tools) {
    const found = tools.find((t) => t.name === name)
    if (found) return found.display_name
  }
  return name || toolId
}

function resetForm() {
  form.value = { name: '', description: '', icon: '🔥', tools: [], configEntries: [] }
}

function handleCreate() {
  if (!canCreate.value) return
  const config: Record<string, string> = {}
  for (const e of form.value.configEntries) {
    if (e.key.trim()) config[e.key.trim()] = e.value
  }
  addSkill({
    name: form.value.name.trim(),
    description: form.value.description.trim(),
    icon: form.value.icon,
    tools: [...form.value.tools],
    config,
  })
  resetForm()
  showCreateForm.value = false
}

function handleEdit(s: SavedSkill) {
  form.value = {
    name: s.name,
    description: s.description,
    icon: s.icon,
    tools: [...s.tools],
    configEntries: Object.entries(s.config).map(([key, value]) => ({ key, value })),
  }
  removeSkill(s.id)
  showCreateForm.value = true
}

function handleDeleteSaved(id: string) {
  const s = savedSkills.value.find((x) => x.id === id)
  if (!s) return
  if (!confirm(`确定删除技能模板「${s.name}」？`)) return
  removeSkill(id)
}

async function loadSkills() {
  loading.value = true
  errorMsg.value = ''
  try {
    const data = await workflowApi.listSkills()
    skillsMap.value = data
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.detail || e?.message || '加载失败，请检查后端服务是否启动'
    skillsMap.value = {}
  } finally {
    loading.value = false
  }
}

const deletingSkill = ref<string | null>(null)

async function handleDeleteSkill(skill: SkillMeta, nodeType: string) {
  const skillType = skill.is_prompt_skill ? '提示词型' : '第三方'
  if (!confirm(`确定删除${skillType} Skill「${skill.display_name}」？\n删除后不可恢复。`)) return
  const key = `${nodeType}/${skill.name}`
  deletingSkill.value = key
  try {
    if (skill.is_prompt_skill) {
      await workflowApi.deletePromptSkill(nodeType, skill.name)
    } else {
      await workflowApi.unregisterSkill(nodeType, skill.name)
    }
    await loadSkills()
  } catch (e: any) {
    const detail = e?.response?.data?.detail || e?.message || '删除失败'
    alert(`删除失败: ${detail}`)
  } finally {
    deletingSkill.value = null
  }
}

// ========== 提示词型 Skill 创建表单 ==========

const showPromptForm = ref(false)
const promptCreating = ref(false)
const promptCreateError = ref('')
const promptCreateSuccess = ref('')

const promptNodeTypeOptions = [
  { value: 'quality_gate', label: '质量关卡' },
  { value: 'topic_evaluator', label: '选题评估' },
  { value: 'analyze', label: '内容分析' },
  { value: 'audit', label: '合规审核' },
  { value: 'copywrite', label: '文案生成' },
  { value: 'final_review', label: '终审' },
  { value: 'image_review', label: '图片审核' },
]

const promptForm = ref({
  nodeType: '',
  name: '',
  displayName: '',
  description: '',
  triggerWordsStr: '',
  promptGuidance: '',
  skillBody: '',
})

const canCreatePromptSkill = computed(() =>
  promptForm.value.nodeType.trim() &&
  promptForm.value.name.trim() &&
  promptForm.value.displayName.trim() &&
  promptForm.value.skillBody.trim()
)

function resetPromptForm() {
  promptForm.value = {
    nodeType: '',
    name: '',
    displayName: '',
    description: '',
    triggerWordsStr: '',
    promptGuidance: '',
    skillBody: '',
  }
  promptCreateError.value = ''
  promptCreateSuccess.value = ''
}

async function handleCreatePromptSkill() {
  if (!canCreatePromptSkill.value) return
  promptCreating.value = true
  promptCreateError.value = ''
  promptCreateSuccess.value = ''

  const triggerWords = promptForm.value.triggerWordsStr
    .split(/[,，]/)
    .map(w => w.trim())
    .filter(Boolean)

  try {
    const resp = await workflowApi.createPromptSkill({
      node_type: promptForm.value.nodeType.trim(),
      name: promptForm.value.name.trim(),
      display_name: promptForm.value.displayName.trim(),
      description: promptForm.value.description.trim(),
      trigger_words: triggerWords,
      prompt_guidance: promptForm.value.promptGuidance.trim(),
      skill_body: promptForm.value.skillBody.trim(),
    })
    promptCreateSuccess.value = resp?.message || '创建成功'
    resetPromptForm()
    await loadSkills()
  } catch (e: any) {
    promptCreateError.value = e?.response?.data?.detail || e?.message || '创建失败'
  } finally {
    promptCreating.value = false
  }
}

onMounted(() => {
  loadSkills()
})
</script>

<style scoped>
.sk-wrap {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

/* ---- 创建区域 ---- */
.sk-create {
  background: var(--ma-bg-subtle, #EEF0F4);
  border: 1px solid var(--ma-border, #E5E7EB);
  border-radius: var(--ma-radius-md, 8px);
  padding: 16px;
}

.sk-create-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.sk-create-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  font-weight: 600;
  color: var(--ma-text-primary, #111827);
}

.sk-create-hint {
  font-size: 11px;
  font-weight: 400;
  color: var(--ma-text-tertiary, #9CA3AF);
}

.sk-toggle-btn {
  display: flex;
  align-items: center;
  padding: 4px 8px;
  border: 1px solid var(--ma-border, #E5E7EB);
  border-radius: 6px;
  background: transparent;
  color: var(--ma-text-secondary, #6B7280);
  cursor: pointer;
  transition: all 0.15s;
}

.sk-toggle-btn:hover {
  background: rgba(59, 108, 246, 0.06);
  color: var(--ma-primary, #3B6CF6);
}

/* ---- 表单 ---- */
.sk-form {
  margin-top: 14px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.sk-form-row {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.sk-label {
  font-size: 12px;
  font-weight: 500;
  color: var(--ma-text-secondary, #6B7280);
}

.sk-required {
  color: var(--ma-destructive, #EF4444);
}

.sk-input {
  padding: 8px 12px;
  border: 1px solid var(--ma-border, #E5E7EB);
  border-radius: 6px;
  background: #FFFFFF;
  font-size: 12px;
  color: var(--ma-text-primary, #111827);
  outline: none;
  transition: border-color 0.15s;
}

.sk-input:focus {
  border-color: var(--ma-primary, #3B6CF6);
}

.sk-input-sm {
  padding: 6px 8px;
  font-size: 11px;
}

.sk-icon-picker {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.sk-icon-opt {
  width: 32px;
  height: 32px;
  border: 1px solid var(--ma-border, #E5E7EB);
  border-radius: 6px;
  background: #FFFFFF;
  font-size: 16px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s;
}

.sk-icon-opt:hover {
  border-color: var(--ma-primary, #3B6CF6);
}

.sk-icon-active {
  border-color: var(--ma-primary, #3B6CF6);
  background: rgba(59, 108, 246, 0.08);
  box-shadow: 0 0 0 2px rgba(59, 108, 246, 0.15);
}

.sk-tool-grid {
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-height: 240px;
  overflow-y: auto;
  padding: 10px;
  background: #FFFFFF;
  border: 1px solid var(--ma-border, #E5E7EB);
  border-radius: 6px;
}

.sk-tool-group-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--ma-text-tertiary, #9CA3AF);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 4px;
}

.sk-tool-items {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.sk-tool-check {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 4px 10px;
  border: 1px solid var(--ma-border, #E5E7EB);
  border-radius: 6px;
  background: #FFFFFF;
  font-size: 11px;
  color: var(--ma-text-secondary, #6B7280);
  cursor: pointer;
  transition: all 0.15s;
  user-select: none;
}

.sk-tool-check:hover {
  border-color: rgba(59, 108, 246, 0.3);
}

.sk-tool-checked {
  border-color: var(--ma-primary, #3B6CF6);
  background: rgba(59, 108, 246, 0.06);
  color: var(--ma-primary, #3B6CF6);
}

.sk-checkbox {
  display: none;
}

.sk-config-area {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.sk-config-row {
  display: flex;
  align-items: center;
  gap: 6px;
}

.sk-config-del {
  padding: 4px;
  border: none;
  background: transparent;
  color: var(--ma-text-tertiary, #6B7280);
  cursor: pointer;
  border-radius: 4px;
}

.sk-config-del:hover {
  color: var(--ma-destructive, #EF4444);
}

.sk-config-add {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  border: 1px dashed var(--ma-border, #E5E7EB);
  border-radius: 6px;
  background: transparent;
  color: var(--ma-text-tertiary, #6B7280);
  font-size: 11px;
  cursor: pointer;
  transition: all 0.15s;
}

.sk-config-add:hover {
  border-color: var(--ma-primary, #3B6CF6);
  color: var(--ma-primary, #3B6CF6);
}

.sk-form-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 4px;
}

.sk-create-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 20px;
  border: none;
  border-radius: var(--ma-radius-md, 8px);
  background: var(--ma-primary, #3B6CF6);
  color: #FFFFFF;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
}

.sk-create-btn:hover:not(:disabled) {
  opacity: 0.9;
}

.sk-create-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.sk-cancel-btn {
  padding: 8px 16px;
  border: 1px solid var(--ma-border, #E5E7EB);
  border-radius: var(--ma-radius-md, 8px);
  background: transparent;
  color: var(--ma-text-secondary, #6B7280);
  font-size: 12px;
  cursor: pointer;
}

.sk-cancel-btn:hover {
  background: var(--ma-bg-subtle, #EEF0F4);
}

.sk-slide-enter-active,
.sk-slide-leave-active {
  transition: all 0.2s ease;
  overflow: hidden;
}

.sk-slide-enter-from,
.sk-slide-leave-to {
  opacity: 0;
  max-height: 0;
}

.sk-slide-enter-to,
.sk-slide-leave-from {
  opacity: 1;
  max-height: 600px;
}

.sk-divider {
  height: 1px;
  background: var(--ma-border, #E5E7EB);
}

/* ---- 已保存技能模板 ---- */
.sk-saved-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.sk-section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.sk-section-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  font-weight: 600;
  color: var(--ma-text-primary, #111827);
}

.sk-section-count {
  font-size: 11px;
  color: var(--ma-text-tertiary, #6B7280);
}

.sk-saved-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 10px;
}

.sk-saved-card {
  background: var(--ma-bg-subtle, #EEF0F4);
  border: 1px solid var(--ma-border, #E5E7EB);
  border-radius: var(--ma-radius-md, 8px);
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  transition: all 0.15s;
}

.sk-saved-card:hover {
  border-color: var(--ma-border-strong, #D1D5DB);
}

.sk-saved-top {
  display: flex;
  align-items: flex-start;
  gap: 10px;
}

.sk-saved-icon {
  font-size: 24px;
  line-height: 1;
  flex-shrink: 0;
}

.sk-saved-info {
  flex: 1;
  min-width: 0;
}

.sk-saved-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--ma-text-primary, #111827);
}

.sk-saved-desc {
  font-size: 11px;
  color: var(--ma-text-secondary, #6B7280);
  line-height: 1.4;
  margin-top: 2px;
}

.sk-saved-actions {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
  opacity: 0;
  transition: opacity 0.15s;
}

.sk-saved-card:hover .sk-saved-actions {
  opacity: 1;
}

.sk-saved-edit,
.sk-saved-del {
  padding: 4px;
  border: none;
  background: transparent;
  color: var(--ma-text-tertiary, #6B7280);
  cursor: pointer;
  border-radius: 4px;
}

.sk-saved-edit:hover {
  color: var(--ma-primary, #3B6CF6);
  background: rgba(59, 108, 246, 0.08);
}

.sk-saved-del:hover {
  color: var(--ma-destructive, #EF4444);
  background: rgba(239, 68, 68, 0.08);
}

.sk-saved-tools {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.sk-saved-tool-tag {
  font-size: 10px;
  padding: 2px 8px;
  border-radius: 9999px;
  background: rgba(59, 108, 246, 0.1);
  color: var(--ma-primary, #3B6CF6);
  font-weight: 500;
}

.sk-more-tag {
  background: rgba(107, 114, 128, 0.1);
  color: var(--ma-text-tertiary, #6B7280);
}

.sk-saved-config {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.sk-config-tag {
  font-size: 10px;
  padding: 2px 6px;
  border-radius: 4px;
  background: rgba(107, 114, 128, 0.08);
  color: var(--ma-text-tertiary, #6B7280);
  font-family: var(--ma-font-mono, monospace);
}

.sk-empty-saved {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 20px;
  color: var(--ma-text-tertiary, #9CA3AF);
  font-size: 12px;
}

/* ---- 工具列表区域 ---- */
.sk-tools-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.sk-loading, .sk-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px 20px;
  color: var(--ma-text-tertiary, #6B7280);
  gap: 12px;
  font-size: 13px;
}

.sk-error {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 18px;
  background: rgba(239, 68, 68, 0.06);
  border: 1px solid rgba(239, 68, 68, 0.15);
  border-radius: var(--ma-radius-md, 8px);
  color: var(--ma-destructive, #EF4444);
  font-size: 13px;
}

.sk-retry-btn {
  margin-left: auto;
  padding: 4px 12px;
  border: 1px solid rgba(239, 68, 68, 0.3);
  border-radius: 6px;
  background: transparent;
  color: var(--ma-destructive, #EF4444);
  font-size: 12px;
  cursor: pointer;
}

.sk-retry-btn:hover {
  background: rgba(239, 68, 68, 0.08);
}

.sk-empty-hint {
  font-size: 11px;
  color: var(--ma-text-disabled, #9CA3AF);
}

.sk-spinner {
  width: 28px;
  height: 28px;
  border: 3px solid var(--ma-border, #E5E7EB);
  border-top-color: var(--ma-primary, #3B6CF6);
  border-radius: 50%;
  animation: skSpin 0.8s linear infinite;
}

@keyframes skSpin { to { transform: rotate(360deg); } }

.sk-groups {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.sk-group-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}

.sk-group-icon {
  width: 32px;
  height: 32px;
  border-radius: var(--ma-radius-md, 8px);
  background: var(--ma-accent, rgba(59, 108, 246, 0.12));
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--ma-primary, #3B6CF6);
}

.sk-group-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--ma-text-primary, #111827);
}

.sk-group-count {
  font-size: 11px;
  color: var(--ma-text-tertiary, #6B7280);
}

.sk-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 8px;
}

.sk-card {
  background: #FFFFFF;
  border: 1px solid var(--ma-border, #E5E7EB);
  border-radius: 6px;
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.sk-card-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.sk-card-name {
  font-size: 12px;
  font-weight: 600;
  color: var(--ma-text-primary, #111827);
}

.sk-card-desc {
  font-size: 11px;
  color: var(--ma-text-secondary, #6B7280);
  line-height: 1.4;
}

.sk-card-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 2px;
}

.sk-card-id {
  font-size: 10px;
  color: var(--ma-text-tertiary, #9CA3AF);
  font-family: var(--ma-font-mono, monospace);
  background: var(--ma-bg-subtle, #EEF0F4);
  padding: 1px 5px;
  border-radius: 3px;
}

.sk-card-tag-tp {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 3px;
  background: rgba(245, 158, 11, 0.1);
  color: #F59E0B;
}

.sk-card-tag-prompt {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 3px;
  background: rgba(59, 108, 246, 0.1);
  color: #3B6CF6;
}

.sk-card-delete {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border: none;
  border-radius: 4px;
  background: transparent;
  color: var(--ma-text-tertiary, #9CA3AF);
  cursor: pointer;
  transition: all 0.12s;
  opacity: 0;
}

.sk-card:hover .sk-card-delete {
  opacity: 1;
}

.sk-card-delete:hover {
  background: rgba(239, 68, 68, 0.1);
  color: var(--ma-destructive, #EF4444);
}

.sk-select {
  appearance: none;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath d='M3 5l3 3 3-3' fill='none' stroke='%236B7280' stroke-width='1.5' stroke-linecap='round'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 10px center;
  padding-right: 28px;
  cursor: pointer;
}

.sk-textarea {
  resize: vertical;
  min-height: 120px;
  line-height: 1.5;
  font-family: var(--ma-font-mono, monospace);
  font-size: 11px;
}

.sk-success-msg {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  background: rgba(34, 197, 94, 0.06);
  border: 1px solid rgba(34, 197, 94, 0.15);
  border-radius: var(--ma-radius-md, 8px);
  color: #22C55E;
  font-size: 12px;
}
</style>