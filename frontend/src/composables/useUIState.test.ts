import { describe, it, expect, beforeEach } from 'vitest'
import { useUIState } from './useUIState'

describe('useUIState', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  describe('isSidebarCollapsed', () => {
    it('should have a boolean initial value', () => {
      const { isSidebarCollapsed } = useUIState()
      expect(typeof isSidebarCollapsed.value).toBe('boolean')
    })
  })

  describe('toggleSidebar', () => {
    it('should toggle sidebar collapsed state and persist to localStorage', () => {
      const { isSidebarCollapsed, toggleSidebar } = useUIState()
      const before = isSidebarCollapsed.value

      toggleSidebar()
      expect(isSidebarCollapsed.value).toBe(!before)
      expect(localStorage.getItem('mint_sidebar_collapsed')).toBe(!before ? '1' : '0')

      toggleSidebar()
      expect(isSidebarCollapsed.value).toBe(before)
      expect(localStorage.getItem('mint_sidebar_collapsed')).toBe(before ? '1' : '0')
    })
  })

  describe('workflowExpanded', () => {
    it('should have a boolean initial value', () => {
      const { workflowExpanded } = useUIState()
      expect(typeof workflowExpanded.value).toBe('boolean')
    })
  })

  describe('toggleWorkflowExpanded', () => {
    it('should toggle workflow expanded state and persist to localStorage', () => {
      const { workflowExpanded, toggleWorkflowExpanded } = useUIState()
      const before = workflowExpanded.value

      toggleWorkflowExpanded()
      expect(workflowExpanded.value).toBe(!before)
      expect(localStorage.getItem('mint_workflow_expanded')).toBe(!before ? '1' : '0')

      toggleWorkflowExpanded()
      expect(workflowExpanded.value).toBe(before)
      expect(localStorage.getItem('mint_workflow_expanded')).toBe(before ? '1' : '0')
    })
  })
})