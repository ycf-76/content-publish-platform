<template>
<div class="min-h-screen" style="position: relative;">

  <div class="mint-shell da-shell" :class="{ 'mint-collapsed': isSidebarCollapsed }" :style="{ '--left-sidebar-width': leftSidebarWidth + 'px' }">

    <SidebarNav
      :current-page="'portfolio'"
      :is-collapsed="isSidebarCollapsed"
      @nav-click="handleNavClick"
      @toggle-sidebar="toggleSidebar"
      @go-eco="goToEco"
      @open-settings="openSettings"
      @new-workflow="goToWorkbench"
      @new-chat="goToChat"
    />

    <div v-if="!isSidebarCollapsed" class="da-sidebar-resizer" @mousedown="startLeftResize"><div class="da-sidebar-resizer-line"></div></div>

    <main class="mw-page">
      <div class="da-content-card-wrapper">
      <div class="da-content-card">

        <div class="mw-container">

          <!-- ====== 顶部 Tab 栏 + 搜索 ====== -->
          <div class="mw-header">
            <div class="mw-tabs">
              <button
                v-for="tab in statusTabs"
                :key="tab.key"
                class="mw-tab"
                :class="{ 'mw-tab-active': activeStatus === tab.key }"
                @click="switchStatus(tab.key)"
              >{{ tab.label }}<span v-if="tab.count !== undefined" class="mw-tab-count">{{ tab.count }}</span></button>
            </div>
            <div class="mw-search">
              <Search :size="16" />
              <input
                v-model="searchQuery"
                type="text"
                placeholder="搜索笔记"
                @input="handleSearch"
              />
            </div>
          </div>

          <!-- ====== 作品卡片网格 ====== -->
          <div v-if="!loading && filteredWorks.length > 0" class="mw-grid">
            <div
              v-for="w in filteredWorks"
              :key="w.id"
              class="mw-card"
              @click="goToDetail(w)"
            >
              <div class="mw-cover">
                <video v-if="w.video_url" class="mw-video" :src="w.video_url" controls preload="metadata"></video>
                <img v-else-if="w.cover_img_url" :src="w.cover_img_url" alt="" @error="onCoverError($event, w.cover_img_url)" />
                <div v-else class="mw-cover-placeholder">
                  <ImageIcon :size="32" />
                </div>
              </div>
              <div class="mw-body">
                <div class="mw-title-row">
                  <span class="mw-title">{{ w.title || w.topic || '无标题' }}</span>
                  <div class="mw-actions" @click.stop>
                    <button class="mw-action-btn" title="分享"><Share2 :size="16" /></button>
                    <button class="mw-action-btn" title="上传"><Upload :size="16" /></button>
                    <button class="mw-action-btn" title="数据"><BarChart3 :size="16" /></button>
                    <button class="mw-action-btn" title="编辑"><Pencil :size="16" /></button>
                    <button class="mw-action-btn mw-action-delete" title="删除" @click="handleDeleteWork(w)"><Trash2 :size="16" /></button>
                  </div>
                </div>
                <div class="mw-date">{{ formatFullDate(w.published_at || w.collected_at) }}</div>
                <div class="mw-stats">
                  <span class="mw-stat"><Eye :size="14" /> {{ (w.collected_likes ?? 0) + (w.collected_collects ?? 0) + (w.collected_comments ?? 0) }}</span>
                  <span class="mw-stat"><MessageCircle :size="14" /> {{ w.collected_comments ?? 0 }}</span>
                  <span class="mw-stat"><Heart :size="14" /> {{ w.collected_likes ?? 0 }}</span>
                  <span class="mw-stat"><Star :size="14" /> {{ w.collected_collects ?? 0 }}</span>
                  <span class="mw-stat"><Share :size="14" /> {{ w.collected_shares ?? 0 }}</span>
                </div>
              </div>
            </div>
          </div>

          <!-- ====== 加载中 ====== -->
          <div v-if="loading" class="mw-loading">
            <div class="mw-spinner"></div>
            <p>加载中...</p>
          </div>

          <!-- ====== 空状态 ====== -->
          <div v-if="!loading && filteredWorks.length === 0" class="mw-empty">
            <div class="mw-empty-icon"><Inbox :size="48" /></div>
            <p class="mw-empty-text">{{ searchQuery ? '没有找到匹配的作品' : (activeStatus === 'all' ? '还没有作品' : `暂无${statusLabel(activeStatus)}作品`) }}</p>
            <button v-if="activeStatus === 'all'" class="mw-btn-primary" @click="goToWorkbench">开始创作</button>
          </div>

          <!-- ====== 分页 ====== -->
          <div v-if="total > pageSize" class="mw-pagination">
            <button class="mw-pg-btn" :disabled="page <= 1" @click="page--; loadWorks()">&lt; 上一页</button>
            <span class="mw-pg-info">{{ page }} / {{ Math.ceil(total / pageSize) }}</span>
            <button class="mw-pg-btn" :disabled="page >= Math.ceil(total / pageSize)" @click="page++; loadWorks()">下一页 &gt;</button>
          </div>

        </div>
      </div>
      </div>
    </main>
  </div>

</div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import {
  Search, Eye, MessageCircle, Heart, Star, Share, Share2, Upload,
  Pencil, Trash2, BarChart3, Inbox, ImageIcon,
} from 'lucide-vue-next'
import SidebarNav from '@/components/workbench/SidebarNav.vue'
import { useWorkStore } from '@/stores/work'
import { useUIState } from '@/composables/useUIState'
import {
  listMyWorks, deleteMyWork,
  type MyWorkItem,
} from '@/api/my_works'

const router = useRouter()
const workStore = useWorkStore()
const { isSidebarCollapsed, toggleSidebar: toggleSidebarBase } = useUIState()

function toggleSidebar() { toggleSidebarBase() }
function handleNavClick(pageName: string) {
  if (pageName === 'home') { router.push('/').catch(() => {}); return }
  if (pageName === 'portfolio') return
  if (pageName === 'my-works') { router.push('/my-works').catch(() => {}); return }
  if (pageName === 'topic-pool') { router.push('/topic-pool').catch(() => {}); return }
  if (pageName === 'task-plans') { router.push('/task-plans').catch(() => {}); return }
  router.push({ path: '/workbench', query: { page: pageName } })
}
function openSettings() {
  window.dispatchEvent(new Event('open-settings'))
}
function goToEco() { router.push('/eco') }
function goToWorkbench() { router.push({ path: '/workbench', query: { page: 'workflow' } }) }
function goToChat() { router.push('/workbench') }

import { useResizeHandle } from '@/composables/useResizeHandle'
const {
  width: leftSidebarWidth,
  isResizing: isLeftResizing,
  startResize: startLeftResize,
  resetWidth: resetLeftSidebarWidth,
} = useResizeHandle({
  direction: 'left',
  minWidth: 170,
  maxWidth: 520,
  storageKey: 'mint-left-sidebar-width-v2',
})

const PLATFORM_MAP: Record<string, string> = { xiaohongshu: '小红书', douyin: '抖音', bilibili: 'B站', wechat_mp: '微信', instagram: 'Instagram', threads: 'Threads', unknown: '未知' }
function platformLabel(p: string | null | undefined): string { return PLATFORM_MAP[p || 'unknown'] || p || '未知' }

const STATUS_LABELS: Record<string, string> = { all: '全部', draft: '未发布', published: '已发布', collected: '已采集', reviewing: '审核中', rejected: '未通过' }
function statusLabel(s: string | null): string { return STATUS_LABELS[s || 'all'] || s || '未知' }

const STATUS_MAP: Record<string, string[]> = {
  all: [],
  published: ['published', 'collected'],
  draft: ['draft'],
  reviewing: ['reviewing'],
  rejected: ['rejected'],
}

const works = ref<MyWorkItem[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const loading = ref(false)
const activeStatus = ref('all')
const searchQuery = ref('')
let _searchTimer: number | null = null

const statusTabs = computed(() => [
  { key: 'all', label: '全部', count: undefined },
  { key: 'published', label: '已发布', count: undefined },
  { key: 'reviewing', label: '审核中', count: undefined },
  { key: 'rejected', label: '未通过', count: undefined },
])

const filteredWorks = computed(() => {
  let list = works.value
  if (searchQuery.value.trim()) {
    const q = searchQuery.value.toLowerCase().trim()
    list = list.filter(w =>
      (w.title || '').toLowerCase().includes(q) ||
      (w.topic || '').toLowerCase().includes(q) ||
      ('tags' in w && (w as any).tags && ((w as any).tags as string[]).some((t: string) => t.toLowerCase().includes(q)))
    )
  }
  return list
})

async function switchStatus(key: string) {
  activeStatus.value = key
  page.value = 1
  await loadWorks()
}

function handleSearch() {
  if (_searchTimer) clearTimeout(_searchTimer)
  _searchTimer = window.setTimeout(() => {}, 300)
}

async function loadWorks() {
  loading.value = true
  try {
    const params: any = { page: page.value, page_size: pageSize.value }
    const statuses = STATUS_MAP[activeStatus.value] || []
    if (statuses.length > 0) params.content_status = statuses.join(',')
    const res = await listMyWorks(params)
    works.value = res.items
    total.value = res.total
  } catch (e: any) { console.error('loadWorks failed:', e) } finally { loading.value = false }
}

function goToDetail(w: MyWorkItem) {
  router.push(`/portfolio/${w.id}?source=published`).catch(() => {})
}

async function handleDeleteWork(w: MyWorkItem) {
  if (!confirm(`确定删除「${w.title || w.topic || '无标题'}」？`)) return
  try {
    const { deleteMyWork: doDelete } = await import('@/api/my_works')
    await doDelete(w.id)
    works.value = works.value.filter(item => item.id !== w.id)
    total.value = Math.max(0, total.value - 1)
    try { await workStore.fetchWorks() } catch (e) { console.error(e) }
  } catch (e: any) {
    console.error('删除失败:', e)
    alert('删除失败：' + (e.response?.data?.detail || e.message))
  }
}

function formatFullDate(d: string | null): string {
  if (!d) return '—'
  const date = new Date(d)
  const y = date.getFullYear()
  const m = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  const h = String(date.getHours()).padStart(2, '0')
  const min = String(date.getMinutes()).padStart(2, '0')
  return `${y}-${m}-${day} ${h}:${min}`
}

function onCoverError(e: Event, originalUrl: string | null) {
  const img = e.target as HTMLImageElement
  if (!originalUrl) return
  const currentSrc = img.src
  if (!currentSrc.includes('/api/proxy/image')) {
    if (
      originalUrl.includes('xhscdn.com') ||
      originalUrl.includes('xiaohongshu.com') ||
      originalUrl.includes('picasso-static') ||
      originalUrl.includes('douyinvod.com') ||
      originalUrl.includes('bytedanceimg.com') ||
      originalUrl.includes('bilibili.com') ||
      originalUrl.startsWith('http')
    ) {
      img.src = '/api/proxy/image?url=' + encodeURIComponent(originalUrl)
      return
    }
  }
  img.style.display = 'none'
}

onMounted(() => { loadWorks() })
</script>

<style scoped>
.da-shell { grid-template-columns: auto auto 1fr !important; }
.da-shell.mint-collapsed { grid-template-columns: 56px 1fr !important; }
.da-sidebar-resizer { position: relative; width: 0; cursor: col-resize; flex-shrink: 0; align-self: stretch; z-index: 5; overflow: visible; }
.da-sidebar-resizer::before { content: ''; position: absolute; top: 0; bottom: 0; left: -4px; right: -4px; z-index: 1; }
.da-sidebar-resizer-line { display: none !important; }
.da-sidebar-resizer:hover { background: rgba(0, 0, 0, 0.04); }

.mw-page { flex: 1; min-width: 0; height: 100%; display: flex; flex-direction: column; overflow: hidden; padding: 56px 20px 16px; }
.da-content-card-wrapper { display: flex; flex-direction: column; flex: 1; min-height: 0; min-width: 0; overflow: hidden; }
.da-content-card { flex: 1; min-height: 0; min-width: 0; background: transparent; border-radius: 0; border: none; box-shadow: none; display: flex; flex-direction: column; overflow: hidden; }
.mw-container { flex: 1; overflow-y: auto; padding: 24px; }

/* ====== Header: Tabs + Search ====== */
.mw-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 24px; gap: 20px; flex-wrap: wrap; }
.mw-tabs { display: flex; gap: 8px; align-items: center; }
.mw-tab { padding: 6px 18px; border-radius: 8px; font-size: 14px; cursor: pointer; background: #fff; border: 1px solid #E5E7EB; color: #374151; transition: all 0.15s; white-space: nowrap; display: inline-flex; align-items: center; gap: 6px; }
.mw-tab:hover { background: #F9FAFB; border-color: #D1D5DB; }
.mw-tab-active { background: #333; color: #fff; border-color: #333; font-weight: 600; }
.mw-tab-count { font-size: 12px; color: #9CA3AF; }
.mw-tab-active .mw-tab-count { color: rgba(255,255,255,0.7); }

.mw-search { display: flex; align-items: center; gap: 8px; padding: 8px 14px; background: #fff; border: 1px solid #E5E7EB; border-radius: 10px; min-width: 240px; transition: all 0.15s; }
.mw-search:focus-within { border-color: #999; box-shadow: 0 0 0 3px rgba(0,0,0,0.04); }
.mw-search svg { color: #9CA3AF; flex-shrink: 0; }
.mw-search input { border: none; outline: none; background: transparent; font-size: 13px; color: #1a1a1a; width: 100%; }
.mw-search input::placeholder { color: #C4C9D4; }

/* ====== Card Grid ====== */
.mw-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 16px; }
@media (max-width: 900px) { .mw-grid { grid-template-columns: 1fr; } }

.mw-card { display: flex; gap: 16px; padding: 16px; background: #fff; border-radius: 12px; cursor: pointer; transition: all 0.15s; border: 1px solid #F0F0F0; position: relative; }
.mw-card:hover { box-shadow: 0 4px 12px rgba(0,0,0,0.06); border-color: #E5E7EB; transform: translateY(-1px); }

.mw-cover { width: 120px; height: 90px; border-radius: 8px; overflow: hidden; flex-shrink: 0; background: #F5F5F5; display: flex; align-items: center; justify-content: center; }
.mw-cover img { width: 100%; height: 100%; object-fit: cover; }
.mw-cover video { width: 100%; height: 100%; object-fit: cover; }
.mw-cover-placeholder { color: #D1D5DB; }

.mw-body { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 6px; }

.mw-title-row { display: flex; align-items: flex-start; justify-content: space-between; gap: 8px; }
.mw-title { font-size: 15px; font-weight: 500; color: #1a1a1a; line-height: 1.4; overflow: hidden; text-overflow: ellipsis; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; flex: 1; }

.mw-actions { display: flex; gap: 4px; opacity: 0; transition: opacity 0.15s; flex-shrink: 0; }
.mw-card:hover .mw-actions { opacity: 1; }
.mw-action-btn { width: 28px; height: 28px; border-radius: 6px; border: none; background: transparent; color: #9CA3AF; display: flex; align-items: center; justify-content: center; cursor: pointer; transition: all 0.12s; }
.mw-action-btn:hover { background: #F3F4F6; color: #374151; }
.mw-action-delete:hover { background: #FEF2F2; color: #EF4444; }

.mw-date { font-size: 12px; color: #9CA3AF; }

.mw-stats { display: flex; gap: 16px; margin-top: 2px; }
.mw-stat { display: inline-flex; align-items: center; gap: 4px; font-size: 13px; color: #6B7280; }

/* ====== Empty / Loading ====== */
.mw-loading { display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 80px 0; gap: 12px; }
.mw-spinner { width: 36px; height: 36px; border: 3px solid #E5E7EB; border-top-color: #FF2442; border-radius: 50%; animation: mw-spin 0.6s linear infinite; }
@keyframes mw-spin { to { transform: rotate(360deg); } }
.mw-loading p { font-size: 14px; color: #9CA3AF; }

.mw-empty { display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 80px 0; gap: 12px; }
.mw-empty-icon { color: #D1D5DB; }
.mw-empty-text { font-size: 15px; color: #9CA3AF; margin: 0; }
.mw-btn-primary { display: inline-flex; align-items: center; gap: 6px; padding: 8px 20px; border-radius: 8px; cursor: pointer; font-size: 14px; border: none; background: #FF2442; color: #fff; transition: all 0.15s; }
.mw-btn-primary:hover { background: #E0203C; }

/* ====== Pagination ====== */
.mw-pagination { display: flex; align-items: center; justify-content: center; gap: 16px; padding: 24px 0 8px; }
.mw-pg-btn { padding: 6px 14px; border-radius: 6px; font-size: 13px; cursor: pointer; border: 1px solid #E5E7EB; background: #fff; color: #374151; transition: all 0.15s; }
.mw-pg-btn:hover:not(:disabled) { background: #F9FAFB; border-color: #D1D5DB; }
.mw-pg-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.mw-pg-info { font-size: 13px; color: #6B7280; }
</style>