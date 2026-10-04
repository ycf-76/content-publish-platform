import apiClient from './client'

export interface DashboardSummary {
  total_reads: number
  total_interactions: number
  total_count: number
  collected_count: number
  hot_count: number
  avg_engagement_rate: number
}

export interface DailyTrendItem {
  date: string
  interactions: number
  count: number
}

export interface PlatformAccountInfo {
  platform: string
  platform_label: string
  platform_nickname: string | null
  platform_avatar_url: string | null
  fans_count: number
  works_count: number
  last_synced_at: string | null
  sync_status: string
  bound: boolean
}

export interface PlatformContentStats {
  likes: number
  collects: number
  comments: number
  shares: number
  reads: number
  interactions: number
  count: number
}

export interface DashboardOverview {
  summary: DashboardSummary
  daily_trend: DailyTrendItem[]
  platform_accounts: PlatformAccountInfo[]
  platform_content_stats: Record<string, PlatformContentStats>
  days: number
}

export interface ContentTopItem {
  id: string
  title: string
  cover_img_url: string | null
  platform: string
  published_at: string | null
  collected_at: string | null
  likes: number
  collects: number
  comments: number
  shares: number
  reads: number
  interactions: number
  engagement_rate: number
  is_replicated: boolean
  performance_score: number | null
  content_status: string
}

export interface ContentAnalysis {
  top_items: ContentTopItem[]
  content_type_dist: Record<string, number>
  pattern_ranking: Array<{ name: string; count: number }>
  emotion_ranking: Array<{ name: string; count: number }>
  platform_dist: Record<string, number>
  total: number
}

export interface FollowerAnalysis {
  total_fans: number
  platform_fans: Array<{
    platform: string
    platform_label: string
    fans_count: number
    works_count: number
    nickname: string | null
    avatar_url: string | null
    last_synced_at: string | null
    bound: boolean
  }>
}

export interface PlatformDetail {
  platform: string
  platform_label: string
  summary: {
    total_likes: number
    total_collects: number
    total_comments: number
    total_shares: number
    total_reads: number
    total_interactions: number
    total_count: number
    hot_count: number
    avg_engagement_rate: number
  }
  daily_trend: Array<{ date: string; interactions: number; count: number }>
  top_items: Array<{
    id: string
    title: string
    cover_img_url: string | null
    likes: number
    collects: number
    comments: number
    shares: number
    reads: number
    is_replicated: boolean
    published_at: string | null
  }>
  account_info: {
    nickname: string | null
    fans_count: number
    works_count: number
    last_synced_at: string | null
  } | null
  days: number
}

export async function getDashboardOverview(days = 7): Promise<DashboardOverview> {
  const res = await apiClient.get('/dashboard/overview', { params: { days } })
  return res.data
}

export async function getContentAnalysis(params: {
  platform?: string
  sort_by?: string
  limit?: number
} = {}): Promise<ContentAnalysis> {
  const res = await apiClient.get('/dashboard/content-analysis', { params })
  return res.data
}

export async function getFollowerAnalysis(): Promise<FollowerAnalysis> {
  const res = await apiClient.get('/dashboard/follower-analysis')
  return res.data
}

export async function getPlatformDetail(platform: string, days = 7): Promise<PlatformDetail> {
  const res = await apiClient.get(`/dashboard/platform/${platform}`, { params: { days } })
  return res.data
}