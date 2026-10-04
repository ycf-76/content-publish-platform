import type { ContentPack, PlatformAdapter, PlatformPayload, PlatformPublishResult, TargetPlatform } from '@/types'
import { authFetch } from '@/api/client'

interface XhsPayload extends PlatformPayload {
  platform: 'xiaohongshu'
  title: string
  content: string
  images_base64: string[]
}

export class XiaohongshuAdapter implements PlatformAdapter {
  platform: TargetPlatform = 'xiaohongshu'

  async transform(pack: ContentPack): Promise<XhsPayload> {
    const tags = pack.copy.tags.length > 0
      ? '\n\n' + pack.copy.tags.map(t => `#${t}`).join(' ')
      : ''

    const imagesBase64 = pack.images.map(img => {
      if (img.base64) return img.base64
      if (img.url.startsWith('data:')) {
        return img.url.replace(/^data:image\/[a-z]+;base64,/, '')
      }
      return ''
    }).filter(Boolean)

    return {
      platform: 'xiaohongshu',
      title: pack.copy.title,
      content: pack.copy.body + tags,
      images_base64: imagesBase64,
    }
  }

  async publish(payload: XhsPayload, accountId: string): Promise<PlatformPublishResult> {
    try {
      const res = await authFetch('/api/workflows/publish', {
        method: 'POST',
        body: JSON.stringify({
          title: payload.title,
          content: payload.content,
          images_base64: payload.images_base64,
          account_id: accountId,
        }),
      })
      const data = await res.json()
      return {
        success: data.status === 'success' || !!data.post_id,
        postId: data.post_id,
        message: data.message,
        platform: 'xiaohongshu',
      }
    } catch (e: any) {
      return {
        success: false,
        message: e.message || '发布失败',
        platform: 'xiaohongshu',
      }
    }
  }
}