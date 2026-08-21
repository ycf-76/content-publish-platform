/**
 * Template registry API client.
 *
 * Phase 1: used as a cache-only bridge so the future image workspace can
 * consume server-side templates without replacing the current frontend
 * rendering logic.
 */

import apiClient from './client'

export interface PlatformFormat {
  platform: string
  format: string
  width: number
  height: number
  safe_area?: Record<string, number>
}

export interface TemplateField {
  key: string
  type: string
  label: string
  required: boolean
}

export interface TemplateManifest {
  id: string
  name: string
  category: string[]
  description: string
  platforms: Record<string, PlatformFormat>
  fields: TemplateField[]
  page_types: string[]
  theme: Record<string, string>
  default_decoration: Record<string, unknown>
  renderer: string
  source: string
}

export interface PlatformProfile {
  platform: string
  display_name: string
  formats: Record<string, PlatformFormat>
}

export async function listTemplates(params?: {
  platform?: string
  category?: string
}): Promise<TemplateManifest[]> {
  const response: any = await apiClient.get('/templates', { params })
  return response?.data ?? response ?? []
}

export async function getTemplate(templateId: string): Promise<TemplateManifest | null> {
  const response: any = await apiClient.get(`/templates/${encodeURIComponent(templateId)}`)
  return response?.data ?? response ?? null
}

export async function listPlatformProfiles(): Promise<PlatformProfile[]> {
  const response: any = await apiClient.get('/templates/platforms')
  return response?.data ?? response ?? []
}

export const templatesApi = {
  listTemplates,
  getTemplate,
  listPlatformProfiles,
}
