<template>
  <div class="am-wrap">
    <div class="am-create">
      <div class="am-create-header">
        <div class="am-create-title">
          <PlusCircle :size="15" class="am-create-icon" />
          <span>创建智能体</span>
        </div>
        <button @click="showCreateForm = !showCreateForm" class="am-toggle-btn">
          <ChevronUp v-if="showCreateForm" :size="14" />
          <ChevronDown v-else :size="14" />
        </button>
      </div>

      <transition name="am-slide">
        <div v-if="showCreateForm" class="am-form">
          <div class="am-form-row">
            <label class="am-label">ID <span class="am-required">*</span></label>
            <input v-model="form.agent_id" class="am-input" placeholder="如：my_expert" />
          </div>
          <div class="am-form-row">
            <label class="am-label">角色</label>
            <input v-model="form.role" class="am-input" placeholder="如：美食分析专家" />
          </div>
          <div class="am-form-row">
            <label class="am-label">LLM 模型</label>
            <select v-model="form.llm_model" class="am-select">
              <option value="deepseek-v3">DeepSeek V3</option>
              <option value="deepseek-r1">DeepSeek R1</option>
              <option value="mock-test">Mock (测试)</option>
            </select>
          </div>
          <div class="am-form-row">
            <label class="am-label">执行器</label>
            <select v-model="form.executor" class="am-select">
              <option value="loop">Loop (多轮思考)</option>
              <option value="single_shot">Single Shot (一次出结果)</option>
            </select>
          </div>
          <div class="am-form-row" v-if="form.executor === 'loop'">
            <label class="am-label">最大迭代</label>
            <input v-model.number="form.max_iterations" type="number" min="1" max="20" class="am-input am-input-sm" />
          </div>
          <div class="am-form-row">
            <label class="am-label">选择技能</label>
            <div class="am-skill-grid">
              <label
                v-for="s in availableSkills"
                :key="s.name"
                class="am-skill-check"
                :class="{ 'am-skill-checked': form.skills.includes(s.name) }"
              >
                <input type="checkbox" :value="s.name" v-model="form.skills" class="am-checkbox" />
                <span>{{ s.display_name || s.name }}</span>
              </label>
            </div>
          </div>
          <div class="am-form-row">
            <label class="am-label">系统提示词</label>
            <textarea v-model="form.prompt_template" class="am-textarea" rows="4" placeholder="你是一个xxx专家，请..."></textarea>
          </div>
          <div class="am-form-actions">
            <button @click="handleCreate" class="am-create-btn" :disabled="!canCreate">
              <Check :size="14" />
              <span>创建</span>
            </button>
            <button @click="resetForm" class="am-cancel-btn">重置</button>
          </div>
        </div>
      </transition>
    </div>

    <div class="am-divider"></div>

    <div class="am-list-section">
      <div class="am-section-header">
        <div class="am-section-title">
          <Bot :size="16" />
          <span>已注册智能体</span>
        </div>
        <span class="am-section-count">{{ agents.length }} 个在线</span>
      </div>

      <div v-if="loading" class="am-loading">
        <div class="am-spinner"></div>
        <span>扫描智能体网络...</span>
      </div>

      <div v-else-if="errorMsg" class="am-error">
        <AlertCircle :size="18" />
        <span>{{ errorMsg }}</span>
        <button @click="loadAgents" class="am-retry-btn">重试</button>
      </div>

      <div v-else-if="agents.length === 0" class="am-empty">
        <div class="am-empty-orb">
          <Bot :size="28" />
        </div>
        <p>暂无智能体</p>
        <span class="am-empty-hint">点击上方创建你的第一个 AI Agent</span>
      </div>

      <div v-else class="am-grid">
        <div
          v-for="a in agents"
          :key="a.agent_id"
          class="am-card"
          :class="{ 'am-card-builtin': a.is_builtin }"
        >
          <div class="am-card-header">
            <div class="am-agent-icon" :class="a.is_builtin ? 'am-icon-builtin' : 'am-icon-custom'">
              <Bot :size="16" />
            </div>
            <div class="am-card-info">
              <div class="am-card-id">
                <span class="am-card-badge" v-if="a.is_builtin">内置</span>
                <span class="am-card-badge am-card-badge-custom" v-else>自定义</span>
                <span class="am-id-text">{{ a.agent_id }}</span>
              </div>
              <div class="am-card-role">{{ a.role || '无角色描述' }}</div>
            </div>
            <div class="am-card-actions">
              <button @click="openEdit(a)" class="am-card-action" title="编辑">
                <Pencil :size="13" />
              </button>
              <button
                v-if="!a.is_builtin"
                @click="handleDelete(a.agent_id)"
                class="am-card-action am-card-action-danger"
                title="删除"
              >
                <Trash2 :size="13" />
              </button>
            </div>
          </div>

          <div class="am-card-meta">
            <span class="am-meta-chip">
              <Cpu :size="11" />
              {{ a.llm_model || 'default' }}
            </span>
            <span class="am-meta-chip">
              <Zap :size="11" />
              {{ a.executor === 'loop' ? '多轮思考' : '单次执行' }}
            </span>
            <span class="am-meta-chip" v-if="a.executor === 'loop'">
              <RefreshCw :size="11" />
              ≤{{ a.max_iterations }}轮
            </span>
          </div>

          <div class="am-card-skills">
            <span v-for="s in a.skills.slice(0, 4)" :key="s" class="am-skill-tag">{{ s }}</span>
            <span v-if="a.skills.length > 4" class="am-skill-tag am-more-tag">+{{ a.skills.length - 4 }}</span>
            <span v-if="a.skills.length === 0" class="am-skill-tag am-empty-tag">无技能</span>
          </div>
        </div>
      </div>
    </div>

    <teleport to="body">
      <div v-if="editingAgent" class="am-modal-overlay" @click.self="closeEdit">
        <div class="am-modal">
          <div class="am-modal-header">
            <div class="am-modal-title-group">
              <Bot :size="16" class="am-modal-icon" />
              <h3>编辑智能体</h3>
              <span class="am-modal-id">{{ editingAgent.agent_id }}</span>
            </div>
            <button @click="closeEdit" class="am-modal-close"><X :size="16" /></button>
          </div>
          <div class="am-modal-body">
            <div class="am-form-row">
              <label class="am-label">角色</label>
              <input v-model="editForm.role" class="am-input" />
            </div>
            <div class="am-form-row">
              <label class="am-label">LLM 模型</label>
              <select v-model="editForm.llm_model" class="am-select">
                <option value="deepseek-v3">DeepSeek V3</option>
                <option value="deepseek-r1">DeepSeek R1</option>
                <option value="mock-test">Mock (测试)</option>
              </select>
            </div>
            <div class="am-form-row">
              <label class="am-label">执行器</label>
              <select v-model="editForm.executor" class="am-select">
                <option value="loop">Loop (多轮思考)</option>
                <option value="single_shot">Single Shot (一次出结果)</option>
              </select>
            </div>
            <div class="am-form-row" v-if="editForm.executor === 'loop'">
              <label class="am-label">最大迭代</label>
              <input v-model.number="editForm.max_iterations" type="number" min="1" max="20" class="am-input am-input-sm" />
            </div>
            <div class="am-form-row">
              <label class="am-label">选择技能</label>
              <div class="am-skill-grid">
                <label
                  v-for="s in availableSkills"
                  :key="s.name"
                  class="am-skill-check"
                  :class="{ 'am-skill-checked': editForm.skills.includes(s.name) }"
                >
                  <input type="checkbox" :value="s.name" v-model="editForm.skills" class="am-checkbox" />
                  <span>{{ s.display_name || s.name }}</span>
                </label>
              </div>
            </div>
            <div class="am-form-row">
              <label class="am-label">系统提示词</label>
              <textarea v-model="editForm.prompt_template" class="am-textarea" rows="6"></textarea>
            </div>
          </div>
          <div class="am-modal-footer">
            <button @click="handleUpdate" class="am-create-btn" :disabled="saving">
              <Check :size="14" />
              <span>{{ saving ? '保存中...' : '保存' }}</span>
            </button>
            <button @click="handleSwitchLlm" class="am-switch-btn" :disabled="saving" v-if="editForm.llm_model !== editingAgent?.llm_model">
              <Zap :size="14" />
              <span>切换 LLM</span>
            </button>
            <button @click="closeEdit" class="am-cancel-btn">取消</button>
          </div>
        </div>
      </div>
    </teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import {
  PlusCircle, ChevronUp, ChevronDown, X, Plus, Check,
  Pencil, Trash2, Bot, AlertCircle, Cpu, Zap, RefreshCw,
} from 'lucide-vue-next'
import { agentsApi, type AgentSummary, type AgentUpdateRequest } from '@/api/agents'
import { workflowApi, type SkillMeta } from '@/api/workflow'

interface FlatSkill {
  name: string
  display_name: string
  node_type: string
}

const agents = ref<AgentSummary[]>([])
const loading = ref(true)
const errorMsg = ref('')
const saving = ref(false)
const showCreateForm = ref(false)
const editingAgent = ref<AgentSummary | null>(null)
const availableSkills = ref<FlatSkill[]>([])

const form = ref({
  agent_id: '',
  role: '',
  llm_model: 'deepseek-v3',
  executor: 'loop',
  max_iterations: 5,
  skills: [] as string[],
  prompt_template: '',
})

const editForm = ref<AgentUpdateRequest & { skills: string[]; executor: string; max_iterations: number; llm_model: string; prompt_template: string }>({
  role: '',
  llm_model: 'deepseek-v3',
  skills: [],
  executor: 'loop',
  max_iterations: 5,
  prompt_template: '',
})

const canCreate = computed(() => form.value.agent_id.trim() && form.value.skills.length > 0)

function resetForm() {
  form.value = { agent_id: '', role: '', llm_model: 'deepseek-v3', executor: 'loop', max_iterations: 5, skills: [], prompt_template: '' }
}

async function loadAgents() {
  loading.value = true
  errorMsg.value = ''
  try {
    agents.value = await agentsApi.list()
  } catch (e: any) {
    errorMsg.value = e?.message || '加载失败'
  } finally {
    loading.value = false
  }
}

async function loadSkills() {
  try {
    const data = await workflowApi.listSkills()
    const flat: FlatSkill[] = []
    for (const [nt, skills] of Object.entries(data)) {
      for (const s of skills) {
        flat.push({ name: s.name, display_name: s.display_name, node_type: nt })
      }
    }
    availableSkills.value = flat
  } catch {
    // ignore
  }
}

async function handleCreate() {
  if (!canCreate.value) return
  try {
    const resp = await agentsApi.create({
      agent_id: form.value.agent_id.trim(),
      role: form.value.role.trim() || undefined,
      llm_model: form.value.llm_model,
      skills: form.value.skills,
      executor: form.value.executor,
      max_iterations: form.value.max_iterations,
      prompt_template: form.value.prompt_template.trim() || undefined,
    })
    if (resp.success) {
      resetForm()
      showCreateForm.value = false
      await loadAgents()
    } else {
      alert(resp.message || '创建失败')
    }
  } catch (e: any) {
    alert(e?.response?.data?.detail || e?.message || '创建失败')
  }
}

function openEdit(a: AgentSummary) {
  editingAgent.value = a
  editForm.value = {
    role: a.role,
    llm_model: a.llm_model || 'deepseek-v3',
    skills: [...a.skills],
    executor: a.executor,
    max_iterations: a.max_iterations,
    prompt_template: a.prompt_template,
  }
}

function closeEdit() {
  editingAgent.value = null
}

async function handleUpdate() {
  if (!editingAgent.value) return
  saving.value = true
  try {
    const data: AgentUpdateRequest = {}
    if (editForm.value.role !== undefined) data.role = editForm.value.role
    if (editForm.value.llm_model !== undefined) data.llm_model = editForm.value.llm_model
    if (editForm.value.skills !== undefined) data.skills = editForm.value.skills
    if (editForm.value.executor !== undefined) data.executor = editForm.value.executor
    if (editForm.value.max_iterations !== undefined) data.max_iterations = editForm.value.max_iterations
    if (editForm.value.prompt_template !== undefined) data.prompt_template = editForm.value.prompt_template

    const resp = await agentsApi.update(editingAgent.value.agent_id, data)
    if (resp.success) {
      closeEdit()
      await loadAgents()
    } else {
      alert(resp.message || '更新失败')
    }
  } catch (e: any) {
    alert(e?.response?.data?.detail || e?.message || '更新失败')
  } finally {
    saving.value = false
  }
}

async function handleSwitchLlm() {
  if (!editingAgent.value || !editForm.value.llm_model) return
  saving.value = true
  try {
    const resp = await agentsApi.switchLlm(editingAgent.value.agent_id, editForm.value.llm_model)
    if (resp.success) {
      closeEdit()
      await loadAgents()
    } else {
      alert(resp.message || '切换失败')
    }
  } catch (e: any) {
    alert(e?.response?.data?.detail || e?.message || '切换失败')
  } finally {
    saving.value = false
  }
}

async function handleDelete(agentId: string) {
  if (!confirm(`确定删除智能体「${agentId}」？`)) return
  try {
    await agentsApi.delete(agentId)
    await loadAgents()
  } catch (e: any) {
    alert(e?.response?.data?.detail || e?.message || '删除失败')
  }
}

onMounted(() => {
  loadAgents()
  loadSkills()
})
</script>

<style scoped>
.am-wrap { padding: 4px 0; font-size: 13px; color: #374151; }

.am-create-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.am-create-title { display: flex; align-items: center; gap: 8px; font-weight: 600; color: #1A1A1A; }
.am-create-icon { color: #6B7280; }
.am-toggle-btn { background: none; border: none; cursor: pointer; color: #9A9A9A; padding: 4px; border-radius: 4px; transition: background 0.15s; }
.am-toggle-btn:hover { background: #F3F4F6; }

.am-form { display: flex; flex-direction: column; gap: 12px; padding: 14px; background: #F9FAFB; border: 1px solid #E5E7EB; border-radius: 10px; }
.am-form-row { display: flex; flex-direction: column; gap: 4px; }
.am-label { font-size: 12px; color: #6B7280; font-weight: 500; }
.am-required { color: #EF4444; }
.am-input { padding: 7px 10px; border: 1px solid #E5E7EB; border-radius: 7px; font-size: 13px; outline: none; transition: border-color 0.15s; background: white; }
.am-input:focus { border-color: #3B82F6; }
.am-input-sm { width: 80px; }
.am-select { padding: 7px 10px; border: 1px solid #E5E7EB; border-radius: 7px; font-size: 13px; outline: none; background: white; }
.am-select:focus { border-color: #3B82F6; }
.am-textarea { padding: 7px 10px; border: 1px solid #E5E7EB; border-radius: 7px; font-size: 13px; outline: none; resize: vertical; font-family: inherit; }
.am-textarea:focus { border-color: #3B82F6; }

.am-skill-grid { display: flex; flex-wrap: wrap; gap: 6px; }
.am-skill-check { display: flex; align-items: center; gap: 4px; padding: 4px 10px; border: 1px solid #E5E7EB; border-radius: 20px; cursor: pointer; font-size: 12px; transition: all 0.15s; }
.am-skill-check:hover { border-color: #93C5FD; }
.am-skill-checked { background: #EFF6FF; border-color: #3B82F6; color: #1D4ED8; }
.am-checkbox { accent-color: #3B82F6; }

.am-form-actions { display: flex; gap: 8px; padding-top: 4px; }
.am-create-btn { display: flex; align-items: center; gap: 6px; padding: 7px 18px; background: #3B82F6; color: white; border: none; border-radius: 8px; font-size: 13px; cursor: pointer; font-weight: 500; transition: background 0.15s; }
.am-create-btn:hover:not(:disabled) { background: #2563EB; }
.am-create-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.am-cancel-btn { padding: 7px 16px; background: white; color: #6B7280; border: 1px solid #E5E7EB; border-radius: 8px; font-size: 13px; cursor: pointer; }
.am-cancel-btn:hover { background: #F9FAFB; }
.am-switch-btn { display: flex; align-items: center; gap: 6px; padding: 7px 16px; background: #F59E0B; color: white; border: none; border-radius: 8px; font-size: 13px; cursor: pointer; font-weight: 500; }
.am-switch-btn:hover:not(:disabled) { background: #D97706; }

.am-divider { height: 1px; background: #E5E7EB; margin: 20px 0; }

.am-section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 14px; }
.am-section-title { display: flex; align-items: center; gap: 8px; font-weight: 600; font-size: 14px; color: #1A1A1A; }
.am-section-count { font-size: 12px; color: #6B7280; background: #F3F4F6; padding: 2px 10px; border-radius: 20px; font-weight: 500; }

.am-loading, .am-error, .am-empty { display: flex; flex-direction: column; align-items: center; gap: 8px; padding: 32px; color: #9A9A9A; }
.am-spinner { width: 22px; height: 22px; border: 2px solid #E5E7EB; border-top-color: #3B82F6; border-radius: 50%; animation: am-spin 0.6s linear infinite; }
@keyframes am-spin { to { transform: rotate(360deg); } }
.am-error { color: #EF4444; }
.am-retry-btn { padding: 4px 14px; background: #FEE2E2; color: #EF4444; border: none; border-radius: 6px; cursor: pointer; font-size: 12px; }

.am-empty-orb { width: 48px; height: 48px; border-radius: 50%; background: #F3F4F6; display: flex; align-items: center; justify-content: center; color: #9A9A9A; margin-bottom: 4px; }
.am-empty-hint { font-size: 12px; color: #B0B0B0; }

.am-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 10px; }

.am-card { padding: 14px 16px; border: 1px solid #E5E7EB; border-radius: 10px; background: white; transition: box-shadow 0.15s; }
.am-card:hover { box-shadow: 0 2px 8px rgba(0,0,0,0.06); }
.am-card-builtin { }

.am-card-header { display: flex; align-items: flex-start; gap: 10px; margin-bottom: 10px; }

.am-agent-icon { width: 34px; height: 34px; border-radius: 8px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.am-icon-builtin { background: #EFF6FF; color: #3B82F6; }
.am-icon-custom { background: #FEF3C7; color: #D97706; }

.am-card-info { flex: 1; min-width: 0; }
.am-card-id { display: flex; align-items: center; gap: 6px; margin-bottom: 2px; }
.am-id-text { font-weight: 600; color: #1A1A1A; font-size: 13px; font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace; letter-spacing: -0.02em; }
.am-card-badge { font-size: 10px; padding: 1px 7px; border-radius: 10px; font-weight: 500; background: #EFF6FF; color: #3B82F6; }
.am-card-badge-custom { background: #FEF3C7; color: #D97706; }
.am-card-role { font-size: 12px; color: #6B7280; line-height: 1.4; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.am-card-actions { display: flex; gap: 2px; flex-shrink: 0; opacity: 0; transition: opacity 0.15s; }
.am-card:hover .am-card-actions { opacity: 1; }
.am-card-action { background: none; border: none; cursor: pointer; color: #9A9A9A; padding: 4px; border-radius: 4px; transition: all 0.15s; }
.am-card-action:hover { background: #F3F4F6; color: #4B4B4B; }
.am-card-action-danger:hover { background: #FEE2E2; color: #EF4444; }

.am-card-meta { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; }
.am-meta-chip { display: inline-flex; align-items: center; gap: 4px; font-size: 11px; color: #6B7280; padding: 2px 8px; background: #F9FAFB; border-radius: 5px; }

.am-card-skills { display: flex; flex-wrap: wrap; gap: 4px; }
.am-skill-tag { font-size: 11px; padding: 2px 8px; background: #F3F4F6; border-radius: 12px; color: #6B7280; }
.am-more-tag { background: #EFF6FF; color: #3B82F6; }
.am-empty-tag { color: #D1D5DB; }

.am-modal-overlay { position: fixed; inset: 0; z-index: 10002; background: rgba(0,0,0,0.3); backdrop-filter: blur(4px); display: flex; align-items: center; justify-content: center; }
.am-modal { width: 560px; max-width: 90vw; max-height: 80vh; background: white; border-radius: 12px; display: flex; flex-direction: column; box-shadow: 0 20px 60px rgba(0,0,0,0.15); }
.am-modal-header { display: flex; align-items: center; justify-content: space-between; padding: 16px 20px; border-bottom: 1px solid #E5E7EB; }
.am-modal-title-group { display: flex; align-items: center; gap: 8px; }
.am-modal-icon { color: #6B7280; }
.am-modal-header h3 { margin: 0; font-size: 15px; color: #1A1A1A; font-weight: 600; }
.am-modal-id { font-size: 12px; color: #6B7280; font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace; background: #F3F4F6; padding: 2px 8px; border-radius: 5px; }
.am-modal-close { background: none; border: none; cursor: pointer; color: #9A9A9A; padding: 4px; border-radius: 4px; }
.am-modal-close:hover { background: #F3F4F6; }
.am-modal-body { padding: 16px 20px; overflow-y: auto; flex: 1; display: flex; flex-direction: column; gap: 12px; }
.am-modal-footer { display: flex; gap: 8px; padding: 12px 20px; border-top: 1px solid #E5E7EB; }

.am-slide-enter-active, .am-slide-leave-active { transition: all 0.2s ease; overflow: hidden; }
.am-slide-enter-from, .am-slide-leave-to { opacity: 0; max-height: 0; }
.am-slide-enter-to, .am-slide-leave-from { opacity: 1; max-height: 600px; }
</style>