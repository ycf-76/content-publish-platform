import type { TargetPlatform, PlatformAdapter } from '@/types'
import { XiaohongshuAdapter } from './xiaohongshu'
import { WeiboAdapter } from './weibo'
import { WechatMpAdapter } from './wechat-mp'

const registry = new Map<TargetPlatform, PlatformAdapter>()

registry.set('xiaohongshu', new XiaohongshuAdapter())
registry.set('weibo', new WeiboAdapter())
registry.set('wechat_mp', new WechatMpAdapter())

export function getAdapter(platform: TargetPlatform): PlatformAdapter | undefined {
  return registry.get(platform)
}

export function registerAdapter(adapter: PlatformAdapter): void {
  registry.set(adapter.platform, adapter)
}

export function availablePlatforms(): TargetPlatform[] {
  return Array.from(registry.keys())
}