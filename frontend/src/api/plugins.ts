/**
 * Plugin API Client - 插件系统RESTful API客户端
 * 与后端 /api/plugins/* 端点交互
 */

import apiClient from './client'

// ==================== Types ====================

export interface Plugin {
  id: string
  name: string
  version: string
  category: PluginCategory
  author_name: string
  author_email?: string
  description: string
  display_icon?: string
  pricing_model: PricingModel
  price?: number
  price_monthly?: number
  status: PluginStatus
  is_builtin: boolean
  is_featured?: boolean
  is_installed?: boolean
  is_active?: boolean
  capabilities: string[]
  permissions_required: string[]
  dependencies?: string[]
  config_schema?: Record<string, any>
  stats?: PluginStats
  created_at: string
  updated_at: string
}

export interface PluginStats {
  install_count: number
  active_users: number
  avg_rating: number
  review_count: number
  download_count?: number
  avg_execution_time_ms?: number
  success_rate?: number
}

export interface PluginVersion {
  id: number
  plugin_id: string
  version: string
  changelog?: string
  release_notes?: string
  is_latest: boolean
  released_at: string
  download_count: number
}

export interface PluginConfig {
  id: number
  user_id: string
  plugin_id: string
  config_json: Record<string, any>
  is_enabled: boolean
  updated_at: string
}

export interface PluginReview {
  id: number
  plugin_id: string
  user_id: string
  rating: number
  title: string
  content: string
  moderation_status: 'pending' | 'approved' | 'rejected'
  helpful_count: number
  is_verified_purchase?: boolean
  created_at: string
}

export type PluginCategory = 
  | 'platform'
  | 'datasource' 
  | 'workflow_node'
  | 'ui_theme'
  | 'analytics'
  | 'utility'
  | 'integration'
  | 'ai_model'
  | 'tool'
  | 'theme'

export type PluginStatus = 'active' | 'deprecated' | 'draft' | 'pending_review' | 'approved' | 'rejected'

export type PricingModel = 'free' | 'freemium' | 'paid' | 'subscription'

export interface PluginListParams {
  q?: string
  category?: PluginCategory
  status?: PluginStatus
  pricing_model?: PricingModel
  author_name?: string
  featured?: boolean
  sort_by?: 'created_at' | 'name' | 'install_count' | 'avg_rating'
  sort_order?: 'asc' | 'desc'
  page?: number
  page_size?: number
}

export interface PluginListResponse {
  total: number
  page: number
  page_size: number
  items: Plugin[]
}

export interface InstallRequest {
  config?: Record<string, any>
}

export interface InstallResponse {
  success: boolean
  action: 'install'
  message: string
  plugin_id: string
  timestamp: string
}

export interface ConfigUpdateRequest {
  config_json?: Record<string, any>
  is_enabled?: boolean
}

export interface BulkActionRequest {
  plugin_ids: string[]
  action: 'enable' | 'disable' | 'uninstall'
}

export interface HealthCheckResponse {
  status: 'healthy' | 'degraded' | 'unhealthy'
  statistics: {
    total_plugins: number
    active_plugins: number
    builtin_plugins: number
    third_party_plugins: number
  }
  version: string
  uptime_seconds: number
}

// ==================== API Methods ====================

function unpack<T>(response: any): T {
  if (response && typeof response === 'object' && 'data' in response) {
    return response.data as T
  }
  return response as T
}

export const pluginsApi = {
  /**
   * 获取插件列表（支持搜索、过滤、排序、分页）
   */
  async list(params?: PluginListParams): Promise<PluginListResponse> {
    const response = await apiClient.get('/plugins', { params })
    return unpack(response)
  },

  /**
   * 获取单个插件详情
   */
  async get(pluginId: string): Promise<Plugin> {
    const response = await apiClient.get(`/plugins/${pluginId}`)
    return unpack(response)
  },

  /**
   * 创建新插件（管理员权限）
   */
  async create(data: Partial<Plugin>): Promise<Plugin> {
    const response = await apiClient.post('/plugins', data)
    return unpack(response)
  },

  /**
   * 更新插件信息（管理员权限）
   */
  async update(pluginId: string, data: Partial<Plugin>): Promise<Plugin> {
    const response = await apiClient.put(`/plugins/${pluginId}`, data)
    return unpack(response)
  },

  /**
   * 删除插件（管理员权限）
   */
  async delete(pluginId: string): Promise<void> {
    await apiClient.delete(`/plugins/${pluginId}`)
  },

  // ==================== Install Management ====================

  /**
   * 安装插件
   */
  async install(pluginId: string, request?: InstallRequest): Promise<InstallResponse> {
    const response = await apiClient.post(`/plugins/${pluginId}/install`, request)
    return unpack(response)
  },

  /**
   * 卸载插件
   */
  async uninstall(pluginId: string): Promise<InstallResponse> {
    const response = await apiClient.delete(`/plugins/${pluginId}/uninstall`)
    return unpack(response)
  },

  /**
   * 启用插件
   */
  async enable(pluginId: string): Promise<InstallResponse> {
    const response = await apiClient.post(`/plugins/${pluginId}/enable`)
    return unpack(response)
  },

  /**
   * 禁用插件
   */
  async disable(pluginId: string): Promise<InstallResponse> {
    const response = await apiClient.post(`/plugins/${pluginId}/disable`)
    return unpack(response)
  },

  // ==================== Configuration ====================

  /**
   * 获取用户对某插件的配置
   */
  async getConfig(pluginId: string): Promise<PluginConfig> {
    const response = await apiClient.get(`/plugins/${pluginId}/config`)
    return unpack(response)
  },

  /**
   * 更新用户对某插件的配置
   */
  async updateConfig(pluginId: string, request: ConfigUpdateRequest): Promise<PluginConfig> {
    const response = await apiClient.put(`/plugins/${pluginId}/config`, request)
    return unpack(response)
  },

  // ==================== Versions ====================

  /**
   * 获取插件版本历史
   */
  async listVersions(pluginId: string, includeDeprecated = false): Promise<PluginVersion[]> {
    const response = await apiClient.get(`/plugins/${pluginId}/versions`, {
      params: { include_deprecated: includeDeprecated }
    })
    return unpack(response)
  },

  // ==================== Reviews ====================

  /**
   * 创建评价
   */
  async createReview(
    pluginId: string,
    data: { rating: number; title?: string; content?: string }
  ): Promise<PluginReview> {
    const response = await apiClient.post(`/plugins/${pluginId}/reviews`, data)
    return unpack(response)
  },

  /**
   * 获取插件评价列表（支持分页、排序、筛选）
   */
  async getReviews(
    pluginId: string,
    params?: {
      page?: number
      page_size?: number
      sort_by?: 'newest' | 'oldest' | 'rating_high' | 'rating_low' | 'helpful'
      rating_filter?: number
    }
  ): Promise<{
    success: boolean
    data: {
      reviews: PluginReview[]
      pagination: {
        total: number
        page: number
        page_size: number
        total_pages: number
      }
      summary: {
        avg_rating: number | null
        total_reviews: number
      }
    }
  }> {
    const response = await apiClient.get(`/plugins/${pluginId}/reviews`, { params })
    return unpack(response)
  },

  /**
   * 获取当前用户的评价
   */
  async getMyReview(pluginId: string): Promise<PluginReview | null> {
    const response = await apiClient.get(`/plugins/${pluginId}/my-review`)
    return unpack(response)
  },

  /**
   * 更新评价
   */
  async updateReview(
    pluginId: string,
    reviewId: number,
    data: { rating: number; title?: string; content?: string }
  ): Promise<PluginReview> {
    const response = await apiClient.put(`/plugins/${pluginId}/reviews/${reviewId}`, data)
    return unpack(response)
  },

  /**
   * 删除评价
   */
  async deleteReview(pluginId: string, reviewId: number): Promise<{ success: boolean; message: string }> {
    const response = await apiClient.delete(`/plugins/${pluginId}/reviews/${reviewId}`)
    return unpack(response)
  },

  /**
   * 标记评价为有用
   */
  async markHelpful(
    pluginId: string,
    reviewId: number
  ): Promise<{ success: boolean; message: string; helpful_count: number }> {
    const response = await apiClient.post(`/plugins/${pluginId}/reviews/${reviewId}/helpful`)
    return unpack(response)
  },

  // ==================== Marketplace & User Plugins ====================

  /**
   * 浏览插件市场
   */
  async getMarketplace(params?: {
    featured?: boolean
    trending?: boolean
    new_releases?: boolean
    category?: PluginCategory
    min_rating?: number
    free_only?: boolean
  }): Promise<PluginListResponse> {
    const response = await apiClient.get('/plugins/marketplace', { params })
    return unpack(response)
  },

  /**
   * 上传插件包到市场（开发者功能）
   * @param file 插件zip包
   */
  async upload(file: File): Promise<{ success: boolean; message: string; plugin_id?: string; name?: string; version?: string; category?: string }> {
    const formData = new FormData()
    formData.append('plugin_package', file)

    const response = await apiClient.post('/plugins/upload', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
      timeout: 120000,
    })

    return unpack(response)
  },

  /**
   * 获取插件详情（别名方法，兼容store调用）
   */
  async getById(pluginId: string): Promise<Plugin> {
    return this.get(pluginId)
  },

  /**
   * 获取当前用户已安装的插件列表
   */
  async getMyPlugins(onlyEnabled = false): Promise<Plugin[]> {
    const response = await apiClient.get('/plugins/my', {
      params: { only_enabled: onlyEnabled }
    })
    return unpack(response) as Plugin[]
  },

  // ==================== Bulk Operations ====================

  /**
   * 批量操作（启用/禁用/卸载）
   */
  async bulkAction(request: BulkActionRequest): Promise<{
    success: boolean
    results: Array<{ plugin_id: string; success: boolean; message?: string }>
  }> {
    const response = await apiClient.post('/plugins/bulk', request)
    return unpack(response)
  },

  // ==================== System ====================

  /**
   * 健康检查
   */
  async healthCheck(): Promise<HealthCheckResponse> {
    const response = await apiClient.get('/plugins/health')
    return unpack(response)
  }
}

export default pluginsApi