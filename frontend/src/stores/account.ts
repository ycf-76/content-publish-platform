import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { accountApi } from '../api/account'

export const useAccountStore = defineStore('account', () => {
  const accounts = ref<any[]>([])
  const currentAccount = ref<any>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  /** 当前选中的账号 ID（用于启动工作流） */
  const currentAccountId = computed(() => currentAccount.value?.account_id || '')

  async function fetchAccounts() {
    loading.value = true
    error.value = null
    try {
      const res: any = await accountApi.listAccounts()
      accounts.value = res.data || []
      // 每次都重新选中：优先选 active 账号，否则选第一个
      if (accounts.value.length > 0) {
        const active = accounts.value.find((a: any) => a.status === 'active')
        currentAccount.value = active || accounts.value[0]
      } else {
        currentAccount.value = null
      }
    } catch (e: any) {
      error.value = e.response?.data?.message || '获取账号列表失败'
    } finally {
      loading.value = false
    }
  }

  function selectAccount(accountId: string) {
    const found = accounts.value.find((a: any) => a.account_id === accountId)
    if (found) currentAccount.value = found
  }

  async function refreshSession(accountId: string) {
    try {
      await accountApi.refreshSession(accountId)
      await fetchAccounts()
    } catch (e: any) {
      error.value = e.response?.data?.message || '刷新会话失败'
      throw e
    }
  }

  async function deleteAccount(accountId: string) {
    try {
      await accountApi.deleteAccount(accountId)
      accounts.value = accounts.value.filter((a: any) => a.account_id !== accountId)
      if (currentAccount.value?.account_id === accountId) {
        currentAccount.value = accounts.value[0] || null
      }
    } catch (e: any) {
      error.value = e.response?.data?.message || '删除账号失败'
      throw e
    }
  }

  function clearError() {
    error.value = null
  }

  return {
    accounts,
    currentAccount,
    currentAccountId,
    loading,
    error,
    fetchAccounts,
    selectAccount,
    refreshSession,
    deleteAccount,
    clearError,
  }
})