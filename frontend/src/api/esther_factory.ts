/**
 * Esther Factory API
 *
 * Template production factory: produce via LLM, render via Jinja2
 */

import apiClient from './client'

export interface SceneInfo {
  id: string
  name: string
}

export interface TemplateInfo {
  id: string
  name: string
  scene: string
  fields_count: number
}

export interface ProduceRequest {
  scene: string
  description: string
  template_id: string
  brand_overrides?: Record<string, string>
  extra_instructions?: string
}

export interface ProduceResult {
  success: boolean
  template_id: string
  issues: Array<{ level: string; rule: string; message: string }>
  error: string | null
}

export interface RenderRequest {
  template_id: string
  data: Record<string, any>
  brand?: Record<string, string>
}

export interface ImportRequest {
  template_id: string
  template_schema: Record<string, any>
  template_html: string
  meta?: Record<string, any>
  overwrite?: boolean
}

export interface ImportResult {
  success: boolean
  template_id: string
  issues: Array<{ level: string; rule: string; message: string }>
  error: string | null
}

export interface ExportResult {
  template_id: string
  template_schema: Record<string, any>
  template_html: string
  meta: Record<string, any>
}

export interface BrandConfig {
  brand_name: string
  avatar_url: string
  gender: string
  primary: string
  accent: string
  spot: string
}

export const estherFactoryApi = {
  listScenes(): Promise<SceneInfo[]> {
    return apiClient.get('/esther-factory/scenes').then((r: any) => r?.data ?? r)
  },

  listTemplates(): Promise<TemplateInfo[]> {
    return apiClient.get('/esther-factory/templates').then((r: any) => r?.data ?? r)
  },

  getSchema(templateId: string): Promise<any> {
    return apiClient.get(`/esther-factory/templates/${templateId}/schema`).then((r: any) => r?.data ?? r)
  },

  getMeta(templateId: string): Promise<any> {
    return apiClient.get(`/esther-factory/templates/${templateId}/meta`).then((r: any) => r?.data ?? r)
  },

  produce(request: ProduceRequest): Promise<ProduceResult> {
    return apiClient.post('/esther-factory/produce', request).then((r: any) => r?.data ?? r)
  },

  render(request: RenderRequest): Promise<string> {
    return apiClient.post('/esther-factory/render', request).then((r: any) => {
      const data = r?.data ?? r
      return data?.html ?? ''
    })
  },

  deleteTemplate(templateId: string): Promise<void> {
    return apiClient.delete(`/esther-factory/templates/${templateId}`)
  },

  importTemplate(request: ImportRequest): Promise<ImportResult> {
    return apiClient.post('/esther-factory/import', request).then((r: any) => r?.data ?? r)
  },

  exportTemplate(templateId: string): Promise<ExportResult> {
    return apiClient.get(`/esther-factory/templates/${templateId}/export`).then((r: any) => r?.data ?? r)
  },

  getBrandConfig(): Promise<BrandConfig> {
    return apiClient.get('/esther-factory/brand-config').then((r: any) => r?.data ?? r)
  },

  saveBrandConfig(config: Partial<BrandConfig>): Promise<BrandConfig> {
    return apiClient.put('/esther-factory/brand-config', config).then((r: any) => r?.data ?? r)
  },

  uploadAvatar(file: File): Promise<{ avatar_url: string }> {
    const formData = new FormData()
    formData.append('file', file)
    return apiClient.post('/esther-factory/brand-config/avatar', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }).then((r: any) => r?.data ?? r)
  },
}