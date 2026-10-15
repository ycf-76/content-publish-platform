export type MediaType =
  | 'image'
  | 'html'
  | 'audio'
  | 'video'
  | 'chart'
  | 'mindmap'
  | 'structured'

export interface VideoMeta {
  publishStatus?: string
  postId?: string
  message?: string
}

export interface MediaPage {
  id: string
  type: string
  mediaType: MediaType
  title?: string
  width: number
  height: number
  imageUrl?: string
  htmlContent?: string
  audioUrl?: string
  videoUrl?: string
  videoMeta?: VideoMeta
  [key: string]: unknown
}