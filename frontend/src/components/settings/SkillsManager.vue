<template>
  <div class="sk-wrap">
    <!-- 注册区域 -->
    <div class="sk-register">
      <div class="sk-register-header">
        <div class="sk-register-title">
          <i data-lucide="plus-circle" style="width:16px;height:16px;"></i>
          <span>注册第三方 Skill</span>
        </div>
        <button @click="showCodeHelp = !showCodeHelp" class="sk-help-toggle">
          <i data-lucide="help-circle" style="width:14px;height:14px;"></i>
          <span>开发指南</span>
        </button>
      </div>

      <transition name="sk-slide">
        <div v-if="showCodeHelp" class="sk-code-help">
          <div class="sk-code-help-title">第三方 Skill 开发步骤</div>
          <ol class="sk-code-help-steps">
            <li>创建 <code>.py</code> 文件，定义 <code>Skill</code> 子类</li>
            <li>声明 <code>node_type</code>、<code>name</code>、<code>display_name</code>、<code>description</code></li>
            <li>实现 <code>async def execute(self, inputs)</code> 方法</li>
            <li>用 <code>@register</code> 装饰器注册</li>
          </ol>
          <div class="sk-code-example">
            <pre><code>from app.tools.base import Skill
from app.tools.registry import register

@register
class MySkill(Skill):
    node_type = "copywrite"
    name = "my_style"
    display_name = "我的风格"
    description = "自定义文案风格"

    async def execute(self, inputs):
        return {"title": "...", "content": "..."}</code></pre>
          </div>
        </div>
      </transition>

      <div class="sk-register-actions">
        <button @click="triggerUpload" class="sk-upload-btn" :disabled="uploading">
          <i :data-lucide="uploading ? 'loader' : 'upload'" :class="{ spinning: uploading }" style="width:14px;height:14px;"></i>
          <span>{{ uploading ? '上传中...' : '上传 .py 文件' }}</span>
        </button>
        <input
          ref="fileInputRef"
          type="file"
          accept=".py"
          style="display:none"
          @change="handleFileUpload"
        />
        <span class="sk-upload-hint">选择 Skill Python 文件上传注册</span>
      </div>

      <div v-if="uploadStatus" class="sk-upload-status" :class="uploadStatus.type">
        <i :data-lucide="uploadStatus.type === 'success' ? 'check-circle' : uploadStatus.type === 'error' ? 'alert-circle' : 'loader'" style="width:14px;height:14px;"></i>
        <span>{{ uploadStatus.message }}</span>
        <button @click="uploadStatus = null" class="sk-status-close">
          <i data-lucide="x" style="width:12px;height:12px;"></i>
        </button>
      </div>
    </div>

    <div class="sk-divider"></div>

    <!-- Skill 列表 -->
    <div v-if="loading" class="sk-loading">
      <div class="sk-spinner"></div>
      <span>加载 Skills 中...</span>
    </div>

    <div v-else-if="errorMsg" class="sk-error">
      <i data-lucide="alert-circle" style="width:18px;height:18px;"></i>
      <span>{{ errorMsg }}</span>
      <button @click="loadSkills" class="sk-retry-btn">重试</button>
    </div>

    <div v-else-if="Object.keys(skillsMap).length === 0" class="sk-empty">
      <i data-lucide="sparkles" style="width:32px;height:32px;opacity:0.4;"></i>
      <p>暂无可用 Skill</p>
      <p class="sk-empty-hint">请确保后端服务已启动并注册了 Skill</p>
    </div>

    <div v-else class="sk-groups">
      <div v-for="(skills, nodeType) in skillsMap" :key="nodeType" class="sk-group">
        <div class="sk-group-header">
          <div class="sk-group-icon">
            <i :data-lucide="nodeTypeIcon(nodeType)" style="width:16px;height:16px;"></i>
          </div>
          <div>
            <div class="sk-group-title">{{ nodeTypeLabel(nodeType) }}</div>
            <div class="sk-group-count">{{ skills.length }} 个 Skill</div>
          </div>
        </div>
        <div class="sk-list">
          <div
            v-for="skill in skills"
            :key="skill.name"
            class="sk-card"
            :class="{ 'sk-card-active': isActiveSkill(nodeType, skill.name) }"
          >
            <div class="sk-card-top">
              <div class="sk-card-name">{{ skill.display_name }}</div>
              <div class="sk-card-badges">
                <span class="sk-card-badge" v-if="isActiveSkill(nodeType, skill.name)">当前</span>
                <span class="sk-card-badge sk-badge-tp" v-if="isThirdParty(nodeType, skill.name)">第三方</span>
              </div>
            </div>
            <div class="sk-card-desc">{{ skill.description }}</div>
            <div class="sk-card-meta">
              <span class="sk-card-id">{{ skill.name }}</span>
              <button
                v-if="isThirdParty(nodeType, skill.name)"
                @click.stop="handleUnregister(nodeType, skill.name, skill.display_name)"
                class="sk-card-delete"
                title="注销此 Skill"
              >
                <i data-lucide="trash-2" style="width:12px;height:12px;"></i>
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, nextTick } from 'vue'
import { createIcons, icons } from 'lucide'
import { workflowApi, type SkillMeta } from '@/api/workflow'

const skillsMap = ref<Record<string, SkillMeta[]>>({})
const loading = ref(true)
const errorMsg = ref('')
const uploading = ref(false)
const uploadStatus = ref<{ type: 'success' | 'error' | 'loading'; message: string } | null>(null)
const showCodeHelp = ref(false)
const fileInputRef = ref<HTMLInputElement | null>(null)

const thirdPartySkills = ref<Set<string>>(new Set())

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

const nodeTypeIcons: Record<string, string> = {
  copywrite: 'pen-tool',
  image_gen: 'image',
  analyze: 'scan-search',
  audit: 'shield-check',
  image_plan: 'palette',
  image_review: 'eye',
  search: 'search',
  final_review: 'check-circle',
  publish: 'send',
}

const builtinSkillNames = new Set([
  'standard', 'vl_analyze', 'lively_girl', 'elegant', 'professional', 'casual',
  'xhs_blueprint', 'xhs_publish', 'trending_search', 'xhs_search',
])

function nodeTypeLabel(nt: string) {
  return nodeTypeLabels[nt] || nt
}

function nodeTypeIcon(nt: string) {
  return nodeTypeIcons[nt] || 'box'
}

function isActiveSkill(_nodeType: string, _skillName: string) {
  return false
}

function isThirdParty(_nodeType: string, skillName: string) {
  return !builtinSkillNames.has(skillName) || thirdPartySkills.value.has(skillName)
}

function triggerUpload() {
  fileInputRef.value?.click()
}

async function handleFileUpload(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  input.value = ''

  if (!file.name.endsWith('.py')) {
    uploadStatus.value = { type: 'error', message: '仅支持 .py 文件' }
    nextTick(() => { try { createIcons({ icons }) } catch {} })
    return
  }

  uploading.value = true
  uploadStatus.value = { type: 'loading', message: `正在注册 ${file.name}...` }
  nextTick(() => { try { createIcons({ icons }) } catch {} })

  try {
    const result = await workflowApi.registerSkill(file)
    if (result.success && result.data) {
      const d = result.data
      thirdPartySkills.value.add(d.skill_name)
      uploadStatus.value = {
        type: 'success',
        message: `Skill "${d.display_name}" (${d.node_type}.${d.skill_name}) 注册成功`,
      }
      await loadSkills()
    } else {
      uploadStatus.value = { type: 'error', message: result.message || '注册失败' }
    }
  } catch (e: any) {
    const detail = e?.response?.data?.detail || e?.message || '注册失败'
    uploadStatus.value = { type: 'error', message: detail }
  } finally {
    uploading.value = false
    nextTick(() => { try { createIcons({ icons }) } catch {} })
    setTimeout(() => { uploadStatus.value = null }, 6000)
  }
}

async function handleUnregister(nodeType: string, skillName: string, displayName: string) {
  if (!confirm(`确定要注销 Skill "${displayName}" 吗？\n注销后对应的 .py 文件将被删除。`)) return
  try {
    await workflowApi.unregisterSkill(nodeType, skillName)
    thirdPartySkills.value.delete(skillName)
    await loadSkills()
  } catch (e: any) {
    const detail = e?.response?.data?.detail || e?.message || '注销失败'
    alert(detail)
  }
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
    nextTick(() => { try { createIcons({ icons }) } catch {} })
  }
}

onMounted(loadSkills)
</script>

<style scoped>
.sk-wrap {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

/* ---- 注册区域 ---- */
.sk-register {
  background: var(--ma-bg-subtle, #EEF0F4);
  border: 1px solid var(--ma-border, #E5E7EB);
  border-radius: var(--ma-radius-md, 8px);
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.sk-register-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.sk-register-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  font-weight: 600;
  color: var(--ma-text-primary, #111827);
}

.sk-help-toggle {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  border: 1px solid var(--ma-border, #E5E7EB);
  border-radius: 6px;
  background: transparent;
  color: var(--ma-text-secondary, #6B7280);
  font-size: 11px;
  cursor: pointer;
  transition: all 0.15s;
}

.sk-help-toggle:hover {
  background: rgba(59, 108, 246, 0.06);
  color: var(--ma-primary, #3B6CF6);
  border-color: rgba(59, 108, 246, 0.2);
}

.sk-code-help {
  background: #FFFFFF;
  border: 1px solid var(--ma-border, #E5E7EB);
  border-radius: 6px;
  padding: 14px;
  font-size: 12px;
  color: var(--ma-text-secondary, #6B7280);
  line-height: 1.6;
}

.sk-code-help-title {
  font-weight: 600;
  color: var(--ma-text-primary, #111827);
  margin-bottom: 8px;
}

.sk-code-help-steps {
  margin: 0 0 10px;
  padding-left: 18px;
}

.sk-code-help-steps li {
  margin-bottom: 2px;
}

.sk-code-help-steps code {
  background: var(--ma-bg-subtle, #EEF0F4);
  padding: 1px 5px;
  border-radius: 3px;
  font-family: var(--ma-font-mono, monospace);
  font-size: 11px;
}

.sk-code-example {
  background: #1E1E2E;
  border-radius: 6px;
  padding: 12px;
  overflow-x: auto;
}

.sk-code-example pre {
  margin: 0;
}

.sk-code-example code {
  color: #CDD6F4;
  font-family: var(--ma-font-mono, 'Consolas', monospace);
  font-size: 11px;
  line-height: 1.5;
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
  margin-top: -12px;
}

.sk-slide-enter-to,
.sk-slide-leave-from {
  opacity: 1;
  max-height: 300px;
}

.sk-register-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.sk-upload-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  border: 1px solid rgba(59, 108, 246, 0.3);
  border-radius: var(--ma-radius-md, 8px);
  background: rgba(59, 108, 246, 0.08);
  color: var(--ma-primary, #3B6CF6);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
}

.sk-upload-btn:hover:not(:disabled) {
  background: rgba(59, 108, 246, 0.15);
  border-color: rgba(59, 108, 246, 0.4);
}

.sk-upload-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.sk-upload-hint {
  font-size: 11px;
  color: var(--ma-text-tertiary, #6B7280);
}

.sk-upload-status {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: 6px;
  font-size: 12px;
}

.sk-upload-status.success {
  background: rgba(34, 197, 94, 0.08);
  border: 1px solid rgba(34, 197, 94, 0.2);
  color: #16A34A;
}

.sk-upload-status.error {
  background: rgba(239, 68, 68, 0.06);
  border: 1px solid rgba(239, 68, 68, 0.15);
  color: var(--ma-destructive, #EF4444);
}

.sk-upload-status.loading {
  background: rgba(59, 108, 246, 0.06);
  border: 1px solid rgba(59, 108, 246, 0.15);
  color: var(--ma-primary, #3B6CF6);
}

.sk-status-close {
  margin-left: auto;
  padding: 2px;
  border: none;
  background: transparent;
  color: inherit;
  opacity: 0.6;
  cursor: pointer;
  border-radius: 4px;
}

.sk-status-close:hover {
  opacity: 1;
}

.spinning {
  animation: skSpin 0.8s linear infinite;
}

.sk-divider {
  height: 1px;
  background: var(--ma-border, #E5E7EB);
}

/* ---- 列表区域 ---- */
.sk-loading, .sk-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
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
  transition: all 0.15s;
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
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 10px;
}

.sk-card {
  background: var(--ma-bg-subtle, #EEF0F4);
  border: 1px solid var(--ma-border, #E5E7EB);
  border-radius: var(--ma-radius-md, 8px);
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  transition: all 0.15s;
}

.sk-card:hover {
  border-color: var(--ma-border-strong, #D1D5DB);
}

.sk-card-active {
  border-color: rgba(59, 108, 246, 0.3);
  background: var(--ma-accent, rgba(59, 108, 246, 0.08));
}

.sk-card-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.sk-card-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--ma-text-primary, #111827);
}

.sk-card-badges {
  display: flex;
  align-items: center;
  gap: 4px;
}

.sk-card-badge {
  font-size: 10px;
  padding: 2px 8px;
  border-radius: var(--ma-radius-full, 9999px);
  background: var(--ma-accent, rgba(59, 108, 246, 0.15));
  color: var(--ma-primary, #3B6CF6);
  font-weight: 500;
}

.sk-badge-tp {
  background: rgba(139, 92, 246, 0.12);
  color: #7C3AED;
}

.sk-card-desc {
  font-size: 11px;
  color: var(--ma-text-secondary, #6B7280);
  line-height: 1.5;
}

.sk-card-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 4px;
}

.sk-card-id {
  font-size: 10px;
  color: var(--ma-text-tertiary, #6B7280);
  font-family: var(--ma-font-mono, monospace);
  background: var(--ma-bg-subtle, #EEF0F4);
  padding: 2px 6px;
  border-radius: 4px;
}

.sk-card-delete {
  margin-left: auto;
  padding: 4px;
  border: none;
  background: transparent;
  color: var(--ma-text-tertiary, #6B7280);
  cursor: pointer;
  border-radius: 4px;
  opacity: 0;
  transition: all 0.15s;
}

.sk-card:hover .sk-card-delete {
  opacity: 1;
}

.sk-card-delete:hover {
  color: var(--ma-destructive, #EF4444);
  background: rgba(239, 68, 68, 0.08);
}
</style>