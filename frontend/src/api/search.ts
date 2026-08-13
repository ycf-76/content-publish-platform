import apiClient from './client'

/** 搜索平台信息（对齐后端 /api/search/platforms） */
export interface SearchPlatform {
  name: string         // 平台标识：builtin / hackernews / reddit / xiaohongshu
  label: string        // 显示名：热门话题 / HackerNews / ...
  desc: string         // 描述
  is_default: boolean  // 是否默认平台
}

/** 搜索结果条目 */
export interface SearchResultItem {
  platform: string
  content_id: string
  title: string
  summary: string
  content?: string
  author: string
  url: string
  likes: number
  comments: number
  shares: number
  views: number
  cover_img: string
  published_at: string
  tags: string[]
}

/** 搜索响应（对齐后端 SearchResponse） */
export interface SearchResponse {
  keyword: string
  platform: string
  count: number
  fallback_used: boolean
  searched_platforms: string[]
  summary: string
  results: SearchResultItem[]
}

export const searchApi = {
  /** 全网搜 / 指定平台搜 GET /api/search
   * platform 为空 = 全网搜（并发所有平台）
   * platform 非空 = 只搜指定平台
   */
  search(keyword: string, platform: string = '', limit: number = 20) {
    return apiClient.get<SearchResponse>('/search', {
      params: { keyword, platform, limit },
    })
  },

  /** 获取可用平台列表 GET /api/search/platforms */
  getPlatforms() {
    return apiClient.get<SearchPlatform[]>('/search/platforms')
  },
}
