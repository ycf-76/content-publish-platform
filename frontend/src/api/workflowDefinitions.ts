/**
 * Workflow Definitions API - 工作流定义管理接口
 * ============================================
 * 
 * 提供工作流模板的 CRUD 操作：
 * - 创建/编辑/删除工作流定义
 * - 查询可用节点列表（含插件节点）
 * - 保存和加载自定义流程
 * - 内置模板管理
 */

import apiClient from './client'

// ===== 类型定义 =====

export interface GraphNode {
  id: string
  type: string  // 节点类型标识符
  config: Record<string, any>
  position: { x: number; y: number }
}

export interface GraphEdge {
  id: string
  source: string
  target: string
  source_handle?: string
  target_handle?: string
  condition?: string
  label?: string
}

export interface GraphDefinition {
  nodes: GraphNode[]
  edges: GraphEdge[]
}

export interface WorkflowDefinition {
  id: string
  name: string
  description?: string
  icon: string
  category: string
  version: number
  user_id: string
  graph_definition: GraphDefinition
  status: 'draft' | 'active' | 'archived' | 'deprecated'
  is_builtin: boolean
  is_public: boolean
  usage_count: number
  success_count: number
  avg_duration_ms?: number
  tags?: string[]
  author_name?: string
  thumbnail_url?: string
  created_at: string
  updated_at?: string
}

export interface NodeDefinition {
  node_type: string
  display_name: string
  category: string
  description: string
  icon: string
  version: string
  input_schema: any
  output_schema: any
  config_schema: any
  plugin_id?: string
  is_builtin: boolean
  tags: string[]
}

export interface NodeListResponse {
  nodes: NodeDefinition[]
  categories: Array<{
    category: string
    label: string
    count: number
  }>
  total: number
}

// ===== API 方法 =====

/**
 * 获取所有可用的工作流节点
 */
export async function getAvailableNodes(params?: {
  category?: string
  include_details?: boolean
  search?: string
}): Promise<NodeListResponse> {
  const response = await apiClient.get('/workflow-definitions/nodes/available', { params })
  return (response as any)?.data ?? response
}

/**
 * 获取工作流定义列表
 */
export async function listWorkflowDefinitions(params?: {
  status?: string
  category?: string
  include_builtin?: boolean
  search?: string
  limit?: number
  offset?: number
}): Promise<WorkflowDefinition[]> {
  const response = await apiClient.get('/workflow-definitions', { params })
  return (response as any)?.data ?? response
}

/**
 * 获取单个工作流定义详情
 */
export async function getWorkflowDefinition(definitionId: string): Promise<WorkflowDefinition> {
  const response = await apiClient.get(`/workflow-definitions/${definitionId}`)
  return (response as any)?.data ?? response
}

/**
 * 创建工作流定义
 */
export async function createWorkflowDefinition(data: {
  name: string
  description?: string
  icon?: string
  category?: string
  graph_definition: GraphDefinition
  tags?: string[]
  is_public?: boolean
}): Promise<WorkflowDefinition> {
  const response = await apiClient.post('/workflow-definitions', data)
  return (response as any)?.data ?? response
}

/**
 * 更新工作流定义
 */
export async function updateWorkflowDefinition(
  definitionId: string,
  data: Partial<{
    name: string
    description: string
    icon: string
    category: string
    graph_definition: GraphDefinition
    tags: string[]
    status: string
    is_public: boolean
  }>
): Promise<WorkflowDefinition> {
  const response = await apiClient.put(`/workflow-definitions/${definitionId}`, data)
  return (response as any)?.data ?? response
}

/**
 * 删除工作流定义
 */
export async function deleteWorkflowDefinition(definitionId: string): Promise<void> {
  await apiClient.delete(`/workflow-definitions/${definitionId}`)
}

/**
 * 复制工作流定义
 */
export async function duplicateWorkflowDefinition(
  definitionId: string,
  newName?: string
): Promise<WorkflowDefinition> {
  const response = await apiClient.post(
    `/workflow-definitions/${definitionId}/duplicate`,
    null,
    { params: { new_name: newName } }
  )
  return (response as any)?.data ?? response
}

/**
 * 获取内置模板列表
 */
export async function getBuiltinTemplates(): Promise<WorkflowDefinition[]> {
  const response = await apiClient.get('/workflow-definitions/builtin/templates')
  return (response as any)?.data ?? response
}

/**
 * 基于工作流定义启动执行
 */
export async function runWorkflowFromDefinition(
  definitionId: string,
  params: {
    topic: string
    account_id?: string
    model_settings?: Record<string, any>
  }
): Promise<{
  workflow_id: string
  definition_id: string
  status: string
  message: string
}> {
  const { model_settings, ...queryParams } = params
  const response = await apiClient.post(
    `/workflow-definitions/${definitionId}/run`,
    model_settings ? { model_settings } : null,
    { params: queryParams }
  )
  return (response as any)?.data ?? response
}

/**
 * 工作流定义服务健康检查
 */
export async function healthCheck(): Promise<any> {
  const response = await apiClient.get('/workflow-definitions/health')
  return (response as any)?.data ?? response
}

// 导出默认对象
const workflowDefinitionsApi = {
  getAvailableNodes,
  listWorkflowDefinitions,
  getWorkflowDefinition,
  createWorkflowDefinition,
  updateWorkflowDefinition,
  deleteWorkflowDefinition,
  duplicateWorkflowDefinition,
  getBuiltinTemplates,
  runWorkflowFromDefinition,
  healthCheck,
}

export default workflowDefinitionsApi