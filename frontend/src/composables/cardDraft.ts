/**
 * cardDraft 统一处理工具
 *
 * 背景：对话式创作中后端可能返回非常完整的卡片数据（compare/steps/timeline/
 * stat_card/image_page 等字段），但 ChatView、useChatSSE 过去只保留
 * type/title/imageUrl/htmlUrl，导致编辑器无法继承组件级内容，也无法做
 * 单页改版和重新生成。这里统一保留完整字段，仅补齐缺失字段。
 */
import type { CardPage } from '@/card-editor/templates'

export interface CardDraftPayload {
  title?: string
  template?: string
  pages?: any[]
  pngUrls?: string[]
  htmlUrls?: string[]
  [key: string]: any
}

export interface NormalizedCardDraft {
  title?: string
  template?: string
  pages: Array<Partial<CardPage> & { type: string; htmlContent?: string }>
  pngUrls: string[]
  htmlUrls: string[]
}

function makeId(): string {
  return `page_${Math.random().toString(36).slice(2, 10)}`
}

/** 保留页面所有字段，只补齐 id / type / title 等基础字段 */
export function normalizeDraftPages(pages: any[] = []): Array<Partial<CardPage> & { type: string; htmlContent?: string }> {
  return (pages || []).map((page: any) => ({
    ...(page || {}),
    id: page?.id || makeId(),
    type: page?.type || 'content',
    title: page?.title || '',
  }))
}

/** 统一处理后端 card_draft / _card_draft 结构，避免各页面重复裁剪字段 */
export function normalizeCardDraft(cardDraft: CardDraftPayload | null | undefined): NormalizedCardDraft {
  const source = cardDraft || {}
  return {
    title: source.title,
    template: source.template,
    pages: normalizeDraftPages(source.pages || []),
    pngUrls: source.pngUrls || [],
    htmlUrls: source.htmlUrls || [],
  }
}

/** 从页面列表中推断封面图：优先第一张真实图片 */
export function pickCoverUrl(pages: any[], pngUrls: string[] = []): string {
  const withImage = (pages || []).find((p: any) => p?.imageUrl)
  if (withImage?.imageUrl) return withImage.imageUrl
  return pngUrls?.[0] || ''
}

/** 最终写入 work.images 的图片列表 */
export function pickImages(pages: any[], pngUrls: string[] = []): string[] {
  if (pngUrls && pngUrls.length > 0) return pngUrls
  return (pages || [])
    .map((p: any) => p?.imageUrl)
    .filter(Boolean) as string[]
}