import { defineStore } from 'pinia'

export const useAccountStore = defineStore('account', () => {
  return {
    accounts: [] as any[],
    loading: false,
    error: null as string | null,
    currentAccountId: null as string | null,
    currentAccount: null as any,
    async fetchAccounts() {},
    async refreshSession(_id: string) {},
    async deleteAccount(_id: string) {},
    getAccountById(_id: string) {
      return null
    },
  }
})