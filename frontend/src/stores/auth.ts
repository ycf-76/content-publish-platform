import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { authApi, type UserInfo } from '@/api/auth'

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(localStorage.getItem('token'))
  const user = ref<UserInfo | null>(null)
  const isLoading = ref(false)
  const error = ref<string | null>(null)

  const hasXhsAuth = computed(() => !!user.value?.has_xhs_auth)

  const isAuthenticated = computed(() => !!token.value)

  if (token.value && !user.value) {
    try {
      const raw = localStorage.getItem('mint_user_info')
      if (raw) user.value = JSON.parse(raw)
    } catch { /* ignore */ }
  }

  async function emailLogin(email: string, code: string) {
    try {
      isLoading.value = true
      error.value = null

      const response = await authApi.emailLogin(email, code)

      token.value = response.data.token
      user.value = {
        user_id: response.data.user_id,
        xhs_user_id: response.data.xhs_user_id,
        nickname: response.data.nickname,
        avatar_url: response.data.avatar_url,
        has_xhs_auth: response.data.has_xhs_auth ?? !!response.data.xhs_user_id,
        login_method: response.data.login_method || 'email',
      }

      localStorage.setItem('token', response.data.token)
      if (response.data.refresh_token) {
        localStorage.setItem('refresh_token', response.data.refresh_token)
      }

      return response.data
    } catch (e: any) {
      error.value = e.response?.data?.detail || e.response?.data?.message || '登录失败'
      throw e
    } finally {
      isLoading.value = false
    }
  }

  async function logout() {
    try {
      await authApi.logout()
    } catch (e) {
      console.error('Logout error:', e)
    } finally {
      token.value = null
      user.value = null
      localStorage.removeItem('token')
      localStorage.removeItem('refresh_token')
    }
  }

  async function fetchCurrentUser() {
    if (!token.value) return null

    try {
      isLoading.value = true
      const response = await authApi.getCurrentUser()
      user.value = response.data
      return response.data
    } catch (e: any) {
      error.value = e.response?.data?.detail || e.response?.data?.message || '获取用户信息失败'
      throw e
    } finally {
      isLoading.value = false
    }
  }

  function clearError() {
    error.value = null
  }

  return {
    token,
    user,
    isLoading,
    error,
    isAuthenticated,
    hasXhsAuth,
    emailLogin,
    logout,
    fetchCurrentUser,
    clearError
  }
})