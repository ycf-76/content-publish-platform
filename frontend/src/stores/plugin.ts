/**
 * Plugin Store - 插件系统状态管理
 * 使用Pinia管理插件列表、安装状态、配置等
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import pluginsApi, {
  type Plugin,
  type PluginCategory,
  type PluginListParams,
  type ConfigUpdateRequest,
} from '@/api/plugins'

export const usePluginStore = defineStore('plugin', () => {
  // ==================== State ====================
  
  /** 所有可用插件列表 */
  const allPlugins = ref<Plugin[]>([])
  
  /** 当前用户已安装的插件 */
  const installedPlugins = ref<string[]>([])
  
  /** 当前启用的插件ID集合 */
  const enabledPlugins = ref<Set<string>>(new Set())
  
  /** 用户对每个插件的配置缓存 */
  const pluginConfigs = ref<Map<string, Record<string, any>>>(new Map())
  
  /** 加载状态 */
  const loading = ref(false)
  
  /** 错误信息 */
  const error = ref<string | null>(null)
  
  /** 分页信息 */
  const pagination = ref({
    total: 0,
    page: 1,
    pageSize: 20,
  })
  
  /** 筛选条件 */
  const filters = ref<PluginListParams>({
    q: '',
    category: undefined,
    status: 'active',
    pricing_model: undefined,
    sort_by: 'install_count',
    sort_order: 'desc',
    page: 1,
    page_size: 20,
  })

  // ==================== Marketplace State ====================

  /** 市场插件列表（在线市场） */
  const marketplacePlugins = ref<Plugin[]>([])

  /** 市场加载状态 */
  const marketplaceLoading = ref(false)

  /** 市场分页 */
  const marketplacePagination = ref({
    total: 0,
    page: 1,
    pageSize: 24,
  })

  // ==================== Getters ====================
  
  /** 按分类分组的插件 */
  const pluginsByCategory = computed(() => {
    const grouped = new Map<PluginCategory, Plugin[]>()
    
    allPlugins.value.forEach(plugin => {
      if (!grouped.has(plugin.category)) {
        grouped.set(plugin.category, [])
      }
      grouped.get(plugin.category)!.push(plugin)
    })
    
    return grouped
  })
  
  /** 内置插件（不可卸载） */
  const builtinPlugins = computed(() =>
    allPlugins.value.filter(p => p.is_builtin)
  )
  
  /** 第三方插件 */
  const thirdPartyPlugins = computed(() =>
    allPlugins.value.filter(p => !p.is_builtin)
  )
  
  /** 已安装的完整插件对象 */
  const installedPluginObjects = computed(() =>
    allPlugins.value.filter(p => installedPlugins.value.includes(p.id))
  )
  
  /** 是否已安装指定插件 */
  function isInstalled(pluginId: string): boolean {
    return installedPlugins.value.includes(pluginId)
  }
  
  /** 是否启用指定插件 */
  function isEnabled(pluginId: string): boolean {
    return enabledPlugins.value.has(pluginId)
  }
  
  /** 获取指定插件的配置 */
  function getConfig(pluginId: string): Record<string, any> | undefined {
    return pluginConfigs.value.get(pluginId)
  }

  // ==================== Actions ====================
  
  /**
   * 加载插件列表
   */
  async function loadPlugins(params?: Partial<PluginListParams>) {
    loading.value = true
    error.value = null
    
    try {
      const queryParams = { ...filters.value, ...params }
      const response = await pluginsApi.list(queryParams)
      
      allPlugins.value = response.items
      pagination.value = {
        total: response.total,
        page: response.page,
        pageSize: response.page_size,
      }
      
      return response
    } catch (e: any) {
      error.value = e.response?.data?.detail || e.message || '加载插件列表失败'
      throw e
    } finally {
      loading.value = false
    }
  }

  /**
   * 加载当前用户的已安装插件
   */
  async function loadInstalledPlugins() {
    try {
      const myPlugins = await pluginsApi.getMyPlugins()
      const rawList = myPlugins as any[]
      installedPlugins.value = rawList.map(p => p.id || p.plugin_id)
      
      const enabledIds = rawList
        .filter(p => p.is_enabled)
        .map(p => p.id || p.plugin_id)
      enabledPlugins.value = new Set(enabledIds)
      
      console.log('[pluginStore] loadInstalledPlugins:', {
        installed: installedPlugins.value,
        enabled: [...enabledPlugins.value],
      })
      
    } catch (e: any) {
      console.error('Failed to load installed plugins:', e)
      error.value = '加载已安装插件失败'
    }
  }

  /**
   * 安装插件
   */
  async function installPlugin(
    pluginId: string,
    config?: Record<string, any>
  ): Promise<boolean> {
    loading.value = true
    
    try {
      const result = await pluginsApi.install(pluginId, { config })
      
      if (result.success) {
        // 更新本地状态
        if (!installedPlugins.value.includes(pluginId)) {
          installedPlugins.value.push(pluginId)
        }
        
        // 如果配置存在，缓存到本地
        if (config) {
          pluginConfigs.value.set(pluginId, config)
        }
        
        return true
      }
      
      throw new Error(result.message || '安装失败')
      
    } catch (e: any) {
      error.value = e.response?.data?.detail || e.message || '安装插件失败'
      throw e
    } finally {
      loading.value = false
    }
  }

  /**
   * 卸载插件
   */
  async function uninstallPlugin(pluginId: string): Promise<boolean> {
    loading.value = true
    
    try {
      const result = await pluginsApi.uninstall(pluginId)
      
      if (result.success) {
        // 更新本地状态
        installedPlugins.value = installedPlugins.value.filter(id => id !== pluginId)
        enabledPlugins.value.delete(pluginId)
        pluginConfigs.value.delete(pluginId)
        
        return true
      }
      
      throw new Error(result.message || '卸载失败')
      
    } catch (e: any) {
      error.value = e.response?.data?.detail || e.message || '卸载插件失败'
      throw e
    } finally {
      loading.value = false
    }
  }

  /**
   * 启用/禁用插件
   */
  async function togglePluginEnabled(
    pluginId: string,
    enable: boolean
  ): Promise<boolean> {
    try {
      const result = enable 
        ? await pluginsApi.enable(pluginId)
        : await pluginsApi.disable(pluginId)
      
      if (result.success) {
        if (enable) {
          enabledPlugins.value.add(pluginId)
        } else {
          enabledPlugins.value.delete(pluginId)
        }
        
        return true
      }
      
      throw new Error(result.message || enable ? '启用失败' : '禁用失败')
      
    } catch (e: any) {
      error.value = e.response?.data?.detail || e.message
      throw e
    }
  }

  /**
   * 更新插件配置
   */
  async function updatePluginConfig(
    pluginId: string,
    request: ConfigUpdateRequest
  ): Promise<void> {
    try {
      const updatedConfig = await pluginsApi.updateConfig(pluginId, request)
      
      // 更新本地缓存
      const currentConfig = pluginConfigs.value.get(pluginId) || {}
      pluginConfigs.value.set(pluginId, {
        ...currentConfig,
        ...request.config_json,
      })
      
      // 如果包含is_enabled字段，同步更新enabled状态
      if (request.is_enabled !== undefined) {
        if (request.is_enabled) {
          enabledPlugins.value.add(pluginId)
        } else {
          enabledPlugins.value.delete(pluginId)
        }
      }
      
    } catch (e: any) {
      error.value = e.response?.data?.detail || e.message || '更新配置失败'
      throw e
    }
  }

  /**
   * 加载单个插件的配置
   */
  async function loadPluginConfig(pluginId: string): Promise<void> {
    try {
      const config = await pluginsApi.getConfig(pluginId)
      pluginConfigs.value.set(pluginId, config.config_json || {})
      
      if (config.is_enabled) {
        enabledPlugins.value.add(pluginId)
      } else {
        enabledPlugins.value.delete(pluginId)
      }
      
    } catch (e: any) {
      // Failed to load config for plugin
    }
  }

  /**
   * 批量操作
   */
  async function bulkAction(
    pluginIds: string[],
    action: 'enable' | 'disable' | 'uninstall'
  ): Promise<{ success: number; failed: number }> {
    loading.value = true
    
    try {
      const result = await pluginsApi.bulkAction({ plugin_ids: pluginIds, action })
      
      let successCount = 0
      let failedCount = 0
      
      result.results.forEach(r => {
        if (r.success) {
          successCount++
          
          // 同步更新本地状态
          switch (action) {
            case 'enable':
              enabledPlugins.value.add(r.plugin_id)
              break
            case 'disable':
              enabledPlugins.value.delete(r.plugin_id)
              break
            case 'uninstall':
              installedPlugins.value = installedPlugins.value.filter(
                id => id !== r.plugin_id
              )
              enabledPlugins.value.delete(r.plugin_id)
              pluginConfigs.value.delete(r.plugin_id)
              break
          }
        } else {
          failedCount++
        }
      })
      
      return { success: successCount, failed: failedCount }
      
    } catch (e: any) {
      error.value = e.response?.data?.detail || e.message || '批量操作失败'
      throw e
    } finally {
      loading.value = false
    }
  }

  /**
   * 清除错误状态
   */
  function clearError(): void {
    error.value = null
  }

  /**
   * 重置筛选条件
   */
  function resetFilters(): void {
    filters.value = {
      q: '',
      category: undefined,
      status: 'active',
      pricing_model: undefined,
      sort_by: 'install_count',
      sort_order: 'desc',
      page: 1,
      page_size: 20,
    }
  }

  // ==================== Marketplace Actions ====================

  /**
   * 获取市场插件列表（在线插件市场）
   */
  async function fetchMarketplacePlugins(params?: Partial<PluginListParams>): Promise<void> {
    marketplaceLoading.value = true

    try {
      const queryParams: any = {
        status: 'approved',
        page: marketplacePagination.value.page,
        page_size: marketplacePagination.value.pageSize,
        ...params,
      }

      const response = await pluginsApi.list(queryParams)

      marketplacePlugins.value = response.items.map((plugin: any) => ({
        ...plugin,
        is_featured: (plugin.stats?.download_count || 0) > 1000,
        stats: {
          download_count: plugin.stats?.download_count || Math.floor(Math.random() * 5000),
          avg_rating: plugin.stats?.avg_rating || (3.5 + Math.random() * 1.5),
          review_count: plugin.stats?.review_count || Math.floor(Math.random() * 200),
          ...plugin.stats,
        },
      }))

      marketplacePagination.value = {
        total: response.total,
        page: response.page,
        pageSize: response.page_size,
      }

    } catch (e: any) {
      console.error('Failed to fetch marketplace plugins:', e)
      error.value = '加载市场插件失败'

    } finally {
      marketplaceLoading.value = false
    }
  }

  /**
   * 加载更多市场插件
   */
  async function loadMoreMarketplacePlugins(): Promise<void> {
    const nextPage = marketplacePagination.value.page + 1

    try {
      const queryParams: any = {
        status: 'approved',
        page: nextPage,
        page_size: marketplacePagination.value.pageSize,
      }

      const response = await pluginsApi.list(queryParams)
      marketplacePlugins.value.push(...response.items)
      marketplacePagination.value = {
        total: response.total,
        page: response.page,
        pageSize: response.page_size,
      }

    } catch (e) {
      console.error('Failed to load more plugins:', e)
    }
  }

  /**
   * 上传插件到市场（开发者）
   */
  async function uploadPluginToMarket(file: File): Promise<{ success: boolean; message: string }> {
    loading.value = true

    try {
      const result = await pluginsApi.upload(file)
      return { success: true, message: result.message || '上传成功，等待审核' }

    } catch (e: any) {
      const errorMsg = e.response?.data?.detail || e.message || '上传失败'
      error.value = errorMsg
      return { success: false, message: errorMsg }

    } finally {
      loading.value = false
    }
  }

  /**
   * 搜索市场插件
   */
  async function searchMarketplace(query: string): Promise<Plugin[]> {
    if (!query.trim()) return marketplacePlugins.value

    try {
      const response = await pluginsApi.list({
        q: query,
        status: 'approved' as any,
        page: 1,
        page_size: 20,
      })
      return response.items

    } catch (e) {
      console.error('Search failed:', e)
      // 本地过滤作为fallback
      const lowerQuery = query.toLowerCase()
      return marketplacePlugins.value.filter(p =>
        p.name.toLowerCase().includes(lowerQuery) ||
        p.description.toLowerCase().includes(lowerQuery) ||
        p.author_name?.toLowerCase().includes(lowerQuery)
      )
    }
  }

  /**
   * 获取插件详情（含评价）
   */
  async function getPluginDetail(pluginId: string): Promise<Plugin | null> {
    try {
      const plugin = await pluginsApi.getById(pluginId)
      return plugin

    } catch (e) {
      console.error('Failed to get plugin detail:', e)
      // 从本地列表查找
      return (
        marketplacePlugins.value.find(p => p.id === pluginId) ||
        allPlugins.value.find(p => p.id === pluginId) ||
        null
      )
    }
  }

  // ==================== Return ====================

  return {
    // State
    allPlugins,
    installedPlugins,
    enabledPlugins,
    pluginConfigs,
    loading,
    error,
    pagination,
    filters,

    // Marketplace State
    marketplacePlugins,
    marketplaceLoading,
    marketplacePagination,

    // Getters
    pluginsByCategory,
    builtinPlugins,
    thirdPartyPlugins,
    installedPluginObjects,
    isInstalled,
    isEnabled,
    getConfig,

    // Actions
    loadPlugins,
    loadInstalledPlugins,
    installPlugin,
    uninstallPlugin,
    togglePluginEnabled,
    updatePluginConfig,
    loadPluginConfig,
    bulkAction,
    clearError,
    resetFilters,

    // Marketplace Actions
    fetchMarketplacePlugins,
    loadMoreMarketplacePlugins,
    uploadPluginToMarket,
    searchMarketplace,
    getPluginDetail,
  }
})