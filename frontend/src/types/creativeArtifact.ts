/**
 * CreativeArtifact：统一创作对象的前端类型
 *
 * 与后端 app/services/creative_artifact.py 对应。
 * 目的是让对话式创作、工作流创作、卡片编辑器、审核发布共用同一份上下文，
 * 而不是各自维护一套页面结构。
 */

export interface ArtifactSource {
  work_id?: string
  session_id?: string
  workflow_id?: string
  platform?: string
}

export interface ArtifactAnalysis {
  analysis_id?: string
  source_work_ids?: string[]
  confidence?: number
  keep_patterns?: string[]
  avoid_patterns?: string[]
  evidence?: string[]
}

export interface ArtifactBrief {
  goal?: string
  audience?: string
  tone?: string
  topic?: string
  title?: string
  visual_direction?: string
  template_id?: string
  keep_patterns?: string[]
  avoid_patterns?: string[]
}

export interface PageComponent {
  semantic_type?: string
  page_type?: string
  template_id?: string
  decoration?: string
}

export interface StoryboardPage {
  page_id: string
  index: number
  role: string
  role_label: string
  rationale: string
  source_evidence: string
  visual_goal: string
  component: PageComponent
  image_role: string
  content: Record<string, any>
  image_url: string
  html_url: string
}

export interface QualityIssue {
  code: string
  message: string
  page_index: number
  level: string
}

export interface ArtifactQuality {
  status: string
  score: number
  checks: string[]
  issues: QualityIssue[]
}

export interface ArtifactReview {
  status: string
  feedback: string
  approved_pages: number[]
  rejected_pages: number[]
}

export interface ArtifactHistoryEntry {
  at: number
  action: string
  detail: string
}

export interface CreativeArtifact {
  artifact_id: string
  version: number
  created_at: number
  updated_at: number
  source: ArtifactSource
  analysis: ArtifactAnalysis
  brief: ArtifactBrief
  storyboard: StoryboardPage[]
  assets: Record<string, any>[]
  quality: ArtifactQuality
  review: ArtifactReview
  history: ArtifactHistoryEntry[]
}

export interface ArtifactSummary {
  artifact_id: string
  title: string
  topic: string
  page_count: number
  updated_at: number
  cover_url?: string
  page_images?: string[]
  first_page_html?: string
}

export function emptyArtifact(): CreativeArtifact {
  return {
    artifact_id: '',
    version: 1,
    created_at: 0,
    updated_at: 0,
    source: { platform: 'xiaohongshu' },
    analysis: { keep_patterns: [], avoid_patterns: [], evidence: [] },
    brief: { keep_patterns: [], avoid_patterns: [] },
    storyboard: [],
    assets: [],
    quality: { status: 'pending', score: 0, checks: [], issues: [] },
    review: { status: 'pending', feedback: '', approved_pages: [], rejected_pages: [] },
    history: [],
  }
}