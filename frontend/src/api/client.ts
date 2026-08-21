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
        sessionStorage.setItem('redirect_after_login', window.location.pathname + window.location.search)
        window.location.href = '/login'
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
        sessionStorage.setItem('redirect_after_login', window.location.pathname + window.location.search)
        window.location.href = '/login'
        return Promise.reject(refreshError)
      } finally {
        _isRefreshing = false
      }
    }

    return Promise.reject(error)
  }
)

export default apiClient