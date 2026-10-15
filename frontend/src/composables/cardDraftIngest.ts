import { normalizeCardDraft, pickCoverUrl, pickImages, type NormalizedCardDraft } from './cardDraft'
import type { MediaType } from '@/types/media-content'

export interface IngestOptions {
  pngUrls?: string[]
  htmlUrls?: string[]
}

export interface IngestResult {
  normalized: NormalizedCardDraft
  coverUrl: string
  images: string[]
}

export function inferMediaType(page: any): MediaType {
  if (page.mediaType) return page.mediaType as MediaType

  if (page.schema_version || page.deck) return 'structured'
  if (page.imageUrl) return 'image'
  if (page.audioUrl) return 'audio'
  if (page.videoUrl) return 'video'

  if (page.htmlContent) {
    const tpl = (page.template || '').toLowerCase()
    if (tpl.includes('chart') || tpl.includes('echarts')) return 'chart'
    if (tpl.includes('mindmap') || tpl.includes('markmap')) return 'mindmap'
    if (tpl.includes('tts') || tpl.includes('audio')) return 'audio'

    const html = page.htmlContent
    if (html.includes('<audio') || html.includes('audio/mpeg')) return 'audio'
    if (html.includes('echarts') || html.includes('ECharts')) return 'chart'
    if (html.includes('markmap') || html.includes('mindmap')) return 'mindmap'

    return 'html'
  }

  return 'html'
}

export function videoResultToCardDraft(videoResult: any): any {
  const videoUrl = videoResult?.media_url || videoResult?.asset_url || videoResult?.video_url
  if (!videoUrl) return null
  return {
    title: videoResult.title || '视频',
    template: 'video',
    pages: [{
      id: 'page_video',
      type: 'content',
      mediaType: 'video',
      title: videoResult.title || '视频',
      videoUrl,
      videoMeta: {
        publishStatus: videoResult.publish_status,
        postId: videoResult.post_id,
        message: videoResult.message,
      },
      width: 1280,
      height: 720,
    }],
    pngUrls: [],
    htmlUrls: [],
  }
}

export async function ingestCardDraft(
  cardDraftRaw: any,
  meta: any | undefined,
  options?: IngestOptions,
): Promise<IngestResult> {
  const normalized = normalizeCardDraft(cardDraftRaw)
  const pngUrls = options?.pngUrls?.length ? options.pngUrls : normalized.pngUrls
  const htmlUrls = options?.htmlUrls?.length ? options.htmlUrls : normalized.htmlUrls
  normalized.pngUrls = pngUrls
  normalized.htmlUrls = htmlUrls

  for (const page of normalized.pages) {
    if (!(page as any).mediaType) {
      (page as any).mediaType = inferMediaType(page)
    }
  }

  const coverUrl = pickCoverUrl(normalized.pages, pngUrls)
  const images = pickImages(normalized.pages, pngUrls)

  try {
    const { useWorkStore } = await import('@/stores/work')
    const workStore = useWorkStore()
    const firstPageHtml = workStore.extractFirstPageHtml(normalized)
    let activeWork = workStore.activeWork
    const videoPage = normalized.pages.find((p: any) => p?.mediaType === 'video' && p?.videoUrl)
    const videoUrl = videoPage ? (videoPage as any).videoUrl : undefined
    const contentType = videoUrl ? 'short_video' : undefined
    if (activeWork && activeWork.isDraft) {
      const updates: Record<string, any> = {
        cardDraft: normalized,
        coverUrl: coverUrl || activeWork.coverUrl,
        images,
        firstPageHtml,
      }
      if (videoUrl) updates.videoUrl = videoUrl
      if (contentType) updates.contentType = contentType
      workStore.updateDraft(activeWork.id, updates)
    } else {
      workStore.saveCardAsDraft(normalized, normalized.title, coverUrl, images)
    }
  } catch {}

  if (meta) {
    meta.cardDraft = normalized
  }

  return { normalized, coverUrl, images }
}