import apiClient from './client'

/** 选题池条目（v6 合并：含监控字段；v7 扩展详情页字段） */
export interface TopicPoolItem {
  id: string
  platform: string
  content_id: string | null
  title: string
  summary: string | null
  url: string | null
  author: string | null
  likes: number
  comments: number
  collects: number
  shares: number
  fans_count: number
  cover_img: string | null
  images: string[]
  source_keyword: string | null
  is_favorited: boolean
  created_at: string
  // 监控字段
  auto_source: 'manual' | 'monitor'
  heat_score: number
  heat_status: string
  dimensions: { emotion: string; scene: string; visual: string } | null
  published_at: string
  // v7 详情页字段（列表接口也会返回，但 content/raw 仅详情接口返回）
  tags: string[]
  ai_summary: string | null
  view_count: number
  ai_summary_generated_at: string
  // 仅详情接口返回（include_full=true）
  content?: string | null
  raw?: Record<string, unknown> | null
}

/** 详情页响应（GET /{item_id}） */
export interface TopicPoolDetailResponse {
  detail: TopicPoolItem
  related: TopicPoolItem[]
}

/** AI 摘要生成响应（POST /{item_id}/ai-summary） */
export interface AiSummaryResult {
  success: boolean
  ai_summary: string
  tags: string[]
  token_usage: number
  cached: boolean
  message: string
}

/** 列表响应 */
export interface TopicPoolListResponse {
  items: TopicPoolItem[]
  total: number
  page: number
  size: number
}

/** 统计响应（v6 扩展） */
export interface TopicPoolStats {
  total: number
  favorited: number
  monitor_count: number
  avg_heat_score: number
  platforms: Record<string, number>
  emotions: Record<string, number>
}

/** 抓取响应 */
export interface TopicPoolFetchResponse {
  saved_count: number
  skipped_duplicate: number
  fetched_count: number
  platform: string
  items: TopicPoolItem[]
  error?: string
}

/** 监控抓取结果 */
export interface MonitorFetchResult {
  fetched: number
  new: number
  updated: number
  skipped: number
  failed: number
}

/** 平台信息（复用 /api/search/platforms） */
export interface PlatformInfo {
  name: string
  label: string
  desc: string
  is_default: boolean
}

export const topicPoolApi = {
  /** 列表查询 GET /api/topic-pool */
  async list(params: {
    platform?: string
    keyword?: string
    favorited_only?: boolean
    auto_source?: 'manual' | 'monitor'
    emotion?: string
    scene?: string
    visual?: string
    sort?: 'created_desc' | 'heat_desc'
    page?: number
    size?: number
  } = {}): Promise<TopicPoolListResponse> {
    const resp: any = await apiClient.get('/topic-pool', { params })
    return (resp?.data ?? resp) as TopicPoolListResponse
  },

  /** 统计 GET /api/topic-pool/stats */
  async getStats(): Promise<TopicPoolStats> {
    const resp: any = await apiClient.get('/topic-pool/stats')
    return (resp?.data ?? resp) as TopicPoolStats
  },

  /** 主动抓取 POST /api/topic-pool/fetch */
  async fetch(params: {
    keyword: string
    platform: string
    limit?: number
  }): Promise<TopicPoolFetchResponse> {
    const resp: any = await apiClient.post('/topic-pool/fetch', params, {
      timeout: 90000,
    })
    return (resp?.data ?? resp) as TopicPoolFetchResponse
  },

  /** 手动触发监控抓取 POST /api/topic-pool/monitor/fetch */
  async monitorFetch(): Promise<{ success: boolean; result: MonitorFetchResult }> {
    const resp: any = await apiClient.post('/topic-pool/monitor/fetch', {}, { timeout: 60000 })
    return (resp?.data ?? resp) as { success: boolean; result: MonitorFetchResult }
  },

  /** 获取可用平台列表 GET /api/search/platforms */
  async getPlatforms(): Promise<PlatformInfo[]> {
    const resp: any = await apiClient.get('/search/platforms')
    return (resp?.data ?? resp) as PlatformInfo[]
  },

  /** 推荐：基于用户常搜关键词返回热点 GET /api/topic-pool/recommended */
  async recommended(limit: number = 10): Promise<{ items: TopicPoolItem[]; total: number; keywords: string[] }> {
    const resp: any = await apiClient.get('/topic-pool/recommended', { params: { limit } })
    return (resp?.data ?? resp) as { items: TopicPoolItem[]; total: number; keywords: string[] }
  },

  /** 切换收藏 POST /api/topic-pool/{id}/favorite */
  async toggleFavorite(itemId: string): Promise<{ success: boolean; is_favorited: boolean }> {
    const resp: any = await apiClient.post(`/topic-pool/${itemId}/favorite`)
    return (resp?.data ?? resp) as { success: boolean; is_favorited: boolean }
  },

  /** 删除 DELETE /api/topic-pool/{id} */
  async deleteItem(itemId: string): Promise<{ success: boolean }> {
    const resp: any = await apiClient.delete(`/topic-pool/${itemId}`)
    return (resp?.data ?? resp) as { success: boolean }
  },

  /** 详情 GET /api/topic-pool/{id}（含完整 content/raw + 关联推荐，自增 view_count） */
  async getDetail(itemId: string, relatedLimit: number = 8): Promise<TopicPoolDetailResponse> {
    const resp: any = await apiClient.get(`/topic-pool/${itemId}`, {
      params: { related_limit: relatedLimit },
    })
    return (resp?.data ?? resp) as TopicPoolDetailResponse
  },

  /** AI 摘要生成 POST /api/topic-pool/{id}/ai-summary
   * force=false（默认）有缓存用缓存不消耗 token；force=true 强制重新生成
   */
  async generateAiSummary(itemId: string, force: boolean = false): Promise<AiSummaryResult> {
    const resp: any = await apiClient.post(`/topic-pool/${itemId}/ai-summary`, null, {
      params: { force },
      timeout: 60000,
    })
    return (resp?.data ?? resp) as AiSummaryResult
  },
}
