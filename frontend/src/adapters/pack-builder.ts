import type { ContentPack, ContentImage, ContentCopy, CreationMode, TargetPlatform } from '@/types'
import type { CardPage, TextOverlayBlock } from '@/card-editor/templates'

export function buildContentPack(opts: {
  images: Array<{ base64?: string; url?: string; overlays?: TextOverlayBlock[] }>
  title: string
  body: string
  tags: string[]
  mode: CreationMode
  targetPlatforms: TargetPlatform[]
  cardPages?: CardPage[]
  category?: string
  workflowId?: string
}): ContentPack {
  const contentImages: ContentImage[] = opts.images.map((img, i) => ({
    url: img.url || `image_${i}`,
    base64: img.base64,
    overlays: img.overlays?.map(o => ({
      id: o.id,
      text: o.text,
      x: o.x,
      y: o.y,
      width: o.width,
      fontSize: o.fontSize,
      color: o.color,
      fontWeight: o.fontWeight,
      textAlign: o.textAlign,
      lineHeight: o.lineHeight,
      backgroundColor: o.backgroundColor,
      borderRadius: o.borderRadius,
      padding: o.padding,
      letterSpacing: o.letterSpacing,
      textShadow: o.textShadow,
    })),
  }))

  const copy: ContentCopy = {
    title: opts.title,
    body: opts.body,
    tags: opts.tags,
  }

  return {
    images: contentImages,
    copy,
    cardPages: opts.cardPages,
    meta: {
      mode: opts.mode,
      category: opts.category,
      targetPlatforms: opts.targetPlatforms,
      sourceWorkflowId: opts.workflowId,
    },
  }
}

export function buildFromAiWorkflow(opts: {
  imagesBase64: string[]
  title: string
  content: string
  tags: string[]
  workflowId?: string
}): ContentPack {
  return buildContentPack({
    images: opts.imagesBase64.map(b64 => ({ base64: b64 })),
    title: opts.title,
    body: opts.content,
    tags: opts.tags,
    mode: 'ai_full',
    targetPlatforms: ['xiaohongshu'],
    workflowId: opts.workflowId,
  })
}

export function buildFromTemplateOverlay(opts: {
  imageUrl: string
  imageBase64?: string
  overlays: TextOverlayBlock[]
  title: string
  body: string
  tags: string[]
  targetPlatforms?: TargetPlatform[]
}): ContentPack {
  return buildContentPack({
    images: [{ url: opts.imageUrl, base64: opts.imageBase64, overlays: opts.overlays }],
    title: opts.title,
    body: opts.body,
    tags: opts.tags,
    mode: 'template_overlay',
    targetPlatforms: opts.targetPlatforms || ['xiaohongshu'],
  })
}

export function buildFromDirect(opts: {
  imageUrls: string[]
  title: string
  body: string
  tags: string[]
  targetPlatforms?: TargetPlatform[]
}): ContentPack {
  return buildContentPack({
    images: opts.imageUrls.map(url => ({ url })),
    title: opts.title,
    body: opts.body,
    tags: opts.tags,
    mode: 'direct',
    targetPlatforms: opts.targetPlatforms || ['xiaohongshu'],
  })
}