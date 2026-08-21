import apiClient from './client'

/** 扫码/插件登录返回结构 */
export interface LoginResponse {
  token: string
  refresh_token?: string
  user_id: string
  xhs_user_id: string
  nickname: string
  avatar_url: string
  has_xhs_auth?: boolean
  login_method?: string
}

/** /auth/me 返回的当前用户信息 */
export interface UserInfo {
  user_id: string
  xhs_user_id: string
  nickname: string
  avatar_url: string
  has_xhs_auth: boolean
  login_method?: string
}

export const authApi = {
  /** 扫码登录：扫码确认后自动获取用户信息，签发 JWT（后端需抓取用户信息+cookies，耗时较长） */
  async qrLogin(qrId: string) {
    return await apiClient.post<LoginResponse>('/auth/qr-login', null, {
      params: { qr_id: qrId },
      timeout: 120000,
    })
  },

  /** 扫码登录手动兜底：自动获取失败时用前端提交的 nickname/red_id 登录 */
  async qrLoginManual(qrId: string, nickname: string, redId?: string, avatarUrl?: string) {
    return await apiClient.post<LoginResponse>('/auth/qr-login-manual', null, {
      params: {
        qr_id: qrId,
        nickname,
        red_id: redId,
        avatar_url: avatarUrl
      },
      timeout: 120000,
    })
  },

  /** 登出（JWT 无状态，前端清 token 即可） */
  async logout() {
    return await apiClient.post('/auth/logout')
  },

  /** 获取当前登录用户信息（需 JWT） */
  async getCurrentUser() {
    return await apiClient.get<UserInfo>('/auth/me')
  },

  /** 建立 SSE cookie session（后端 set-cookie sse_token） */
  async createSseSession() {
    return await apiClient.post('/auth/sse-session')
  },

  /** 发送邮箱验证码 */
  async sendEmailCode(email: string) {
    return await apiClient.post('/auth/send-email-code', null, {
      params: { email },
    })
  },

  /** 邮箱验证码登录 */
  async emailLogin(email: string, code: string) {
    return await apiClient.post<LoginResponse>('/auth/email-login', null, {
      params: { email, code },
    })
  },
}

// ===== Token 存储工具（登录成功后调用） =====
const TOKEN_KEY = 'token'
const USER_KEY = 'mint_user_info'

export function saveLogin(data: LoginResponse) {
  localStorage.setItem(TOKEN_KEY, data.token)
  if (data.refresh_token) {
    localStorage.setItem('refresh_token', data.refresh_token)
  }
  localStorage.setItem(USER_KEY, JSON.stringify({
    user_id: data.user_id,
    xhs_user_id: data.xhs_user_id,
    nickname: data.nickname,
    avatar_url: data.avatar_url,
    has_xhs_auth: data.has_xhs_auth ?? !!data.xhs_user_id,
    login_method: data.login_method || '',
  }))
}

export function clearLogin() {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem('refresh_token')
  localStorage.removeItem(USER_KEY)
}

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function isLoggedIn(): boolean {
  return !!localStorage.getItem(TOKEN_KEY)
}