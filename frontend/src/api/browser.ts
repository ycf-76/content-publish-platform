import apiClient from './client'

export interface BrowserViewEvent {
  url: string
  title: string
  screenshot_base64: string
  elements: BrowserElement[]
}

export interface BrowserElement {
  ref: string
  tag: string
  name?: string
  text?: string
  type?: string
  role?: string
}

export interface BrowserDomainInfo {
  allowed: string[]
  temp_allowed: Record<string, number>
}

export async function getBrowserDomains(): Promise<BrowserDomainInfo> {
  return await apiClient.get('/browser/domains') as any
}

export async function allowDomain(domain: string, ttlMinutes = 60): Promise<void> {
  await apiClient.post('/browser/domains', {
    domain,
    ttl_minutes: ttlMinutes,
    user_confirmed: true,
  })
}

export async function takeBrowserScreenshot(fullPage = false): Promise<BrowserViewEvent> {
  return await apiClient.post('/browser/screenshot', { full_page: fullPage }) as any
}

export interface BrowserInteractResult {
  ok: boolean
  url?: string
  screenshot_base64?: string
  error?: string
}

export async function browserInteractApi(action: string, data: any): Promise<BrowserInteractResult> {
  return await apiClient.post('/browser/interact', { action, ...data }) as any
}

export interface NavigateResult {
  ok: boolean
  url?: string
  title?: string
  screenshot_base64?: string
  error?: string
}

export async function browserNavigate(url: string): Promise<NavigateResult> {
  return await apiClient.post('/browser/navigate', { url }) as any
}

export interface PublishNavigateResult {
  ok: boolean
  platform?: string
  url?: string
  title?: string
  screenshot_base64?: string
  error?: string
}

export async function publishNavigate(platform: string): Promise<PublishNavigateResult> {
  return await apiClient.post('/browser/publish/navigate', { platform }) as any
}

export interface PublishSubmitResult {
  ok: boolean
  platform?: string
  status?: 'awaiting_manual' | 'submitted' | 'failed'
  message?: string
  screenshot_base64?: string
  url?: string
  error?: string
}

export async function publishSubmit(params: {
  platform: string
  title: string
  content: string
  tags?: string[]
  images_base64?: string[]
  images_urls?: string[]
  auto_submit?: boolean
}): Promise<PublishSubmitResult> {
  return await apiClient.post('/browser/publish/submit', {
    platform: params.platform,
    title: params.title,
    content: params.content,
    tags: params.tags || [],
    images_base64: params.images_base64 || [],
    images_urls: params.images_urls || [],
    auto_submit: params.auto_submit || false,
  }) as any
}

export interface PublishCheckResult {
  ok: boolean
  platform?: string
  published?: boolean
  failed?: boolean
  url?: string
  title?: string
  screenshot_base64?: string
  error?: string
}

export async function publishCheck(platform: string, workId: string): Promise<PublishCheckResult> {
  return await apiClient.post('/browser/publish/check', { platform, work_id: workId }) as any
}