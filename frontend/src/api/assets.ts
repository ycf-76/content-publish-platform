/**
 * User image asset API client.
 */

import apiClient from './client'

export interface ImageAsset {
  asset_id: string
  filename: string
  content_type: string
  file_size: number
  width: number | null
  height: number | null
  original_url: string
  thumbnail_url: string
  source: string
}

export async function uploadAssets(files: File[]): Promise<ImageAsset[]> {
  const formData = new FormData()
  files.forEach((file) => formData.append('files', file))

  const response: any = await apiClient.post('/assets', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 120000,
  })
  return response?.data ?? response ?? []
}

export async function listAssets(): Promise<ImageAsset[]> {
  const response: any = await apiClient.get('/assets')
  return response?.data ?? response ?? []
}

export async function deleteAsset(assetId: string): Promise<void> {
  await apiClient.delete(`/assets/${encodeURIComponent(assetId)}`)
}

export const assetsApi = {
  uploadAssets,
  listAssets,
  deleteAsset,
}
