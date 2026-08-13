import { ref, computed, onUnmounted } from 'vue'
import { topicPoolApi, type TopicPoolItem } from '@/api/topic_pool'

const HOT_INTERVAL = 5000

/**
 * 顶部热点轮播：数据加载 + 自动切换定时器 + 导航
 *
 * 从 WorkbenchView.vue 抽出的轮播逻辑。
 * 返回响应式数据和操作方法，点击行为由组件 emit 交给父组件处理。
 */
export function useHotCarousel() {
  const hotSlides = ref<TopicPoolItem[]>([])
  const hotIndex = ref(0)
  let hotTimer: ReturnType<typeof setInterval> | null = null

  const currentHot = computed(() => hotSlides.value[hotIndex.value] || null)

  async function loadHotSlides() {
    try {
      const resp = await topicPoolApi.list({ sort: 'heat_desc', size: 12, auto_source: 'monitor' })
      let items = resp.items || []
      if (items.length < 5) {
        const more = await topicPoolApi.list({ sort: 'created_desc', size: 12 })
        items = [...items, ...(more.items || []).filter(it => !items.find(e => e.id === it.id))]
      }
      hotSlides.value = items.slice(0, 12)
      hotIndex.value = 0
    } catch {
      // 静默失败，轮播区不影响主功能
    }
  }

  function hotNext() {
    if (hotSlides.value.length === 0) return
    hotIndex.value = (hotIndex.value + 1) % hotSlides.value.length
  }

  function hotGo(i: number) {
    hotIndex.value = i
  }

  function startHotTimer() {
    stopHotTimer()
    if (hotSlides.value.length > 1) {
      hotTimer = setInterval(hotNext, HOT_INTERVAL)
    }
  }

  function stopHotTimer() {
    if (hotTimer) { clearInterval(hotTimer); hotTimer = null }
  }

  onUnmounted(() => {
    stopHotTimer()
  })

  return {
    hotSlides,
    hotIndex,
    currentHot,
    loadHotSlides,
    hotNext,
    hotGo,
    startHotTimer,
    stopHotTimer,
  }
}