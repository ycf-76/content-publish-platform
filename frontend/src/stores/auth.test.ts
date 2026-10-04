import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useAuthStore } from './auth'
import { authApi } from '@/api/auth'

vi.mock('@/api/auth', () => ({
  authApi: {
    emailLogin: vi.fn(),
    logout: vi.fn(),
    getCurrentUser: vi.fn(),
    createSseSession: vi.fn(),
  },
}))

describe('useAuthStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    vi.clearAllMocks()
  })

  describe('initial state', () => {
    it('should not be authenticated when no token in localStorage', () => {
      const store = useAuthStore()
      expect(store.isAuthenticated).toBe(false)
      expect(store.token).toBeNull()
      expect(store.user).toBeNull()
    })

    it('should be authenticated when token exists in localStorage', () => {
      localStorage.setItem('token', 'test-token')
      const store = useAuthStore()
      expect(store.isAuthenticated).toBe(true)
      expect(store.token).toBe('test-token')
    })

    it('should restore user info from localStorage', () => {
      localStorage.setItem('token', 'test-token')
      localStorage.setItem('mint_user_info', JSON.stringify({
        user_id: 'u1',
        nickname: 'Test',
        has_xhs_auth: false,
      }))
      const store = useAuthStore()
      expect(store.user?.nickname).toBe('Test')
    })
  })

  describe('hasXhsAuth', () => {
    it('should return true when user has xhs auth', () => {
      localStorage.setItem('token', 'test-token')
      const store = useAuthStore()
      store.$patch({
        user: {
          user_id: 'u1',
                    nickname: 'Test',
          avatar_url: '',
          has_xhs_auth: true,
          login_method: 'email',
        },
      })
      expect(store.hasXhsAuth).toBe(true)
    })

    it('should return false when user has no xhs auth', () => {
      localStorage.setItem('token', 'test-token')
      const store = useAuthStore()
      store.$patch({
        user: {
          user_id: 'u1',
                    nickname: 'Test',
          avatar_url: '',
          has_xhs_auth: false,
          login_method: 'email',
        },
      })
      expect(store.hasXhsAuth).toBe(false)
    })
  })

  describe('emailLogin', () => {
    it('should set token and user on successful login', async () => {
      const mockResponse = {
        data: {
          token: 'jwt-token-123',
          user_id: 'u1',
                    nickname: 'TestUser',
          avatar_url: 'https://avatar.url',
          has_xhs_auth: false,
          login_method: 'email',
        },
      }
      vi.mocked(authApi.emailLogin).mockResolvedValue(mockResponse as any)

      const store = useAuthStore()
      await store.emailLogin('test@example.com', '123456')

      expect(store.token).toBe('jwt-token-123')
      expect(store.user?.nickname).toBe('TestUser')
      expect(store.isAuthenticated).toBe(true)
      expect(localStorage.getItem('token')).toBe('jwt-token-123')
    })

    it('should set error on failed login', async () => {
      vi.mocked(authApi.emailLogin).mockRejectedValue({
        response: { data: { detail: '验证码错误' } },
      })

      const store = useAuthStore()
      await expect(store.emailLogin('test@example.com', 'wrong')).rejects.toThrow()
      expect(store.error).toBe('验证码错误')
      expect(store.isAuthenticated).toBe(false)
    })

    it('should clear error before new login attempt', async () => {
      vi.mocked(authApi.emailLogin).mockRejectedValue({
        response: { data: { detail: '验证码错误' } },
      })

      const store = useAuthStore()
      await expect(store.emailLogin('test@example.com', 'wrong')).rejects.toThrow()
      expect(store.error).toBe('验证码错误')

      vi.mocked(authApi.emailLogin).mockResolvedValue({
        data: {
          token: 'new-token',
          user_id: 'u2',
          nickname: 'NewUser',
          avatar_url: '',
          has_xhs_auth: false,
          login_method: 'email',
        },
      } as any)

      await store.emailLogin('test@example.com', 'correct')
      expect(store.error).toBeNull()
    })
  })

  describe('logout', () => {
    it('should clear token and user on logout', async () => {
      localStorage.setItem('token', 'test-token')
      localStorage.setItem('refresh_token', 'refresh-token')

      const store = useAuthStore()
      store.$patch({
        token: 'test-token',
        user: {
          user_id: 'u1',
          nickname: 'Test',
          avatar_url: '',
          has_xhs_auth: false,
          login_method: 'email',
        },
      })

      await store.logout()

      expect(store.token).toBeNull()
      expect(store.user).toBeNull()
      expect(localStorage.getItem('token')).toBeNull()
      expect(localStorage.getItem('refresh_token')).toBeNull()
    })

    it('should clear local state even if API call fails', async () => {
      vi.mocked(authApi.logout).mockRejectedValue(new Error('Network error'))
      localStorage.setItem('token', 'test-token')

      const store = useAuthStore()
      store.$patch({ token: 'test-token' })

      await store.logout()

      expect(store.token).toBeNull()
      expect(localStorage.getItem('token')).toBeNull()
    })
  })

  describe('fetchCurrentUser', () => {
    it('should return null if no token', async () => {
      const store = useAuthStore()
      const result = await store.fetchCurrentUser()
      expect(result).toBeNull()
    })

    it('should set user on successful fetch', async () => {
      localStorage.setItem('token', 'test-token')
      const mockUser = {
        user_id: 'u1',
        nickname: 'FetchedUser',
        avatar_url: '',
        has_xhs_auth: true,
        login_method: 'qr',
      }
      vi.mocked(authApi.getCurrentUser).mockResolvedValue({ data: mockUser } as any)

      const store = useAuthStore()
      const result = await store.fetchCurrentUser()

      expect(store.user?.nickname).toBe('FetchedUser')
      expect(result?.nickname).toBe('FetchedUser')
    })
  })

  describe('clearError', () => {
    it('should clear error', () => {
      const store = useAuthStore()
      store.$patch({ error: 'Some error' })
      store.clearError()
      expect(store.error).toBeNull()
    })
  })
})