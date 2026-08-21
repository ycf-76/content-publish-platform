import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useAccountStore } from './account'
import { accountApi } from '@/api/account'

vi.mock('@/api/account', () => ({
  accountApi: {
    listAccounts: vi.fn(),
    refreshSession: vi.fn(),
    deleteAccount: vi.fn(),
  },
}))

describe('useAccountStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  describe('initial state', () => {
    it('should have empty accounts and no current account', () => {
      const store = useAccountStore()
      expect(store.accounts).toHaveLength(0)
      expect(store.currentAccount).toBeNull()
      expect(store.currentAccountId).toBe('')
    })
  })

  describe('fetchAccounts', () => {
    it('should load accounts and select active one', async () => {
      const mockAccounts = [
        { account_id: 'a1', nickname: 'Inactive', status: 'inactive' },
        { account_id: 'a2', nickname: 'Active', status: 'active' },
      ]
      vi.mocked(accountApi.listAccounts).mockResolvedValue({ data: mockAccounts } as any)

      const store = useAccountStore()
      await store.fetchAccounts()

      expect(store.accounts).toHaveLength(2)
      expect(store.currentAccount?.account_id).toBe('a2')
      expect(store.currentAccountId).toBe('a2')
    })

    it('should select first account when no active account', async () => {
      const mockAccounts = [
        { account_id: 'a1', nickname: 'First', status: 'inactive' },
        { account_id: 'a2', nickname: 'Second', status: 'inactive' },
      ]
      vi.mocked(accountApi.listAccounts).mockResolvedValue({ data: mockAccounts } as any)

      const store = useAccountStore()
      await store.fetchAccounts()

      expect(store.currentAccount?.account_id).toBe('a1')
    })

    it('should clear current account when no accounts', async () => {
      vi.mocked(accountApi.listAccounts).mockResolvedValue({ data: [] } as any)

      const store = useAccountStore()
      await store.fetchAccounts()

      expect(store.accounts).toHaveLength(0)
      expect(store.currentAccount).toBeNull()
    })

    it('should set error on failure', async () => {
      vi.mocked(accountApi.listAccounts).mockRejectedValue({
        response: { data: { message: 'Network error' } },
      })

      const store = useAccountStore()
      await store.fetchAccounts()

      expect(store.error).toBe('Network error')
    })
  })

  describe('selectAccount', () => {
    it('should select account by id', async () => {
      const mockAccounts = [
        { account_id: 'a1', nickname: 'First' },
        { account_id: 'a2', nickname: 'Second' },
      ]
      vi.mocked(accountApi.listAccounts).mockResolvedValue({ data: mockAccounts } as any)

      const store = useAccountStore()
      await store.fetchAccounts()
      store.selectAccount('a2')

      expect(store.currentAccount?.account_id).toBe('a2')
    })

    it('should not change current account if id not found', async () => {
      const mockAccounts = [
        { account_id: 'a1', nickname: 'First' },
      ]
      vi.mocked(accountApi.listAccounts).mockResolvedValue({ data: mockAccounts } as any)

      const store = useAccountStore()
      await store.fetchAccounts()
      store.selectAccount('nonexistent')

      expect(store.currentAccount?.account_id).toBe('a1')
    })
  })

  describe('deleteAccount', () => {
    it('should remove account from list', async () => {
      const mockAccounts = [
        { account_id: 'a1', nickname: 'First' },
        { account_id: 'a2', nickname: 'Second' },
      ]
      vi.mocked(accountApi.listAccounts).mockResolvedValue({ data: mockAccounts } as any)
      vi.mocked(accountApi.deleteAccount).mockResolvedValue({} as any)

      const store = useAccountStore()
      await store.fetchAccounts()
      await store.deleteAccount('a1')

      expect(store.accounts).toHaveLength(1)
      expect(store.accounts[0].account_id).toBe('a2')
    })

    it('should switch current account when deleted account was selected', async () => {
      const mockAccounts = [
        { account_id: 'a1', nickname: 'First' },
        { account_id: 'a2', nickname: 'Second' },
      ]
      vi.mocked(accountApi.listAccounts).mockResolvedValue({ data: mockAccounts } as any)
      vi.mocked(accountApi.deleteAccount).mockResolvedValue({} as any)

      const store = useAccountStore()
      await store.fetchAccounts()
      store.selectAccount('a1')
      await store.deleteAccount('a1')

      expect(store.currentAccount?.account_id).toBe('a2')
    })

    it('should set current account to null when last account is deleted', async () => {
      const mockAccounts = [
        { account_id: 'a1', nickname: 'Only' },
      ]
      vi.mocked(accountApi.listAccounts).mockResolvedValue({ data: mockAccounts } as any)
      vi.mocked(accountApi.deleteAccount).mockResolvedValue({} as any)

      const store = useAccountStore()
      await store.fetchAccounts()
      await store.deleteAccount('a1')

      expect(store.currentAccount).toBeNull()
    })
  })

  describe('clearError', () => {
    it('should clear error', () => {
      const store = useAccountStore()
      store.$patch({ error: 'Some error' })
      store.clearError()
      expect(store.error).toBeNull()
    })
  })
})