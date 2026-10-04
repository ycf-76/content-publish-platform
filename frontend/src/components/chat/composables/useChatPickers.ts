import { ref, computed, nextTick } from 'vue'
import type { AgentSummary } from '@/api/agents'
import { MODEL_REGISTRY, findModel, type ChatModel } from './modelRegistry'

export function useChatPickers() {
  const selectedAgentId = ref('')
  const selectedAgentLabel = ref('')
  const availableAgents = ref<AgentSummary[]>([])
  const showAgentPicker = ref(false)
  const agentPickerFilter = ref('')
  const showSkillPicker = ref(false)
  const skillPickerFilter = ref('')
  const showWorkspaceList = ref(false)
  const allSkills = ref<{ node_type: string; name: string; display_name: string; description: string }[]>([])
  const showModelPicker = ref(false)
  const currentModel = ref('DeepSeek-V3')
  const modelList = MODEL_REGISTRY.map((m) => m.id)
  const modelOptions = MODEL_REGISTRY
  const thinkingDepth = ref<'off' | 'low' | 'medium' | 'high'>('medium')

  const currentModelMeta = computed<ChatModel | undefined>(
    () => findModel(currentModel.value)
  )

  const filteredAgents = computed(() => {
    const q = agentPickerFilter.value.toLowerCase().trim()
    const list = availableAgents.value.filter(a => a.agent_id !== 'chat_agent')
    if (!q) return list
    return list.filter(a =>
      a.agent_id.toLowerCase().includes(q) ||
      (a.role || '').toLowerCase().includes(q)
    )
  })

  const filteredSkills = computed(() => {
    const q = skillPickerFilter.value.toLowerCase().trim()
    let list = allSkills.value
    if (!q) return list
    return list.filter(s =>
      s.name.toLowerCase().includes(q) ||
      s.display_name.toLowerCase().includes(q) ||
      s.description.toLowerCase().includes(q) ||
      s.node_type.toLowerCase().includes(q)
    )
  })

  const thinkingLabel = computed(() => {
    const map = { off: '思考:关', low: '思考:浅', medium: '思考:中', high: '思考:深' }
    return map[thinkingDepth.value]
  })

  function selectAgent(agent: AgentSummary | null) {
    if (agent) {
      selectedAgentId.value = agent.agent_id
      selectedAgentLabel.value = agent.role || agent.agent_id
    } else {
      selectedAgentId.value = ''
      selectedAgentLabel.value = ''
    }
    showAgentPicker.value = false
    agentPickerFilter.value = ''
  }

  function clearSelectedAgent() {
    selectedAgentId.value = ''
    selectedAgentLabel.value = ''
  }

  function toggleAgentPicker() {
    showAgentPicker.value = !showAgentPicker.value
    agentPickerFilter.value = ''
    if (showAgentPicker.value) { showSkillPicker.value = false; showWorkspaceList.value = false }
  }

  function closeAgentPicker() {
    showAgentPicker.value = false
    agentPickerFilter.value = ''
  }

  function toggleSkillPicker() {
    showSkillPicker.value = !showSkillPicker.value
    skillPickerFilter.value = ''
    if (showSkillPicker.value) { showAgentPicker.value = false; showWorkspaceList.value = false }
  }

  function closeSkillPicker() {
    showSkillPicker.value = false
    skillPickerFilter.value = ''
  }

  function toggleWorkspaceList() {
    showWorkspaceList.value = !showWorkspaceList.value
    if (showWorkspaceList.value) { showAgentPicker.value = false; showSkillPicker.value = false }
  }

  function toggleModelPicker() {
    showModelPicker.value = !showModelPicker.value
    if (showModelPicker.value) {
      showAgentPicker.value = false
      showSkillPicker.value = false
    }
  }

  function selectModel(m: string) {
    currentModel.value = m
    showModelPicker.value = false
  }

  function cycleThinking() {
    const order: Array<'off' | 'low' | 'medium' | 'high'> = ['off', 'low', 'medium', 'high']
    const idx = order.indexOf(thinkingDepth.value)
    thinkingDepth.value = order[(idx + 1) % order.length]
  }

  function insertSkillToInput(
    skill: { node_type: string; name: string; display_name: string; description: string },
    inputText: { value: string },
    inputRef: { value: HTMLTextAreaElement | null }
  ) {
    const tag = `/${skill.name}`
    const slashMatch = inputText.value.match(/\/([^\s]*)$/)
    if (slashMatch) {
      inputText.value = inputText.value.replace(/\/([^\s]*)$/, tag)
    } else if (!inputText.value.includes(tag)) {
      inputText.value = inputText.value ? `${inputText.value} ${tag}` : tag
    }
    showSkillPicker.value = false
    skillPickerFilter.value = ''
    nextTick(() => inputRef.value?.focus())
  }

  function closeAllPickers() {
    showAgentPicker.value = false
    showSkillPicker.value = false
    showModelPicker.value = false
    showWorkspaceList.value = false
    agentPickerFilter.value = ''
    skillPickerFilter.value = ''
  }

  return {
    selectedAgentId,
    selectedAgentLabel,
    availableAgents,
    showAgentPicker,
    agentPickerFilter,
    showSkillPicker,
    skillPickerFilter,
    showWorkspaceList,
    allSkills,
    showModelPicker,
    currentModel,
    modelList,
    modelOptions,
    currentModelMeta,
    thinkingDepth,
    thinkingLabel,
    filteredAgents,
    filteredSkills,
    selectAgent,
    clearSelectedAgent,
    toggleAgentPicker,
    closeAgentPicker,
    toggleSkillPicker,
    closeSkillPicker,
    toggleWorkspaceList,
    toggleModelPicker,
    selectModel,
    cycleThinking,
    insertSkillToInput,
    closeAllPickers,
  }
}