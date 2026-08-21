import { ref, watch, type Ref } from 'vue'
import { useWorkflowStore } from '@/stores/workflow'
import { useAccountStore } from '@/stores/account'
import { searchApi } from '@/api/search'

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
 * 搜索流程
 *
 * 两条路径：
 * 1. 有小红书账号 → 走完整工作流（搜索→分析→写作→图片→审核→发布）
 * 2. 仅邮箱登录（无小红书账号）→ 走独立搜索 API（/api/search），只做搜索，不启动工作流
 *
 * 权限控制：
 * - 邮箱登录用户可搜索除小红书外的所有平台
 * - 小红书搜索需要小红书扫码登录授权
 */
export function useSearchFlow(
  keywordRef: Ref<string>,
  selectedPlatformRef: Ref<string>,
  searchPlatformsRef: Ref<{ name: string; label: string; desc?: string; locked?: boolean; requires_auth?: boolean; auth_met?: boolean }[]>,
  modelSettingsRef: Ref<Record<string, any>>,
  pendingReferenceRef: Ref<Record<string, any> | null>,
  creativeBriefRef: Ref<string>,
) {
  const workflowStore = useWorkflowStore()
  const accountStore = useAccountStore()

  const searchStatus = ref<SearchStatus>('idle')
  const searchResults = ref<SearchNote[]>([])
  const searchError = ref<string>('')
  const isSearching = ref(false)
  let searchWatchStop: (() => void) | null = null

  /** 仅搜索（不走工作流，使用独立搜索 API） */
  async function standaloneSearch(keyword: string, platform: string) {
    isSearching.value = true
    searchStatus.value = 'loading'
    searchResults.value = []
    searchError.value = ''

    try {
      const res = await searchApi.search(keyword, platform, 20)
      const data = (res as any).data || res
      const results: SearchNote[] = (data.results || []).map((r: any) => ({
        cover_img: r.cover_img || '',
        title: r.title || '',
        summary: r.summary || '',
        likes: r.likes || 0,
        author: r.author || '',
        url: r.url || '',
        platform: r.platform || '',
      }))
      completeSearch(results)
    } catch (e: any) {
      const detail = e?.response?.data?.detail || e?.response?.data?.message || e?.message || '搜索失败'
      if (detail.includes('XHS_AUTH_REQUIRED')) {
        showSearchError('小红书搜索需要先通过小红书扫码登录授权，请在账号中心绑定小红书账号')
      } else if (detail.includes('local client') || detail.includes('浏览器扩展未连接')) {
        showSearchError('小红书搜索服务暂不可用（浏览器扩展未连接），请使用其他平台搜索')
      } else if (e?.response?.status === 503) {
        showSearchError(detail || '搜索服务暂不可用，请稍后重试')
      } else {
        showSearchError(detail)
      }
    }
  }

  /** 启动搜索流程 */
  async function startSearchFlow() {
    if (isSearching.value) return
    const keyword = keywordRef.value.trim()
    if (!keyword) return

    const platform = selectedPlatformRef.value
    const platformInfo = searchPlatformsRef.value.find(p => p.name === platform)
    if (platformInfo?.locked) {
      showSearchError('小红书搜索需要先通过小红书扫码登录授权，请在账号中心绑定小红书账号')
      return
    }

    const accountId = accountStore.currentAccountId || 'email_user'

    // 邮箱登录和扫码登录都走完整工作流
    // account_id 只在 publish 节点才真正需要，搜索/分析/写作/图片生成都不依赖它
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
        creativeBriefRef.value.trim(),
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
        /* cancel failed */
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