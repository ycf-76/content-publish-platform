import { ref, watch } from 'vue'

export interface SavedSkill {
  id: string
  name: string
  description: string
  icon: string
  tools: string[]
  config: Record<string, string>
  createdAt: number
}

const STORAGE_KEY = 'xiaohongshu_skill_templates'

const savedSkills = ref<SavedSkill[]>([])

function loadFromStorage() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) savedSkills.value = JSON.parse(raw)
  } catch {
    savedSkills.value = []
  }
}

function saveToStorage() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(savedSkills.value))
}

loadFromStorage()

watch(savedSkills, saveToStorage, { deep: true })

export function useSkillTemplates() {
  function addSkill(skill: Omit<SavedSkill, 'id' | 'createdAt'>): SavedSkill {
    const s: SavedSkill = {
      ...skill,
      id: `skill_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
      createdAt: Date.now(),
    }
    savedSkills.value.push(s)
    return s
  }

  function updateSkill(id: string, patch: Partial<Omit<SavedSkill, 'id' | 'createdAt'>>) {
    const idx = savedSkills.value.findIndex((s) => s.id === id)
    if (idx >= 0) {
      savedSkills.value[idx] = { ...savedSkills.value[idx], ...patch }
    }
  }

  function removeSkill(id: string) {
    savedSkills.value = savedSkills.value.filter((s) => s.id !== id)
  }

  function expandToModelSettings(skill: SavedSkill): Record<string, any> {
    const settings: Record<string, any> = {}

    const nodeTypeToSettingsKey: Record<string, string> = {
      copywrite: 'copywrite_skill',
      image_gen: 'image_gen_skill',
      analyze: 'analyze_skill',
      audit: 'audit_skill',
      search: 'search_skill',
      publish: 'publish_skill',
      image_plan: 'image_plan_skill',
      image_review: 'image_review_skill',
      final_review: 'final_review_skill',
    }

    for (const toolId of skill.tools) {
      const sep = toolId.indexOf('/')
      if (sep < 0) continue
      const nodeType = toolId.slice(0, sep)
      const skillName = toolId.slice(sep + 1)
      const key = nodeTypeToSettingsKey[nodeType]
      if (key) settings[key] = skillName
    }

    for (const [k, v] of Object.entries(skill.config)) {
      if (!k.trim()) continue
      const num = Number(v)
      if (v === 'true') settings[k] = true
      else if (v === 'false') settings[k] = false
      else if (!isNaN(num) && v.trim() !== '') settings[k] = num
      else settings[k] = v
    }

    return settings
  }

  return {
    savedSkills,
    addSkill,
    updateSkill,
    removeSkill,
    expandToModelSettings,
  }
}