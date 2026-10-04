import apiClient from './client'

export interface VideoImageItem {
  type: 'video'
  media_url?: string
  publish_status?: string
  post_id?: string
  message?: string
}

export interface MyWorkItem {
  id: string
  workflow_id: string
  published_note_id: string | null
  topic: string | null
  title: string | null
  cover_img_url: string | null
  images: (string | VideoImageItem)[] | null
  video_url: string
  platform: string
  published_at: string | null
  collected_likes: number | null
  collected_collects: number | null
  collected_comments: number | null
  collected_shares: number | null
  performance_score: number | null
  is_replicated: boolean | null
  predicted_viral_score: number | null
  actual_viral_score: number | null
  prediction_error: number | null
  collected_at: string | null
  content_status: 'draft' | 'published' | 'collected'
  title_pattern: string | null
  emotion_trigger: string | null
  content_structure: string | null
}

export interface MyWorkDetail extends MyWorkItem {
  content_text: string | null
  tags: any
  cover_img_url: string | null
  title_pattern: string | null
  emotion_trigger: string | null
  content_structure: string | null
  selected_pattern: any
  selected_direction: any
  created_at: string | null
}

export interface AttributionResult {
  my_attribution: Record<string, any>
  avoid_patterns: any[]
}

export async function listMyWorks(params: {
  page?: number
  page_size?: number
  platform?: string
  sort_by?: string
  content_status?: string
} = {}): Promise<{ items: MyWorkItem[]; total: number; page: number; page_size: number }> {
  const res = await apiClient.get('/my-works', { params })
  return res.data
}

export async function getMyWorkDetail(recordId: string): Promise<MyWorkDetail> {
  const res = await apiClient.get(`/my-works/${recordId}`)
  return res.data
}

export async function getAttribution(): Promise<AttributionResult> {
  const res = await apiClient.get('/my-works/attribution')
  return res.data
}

export async function collectNoteData(noteUrl: string, platform = 'auto'): Promise<any> {
  const res = await apiClient.post('/my-works/collect', { note_url: noteUrl, platform })
  return res
}

export async function csvImport(records: any[], platform = 'xiaohongshu'): Promise<{ imported: number; errors: number }> {
  const res = await apiClient.post('/my-works/csv-import', { records, platform })
  return res.data
}

export async function deleteMyWork(recordId: string): Promise<void> {
  await apiClient.delete(`/my-works/${recordId}`)
}

export interface AnalysisReport {
  status: string
  confidence: string
  sample_size: number
  my_weight: number
  overview: {
    total: number
    high_performers: number
    low_performers: number
    replicated: number
    total_likes: number
    total_collects: number
    total_comments: number
    avg_score: number
  }
  platform_comparison: {
    platform: string
    count: number
    avg_score: number
    replicated_rate: number
    total_likes: number
    total_collects: number
  }[]
  pattern_ranking: { name: string; avg_score: number; count: number }[]
  emotion_ranking: { name: string; avg_score: number; count: number }[]
  structure_ranking: { name: string; avg_score: number; count: number }[]
  top_performers: { id: string; title: string | null; platform: string | null; score: number; likes: number | null; collects: number | null; comments: number | null; cover_img_url: string | null }[]
  writing_prescription: Record<string, any>
  avoid_patterns: any
  action_items: { priority: string; action: string; reason: string }[]
}

export async function getAnalysisReport(platform?: string): Promise<AnalysisReport> {
  const res = await apiClient.get('/my-works/analysis-report', { params: platform ? { platform } : {} })
  return res.data
}

export async function triggerAttribution(): Promise<any> {
  const res = await apiClient.post('/my-works/trigger-attribution')
  return res
}

export async function createDraft(title = '未命名草稿', platform = 'xiaohongshu', topic?: string): Promise<{ id: string; title: string; platform: string; content_status: string }> {
  const res = await apiClient.post('/my-works/draft', { title, platform, topic })
  return res.data
}

export async function updateContentStatus(recordId: string, contentStatus: 'draft' | 'published' | 'collected'): Promise<{ id: string; content_status: string }> {
  const res = await apiClient.patch(`/my-works/${recordId}/status`, { content_status: contentStatus })
  return res.data
}

export async function refreshWorkImages(recordId: string): Promise<{ id: string; status: string; cover_img_url?: string }> {
  const res = await apiClient.post(`/my-works/${recordId}/refresh-images`)
  return res.data
}