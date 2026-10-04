import axios from 'axios'

const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api',
  timeout: 30000,
  withCredentials: true,
  headers: {
    'Content-Type': 'application/json'
  },
  maxContentLength: 100 * 1024 * 1024,
  maxBodyLength: 100 * 1024 * 1024,
})

const AUTH_FREE_PATHS = [
  '/auth/email-login',
  '/auth/send-email-code',
  '/auth/qr-login',
  '/auth/qr-login-manual',
  '/auth/register',
]

apiClient.interceptors.request.use(
  (config) => {
    const url = config.url || ''
    const isAuthFree = AUTH_FREE_PATHS.some((p) => url.startsWith(p))
    if (!isAuthFree) {
      const token = localStorage.getItem('token')
      if (token) {
        config.headers.Authorization = `Bearer ${token}`
      }
    }
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

let _isRefreshing = false
let _refreshSubscribers: Array<(token: string) => void> = []

function _onTokenRefreshed(token: string) {
  _refreshSubscribers.forEach((cb) => cb(token))
  _refreshSubscribers = []
}

function _addRefreshSubscriber(cb: (token: string) => void) {
  _refreshSubscribers.push(cb)
}

apiClient.interceptors.response.use(
  (response) => {
    return response.data
  },
  async (error) => {
    const originalRequest = error.config

    if (error.response?.status === 401 && !originalRequest._retry) {
      const isOnLoginPage = window.location.pathname === '/login'

      if (isOnLoginPage) {
        localStorage.removeItem('token')
        localStorage.removeItem('refresh_token')
        return Promise.reject(error)
      }

      const refreshToken = localStorage.getItem('refresh_token')

      if (!refreshToken) {
        localStorage.removeItem('token')
        // DEV: 登录验证已暂停，401 不跳登录页
        return Promise.reject(error)
      }

      if (_isRefreshing) {
        return new Promise((resolve) => {
          _addRefreshSubscriber((newToken: string) => {
            originalRequest.headers.Authorization = `Bearer ${newToken}`
            resolve(apiClient(originalRequest))
          })
        })
      }

      originalRequest._retry = true
      _isRefreshing = true

      try {
        const resp = await axios.post(
          `${apiClient.defaults.baseURL}/auth/refresh`,
          null,
          { params: { refresh_token: refreshToken } }
        )
        const data = resp.data?.data || resp.data
        const newToken = data.token
        const newRefresh = data.refresh_token

        localStorage.setItem('token', newToken)
        if (newRefresh) {
          localStorage.setItem('refresh_token', newRefresh)
        }

        _onTokenRefreshed(newToken)

        originalRequest.headers.Authorization = `Bearer ${newToken}`
        return apiClient(originalRequest)
      } catch (refreshError) {
        localStorage.removeItem('token')
        localStorage.removeItem('refresh_token')
        // DEV: 登录验证已暂停，refresh 失败不跳登录页
        return Promise.reject(refreshError)
      } finally {
        _isRefreshing = false
      }
    }

    return Promise.reject(error)
  }
)

export default apiClient

let _fetchIsRefreshing = false
let _fetchRefreshSubscribers: Array<(token: string) => void> = []

function _fetchOnTokenRefreshed(token: string) {
  _fetchRefreshSubscribers.forEach((cb) => cb(token))
  _fetchRefreshSubscribers = []
}

function _fetchAddRefreshSubscriber(cb: (token: string) => void) {
  _fetchRefreshSubscribers.push(cb)
}

export async function tryRefreshToken(): Promise<string | null> {
  const refreshToken = localStorage.getItem('refresh_token')
  if (!refreshToken) return null

  if (_fetchIsRefreshing) {
    return new Promise((resolve) => {
      _fetchAddRefreshSubscriber((newToken: string) => resolve(newToken))
    })
  }

  _fetchIsRefreshing = true
  try {
    const baseURL = import.meta.env.VITE_API_BASE_URL || '/api'
    const resp = await axios.post(`${baseURL}/auth/refresh`, null, {
      params: { refresh_token: refreshToken },
    })
    const data = resp.data?.data || resp.data
    const newToken = data.token
    const newRefresh = data.refresh_token

    localStorage.setItem('token', newToken)
    if (newRefresh) localStorage.setItem('refresh_token', newRefresh)

    _fetchOnTokenRefreshed(newToken)
    return newToken
  } catch {
    localStorage.removeItem('token')
    localStorage.removeItem('refresh_token')
    // DEV: 登录验证已暂停，refresh 失败不跳登录页
    return null
  } finally {
    _fetchIsRefreshing = false
  }
}

export async function authFetch(input: string, init?: RequestInit): Promise<Response> {
  const token = localStorage.getItem('token')
  const headers = new Headers(init?.headers)
  if (token) headers.set('Authorization', `Bearer ${token}`)
  if (!headers.has('Content-Type')) headers.set('Content-Type', 'application/json')

  const response = await fetch(input, { ...init, headers })

  if (response.status === 401) {
    const newToken = await tryRefreshToken()
    if (newToken) {
      headers.set('Authorization', `Bearer ${newToken}`)
      return fetch(input, { ...init, headers })
    }
  }

  return response
}