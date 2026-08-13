<template>
  <div class="mint-shell tp-shell" :class="{ 'mint-collapsed': isSidebarCollapsed, 'cards-transparent': cardsTransparent, 'dark-theme': darkTheme }">

    <!-- ============ LEFT COLUMN ============ -->
    <SidebarNav
      :current-page="'topic-pool'"
      :cards-transparent="cardsTransparent"
      :dark-theme="darkTheme"
      @nav-click="handleNavClick"
      @toggle-sidebar="toggleSidebar"
      @toggle-cards-transparent="toggleCardsTransparent"
      @toggle-theme="toggleTheme"
      @go-eco="goToEco"
    />

    <!-- 侧边栏拖拽条（Codex 风格）：拖动调整侧边栏宽度 -->
    <div
      v-if="!isSidebarCollapsed"
      class="tp-sidebar-resizer"
      @mousedown="startSidebarResize"
      title="拖动调整侧边栏宽度"
    ><div class="tp-sidebar-resizer-line"></div></div>

    <!-- ============ MIDDLE COLUMN ============ -->
    <main class="tp-page">
      <div class="tp-content-card-wrapper">
      <div class="tp-content-card">
      <div class="tp-container">

      <!-- 抓取区域：手动抓取 + 监控抓取 -->
      <section class="tp-fetch">
        <div class="tp-fetch-title">
          <DownloadCloud />
          <span>抓取爆款内容</span>
          <button
            class="tp-monitor-btn"
            @click="doMonitorFetch"
            :disabled="monitorFetching"
            type="button"
            title="手动触发一次监控抓取（评分入池）"
          >
            <Zap v-if="!monitorFetching" />
            <Loader2 class="tp-spin" v-else />
            <span>{{ monitorFetching ? '监控抓取中...' : '监控抓取' }}</span>
          </button>
        </div>
        <div class="tp-fetch-form">
          <input
            class="tp-fetch-input"
            v-model="fetchForm.keyword"
            type="text"
            placeholder="输入关键词抓取爆款内容..."
            @keydown.enter="doFetch"
            :disabled="fetching"
          />
          <select class="tp-fetch-select" v-model="fetchForm.platform" :disabled="fetching">
            <option value="xiaohongshu">小红书（需桥接在线）</option>
            <option value="hackernews">HackerNews</option>
            <option value="reddit">Reddit</option>
            <option value="tavily">Tavily</option>
          </select>
          <div class="tp-stat-inline" v-if="stats.total > 0">
            <span class="tp-stat-inline-item"><Radar class="tp-stat-inline-icon" />{{ stats.monitor_count }}</span>
            <span class="tp-stat-inline-item"><Flame class="tp-stat-inline-icon" />{{ stats.avg_heat_score }}</span>
          </div>
          <button
            class="tp-fetch-btn"
            @click="doFetch"
            :disabled="fetching || !fetchForm.keyword.trim()"
            type="button"
          >
            <Download v-if="!fetching" />
            <Loader2 class="tp-spin" v-else />
            <span>{{ fetching ? '抓取中...' : '抓取' }}</span>
          </button>
        </div>
        <div class="tp-fetch-hint" v-if="fetchForm.platform === 'xiaohongshu'">
          小红书抓取需桥接页面在线 + 登录态，受频率限制（30s间隔/每日30次），请耐心等待
        </div>
        <div class="tp-fetch-hint tp-fetch-hint-alt" v-else>
          其他平台（{{ fetchForm.platform }}）无需桥接，可直接抓取
        </div>
        <div class="tp-fetch-msg" v-if="fetchMessage">{{ fetchMessage }}</div>
        <div class="tp-fetch-msg tp-fetch-msg-monitor" v-if="monitorMessage">{{ monitorMessage }}</div>
      </section>

      <!-- 平台分类标签栏 -->
      <section class="tp-platform-tabs">
        <button
          class="tp-tab"
          :class="{ 'is-active': filters.platform === '' }"
          @click="filters.platform = ''"
          type="button"
        >
          全部 <span class="tp-tab-count">{{ stats.total }}</span>
        </button>
        <button
          v-for="plat in platformTabs"
          :key="plat.value"
          class="tp-tab"
          :class="{ 'is-active': filters.platform === plat.value }"
          @click="filters.platform = plat.value"
          type="button"
        >
          {{ plat.label }}
          <span class="tp-tab-count" v-if="stats.platforms[plat.value]">{{ stats.platforms[plat.value] }}</span>
        </button>
      </section>

      <!-- 筛选栏 -->
      <section class="tp-filters">
        <div class="tp-filter-item tp-filter-search">
          <div class="tp-search-wrap">
            <Search class="tp-search-icon" />
            <input
              class="tp-input"
              v-model="filters.keyword"
              type="text"
              placeholder="搜索标题或摘要..."
            />
          </div>
        </div>

        <div class="tp-filter-item tp-filter-source">
          <div class="tp-source-group">
            <button
              class="tp-source-chip"
              :class="{ 'is-active': filters.auto_source === '' }"
              @click="filters.auto_source = ''"
              type="button"
            >全部</button>
            <button
              class="tp-source-chip"
              :class="{ 'is-active': filters.auto_source === 'monitor' }"
              @click="filters.auto_source = 'monitor'"
              type="button"
            >监控</button>
            <button
              class="tp-source-chip"
              :class="{ 'is-active': filters.auto_source === 'manual' }"
              @click="filters.auto_source = 'manual'"
              type="button"
            >手动</button>
          </div>
        </div>

        <div class="tp-filter-item tp-filter-toggle">
          <label class="tp-switch-label">
            <span>仅看收藏</span>
            <button
              class="tp-switch"
              :class="{ 'is-on': filters.favorited_only }"
              @click="filters.favorited_only = !filters.favorited_only"
              type="button"
              role="switch"
              :aria-checked="filters.favorited_only"
            ></button>
          </label>
        </div>

        <div class="tp-filter-item tp-filter-sort">
          <button
            class="tp-sort-btn"
            @click="toggleSort"
            type="button"
            :title="filters.sort === 'heat_desc' ? '当前按热度分降序，点击切换为最新' : '当前按最新排序，点击切换为热度'"
          >
            <ArrowDownWideNarrow v-if="filters.sort === 'heat_desc'" />
            <Clock v-else />
            <span>{{ filters.sort === 'heat_desc' ? '热度' : '最新' }}</span>
          </button>
        </div>

        <div class="tp-stat-inline" v-if="stats.total > 0">
          <span class="tp-stat-inline-item"><Layers class="tp-stat-inline-icon" />{{ stats.total }}</span>
          <span class="tp-stat-inline-item"><Star class="tp-stat-inline-icon" />{{ stats.favorited }}</span>
        </div>

        <button class="tp-refresh-btn" @click="refresh" :disabled="loading" type="button">
          <RefreshCw />
          <span>刷新</span>
        </button>
      </section>

      <!-- 列表区 -->
      <section class="tp-list">
        <!-- 加载中 -->
        <div v-if="loading" class="tp-loading">
          <Loader2 class="tp-spin" />
          <span>加载中...</span>
        </div>

        <!-- 空状态 -->
        <div v-else-if="items.length === 0" class="tp-empty">
          <Inbox />
          <div class="tp-empty-title">暂无选题</div>
          <div class="tp-empty-desc">尝试调整筛选条件，或点击刷新重新获取</div>
        </div>

        <!-- 卡片列表 -->
        <template v-else>
          <article
            v-for="(item, idx) in items"
            :key="item.id"
            class="tp-card"
            :style="{ animationDelay: `${Math.min(idx, 12) * 40}ms` }"
          >
            <!-- 封面区（仅在有图片时渲染） -->
            <div class="tp-card-cover" v-if="hasCoverImg(item)">
              <img
                :src="safeImageUrl(item.cover_img!)"
                :alt="item.title"
                loading="lazy"
                @error="onCoverImgError($event, item)"
              />
              <!-- 平台标签（左上角悬浮） -->
              <span class="tp-platform-tag tp-platform-tag-float" :style="platformStyle(item.platform)">{{ platformLabel(item.platform) }}</span>
              <!-- 图片数量角标 -->
              <span class="tp-img-count" v-if="(item.images?.length || 0) > 1">{{ item.images.length }}图</span>
              <!-- 监控热度角标（右上角） -->
              <span class="tp-heat-badge" v-if="item.auto_source === 'monitor'" :class="`tp-heat-status-${heatStatusClass(item.heat_status)}`">
                <Flame />
                <span>{{ item.heat_score.toFixed(0) }}</span>
              </span>
              <!-- hover 时浮现的快捷操作 -->
              <div class="tp-cover-actions">
                <button class="tp-cover-btn tp-cover-btn-primary" @click="startWorkflowFromTopic(item)" type="button" title="以此选题发起工作流">
                  <Play /><span>发起工作流</span>
                </button>
                <a v-if="item.url" class="tp-cover-btn" :href="item.url" target="_blank" rel="noopener noreferrer" title="查看原文">
                  <ExternalLink />
                </a>
              </div>
            </div>

            <!-- 内容区 -->
            <div class="tp-card-body">
              <!-- 无封面图时：平台标签放在内容区顶部 -->
              <div class="tp-card-meta-top" v-if="!hasCoverImg(item)">
                <span class="tp-platform-tag" :style="platformStyle(item.platform)">{{ platformLabel(item.platform) }}</span>
                <span class="tp-card-monitor" v-if="item.auto_source === 'monitor'">{{ item.heat_status }}</span>
              </div>
              <!-- 有封面图时：作者行 -->
              <div class="tp-card-meta-top" v-else>
                <span class="tp-author" v-if="item.author">
                  <User />
                  <span>{{ item.author }}</span>
                </span>
                <span class="tp-card-monitor" v-if="item.auto_source === 'monitor'">{{ item.heat_status }}</span>
              </div>
              <h3 class="tp-card-title tp-card-title-clickable" @click="goDetail(item.id)" title="查看详情">{{ item.title }}</h3>
              <p class="tp-card-summary" v-if="item.summary">{{ item.summary }}</p>
              <!-- 无封面图时：作者信息放在摘要下方 -->
              <div class="tp-no-cover-author" v-if="!hasCoverImg(item) && item.author">
                <User /><span>{{ item.author }}</span>
              </div>
              <div class="tp-card-dims" v-if="item.dimensions">
                <span v-if="item.dimensions.emotion">{{ item.dimensions.emotion }}</span>
                <span v-if="item.dimensions.scene">{{ item.dimensions.scene }}</span>
                <span v-if="item.dimensions.visual">{{ item.dimensions.visual }}</span>
              </div>
            </div>

            <!-- 底部：指标 + 操作 -->
            <div class="tp-card-bottom">
              <div class="tp-metrics">
                <span class="tp-metric" v-if="item.fans_count > 0" title="粉丝">
                  <Users /><span>{{ formatNum(item.fans_count) }}</span>
                </span>
                <span class="tp-metric" title="点赞">
                  <ThumbsUp /><span>{{ formatNum(item.likes) }}</span>
                </span>
                <span class="tp-metric" v-if="item.collects > 0" title="收藏">
                  <Bookmark /><span>{{ formatNum(item.collects) }}</span>
                </span>
                <span class="tp-metric" title="评论">
                  <MessageSquare /><span>{{ formatNum(item.comments) }}</span>
                </span>
              </div>
              <div class="tp-actions">
                <a v-if="item.url" class="tp-orig-link" :href="item.url" target="_blank" rel="noopener noreferrer" title="查看原文">
                  <ExternalLink />
                </a>
                <button class="tp-icon-btn" :class="{ 'is-favorited': item.is_favorited }" @click="toggleFavorite(item)" type="button" :title="item.is_favorited ? '取消收藏' : '收藏'">
                  <Star />
                </button>
                <button class="tp-icon-btn" @click="deleteItem(item)" type="button" title="删除">
                  <Trash2 />
                </button>
                <button class="tp-workflow-btn" @click="startWorkflowFromTopic(item)" type="button" title="以此选题发起工作流">
                  <Play /><span>发起工作流</span>
                </button>
              </div>
            </div>
          </article>
        </template>
      </section>

    </div>

    <!-- 分页（固定在 tp-page 底部，独立于瀑布流容器） -->
    <section class="tp-pagination" v-if="!loading && items.length > 0">
      <button
        class="tp-page-btn"
        :disabled="page <= 1"
        @click="changePage(page - 1)"
        type="button"
      >
        <ChevronLeft />
        <span>上一页</span>
      </button>

      <div class="tp-page-numbers">
        <button
          v-for="p in pageNumbers"
          :key="p"
          class="tp-page-num"
          :class="{ 'is-active': p === page }"
          @click="changePage(p)"
          type="button"
        >{{ p }}</button>
      </div>

      <button
        class="tp-page-btn"
        :disabled="page >= totalPages"
        @click="changePage(page + 1)"
        type="button"
      >
        <span>下一页</span>
        <ChevronRight />
      </button>

      <span class="tp-page-info">第 {{ page }} / {{ totalPages }} 页 · 共 {{ total }} 条</span>
    </section>
      </div>
      <div class="tp-content-resize-handle" @mousedown="startContentResize">
        <div class="tp-content-resize-line"></div>
      </div>
      </div>
    </main>

  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, watch, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { createIcons, icons } from 'lucide'
import {
  ArrowLeft, Layers, Star, Globe, DownloadCloud, Download, Loader2,
  Search, RefreshCw, Inbox, User, Users, ThumbsUp, Bookmark,
  MessageSquare, Tag, Play, Trash2, ExternalLink, ChevronLeft, ChevronRight,
  Radar, Flame, Zap, ArrowDownWideNarrow, Clock,
} from 'lucide-vue-next'
import SidebarNav from '@/components/workbench/SidebarNav.vue'
import { topicPoolApi, type TopicPoolItem, type TopicPoolStats, type TopicPoolFetchResponse } from '@/api/topic_pool'

const emit = defineEmits<{
  'start-workflow': [reference: Record<string, unknown>]
}>()

const router = useRouter()

// ===== 侧边栏状态 =====
const SK_COLLAPSED = 'mint_sidebar_collapsed'
const isSidebarCollapsed = ref(localStorage.getItem(SK_COLLAPSED) === '1')
const SK_CARDS_TRANSPARENT = 'mint_cards_transparent'
const cardsTransparent = ref(localStorage.getItem(SK_CARDS_TRANSPARENT) === '1')
const SK_DARK_THEME = 'mint_dark_theme'
const darkTheme = ref(localStorage.getItem(SK_DARK_THEME) === '1')

function toggleSidebar() {
  isSidebarCollapsed.value = !isSidebarCollapsed.value
  localStorage.setItem(SK_COLLAPSED, isSidebarCollapsed.value ? '1' : '0')
}
function toggleCardsTransparent() {
  cardsTransparent.value = !cardsTransparent.value
  localStorage.setItem(SK_CARDS_TRANSPARENT, cardsTransparent.value ? '1' : '0')
}
function toggleTheme(event: MouseEvent) {
  const x = event.clientX
  const y = event.clientY
  const endRadius = Math.hypot(
    Math.max(x, window.innerWidth - x),
    Math.max(y, window.innerHeight - y)
  )
  // @ts-ignore
  if (!document.startViewTransition) {
    darkTheme.value = !darkTheme.value
    localStorage.setItem(SK_DARK_THEME, darkTheme.value ? '1' : '0')
    return
  }
  // @ts-ignore
  const transition = document.startViewTransition(() => {
    darkTheme.value = !darkTheme.value
    localStorage.setItem(SK_DARK_THEME, darkTheme.value ? '1' : '0')
  })
  transition.ready.then(() => {
    document.documentElement.animate(
      {
        clipPath: [
          `circle(0px at ${x}px ${y}px)`,
          `circle(${endRadius}px at ${x}px ${y}px)`,
        ],
      },
      {
        duration: 500,
        easing: 'cubic-bezier(0.4, 0, 0.2, 1)',
        pseudoElement: '::view-transition-new(root)',
      }
    )
  })
}
function handleNavClick(pageName: string) {
  if (pageName === 'topic-pool') return
  router.push({ path: '/workbench', query: pageName === 'workflow' ? {} : { page: pageName } })
}
function goToEco() {
  router.push('/eco')
}

// ===== 状态 =====
const items = ref<TopicPoolItem[]>([])
const stats = ref<TopicPoolStats>({ total: 0, favorited: 0, monitor_count: 0, avg_heat_score: 0, platforms: {}, emotions: {} })
const loading = ref(false)

const filters = reactive({
  platform: '',          // '' = 全部
  keyword: '',
  favorited_only: false,
  auto_source: '' as '' | 'manual' | 'monitor',  // '' = 全部
  sort: 'created_desc' as 'created_desc' | 'heat_desc',
})
const page = ref(1)
const size = ref(20)
const total = ref(0)

// 平台分类标签（用于分类切换栏）
const platformTabs = [
  { value: 'xiaohongshu', label: '小红书' },
  { value: 'hackernews', label: 'HackerNews' },
  { value: 'reddit', label: 'Reddit' },
  { value: 'tavily', label: 'Tavily' },
  { value: 'github', label: 'GitHub' },
]

// ===== 抓取状态 =====
const fetching = ref(false)
const fetchForm = reactive({
  keyword: '',
  platform: 'xiaohongshu',  // 默认小红书（用户核心需求）
})
const fetchMessage = ref('')  // 抓取结果提示

// ===== 监控抓取状态 =====
const monitorFetching = ref(false)
const monitorMessage = ref('')

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / size.value)))
const platformStatsCount = computed(() => Object.keys(stats.value.platforms || {}).length)

// 分页页码列表（当前页前后各 2 个，共最多 5 个）
const pageNumbers = computed(() => {
  const cur = page.value
  const tp = totalPages.value
  const arr: number[] = []
  const start = Math.max(1, cur - 2)
  const end = Math.min(tp, start + 4)
  const realStart = Math.max(1, end - 4)
  for (let i = realStart; i <= end; i++) arr.push(i)
  return arr
})

// ===== 数据加载 =====
async function loadList() {
  loading.value = true
  try {
    const resp = await topicPoolApi.list({
      platform: filters.platform || undefined,
      keyword: filters.keyword.trim() || undefined,
      favorited_only: filters.favorited_only || undefined,
      auto_source: filters.auto_source || undefined,
      sort: filters.sort,
      page: page.value,
      size: size.value,
    })
    items.value = resp.items || []
    total.value = resp.total || 0
    // 修正后端返回的实际页码
    if (resp.page && resp.page !== page.value) {
      page.value = resp.page
    }
  } catch (e) {
    console.error('加载选题列表失败:', e)
    items.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

async function loadStats() {
  try {
    const resp = await topicPoolApi.getStats()
    stats.value = resp
  } catch (e) {
    console.error('加载统计失败:', e)
  }
}

// ===== 操作 =====
async function toggleFavorite(item: TopicPoolItem) {
  const prev = item.is_favorited
  item.is_favorited = !prev  // 乐观更新
  try {
    const resp = await topicPoolApi.toggleFavorite(item.id)
    item.is_favorited = resp.is_favorited
    loadStats()
  } catch (e) {
    console.error('切换收藏失败:', e)
    item.is_favorited = prev  // 回滚
  }
}

async function deleteItem(item: TopicPoolItem) {
  if (!window.confirm(`确认删除选题「${item.title}」？此操作不可撤销。`)) return
  try {
    await topicPoolApi.deleteItem(item.id)
    items.value = items.value.filter(i => i.id !== item.id)
    total.value = Math.max(0, total.value - 1)
    loadStats()
  } catch (e) {
    console.error('删除失败:', e)
  }
}

// ===== 主动抓取 =====
async function doFetch() {
  const keyword = fetchForm.keyword.trim()
  if (!keyword || fetching.value) return

  fetching.value = true
  fetchMessage.value = ''
  try {
    const resp: TopicPoolFetchResponse = await topicPoolApi.fetch({
      keyword,
      platform: fetchForm.platform,
      limit: 100,
    })

    if (resp.error) {
      fetchMessage.value = `抓取失败：${resp.error}`
      // 失败提示保留，不自动清空，让用户看清楚
    } else if (resp.saved_count > 0) {
      fetchMessage.value = `成功抓取 ${resp.saved_count} 条新内容（跳过 ${resp.skipped_duplicate} 条重复）`
      // 刷新列表和统计
      // 如果当前筛选的平台与抓取平台不同，切换到抓取的平台
      if (fetchForm.platform && filters.platform !== fetchForm.platform) {
        filters.platform = fetchForm.platform
      } else {
        await loadList()
        loadStats()
      }
      // 成功提示 5 秒后自动清除
      setTimeout(() => { fetchMessage.value = '' }, 5000)
    } else if (resp.fetched_count > 0 && resp.saved_count === 0) {
      fetchMessage.value = `抓取到 ${resp.fetched_count} 条内容，但全部已存在（重复跳过）`
      setTimeout(() => { fetchMessage.value = '' }, 5000)
    } else {
      fetchMessage.value = '未抓取到相关内容，请尝试其他关键词'
      setTimeout(() => { fetchMessage.value = '' }, 5000)
    }
  } catch (e: any) {
    fetchMessage.value = `抓取失败：${e?.response?.data?.detail || e?.message || '未知错误'}`
  } finally {
    fetching.value = false
  }
}

function refresh() {
  loadList()
  loadStats()
}

// ===== 监控抓取（MonitorAgent）=====
async function doMonitorFetch() {
  if (monitorFetching.value) return
  monitorFetching.value = true
  monitorMessage.value = ''
  try {
    const resp = await topicPoolApi.monitorFetch()
    const r = resp.result
    monitorMessage.value = `监控抓取完成：新增 ${r.new} 条，更新 ${r.updated} 条，跳过 ${r.skipped} 条，失败 ${r.failed} 条`
    await Promise.all([loadList(), loadStats()])
    setTimeout(() => { monitorMessage.value = '' }, 6000)
  } catch (e: any) {
    monitorMessage.value = `监控抓取失败：${e?.response?.data?.detail || e?.message || '未知错误'}`
  } finally {
    monitorFetching.value = false
  }
}

// ===== 排序切换 =====
function toggleSort() {
  filters.sort = filters.sort === 'heat_desc' ? 'created_desc' : 'heat_desc'
  if (page.value === 1) loadList()
  else page.value = 1
}

// ===== 热度状态样式类 =====
function heatStatusClass(status: string): string {
  if (status === '活跃') return 'active'
  if (status === '衰退') return 'decay'
  return 'expired'
}

function changePage(p: number) {
  if (p < 1 || p > totalPages.value || p === page.value) return
  page.value = p
}

// ===== 跳转到详情页 =====
function goDetail(id: string) {
  router.push(`/topic-pool/${id}`)
}

// ===== 从选题池发起新工作流 =====
// 把选题条目存到 sessionStorage（避免 URL 参数过长），跳转到工作台
// 工作台 onMounted 时读取并预填搜索框 + 设置 reference
function startWorkflowFromTopic(item: TopicPoolItem) {
  const reference = {
    title: item.title,
    summary: item.summary || '',
    url: item.url || '',
    platform: item.platform,
    author: item.author || '',
    likes: item.likes || 0,
    comments: item.comments || 0,
    collects: item.collects || 0,
    shares: item.shares || 0,
    source_keyword: item.source_keyword || '',
  }
  sessionStorage.setItem('pending_topic_reference', JSON.stringify(reference))
  router.push('/workbench')
}

// ===== 筛选联动 =====
// 关键词搜索：防抖 350ms
let keywordTimer: number | undefined
watch(() => filters.keyword, () => {
  if (keywordTimer) window.clearTimeout(keywordTimer)
  keywordTimer = window.setTimeout(() => {
    if (page.value === 1) {
      loadList()
    } else {
      page.value = 1  // page watcher 会触发 loadList
    }
  }, 350)
})

// 平台 / 收藏切换：重置到第一页
watch(() => filters.platform, () => {
  if (page.value === 1) loadList()
  else page.value = 1
})
watch(() => filters.favorited_only, () => {
  if (page.value === 1) loadList()
  else page.value = 1
})
watch(() => filters.auto_source, () => {
  if (page.value === 1) loadList()
  else page.value = 1
})

// 翻页
watch(page, () => loadList())

// ===== 数字格式化（万/亿）=====
function formatNum(n: number): string {
  if (n == null || isNaN(n)) return '0'
  if (n >= 100000000) return (n / 100000000).toFixed(1).replace(/\.0$/, '') + '亿'
  if (n >= 10000) return (n / 10000).toFixed(1).replace(/\.0$/, '') + '万'
  return String(n)
}

// ===== 平台标签样式 =====
function platformStyle(platform: string) {
  const p = (platform || '').toLowerCase()
  let color = '#64748B'
  if (p === 'xiaohongshu') color = '#FF2442'
  else if (p === 'hackernews') color = '#FF6600'
  else if (p === 'reddit') color = '#FF4500'
  else if (p === 'tavily') color = '#FF2442'
  else if (p === 'github') color = '#24292E'
  const r = parseInt(color.slice(1, 3), 16)
  const g = parseInt(color.slice(3, 5), 16)
  const b = parseInt(color.slice(5, 7), 16)
  return {
    color,
    backgroundColor: `rgba(${r}, ${g}, ${b}, 0.12)`,
  }
}

// 封面图加载失败记录
const coverImgFailed = ref<Record<string, boolean>>({})

function hasCoverImg(item: TopicPoolItem): boolean {
  return !!(item.cover_img && !coverImgFailed.value[item.id])
}

function safeImageUrl(url: string): string {
  if (!url) return ''
  const u = url.trim()
  if (u.startsWith('data:image')) return u
  return u.replace(/^http:/, 'https:')
}

function onCoverImgError(_e: Event, item: TopicPoolItem) {
  coverImgFailed.value[item.id] = true
}

function platformLabel(platform: string) {
  const p = (platform || '').toLowerCase()
  if (p === 'xiaohongshu') return '小红书'
  if (p === 'hackernews') return 'HackerNews'
  if (p === 'reddit') return 'Reddit'
  if (p === 'tavily') return 'Tavily'
  if (p === 'github') return 'GitHub'
  return platform || '未知'
}

// ===== 初始化 =====
// ===== 侧边栏拖拽调整宽度（Codex 风格）=====
const SK_SIDEBAR_WIDTH = 'mint_sidebar_width'
const sidebarResizing = ref(false)
function applySidebarWidth(w: number) {
  const el = document.querySelector('.tp-shell .mint-sidebar') as HTMLElement | null
  if (el) el.style.width = w + 'px'
}
function startSidebarResize(e: MouseEvent) {
  e.preventDefault()
  sidebarResizing.value = true
  const shell = document.querySelector('.tp-shell') as HTMLElement | null
  if (shell) shell.classList.add('tp-resizing')
  const startX = e.clientX
  const sidebarEl = document.querySelector('.tp-shell .mint-sidebar') as HTMLElement | null
  const startW = sidebarEl ? sidebarEl.offsetWidth : 192
  document.body.style.cursor = 'col-resize'
  document.body.style.userSelect = 'none'
  const onMove = (ev: MouseEvent) => {
    const delta = ev.clientX - startX
    const newW = Math.min(600, Math.max(170, startW + delta))
    applySidebarWidth(newW)
  }
  const onUp = () => {
    sidebarResizing.value = false
    if (shell) shell.classList.remove('tp-resizing')
    document.body.style.cursor = ''
    document.body.style.userSelect = ''
    const cur = (document.querySelector('.tp-shell .mint-sidebar') as HTMLElement | null)?.offsetWidth || 192
    localStorage.setItem(SK_SIDEBAR_WIDTH, String(cur))
    document.removeEventListener('mousemove', onMove)
    document.removeEventListener('mouseup', onUp)
  }
  document.addEventListener('mousemove', onMove)
  document.addEventListener('mouseup', onUp)
}

onMounted(() => {
  loadList()
  loadStats()
  nextTick(() => createIcons({ icons }))
  // 恢复保存的侧边栏宽度
  const savedW = localStorage.getItem(SK_SIDEBAR_WIDTH)
  if (savedW && !isSidebarCollapsed.value) applySidebarWidth(Number(savedW))
})
</script>

<style scoped>
.tp-page {
  --ma-blue-50: #FFF1F3;
  --ma-blue-100: #FFE4E8;
  --ma-blue-200: #FFCDD5;
  --ma-blue-300: #FF9AA7;
  --ma-blue-400: #FF2442;
  --ma-blue-500: #FF2442;
  --ma-blue-600: #FF2442;
  --ma-blue-700: #FF2442;
  --ma-blue-800: #FF2442;
  --ma-blue-900: #FF2442;
  --ma-accent: #FFF1F3;
  --ma-accent-foreground: #FF2442;
  flex: 1;
  min-width: 0;
  height: 100%;
  background: var(--ma-bg-subtle);
  font-family: var(--ma-font-sans);
  color: var(--ma-text-primary);
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  padding: 56px 20px 16px;
}
/* 选题池内容卡片包装层：覆盖全局 mint-content-card-wrapper 的 row 布局，打通滚动链路 */
.tp-content-card-wrapper {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  min-width: 0;
  overflow: hidden;
}

.tp-content-card {
  flex: 1;
  min-height: 0;
min-width: 0;
  background: #FFFFFF;
  border-radius: 16px;
  border: 1px solid var(--ma-border-default);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* ===== 顶部栏 ===== */
.tp-topbar {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 14px 32px;
  background: var(--ma-bg-base);
  border-bottom: 1px solid var(--ma-border-default);
  flex-shrink: 0;
  z-index: 10;
}
.tp-back-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 14px;
  background: var(--ma-bg-base);
  border: 1px solid var(--ma-border-default);
  border-radius: var(--ma-radius-sm);
  color: var(--ma-text-secondary);
  font-size: var(--ma-font-sm);
  font-family: inherit;
  cursor: pointer;
  transition: border-color 0.15s ease, color 0.15s ease;
}
.tp-back-btn:hover {
  border-color: var(--ma-blue-500);
  color: var(--ma-blue-500);
}
.tp-back-btn svg {
  width: 16px;
  height: 16px;
}
.tp-title {
  font-size: var(--ma-font-xl);
  font-weight: 600;
  color: var(--ma-text-primary);
  margin: 0;
  letter-spacing: -0.01em;
}
.tp-topbar-spacer {
  flex: 1;
}

/* ===== 容器（主滚动区）===== */
.tp-container {
  max-width: none;
  width: 100%;
  margin: 0;
  padding: 20px 24px 16px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  overscroll-behavior: contain;
  -webkit-overflow-scrolling: touch;
  scrollbar-width: auto;
  scrollbar-color: initial;
}
/* WebKit 滚动条样式 */
.tp-container::-webkit-scrollbar {
  width: auto;
}
.tp-container::-webkit-scrollbar-track {
  background: initial;
}
.tp-container::-webkit-scrollbar-thumb {
  background: initial;
  border-radius: initial;
}
.tp-container::-webkit-scrollbar-thumb:hover {
  background: initial;
}

/* ===== 统计栏 ===== */
.tp-stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  flex-shrink: 0;
}
.tp-stat-card {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 20px 24px;
  background: transparent;
  border: none;
  border-radius: var(--ma-radius-md);
  box-shadow: none;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}
.tp-stat-card:hover {
  border-color: var(--ma-blue-200);
  box-shadow: var(--ma-shadow-sm);
}
.tp-stat-icon {
  width: 44px;
  height: 44px;
  border-radius: var(--ma-radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--ma-blue-50);
  color: var(--ma-blue-500);
  flex-shrink: 0;
}
.tp-stat-icon svg {
  width: 22px;
  height: 22px;
}
.tp-stat-body {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.tp-stat-num {
  font-size: 26px;
  font-weight: 700;
  color: var(--ma-text-primary);
  line-height: 1.1;
  font-variant-numeric: tabular-nums;
  font-family: var(--ma-font-mono);
}
.tp-stat-label {
  font-size: var(--ma-font-xs);
  color: var(--ma-text-tertiary);
  letter-spacing: 0.02em;
}

/* ===== 抓取区域 ===== */
.tp-fetch {
  padding: 16px 20px;
  background: transparent;
  border: none;
  border-radius: var(--ma-radius-md);
  box-shadow: none;
  flex-shrink: 0;
  position: relative;
  z-index: 1;
}
.tp-fetch-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: var(--ma-font-md);
  font-weight: 600;
  color: var(--ma-text-primary);
  margin-bottom: 12px;
}
.tp-fetch-title svg {
  width: 18px;
  height: 18px;
  color: var(--ma-blue-500);
}
.tp-fetch-form {
  display: flex;
  gap: 10px;
  align-items: center;
}
.tp-fetch-input {
  width: 600px;
  flex-shrink: 0;
  height: 38px;
  padding: 0 14px;
  border: 1px solid var(--ma-border-default);
  border-radius: 12px;
  font-size: var(--ma-font-sm);
  font-family: inherit;
  color: var(--ma-text-primary);
  background: #F5F6F7 !important;
  outline: none;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
  box-sizing: border-box;
}
.tp-fetch-input:focus {
  border-color: var(--ma-border-default);
  box-shadow: none;
}
.tp-fetch-input::placeholder {
  color: #9CA3AF !important;
  opacity: 1 !important;
}
.tp-fetch-input:disabled {
  background: var(--ma-bg-subtle);
  cursor: not-allowed;
}
.tp-fetch-select {
  height: 38px;
  padding: 0 28px 0 12px;
  border: 1px solid var(--ma-border-default);
  border-radius: var(--ma-radius-sm);
  font-size: var(--ma-font-sm);
  font-family: inherit;
  color: var(--ma-text-primary);
  background: var(--ma-bg-base);
  cursor: pointer;
  outline: none;
  flex-shrink: 0;
}
.tp-fetch-select:focus {
  border-color: var(--ma-blue-500);
  box-shadow: var(--ma-shadow-focus);
}
.tp-fetch-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 38px;
  padding: 0 20px;
  border: 1px solid var(--ma-blue-500);
  background: var(--ma-blue-500);
  color: #fff;
  font-size: var(--ma-font-sm);
  font-weight: 500;
  font-family: inherit;
  border-radius: var(--ma-radius-sm);
  cursor: pointer;
  flex-shrink: 0;
  transition: background-color 0.15s ease, border-color 0.15s ease;
}
.tp-fetch-btn:hover:not(:disabled) {
  background: var(--ma-blue-600);
  border-color: var(--ma-blue-600);
}
.tp-fetch-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.tp-fetch-btn svg {
  width: 16px;
  height: 16px;
}
.tp-fetch-hint {
  margin-top: 10px;
  font-size: var(--ma-font-xs);
  color: var(--ma-text-tertiary);
  line-height: 1.5;
}
.tp-fetch-msg {
  margin-top: 10px;
  padding: 8px 12px;
  font-size: var(--ma-font-sm);
  color: var(--ma-accent-foreground);
  background: var(--ma-accent);
  border-radius: var(--ma-radius-sm);
  line-height: 1.5;
}

/* ===== 平台分类标签栏 ===== */
.tp-platform-tabs {
  display: flex;
  gap: 8px;
  padding: 0;
  background: transparent;
  border: none;
  border-radius: 0;
  box-shadow: none;
  overflow-x: auto;
  flex-shrink: 0;
  position: relative;
  z-index: 2;
}
.tp-tab {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 34px;
  padding: 0 16px;
  border: none;
  background: transparent;
  color: var(--ma-text-secondary);
  font-size: var(--ma-font-sm);
  font-weight: 700;
  font-family: inherit;
  border-radius: var(--ma-radius-sm);
  cursor: pointer;
  white-space: nowrap;
  transition: background-color 0.15s ease, color 0.15s ease;
}
.tp-tab:hover {
  background: var(--ma-bg-subtle);
  color: var(--ma-text-primary);
}
.tp-tab.is-active {
  background: var(--ma-blue-500);
  color: #fff;
}
.tp-tab-count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 20px;
  height: 18px;
  padding: 0 6px;
  font-size: var(--ma-font-xs);
  font-weight: 600;
  border-radius: var(--ma-radius-full);
  background: rgba(0, 0, 0, 0.08);
  color: inherit;
}
.tp-tab.is-active .tp-tab-count {
  background: rgba(255, 255, 255, 0.25);
}

/* ===== 筛选栏 ===== */
.tp-filters {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 16px 20px;
  background: var(--ma-bg-base);
  border: none;
  border-radius: var(--ma-radius-md);
  box-shadow: none;
  flex-shrink: 0;
}
.tp-filter-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.tp-filter-search {
  width: 600px;
  flex-shrink: 0;
}
.tp-filter-toggle {
  flex-shrink: 0;
}
.tp-filter-label {
  font-size: var(--ma-font-xs);
  color: var(--ma-text-tertiary);
  font-weight: 500;
  letter-spacing: 0.02em;
}
.tp-select {
  height: 36px;
  width: 160px;
  padding: 0 32px 0 12px;
  border: 1px solid var(--ma-border-default);
  border-radius: var(--ma-radius-sm);
  background-color: var(--ma-bg-base);
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%2364748B' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='6 9 12 15 18 9'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 10px center;
  color: var(--ma-text-primary);
  font-size: var(--ma-font-sm);
  font-family: inherit;
  cursor: pointer;
  outline: none;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
  appearance: none;
  -webkit-appearance: none;
  -moz-appearance: none;
}
.tp-select:focus {
  border-color: var(--ma-blue-500);
  box-shadow: var(--ma-shadow-focus);
}
.tp-search-wrap {
  position: relative;
  width: 100%;
}
.tp-search-icon {
  position: absolute;
  left: 10px;
  top: 50%;
  transform: translateY(-50%);
  width: 16px;
  height: 16px;
  color: var(--ma-text-tertiary);
  pointer-events: none;
}
.tp-input {
  width: 100%;
  height: 36px;
  padding: 0 12px 0 34px;
  border: 1px solid var(--ma-border-default);
  border-radius: 12px;
  background: #F5F6F7 !important;
  color: var(--ma-text-primary);
  font-size: var(--ma-font-sm);
  font-family: inherit;
  outline: none;
  box-sizing: border-box;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}
.tp-input:focus {
  border-color: var(--ma-border-default);
  box-shadow: none;
}
.tp-input::placeholder {
  color: #9CA3AF !important;
  opacity: 1 !important;
}

/* ===== 开关 ===== */
.tp-switch-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: var(--ma-font-sm);
  color: var(--ma-text-secondary);
  cursor: pointer;
  height: 36px;
  user-select: none;
}
.tp-switch {
  position: relative;
  width: 38px;
  height: 22px;
  border: none;
  border-radius: 9999px;
  background: var(--ma-border-strong);
  cursor: pointer;
  transition: background-color 0.2s ease;
  padding: 0;
  flex-shrink: 0;
}
.tp-switch::after {
  content: '';
  position: absolute;
  top: 3px;
  left: 3px;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: #fff;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.15);
  transition: transform 0.2s ease;
}
.tp-switch.is-on {
  background: #6B7280;
}
.tp-switch.is-on::after {
  transform: translateX(16px);
}

/* ===== 内联统计 ===== */
.tp-stat-inline {
  display: inline-flex;
  align-items: center;
  gap: 14px;
  padding: 0 4px;
}
.tp-stat-inline-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  font-weight: 500;
  color: var(--ma-text-secondary, #6B7280);
  white-space: nowrap;
}
.tp-stat-inline-icon {
  width: 14px;
  height: 14px;
  color: var(--ma-text-tertiary, #9CA3AF);
  flex-shrink: 0;
}

.tp-fetch-form .tp-stat-inline {
  margin-left: auto;
}
.tp-filters .tp-stat-inline {
  margin-left: auto;
}

/* ===== 刷新按钮 ===== */
.tp-refresh-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 36px;
  padding: 0 16px;
  border: 1px solid var(--ma-blue-500);
  border-radius: var(--ma-radius-sm);
  background: var(--ma-blue-500);
  color: #fff;
  font-size: var(--ma-font-sm);
  font-weight: 500;
  font-family: inherit;
  cursor: pointer;
  transition: background-color 0.15s ease, border-color 0.15s ease;
  flex-shrink: 0;
}
.tp-refresh-btn:hover:not(:disabled) {
  background: var(--ma-blue-600);
  border-color: var(--ma-blue-600);
}
.tp-refresh-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.tp-refresh-btn svg {
  width: 15px;
  height: 15px;
}

/* ===== 列表区：小红书主页风格瀑布流 ===== */
.tp-list {
  column-count: 5;
  column-gap: 12px;
  min-height: 200px;
}
@media (max-width: 1700px) {
  .tp-list { column-count: 4; }
}
@media (max-width: 1400px) {
  .tp-list { column-count: 3; }
}
@media (max-width: 1100px) {
  .tp-list { column-count: 2; }
}
@media (max-width: 720px) {
  .tp-list { column-count: 1; }
}

/* 加载中 */
.tp-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 64px 0;
  color: var(--ma-text-secondary);
  font-size: var(--ma-font-sm);
  background: var(--ma-bg-base);
  border: 1px solid var(--ma-border-default);
  border-radius: var(--ma-radius-md);
}
.tp-loading svg {
  width: 18px;
  height: 18px;
  color: var(--ma-blue-500);
}
.tp-spin {
  animation: tp-spin 1s linear infinite;
}
@keyframes tp-spin {
  to { transform: rotate(360deg); }
}

/* 空状态 */
.tp-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 64px 0;
  background: var(--ma-bg-base);
  border: 1px solid var(--ma-border-default);
  border-radius: var(--ma-radius-md);
}
.tp-empty svg {
  width: 40px;
  height: 40px;
  color: var(--ma-text-tertiary);
  margin-bottom: 4px;
}
.tp-empty-title {
  font-size: var(--ma-font-md);
  font-weight: 600;
  color: var(--ma-text-secondary);
}
.tp-empty-desc {
  font-size: var(--ma-font-sm);
  color: var(--ma-text-tertiary);
}

/* ===== 选题卡片 ===== */
@keyframes tp-card-enter {
  from { opacity: 0; }
  to { opacity: 1; }
}
.tp-card {
  display: block;
  break-inside: avoid;
  page-break-inside: avoid;
  margin-bottom: 14px;
  background: var(--ma-bg-base);
  border: 1px solid var(--ma-border-default);
  border-radius: 16px;
  overflow: hidden;
  animation: tp-card-enter 0.4s ease both;
  transition: transform 0.25s cubic-bezier(0.16, 1, 0.3, 1),
              box-shadow 0.25s ease,
              border-color 0.25s ease;
}
.tp-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 10px 28px rgba(17, 24, 39, 0.12);
  border-color: rgba(59, 108, 246, 0.35);
}

/* 封面区 */
.tp-card-cover {
  position: relative;
  overflow: hidden;
  background: var(--ma-bg-subtle);
}
.tp-card-cover img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
  transition: transform 0.45s cubic-bezier(0.16, 1, 0.3, 1);
}
.tp-card:hover .tp-card-cover img {
  transform: scale(1.06);
}
.tp-card-cover-fallback,
.tp-cover-letter { display: none; }

/* 无封面图卡片：内容区扩展 */
.tp-card:not(:has(.tp-card-cover)) .tp-card-body {
  padding-top: 14px;
}
.tp-no-cover-author {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--ma-text-tertiary);
}
.tp-no-cover-author svg {
  width: 13px;
  height: 13px;
}

/* 底部操作区：发起工作流按钮 + 原文链接 */
.tp-workflow-btn {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 3px 8px;
  font-size: 11px;
  font-weight: 500;
  color: #fff;
  background: #FF2442;
  border: none;
  border-radius: 5px;
  cursor: pointer;
  transition: background 0.15s ease;
}
.tp-workflow-btn:hover {
  background: #E0203A;
}
.tp-workflow-btn svg {
  width: 12px;
  height: 12px;
}
.tp-orig-link {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  color: var(--ma-text-tertiary);
  border-radius: 5px;
  transition: color 0.15s, background 0.15s;
}
.tp-orig-link:hover {
  color: #FF2442;
  background: rgba(255, 36, 66, 0.08);
}
.tp-orig-link svg {
  width: 13px;
  height: 13px;
}

/* 封面上的悬浮标签 */
.tp-platform-tag-float {
  position: absolute;
  top: 8px;
  left: 8px;
  backdrop-filter: blur(6px);
  -webkit-backdrop-filter: blur(6px);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.12);
}
.tp-img-count {
  position: absolute;
  right: 8px;
  bottom: 8px;
  padding: 2px 7px;
  border-radius: 4px;
  background: rgba(17, 24, 39, 0.72);
  backdrop-filter: blur(4px);
  -webkit-backdrop-filter: blur(4px);
  color: #fff;
  font-size: 11px;
  line-height: 1.4;
}
.tp-heat-badge {
  position: absolute;
  top: 8px;
  right: 8px;
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 2px 8px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.92);
  backdrop-filter: blur(6px);
  -webkit-backdrop-filter: blur(6px);
  font-size: 11px;
  font-weight: 600;
  color: #EF4444;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}
.tp-heat-badge svg {
  width: 12px;
  height: 12px;
}

/* hover 时浮现的快捷操作 */
.tp-cover-actions {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  background: rgba(17, 24, 39, 0.42);
  backdrop-filter: blur(2px);
  -webkit-backdrop-filter: blur(2px);
  opacity: 0;
  transition: opacity 0.25s ease;
}
.tp-card:hover .tp-cover-actions {
  opacity: 1;
}
.tp-cover-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 34px;
  padding: 0 16px;
  border: none;
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.95);
  color: #1F2937;
  font-size: 13px;
  font-weight: 500;
  font-family: inherit;
  cursor: pointer;
  text-decoration: none;
  transition: transform 0.15s ease, background 0.15s ease;
  transform: translateY(8px);
}
.tp-card:hover .tp-cover-btn {
  transform: translateY(0);
}
.tp-cover-btn:hover {
  background: #fff;
  transform: translateY(-1px);
}
.tp-cover-btn-primary {
  background: #3B6CF6;
  color: #fff;
}
.tp-cover-btn-primary:hover {
  background: #2B5AE0;
}
.tp-cover-btn svg {
  width: 14px;
  height: 14px;
}

/* 内容区 */
.tp-card-body {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 12px 14px 10px;
}
.tp-card-meta-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.tp-card-monitor {
  font-size: 11px;
  color: var(--ma-text-tertiary);
  font-variant-numeric: tabular-nums;
}
.tp-card-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--ma-text-primary);
  line-height: 1.45;
  margin: 0;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  transition: color 0.2s ease;
}
.tp-card:hover .tp-card-title {
  color: var(--ma-blue-600, #3B6CF6);
}
.tp-card-title-clickable {
  cursor: pointer;
  transition: color 0.15s ease;
}
.tp-card-title-clickable:hover {
  color: var(--ma-blue-500, #3B6CF6);
  text-decoration: underline;
  text-decoration-color: rgba(59, 108, 246, 0.4);
  text-underline-offset: 2px;
}
.tp-card-summary {
  font-size: 13px;
  color: var(--ma-text-secondary);
  line-height: 1.5;
  margin: 0;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.tp-card-dims {
  display: flex;
  gap: 5px;
  flex-wrap: wrap;
  margin-top: 2px;
}
.tp-card-dims span {
  font-size: 11px;
  color: var(--ma-text-tertiary);
  padding: 1px 7px;
  background: var(--ma-bg-subtle);
  border-radius: 12px;
}

/* 底部 */
.tp-card-bottom {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 8px 14px;
  border-top: 1px solid var(--ma-border-subtle, #F1F5F9);
}
.tp-metrics {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.tp-metric {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: 12px;
  color: var(--ma-text-tertiary);
  font-variant-numeric: tabular-nums;
}
.tp-metric svg {
  width: 13px;
  height: 13px;
}
.tp-actions {
  display: flex;
  align-items: center;
  gap: 2px;
  opacity: 0.5;
  transition: opacity 0.2s ease;
}
.tp-card:hover .tp-actions {
  opacity: 1;
}
.tp-icon-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--ma-text-tertiary);
  cursor: pointer;
  transition: background 0.15s ease, color 0.15s ease, transform 0.15s ease;
}
.tp-icon-btn:hover {
  background: var(--ma-bg-subtle);
  color: var(--ma-text-secondary);
  transform: scale(1.1);
}
.tp-icon-btn svg {
  width: 15px;
  height: 15px;
}
.tp-icon-btn.is-favorited {
  color: #F59E0B;
}
.tp-icon-btn.is-disabled {
  opacity: 0.3;
  cursor: not-allowed;
}
.tp-author {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: 12px;
  color: var(--ma-text-tertiary);
  max-width: 160px;
}
.tp-author svg {
  width: 12px;
  height: 12px;
  flex-shrink: 0;
}
.tp-author span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.tp-platform-tag {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 3px;
  font-size: 11px;
  font-weight: 500;
  line-height: 1.5;
}

/* ===== 分页（tp-page 底部固定栏） ===== */
.tp-pagination {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  flex-wrap: wrap;
  padding: 10px 20px;
  margin: 0 24px;
  background: var(--ma-bg-base, #fff);
  border-top: 1px solid var(--ma-border-subtle, #F1F5F9);
  border-radius: 12px;
}
.tp-page-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 34px;
  padding: 0 14px;
  border: 1px solid var(--ma-border-default);
  border-radius: var(--ma-radius-sm);
  background: var(--ma-bg-base);
  color: var(--ma-text-secondary);
  font-size: var(--ma-font-sm);
  font-family: inherit;
  cursor: pointer;
  transition: border-color 0.15s ease, color 0.15s ease;
}
.tp-page-btn:hover:not(:disabled) {
  border-color: var(--ma-blue-500);
  color: var(--ma-blue-500);
}
.tp-page-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.tp-page-btn svg {
  width: 14px;
  height: 14px;
}
.tp-page-numbers {
  display: flex;
  align-items: center;
  gap: 4px;
}
.tp-page-num {
  min-width: 34px;
  height: 34px;
  padding: 0 8px;
  border: 1px solid var(--ma-blue-300);
  border-radius: var(--ma-radius-sm);
  background: var(--ma-bg-base);
  color: var(--ma-blue-600);
  font-size: var(--ma-font-sm);
  font-family: var(--ma-font-mono);
  font-variant-numeric: tabular-nums;
  cursor: pointer;
  transition: border-color 0.15s ease, background-color 0.15s ease, color 0.15s ease;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.tp-page-num:hover:not(.is-active) {
  border-color: var(--ma-blue-500);
}
.tp-page-num.is-active {
  background: var(--ma-blue-500);
  border-color: var(--ma-blue-500);
  color: #fff;
  cursor: default;
}
.tp-page-info {
  font-size: var(--ma-font-xs);
  color: var(--ma-text-tertiary);
  margin-left: 12px;
  font-variant-numeric: tabular-nums;
}

/* ===== v6 监控融合样式 ===== */
.tp-monitor-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  margin-left: 12px;
  padding: 5px 12px;
  background: var(--mint-primary, #10B981);
  border: none;
  border-radius: 6px;
  color: #FFFFFF;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.15s;
}
.tp-monitor-btn:hover:not(:disabled) { background: #059669; }
.tp-monitor-btn:disabled { opacity: 0.6; cursor: not-allowed; }
.tp-monitor-btn svg { width: 14px; height: 14px; }

.tp-fetch-msg-monitor {
  background: #ECFDF5;
  border-color: #A7F3D0;
  color: #065F46;
}

.tp-filter-source, .tp-filter-sort {
  display: flex;
  align-items: center;
  gap: 8px;
}
.tp-source-group { display: flex; gap: 6px; }
.tp-source-chip {
  padding: 4px 10px;
  background: #F5F6F7 !important;
  border: 1px solid var(--ma-border, #E5E7EB);
  border-radius: 6px;
  font-size: 13px;
  color: var(--ma-text-secondary, #374151);
  cursor: pointer;
  transition: all 0.15s;
  height: 36px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.tp-source-chip:hover { border-color: #9CA3AF; }
.tp-source-chip.is-active {
  background: #E5E7EB;
  border-color: #6B7280;
  color: #374151;
}
.tp-sort-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 5px 12px;
  height: 36px;
  background: #F5F6F7 !important;
  border: 1px solid var(--ma-border, #E5E7EB);
  border-radius: 6px;
  font-size: 13px;
  color: var(--ma-text-secondary, #374151);
  cursor: pointer;
  transition: all 0.15s;
}
.tp-sort-btn:hover { border-color: #9CA3AF; }
.tp-sort-btn svg { width: 14px; height: 14px; }

.tp-heat-status-active { color: #047857; }
.tp-heat-status-decay { color: #B45309; }
.tp-heat-status-expired { color: #6B7280; }

/* 选题池专用：去掉 mint-shell 右侧空列，主区撑满（3列：侧边栏 + 拖拽条 + 主区） */
.tp-shell {
  grid-template-columns: auto auto 1fr !important;
}
.tp-shell.mint-collapsed {
  grid-template-columns: 56px 1fr !important;
}

/* ===== 侧边栏拖拽条（Codex 风格）===== */
.tp-sidebar-resizer {
  position: relative;
  width: 6px;
  cursor: col-resize;
  flex-shrink: 0;
  align-self: stretch;
  z-index: 5;
  transition: background 0.15s ease;
}
.tp-sidebar-resizer-line {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: 2px;
  height: 40px;
  border-radius: 2px;
  background: #D1D5DB;
  transition: background 0.15s ease, height 0.15s ease;
}
.tp-sidebar-resizer:hover {
  background: rgba(59, 108, 246, 0.08);
}
.tp-sidebar-resizer:hover .tp-sidebar-resizer-line {
  background: #3B6CF6;
  height: 60px;
}
.tp-sidebar-resizer:active,
.tp-shell.tp-resizing .tp-sidebar-resizer {
  background: rgba(59, 108, 246, 0.12);
}
.tp-shell.tp-resizing .tp-sidebar-resizer-line {
  background: #3B6CF6;
  height: 60px;
}
/* 拖拽中禁用过渡，跟随鼠标实时变化 */
.tp-shell.tp-resizing .mint-sidebar {
  transition: none !important;
}
</style>
