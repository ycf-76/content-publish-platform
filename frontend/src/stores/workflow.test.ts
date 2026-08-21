import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useWorkflowStore } from './workflow'

vi.mock('@/api/workflow', () => ({
  workflowApi: {
    start: vi.fn(),
    getDetail: vi.fn(),
    getNodes: vi.fn(),
    pause: vi.fn(),
    resume: vi.fn(),
    terminate: vi.fn(),
    cancel: vi.fn(),
    rollback: vi.fn(),
    submitReview: vi.fn(),
    updateNodeOutput: vi.fn(),
    subscribe: vi.fn(),
    checkPublishResult: vi.fn(),
    list: vi.fn(),
    delete: vi.fn(),
  },
}))

vi.mock('@/api/auth', () => ({
  authApi: {
    createSseSession: vi.fn().mockResolvedValue({}),
  },
}))

describe('useWorkflowStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    vi.clearAllMocks()
  })

  describe('initial state', () => {
    it('should have correct default values', () => {
      const store = useWorkflowStore()
      expect(store.currentWorkflow).toBeNull()
      expect(store.nodes).toHaveLength(0)
      expect(store.eventLogs).toHaveLength(0)
      expect(store.isLoading).toBe(false)
      expect(store.error).toBeNull()
      expect(store.isStreaming).toBe(false)
      expect(store.notifications).toHaveLength(0)
    })
  })

  describe('computed properties', () => {
    it('pendingReviews should count nodes with awaiting_review status', () => {
      const store = useWorkflowStore()
      store.$patch({
        nodes: [
          { node_id: 'n1', node_type: 'search', status: 'completed' },
          { node_id: 'n2', node_type: 'copywrite', status: 'awaiting_review' },
          { node_id: 'n3', node_type: 'image_review', status: 'awaiting_review' },
        ] as any,
      })
      expect(store.pendingReviews).toBe(2)
    })

    it('runningNodes should count running nodes', () => {
      const store = useWorkflowStore()
      store.$patch({
        nodes: [
          { node_id: 'n1', node_type: 'search', status: 'running' },
          { node_id: 'n2', node_type: 'copywrite', status: 'completed' },
          { node_id: 'n3', node_type: 'image_gen', status: 'running' },
        ] as any,
      })
      expect(store.runningNodes).toBe(2)
    })

    it('progress should calculate percentage of completed/passed nodes', () => {
      const store = useWorkflowStore()
      store.$patch({
        nodes: [
          { node_id: 'n1', node_type: 'search', status: 'completed' },
          { node_id: 'n2', node_type: 'copywrite', status: 'passed' },
          { node_id: 'n3', node_type: 'image_gen', status: 'running' },
          { node_id: 'n4', node_type: 'publish', status: 'idle' },
        ] as any,
      })
      expect(store.progress).toBe(50)
    })

    it('progress should be 0 when no nodes', () => {
      const store = useWorkflowStore()
      expect(store.progress).toBe(0)
    })
  })

  describe('notifications', () => {
    it('pushNotification should add notification with id and timestamp', () => {
      const store = useWorkflowStore()
      store.pushNotification({
        type: 'arrearage',
        message: '图片生成账号欠费',
        action_url: 'https://example.com/recharge',
        action_text: '去充值',
      })

      expect(store.notifications).toHaveLength(1)
      expect(store.notifications[0].type).toBe('arrearage')
      expect(store.notifications[0].message).toBe('图片生成账号欠费')
      expect(store.notifications[0].id).toBeTruthy()
      expect(store.notifications[0].timestamp).toBeGreaterThan(0)
    })

    it('dismissNotification should remove notification by id', () => {
      const store = useWorkflowStore()
      store.pushNotification({ type: 'workflow_error', message: 'Error 1' })
      store.pushNotification({ type: 'arrearage', message: 'Error 2' })

      const id = store.notifications[0].id
      store.dismissNotification(id)

      expect(store.notifications).toHaveLength(1)
      expect(store.notifications[0].message).toBe('Error 2')
    })

    it('clearNotifications should remove all notifications', () => {
      const store = useWorkflowStore()
      store.pushNotification({ type: 'workflow_error', message: 'Error 1' })
      store.pushNotification({ type: 'arrearage', message: 'Error 2' })
      store.clearNotifications()

      expect(store.notifications).toHaveLength(0)
    })
  })

  describe('handleWorkflowEvent', () => {
    it('should handle workflow_started event', () => {
      const store = useWorkflowStore()
      store.$patch({ currentWorkflow: { workflow_id: 'wf1', status: 'pending' } as any })

      store.handleWorkflowEvent('workflow_started', { topic: 'test topic' }, 'evt1')

      expect(store.currentWorkflow?.status).toBe('running')
    })

    it('should handle workflow_completed event', () => {
      const store = useWorkflowStore()
      store.$patch({
        currentWorkflow: { workflow_id: 'wf1', status: 'running' } as any,
        isStreaming: true,
      })

      store.handleWorkflowEvent('workflow_completed', {}, 'evt2')

      expect(store.currentWorkflow?.status).toBe('completed')
      expect(store.isStreaming).toBe(false)
    })

    it('should handle workflow_failed event and push notification', () => {
      const store = useWorkflowStore()
      store.$patch({
        currentWorkflow: { workflow_id: 'wf1', status: 'running' } as any,
        isStreaming: true,
      })

      store.handleWorkflowEvent('workflow_failed', { message: 'Search failed' }, 'evt3')

      expect(store.currentWorkflow?.status).toBe('failed')
      expect(store.isStreaming).toBe(false)
      expect(store.notifications).toHaveLength(1)
      expect(store.notifications[0].type).toBe('workflow_failed')
    })

    it('should handle model_arrearage event and push notification', () => {
      const store = useWorkflowStore()

      store.handleWorkflowEvent('model_arrearage', {
        message: '欠费',
        action_url: 'https://recharge.url',
        action_text: '去充值',
      }, 'evt4')

      expect(store.notifications).toHaveLength(1)
      expect(store.notifications[0].type).toBe('arrearage')
      expect(store.notifications[0].action_url).toBe('https://recharge.url')
    })

    it('should handle node_started event and update existing node', () => {
      const store = useWorkflowStore()
      store.$patch({
        nodes: [
          { node_id: 'search', node_type: 'search', status: 'idle' },
        ] as any,
      })

      store.handleWorkflowEvent('node_started', {
        node_id: 'search',
        status: 'running',
      }, 'evt5')

      expect(store.nodes[0].status).toBe('running')
    })

    it('should handle node_started event and add new node if not found', () => {
      const store = useWorkflowStore()

      store.handleWorkflowEvent('node_started', {
        node_id: 'copywrite',
        status: 'running',
      }, 'evt6')

      expect(store.nodes).toHaveLength(1)
      expect(store.nodes[0].node_id).toBe('copywrite')
      expect(store.nodes[0].status).toBe('running')
    })

    it('should handle node_completed event', () => {
      const store = useWorkflowStore()
      store.$patch({
        nodes: [
          { node_id: 'search', node_type: 'search', status: 'running' },
        ] as any,
      })

      store.handleWorkflowEvent('node_completed', {
        node_id: 'search',
        output: { results: [] },
      }, 'evt7')

      expect(store.nodes[0].status).toBe('completed')
    })

    it('should handle node_error event', () => {
      const store = useWorkflowStore()
      store.$patch({
        nodes: [
          { node_id: 'search', node_type: 'search', status: 'running' },
        ] as any,
      })

      store.handleWorkflowEvent('node_error', {
        node_id: 'search',
        error: 'Timeout',
      }, 'evt8')

      expect(store.nodes[0].status).toBe('error')
    })

    it('should handle review_required event', () => {
      const store = useWorkflowStore()
      store.$patch({
        nodes: [
          { node_id: 'copywrite', node_type: 'copywrite', status: 'running', output: {} },
        ] as any,
      })

      store.handleWorkflowEvent('review_required', {
        review_node: 'copywrite',
        review_type: 'direction_select',
        options: ['方向A', '方向B'],
      }, 'evt9')

      expect(store.nodes[0].status).toBe('awaiting_review')
      expect(store.nodes[0].output.review_type).toBe('direction_select')
    })

    it('should handle stream_chunk event and append text to agent_thinking', () => {
      const store = useWorkflowStore()
      store.$patch({
        nodes: [
          { node_id: 'analyze', node_type: 'analyze', status: 'running', agent_thinking: 'Hello' },
        ] as any,
      })

      store.handleWorkflowEvent('stream_chunk', {
        node_id: 'analyze',
        chunk: ' World',
      }, 'evt10')

      expect(store.nodes[0].agent_thinking).toBe('Hello World')
    })

    it('should handle search_degraded event and push notification', () => {
      const store = useWorkflowStore()

      store.handleWorkflowEvent('search_degraded', {
        message: '搜索降级',
        searched_platforms: ['weibo', 'zhihu'],
      }, 'evt11')

      expect(store.notifications).toHaveLength(1)
      expect(store.notifications[0].type).toBe('search_degraded')
    })

    it('should protect rollback nodes from stale completed status', () => {
      const store = useWorkflowStore()
      store.$patch({
        nodes: [
          {
            node_id: 'image_gen',
            node_type: 'image_gen',
            status: 'idle',
            output: { _rollback: true },
          },
        ] as any,
      })

      store.handleWorkflowEvent('node_started', {
        node_id: 'image_gen',
        status: 'completed',
      }, 'evt12')

      expect(store.nodes[0].status).toBe('idle')
    })

    it('should allow rollback node to transition to running (clear _rollback)', () => {
      const store = useWorkflowStore()
      store.$patch({
        nodes: [
          {
            node_id: 'image_gen',
            node_type: 'image_gen',
            status: 'idle',
            output: { _rollback: true },
          },
        ] as any,
      })

      store.handleWorkflowEvent('node_started', {
        node_id: 'image_gen',
        status: 'running',
      }, 'evt13')

      expect(store.nodes[0].status).toBe('running')
      expect(store.nodes[0].output?._rollback).toBeUndefined()
    })
  })

  describe('eventLogs', () => {
    it('should add log entry for each event', () => {
      const store = useWorkflowStore()

      store.handleWorkflowEvent('workflow_started', { topic: 'test' }, 'evt1')
      store.handleWorkflowEvent('node_completed', { node_id: 'search' }, 'evt2')

      expect(store.eventLogs).toHaveLength(2)
      expect(store.eventLogs[0].event_type).toBe('workflow_started')
      expect(store.eventLogs[1].event_type).toBe('node_completed')
    })

    it('should assign correct log levels', () => {
      const store = useWorkflowStore()

      store.handleWorkflowEvent('workflow_started', { topic: 'test' }, 'e1')
      store.handleWorkflowEvent('workflow_completed', {}, 'e2')
      store.handleWorkflowEvent('workflow_error', { message: 'err' }, 'e3')
      store.handleWorkflowEvent('node_started', { node_id: 'n1' }, 'e4')

      expect(store.eventLogs[0].level).toBe('info')
      expect(store.eventLogs[1].level).toBe('success')
      expect(store.eventLogs[2].level).toBe('error')
      expect(store.eventLogs[3].level).toBe('info')
    })

    it('should cap logs at 200 entries', () => {
      const store = useWorkflowStore()

      for (let i = 0; i < 210; i++) {
        store.handleWorkflowEvent('workflow_started', { topic: `t${i}` }, `e${i}`)
      }

      expect(store.eventLogs).toHaveLength(200)
    })
  })

  describe('reset', () => {
    it('should clear all workflow state', () => {
      const store = useWorkflowStore()
      store.$patch({
        currentWorkflow: { workflow_id: 'wf1' } as any,
        nodes: [{ node_id: 'n1', status: 'running' }] as any,
        eventLogs: [{ event_id: 'e1', event_type: 'test', timestamp: '', message: '', level: 'info' }] as any,
        error: 'some error',
        isStreaming: true,
      })

      store.reset()

      expect(store.currentWorkflow).toBeNull()
      expect(store.nodes).toHaveLength(0)
      expect(store.eventLogs).toHaveLength(0)
      expect(store.error).toBeNull()
      expect(store.isStreaming).toBe(false)
    })
  })

  describe('clearError', () => {
    it('should clear error', () => {
      const store = useWorkflowStore()
      store.$patch({ error: 'some error' })
      store.clearError()
      expect(store.error).toBeNull()
    })
  })
})