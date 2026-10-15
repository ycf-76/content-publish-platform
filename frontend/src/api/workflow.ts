// workflow API — MIGRATED to workflow-engine project

export interface ModelSettings { text_model?: string; image_model?: string; temperature?: number; writing_style?: string; image_style?: string; copywrite_skill?: string; image_gen_skill?: string; analyze_skill?: string; audit_skill?: string }
export interface SkillMeta { node_type: string; name: string; display_name: string; description?: string; tags?: string[] }
export interface WorkflowResponse { workflow_id: string; status: string; [key: string]: any }
export interface WorkflowListItem { id: string; status: string; [key: string]: any }
export interface NodeSnapshot { node_type: string; status: string; [key: string]: any }
export interface WorkflowResumeRequest { action: string; feedback?: string; selected_candidate?: number }

const _m = (..._args: any[]): Promise<any> => Promise.reject(new Error('DAG migrated to workflow-engine project'))
const _ok = (): Promise<any> => Promise.resolve({ skills: [], data: [], nodes: [], categories: [], total: 0 })

export const workflowApi = new Proxy({} as Record<string, any>, {
  get(_target, _prop: string) {
    return _m
  },
})