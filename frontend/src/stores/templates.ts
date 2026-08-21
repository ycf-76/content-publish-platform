/**
 * Template registry cache.
 *
 * Phase 1 only caches the server response. It intentionally does not replace
 * the existing hardcoded template rendering in `card-editor/templates.ts`.
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { templatesApi, type TemplateManifest } from '@/api/templates'

export const useTemplateStore = defineStore('templates', () => {
  const templates = ref<TemplateManifest[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  const templateMap = computed(() => {
    return new Map(templates.value.map((template) => [template.id, template]))
  })

  async function ensureLoaded() {
    if (templates.value.length > 0 || loading.value) return
    loading.value = true
    error.value = null
    try {
      templates.value = await templatesApi.listTemplates()
    } catch (e) {
      error.value = e instanceof Error ? e.message : '模板加载失败'
    } finally {
      loading.value = false
    }
  }

  function labelFor(templateId: string): string {
    return templateMap.value.get(templateId)?.name || templateId
  }

  return {
    templates,
    templateMap,
    loading,
    error,
    ensureLoaded,
    labelFor,
  }
})
