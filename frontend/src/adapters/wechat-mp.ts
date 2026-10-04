import type { ContentPack, PlatformAdapter, PlatformPayload, PlatformPublishResult, TargetPlatform } from '@/types'
import { authFetch } from '@/api/client'

interface WechatMpPayload extends PlatformPayload {
  platform: 'wechat_mp'
  title: string
  content: string
  cover_image_base64?: string
}

export class WechatMpAdapter implements PlatformAdapter {
  platform: TargetPlatform = 'wechat_mp'

  async transform(pack: ContentPack): Promise<WechatMpPayload> {
    const tags = pack.copy.tags.length > 0
      ? '\n\n' + pack.copy.tags.map(t => `#${t}`).join(' ')
      : ''
    const content = pack.copy.body + tags

    const coverImage = pack.images.length > 0
      ? (() => {
          const img = pack.images[0]
          if (img.base64) return img.base64
          if (img.url.startsWith('data:')) {
            return img.url.replace(/^data:image\/[a-z]+;base64,/, '')
          }
          return undefined
        })()
      : undefined

    return {
      platform: 'wechat_mp',
      title: pack.copy.title,
      content,
      cover_image_base64: coverImage,
    }
  }

  async publish(payload: WechatMpPayload, accountId: string): Promise<PlatformPublishResult> {
    try {
      const res = await authFetch('/api/workflows/publish/wechat_mp', {
        method: 'POST',
        body: JSON.stringify({
          title: payload.title,
          content: payload.content,
          cover_image_base64: payload.cover_image_base64,
          account_id: accountId,
        }),
      })
      const data = await res.json()
      return {
        success: data.status === 'success' || !!data.post_id,
        postId: data.post_id,
        message: data.message,
        platform: 'wechat_mp',
      }
    } catch (e: any) {
      return {
        success: false,
        message: e.message || '公众号发布失败',
        platform: 'wechat_mp',
      }
    }
  }
}