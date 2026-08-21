import { ref } from 'vue'

const SK_COLLAPSED = 'mint_sidebar_collapsed'
const isSidebarCollapsed = ref(localStorage.getItem(SK_COLLAPSED) === '1')

const SK_WORKFLOW_EXPANDED = 'mint_workflow_expanded'
const workflowExpanded = ref(localStorage.getItem(SK_WORKFLOW_EXPANDED) !== '0')

export function useUIState() {
  function toggleSidebar() {
    isSidebarCollapsed.value = !isSidebarCollapsed.value
    localStorage.setItem(SK_COLLAPSED, isSidebarCollapsed.value ? '1' : '0')
  }

  function toggleWorkflowExpanded() {
    workflowExpanded.value = !workflowExpanded.value
    localStorage.setItem(SK_WORKFLOW_EXPANDED, workflowExpanded.value ? '1' : '0')
  }

  return {
    isSidebarCollapsed,
    workflowExpanded,
    toggleSidebar,
    toggleWorkflowExpanded
  }
}