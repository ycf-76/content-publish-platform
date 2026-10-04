import type { ContentPack, PlatformAdapter, PlatformPayload, PlatformPublishResult, TargetPlatform } from '@/types'
import { authFetch } from '@/api/client'

interface WeiboPayload extends PlatformPayload {
  platform: 'weibo'
  content: string
  images_base64: string[]
}

export class WeiboAdapter implements PlatformAdapter {
  platform: TargetPlatform = 'weibo'

  async transform(pack: ContentPack): Promise<WeiboPayload> {
    const title = pack.copy.title
    const tags = pack.copy.tags.length > 0
      ? ' ' + pack.copy.tags.map(t => `#${t}#`).join(' ')
      : ''
    const content = `${title}\n\n${pack.copy.body}${tags}`

    const imagesBase64 = pack.images.map(img => {
      if (img.base64) return img.base64
      if (img.url.startsWith('data:')) {
        return img.url.replace(/^data:image\/[a-z]+;base64,/, '')
      }
      return ''
    }).filter(Boolean)

    return {
      platform: 'weibo',
      content,
      images_base64: imagesBase64,
    }
  }

  async publish(payload: WeiboPayload, accountId: string): Promise<PlatformPublishResult> {
    try {
      const res = await authFetch('/api/workflows/publish/weibo', {
        method: 'POST',
        body: JSON.stringify({
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
        platform: 'weibo',
      }
    } catch (e: any) {
      return {
        success: false,
        message: e.message || '微博发布失败',
        platform: 'weibo',
      }
    }
  }
}