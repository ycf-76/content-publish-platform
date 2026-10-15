// workflow store — MIGRATED to workflow-engine project
import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useWorkflowStore = defineStore('workflow', () => {
  const currentWorkflow = ref<any>(null)
  const workflows = ref<any[]>([])
  const nodes = ref<any[]>([])
  const error = ref<string | null>(null)
  const isStreaming = ref(false)

  function reset() { currentWorkflow.value = null; workflows.value = []; nodes.value = []; error.value = null; isStreaming.value = false }
  async function startWorkflow(..._args: any[]): Promise<any> { error.value = 'DAG migrated to workflow-engine project'; return null }
  async function cancelWorkflow(..._args: any[]): Promise<any> { return null }
  async function fetchWorkflows(..._args: any[]): Promise<any> { workflows.value = []; return [] }
  async function fetchWorkflow(..._args: any[]): Promise<any> { return null }

  return { currentWorkflow, workflows, nodes, error, isStreaming, reset, startWorkflow, cancelWorkflow, fetchWorkflows, fetchWorkflow }
})

export type { ModelSettings, SkillMeta, WorkflowResponse, WorkflowListItem, NodeSnapshot, WorkflowResumeRequest } from '@/api/workflow'