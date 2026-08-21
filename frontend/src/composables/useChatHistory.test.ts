import { describe, it, expect, beforeEach } from 'vitest'
import { useChatHistory } from './useChatHistory'

describe('useChatHistory', () => {
  beforeEach(() => {
    const { clearAll } = useChatHistory()
    clearAll()
  })

  describe('addConversation', () => {
    it('should add a new conversation to the beginning of history', () => {
      const { addConversation, history } = useChatHistory()
      addConversation('1', 'First Chat')
      addConversation('2', 'Second Chat')

      expect(history.value).toHaveLength(2)
      expect(history.value[0].id).toBe('2')
      expect(history.value[1].id).toBe('1')
    })

    it('should update title if conversation with same id already exists', () => {
      const { addConversation, history } = useChatHistory()
      addConversation('1', 'Original Title')
      addConversation('1', 'Updated Title')

      expect(history.value).toHaveLength(1)
      expect(history.value[0].title).toBe('Updated Title')
    })

    it('should default title to "新会话" when title is empty', () => {
      const { addConversation, history } = useChatHistory()
      addConversation('1', '')

      expect(history.value[0].title).toBe('新会话')
    })

    it('should set createdAt timestamp', () => {
      const { addConversation, history } = useChatHistory()
      const before = Date.now()
      addConversation('1', 'Test')
      const after = Date.now()

      expect(history.value[0].createdAt).toBeGreaterThanOrEqual(before)
      expect(history.value[0].createdAt).toBeLessThanOrEqual(after)
    })
  })

  describe('removeConversation', () => {
    it('should remove conversation by id', () => {
      const { addConversation, removeConversation, history } = useChatHistory()
      addConversation('1', 'Chat 1')
      addConversation('2', 'Chat 2')
      removeConversation('1')

      expect(history.value).toHaveLength(1)
      expect(history.value[0].id).toBe('2')
    })

    it('should do nothing if id not found', () => {
      const { addConversation, removeConversation, history } = useChatHistory()
      addConversation('1', 'Chat 1')
      removeConversation('nonexistent')

      expect(history.value).toHaveLength(1)
    })
  })

  describe('updateTitle', () => {
    it('should update title of existing conversation', () => {
      const { addConversation, updateTitle, history } = useChatHistory()
      addConversation('1', 'Old Title')
      updateTitle('1', 'New Title')

      expect(history.value[0].title).toBe('New Title')
    })

    it('should default to "新会话" when new title is empty', () => {
      const { addConversation, updateTitle, history } = useChatHistory()
      addConversation('1', 'Some Title')
      updateTitle('1', '')

      expect(history.value[0].title).toBe('新会话')
    })

    it('should do nothing if id not found', () => {
      const { addConversation, updateTitle, history } = useChatHistory()
      addConversation('1', 'Title')
      updateTitle('nonexistent', 'New')

      expect(history.value[0].title).toBe('Title')
    })
  })

  describe('clearAll', () => {
    it('should remove all conversations', () => {
      const { addConversation, clearAll, history } = useChatHistory()
      addConversation('1', 'Chat 1')
      addConversation('2', 'Chat 2')
      clearAll()

      expect(history.value).toHaveLength(0)
    })
  })

  describe('displayItems & hasMore', () => {
    it('should show at most MAX_DISPLAY items when not expanded', () => {
      const { addConversation, displayItems, hasMore } = useChatHistory()
      for (let i = 1; i <= 8; i++) {
        addConversation(String(i), `Chat ${i}`)
      }

      expect(displayItems.value).toHaveLength(6)
      expect(hasMore.value).toBe(true)
    })

    it('should show all items when expanded', () => {
      const { addConversation, displayItems, hasMore, toggleExpand } = useChatHistory()
      for (let i = 1; i <= 8; i++) {
        addConversation(String(i), `Chat ${i}`)
      }
      toggleExpand()

      expect(displayItems.value).toHaveLength(8)
      expect(hasMore.value).toBe(true)
    })

    it('should not show hasMore when items <= MAX_DISPLAY', () => {
      const { addConversation, hasMore } = useChatHistory()
      for (let i = 1; i <= 6; i++) {
        addConversation(String(i), `Chat ${i}`)
      }

      expect(hasMore.value).toBe(false)
    })
  })

  describe('totalCount', () => {
    it('should return total number of conversations', () => {
      const { addConversation, totalCount } = useChatHistory()
      addConversation('1', 'Chat 1')
      addConversation('2', 'Chat 2')

      expect(totalCount.value).toBe(2)
    })
  })

  describe('toggleExpand', () => {
    it('should toggle allExpanded state', () => {
      const { allExpanded, toggleExpand } = useChatHistory()
      expect(allExpanded.value).toBe(false)
      toggleExpand()
      expect(allExpanded.value).toBe(true)
      toggleExpand()
      expect(allExpanded.value).toBe(false)
    })
  })
})