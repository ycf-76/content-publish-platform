<template>
  <div class="wfe-root">
    <!-- ===== 顶部工具栏 ===== -->
    <header class="wfe-toolbar">
      <div class="wfe-toolbar-left">
        <button class="wfe-tool-btn wfe-back-btn" @click="goBack" title="返回">
          <ArrowLeft :size="16" />
        </button>
        <div class="wfe-title-wrap">
          <input
            v-model="workflowName"
            class="wfe-name-input"
            placeholder="未命名工作流"
            aria-label="工作流名称"
          />
          <span class="wfe-unsaved-badge" v-if="hasUnsavedChanges">
            <CircleDot :size="12" />
            未保存
          </span>
        </div>
      </div>

      <div class="wfe-toolbar-right">
        <button class="wfe-tool-btn" @click="saveWorkflow" :disabled="saving" title="保存 (Ctrl+S)">
          <Save :size="15" />
          <span>{{ saving ? '保存中...' : '保存' }}</span>
        </button>
        
        <button 
          class="wfe-tool-btn wfe-primary-btn" 
          @click="runWorkflow" 
          :disabled="!canRun || running"
          title="运行工作流"
        >
          <Play :size="15" />
          <span>{{ running ? '启动中...' : '运行' }}</span>
        </button>

        <div class="wfe-toolbar-divider"></div>

        <button class="wfe-tool-btn" @click="applyAutoLayout" title="自动排列" :disabled="nodes.length === 0">
          <LayoutGrid :size="15" />
        </button>
        
        <button class="wfe-tool-btn" @click="validateWorkflow" title="验证工作流">
          <CheckCircle :size="15" />
        </button>

        <div class="wfe-toolbar-divider"></div>

        <button class="wfe-tool-btn" @click="showImportDialog = true" title="导入">
          <Upload :size="15" />
        </button>
        <button class="wfe-tool-btn" @click="exportWorkflow" title="导出">
          <Download :size="15" />
        </button>
        
        <button 
          class="wfe-tool-btn wfe-danger-btn" 
          @click="clearCanvas" 
          title="清空画布"
          :disabled="nodes.length === 0"
        >
          <Trash2 :size="15" />
        </button>

        <div class="wfe-toolbar-spacer"></div>

        <button 
          class="wfe-tool-btn" 
          @click="toggleFullscreen" 
          :title="isFullscreen ? '退出全屏 (Esc)' : '全屏'"
        >
          <Maximize2 v-if="!isFullscreen" :size="15" />
          <Minimize2 v-else :size="15" />
        </button>
      </div>
    </header>

    <!-- ===== 主体区域：左侧面板 + 画布 + 右侧面板 ===== -->
    <div class="wfe-main">
      <!-- 左侧节点库 -->
      <aside class="wfe-sidebar" :class="{ 'wfe-collapsed': leftCollapsed }">
        <div class="wfe-sidebar-header">
          <template v-if="!leftCollapsed">
            <h3 class="wfe-sidebar-title">
              <Layers :size="14" />
              节点库
            </h3>
          </template>
          <button 
            class="wfe-collapse-btn"
            @click="leftCollapsed = !leftCollapsed"
            :title="leftCollapsed ? '展开节点库' : '收起节点库'"
          >
            <PanelLeftClose v-if="!leftCollapsed" :size="16" />
            <PanelLeftOpen v-else :size="16" />
          </button>
        </div>

        <div class="wfe-sidebar-body" v-if="!leftCollapsed">
          <!-- 搜索框 -->
          <div class="wfe-search-box">
            <Search :size="14" class="wfe-search-icon" />
            <input 
              type="text" 
              v-model="nodeSearchQuery"
              placeholder="搜索节点..."
              class="wfe-search-input"
            />
          </div>

          <!-- 节点分类列表 -->
          <div class="wfe-node-list">
            <div 
              v-for="category in filteredNodeCategories" 
              :key="category.key"
              class="wfe-node-category"
            >
              <button 
                class="wfe-cat-header"
                :class="{ 'wfe-cat-open': activeCategories.includes(category.key) }"
                @click="toggleCategory(category.key)"
              >
                <span class="wfe-cat-icon">{{ category.icon }}</span>
                <span class="wfe-cat-name">{{ category.label }}</span>
                <span class="wfe-cat-count">{{ category.nodes.length }}</span>
                <ChevronDown :size="12" class="wfe-cat-arrow" />
              </button>

              <transition name="wfe-collapse">
                <div v-show="activeCategories.includes(category.key)" class="wfe-cat-body">
                  <div 
                    v-for="node in category.nodes" 
                    :key="node.node_type"
                    class="wfe-palette-node"
                    draggable="true"
                    @dragstart="onNodeDragStart($event, node)"
                    :title="node.description"
                  >
                    <span class="wfe-node-icon">{{ node.icon }}</span>
                    <div class="wfe-node-info">
                      <span class="wfe-node-name">{{ node.display_name }}</span>
                      <span class="wfe-node-type">{{ node.node_type }}</span>
                    </div>
                  </div>
                </div>
              </transition>
            </div>
          </div>
        </div>

        <!-- 收起时的图标提示 -->
        <div class="wfe-collapsed-hint" v-else>
          <GitBranch :size="18" />
        </div>
      </aside>

      <!-- 可拖拽分割线 -->
      <div class="wfe-resize-handle" v-show="!leftCollapsed"></div>

      <!-- 画布区域 -->
      <main class="wfe-canvas-area">
        <div class="wfe-canvas" ref="canvasContainer">
          <VueFlow
            :id="FLOW_ID"
            v-model:nodes="nodes"
            v-model:edges="edges"
            :default-edge-options="defaultEdgeOptions"
            :snap-to-grid="true"
            :snap-grid="[20, 20]"
            :fit-view-on-init="true"
            :min-zoom="0.2"
            :max-zoom="2"
            :delete-key-code="'Delete'"
            @node-click="onNodeClick"
            @edge-click="onEdgeClick"
            @pane-click="onPaneClick"
            @connect="onConnect"
            @nodes-change="onNodesChange"
            @edges-change="onEdgesChange"
            @drop="onCanvasDrop"
            @dragover="onCanvasDragOver"
            @node-drag-stop="onNodeDragStop"
            class="wfe-vueflow"
          >
            <Controls position="bottom-right" />
            <MiniMap 
              position="bottom-left"
              :pannable="true"
              :zoomable="true"
              :node-color="miniMapNodeColor"
            />

            <template #node-custom="nodeProps">
              <CustomWorkflowNode 
                v-bind="nodeProps" 
                @configure="openConfigPanel"
                @delete="deleteNode"
              />
            </template>
          </VueFlow>

          <!-- 空状态 -->
          <transition name="wfe-fade">
            <div class="wfe-empty-state" v-if="nodes.length === 0">
              <div class="wfe-empty-card">
                <LayoutTemplate :size="32" class="wfe-empty-icon" />
                <h3>开始构建工作流</h3>
                <p>从左侧拖拽节点到画布，或点击下方快速添加</p>
                <div class="wfe-quick-add">
                  <button 
                    v-for="quickNode in quickAddNodes" 
                    :key="quickNode.node_type"
                    class="wfe-quick-btn"
                    @click="addQuickNode(quickNode)"
                  >
                    {{ quickNode.icon }} {{ quickNode.display_name }}
                  </button>
                </div>
              </div>
            </div>
          </transition>
        </div>
      </main>

      <!-- 右侧配置面板 -->
      <aside class="wfe-config-panel" :class="{ 'wfe-panel-visible': showRightPanel && selectedNodeData }">
        <div class="wfe-panel-header">
          <h3 class="wfe-panel-title">
            <span class="wfe-panel-icon">{{ selectedNodeData?.data?.icon || '📦' }}</span>
            {{ selectedNodeData?.data?.label || '节点配置' }}
          </h3>
          <button class="wfe-panel-close" @click="showRightPanel = false" title="关闭">
            <X :size="16" />
          </button>
        </div>

        <div class="wfe-panel-body">
          <div class="wfe-panel-form" v-if="selectedNodeSchema">
            <DynamicForm
              :schema="selectedNodeSchema.config_schema"
              v-model="selectedNodeData.data.config"
              @change="onNodeConfigChange"
            />
          </div>

          <div v-else class="wfe-panel-simple">
            <div class="wfe-info-row">
              <label>节点类型</label>
              <span class="wfe-type-badge">{{ selectedNodeData?.data?.nodeType || 'custom' }}</span>
            </div>
            <div class="wfe-info-row" v-if="selectedNodeData?.data?.config && Object.keys(selectedNodeData.data.config).length > 0">
              <label>当前配置</label>
              <pre class="wfe-config-preview">{{ formatJson(selectedNodeData.data.config) }}</pre>
            </div>
          </div>

          <div class="wfe-panel-footer">
            <button class="wfe-delete-btn" @click="confirmDeleteNode">
              <Trash2 :size="14" />
              删除此节点
            </button>
          </div>
        </div>
      </aside>
    </div>

    <!-- 导入对话框 -->
    <Teleport to="body">
      <div class="wfe-modal-backdrop" v-if="showImportDialog" @click.self="showImportDialog = false">
        <div class="wfe-modal">
          <div class="wfe-modal-header">
            <h3>导入工作流</h3>
            <button class="wfe-modal-close" @click="showImportDialog = false"><X :size="18" /></button>
          </div>
          <div class="wfe-modal-body">
            <p class="wfe-modal-desc">粘贴工作流 JSON 定义：</p>
            <textarea 
              v-model="importJsonText"
              placeholder='{"name": "...", "graph_definition": {"nodes": [...], "edges": [...]}}'
              class="wfe-import-textarea"
              rows="10"
            ></textarea>
            <div class="wfe-modal-actions">
              <button class="wfe-btn wfe-btn-primary" @click="handleImport">确认导入</button>
              <button class="wfe-btn wfe-btn-secondary" @click="showImportDialog = false">取消</button>
            </div>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- 验证结果 Toast -->
    <Teleport to="body">
      <transition name="wfe-slide-down">
        <div class="wfe-toast" v-if="validationResult" :class="'wfe-toast-' + validationResult.valid">
          <CheckCircle v-if="validationResult.valid" :size="16" />
          <AlertCircle v-else :size="16" />
          {{ validationResult.message }}
        </div>
      </transition>
    </Teleport>

    <ConfirmDialog
      :visible="confirmState.visible"
      :title="confirmState.title"
      :message="confirmState.message"
      :confirm-text="confirmState.confirmText"
      :cancel-text="confirmState.cancelText"
      :danger="confirmState.danger"
      @confirm="onConfirm"
      @cancel="onCancel"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import { VueFlow, useVueFlow, Position } from '@vue-flow/core'
import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import { Controls } from '@vue-flow/controls'
import '@vue-flow/controls/dist/style.css'
import { MiniMap } from '@vue-flow/minimap'
import '@vue-flow/minimap/dist/style.css'
import {
  AlertCircle, ArrowLeft, CheckCircle, CircleDot, Download,
  GitBranch, LayoutGrid, LayoutTemplate, Maximize2, Minimize2,
  PanelLeftClose, PanelLeftOpen, Play, Save, Search, Trash2, Upload, X, ChevronDown, Layers
} from 'lucide-vue-next'
import workflowDefinitionsApi from '@/api/workflowDefinitions'
import CustomWorkflowNode from './CustomWorkflowNode.vue'
import DynamicForm from '@/components/common/DynamicForm.vue'
import { useConfirm } from '@/composables/useConfirm'
import ConfirmDialog from '@/components/common/ConfirmDialog.vue'

const { state: confirmState, confirm, onConfirm, onCancel } = useConfirm()

function showToast(message: string, type: 'success' | 'error' | 'warning' | 'info' = 'info') {
  const toast = document.createElement('div')
  toast.textContent = message
  
  const colors: Record<string, { bg: string; color: string; border: string }> = {
    success: { bg: '#f0fdf4', color: '#166534', border: '#bbf7d0' },
    error: { bg: '#fef2f2', color: '#991b1b', border: '#fecaca' },
    warning: { bg: '#fffbeb', color: '#92400e', border: '#fde68a' },
    info: { bg: '#eff6ff', color: '#1e40af', border: '#bfdbfe' },
  }
  
  const theme = colors[type]
  Object.assign(toast.style, {
    position: 'fixed',
    top: '72px',
    left: '50%',
    transform: 'translateX(-50%)',
    padding: '10px 20px',
    borderRadius: 'var(--ma-radius-md)',
    fontSize: 'var(--ma-font-sm)',
    fontWeight: '500',
    zIndex: '9999',
    boxShadow: 'var(--ma-shadow-lg)',
    background: theme.bg,
    color: theme.color,
    border: `1px solid ${theme.border}`,
  })
  
  document.body.appendChild(toast)
  setTimeout(() => {
    toast.style.opacity = '0'
    toast.style.transition = 'opacity 0.25s ease'
    setTimeout(() => toast.remove(), 250)
  }, 2800)
}

async function showConfirm(message: string): Promise<boolean> {
  return confirm({ message, danger: true })
}

const props = defineProps<{
  definitionId?: string
}>()

const emit = defineEmits<{
  (e: 'saved', definitionId: string): void
  (e: 'run', workflowId: string): void
  (e: 'fullscreen', isFullscreen: boolean): void
}>()

const currentDefinitionId = ref<string | undefined>(props.definitionId)

const FLOW_ID = 'workflow-editor-flow'
const vueFlowInstance = useVueFlow({ id: FLOW_ID })
const { addEdges, addNodes, removeNodes, removeEdges, fitView, screenToFlowCoordinate } = vueFlowInstance

// ===== 状态 =====
const nodes = ref<any[]>([])
const edges = ref<any[]>([])

const FALLBACK_NODES: any[] = [
  { node_type: 'search', display_name: '选题搜索', description: '从内容池搜索热门选题', category: 'datasource', icon: '🔍', config_schema: { type: 'object', properties: { keyword: { type: 'string', title: '搜索关键词' }, max_results: { type: 'integer', title: '最大结果数', default: 5 } } }, tags: [] },
  { node_type: 'analyze', display_name: '选题分析', description: '分析选题热度和趋势', category: 'analysis', icon: '📊', config_schema: { type: 'object', properties: { depth: { type: 'string', title: '分析深度', enum: ['quick', 'normal', 'deep'], default: 'normal' } } }, tags: [] },
  { node_type: 'copywrite', display_name: '文案生成', description: '生成小红书文案', category: 'creation', icon: '✍️', config_schema: { type: 'object', properties: { model: { type: 'string', title: '模型', enum: ['deepseek-chat', 'gpt-4o-mini'], default: 'deepseek-chat' }, style: { type: 'string', title: '风格', enum: ['种草', '教程', '日常', '测评'], default: '种草' }, content_length: { type: 'integer', title: '文案长度（字）', minimum: 100, maximum: 500, default: 300 }, require_review: { type: 'boolean', title: '需要人工审核', default: true } } }, tags: [] },
  { node_type: 'image_plan', display_name: '图片规划', description: '规划配图方案', category: 'creation', icon: '🖼️', config_schema: { type: 'object', properties: { count: { type: 'integer', title: '图片数量', default: 3 } } }, tags: [] },
  { node_type: 'image_gen', display_name: '图片生成', description: '生成配图', category: 'creation', icon: '🎨', config_schema: { type: 'object', properties: { style: { type: 'string', title: '风格', enum: ['realistic', 'illustration', 'flat-design'], default: 'realistic' } } }, tags: [] },
  { node_type: 'image_review', display_name: '图片审核', description: '审核图片质量和合规性', category: 'review', icon: '👁️', config_schema: { type: 'object', properties: { strict: { type: 'boolean', title: '严格模式', default: true } } }, tags: [] },
  { node_type: 'audit', display_name: '合规审查', description: '内容合规审查', category: 'review', icon: '🛡️', config_schema: { type: 'object', properties: { level: { type: 'string', title: '审查级别', enum: ['basic', 'standard', 'strict'], default: 'standard' } } }, tags: [] },
  { node_type: 'final_review', display_name: '终审确认', description: '人工终审确认', category: 'review', icon: '✅', config_schema: { type: 'object', properties: { require_approval: { type: 'boolean', title: '需要人工审批', default: true } } }, tags: [] },
  { node_type: 'publish', display_name: '发布', description: '发布到小红书', category: 'publish', icon: '🚀', config_schema: { type: 'object', properties: { auto_publish: { type: 'boolean', title: '自动发布', default: false } } }, tags: [] },
]

const FALLBACK_CATEGORIES: any[] = [
  { key: 'datasource', label: '数据源', icon: '📡', color: '#10b981', nodes: FALLBACK_NODES.filter(n => n.category === 'datasource') },
  { key: 'analysis', label: '分析', icon: '📊', color: '#6366f1', nodes: FALLBACK_NODES.filter(n => n.category === 'analysis') },
  { key: 'creation', label: '内容创作', icon: '✨', color: '#f59e0b', nodes: FALLBACK_NODES.filter(n => n.category === 'creation') },
  { key: 'review', label: '审核', icon: '🔍', color: '#ef4444', nodes: FALLBACK_NODES.filter(n => n.category === 'review') },
  { key: 'publish', label: '发布', icon: '🚀', color: '#8b5cf6', nodes: FALLBACK_NODES.filter(n => n.category === 'publish') },
]

// UI状态
const leftCollapsed = ref(true)
const showRightPanel = ref(false)
const nodeSearchQuery = ref('')
const activeCategories = ref<string[]>(['datasource', 'analysis', 'creation', 'review', 'publish'])
const saving = ref(false)
const running = ref(false)
const isFullscreen = ref(false)
const showImportDialog = ref(false)
const importJsonText = ref('')
const hasUnsavedChanges = ref(false)

const selectedNodeId = ref<string | null>(null)
const selectedNode = computed<any>(() => nodes.value.find((n: any) => n.id === selectedNodeId.value))
const selectedNodeData = computed<any>(() => selectedNode.value || null)
const selectedNodeSchema = computed<any>(() => {
  if (!selectedNode.value) return null
  return availableNodes.value.find((n: any) => n.node_type === selectedNode.value.data?.nodeType) || null
})

const workflowName = ref('新工作流')
const workflowDescription = ref('')
const workflowCategory = ref('custom')
const workflowTagsInput = ref('')

const availableNodes = ref<any[]>([])
const allNodeCategories = ref<any[]>([])

const validationResult = ref<any>(null)

// ===== 计算属性 =====
const filteredNodeCategories = computed(() => {
  const query = nodeSearchQuery.value.toLowerCase().trim()
  let categories = allNodeCategories.value.map(cat => ({
    ...cat,
    nodes: cat.nodes.filter((node: any) => {
      if (!query) return true
      return (
        node.display_name.toLowerCase().includes(query) ||
        node.node_type.toLowerCase().includes(query) ||
        node.description?.toLowerCase().includes(query)
      )
    }),
  }))
  return categories.filter(cat => cat.nodes.length > 0)
})

const quickAddNodes = computed(() => {
  const popularTypes = ['search', 'copywrite', 'publish']
  return availableNodes.value.filter(n => popularTypes.includes(n.node_type)).slice(0, 3)
})

const canRun = computed(() => nodes.value.length >= 1 && workflowName.value.trim() !== '')

const defaultEdgeOptions: any = {
  type: 'smoothstep',
  animated: true,
  style: { stroke: 'var(--ma-primary)', strokeWidth: 2 },
  markerEnd: { type: 'arrowclosed' as any, color: 'var(--ma-primary)' },
}

// ===== 自动布局算法 =====
function computeAutoLayout(
  nodeList: any[],
  edgeList: any[],
  options?: { nodeWidth?: number; nodeHeight?: number; gapX?: number; gapY?: number; paddingX?: number; paddingY?: number }
): Map<string, { x: number; y: number }> {
  const { nodeWidth = 220, nodeHeight = 100, gapX = 120, gapY = 50, paddingX = 80, paddingY = 80 } = options || {}
  if (nodeList.length === 0) return new Map()
  const GRID = 20
  const snapToGrid = (v: number) => Math.round(v / GRID) * GRID
  const nodeIds = new Set(nodeList.map((n: any) => n.id))
  const adj = new Map<string, string[]>()
  const inDegree = new Map<string, number>()
  for (const n of nodeList) { adj.set(n.id, []); inDegree.set(n.id, 0) }
  for (const e of edgeList) {
    if (nodeIds.has(e.source) && nodeIds.has(e.target)) {
      adj.get(e.source)!.push(e.target)
      inDegree.set(e.target, (inDegree.get(e.target) || 0) + 1)
    }
  }
  const layers = new Map<string, number>()
  const queue: string[] = []
  for (const [nid, deg] of inDegree) { if (deg === 0) { queue.push(nid); layers.set(nid, 0) } }
  let qi = 0
  while (qi < queue.length) {
    const nid = queue[qi++]
    const currentLayer = layers.get(nid)!
    for (const neighbor of adj.get(nid) || []) {
      const newLayer = currentLayer + 1
      const existingLayer = layers.get(neighbor)
      if (existingLayer === undefined || newLayer > existingLayer) layers.set(neighbor, newLayer)
      const newDeg = (inDegree.get(neighbor) || 1) - 1
      inDegree.set(neighbor, newDeg)
      if (newDeg === 0) queue.push(neighbor)
    }
  }
  let maxLayer = 0
  for (const l of layers.values()) { if (l > maxLayer) maxLayer = l }
  for (const n of nodeList) { if (!layers.has(n.id)) { maxLayer++; layers.set(n.id, maxLayer) } }
  const layerGroups = new Map<number, string[]>()
  for (const [nid, layer] of layers) { if (!layerGroups.has(layer)) layerGroups.set(layer, []); layerGroups.get(layer)!.push(nid) }
  const maxNodesInLayer = Math.max(...Array.from(layerGroups.values()).map(g => g.length), 1)
  const totalHeight = maxNodesInLayer * nodeHeight + (maxNodesInLayer - 1) * gapY
  const positions = new Map<string, { x: number; y: number }>()
  for (const [layer, nodeIdsInLayer] of layerGroups) {
    const layerHeight = nodeIdsInLayer.length * nodeHeight + (nodeIdsInLayer.length - 1) * gapY
    const startY = Math.max(paddingY, (totalHeight - layerHeight) / 2 + paddingY)
    nodeIdsInLayer.forEach((nid, idx) => {
      positions.set(nid, { x: Math.max(GRID, snapToGrid(paddingX + layer * (nodeWidth + gapX))), y: Math.max(GRID, snapToGrid(startY + idx * (nodeHeight + gapY))) })
    })
  }
  return positions
}

function applyAutoLayout() {
  const positions = computeAutoLayout(nodes.value, edges.value)
  nodes.value = nodes.value.map((n: any) => { const pos = positions.get(n.id); return pos ? { ...n, position: pos } : n })
  hasUnsavedChanges.value = true
  setTimeout(() => fitView({ padding: 0.3, duration: 400 }), 100)
  showToast('✅ 已自动排列节点', 'success')
}

function miniMapNodeColor(node: any) {
  const map: Record<string, string> = { datasource: '#10b981', creation: '#f59e0b', review: '#ef4444', publish: '#8b5cf6', utility: '#6b7280' }
  return map[node.data?.category] || '#94a3b8'
}

// ===== 方法 =====
function toggleCategory(key: string) {
  const idx = activeCategories.value.indexOf(key)
  if (idx >= 0) activeCategories.value.splice(idx, 1)
  else activeCategories.value.push(key)
}

async function loadAvailableNodes() {
  try {
    const result = await workflowDefinitionsApi.getAvailableNodes({ include_details: true })
    if (result?.nodes?.length > 0) {
      availableNodes.value = result.nodes
      const meta: Record<string, { icon: string; color: string }> = {
        datasource: { icon: '📡', color: '#10b981' }, analysis: { icon: '📊', color: '#6366f1' },
        creation: { icon: '✨', color: '#f59e0b' }, review: { icon: '🔍', color: '#ef4444' },
        publish: { icon: '🚀', color: '#8b5cf6' }, utility: { icon: '🔧', color: '#6b7280' }, custom: { icon: '📦', color: '#94a3b8' },
      }
      const grouped = new Map<string, any[]>()
      result.nodes.forEach((node: any) => { const cat = node.category || 'custom'; if (!grouped.has(cat)) grouped.set(cat, []); grouped.get(cat)!.push(node) })
      allNodeCategories.value = Array.from(grouped.entries()).map(([cat, catNodes]) => {
        const m = meta[cat] || meta.custom
        const bc = result.categories?.find((c: any) => c.category === cat)
        return { key: cat, label: bc?.label || cat, icon: m.icon, color: m.color, nodes: catNodes }
      })
      return
    }
  } catch (error: any) {
    console.warn('[WFE] API failed:', error?.message)
  }
  availableNodes.value = FALLBACK_NODES
  allNodeCategories.value = FALLBACK_CATEGORIES
}

async function loadDefinition(definitionId: string) {
  try {
    saving.value = true
    const definition = await workflowDefinitionsApi.getWorkflowDefinition(definitionId)
    currentDefinitionId.value = definition.id
    workflowName.value = definition.name
    workflowDescription.value = definition.description || ''
    workflowCategory.value = definition.category
    workflowTagsInput.value = (definition.tags || []).join(', ')
    
    const graphDef = definition.graph_definition
    if (graphDef.nodes) {
      nodes.value = graphDef.nodes.map((n: any) => ({
        id: n.id, type: 'custom', position: n.position || { x: 0, y: 0 },
        data: { label: getNodeDisplayName(n.type), icon: getNodeIcon(n.type), nodeType: n.type, config: n.config || {}, category: getNodeCategory(n.type) },
      }))
    }
    if (graphDef.edges) {
      edges.value = graphDef.edges.map((e: any) => ({
        id: e.id, source: e.source, target: e.target, sourceHandle: e.source_handle, targetHandle: e.target_handle,
        type: 'smoothstep', animated: true, label: e.label, ...defaultEdgeOptions,
      }))
    }
    nextTick(() => { applyAutoLayout() })
    showToast('✅ 已加载: ' + definition.name, 'success')
  } catch (error: any) {
    showToast(error.response?.data?.detail || '加载失败', 'error')
  } finally { saving.value = false }
}

const dragNodeType = ref<string | null>(null)

function onNodeDragStart(event: DragEvent, nodeData: any) {
  if (!event.dataTransfer) return
  event.dataTransfer.setData('application/vueflow', JSON.stringify(nodeData))
  event.dataTransfer.effectAllowed = 'move'
  dragNodeType.value = nodeData.node_type
}

function onCanvasDragOver(event: DragEvent) { event.preventDefault(); if (event.dataTransfer) event.dataTransfer.dropEffect = 'move' }

function onCanvasDrop(event: DragEvent) {
  event.preventDefault()
  const payload = event.dataTransfer?.getData('application/vueflow')
  if (!payload) return
  try {
    const nodeData = JSON.parse(payload)
    const position = screenToFlowCoordinate({ x: event.clientX, y: event.clientY })
    position.x = Math.round(position.x / 20) * 20
    position.y = Math.round(position.y / 20) * 20
    
    addNodes([{
      id: `node_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
      type: 'custom',
      position: { x: Math.max(20, position.x), y: Math.max(20, position.y) },
      data: { label: nodeData.display_name, icon: nodeData.icon, nodeType: nodeData.node_type, config: {}, category: nodeData.category || 'custom' },
    }])
    hasUnsavedChanges.value = true
    dragNodeType.value = null
    showToast(`✅ 已添加: ${nodeData.display_name}`, 'success')
  } catch (error) { showToast('添加节点失败', 'error') }
}

function addQuickNode(nodeData: any) {
  let lastX = 60, lastY = 60
  if (nodes.value.length > 0) {
    const rightmost = nodes.value.reduce((max: any, n: any) => (n.position?.x || 0) > (max.position?.x || 0) ? n : max, nodes.value[0])
    lastX = (rightmost.position?.x || 0) + 320
    lastY = rightmost.position?.y || 60
  }
  addNodes([{ id: `node_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`, type: 'custom', position: { x: lastX, y: lastY }, data: { label: nodeData.display_name, icon: nodeData.icon, nodeType: nodeData.node_type, config: {}, category: nodeData.category } }])
  hasUnsavedChanges.value = true
}

function onNodeClick({ node }: { node: any }) { selectedNodeId.value = node.id; showRightPanel.value = true }
function onEdgeClick() { selectedNodeId.value = null }
function onPaneClick() { selectedNodeId.value = null }

function onConnect(params: any) {
  addEdges([{ id: `edge_${Date.now()}`, source: params.source!, target: params.target!, sourceHandle: params.sourceHandle, targetHandle: params.targetHandle, type: 'smoothstep', animated: true, ...defaultEdgeOptions }])
  hasUnsavedChanges.value = true
}
function onNodesChange(changes: any[]) { for (const c of changes) { if (c.type === 'remove') hasUnsavedChanges.value = true } }
function onEdgesChange(changes: any[]) { for (const c of changes) { if (c.type === 'remove') hasUnsavedChanges.value = true } }
function onNodeDragStop() { hasUnsavedChanges.value = true }

function openConfigPanel(nodeId: string) { selectedNodeId.value = nodeId; showRightPanel.value = true }
function onNodeConfigChange(newConfig: any) { if (selectedNode.value) { selectedNode.value.data.config = newConfig; hasUnsavedChanges.value = true } }

function deleteNode(nodeId: string) { confirmDeleteNodeWithId(nodeId) }
function confirmDeleteNode() { if (selectedNodeId.value) confirmDeleteNodeWithId(selectedNodeId.value) }

async function confirmDeleteNodeWithId(nodeId: string) {
  const ok = await showConfirm('确定要删除此节点吗？相关的连接也会被删除。')
  if (!ok) return
  removeNodes([nodeId])
  const connectedEdges = edges.value.filter(e => e.source === nodeId || e.target === nodeId)
  if (connectedEdges.length > 0) removeEdges(connectedEdges.map(e => e.id))
  selectedNodeId.value = null
  hasUnsavedChanges.value = true
  showToast('✅ 已删除节点', 'success')
}

async function clearCanvas() {
  const ok = await showConfirm('确定要清空整个画布吗？所有节点和连接都会被删除。')
  if (!ok) return
  nodes.value = []; edges.value = []; selectedNodeId.value = null; hasUnsavedChanges.value = true
  showToast('画布已清空', 'info')
}

async function validateWorkflow() {
  if (nodes.value.length === 0) { validationResult.value = { valid: false, message: '❌ 工作流为空，请至少添加一个节点' }; hideValidationAfterDelay(); return }
  const adj = new Map<string, string[]>(); const inDegree = new Map<string, number>()
  nodes.value.forEach(n => adj.set(n.id, [])); nodes.value.forEach(n => inDegree.set(n.id, 0))
  edges.value.forEach(e => { if (adj.has(e.source)) { adj.get(e.source)?.push(e.target); inDegree.set(e.target, (inDegree.get(e.target) || 0) + 1) } })
  const queue: string[] = []; inDegree.forEach((deg, id) => { if (deg === 0) queue.push(id) })
  let sortedCount = 0
  while (queue.length > 0) { const cur = queue.shift()!; sortedCount++; (adj.get(cur) || []).forEach(neighbor => { const d = (inDegree.get(neighbor) || 1) - 1; inDegree.set(neighbor, d); if (d === 0) queue.push(neighbor) }) }
  if (sortedCount !== nodes.value.length) { validationResult.value = { valid: false, message: '❌ 工作流包含循环依赖！' } }
  else { validationResult.value = { valid: true, message: `✅ 验证通过 (${nodes.value.length}节点, ${edges.value.length}连接)` } }
  hideValidationAfterDelay()
}

function hideValidationAfterDelay() { setTimeout(() => { validationResult.value = null }, 4000) }

function goBack() { window.history.length > 1 ? window.history.back() : (window.location.href = '/workflow-templates') }

function toggleFullscreen() {
  isFullscreen.value = !isFullscreen.value
  isFullscreen.value ? document.documentElement.requestFullscreen?.() : document.fullscreenElement?.exit?.()
  emit('fullscreen', isFullscreen.value)
}

async function saveWorkflow() {
  if (!workflowName.value.trim()) { showToast('请输入工作流名称', 'warning'); return '' }
  if (nodes.value.length === 0) { showToast('工作流至少需要一个节点', 'warning'); return '' }
  saving.value = true
  try {
    const graphDefinition: any = {
      nodes: nodes.value.map(n => ({ id: n.id, type: n.data.nodeType, config: n.data.config || {}, position: n.position })),
      edges: edges.value.map(e => ({ id: e.id, source: e.source, target: e.target, source_handle: e.sourceHandle || null, target_handle: e.targetHandle || null, condition: null, label: e.label || '' })),
    }
    const submitData: any = { name: workflowName.value, description: workflowDescription.value, icon: '⚙️', category: workflowCategory.value, graph_definition: graphDefinition, tags: workflowTagsInput.value.split(',').map(t => t.trim()).filter(Boolean), is_public: false }
    let savedDefinition
    if (currentDefinitionId.value) { savedDefinition = await workflowDefinitionsApi.updateWorkflowDefinition(currentDefinitionId.value, submitData); showToast('✅ 已更新', 'success') }
    else { savedDefinition = await workflowDefinitionsApi.createWorkflowDefinition(submitData); showToast('✅ 已保存', 'success') }
    currentDefinitionId.value = savedDefinition.id; hasUnsavedChanges.value = false; emit('saved', savedDefinition.id); return savedDefinition.id
  } catch (error: any) { showToast(error.response?.data?.detail || '保存失败', 'error'); return '' }
  finally { saving.value = false }
}

async function runWorkflow() {
  let definitionId = currentDefinitionId.value
  if (hasUnsavedChanges.value || !definitionId) { definitionId = await saveWorkflow() }
  if (!definitionId) { showToast('请先保存工作流', 'warning'); return }
  running.value = true
  try {
    const topic = window.prompt('输入创作主题', workflowName.value)?.trim()
    if (!topic) { showToast('请输入主题', 'warning'); return }
    const modelSettings: Record<string, any> = {}
    for (const node of nodes.value) { const c = node.data?.config; if (!c) continue; const t = node.data?.nodeType; if (t === 'copywrite') { if (c.writingStyle) modelSettings.writing_style = c.writingStyle; if (c.contentLength) modelSettings.content_length = c.contentLength; if (c.textModel) modelSettings.text_model = c.textModel } else if (t === 'search' && c.searchLimit) modelSettings.search_limit = c.searchLimit }
    const result = await workflowDefinitionsApi.runWorkflowFromDefinition(definitionId, { topic, model_settings: modelSettings })
    showToast('🚀 已启动！', 'success'); emit('run', result.workflow_id)
  } catch (error: any) { showToast(error.response?.data?.detail || '启动失败', 'error') }
  finally { running.value = false }
}

function exportWorkflow() {
  const data = { name: workflowName.value, version: '1.0.0', exported_at: new Date().toISOString(), graph_definition: { nodes: nodes.value.map(n => ({ id: n.id, type: n.data.nodeType, config: n.data.config || {}, position: n.position })), edges: edges.value.map(e => ({ source: e.source, target: e.target })) } }
  const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })); a.download = `${workflowName.value}.json`; a.click(); URL.revokeObjectURL(a.href); showToast('✅ 已导出', 'success')
}

function handleImport() {
  try {
    const data = JSON.parse(importJsonText.value)
    if (!data.graph_definition?.nodes) throw new Error('无效格式')
    nodes.value = []; edges.value = []
    if (data.name) workflowName.value = data.name
    if (data.graph_definition.nodes) addNodes(data.graph_definition.nodes.map((n: any) => ({ id: n.id, type: 'custom', position: n.position || { x: 100, y: 100 }, data: { label: getNodeDisplayName(n.type), icon: getNodeIcon(n.type), nodeType: n.type, config: n.config || {}, category: getNodeCategory(n.type) } })))
    if (data.graph_definition.edges) addEdges(data.graph_definition.edges.map((e: any, i: number) => ({ id: e.id || `edge_${i}`, source: e.source, target: e.target, type: 'smoothstep', animated: true, ...defaultEdgeOptions })))
    hasUnsavedChanges.value = true; showImportDialog.value = false; importJsonText.value = ''
    nextTick(() => applyAutoLayout())
    showToast('✅ 已导入', 'success')
  } catch (error: any) { showToast('导入失败: ' + error.message, 'error') }
}

function getNodeDisplayName(t: string): string { return ({ search: '🔍 智能搜索', analyze: '📊 选题分析', copywrite: '✍️ 文案生成', image_plan: '🎨 图片规划', image_gen: '🖼️ 图片生成', image_review: '👁️ 图片审核', audit: '✅ 合规审核', final_review: '👁️ 终审确认', publish: '🚀 发布' })[t] || t }
function getNodeIcon(t: string): string { return ({ search: '🔍', analyze: '📊', copywrite: '✍️', image_plan: '🎨', image_gen: '🖼️', image_review: '👁️', audit: '✅', final_review: '👁️', publish: '🚀' })[t] || '📦' }
function getNodeCategory(t: string): string { return ({ search: 'datasource', analyze: 'analysis', copywrite: 'creation', image_plan: 'creation', image_gen: 'creation', image_review: 'review', audit: 'review', final_review: 'review', publish: 'publish' })[t] || 'custom' }
function formatJson(obj: any): string { return JSON.stringify(obj, null, 2) }

defineExpose({ saveWorkflow, loadFromTemplateData, applyAutoLayout })

function loadFromTemplateData(templateData: any) {
  if (!templateData) return
  workflowName.value = templateData.name || '新工作流'; workflowDescription.value = templateData.description || ''; workflowCategory.value = templateData.category || 'custom'
  const gd = templateData.graph_definition; if (!gd) return
  nodes.value = []; edges.value = []
  if (gd.nodes) addNodes(gd.nodes.map((n: any) => ({ id: n.id, type: 'custom', position: n.position || { x: 0, y: 0 }, data: { label: getNodeDisplayName(n.type), icon: getNodeIcon(n.type), nodeType: n.type, config: n.config || {}, category: getNodeCategory(n.type) } })))
  if (gd.edges) addEdges(gd.edges.map((e: any) => ({ id: e.id, source: e.source, target: e.target, sourceHandle: e.source_handle, targetHandle: e.target_handle, type: 'smoothstep', animated: true, ...defaultEdgeOptions })))
  nextTick(() => applyAutoLayout()); hasUnsavedChanges.value = true; showToast(`✅ 已加载: ${templateData.name}`, 'success')
}

onMounted(async () => {
  await loadAvailableNodes()
  if (props.definitionId) { try { await loadDefinition(props.definitionId) } catch (e) { console.error('[WFE] load failed:', e) } }
  nextTick(() => { try { fitView({ padding: 0.3, duration: 300 }) } catch {} })
})
</script>

<style scoped>
/* ===== 根容器 ===== */
.wfe-root {
  display: flex;
  flex-direction: column;
  width: 100%;
  flex: 1;
  min-height: 0;
  background: var(--ma-bg-base);
  font-family: var(--ma-font-sans);
  overflow: hidden;
  position: relative;
}

/* ===== 顶部工具栏 ===== */
.wfe-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  height: 50px;
  padding: 0 16px;
  background: #ffffff;
  border-bottom: 1px solid #e5e7eb;
  flex-shrink: 0;
  z-index: 10;
}

.wfe-toolbar-left, .wfe-toolbar-right {
  display: flex;
  align-items: center;
  gap: 6px;
}

.wfe-back-btn {
  color: #6b7280;
}

.wfe-back-btn:hover {
  color: #ff2442;
  background: #fff5f5;
}

.wfe-title-wrap {
  display: flex;
  align-items: center;
  gap: 8px;
}

.wfe-name-input {
  border: none;
  background: transparent;
  font-size: 15px;
  font-weight: 600;
  color: #111827;
  padding: 5px 8px;
  outline: none;
  border-radius: 6px;
  max-width: 260px;
  transition: all 0.2s;
}

.wfe-name-input:hover { background: #f3f4f6; }
.wfe-name-input:focus { background: #f3f4f6; box-shadow: 0 0 0 2px rgba(255, 36, 66, 0.1); }

.wfe-unsaved-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 10px;
  color: #f59e0b;
  animation: ma-blink-slow 2s infinite;
}

/* 工具按钮 */
.wfe-tool-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  height: 32px;
  padding: 0 10px;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  background: #ffffff;
  color: #374151;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease;
  white-space: nowrap;
}

.wfe-tool-btn:hover:not(:disabled) {
  border-color: #d1d5db;
  background: #f9fafb;
  color: #111827;
}

.wfe-tool-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.wfe-primary-btn {
  background: #ff2442;
  color: white;
  border-color: #ff2442;
}

.wfe-primary-btn:hover:not(:disabled) {
  background: #E51B34;
  border-color: #E51B34;
  box-shadow: 0 2px 8px rgba(255, 36, 66, 0.25);
}

.wfe-danger-btn:hover:not(:disabled) {
  color: #dc2626;
  border-color: #fca5a5;
  background: #fef2f2;
}

.wfe-toolbar-divider {
  width: 1px;
  height: 18px;
  background: #e5e7eb;
  margin: 0 4px;
}

.wfe-toolbar-spacer {
  width: 10px;
}

/* ===== 主体区域 ===== */
.wfe-main {
  display: flex;
  flex: 1;
  min-height: 0;
  overflow: hidden;
  position: relative;
}

/* ===== 左侧边栏 ===== */
.wfe-sidebar {
  width: 240px;
  min-width: 240px;
  background: #fafafa;
  border-right: 1px solid #e5e7eb;
  display: flex;
  flex-direction: column;
  transition: width 0.25s ease, min-width 0.25s ease;
  z-index: 5;
  flex-shrink: 0;
}

.wfe-sidebar.wfe-collapsed {
  width: 48px;
  min-width: 48px;
}

.wfe-sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 14px;
  border-bottom: 1px solid #e5e7eb;
  min-height: 48px;
}

.wfe-sidebar-title {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  color: #111827;
  display: flex;
  align-items: center;
  gap: 6px;
}

.wfe-collapse-btn {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  background: transparent;
  border-radius: 6px;
  color: #9ca3af;
  cursor: pointer;
  transition: all 0.15s;
  flex-shrink: 0;
}

.wfe-collapse-btn:hover {
  background: #f3f4f6;
  color: #374151;
}

.wfe-sidebar-body {
  display: flex;
  flex-direction: column;
  flex: 1;
  overflow: hidden;
}

/* 搜索框 */
.wfe-search-box {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  border-bottom: 1px solid #e5e7eb;
  background: #ffffff;
}

.wfe-search-icon {
  color: #9ca3af;
  flex-shrink: 0;
}

.wfe-search-input {
  flex: 1;
  border: none;
  background: transparent;
  font-size: 12px;
  color: #111827;
  outline: none;
}

.wfe-search-input::placeholder { color: #9ca3af; }

/* 节点列表 */
.wfe-node-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.wfe-node-category { margin-bottom: 4px; }

.wfe-cat-header {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 9px 10px;
  border: none;
  background: transparent;
  border-radius: 6px;
  cursor: pointer;
  text-align: left;
  transition: all 0.15s;
}

.wfe-cat-header:hover { background: #f3f4f6; }

.wfe-cat-icon { font-size: 14px; }

.wfe-cat-name {
  flex: 1;
  font-size: 12px;
  font-weight: 500;
  color: #111827;
}

.wfe-cat-count {
  font-size: 10px;
  color: #6b7280;
  background: #f3f4f6;
  padding: 2px 7px;
  border-radius: 10px;
}

.wfe-cat-arrow {
  color: #9ca3af;
  transition: transform 0.2s;
}

.wfe-cat-open .wfe-cat-arrow { transform: rotate(180deg); }

.wfe-cat-body {
  padding: 4px 0 8px;
}

.wfe-palette-node {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 11px;
  margin: 2px 0;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  cursor: grab;
  background: #ffffff;
  transition: all 0.15s ease;
}

.wfe-palette-node:hover {
  border-color: #ff2442;
  box-shadow: 0 2px 8px rgba(255, 36, 66, 0.1);
  transform: translateX(3px);
}

.wfe-palette-node:active { cursor: grabbing; transform: scale(0.98); }

.wfe-node-icon {
  font-size: 20px;
  width: 34px;
  height: 34px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #f3f4f6;
  border-radius: 8px;
  flex-shrink: 0;
}

.wfe-node-info { flex: 1; min-width: 0; }

.wfe-node-name {
  display: block;
  font-size: 12px;
  font-weight: 500;
  color: #111827;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.wfe-node-type {
  display: block;
  font-size: 10px;
  color: #9ca3af;
  font-family: 'Courier New', monospace;
}

/* 收起状态 */
.wfe-collapsed-hint {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #d1d5db;
}

/* 分割线 */
.wfe-resize-handle {
  width: 0;
  cursor: col-resize;
  flex-shrink: 0;
  overflow: visible;
  position: relative;
}
.wfe-resize-handle::before {
  content: '';
  position: absolute;
  top: 0;
  bottom: 0;
  left: -4px;
  right: -4px;
  z-index: 1;
}
.wfe-resize-handle:hover { background: rgba(0, 0, 0, 0.04); }

/* ===== 画布区域 ===== */
.wfe-canvas-area {
  flex: 1;
  min-width: 0;
  position: relative;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.wfe-canvas {
  width: 100%;
  flex: 1;
  min-height: 0;
}

.wfe-vueflow :deep(.vue-flow) {
  background-color: #f9fafb !important;
  background-image:
    linear-gradient(to right, #e5e7eb 1px, transparent 1px),
    linear-gradient(to bottom, #e5e7eb 1px, transparent 1px) !important;
  background-size: 24px 24px !important;
}

/* 空状态 */
.wfe-empty-state {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  pointer-events: none;
  z-index: 5;
}

.wfe-empty-card {
  background: #ffffff;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  padding: 40px 56px;
  text-align: center;
  pointer-events: auto;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.08);
}

.wfe-empty-icon {
  color: #d1d5db;
  margin-bottom: 16px;
}

.wfe-empty-card h3 {
  margin: 0 0 8px;
  font-size: 18px;
  font-weight: 600;
  color: #111827;
}

.wfe-empty-card p {
  margin: 0 0 28px;
  font-size: 14px;
  color: #6b7280;
}

.wfe-quick-add {
  display: flex;
  gap: 8px;
  justify-content: center;
  flex-wrap: wrap;
}

.wfe-quick-btn {
  padding: 9px 16px;
  border: 1px solid #e5e7eb;
  border-radius: 20px;
  background: #ffffff;
  font-size: 12px;
  color: #374151;
  cursor: pointer;
  transition: all 0.15s;
}

.wfe-quick-btn:hover {
  border-color: #ff2442;
  color: #ff2442;
  background: #fff5f5;
}

/* ===== 右侧配置面板 ===== */
.wfe-config-panel {
  width: 280px;
  min-width: 280px;
  background: #ffffff;
  border-left: 1px solid #e5e7eb;
  display: flex;
  flex-direction: column;
  transform: translateX(100%);
  opacity: 0;
  pointer-events: none;
  transition: transform 0.25s ease, opacity 0.25s ease;
  z-index: 5;
  flex-shrink: 0;
}

.wfe-config-panel.wfe-panel-visible {
  transform: translateX(0);
  opacity: 1;
  pointer-events: auto;
}

.wfe-panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
  border-bottom: 1px solid #e5e7eb;
  min-height: 52px;
}

.wfe-panel-title {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  color: #111827;
  display: flex;
  align-items: center;
  gap: 8px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.wfe-panel-icon { font-size: 15px; }

.wfe-panel-close {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  background: transparent;
  border-radius: 6px;
  color: #9ca3af;
  cursor: pointer;
  flex-shrink: 0;
}

.wfe-panel-close:hover { background: #f3f4f6; color: #ef4444; }

.wfe-panel-body {
  flex: 1;
  overflow-y: auto;
  padding: 14px 16px;
}

.wfe-panel-form { margin-bottom: 14px; }

.wfe-panel-simple { padding-top: 4px; }

.wfe-info-row { margin-bottom: 14px; }

.wfe-info-row label {
  display: block;
  font-size: 11px;
  color: #6b7280;
  font-weight: 500;
  margin-bottom: 5px;
}

.wfe-type-badge {
  font-size: 10px;
  padding: 3px 10px;
  background: #fff5f5;
  color: #ff2442;
  border-radius: 20px;
  font-family: 'Courier New', monospace;
}

.wfe-config-preview {
  background: #f9fafb;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 10px;
  font-size: 11px;
  line-height: 1.6;
  color: #374151;
  max-height: 180px;
  overflow: auto;
  margin: 0;
  font-family: 'Courier New', monospace;
}

.wfe-panel-footer {
  margin-top: auto;
  padding-top: 12px;
  border-top: 1px solid #e5e7eb;
}

.wfe-delete-btn {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 9px;
  border: 1px solid rgba(239, 68, 68, 0.2);
  border-radius: 8px;
  background: rgba(239, 68, 68, 0.04);
  color: #dc2626;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
}

.wfe-delete-btn:hover { background: rgba(239, 68, 68, 0.08); border-color: rgba(239, 68, 68, 0.3); }

/* ===== Modal ===== */
.wfe-modal-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  backdrop-filter: blur(4px);
}

.wfe-modal {
  background: #ffffff;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  width: 90%;
  max-width: 540px;
  max-height: 85vh;
  overflow: hidden;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.2);
}

.wfe-modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px 22px;
  border-bottom: 1px solid #e5e7eb;
}

.wfe-modal-header h3 { margin: 0; font-size: 16px; font-weight: 600; color: #111827; }

.wfe-modal-close {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  background: transparent;
  border-radius: 6px;
  color: #9ca3af;
  cursor: pointer;
}

.wfe-modal-close:hover { background: #f3f4f6; color: #374151; }

.wfe-modal-body { padding: 22px; }

.wfe-modal-desc { margin: 0 0 14px; color: #6b7280; font-size: 13px; }

.wfe-import-textarea {
  width: 100%;
  padding: 12px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  font-family: 'Courier New', monospace;
  font-size: 13px;
  resize: vertical;
  outline: none;
  background: #f9fafb;
  color: #111827;
}

.wfe-import-textarea:focus { border-color: #ff2442; box-shadow: 0 0 0 3px rgba(255, 36, 66, 0.1); }

.wfe-modal-actions {
  display: flex;
  gap: 12px;
  justify-content: flex-end;
  margin-top: 22px;
}

.wfe-btn {
  padding: 10px 20px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  border: none;
  transition: all 0.15s;
}

.wfe-btn-primary { background: #ff2442; color: white; }
.wfe-btn-primary:hover { background: #E51B34; }

.wfe-btn-secondary { background: #f3f4f6; color: #374151; }
.wfe-btn-secondary:hover { background: #e5e7eb; }

/* ===== Toast ===== */
.wfe-toast {
  position: fixed;
  top: 76px;
  left: 50%;
  transform: translateX(-50%);
  padding: 12px 24px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 500;
  z-index: 2000;
  display: flex;
  align-items: center;
  gap: 8px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
}

.wfe-toast-true { background: #f0fdf4; color: #166534; border: 1px solid #bbf7d0; }
.wfe-toast-false { background: #fef2f2; color: #991b1b; border: 1px solid #fecaca; }

/* ===== Transitions ===== */
.wfe-collapse-enter-active, .wfe-collapse-leave-active { transition: all 0.2s ease; overflow: hidden; }
.wfe-collapse-enter-from, .wfe-collapse-leave-to { opacity: 0; max-height: 0; }

.wfe-fade-enter-active, .wfe-fade-leave-active { transition: opacity 0.25s ease; }
.wfe-fade-enter-from, .wfe-fade-leave-to { opacity: 0; }

.wfe-slide-down-enter-active { transition: all 0.3s ease; }
.wfe-slide-down-leave-active { transition: all 0.25s ease; }
.wfe-slide-down-enter-from { opacity: 0; transform: translateX(-50%) translateY(-16px); }
.wfe-slide-down-leave-to { opacity: 0; transform: translateX(-50%) translateY(-16px); }
</style>