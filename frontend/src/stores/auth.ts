import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { authApi, type LoginRequest, type UserInfo } from '@/api/auth'

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(localStorage.getItem('token'))
  const user = ref<UserInfo | null>(null)
  const isLoading = ref(false)
  const error = ref<string | null>(null)

  const isAuthenticated = computed(() => !!token.value)

  async function login(email: string, password: string) {
    try {
      isLoading.value = true
      error.value = null

      const response = await authApi.login({ email, password })
      
      token.value = response.data.token
      user.value = {
        ...response.data.user,
        created_at: new Date().toISOString()
      }
      
      localStorage.setItem('token', response.data.token)
      
      return response.data
    } catch (e: any) {
      error.value = e.response?.data?.message || '登录失败'
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
      error.value = e.response?.data?.message || '获取用户信息失败'
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
    login,
    logout,
    fetchCurrentUser,
    clearError
  }
})