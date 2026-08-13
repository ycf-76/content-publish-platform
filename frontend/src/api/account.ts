import apiClient from './client'

export interface AccountResponse {
  account_id: string
  xhs_user_id: string
  xhs_nickname: string
  xhs_avatar_url: string
  status: string
  login_method: string
}

export interface QRCodeResponse {
  qr_id: string
  qrcode_base64: string
  qr_url: string
  expires_at: string
}

export interface QRCodeStatusResponse {
  status: 'pending' | 'scanned' | 'confirmed' | 'expired'
  message: string
}

export const accountApi = {
  async listAccounts() {
    return await apiClient.get('/accounts')
  },

  async generateQRCode() {
    return await apiClient.post('/accounts/qrcode', null, { timeout: 120000 })
  },

  async pollQRCode(qrId: string) {
    return await apiClient.post(`/accounts/qrcode/${qrId}/poll`)
  },

  async confirmQRCode(qrId: string) {
    return await apiClient.post(`/accounts/qrcode/${qrId}/confirm`)
  },

  async bindAccount(qrId: string) {
    return await apiClient.post('/accounts/bind', null, {
      params: { qr_id: qrId }
    })
  },

  async bindAccountManual(qrId: string, nickname: string, redId?: string, avatarUrl?: string) {
    return await apiClient.post('/accounts/bind-manual', null, {
      params: {
        qr_id: qrId,
        nickname,
        red_id: redId,
        avatar_url: avatarUrl
      }
    })
  },

  async refreshSession(accountId: string) {
    return await apiClient.post('/accounts/refresh-session', null, {
      params: { account_id: accountId }
    })
  },

  async deleteAccount(accountId: string) {
    return await apiClient.delete(`/accounts/${accountId}`)
  }
}