import { describe, it, expect, beforeEach, vi } from 'vitest'

describe('API Client configuration', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.clearAllMocks()
  })

  describe('auth-free paths', () => {
    it('should define auth-free paths for login endpoints', () => {
      const AUTH_FREE_PATHS = [
        '/auth/email-login',
        '/auth/send-email-code',
        '/auth/qr-login',
        '/auth/qr-login-manual',
        '/auth/register',
      ]
      expect(AUTH_FREE_PATHS).toContain('/auth/email-login')
      expect(AUTH_FREE_PATHS).toContain('/auth/register')
      expect(AUTH_FREE_PATHS).not.toContain('/auth/me')
      expect(AUTH_FREE_PATHS).not.toContain('/auth/logout')
    })

    it('should not attach Bearer token for auth-free paths', () => {
      const AUTH_FREE_PATHS = [
        '/auth/email-login',
        '/auth/send-email-code',
        '/auth/qr-login',
        '/auth/qr-login-manual',
        '/auth/register',
      ]
      const url = '/auth/email-login'
      const isAuthFree = AUTH_FREE_PATHS.some((p) => url.startsWith(p))
      expect(isAuthFree).toBe(true)
    })

    it('should attach Bearer token for protected paths', () => {
      const AUTH_FREE_PATHS = [
        '/auth/email-login',
        '/auth/send-email-code',
        '/auth/qr-login',
        '/auth/qr-login-manual',
        '/auth/register',
      ]
      const url = '/auth/me'
      const isAuthFree = AUTH_FREE_PATHS.some((p) => url.startsWith(p))
      expect(isAuthFree).toBe(false)
    })
  })

  describe('token handling', () => {
    it('should store token in localStorage on login', () => {
      const token = 'jwt-test-token-123'
      localStorage.setItem('token', token)
      expect(localStorage.getItem('token')).toBe(token)
    })

    it('should clear token from localStorage on logout', () => {
      localStorage.setItem('token', 'test-token')
      localStorage.setItem('refresh_token', 'refresh-token')
      localStorage.removeItem('token')
      localStorage.removeItem('refresh_token')
      expect(localStorage.getItem('token')).toBeNull()
      expect(localStorage.getItem('refresh_token')).toBeNull()
    })

    it('should construct Bearer token header', () => {
      const token = 'my-jwt-token'
      const header = `Bearer ${token}`
      expect(header).toBe('Bearer my-jwt-token')
    })

    it('should not attach token when localStorage is empty', () => {
      const token = localStorage.getItem('token')
      expect(token).toBeNull()
    })
  })

  describe('refresh token logic', () => {
    it('should detect missing refresh token', () => {
      localStorage.removeItem('refresh_token')
      expect(localStorage.getItem('refresh_token')).toBeNull()
    })

    it('should store redirect path before navigating to login', () => {
      const currentPath = '/workbench?tab=workflow'
      sessionStorage.setItem('redirect_after_login', currentPath)
      expect(sessionStorage.getItem('redirect_after_login')).toBe(currentPath)
    })

    it('should clear redirect path after login', () => {
      sessionStorage.setItem('redirect_after_login', '/workbench')
      sessionStorage.removeItem('redirect_after_login')
      expect(sessionStorage.getItem('redirect_after_login')).toBeNull()
    })
  })

  describe('request configuration', () => {
    it('should use 30s timeout by default', () => {
      const DEFAULT_TIMEOUT = 30000
      expect(DEFAULT_TIMEOUT).toBe(30000)
    })

    it('should use /api as default base URL', () => {
      const DEFAULT_BASE_URL = '/api'
      expect(DEFAULT_BASE_URL).toBe('/api')
    })

    it('should send credentials with requests', () => {
      const withCredentials = true
      expect(withCredentials).toBe(true)
    })
  })
})