<template>
  <div class="mint-shell wt-shell" :class="{ 'mint-collapsed': isSidebarCollapsed, 'settings-blur': showSettings }">
    <SidebarNav
      current-page="workflow-templates"
      :is-collapsed="isSidebarCollapsed"
      @nav-click="handleNavClick"
      @toggle-sidebar="toggleSidebar"
      @go-eco="goToEco"
      @open-settings="openSettings"
    />

    <main class="mint-main wt-page">
      <div class="mint-content-card-wrapper">
        <div class="mint-content-card wt-content-card">
          <div class="wt-header">
            <div>
              <div class="wt-kicker">
                <i data-lucide="git-branch"></i>
                Dynamic Orchestration
              </div>
              <h1>动态编排</h1>
              <p>把搜索、分析、写作、图片和发布节点组合成你自己的流程。</p>
            </div>
            <div class="wt-actions">
              <button class="mint-btn mint-btn-outline" :disabled="loading" @click="refreshData">
                <i data-lucide="refresh-cw" :class="{ spinning: loading }"></i>
                刷新
              </button>
              <button class="mint-btn mint-btn-primary" @click="goToEditor()">
                <i data-lucide="plus"></i>
                创建流程
              </button>
            </div>
          </div>

          <div class="wt-stats">
            <div class="wt-stat">
              <span class="wt-stat-value">{{ builtinTemplates.length }}</span>
              <span class="wt-stat-label">推荐模板</span>
            </div>
            <div class="wt-stat">
              <span class="wt-stat-value">{{ customDefinitions.length }}</span>
              <span class="wt-stat-label">我的流程</span>
            </div>
            <div class="wt-stat">
              <span class="wt-stat-value">{{ availableNodes.total }}</span>
              <span class="wt-stat-label">可用节点</span>
            </div>
          </div>

          <div class="wt-body">
            <section class="wt-section">
              <div class="wt-section-title">
                <i data-lucide="star"></i>
                <span>推荐模板</span>
              </div>

              <div v-if="loading" class="wt-loading">
                <span class="wt-spinner"></span>
                <span>加载中...</span>
              </div>

              <div v-else class="wt-template-list">
                <button
                  v-for="template in builtinTemplates"
                  :key="template.id"
                  class="wt-template-card"
                  :class="{ selected: selectedTemplate?.id === template.id }"
                  @click="selectTemplate(template)"
                >
                  <span class="wt-template-icon">{{ template.icon }}</span>
                  <span class="wt-template-main">
                    <span class="wt-template-name">{{ template.name }}</span>
                    <span class="wt-template-desc">{{ template.description }}</span>
                    <span class="wt-template-meta">
                      <span><i data-lucide="layers"></i>{{ template.graph_definition?.nodes?.length || 0 }} 节点</span>
                      <span><i data-lucide="play"></i>{{ template.usage_count }} 次使用</span>
                    </span>
                  </span>
                  <span class="wt-template-actions">
                    <span class="wt-card-action" @click.stop="quickStart(template)">立即使用</span>
                    <span class="wt-card-action" @click.stop="editDefinition(template)">编辑</span>
                    <span class="wt-card-action" @click.stop="viewDetails(template)">详情</span>
                  </span>
                </button>
              </div>
            </section>

            <section class="wt-section">
              <div class="wt-section-title">
                <i data-lucide="folder"></i>
                <span>我的流程</span>
                <span class="wt-count">{{ customDefinitions.length }}</span>
              </div>

              <div v-if="loading" class="wt-loading">
                <span class="wt-spinner"></span>
                <span>加载中...</span>
              </div>

              <div v-else-if="customDefinitions.length === 0" class="wt-empty">
                <i data-lucide="inbox"></i>
                <strong>还没有自定义流程</strong>
                <span>从推荐模板开始，或创建一张空白画布。</span>
                <button class="mint-btn mint-btn-primary" @click="goToEditor()">创建第一个流程</button>
              </div>

              <div v-else class="wt-custom-list">
                <div
                  v-for="defn in customDefinitions"
                  :key="defn.id"
                  class="wt-custom-item"
                  @click="selectTemplate(defn)"
                >
                  <span class="wt-custom-icon">{{ defn.icon }}</span>
                  <span class="wt-custom-main">
                    <span class="wt-custom-name">{{ defn.name }}</span>
                    <span class="wt-custom-desc">{{ defn.description || '无描述' }}</span>
                    <span class="wt-tags">
                      <span v-for="tag in (defn.tags || []).slice(0, 3)" :key="tag">#{{ tag }}</span>
                    </span>
                  </span>
                  <span class="wt-status" :class="defn.status">{{ statusLabels[defn.status] || defn.status }}</span>
                  <span class="wt-custom-actions">
                    <button class="mint-icon-btn" title="运行" @click.stop="quickStart(defn)"><i data-lucide="play"></i></button>
                    <button class="mint-icon-btn" title="编辑" @click.stop="editDefinition(defn)"><i data-lucide="edit-2"></i></button>
                    <button class="mint-icon-btn danger" title="删除" @click.stop="confirmDelete(defn)"><i data-lucide="trash-2"></i></button>
                  </span>
                </div>
              </div>
            </section>

            <section class="wt-section">
              <div class="wt-section-title">
                <i data-lucide="cpu"></i>
                <span>可用节点</span>
                <span class="wt-count">{{ availableNodes.total }}</span>
              </div>

              <div class="wt-node-grid">
                <div
                  v-for="cat in availableNodes.categories"
                  :key="cat.category"
                  class="wt-node-category"
                >
                  <div class="wt-node-cat-header">{{ cat.label }} ({{ cat.count }})</div>
                  <div class="wt-node-chips">
                    <span
                      v-for="node in getNodesByCategory(cat.category)"
                      :key="node.node_type"
                      class="wt-node-chip"
                      :title="node.description"
                    >
                      {{ node.icon }} {{ node.display_name }}
                    </span>
                  </div>
                </div>
              </div>
            </section>
          </div>
        </div>
      </div>
    </main>

    <div v-if="showStartDialog" class="wt-modal-overlay" @click.self="showStartDialog = false">
      <div class="wt-modal">
        <div class="wt-modal-header">
          <div>
            <span class="wt-modal-icon">{{ selectedTemplate?.icon }}</span>
            <div>
              <h3>启动工作流</h3>
              <p>{{ selectedTemplate?.name }}</p>
            </div>
          </div>
          <button class="mint-icon-btn" @click="showStartDialog = false"><i data-lucide="x"></i></button>
        </div>
        <form class="wt-modal-body" @submit.prevent="handleStartWorkflow">
          <label>创作主题</label>
          <input
            v-model="startForm.topic"
            class="mint-input"
            placeholder="例如：夏日通勤穿搭"
            required
          />
          <label>发布账号</label>
          <select v-model="startForm.account_id" class="mint-select">
            <option value="">使用默认账号</option>
            <option v-for="account in accounts" :key="account.id" :value="account.id">
              {{ account.xhs_nickname || account.xhs_user_id || account.id }}
            </option>
          </select>

          <div class="wt-params-section">
            <div class="wt-params-title">创作参数（可选）</div>

            <label>文风</label>
            <select v-model="startForm.writing_style" class="mint-select">
              <option value="">默认</option>
              <option value="种草安利">种草安利</option>
              <option value="干货分享">干货分享</option>
              <option value="故事叙述">故事叙述</option>
              <option value="情绪共鸣">情绪共鸣</option>
              <option value="教程攻略">教程攻略</option>
              <option value="测评对比">测评对比</option>
            </select>

            <label>内容长度</label>
            <select v-model="startForm.content_length" class="mint-select">
              <option value="short">短文（200字内）</option>
              <option value="medium">中等（500字内）</option>
              <option value="long">长文（1000字内）</option>
            </select>

            <label>创意度 {{ (startForm.temperature / 100).toFixed(2) }}</label>
            <input
              type="range" min="0" max="100" step="5"
              v-model.number="startForm.temperature"
              class="wt-range"
            />

            <label>搜索条数</label>
            <input
              type="number" min="3" max="30"
              v-model.number="startForm.search_limit"
              class="mint-input"
            />

            <div class="wt-params-toggles">
              <label class="wt-toggle">
                <input type="checkbox" v-model="startForm.auto_emoji" />
                <span>自动添加 Emoji</span>
              </label>
              <label class="wt-toggle">
                <input type="checkbox" v-model="startForm.auto_tags" />
                <span>自动添加标签</span>
              </label>
            </div>
          </div>
          <div class="wt-modal-actions">
            <button type="button" class="mint-btn mint-btn-outline" @click="showStartDialog = false">取消</button>
            <button type="submit" class="mint-btn mint-btn-primary" :disabled="starting || !startForm.topic.trim()">
              {{ starting ? '启动中...' : '确认启动' }}
            </button>
          </div>
        </form>
      </div>
    </div>

    <div v-if="showDetailDialog" class="wt-modal-overlay" @click.self="showDetailDialog = false">
      <div class="wt-modal wt-modal-wide">
        <div class="wt-modal-header">
          <div>
            <span class="wt-modal-icon">{{ detailTemplate?.icon }}</span>
            <div>
              <h3>{{ detailTemplate?.name }}</h3>
              <p>{{ detailTemplate?.description }}</p>
            </div>
          </div>
          <button class="mint-icon-btn" @click="showDetailDialog = false"><i data-lucide="x"></i></button>
        </div>
        <div class="wt-modal-body">
          <div class="wt-detail-stats">
            <div><strong>{{ detailTemplate?.graph_definition?.nodes?.length || 0 }}</strong><span>节点</span></div>
            <div><strong>{{ detailTemplate?.graph_definition?.edges?.length || 0 }}</strong><span>连接</span></div>
            <div><strong>{{ detailTemplate?.usage_count || 0 }}</strong><span>使用</span></div>
            <div><strong>{{ successRate(detailTemplate) }}%</strong><span>成功率</span></div>
          </div>
          <div class="wt-node-flow">
            <template v-for="(node, index) in detailTemplate?.graph_definition?.nodes || []" :key="node.id">
              <span class="wt-flow-node">
                <span>{{ getNodeIcon(node.type) }}</span>
                {{ getNodeName(node.type) }}
              </span>
              <i v-if="Number(index) < (detailTemplate?.graph_definition?.nodes?.length || 0) - 1" data-lucide="chevron-right"></i>
            </template>
          </div>
          <div class="wt-modal-actions">
            <button class="mint-btn mint-btn-primary" @click="quickStart(detailTemplate); showDetailDialog = false">使用此模板</button>
          </div>
        </div>
      </div>
    </div>

    <SettingsView v-if="showSettings" @close="showSettings = false" />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, nextTick, ref } from 'vue'
import { useRouter } from 'vue-router'
import { createIcons, icons } from 'lucide'
import SidebarNav from '@/components/workbench/SidebarNav.vue'
import SettingsView from '@/views/SettingsView.vue'
import workflowDefinitionsApi from '@/api/workflowDefinitions'
import { useAccountStore } from '@/stores/account'
import { useUIState } from '@/composables/useUIState'

const router = useRouter()

const showSettings = ref(false)
function openSettings() {
  showSettings.value = true
}
const accountStore = useAccountStore()
const { isSidebarCollapsed, toggleSidebar } = useUIState()

const loading = ref(false)
const starting = ref(false)
const builtinTemplates = ref<any[]>([])
const customDefinitions = ref<any[]>([])
const availableNodes = ref<any>({ nodes: [], categories: [], total: 0 })
const accounts = ref<any[]>([])
const selectedTemplate = ref<any>(null)
const detailTemplate = ref<any>(null)
const showStartDialog = ref(false)
const showDetailDialog = ref(false)
const startForm = ref({
  topic: '',
  account_id: '',
  text_model: '',
  temperature: 70,
  writing_style: '',
  content_length: 'medium',
  search_limit: 10,
  auto_emoji: true,
  auto_tags: true,
})

const statusLabels: Record<string, string> = {
  draft: '草稿',
  active: '启用',
  archived: '归档',
  deprecated: '废弃',
}

const FALLBACK_BUILTIN_TEMPLATES: any[] = [
  {
    id: 'default-full-workflow',
    name: '完整创作流程',
    description: '搜索 → 分析 → 文案 → 图片规划 → 生图 → 审核 → 合规 → 终审 → 发布',
    icon: '🎯',
    category: 'full_pipeline',
    is_builtin: true,
    status: 'active',
    usage_count: 0,
    success_count: 0,
    graph_definition: {
      nodes: [
        { id: 'node_1', type: 'search', config: {}, position: { x: 50, y: 50 } },
        { id: 'node_2', type: 'analyze', config: {}, position: { x: 250, y: 50 } },
        { id: 'node_3', type: 'copywrite', config: {}, position: { x: 450, y: 50 } },
        { id: 'node_4', type: 'image_plan', config: {}, position: { x: 650, y: 50 } },
        { id: 'node_5', type: 'image_gen', config: {}, position: { x: 850, y: 50 } },
        { id: 'node_6', type: 'image_review', config: {}, position: { x: 1050, y: 50 } },
        { id: 'node_7', type: 'audit', config: {}, position: { x: 1250, y: 50 } },
        { id: 'node_8', type: 'final_review', config: {}, position: { x: 1450, y: 50 } },
        { id: 'node_9', type: 'publish', config: {}, position: { x: 1650, y: 50 } },
      ],
      edges: [
        { id: 'e1', source: 'node_1', target: 'node_2' },
        { id: 'e2', source: 'node_2', target: 'node_3' },
        { id: 'e3', source: 'node_3', target: 'node_4' },
        { id: 'e4', source: 'node_4', target: 'node_5' },
        { id: 'e5', source: 'node_5', target: 'node_6' },
        { id: 'e6', source: 'node_6', target: 'node_7' },
        { id: 'e7', source: 'node_7', target: 'node_8' },
        { id: 'e8', source: 'node_8', target: 'node_9' },
      ],
    },
  },
  {
    id: 'default-search-only',
    name: '仅搜索分析',
    description: '搜索热点 → 要素分析，不生成内容',
    icon: '🔍',
    category: 'search_only',
    is_builtin: true,
    status: 'active',
    usage_count: 0,
    success_count: 0,
    graph_definition: {
      nodes: [
        { id: 'node_1', type: 'search', config: {}, position: { x: 50, y: 50 } },
        { id: 'node_2', type: 'analyze', config: {}, position: { x: 250, y: 50 } },
      ],
      edges: [
        { id: 'e1', source: 'node_1', target: 'node_2' },
      ],
    },
  },
  {
    id: 'default-quick-publish',
    name: '快速图文',
    description: '搜索 → 文案 → 图片规划 → 生图 → 发布（跳过审核）',
    icon: '⚡',
    category: 'quick_publish',
    is_builtin: true,
    status: 'active',
    usage_count: 0,
    success_count: 0,
    graph_definition: {
      nodes: [
        { id: 'node_1', type: 'search', config: {}, position: { x: 50, y: 50 } },
        { id: 'node_2', type: 'copywrite', config: {}, position: { x: 250, y: 50 } },
        { id: 'node_3', type: 'image_plan', config: {}, position: { x: 450, y: 50 } },
        { id: 'node_4', type: 'image_gen', config: {}, position: { x: 650, y: 50 } },
        { id: 'node_5', type: 'publish', config: {}, position: { x: 850, y: 50 } },
      ],
      edges: [
        { id: 'e1', source: 'node_1', target: 'node_2' },
        { id: 'e2', source: 'node_2', target: 'node_3' },
        { id: 'e3', source: 'node_3', target: 'node_4' },
        { id: 'e4', source: 'node_4', target: 'node_5' },
      ],
    },
  },
  {
    id: 'default-search-raw',
    name: '纯搜索',
    description: '仅执行搜索，获取热点数据',
    icon: '🔎',
    category: 'search_raw',
    is_builtin: true,
    status: 'active',
    usage_count: 0,
    success_count: 0,
    graph_definition: {
      nodes: [
        { id: 'node_1', type: 'search', config: {}, position: { x: 50, y: 50 } },
      ],
      edges: [],
    },
  },
  {
    id: 'default-search-copywrite',
    name: '搜索加文案',
    description: '搜索 → 分析 → 文案生成，不生成图片',
    icon: '✍️',
    category: 'search_copywrite',
    is_builtin: true,
    status: 'active',
    usage_count: 0,
    success_count: 0,
    graph_definition: {
      nodes: [
        { id: 'node_1', type: 'search', config: {}, position: { x: 50, y: 50 } },
        { id: 'node_2', type: 'analyze', config: {}, position: { x: 250, y: 50 } },
        { id: 'node_3', type: 'copywrite', config: {}, position: { x: 450, y: 50 } },
      ],
      edges: [
        { id: 'e1', source: 'node_1', target: 'node_2' },
        { id: 'e2', source: 'node_2', target: 'node_3' },
      ],
    },
  },
  {
    id: 'default-copywrite-publish',
    name: '文案加发布',
    description: '文案生成 → 发布（纯文字笔记）',
    icon: '📝',
    category: 'copywrite_publish',
    is_builtin: true,
    status: 'active',
    usage_count: 0,
    success_count: 0,
    graph_definition: {
      nodes: [
        { id: 'node_1', type: 'copywrite', config: {}, position: { x: 50, y: 50 } },
        { id: 'node_2', type: 'publish', config: {}, position: { x: 250, y: 50 } },
      ],
      edges: [
        { id: 'e1', source: 'node_1', target: 'node_2' },
      ],
    },
  },
]

function successRate(template: any): number {
  if (!template?.usage_count) return 0
  return Math.round((template.success_count / template.usage_count) * 100)
}

function showToast(message: string, type: 'success' | 'error' | 'warning' | 'info' = 'info') {
  const el = document.createElement('div')
  el.className = `wt-toast wt-toast-${type}`
  el.textContent = message
  document.body.appendChild(el)
  setTimeout(() => el.remove(), 2800)
}

const FALLBACK_AVAILABLE_NODES = {
  nodes: [
    { node_type: 'search', display_name: '智能搜索', category: 'datasource', icon: '🔍', description: '搜索热点内容' },
    { node_type: 'analyze', display_name: 'AI分析', category: 'analysis', icon: '📊', description: '分析选题价值' },
    { node_type: 'copywrite', display_name: 'AI文案', category: 'creation', icon: '✍️', description: '生成小红书文案' },
    { node_type: 'image_plan', display_name: '图片规划', category: 'creation', icon: '🖼️', description: '规划配图方案' },
    { node_type: 'image_gen', display_name: 'AI生图', category: 'creation', icon: '🎨', description: 'AI生成配图' },
    { node_type: 'image_review', display_name: '图片审核', category: 'review', icon: '👁️', description: '审核图片质量' },
    { node_type: 'audit', display_name: '合规审查', category: 'review', icon: '🛡️', description: '内容合规审查' },
    { node_type: 'final_review', display_name: '终审确认', category: 'review', icon: '✅', description: '人工终审' },
    { node_type: 'publish', display_name: '发布', category: 'publish', icon: '🚀', description: '发布到小红书' },
  ],
  categories: [
    { category: 'datasource', label: '数据源', count: 1 },
    { category: 'analysis', label: '分析', count: 1 },
    { category: 'creation', label: '内容创作', count: 3 },
    { category: 'review', label: '审核', count: 3 },
    { category: 'publish', label: '发布', count: 1 },
  ],
  total: 9,
}

async function refreshData() {
  loading.value = true
  try {
    const [builtinRes, customRes, nodesRes] = await Promise.all([
      workflowDefinitionsApi.getBuiltinTemplates().catch(() => null),
      workflowDefinitionsApi.listWorkflowDefinitions({ include_builtin: false }).catch(() => null),
      workflowDefinitionsApi.getAvailableNodes({ include_details: false }).catch(() => null),
    ])
    builtinTemplates.value = builtinRes?.length
      ? builtinRes.map((t: any) => ({ ...t, _fromApi: true }))
      : FALLBACK_BUILTIN_TEMPLATES
    customDefinitions.value = customRes || []
    availableNodes.value = (nodesRes && nodesRes.nodes && nodesRes.nodes.length > 0)
      ? nodesRes
      : FALLBACK_AVAILABLE_NODES
  } catch (error) {
    console.error('[WorkflowTemplates] load failed:', error)
    builtinTemplates.value = FALLBACK_BUILTIN_TEMPLATES
    availableNodes.value = FALLBACK_AVAILABLE_NODES
  } finally {
    loading.value = false
  }
}

async function loadAccounts() {
  try {
    await accountStore.fetchAccounts()
    accounts.value = accountStore.accounts || []
  } catch {
    accounts.value = []
  }
}

function handleNavClick(pageName: string) {
  if (pageName === 'workflow-templates') return
  router.push({ path: '/workbench', query: pageName === 'workflow' ? {} : { page: pageName } })
}

function goToEco() {
  router.push('/eco')
}

function selectTemplate(template: any) {
  selectedTemplate.value = template
}

function quickStart(template: any) {
  selectedTemplate.value = template
  startForm.value = { topic: '', account_id: '', text_model: '', temperature: 70, writing_style: '', content_length: 'medium', search_limit: 10, auto_emoji: true, auto_tags: true }
  showStartDialog.value = true
}

async function handleStartWorkflow() {
  if (!selectedTemplate.value || !startForm.value.topic.trim()) return
  starting.value = true
  try {
    let definitionId = selectedTemplate.value.id
    const isFromApi = !!selectedTemplate.value._fromApi

    if (!isFromApi) {
      try {
        const existing = await workflowDefinitionsApi.getWorkflowDefinition(definitionId)
        if (existing?.id) {
          definitionId = existing.id
        }
      } catch {
        const created = await workflowDefinitionsApi.createWorkflowDefinition({
          name: selectedTemplate.value.name,
          description: selectedTemplate.value.description,
          icon: selectedTemplate.value.icon,
          category: selectedTemplate.value.category || 'custom',
          graph_definition: selectedTemplate.value.graph_definition,
          tags: ['builtin'],
        })
        definitionId = created.id
      }
    }

    const result = await workflowDefinitionsApi.runWorkflowFromDefinition(definitionId, {
      topic: startForm.value.topic,
      account_id: startForm.value.account_id || undefined,
      model_settings: {
        text_model: startForm.value.text_model || undefined,
        temperature: startForm.value.temperature / 100,
        writing_style: startForm.value.writing_style || undefined,
        content_length: startForm.value.content_length,
        search_limit: startForm.value.search_limit,
        auto_emoji: startForm.value.auto_emoji,
        auto_tags: startForm.value.auto_tags,
      },
    })

    showStartDialog.value = false
    showToast('工作流已启动', 'success')
    router.push({ path: '/workflow-editor', query: { id: definitionId, workflow: result.workflow_id } })
  } catch (error: any) {
    showToast(error?.response?.data?.detail || '启动失败，请重试', 'error')
  } finally {
    starting.value = false
  }
}

function viewDetails(template: any) {
  detailTemplate.value = template
  showDetailDialog.value = true
}

function goToEditor(definitionId?: string, templateData?: any) {
  if (templateData && !definitionId) {
    sessionStorage.setItem('workflow-editor-init', JSON.stringify({
      name: templateData.name,
      description: templateData.description,
      icon: templateData.icon,
      category: templateData.category,
      graph_definition: templateData.graph_definition,
    }))
    router.push('/workflow-editor')
    return
  }
  router.push({ path: '/workflow-editor', query: definitionId ? { id: definitionId } : {} })
}

function editDefinition(defn: any) {
  if (defn.is_builtin && !defn._fromApi) {
    goToEditor(undefined, defn)
  } else {
    goToEditor(defn.id)
  }
}

async function confirmDelete(defn: any) {
  if (!window.confirm(`确定删除流程「${defn.name}」吗？`)) return
  try {
    await workflowDefinitionsApi.deleteWorkflowDefinition(defn.id)
    showToast('已删除', 'success')
    refreshData()
  } catch (error: any) {
    showToast(error?.response?.data?.detail || '删除失败', 'error')
  }
}

function getNodeIcon(nodeType: string): string {
  const map: Record<string, string> = {
    search: '🔍', analyze: '📊', copywrite: '✍️', image_plan: '🎨',
    image_gen: '🖼️', image_review: '👁️', audit: '✅', final_review: '👁️', publish: '📕',
  }
  return map[nodeType] || '📦'
}

function getNodeName(nodeType: string): string {
  const map: Record<string, string> = {
    search: '智能搜索', analyze: 'AI分析', copywrite: '文案生成', image_plan: '图片规划',
    image_gen: '图片生成', image_review: '图片审核', audit: '合规审核', final_review: '终审确认', publish: '发布',
  }
  return map[nodeType] || nodeType
}

function getNodesByCategory(category: string): any[] {
  return availableNodes.value.nodes?.filter((n: any) => n.category === category) || []
}

onMounted(async () => {
  await Promise.all([refreshData(), loadAccounts()])
  nextTick(() => createIcons({ icons }))
})
</script>

<style scoped>
.wt-shell {
  grid-template-columns: auto minmax(0, 1fr) !important;
}

.wt-page {
  min-width: 0;
  min-height: 0;
}

.wt-content-card {
  padding: 24px 26px 28px;
  overflow: auto;
}

.wt-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 24px;
  margin-bottom: 22px;
}

.wt-kicker {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: #ff2442;
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.06em;
  margin-bottom: 8px;
}

.wt-kicker svg { width: 14px; height: 14px; }

.wt-header h1 {
  margin: 0;
  font-size: 26px;
  line-height: 1.2;
  font-weight: 700;
  color: #1a1a1a;
}

.wt-header p {
  margin: 6px 0 0;
  color: #6b7280;
  font-size: 14px;
}

.wt-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

.wt-stats {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 20px;
}

.wt-stat {
  background: #fafafa;
  border: 1px solid #ededed;
  border-radius: 8px;
  padding: 14px 16px;
  display: flex;
  align-items: baseline;
  gap: 8px;
}

.wt-stat-value {
  font-size: 24px;
  font-weight: 700;
  color: #ff2442;
  font-variant-numeric: tabular-nums;
}

.wt-stat-label {
  color: #6b7280;
  font-size: 13px;
}

.wt-body {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  align-items: start;
}

.wt-section {
  min-width: 0;
}

.wt-section-title {
  display: flex;
  align-items: center;
  gap: 7px;
  color: #1a1a1a;
  font-weight: 600;
  font-size: 15px;
  margin-bottom: 12px;
}

.wt-section-title svg { width: 16px; height: 16px; color: #ff2442; }
.wt-count { color: #9a9a9a; font-weight: 500; }

.wt-template-list,
.wt-custom-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.wt-template-card,
.wt-custom-item {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  text-align: left;
  border: 1px solid #ededed;
  border-radius: 8px;
  background: #fff;
  padding: 14px;
  cursor: pointer;
  transition: border-color 0.2s, box-shadow 0.2s, background 0.2s;
  font: inherit;
}

.wt-template-card:hover,
.wt-custom-item:hover {
  border-color: #ff2442;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
}

.wt-template-card.selected {
  border-color: #ff2442;
  background: #fff7f8;
}

.wt-template-icon,
.wt-custom-icon {
  width: 42px;
  height: 42px;
  flex: 0 0 42px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  background: #f5f5f5;
  font-size: 22px;
}

.wt-template-main,
.wt-custom-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.wt-template-name,
.wt-custom-name {
  font-weight: 600;
  color: #1a1a1a;
  font-size: 14px;
}

.wt-template-desc,
.wt-custom-desc {
  color: #6b7280;
  font-size: 12px;
  line-height: 1.45;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.wt-template-meta,
.wt-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  color: #9a9a9a;
  font-size: 11px;
}

.wt-template-meta span {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.wt-template-meta svg { width: 12px; height: 12px; }
.wt-tags span { color: #ff2442; }

.wt-template-actions,
.wt-custom-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

.wt-card-action {
  color: #6b7280;
  font-size: 12px;
  padding: 6px 9px;
  border-radius: 999px;
  background: #f5f5f5;
  transition: color 0.2s, background 0.2s;
}

.wt-card-action:hover { color: #ff2442; background: #fff1f3; }

.wt-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: #6b7280;
  padding: 32px;
}

.wt-spinner {
  width: 16px;
  height: 16px;
  border: 2px solid #ededed;
  border-top-color: #ff2442;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin { to { transform: rotate(360deg); } }
.spinning { animation: spin 0.8s linear infinite; }

.wt-empty {
  min-height: 180px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: #6b7280;
  border: 1px dashed #d1d5db;
  border-radius: 8px;
  padding: 24px;
  text-align: center;
}

.wt-empty svg { width: 30px; height: 30px; color: #d1d5db; }
.wt-empty strong { color: #1a1a1a; font-size: 14px; }
.wt-empty span { font-size: 12px; }

.wt-status {
  font-size: 11px;
  padding: 4px 8px;
  border-radius: 999px;
  flex-shrink: 0;
}

.wt-status.active { background: #ecfdf5; color: #059669; }
.wt-status.draft { background: #fffbeb; color: #d97706; }
.wt-status.archived,
.wt-status.deprecated { background: #f3f4f6; color: #6b7280; }

.mint-icon-btn {
  width: 30px;
  height: 30px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid #ededed;
  border-radius: 8px;
  background: #fff;
  color: #6b7280;
  cursor: pointer;
}

.mint-icon-btn:hover { color: #ff2442; border-color: #ff2442; background: #fff7f8; }
.mint-icon-btn.danger:hover { color: #ef4444; border-color: #ef4444; background: #fef2f2; }
.mint-icon-btn svg { width: 14px; height: 14px; }

.wt-modal-overlay {
  position: fixed;
  inset: 0;
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: rgba(0, 0, 0, 0.35);
}

.wt-modal {
  width: min(460px, 100%);
  max-height: 90vh;
  overflow: auto;
  background: #fff;
  border: 1px solid #ededed;
  border-radius: 12px;
  box-shadow: 0 16px 48px rgba(0, 0, 0, 0.16);
}

.wt-modal-wide { width: min(680px, 100%); }

.wt-modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 18px 20px;
  border-bottom: 1px solid #f3f4f6;
}

.wt-modal-header > div:first-child {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.wt-modal-icon { font-size: 26px; }
.wt-modal-header h3 { margin: 0; font-size: 16px; color: #1a1a1a; }
.wt-modal-header p { margin: 2px 0 0; color: #6b7280; font-size: 12px; }

.wt-modal-body {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 20px;
}

.wt-modal-body label {
  color: #4b4b4b;
  font-size: 13px;
  font-weight: 500;
  margin-top: 8px;
}

.mint-select {
  width: 100%;
  background: #f5f5f5;
  border: 1px solid transparent;
  border-radius: 999px;
  padding: 9px 12px;
  color: #1a1a1a;
  font: inherit;
  outline: none;
}

.mint-select:focus { border-color: #d1d5db; }

.wt-modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 14px;
}

.wt-params-section {
  margin-top: 12px;
  padding: 12px;
  background: #f8f9fa;
  border-radius: 8px;
  border: 1px solid #eee;
}

.wt-params-title {
  font-size: 13px;
  font-weight: 600;
  color: #666;
  margin-bottom: 8px;
}

.wt-params-section label {
  font-size: 12px;
  color: #888;
  margin-bottom: 2px;
  display: block;
}

.wt-range {
  width: 100%;
  margin: 4px 0 8px;
  accent-color: var(--mint-primary, #10b981);
}

.wt-params-toggles {
  display: flex;
  gap: 16px;
  margin-top: 8px;
}

.wt-toggle {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: #555;
  cursor: pointer;
}

.wt-toggle input[type="checkbox"] {
  accent-color: var(--mint-primary, #10b981);
}

.wt-detail-stats {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
}

.wt-detail-stats > div {
  background: #fafafa;
  border: 1px solid #ededed;
  border-radius: 8px;
  padding: 12px;
  text-align: center;
}

.wt-detail-stats strong { display: block; color: #1a1a1a; font-size: 18px; }
.wt-detail-stats span { color: #6b7280; font-size: 11px; }

.wt-node-flow {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  padding: 14px;
  border: 1px solid #ededed;
  border-radius: 8px;
  background: #fafafa;
  margin-top: 12px;
}

.wt-flow-node {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 7px 9px;
  background: #fff;
  border: 1px solid #ededed;
  border-radius: 6px;
  font-size: 12px;
  color: #4b4b4b;
}

.wt-node-flow svg { width: 15px; height: 15px; color: #cbd5e1; }

:global(.wt-toast) {
  position: fixed;
  top: 78px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 2000;
  padding: 10px 16px;
  border-radius: 8px;
  background: #1f2937;
  color: #fff;
  font-size: 13px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.18);
}

:global(.wt-toast-success) { background: #059669; }
:global(.wt-toast-error) { background: #dc2626; }
:global(.wt-toast-warning) { background: #d97706; }

/* ===== 可用节点区域 ===== */
.wt-node-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 12px;
}

.wt-node-category {
  background: rgba(249, 250, 251, 0.8);
  border: 1px solid rgba(229, 231, 235, 0.6);
  border-radius: 8px;
  padding: 10px 12px;
}

.wt-node-cat-header {
  font-size: 12px;
  font-weight: 600;
  color: #6b7280;
  margin-bottom: 8px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.wt-node-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.wt-node-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  background: white;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  font-size: 12px;
  color: #374151;
  cursor: default;
  transition: border-color 0.15s, box-shadow 0.15s;
}

.wt-node-chip:hover {
  border-color: #ff2442;
  box-shadow: 0 0 0 1px rgba(255, 36, 66, 0.15);
}

@media (max-width: 1000px) {
  .wt-body { grid-template-columns: 1fr; }
  .wt-node-grid { grid-template-columns: 1fr; }
}
</style>