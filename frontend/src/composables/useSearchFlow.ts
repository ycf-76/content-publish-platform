import { ref, watch, type Ref } from 'vue'
import { useWorkflowStore } from '@/stores/workflow'
import { useAccountStore } from '@/stores/account'

export type SearchStatus = 'idle' | 'loading' | 'completed' | 'error'

export interface SearchNote {
  cover_img: string
  title: string
  summary: string
  likes: number
  author: string
  url: string
  platform: string
}

/**
 * 搜索流程：工作流搜索
 *
 * 从 WorkbenchView.vue 抽出的搜索逻辑，用响应式状态替代 DOM 操作。
 * searchStatus 驱动模板渲染（loading / results / error），不再用 innerHTML。
 */
export function useSearchFlow(
  keywordRef: Ref<string>,
  selectedPlatformRef: Ref<string>,
  searchPlatformsRef: Ref<{ name: string; label: string; desc?: string }[]>,
  modelSettingsRef: Ref<Record<string, any>>,
  pendingReferenceRef: Ref<Record<string, any> | null>,
) {
  const workflowStore = useWorkflowStore()
  const accountStore = useAccountStore()

  const searchStatus = ref<SearchStatus>('idle')
  const searchResults = ref<SearchNote[]>([])
  const searchError = ref<string>('')
  const isSearching = ref(false)
  let searchWatchStop: (() => void) | null = null
  /** 启动工作流搜索 */
  async function startSearchFlow() {
    if (isSearching.value) return
    const keyword = keywordRef.value.trim()
    if (!keyword) return

    const accountId = accountStore.currentAccountId
    if (!accountId) {
      alert('请先在小红书账号管理中绑定账号')
      return
    }

    isSearching.value = true
    searchStatus.value = 'loading'
    searchResults.value = []
    searchError.value = ''

    if (searchWatchStop) searchWatchStop()
    searchWatchStop = watch(
      () => workflowStore.nodes,
      (nodes) => {
        const searchNode = nodes.find((n) => n.node_id === 'search')
        if (!searchNode) return
        if (searchNode.status === 'completed' && (searchNode as any).results) {
          completeSearch((searchNode as any).results)
        } else if (searchNode.status === 'error') {
          showSearchError((searchNode as any).error || '搜索节点执行失败')
        }
      },
      { deep: true },
    )

    const stopErrorWatch = watch(
      () => workflowStore.error,
      (err) => {
        if (err) {
          showSearchError(err)
          stopErrorWatch()
        }
      },
    )

    try {
      await workflowStore.startWorkflow(
        keyword,
        accountId,
        modelSettingsRef.value,
        pendingReferenceRef.value || undefined,
      )
      pendingReferenceRef.value = null
    } catch (e: any) {
      showSearchError(e?.response?.data?.message || e?.message || '启动工作流失败')
      stopErrorWatch()
    }
  }

  function completeSearch(results: SearchNote[]) {
    isSearching.value = false
    searchResults.value = results
    searchStatus.value = 'completed'
    if (searchWatchStop) {
      searchWatchStop()
      searchWatchStop = null
    }
  }

  function showSearchError(message: string) {
    isSearching.value = false
    searchStatus.value = 'error'
    searchError.value = message
  }

  function resetSearch() {
    searchStatus.value = 'idle'
    searchResults.value = []
    searchError.value = ''
  }
  /** 取消当前工作流并重新开始搜索 */
  async function cancelAndRestart() {
    // 取消当前工作流
    if (workflowStore.currentWorkflow && workflowStore.isStreaming) {
      try {
        await workflowStore.cancelWorkflow()
      } catch (e) {
        console.warn('取消工作流失败:', e)
        // 即使取消失败，也继续执行重置+启动
      }
    }
    // 清理状态
    resetSearch()
    workflowStore.reset()
    // 启动新搜索
    await startSearchFlow()
  }


  return {
    searchStatus,
    searchResults,
    searchError,
    isSearching,
    startSearchFlow,
    cancelAndRestart,
    completeSearch,
    showSearchError,
    resetSearch,
  }
}