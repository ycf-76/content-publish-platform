<template>
  <div class="workflow-editor">
    <!-- ===== 画布占满全屏 ===== -->
    <div class="editor-canvas" ref="canvasContainer">
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
        class="vue-flow-wrapper"
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

      <!-- 空状态提示 -->
      <div class="canvas-empty" v-if="nodes.length === 0">
        <div class="empty-content">
          <i data-lucide="layout-template" class="empty-icon"></i>
          <h3>从左侧拖拽节点到这里</h3>
          <p>构建你的自定义工作流</p>
          <div class="quick-add-buttons">
            <button 
              v-for="quickNode in quickAddNodes" 
              :key="quickNode.node_type"
              class="quick-add-btn"
              @click="addQuickNode(quickNode)"
            >
              {{ quickNode.icon }} {{ quickNode.display_name }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- ===== 左侧节点面板（浮动在画布上方） ===== -->
    <div class="floating-sidebar" :class="{ collapsed: leftCollapsed }">
      <div class="sidebar-header">
        <h3 v-if="!leftCollapsed">
          <i data-lucide="layers"></i>
          节点库
        </h3>
        <button 
          class="collapse-btn"
          @click="leftCollapsed = !leftCollapsed"
          :title="leftCollapsed ? '展开' : '收起'"
        >
          <i :data-lucide="leftCollapsed ? 'chevron-right' : 'chevron-left'"></i>
        </button>
      </div>

      <div class="node-search" v-if="!leftCollapsed">
        <i data-lucide="search" class="search-icon"></i>
        <input 
          type="text" 
          v-model="nodeSearchQuery"
          placeholder="搜索节点..."
          class="search-input"
        />
      </div>

      <div class="node-categories" v-if="!leftCollapsed">
        <div 
          v-for="category in filteredNodeCategories" 
          :key="category.key"
          class="category-section"
        >
          <div 
            class="category-title" 
            @click="toggleCategory(category.key)"
          >
            <span class="category-icon">{{ category.icon }}</span>
            <span class="category-name">{{ category.label }}</span>
            <span class="category-count">{{ category.nodes.length }}</span>
            <span class="category-toggle">{{ activeCategories.includes(category.key) ? '▼' : '▶' }}</span>
          </div>

          <div v-show="activeCategories.includes(category.key)" class="category-nodes">
            <div 
              v-for="node in category.nodes" 
              :key="node.node_type"
              class="palette-node"
              draggable="true"
              @dragstart="onNodeDragStart($event, node)"
              :title="node.description"
            >
              <span class="node-icon-lg">{{ node.icon }}</span>
              <div class="node-info">
                <span class="node-name">{{ node.display_name }}</span>
                <span class="node-type">{{ node.node_type }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="collapsed-hint" v-else>
        <i data-lucide="git-branch"></i>
      </div>
    </div>

    <!-- ===== 顶部工具栏（浮动在画布上方） ===== -->
    <div class="floating-toolbar">
      <div class="toolbar-left">
        <button class="toolbar-btn back-btn" @click="goBack" title="返回">
          <i data-lucide="arrow-left"></i>
          返回
        </button>
        <input
          v-model="workflowName"
          class="workflow-name-input"
          placeholder="未命名工作流"
          aria-label="工作流名称"
        />
        <span class="auto-save-hint" v-if="hasUnsavedChanges">
          <i data-lucide="circle-dot"></i>
          未保存
        </span>
      </div>

      <div class="toolbar-right">
        <button class="toolbar-btn" @click="saveWorkflow" :disabled="saving">
          <i data-lucide="save"></i>
          {{ saving ? '保存中...' : '保存' }}
        </button>
        
        <button 
          class="toolbar-btn primary" 
          @click="runWorkflow" 
          :disabled="!canRun || running"
        >
          <i data-lucide="play"></i>
          {{ running ? '启动中...' : '运行' }}
        </button>

        <button class="toolbar-btn" @click="applyAutoLayout" title="自动排列" :disabled="nodes.length === 0">
          <i data-lucide="layout-grid"></i>
          排列
        </button>
        
        <button class="toolbar-btn" @click="validateWorkflow" title="验证">
          <i data-lucide="check-circle"></i>
          验证
        </button>
        
        <button class="toolbar-btn" @click="exportWorkflow" title="导出">
          <i data-lucide="download"></i>
          导出
        </button>
        
        <button class="toolbar-btn" @click="showImportDialog = true" title="导入">
          <i data-lucide="upload"></i>
          导入
        </button>
        
        <button 
          class="toolbar-btn" 
          @click="clearCanvas" 
          title="清空"
          :disabled="nodes.length === 0"
        >
          <i data-lucide="trash-2"></i>
          清空
        </button>

        <button 
          class="toolbar-btn" 
          @click="toggleFullscreen" 
          :title="isFullscreen ? '退出全屏' : '全屏'"
        >
          <i data-lucide="maximize-2"></i>
          {{ isFullscreen ? '退出' : '全屏' }}
        </button>
      </div>
    </div>

    <!-- ===== 右侧配置面板（浮动在画布上方） ===== -->
    <div class="floating-config-panel" :class="{ visible: showRightPanel && selectedNodeData }">
      <div class="panel-header">
        <h3>
          <span class="selected-node-icon-sm">{{ selectedNodeData?.data?.icon || '📦' }}</span>
          {{ selectedNodeData?.data?.label || '节点配置' }}
        </h3>
        <button 
          class="panel-close-btn"
          @click="showRightPanel = false"
          title="关闭"
        >
          <i data-lucide="x"></i>
        </button>
      </div>

      <div class="config-content">
        <div class="config-form" v-if="selectedNodeSchema">
          <DynamicForm
            :schema="selectedNodeSchema.config_schema"
            v-model="selectedNodeData.data.config"
            @change="onNodeConfigChange"
          />
        </div>

        <div v-else class="simple-config">
          <div class="info-group">
            <label>节点类型</label>
            <span class="node-type-badge">{{ selectedNodeData?.data?.nodeType || 'custom' }}</span>
          </div>
          <div class="info-group" v-if="selectedNodeData?.data?.config">
            <label>当前配置</label>
            <pre class="config-preview">{{ formatJson(selectedNodeData.data.config) }}</pre>
          </div>
        </div>

        <div class="config-actions">
          <button class="action-btn danger" @click="confirmDeleteNode">
            <i data-lucide="trash-2"></i>
            删除此节点
          </button>
        </div>
      </div>
    </div>

    <!-- 导入对话框 -->
    <div class="modal-overlay" v-if="showImportDialog" @click.self="showImportDialog = false">
      <div class="modal">
        <div class="modal-header">
          <h3>导入工作流定义</h3>
          <button class="close-btn" @click="showImportDialog = false">
            <i data-lucide="x"></i>
          </button>
        </div>
        <div class="modal-body">
          <p>粘贴或上传工作流 JSON 定义：</p>
          <textarea 
            v-model="importJsonText"
            placeholder='{"name": "...", "graph_definition": {"nodes": [...], "edges": [...]}}'
            class="import-textarea"
            rows="10"
          ></textarea>
          <div class="modal-actions">
            <button class="btn primary" @click="handleImport">确认导入</button>
            <button class="btn secondary" @click="showImportDialog = false">取消</button>
          </div>
        </div>
      </div>
    </div>

    <!-- 验证结果提示 -->
    <div class="validation-toast" v-if="validationResult" :class="validationResult.valid ? 'success' : 'error'">
      <i :data-lucide="validationResult.valid ? 'check-circle' : 'alert-circle'"></i>
      {{ validationResult.message }}
    </div>
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
import { createIcons, icons } from 'lucide'
import workflowDefinitionsApi from '@/api/workflowDefinitions'
import CustomWorkflowNode from './CustomWorkflowNode.vue'
import DynamicForm from '@/components/common/DynamicForm.vue'

// ===== 简易Toast工具（替代Element Plus）=====
function showToast(message: string, type: 'success' | 'error' | 'warning' | 'info' = 'info') {
  const toast = document.createElement('div')
  toast.textContent = message
  
  Object.assign(toast.style, {
    position: 'fixed',
    top: '80px',
    left: '50%',
    transform: 'translateX(-50%)',
    padding: '12px 24px',
    borderRadius: '8px',
    fontSize: '14px',
    fontWeight: '500',
    zIndex: '9999',
    boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
  })
  
  const colors = {
    success: { bg: '#f0fdf4', color: '#166534', border: '#bbf7d0' },
    error: { bg: '#fef2f2', color: '#991b1b', border: '#fecaca' },
    warning: { bg: '#fffbeb', color: '#92400e', border: '#fde68a' },
    info: { bg: '#eff6ff', color: '#1e40af', border: '#bfdbfe' },
  }
  
  const theme = colors[type]
  toast.style.background = theme.bg
  toast.style.color = theme.color
  toast.style.border = `1px solid ${theme.border}`
  
  document.body.appendChild(toast)
  
  setTimeout(() => {
    toast.style.opacity = '0'
    toast.style.transition = 'opacity 0.3s ease'
    setTimeout(() => document.body.removeChild(toast), 300)
  }, 3000)
}

async function showConfirm(message: string): Promise<boolean> {
  return new Promise((resolve) => {
    resolve(window.confirm(message))
  })
}

// Props & Emits
const props = defineProps<{
  definitionId?: string  // 编辑已有定义时传入
}>()

const emit = defineEmits<{
  (e: 'saved', definitionId: string): void
  (e: 'run', workflowId: string): void
  (e: 'fullscreen', isFullscreen: boolean): void
}>()

const currentDefinitionId = ref<string | undefined>(props.definitionId)

// VueFlow 实例 - 使用明确 id 确保与 <VueFlow> 组件连接
const FLOW_ID = 'workflow-editor-flow'
const vueFlowInstance = useVueFlow({ id: FLOW_ID })
const { addEdges, addNodes, removeNodes, removeEdges, fitView, screenToFlowCoordinate } = vueFlowInstance

// ===== 状态管理 =====
const nodes = ref<any[]>([])
const edges = ref<any[]>([])

// ===== Fallback 节点数据（API不可用时使用）=====
const FALLBACK_NODES: any[] = [
  { node_type: 'search', display_name: '选题搜索', description: '从内容池搜索热门选题', category: 'datasource', icon: '🔍', config_schema: { type: 'object', properties: { keyword: { type: 'string', title: '搜索关键词' }, max_results: { type: 'integer', title: '最大结果数', default: 5 } } }, tags: [] },
  { node_type: 'analyze', display_name: '选题分析', description: '分析选题热度和趋势', category: 'analysis', icon: '📊', config_schema: { type: 'object', properties: { depth: { type: 'string', title: '分析深度', enum: ['quick', 'normal', 'deep'], default: 'normal' } } }, tags: [] },
  { node_type: 'copywrite', display_name: 'AI文案', description: 'AI生成小红书文案', category: 'creation', icon: '✍️', config_schema: { type: 'object', properties: { model: { type: 'string', title: '模型', enum: ['deepseek-chat', 'gpt-4o-mini'], default: 'deepseek-chat' }, style: { type: 'string', title: '风格', enum: ['种草', '教程', '日常', '测评'], default: '种草' }, content_length: { type: 'integer', title: '文案长度（字）', description: '控制生成文案的字数，100-500字', minimum: 100, maximum: 500, default: 300 }, require_review: { type: 'boolean', title: '需要人工审核', default: true, description: '生成后暂停等待人工确认再继续' } } }, tags: [] },
  { node_type: 'image_plan', display_name: '图片规划', description: '规划配图方案', category: 'creation', icon: '🖼️', config_schema: { type: 'object', properties: { count: { type: 'integer', title: '图片数量', default: 3 } } }, tags: [] },
  { node_type: 'image_gen', display_name: 'AI生图', description: 'AI生成配图', category: 'creation', icon: '🎨', config_schema: { type: 'object', properties: { style: { type: 'string', title: '风格', enum: ['realistic', 'illustration', 'flat-design'], default: 'realistic' } } }, tags: [] },
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
const leftCollapsed = ref(false)
const rightCollapsed = ref(false)
const showRightPanel = ref(false)
const nodeSearchQuery = ref('')
const activeCategories = ref<string[]>(['datasource', 'analysis', 'creation', 'review', 'publish'])
const activeSchemaTab = ref<'input' | 'output'>('input')
const saving = ref(false)
const running = ref(false)
const isFullscreen = ref(false)
const showImportDialog = ref(false)
const importJsonText = ref('')
const hasUnsavedChanges = ref(false)

// 选中的节点
const selectedNodeId = ref<string | null>(null)
const selectedNode = computed<any>(() => nodes.value.find((n: any) => n.id === selectedNodeId.value))
const selectedNodeData = computed<any>(() => selectedNode.value || null)
const selectedNodeSchema = computed<any>(() => {
  if (!selectedNode.value) return null
  const nodeType = selectedNode.value.data?.nodeType
  return availableNodes.value.find((n: any) => n.node_type === nodeType) || null
})

// 工作流基本信息
const workflowName = ref('未命名工作流')
const workflowDescription = ref('')
const workflowCategory = ref('custom')
const workflowTagsInput = ref('')

// 可用节点数据
const availableNodes = ref<any[]>([])
const allNodeCategories = ref<any[]>([])

// 拖拽连接状态
const isConnecting = ref(false)
const connectionPath = ref('')

// 验证结果
const validationResult = ref<any>(null)

// ===== 计算属性 =====

// 过滤后的分类和节点
const filteredNodeCategories = computed(() => {
  const query = nodeSearchQuery.value.toLowerCase().trim()
  
  let categories = allNodeCategories.value.map(cat => ({
    ...cat,
    nodes: cat.nodes.filter((node: any) => {
      if (!query) return true
      return (
        node.display_name.toLowerCase().includes(query) ||
        node.node_type.toLowerCase().includes(query) ||
        node.description?.toLowerCase().includes(query) ||
        node.tags?.some((tag: string) => tag.toLowerCase().includes(query))
      )
    }),
  }))
  
  // 过滤掉空分类
  return categories.filter(cat => cat.nodes.length > 0)
})

// 快速添加的常用节点
const quickAddNodes = computed(() => {
  const popularTypes = ['search', 'copywrite', 'publish']
  return availableNodes.value.filter(n => popularTypes.includes(n.node_type)).slice(0, 3)
})

// 是否可以运行
const canRun = computed(() => {
  return nodes.value.length >= 1 && workflowName.value.trim() !== ''
})

// 默认边样式
const defaultEdgeOptions: any = {
  type: 'smoothstep',
  animated: true,
  style: { stroke: '#FF2442', strokeWidth: 2 },
  markerEnd: {
    type: 'arrowclosed' as any,
    color: '#FF2442',
  },
}

// ===== 自动格子布局算法 =====
// 按拓扑层级排列节点：入度为0的放第0列，逐层向右展开
// 同层节点垂直均匀分布，形成整齐的格子图

function computeAutoLayout(
  nodeList: any[],
  edgeList: any[],
  options?: { nodeWidth?: number; nodeHeight?: number; gapX?: number; gapY?: number; paddingX?: number; paddingY?: number }
): Map<string, { x: number; y: number }> {
  const {
    nodeWidth = 220,
    nodeHeight = 100,
    gapX = 120,
    gapY = 50,
    paddingX = 80,
    paddingY = 80,
  } = options || {}

  if (nodeList.length === 0) return new Map()

  const GRID = 20

  const snapToGrid = (v: number) => Math.round(v / GRID) * GRID

  const nodeIds = new Set(nodeList.map((n: any) => n.id))

  // 构建邻接表和入度表
  const adj = new Map<string, string[]>()
  const inDegree = new Map<string, number>()
  for (const n of nodeList) {
    adj.set(n.id, [])
    inDegree.set(n.id, 0)
  }
  for (const e of edgeList) {
    const src = e.source
    const tgt = e.target
    if (nodeIds.has(src) && nodeIds.has(tgt)) {
      adj.get(src)!.push(tgt)
      inDegree.set(tgt, (inDegree.get(tgt) || 0) + 1)
    }
  }

  // BFS 拓扑分层
  const layers = new Map<string, number>()
  const queue: string[] = []
  for (const [nid, deg] of inDegree) {
    if (deg === 0) {
      queue.push(nid)
      layers.set(nid, 0)
    }
  }

  let qi = 0
  while (qi < queue.length) {
    const nid = queue[qi++]
    const currentLayer = layers.get(nid)!
    for (const neighbor of adj.get(nid) || []) {
      const newLayer = currentLayer + 1
      const existingLayer = layers.get(neighbor)
      if (existingLayer === undefined || newLayer > existingLayer) {
        layers.set(neighbor, newLayer)
      }
      const newDeg = (inDegree.get(neighbor) || 1) - 1
      inDegree.set(neighbor, newDeg)
      if (newDeg === 0) {
        queue.push(neighbor)
      }
    }
  }

  // 处理未分层的节点（环或孤立节点）
  let maxLayer = 0
  for (const l of layers.values()) {
    if (l > maxLayer) maxLayer = l
  }
  for (const n of nodeList) {
    if (!layers.has(n.id)) {
      maxLayer++
      layers.set(n.id, maxLayer)
    }
  }

  // 按层分组
  const layerGroups = new Map<number, string[]>()
  for (const [nid, layer] of layers) {
    if (!layerGroups.has(layer)) layerGroups.set(layer, [])
    layerGroups.get(layer)!.push(nid)
  }

  // 计算每层的最大高度，用于垂直居中
  const maxNodesInLayer = Math.max(...Array.from(layerGroups.values()).map(g => g.length), 1)
  const totalHeight = maxNodesInLayer * nodeHeight + (maxNodesInLayer - 1) * gapY

  // 计算每个节点的位置（对齐到20px格子）
  const positions = new Map<string, { x: number; y: number }>()
  
  for (const [layer, nodeIdsInLayer] of layerGroups) {
    const layerHeight = nodeIdsInLayer.length * nodeHeight + (nodeIdsInLayer.length - 1) * gapY
    const startY = (totalHeight - layerHeight) / 2 + paddingY
    
    // 确保起始位置为正数
    const safeStartY = Math.max(paddingY, startY)

    nodeIdsInLayer.forEach((nid, idx) => {
      const x = snapToGrid(paddingX + layer * (nodeWidth + gapX))
      const y = snapToGrid(safeStartY + idx * (nodeHeight + gapY))
      
      positions.set(nid, { 
        x: Math.max(GRID, x),  // 确保x坐标为正
        y: Math.max(GRID, y),  // 确保y坐标为正
      })
    })
  }

  return positions
}

// 对当前画布上的节点执行自动布局
function applyAutoLayout() {
  const positions = computeAutoLayout(nodes.value, edges.value)
  nodes.value = nodes.value.map((n: any) => {
    const pos = positions.get(n.id)
    if (pos) {
      return { ...n, position: pos }
    }
    return n
  })
  hasUnsavedChanges.value = true
  
  // 延迟适配视图，确保DOM更新完成
  setTimeout(() => {
    fitView({ 
      padding: 0.3,
      duration: 400 
    })
  }, 100)
  
  showToast('✅ 已自动排列节点', 'success')
}

// MiniMap 节点颜色
function miniMapNodeColor(node: any) {
  const categoryColors: Record<string, string> = {
    datasource: '#10b981',
    creation: '#f59e0b',
    review: '#ef4444',
    publish: '#8b5cf6',
    utility: '#6b7280',
  }
  const nodeType = node.data?.category || 'custom'
  return categoryColors[nodeType] || '#94a3b8'
}

// ===== 方法 =====

// 加载可用节点列表
function toggleCategory(key: string) {
  const idx = activeCategories.value.indexOf(key)
  if (idx >= 0) {
    activeCategories.value.splice(idx, 1)
  } else {
    activeCategories.value.push(key)
  }
}

async function loadAvailableNodes() {
  try {
    const result = await workflowDefinitionsApi.getAvailableNodes({ include_details: true })
    if (result && result.nodes && result.nodes.length > 0) {
      availableNodes.value = result.nodes
      const categoryMeta: Record<string, { icon: string; color: string }> = {
        datasource: { icon: '📡', color: '#10b981' },
        analysis: { icon: '📊', color: '#6366f1' },
        creation: { icon: '✨', color: '#f59e0b' },
        review: { icon: '🔍', color: '#ef4444' },
        publish: { icon: '🚀', color: '#8b5cf6' },
        utility: { icon: '🔧', color: '#6b7280' },
        custom: { icon: '📦', color: '#94a3b8' },
      }
      const grouped = new Map<string, any[]>()
      result.nodes.forEach((node: any) => {
        const cat = node.category || 'custom'
        if (!grouped.has(cat)) grouped.set(cat, [])
        grouped.get(cat)!.push(node)
      })
      allNodeCategories.value = Array.from(grouped.entries()).map(([cat, catNodes]) => {
        const meta = categoryMeta[cat] || categoryMeta.custom
        const backendCat = result.categories?.find((c: any) => c.category === cat)
        return {
          key: cat,
          label: backendCat?.label || cat,
          icon: meta.icon,
          color: meta.color,
          nodes: catNodes,
        }
      })
      console.log('[WorkflowEditor] API nodes loaded:', result.nodes.length, 'categories:', allNodeCategories.value.length)
      return
    }
    console.warn('[WorkflowEditor] API returned empty nodes, using fallback')
  } catch (error: any) {
    console.warn('[WorkflowEditor] API failed, using fallback nodes:', error?.message || error)
  }
  
  availableNodes.value = FALLBACK_NODES
  allNodeCategories.value = FALLBACK_CATEGORIES
  console.log('[WorkflowEditor] Fallback nodes loaded:', FALLBACK_NODES.length)
}

// 从后端加载已有的工作流定义
async function loadDefinition(definitionId: string) {
  try {
    saving.value = true
    const definition = await workflowDefinitionsApi.getWorkflowDefinition(definitionId)

    currentDefinitionId.value = definition.id
    
    // 填充基本信息
    workflowName.value = definition.name
    workflowDescription.value = definition.description || ''
    workflowCategory.value = definition.category
    workflowTagsInput.value = (definition.tags || []).join(', ')
    
    // 填充图定义
    const graphDef = definition.graph_definition
    
    // 转换节点格式（先用临时位置）
    if (graphDef.nodes) {
      nodes.value = graphDef.nodes.map((n: any) => ({
        id: n.id,
        type: 'custom',
        position: n.position || { x: 0, y: 0 },
        data: {
          label: getNodeDisplayName(n.type),
          icon: getNodeIcon(n.type),
          nodeType: n.type,
          config: n.config || {},
          category: getNodeCategory(n.type),
        },
      })) as any
    }
    
    // 转换边格式
    if (graphDef.edges) {
      edges.value = graphDef.edges.map((e: any) => ({
        id: e.id,
        source: e.source,
        target: e.target,
        sourceHandle: e.source_handle,
        targetHandle: e.target_handle,
        type: 'smoothstep',
        animated: true,
        label: e.label,
        ...defaultEdgeOptions,
      })) as any
    }
    
    // 自动应用格子布局
    nextTick(() => {
      const positions = computeAutoLayout(nodes.value, edges.value)
      nodes.value = nodes.value.map((n: any) => {
        const pos = positions.get(n.id)
        if (pos) {
          return { ...n, position: pos }
        }
        return n
      })
      
      // 延迟适配视图
      setTimeout(() => {
        fitView({ 
          padding: 0.3,
          duration: 400 
        })
      }, 150)
    })
    
    showToast('✅ 已加载工作流: ' + definition.name, 'success')
    
  } catch (error: any) {
    console.error('[WorkflowEditor] Failed to load definition:', error)
    showToast(error.response?.data?.detail || '加载失败', 'error')
  } finally {
    saving.value = false
  }
}

// 拖拽状态
const dragNodeType = ref<string | null>(null)

// 节点拖拽开始（从左侧面板）
function onNodeDragStart(event: DragEvent, nodeData: any) {
  if (!event.dataTransfer) return
  
  const payload = JSON.stringify(nodeData)
  event.dataTransfer.setData('application/vueflow', payload)
  event.dataTransfer.effectAllowed = 'move'
  dragNodeType.value = nodeData.node_type
  console.log('[WorkflowEditor] Drag start:', nodeData.node_type, nodeData.display_name)
}

// 画布拖拽事件
function onCanvasDragOver(event: DragEvent) {
  event.preventDefault()
  if (event.dataTransfer) {
    event.dataTransfer.dropEffect = 'move'
  }
}

// 放置到画布 - 创建新节点
function onCanvasDrop(event: DragEvent) {
  event.preventDefault()
  
  const nodeDataStr = event.dataTransfer?.getData('application/vueflow')
  if (!nodeDataStr) {
    console.warn('[WorkflowEditor] Drop event but no node data found')
    return
  }
  
  try {
    const nodeData = JSON.parse(nodeDataStr)
    console.log('[WorkflowEditor] Drop node:', nodeData.node_type, 'at', event.clientX, event.clientY)
    
    const position = screenToFlowCoordinate({
      x: event.clientX,
      y: event.clientY,
    })
    
    position.x = Math.round(position.x / 20) * 20
    position.y = Math.round(position.y / 20) * 20
    
    const newNode = {
      id: `node_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
      type: 'custom',
      position: { x: Math.max(20, position.x), y: Math.max(20, position.y) },
      data: {
        label: nodeData.display_name || nodeData.node_type,
        icon: nodeData.icon || '📦',
        nodeType: nodeData.node_type,
        config: {},
        category: nodeData.category || 'custom',
      },
    }
    
    addNodes([newNode])
    hasUnsavedChanges.value = true
    dragNodeType.value = null
    showToast(`✅ 已添加节点: ${nodeData.display_name}`, 'success')

  } catch (error) {
    console.error('[WorkflowEditor] Drop error:', error)
    showToast('添加节点失败', 'error')
  }
}

// 快速添加节点
function addQuickNode(nodeData: any) {
  // 放在最后一个节点右侧
  let lastX = 60
  let lastY = 60
  if (nodes.value.length > 0) {
    const rightmost = nodes.value.reduce((max: any, n: any) => 
      (n.position?.x || 0) > (max.position?.x || 0) ? n : max, nodes.value[0])
    lastX = (rightmost.position?.x || 0) + 320
    lastY = rightmost.position?.y || 60
  }
  
  const newNode: any = {
    id: `node_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
    type: 'custom',
    position: { x: lastX, y: lastY },
    data: {
      label: nodeData.display_name,
      icon: nodeData.icon,
      nodeType: nodeData.node_type,
      config: {},
      category: nodeData.category,
    },
  }
  
  addNodes([newNode])
  hasUnsavedChanges.value = true
}

// 点击节点
function onNodeClick({ node }: { node: any }) {
  selectedNodeId.value = node.id
  showRightPanel.value = true
}

// 点击连线
function onEdgeClick({ edge }: { edge: any }) {
  selectedNodeId.value = null
}

// 点击空白处
function onPaneClick() {
  selectedNodeId.value = null
}

// 连接节点
function onConnect(params: any) {
  const newEdge: any = {
    id: `edge_${Date.now()}`,
    source: params.source!,
    target: params.target!,
    sourceHandle: params.sourceHandle,
    targetHandle: params.targetHandle,
    type: 'smoothstep',
    animated: true,
    ...defaultEdgeOptions,
  }
  
  addEdges([newEdge])
  hasUnsavedChanges.value = true
}

// 节点变化处理
function onNodesChange(changes: any[]) {
  for (const change of changes) {
    if (change.type === 'remove') {
      hasUnsavedChanges.value = true
    }
  }
}

function onEdgesChange(changes: any[]) {
  for (const change of changes) {
    if (change.type === 'remove') {
      hasUnsavedChanges.value = true
    }
  }
}

// 节点拖拽停止
function onNodeDragStop({ node }: { node: any }) {
  hasUnsavedChanges.value = true
}

// 打开配置面板
function openConfigPanel(nodeId: string) {
  selectedNodeId.value = nodeId
  showRightPanel.value = true
}

// 节点配置变更
function onNodeConfigChange(newConfig: any) {
  if (selectedNode.value) {
    selectedNode.value.data.config = newConfig
    hasUnsavedChanges.value = true
  }
}

// 删除节点
function deleteNode(nodeId: string) {
  confirmDeleteNodeWithId(nodeId)
}

// 确认删除节点
function confirmDeleteNode() {
  if (!selectedNodeId.value) return
  confirmDeleteNodeWithId(selectedNodeId.value)
}

async function confirmDeleteNodeWithId(nodeId: string) {
  const ok = await showConfirm('确定要删除此节点吗？相关的连接也会被删除。')
  if (!ok) return
  
  removeNodes([nodeId])
  
  const connectedEdges = edges.value.filter(
    e => e.source === nodeId || e.target === nodeId
  )
  if (connectedEdges.length > 0) {
    removeEdges(connectedEdges.map(e => e.id))
  }
  
  selectedNodeId.value = null
  hasUnsavedChanges.value = true
  showToast('✅ 已删除节点', 'success')
}

// 清空画布
async function clearCanvas() {
  const ok = await showConfirm('确定要清空整个画布吗？所有节点和连接都会被删除。')
  if (!ok) return
  
  nodes.value = []
  edges.value = []
  selectedNodeId.value = null
  hasUnsavedChanges.value = true
  showToast('画布已清空', 'info')
}

// 验证工作流
async function validateWorkflow() {
  if (nodes.value.length === 0) {
    validationResult.value = { valid: false, message: '❌ 工作流为空，请至少添加一个节点' }
    hideValidationAfterDelay()
    return
  }

  // 构建邻接表检查环
  const adj = new Map<string, string[]>()
  const inDegree = new Map<string, number>()
  
  nodes.value.forEach(node => adj.set(node.id, []))
  nodes.value.forEach(node => inDegree.set(node.id, 0))
  
  edges.value.forEach(edge => {
    if (adj.has(edge.source)) {
      adj.get(edge.source)?.push(edge.target)
      inDegree.set(edge.target, (inDegree.get(edge.target) || 0) + 1)
    }
  })
  
  // Kahn算法拓扑排序
  const queue: string[] = []
  inDegree.forEach((deg, nodeId) => {
    if (deg === 0) queue.push(nodeId)
  })
  
  let sortedCount = 0
  while (queue.length > 0) {
    const current = queue.shift()!
    sortedCount++
    
    adj.get(current)?.forEach(neighbor => {
      const newDeg = (inDegree.get(neighbor) || 1) - 1
      inDegree.set(neighbor, newDeg)
      if (newDeg === 0) queue.push(neighbor)
    })
  }

  if (sortedCount !== nodes.value.length) {
    validationResult.value = { valid: false, message: '❌ 工作流包含循环依赖！请检查节点连接。' }
  } else {
    validationResult.value = { valid: true, message: `✅ 工作流验证通过！(${nodes.value.length}个节点, ${edges.value.length}条连接)` }
  }
  
  hideValidationAfterDelay()
}

function hideValidationAfterDelay() {
  setTimeout(() => {
    validationResult.value = null
  }, 5000)
}

// 返回上一页
function goBack() {
  if (window.history.length > 1) {
    window.history.back()
  } else {
    window.location.href = '/workflow-templates'
  }
}

// 切换全屏
function toggleFullscreen() {
  isFullscreen.value = !isFullscreen.value
  
  if (isFullscreen.value) {
    document.documentElement.requestFullscreen?.()
  } else {
    document.fullscreenElement && document.exitFullscreen()
  }
  
  emit('fullscreen', isFullscreen.value)
}

// 保存工作流
async function saveWorkflow() {
  if (!workflowName.value.trim()) {
    showToast('请先输入工作流名称', 'warning')
    return ''
  }

  if (nodes.value.length === 0) {
    showToast('工作流至少需要一个节点', 'warning')
    return ''
  }

  saving.value = true
  
  try {
    // 构建图定义对象
    const graphDefinition: any = {
      nodes: nodes.value.map(n => ({
        id: n.id,
        type: n.data.nodeType,
        config: n.data.config || {},
        position: n.position,
      })),
      edges: edges.value.map(e => ({
        id: e.id,
        source: e.source,
        target: e.target,
        source_handle: e.sourceHandle || null,
        target_handle: e.targetHandle || null,
        condition: null,
        label: e.label || '',
      })),
    }

    // 准备提交数据
    const submitData: any = {
      name: workflowName.value,
      description: workflowDescription.value,
      icon: '⚙️',
      category: workflowCategory.value,
      graph_definition: graphDefinition,
      tags: workflowTagsInput.value.split(',').map(t => t.trim()).filter(Boolean),
      is_public: false,
    }

    let savedDefinition
    
    if (currentDefinitionId.value) {
      // 更新已有定义
      savedDefinition = await workflowDefinitionsApi.updateWorkflowDefinition(
        currentDefinitionId.value,
        submitData
      )
      showToast('✅ 工作流已更新', 'success')
    } else {
      // 创建新定义
      savedDefinition = await workflowDefinitionsApi.createWorkflowDefinition(submitData)
      showToast('✅ 工作流已保存', 'success')
    }

    currentDefinitionId.value = savedDefinition.id
    hasUnsavedChanges.value = false
    emit('saved', savedDefinition.id)
    return savedDefinition.id
    
  } catch (error: any) {
    console.error('[WorkflowEditor] Save failed:', error)
    showToast(error.response?.data?.detail || '保存失败', 'error')
    return ''
  } finally {
    saving.value = false
  }
}

// 运行工作流
async function runWorkflow() {
  let definitionId = currentDefinitionId.value

  if (hasUnsavedChanges.value || !definitionId) {
    definitionId = await saveWorkflow()
  }

  if (!definitionId) {
    showToast('请先保存工作流再运行', 'warning')
    return
  }

  running.value = true
  
  try {
    const topic = window.prompt('输入要创作的选题或主题', workflowName.value)?.trim()
    if (!topic) {
      showToast('请先输入创作主题', 'warning')
      return
    }

    const modelSettings = collectModelSettings()
    const result = await workflowDefinitionsApi.runWorkflowFromDefinition(definitionId, {
      topic,
      model_settings: modelSettings,
    })

    showToast('🚀 工作流已启动！', 'success')
    emit('run', result.workflow_id)
    
  } catch (error: any) {
    console.error('[WorkflowEditor] Run failed:', error)
    showToast(error.response?.data?.detail || '启动失败', 'error')
  } finally {
    running.value = false
  }
}

function collectModelSettings(): Record<string, any> {
  const settings: Record<string, any> = {}
  for (const node of nodes.value) {
    const config = node.data?.config
    if (!config || typeof config !== 'object') continue
    const nodeType = node.data?.nodeType
    if (nodeType === 'copywrite') {
      if (config.writingStyle) settings.writing_style = config.writingStyle
      if (config.contentLength) settings.content_length = config.contentLength
      if (config.temperature !== undefined) settings.temperature = config.temperature
      if (config.textModel) settings.text_model = config.textModel
    } else if (nodeType === 'search') {
      if (config.searchLimit) settings.search_limit = config.searchLimit
    } else if (nodeType === 'analyze') {
      if (config.analyzeSkill) settings.analyze_skill = config.analyzeSkill
    } else if (nodeType === 'audit') {
      if (config.auditSkill) settings.audit_skill = config.auditSkill
    }
  }
  return settings
}

// 导出工作流
function exportWorkflow() {
  const exportData = {
    name: workflowName.value,
    description: workflowDescription.value,
    category: workflowCategory.value,
    tags: workflowTagsInput.value.split(',').map(t => t.trim()).filter(Boolean),
    version: '1.0.0',
    exported_at: new Date().toISOString(),
    graph_definition: {
      nodes: nodes.value.map(n => ({
        id: n.id,
        type: n.data.nodeType,
        config: n.data.config || {},
        position: n.position,
      })),
      edges: edges.value.map(e => ({
        source: e.source,
        target: e.target,
        condition: null,
        label: e.label || '',
      })),
    },
  }

  const jsonStr = JSON.stringify(exportData, null, 2)
  const blob = new Blob([jsonStr], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  
  const a = document.createElement('a')
  a.href = url
  a.download = `${workflowName.value || 'workflow'}_${Date.now()}.json`
  a.click()
  
  URL.revokeObjectURL(url)
  showToast('✅ 工作流已导出', 'success')
}

// 导入工作流
function handleImport() {
  try {
    const data = JSON.parse(importJsonText.value)
    
    if (!data.graph_definition || !data.graph_definition.nodes) {
      throw new Error('无效的工作流定义格式')
    }

    // 清空当前画布
    nodes.value = []
    edges.value = []

    // 加载导入的数据
    if (data.name) workflowName.value = data.name
    if (data.description) workflowDescription.value = data.description
    if (data.category) workflowCategory.value = data.category
    if (data.tags) workflowTagsInput.value = data.tags.join(', ')

    // 转换并添加节点
    if (data.graph_definition.nodes) {
      const importedNodes = data.graph_definition.nodes.map((n: any) => ({
        id: n.id,
        type: 'custom',
        position: n.position || { x: 100, y: 100 },
        data: {
          label: getNodeDisplayName(n.type),
          icon: getNodeIcon(n.type),
          nodeType: n.type,
          config: n.config || {},
          category: getNodeCategory(n.type),
        },
      }))
      
      addNodes(importedNodes)
    }

    // 转换并添加边
    if (data.graph_definition.edges) {
      const importedEdges = data.graph_definition.edges.map((e: any, idx: number) => ({
        id: e.id || `edge_imported_${idx}`,
        source: e.source,
        target: e.target,
        type: 'smoothstep',
        animated: true,
        ...defaultEdgeOptions,
      }))
      
      addEdges(importedEdges)
    }

    hasUnsavedChanges.value = true
    showImportDialog.value = false
    importJsonText.value = ''
    
    // 自动应用格子布局
    nextTick(() => {
      const positions = computeAutoLayout(nodes.value, edges.value)
      nodes.value = nodes.value.map((n: any) => {
        const pos = positions.get(n.id)
        if (pos) {
          return { ...n, position: pos }
        }
        return n
      })
      
      // 延迟适配视图
      setTimeout(() => {
        fitView({ 
          padding: 0.3,
          duration: 400 
        })
      }, 150)
    })
    
    showToast('✅ 工作流已导入', 'success')

  } catch (error: any) {
    console.error('[WorkflowEditor] Import failed:', error)
    showToast('导入失败: ' + error.message, 'error')
  }
}

// 辅助函数：获取节点显示名称
function getNodeDisplayName(nodeType: string): string {
  const nameMap: Record<string, string> = {
    search: '🔍 智能搜索',
    analyze: '📊 AI分析',
    copywrite: '✍️ AI文案',
    image_plan: '🎨 图片规划',
    image_gen: '🖼️ 图片生成',
    image_review: '🔍 图片审核',
    audit: '✅ 合规审核',
    final_review: '👁️ 终审确认',
    publish: '📕 发布到小红书',
  }
  return nameMap[nodeType] || nodeType
}

// 辅助函数：获取节点图标
function getNodeIcon(nodeType: string): string {
  const iconMap: Record<string, string> = {
    search: '🔍',
    analyze: '📊',
    copywrite: '✍️',
    image_plan: '🎨',
    image_gen: '🖼️',
    image_review: '🔍',
    audit: '✅',
    final_review: '👁️',
    publish: '📕',
  }
  return iconMap[nodeType] || '📦'
}

// 辅助函数：获取节点分类
function getNodeCategory(nodeType: string): string {
  const categoryMap: Record<string, string> = {
    search: 'datasource',
    analyze: 'analysis',
    copywrite: 'creation',
    image_plan: 'creation',
    image_gen: 'creation',
    image_review: 'review',
    audit: 'review',
    final_review: 'review',
    publish: 'publish',
  }
  return categoryMap[nodeType] || 'custom'
}

// 格式化JSON显示
function formatJson(obj: any): string {
  return JSON.stringify(obj, null, 2)
}

// 暴露方法给父组件调用
defineExpose({
  saveWorkflow,
  loadFromTemplateData,
  applyAutoLayout,
})

// 从模板数据加载（从模板页跳转过来时使用）
function loadFromTemplateData(templateData: any) {
  if (!templateData) return
  
  // 填充基本信息
  workflowName.value = templateData.name || '未命名工作流'
  workflowDescription.value = templateData.description || ''
  workflowCategory.value = templateData.category || 'custom'
  
  // 填充图定义
  const graphDef = templateData.graph_definition
  if (!graphDef) return
  
  // 清空当前画布
  nodes.value = []
  edges.value = []
  
  // 转换节点格式（先用临时位置）
  if (graphDef.nodes) {
    const importedNodes = graphDef.nodes.map((n: any) => ({
      id: n.id,
      type: 'custom',
      position: n.position || { x: 0, y: 0 },
      data: {
        label: getNodeDisplayName(n.type),
        icon: getNodeIcon(n.type),
        nodeType: n.type,
        config: n.config || {},
        category: getNodeCategory(n.type),
      },
    }))
    addNodes(importedNodes)
  }
  
  // 转换边格式
  if (graphDef.edges) {
    const importedEdges = graphDef.edges.map((e: any) => ({
      id: e.id,
      source: e.source,
      target: e.target,
      sourceHandle: e.source_handle,
      targetHandle: e.target_handle,
      type: 'smoothstep',
      animated: true,
      ...defaultEdgeOptions,
    }))
    addEdges(importedEdges)
  }
  
  // 自动应用格子布局
  nextTick(() => {
    const positions = computeAutoLayout(nodes.value, edges.value)
    nodes.value = nodes.value.map((n: any) => {
      const pos = positions.get(n.id)
      if (pos) {
        return { ...n, position: pos }
      }
      return n
    })
    
    // 延迟适配视图
    setTimeout(() => {
      fitView({ 
        padding: 0.3,
        duration: 400 
      })
    }, 150)
  })
  
  hasUnsavedChanges.value = true
  showToast(`✅ 已加载模板: ${templateData.name}`, 'success')
}

// ===== 生命周期 =====
// 刷新 Lucide 图标
function refreshIcons() {
  nextTick(() => {
    createIcons({ icons })
  })
}

onMounted(async () => {
  console.log('[WorkflowEditor] Component mounted, loading nodes...')
  
  try {
    await loadAvailableNodes()
  } catch (e) {
    console.error('[WorkflowEditor] loadAvailableNodes failed:', e)
  }
  
  if (props.definitionId) {
    try {
      await loadDefinition(props.definitionId)
    } catch (e) {
      console.error('[WorkflowEditor] loadDefinition failed:', e)
    }
  }
  
  nextTick(() => {
    try {
      fitView({ padding: 0.3, duration: 300 })
    } catch (e) {
      console.warn('[WorkflowEditor] fitView failed:', e)
    }
    refreshIcons()
  })
  
  console.log('[WorkflowEditor] Init complete. Categories:', allNodeCategories.value.length, 'Nodes:', availableNodes.value.length)
})

// 监听关键状态变化，刷新图标
watch([leftCollapsed, activeCategories, showRightPanel, showImportDialog, validationResult], () => {
  refreshIcons()
})

// 节点列表加载完成后也要刷新
watch(filteredNodeCategories, () => {
  refreshIcons()
}, { deep: true })

watch(nodes, () => {
  refreshIcons()
}, { deep: true })
</script>

<style scoped>
/* ===== 编辑器根容器 ===== */
.workflow-editor {
  position: relative;
  width: 100%;
  height: 100%;
  min-height: 500px;
  overflow: hidden;
}

/* ===== 画布占满全屏 ===== */
.editor-canvas {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  overflow: hidden;
}

.vue-flow-wrapper :deep(.vue-flow) {
  background-color: #fafbfc !important;
  background-image:
    linear-gradient(to right, #cdd0d6 1px, transparent 1px),
    linear-gradient(to bottom, #cdd0d6 1px, transparent 1px),
    linear-gradient(to right, #e5e7eb 1px, transparent 1px),
    linear-gradient(to bottom, #e5e7eb 1px, transparent 1px) !important;
  background-size:
    100px 100px,
    100px 100px,
    20px 20px,
    20px 20px !important;
  background-position: -1px -1px !important;
}

.vue-flow-wrapper {
  width: 100%;
  height: 100%;
  min-height: 400px;
}

.vue-flow-wrapper :deep(.vue-flow__pane),
.vue-flow-wrapper :deep(.vue-flow__transformationpane),
.vue-flow-wrapper :deep(.vue-flow__viewport),
.vue-flow-wrapper :deep(.vue-flow__background),
.vue-flow-wrapper :deep(.vue-flow__container) {
  background: transparent !important;
}

.canvas-empty {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  text-align: center;
  pointer-events: none;
}

.empty-content {
  background: rgba(255, 255, 255, 0.9);
  backdrop-filter: blur(8px);
  padding: 40px 60px;
  border-radius: 16px;
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.08);
  pointer-events: auto;
}

.empty-icon {
  font-size: 64px;
  color: #d1d5db;
  margin-bottom: 16px;
}

.empty-content h3 {
  font-size: 18px;
  color: #374151;
  margin: 0 0 8px 0;
}

.empty-content p {
  font-size: 14px;
  color: #9ca3af;
  margin: 0 0 24px 0;
}

.quick-add-buttons {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: center;
}

.quick-add-btn {
  padding: 8px 16px;
  border: 1px solid #e5e7eb;
  border-radius: 20px;
  background: white;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
}

.quick-add-btn:hover {
  border-color: #FF2442;
  color: #FF2442;
  background: rgba(255, 36, 66, 0.05);
}

/* ===== 左侧浮动节点面板 ===== */
.floating-sidebar {
  position: absolute;
  top: 56px;
  left: 12px;
  bottom: 12px;
  margin-top: 16px;
  width: 220px;
  background: rgba(255, 255, 255, 0.88);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border: 1px solid rgba(229, 231, 235, 0.6);
  border-radius: 12px;
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.08);
  display: flex;
  flex-direction: column;
  z-index: 20;
  transition: width 0.3s ease;
  overflow: hidden;
}

.floating-sidebar.collapsed {
  width: 44px;
}

.sidebar-header {
  padding: 12px;
  border-bottom: 1px solid rgba(243, 244, 246, 0.6);
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 44px;
}

.sidebar-header h3 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: #1f2937;
  display: flex;
  align-items: center;
  gap: 6px;
}

.collapse-btn {
  width: 26px;
  height: 26px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  background: transparent;
  cursor: pointer;
  border-radius: 6px;
  color: #6b7280;
  transition: all 0.2s;
  flex-shrink: 0;
}

.collapse-btn:hover {
  background: rgba(0, 0, 0, 0.05);
  color: #374151;
}

.node-search {
  padding: 10px 12px;
  border-bottom: 1px solid rgba(243, 244, 246, 0.6);
  display: flex;
  align-items: center;
  gap: 8px;
}

.search-icon {
  color: #9ca3af;
  width: 16px;
  height: 16px;
}

.search-input {
  flex: 1;
  border: none;
  background: transparent;
  font-size: 13px;
  color: #374151;
  outline: none;
}

.search-input::placeholder {
  color: #d1d5db;
}

.node-categories {
  flex: 1;
  overflow-y: auto;
  padding: 6px;
}

.category-title {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 10px;
  cursor: pointer;
  border-radius: 6px;
  font-weight: 500;
  transition: background 0.15s;
}

.category-title:hover {
  background: rgba(0, 0, 0, 0.03);
}

.category-icon {
  font-size: 14px;
}

.category-name {
  flex: 1;
  font-size: 13px;
  color: #374151;
}

.category-count {
  font-size: 10px;
  color: #9ca3af;
  background: rgba(0, 0, 0, 0.04);
  padding: 1px 6px;
  border-radius: 10px;
}

.category-toggle {
  font-size: 10px;
  color: #9ca3af;
}

.palette-node {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  margin: 3px 0;
  border: 1px solid rgba(229, 231, 235, 0.8);
  border-radius: 8px;
  cursor: grab;
  transition: all 0.2s;
  background: rgba(255, 255, 255, 0.6);
}

.palette-node:hover {
  border-color: #FF2442;
  box-shadow: 0 2px 8px rgba(255, 36, 66, 0.15);
  transform: translateX(2px);
}

.palette-node:active {
  cursor: grabbing;
  transform: scale(0.98);
}

.node-icon-lg {
  font-size: 20px;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.03);
  border-radius: 6px;
  flex-shrink: 0;
}

.node-info {
  flex: 1;
  min-width: 0;
}

.node-name {
  display: block;
  font-size: 12px;
  font-weight: 500;
  color: #1f2937;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.node-type {
  display: block;
  font-size: 10px;
  color: #9ca3af;
  font-family: monospace;
}

.collapsed-hint {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #d1d5db;
}

/* ===== 顶部浮动工具栏 ===== */
.floating-toolbar {
  position: absolute;
  top: 72px;
  left: 250px;
  right: 12px;
  min-height: 40px;
  background: rgba(255, 255, 255, 0.88);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border: 1px solid rgba(229, 231, 235, 0.6);
  border-radius: 10px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 12px;
  z-index: 20;
  gap: 8px;
  flex-wrap: wrap;
}

.toolbar-left,
.toolbar-right {
  display: flex;
  align-items: center;
  gap: 6px;
}

.toolbar-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  padding: 6px 10px;
  border: 1px solid rgba(229, 231, 235, 0.8);
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.6);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
  color: #374151;
  white-space: nowrap;
}

.toolbar-btn:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.9);
  border-color: #d1d5db;
}

.toolbar-btn.back-btn {
  color: #6b7280;
}

.toolbar-btn.primary {
  background: linear-gradient(135deg, #FF2442 0%, #FF2442 100%);
  color: white;
  border: none;
}

.toolbar-btn.primary:hover:not(:disabled) {
  box-shadow: 0 2px 8px rgba(255, 36, 66, 0.35);
}

.toolbar-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.workflow-name-input {
  border: none;
  border-bottom: 1.5px solid transparent;
  background: transparent;
  font-size: 13px;
  font-weight: 600;
  color: #1f2937;
  padding: 4px 6px;
  outline: none;
  max-width: 180px;
  transition: border-color 0.2s;
}

.workflow-name-input:focus {
  border-bottom-color: #FF2442;
}

.workflow-name-input::placeholder {
  color: #9ca3af;
  font-weight: 400;
}

.auto-save-hint {
  display: flex;
  align-items: center;
  gap: 3px;
  font-size: 11px;
  color: #f59e0b;
  animation: pulse 2s infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

/* ===== 右侧浮动配置面板 ===== */
.floating-config-panel {
  position: absolute;
  top: 56px;
  right: 12px;
  bottom: 12px;
  width: 260px;
  background: rgba(255, 255, 255, 0.88);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border: 1px solid rgba(229, 231, 235, 0.6);
  border-radius: 12px;
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.08);
  display: flex;
  flex-direction: column;
  z-index: 20;
  pointer-events: none;
  transform: translateX(calc(100% + 20px));
  opacity: 0;
  transition: transform 0.3s ease, opacity 0.3s ease;
}

.floating-config-panel.visible {
  transform: translateX(0);
  pointer-events: auto;
  opacity: 1;
}

.panel-header {
  padding: 12px 14px;
  border-bottom: 1px solid rgba(243, 244, 246, 0.6);
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 44px;
}

.panel-header h3 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: #1f2937;
  display: flex;
  align-items: center;
  gap: 6px;
}

.panel-close-btn {
  width: 26px;
  height: 26px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  background: transparent;
  cursor: pointer;
  border-radius: 6px;
  color: #6b7280;
  transition: all 0.2s;
}

.panel-close-btn:hover {
  background: rgba(239, 68, 68, 0.1);
  color: #ef4444;
}

.config-content {
  flex: 1;
  overflow-y: auto;
  padding: 14px;
}

.selected-node-icon-sm {
  font-size: 16px;
  margin-right: 2px;
}

.node-type-badge {
  font-size: 11px;
  padding: 2px 8px;
  background: rgba(255, 36, 66, 0.15);
  color: #FF2442;
  border-radius: 10px;
  font-family: monospace;
}

.config-form {
  margin-bottom: 14px;
}

.simple-config {
  padding: 4px 0;
}

.simple-config .info-group {
  margin-bottom: 10px;
}

.simple-config .info-group label {
  display: block;
  font-size: 12px;
  color: #6b7280;
  margin-bottom: 4px;
  font-weight: 500;
}

.config-preview {
  background: rgba(0, 0, 0, 0.03);
  border: 1px solid rgba(229, 231, 235, 0.6);
  border-radius: 6px;
  padding: 8px;
  font-size: 11px;
  line-height: 1.5;
  color: #4b5563;
  overflow-x: auto;
  max-height: 180px;
  overflow-y: auto;
  margin: 0;
  font-family: 'Consolas', 'Monaco', monospace;
}

.config-actions {
  margin-top: 14px;
  padding-top: 14px;
  border-top: 1px solid rgba(243, 244, 246, 0.6);
}

.action-btn {
  width: 100%;
  padding: 8px;
  border: none;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
}

.action-btn.danger {
  background: rgba(239, 68, 68, 0.08);
  color: #dc2626;
  border: 1px solid rgba(239, 68, 68, 0.2);
}

.action-btn.danger:hover {
  background: rgba(239, 68, 68, 0.15);
}

/* ===== 对话框 ===== */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal {
  background: white;
  border-radius: 12px;
  width: 90%;
  max-width: 600px;
  max-height: 80vh;
  overflow-y: auto;
}

.modal-header {
  padding: 20px 24px;
  border-bottom: 1px solid #e5e7eb;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.modal-header h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
}

.close-btn {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  background: transparent;
  cursor: pointer;
  border-radius: 6px;
  color: #6b7280;
}

.close-btn:hover {
  background: #f3f4f6;
}

.modal-body {
  padding: 24px;
}

.modal-body p {
  margin: 0 0 12px 0;
  color: #6b7280;
  font-size: 14px;
}

.import-textarea {
  width: 100%;
  padding: 12px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  font-family: 'Consolas', monospace;
  font-size: 12px;
  resize: vertical;
  outline: none;
}

.import-textarea:focus {
  border-color: #FF2442;
  box-shadow: 0 0 0 3px rgba(255, 36, 66, 0.1);
}

.modal-actions {
  display: flex;
  gap: 12px;
  justify-content: flex-end;
  margin-top: 20px;
}

.btn {
  padding: 10px 20px;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  border: none;
  transition: all 0.2s;
}

.btn.primary {
  background: #FF2442;
  color: white;
}

.btn.primary:hover {
  background: #E51B34;
}

.btn.secondary {
  background: #f3f4f6;
  color: #374151;
}

.btn.secondary:hover {
  background: #e5e7eb;
}

/* ===== 验证提示 ===== */
.validation-toast {
  position: fixed;
  top: 80px;
  left: 50%;
  transform: translateX(-50%);
  padding: 12px 24px;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  z-index: 2000;
  display: flex;
  align-items: center;
  gap: 8px;
  animation: slideDown 0.3s ease;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.15);
}

.validation-toast.success {
  background: #f0fdf4;
  color: #166534;
  border: 1px solid #bbf7d0;
}

.validation-toast.error {
  background: #fef2f2;
  color: #991b1b;
  border: 1px solid #fecaca;
}

@keyframes slideDown {
  from {
    opacity: 0;
    transform: translateX(-50%) translateY(-20px);
  }
  to {
    opacity: 1;
    transform: translateX(-50%) translateY(0);
  }
}
</style>