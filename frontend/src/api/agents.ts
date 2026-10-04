import apiClient from './client'

export interface AgentSummary {
  agent_id: string
  role: string
  llm_model: string | null
  skills: string[]
  executor: string
  max_iterations: number
  prompt_template: string
  is_builtin: boolean
}

export interface AgentCreateRequest {
  agent_id: string
  role?: string
  llm_model?: string
  skills?: string[]
  executor?: string
  max_iterations?: number
  prompt_template?: string
  hard_rules?: string[]
  recovery?: Record<string, any>
}

export interface AgentUpdateRequest {
  role?: string
  llm_model?: string
  skills?: string[]
  executor?: string
  max_iterations?: number
  prompt_template?: string
  hard_rules?: string[]
  recovery?: Record<string, any>
}

export const agentsApi = {
  async list(): Promise<AgentSummary[]> {
    const resp: any = await apiClient.get('/agents')
    return (resp?.data ?? resp) as AgentSummary[]
  },

  async get(agentId: string): Promise<AgentSummary> {
    const resp: any = await apiClient.get(`/agents/${encodeURIComponent(agentId)}`)
    return (resp?.data ?? resp) as AgentSummary
  },

  async create(data: AgentCreateRequest): Promise<{ success: boolean; data?: AgentSummary; message?: string }> {
    const resp: any = await apiClient.post('/agents', data)
    return resp
  },

  async update(agentId: string, data: AgentUpdateRequest): Promise<{ success: boolean; data?: AgentSummary; message?: string }> {
    const resp: any = await apiClient.put(`/agents/${encodeURIComponent(agentId)}`, data)
    return resp
  },

  async switchLlm(agentId: string, llmModel: string): Promise<{ success: boolean; data?: AgentSummary; message?: string }> {
    const resp: any = await apiClient.patch(`/agents/${encodeURIComponent(agentId)}/llm`, { llm_model: llmModel })
    return resp
  },

  async delete(agentId: string): Promise<{ success: boolean; message?: string }> {
    const resp: any = await apiClient.delete(`/agents/${encodeURIComponent(agentId)}`)
    return resp
  },
}