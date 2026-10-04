<template>
<div class="min-h-screen" style="position: relative;">
  <div class="mint-shell da-shell" :class="{ 'mint-collapsed': isSidebarCollapsed, 'settings-blur': showSettings }" :style="{ '--left-sidebar-width': leftSidebarWidth + 'px' }">

    <SidebarNav
      :current-page="'home'"
      :is-collapsed="isSidebarCollapsed"
      @nav-click="handleNavClick"
      @toggle-sidebar="toggleSidebar"
      @go-eco="goToEco"
      @open-settings="openSettings"
      @new-workflow="goToWorkbench"
      @new-chat="goToChat"
    />

    <div v-if="!isSidebarCollapsed" class="da-sidebar-resizer" @mousedown="startLeftResize"><div class="da-sidebar-resizer-line"></div></div>

    <main class="da-page">
      <div class="da-content-card-wrapper">
      <div class="da-content-card">
        <div class="da-container">

        <!-- ====== Section 1: Profile Header ====== -->
        <section class="xhs-profile">
          <div class="xhs-profile-left">
            <div class="xhs-avatar-wrap">
              <img v-if="authStore.user?.avatar_url" :src="authStore.user.avatar_url" alt="" class="xhs-avatar"/>
              <div v-else class="xhs-avatar xhs-avatar-placeholder"><User :size="24"/></div>
            </div>
            <div class="xhs-profile-info">
              <div class="xhs-name-row">
                <span class="xhs-nickname">{{ authStore.user?.nickname || '创作者' }}</span>
                <span class="xhs-status-badge">账号状态正常</span>
              </div>
              <div class="xhs-stats-row">
                <span class="xhs-stat-item"><strong>{{ summary.total_count }}</strong> 内容数</span>
                <span class="xhs-stat-item"><strong>{{ formatNum(followerTotalFans) }}</strong> 粉丝数</span>
                <span class="xhs-stat-item"><strong>{{ formatNum(summary.total_interactions) }}</strong> 获赞与收藏</span>
              </div>
              <p class="xhs-bio">用 AI 创作优质内容，让每篇作品都有价值</p>
            </div>
          </div>
          <div class="xhs-profile-right">
            <div class="xhs-growth-tip">
              <span class="xhs-tip-text">持续创作优质内容，粉丝会越来越多哦</span>
            </div>
            <div class="xhs-fans-progress">
              <div class="xhs-fp-label">
                <span><Crown :size="12"/> 粉丝</span>
                <span>{{ followerTotalFans }}<span v-if="followerTarget > 0"> / {{ followerTarget }}</span></span>
              </div>
              <div class="xhs-fp-bar">
                <div class="xhs-fp-fill" :style="{ width: fansProgressPercent + '%' }"></div>
              </div>
            </div>
          </div>
        </section>

        <!-- ====== Section 2: New Creation ====== -->
        <section class="xhs-section">
          <div class="xhs-section-header">
            <h2 class="xhs-section-title">新的创作</h2>
            <div class="xhs-section-links">
              <a href="#" @click.prevent="goToMyWorks" class="xhs-link">草稿箱中有未发布的作品</a>
              <a href="#" @click.prevent="goToMyWorks" class="xhs-link xhs-link-arrow">编辑最新笔记 ›</a>
            </div>
          </div>
          <div class="xhs-create-cards">
            <div class="xhs-create-card xhs-cc-image" @click="goToWorkbench">
              <div class="xhs-cc-icon"><ImageIcon :size="28"/></div>
              <div class="xhs-cc-body">
                <span class="xhs-cc-title">发布图文笔记</span>
                <span class="xhs-cc-desc">支持图片格式 png、jpg、jpeg</span>
              </div>
            </div>
            <div class="xhs-create-card xhs-cc-video" @click="goToWorkbench">
              <div class="xhs-cc-icon"><Video :size="28"/></div>
              <div class="xhs-cc-body">
                <span class="xhs-cc-title">发布视频笔记</span>
                <span class="xhs-cc-desc">支持视频格式 mp4、mov</span>
              </div>
            </div>
            <div class="xhs-create-card xhs-cc-live" @click="goToWorkbench">
              <div class="xhs-cc-icon"><Radio :size="28"/></div>
              <div class="xhs-cc-body">
                <span class="xhs-cc-title">去开播</span>
                <span class="xhs-cc-desc">使用直播助手开播</span>
              </div>
            </div>
          </div>
        </section>

        <!-- ====== Section 3: Data Overview ====== -->
        <section class="xhs-section">
          <div class="xhs-section-header">
            <div class="xhs-tabs-row">
              <button class="xhs-tab" :class="{ 'xhs-tab-active': dataTab === 'note' }" @click="dataTab = 'note'">笔记数据总览 ⓘ</button>
              <button class="xhs-tab" :class="{ 'xhs-tab-active': dataTab === 'live' }" @click="dataTab = 'live'">直播数据总览 ⓘ</button>
            </div>
            <div class="xhs-section-right">
              <a href="#" @click.prevent="goToMyWorks" class="xhs-link xhs-link-arrow">查看详情 ›</a>
            </div>
          </div>
          <div class="xhs-period-bar">
            <span class="xhs-period-label">统计周期 {{ periodStart }} 至 {{ periodEnd }}</span>
            <div class="xhs-period-toggle">
              <button v-for="p in periodOptions" :key="p.value" class="xhs-pbtn" :class="{ 'xhs-pbtn-active': selectedPeriod === p.value }" @click="switchPeriod(p.value)">{{ p.label }}</button>
            </div>
          </div>
          <div class="xhs-metrics-grid">
            <div class="xhs-metric">
              <span class="xhs-metric-label">曝光数</span>
              <span class="xhs-metric-value">{{ formatNum(summary.total_reads) }}</span>
              <span class="xhs-metric-change" :class="changeClass(0)">环比 —</span>
            </div>
            <div class="xhs-metric">
              <span class="xhs-metric-label">观看数</span>
              <span class="xhs-metric-value">{{ formatNum(summary.total_reads) }}</span>
              <span class="xhs-metric-change" :class="changeClass(0)">环比 —</span>
            </div>
            <div class="xhs-metric">
              <span class="xhs-metric-label">点赞数</span>
              <span class="xhs-metric-value">{{ summary.totalLikes }}</span>
              <span class="xhs-metric-change" :class="changeClass(0)">环比 —</span>
            </div>
            <div class="xhs-metric">
              <span class="xhs-metric-label">评论数</span>
              <span class="xhs-metric-value">{{ summary.totalComments }}</span>
              <span class="xhs-metric-change" :class="changeClass(0)">环比 —</span>
            </div>
            <div class="xhs-metric">
              <span class="xhs-metric-label">净涨粉</span>
              <span class="xhs-metric-value">{{ followerTotalFans }}</span>
              <span class="xhs-metric-change" :class="changeClass(0)">环比 —</span>
            </div>
            <div class="xhs-metric">
              <span class="xhs-metric-label">新增关注</span>
              <span class="xhs-metric-value">{{ followerTotalFans }}</span>
              <span class="xhs-metric-change" :class="changeClass(0)">环比 —</span>
            </div>
            <div class="xhs-metric">
              <span class="xhs-metric-label">封面点击率</span>
              <span class="xhs-metric-value">{{ summary.avgEngagementRate }}%</span>
              <span class="xhs-metric-change" :class="changeClass(0)">环比 —</span>
            </div>
            <div class="xhs-metric">
              <span class="xhs-metric-label">收藏数</span>
              <span class="xhs-metric-value">{{ summary.totalCollects }}</span>
              <span class="xhs-metric-change" :class="changeClass(0)">环比 —</span>
            </div>
            <div class="xhs-metric">
              <span class="xhs-metric-label">分享数</span>
              <span class="xhs-metric-value">{{ summary.totalShares }}</span>
              <span class="xhs-metric-change" :class="changeClass(0)">环比 —</span>
            </div>
            <div class="xhs-metric">
              <span class="xhs-metric-label">主页访客</span>
              <span class="xhs-metric-value">{{ summary.totalCount }}</span>
              <span class="xhs-metric-change" :class="changeClass(0)">环比 —</span>
            </div>
          </div>
        </section>

        <!-- ====== Section 4: Latest Notes ====== -->
        <section class="xhs-section">
          <div class="xhs-section-header">
            <h2 class="xhs-section-title">最新笔记</h2>
            <a href="#" @click.prevent="goToMyWorks" class="xhs-link xhs-link-arrow">查看详情 ›</a>
          </div>
          <div class="xhs-note-update-time">数据最后更新时间 {{ lastUpdateTime }}</div>

          <div v-if="contentTopItems.length > 0" class="xhs-note-list">
            <div v-for="(item, idx) in contentTopItems.slice(0, 5)" :key="item.id" class="xhs-note-card">
              <div class="xhs-note-top">
                <div class="xhs-note-tags">
                  <span v-for="(tag, ti) in parseTags(item.tags)" :key="ti" class="xhs-tag">{{ tag }}</span>
                </div>
                <div class="xhs-note-tabs">
                  <button class="xhs-ntab" :class="{ 'xhs-ntab-active': noteDetailTab[Number(idx)] === 'view' }" @click="setNoteTab(Number(idx), 'view')">观看{{ item.reads }}</button>
                  <button class="xhs-ntab" :class="{ 'xhs-ntab-active': noteDetailTab[Number(idx)] === 'like' }" @click="setNoteTab(Number(idx), 'like')">点赞{{ item.likes }}</button>
                  <button class="xhs-ntab" :class="{ 'xhs-ntab-active': noteDetailTab[Number(idx)] === 'collect' }" @click="setNoteTab(Number(idx), 'collect')">收藏{{ item.collects }}</button>
                  <button class="xhs-ntab" :class="{ 'xhs-ntab-active': noteDetailTab[Number(idx)] === 'comment' }" @click="setNoteTab(Number(idx), 'comment')">评论{{ item.comments }}</button>
                </div>
              </div>
              <div class="xhs-note-body" @click="goToMyWorks">
                <div class="xhs-note-cover" v-if="item.cover_img_url">
                  <img :src="item.cover_img_url" alt="" @error="onImgError"/>
                </div>
                <div class="xhs-note-cover xhs-note-cover-empty" v-else>
                  <ImageIcon :size="24"/>
                </div>
                <div class="xhs-note-info">
                  <h3 class="xhs-note-title">{{ item.title }}</h3>
                  <p class="xhs-note-desc">{{ item.content_text ? truncateText(item.content_text, 60) : '暂无描述' }}</p>
                </div>
              </div>
              <div class="xhs-note-chart" v-if="dailyTrend.length > 1">
                <svg :viewBox="`0 0 ${chartW} ${chartH}`" preserveAspectRatio="none" class="xhs-chart-svg">
                  <defs>
                    <linearGradient :id="'grad' + Number(idx)" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stop-color="#3B82F6" stop-opacity="0.25"/>
                      <stop offset="100%" stop-color="#3B82F6" stop-opacity="0.02"/>
                    </linearGradient>
                  </defs>
                  <path :d="chartArea(Number(idx))" :fill="'url(#grad' + Number(idx) + ')'"/>
                  <polyline :points="chartLine(Number(idx))" fill="none" stroke="#3B82F6" stroke-width="1.8" stroke-linejoin="round"/>
                </svg>
              </div>
            </div>
          </div>
          <div v-else class="xhs-notes-empty">
            <FileText :size="40" class="xhs-empty-icon"/>
            <p>还没有笔记数据，点击上方「发布图文笔记」开始创作吧</p>
            <button class="da-btn da-btn-primary" @click="goToWorkbench"><Plus :size="14" /> 开始创作</button>
          </div>
        </section>

        <!-- bottom spacer -->
        <div style="height:40px;"></div>

        </div>
      </div>
      </div>
    </main>
  </div>

  <SettingsView v-if="showSettings" @close="showSettings = false" />
</div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, defineAsyncComponent } from 'vue'
import { useRouter } from 'vue-router'
import {
  Plus, BarChart3, Eye, MessageCircle, TrendingUp, Flame,
  Image as ImageIcon, Video, User, Crown, Radio, FileText,
} from 'lucide-vue-next'
import SidebarNav from '@/components/workbench/SidebarNav.vue'
const SettingsView = defineAsyncComponent(() => import('@/views/SettingsView.vue'))
import { useAuthStore } from '@/stores/auth'
import { useUIState } from '@/composables/useUIState'
import { useResizeHandle } from '@/composables/useResizeHandle'
import {
  getDashboardOverview, getContentAnalysis, getFollowerAnalysis,
} from '@/api/dashboard'

const router = useRouter()
const authStore = useAuthStore()
const { isSidebarCollapsed, toggleSidebar: toggleSidebarBase } = useUIState()

function toggleSidebar() { toggleSidebarBase() }
function handleNavClick(pageName: string) {
  if (pageName === 'home') return
  if (pageName === 'my-works') { router.push('/my-works').catch(() => {}); return }
  if (pageName === 'portfolio') { router.push('/portfolio').catch(() => {}); return }
  if (pageName === 'topic-pool') { router.push('/topic-pool').catch(() => {}); return }
  if (pageName === 'task-plans') { router.push('/task-plans').catch(() => {}); return }
  router.push({ path: '/workbench', query: { page: pageName } })
}
function openSettings() {
  showSettings.value = true
}
function goToEco() { router.push('/eco') }
function goToWorkbench() { router.push({ path: '/workbench', query: { page: 'workflow' } }) }
function goToChat() { router.push('/workbench') }
function goToMyWorks() { router.push('/my-works') }

const {
  width: leftSidebarWidth,
  startResize: startLeftResize,
} = useResizeHandle({
  direction: 'left',
  minWidth: 170,
  maxWidth: 520,
  storageKey: 'mint-left-sidebar-width-v2',
})

const periodOptions = [
  { value: 7, label: '近7日' },
  { value: 30, label: '近30日' },
]
const selectedPeriod = ref(7)
const dataTab = ref('note')
const noteDetailTab = ref<Record<number, string>>({})
const showSettings = ref(false)

const overview = ref<any>(null)
const contentAnalysis = ref<any>(null)
const followerData = ref<any>(null)
const followerTarget = 500

const summary = computed(() => overview.value?.summary ?? {
  total_reads: 0, total_interactions: 0, total_count: 0,
  collected_count: 0, hot_count: 0, avg_engagement_rate: 0,
})
const dailyTrend = computed(() => overview.value?.daily_trend ?? [])
const contentTopItems = computed(() => contentAnalysis.value?.top_items ?? [])
const followerTotalFans = computed(() => followerData.value?.total_fans ?? 0)

const fansProgressPercent = computed(() => {
  if (followerTarget <= 0) return 100
  return Math.min(Math.round(followerTotalFans.value / followerTarget * 100), 100)
})

const periodStart = computed(() => {
  const d = new Date()
  d.setDate(d.getDate() - selectedPeriod.value)
  return formatDate(d)
})
const periodEnd = computed(() => formatDate(new Date()))
const lastUpdateTime = computed(() => {
  if (!contentTopItems.value.length) return '—'
  const t = contentTopItems.value[0]?.collected_at || contentTopItems.value[0]?.published_at
  if (!t) return '—'
  try { return new Date(t).toLocaleString('zh-CN') } catch { return t }
})

const chartW = 800
const chartH = 120

function setNoteTab(idx: number, tab: string) {
  noteDetailTab.value = { ...noteDetailTab.value, [idx]: tab }
}

function chartLine(noteIdx: number): string {
  const data = dailyTrend.value
  if (data.length < 2) return ''
  const maxV = Math.max(...data.map((d: any) => d.interactions), 1)
  const w = chartW
  const h = chartH
  const padL = 0
  const padR = 0
  const padT = 4
  const padB = 4
  return data.map((d: any, i: number) => {
    const x = padL + (i / Math.max(data.length - 1, 1)) * (w - padL - padR)
    const y = padT + (h - padT - padB) - (d.interactions / maxV) * (h - padT - padB)
    return `${x},${y}`
  }).join(' ')
}

function chartArea(noteIdx: number): string {
  const data = dailyTrend.value
  if (data.length < 2) return ''
  const maxV = Math.max(...data.map((d: any) => d.interactions), 1)
  const w = chartW
  const h = chartH
  const padL = 0
  const padR = 0
  const padT = 4
  const padB = 4
  const bottomY = h - padB
  const pts = data.map((d: any, i: number) => {
    const x = padL + (i / Math.max(data.length - 1, 1)) * (w - padL - padR)
    const y = padT + (h - padT - padB) - (d.interactions / maxV) * (h - padT - padB)
    return `${x},${y}`
  })
  return `M ${padL},${bottomY} L ${pts.join(' L ')} L ${w - padR},${bottomY} Z`
}

function formatNum(n: number): string {
  if (n >= 10000) return (n / 10000).toFixed(1) + 'w'
  if (n >= 1000) return (n / 1000).toFixed(1) + 'k'
  return String(n)
}

function formatDate(d: Date): string {
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${m}-${day}`
}

function changeClass(val: number): string {
  if (val > 0) return 'xhs-up'
  if (val < 0) return 'xhs-down'
  return 'xhs-flat'
}

function parseTags(tags: any): string[] {
  if (!tags) return []
  if (Array.isArray(tags)) return tags.map(String).filter(Boolean)
  if (typeof tags === 'object') {
    const arr: string[] = []
    for (const k in tags) { arr.push(tags[k]) }
    return arr.filter(Boolean)
  }
  return [String(tags)].filter(Boolean)
}

function truncateText(text: string, len: number): string {
  if (!text) return ''
  return text.length > len ? text.slice(0, len) + '...' : text
}

function onImgError(e: Event) {
  const img = e.target as HTMLImageElement
  img.style.display = 'none'
}

function switchPeriod(days: number) {
  selectedPeriod.value = days
  loadAll()
}

async function loadAll() {
  try {
    const [ov, ca, fa] = await Promise.all([
      getDashboardOverview(selectedPeriod.value),
      getContentAnalysis({ sort_by: 'latest', limit: 20 }),
      getFollowerAnalysis(),
    ])
    overview.value = ov
    contentAnalysis.value = ca
    followerData.value = fa
  } catch (e: any) {
    console.error('Dashboard load failed:', e)
  }
}

onMounted(() => { loadAll() })
</script>

<style scoped>
.da-page { flex: 1; min-width: 0; height: 100%; display: flex; flex-direction: column; overflow: hidden; padding: 56px 20px 16px;
  background: transparent;
}
.da-content-card-wrapper { display: flex; flex-direction: column; flex: 1; min-height: 0; min-width: 0; overflow: hidden; }
.da-content-card { flex: 1; min-height: 0; min-width: 0; background: transparent; border-radius: 0; border: none; box-shadow: none; display: flex; flex-direction: column; overflow: hidden; }
.da-container { flex: 1; overflow-y: auto; padding: 0; }

.da-shell { grid-template-columns: auto auto 1fr !important; }
.da-shell.mint-collapsed { grid-template-columns: 56px 1fr !important; }
.mint-shell.settings-blur { filter: blur(3px); transition: filter 0.25s ease; }
.da-sidebar-resizer { position: relative; width: 0; cursor: col-resize; flex-shrink: 0; align-self: stretch; z-index: 5; overflow: visible; }
.da-sidebar-resizer::before { content: ''; position: absolute; top: 0; bottom: 0; left: -4px; right: -4px; z-index: 1; }
.da-sidebar-resizer-line { display: none !important; }
.da-sidebar-resizer:hover { background: rgba(0, 0, 0, 0.04); }

/* ===== Profile Header ===== */
.xhs-profile {
  display: flex; align-items: flex-start; justify-content: space-between; gap: 24px;
  background: linear-gradient(135deg, #FFFFFF 0%, #FFFCFA 100%);
  border-radius: 16px; padding: 24px 28px; margin-bottom: 18px;
  box-shadow:
    0 1px 2px rgba(0,0,0,0.03),
    0 4px 12px rgba(0,0,0,0.02),
    inset 0 1px 0 rgba(255,255,255,0.8);
  border: 1px solid rgba(255,255,255,0.6);
  position: relative; overflow: hidden;
}
.xhs-profile::before {
  content: '';
  position: absolute; top: -60px; right: -40px; width: 200px; height: 200px;
  background: radial-gradient(circle, rgba(255, 107, 107, 0.08) 0%, transparent 70%);
  pointer-events: none;
}
.xhs-profile-left { display: flex; gap: 16px; flex: 1; min-width: 0; }
.xhs-avatar-wrap { flex-shrink: 0; }
.xhs-avatar { width: 64px; height: 64px; border-radius: 50%; object-fit: cover; background: #F0F0F0; display: flex; align-items: center; justify-content: center; color: #9CA3AF; }
.xhs-profile-info { min-width: 0; }
.xhs-name-row { display: flex; align-items: center; gap: 10px; margin-bottom: 6px; }
.xhs-nickname { font-size: 18px; font-weight: 700; color: #1a1a1a; }
.xhs-status-badge { display: inline-flex; align-items: center; gap: 4px; font-size: 11px; color: #059669; background: #ECFDF5; padding: 2px 8px; border-radius: 10px; font-weight: 500; }
.xhs-stats-row { display: flex; gap: 18px; margin-bottom: 6px; font-size: 13px; color: #374151; }
.xhs-stat-item strong { font-weight: 600; color: #1a1a1a; margin-right: 2px; }
.xhs-bio { font-size: 12px; color: #9CA3AF; margin: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 480px; }
.xhs-profile-right { width: 240px; flex-shrink: 0; }
.xhs-growth-tip { font-size: 12px; color: #6B7280; margin-bottom: 10px; }
.xhs-tip-text { background: linear-gradient(90deg, #FEF3C7, #FDE68A); padding: 6px 12px; border-radius: 8px; display: block; font-size: 11.5px; color: #92400E; }
.xhs-fans-progress { }
.xhs-fp-label { display: flex; justify-content: space-between; font-size: 11px; color: #6B7280; margin-bottom: 4px; }
.xhs-fp-label span:first-child { display: flex; align-items: center; gap: 3px; color: #F59E0B; font-weight: 600; }
.xhs-fp-bar { height: 6px; background: #E5E7EB; border-radius: 3px; overflow: hidden; }
.xhs-fp-fill { height: 100%; background: linear-gradient(90deg, #F59E0B, #FBBF24); border-radius: 3px; transition: width 0.5s ease; }

/* ===== Sections ===== */
.xhs-section {
  background:
    linear-gradient(135deg, rgba(255,255,255,0.95) 0%, rgba(252,250,248,0.9) 100%);
  backdrop-filter: blur(10px);
  border-radius: 16px; padding: 22px 26px; margin-bottom: 18px;
  box-shadow:
    0 1px 3px rgba(0,0,0,0.02),
    0 6px 20px rgba(0,0,0,0.03),
    inset 0 1px 0 rgba(255,255,255,0.7);
  border: 1px solid rgba(255,255,255,0.5);
  transition: box-shadow 0.3s ease;
}
.xhs-section:hover {
  box-shadow:
    0 2px 4px rgba(0,0,0,0.03),
    0 8px 28px rgba(0,0,0,0.04),
    inset 0 1px 0 rgba(255,255,255,0.8);
}
.xhs-section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }
.xhs-section-title { font-size: 16px; font-weight: 700; color: #1a1a1a; margin: 0; }
.xhs-section-links { display: flex; gap: 16px; font-size: 12px; }
.xhs-link { color: #6B7280; text-decoration: none; transition: color 0.15s; }
.xhs-link:hover { color: #FF2442; }
.xhs-link-arrow::after { content: '›'; margin-left: 2px; }
.xhs-section-right { font-size: 12px; }

/* ===== New Creation Cards ===== */
.xhs-create-cards { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }
@media (max-width: 900px) { .xhs-create-cards { grid-template-columns: 1fr; } }
.xhs-create-card {
  display: flex; align-items: center; gap: 14px;
  padding: 18px 20px; border-radius: 14px; cursor: pointer;
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
  border: 1px solid rgba(255,255,255,0.6);
  position: relative; overflow: hidden;
}
.xhs-create-card::before {
  content: '';
  position: absolute; top: 0; left: 0; right: 0; bottom: 0;
  background: linear-gradient(135deg, rgba(255,255,255,0.3) 0%, transparent 60%);
  pointer-events: none;
}
.xhs-create-card:hover {
  transform: translateY(-2px);
  box-shadow:
    0 8px 24px rgba(0,0,0,0.08),
    0 2px 8px rgba(0,0,0,0.04);
}
.xhs-cc-image { background: linear-gradient(135deg, #FFF7ED, #FFEDD5); }
.xhs-cc-video { background: linear-gradient(135deg, #EFF6FF, #DBEAFE); }
.xhs-cc-live { background: linear-gradient(135deg, #FDF2F8, #FCE7F3); }
.xhs-cc-icon { width: 48px; height: 48px; border-radius: 12px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.xhs-cc-image .xhs-cc-icon { background: #FFF7ED; color: #F97316; }
.xhs-cc-video .xhs-cc-icon { background: #EFF6FF; color: #3B82F6; }
.xhs-cc-live .xhs-cc-icon { background: #FDF2F8; color: #EC4899; }
.xhs-cc-body { display: flex; flex-direction: column; gap: 2px; }
.xhs-cc-title { font-size: 14px; font-weight: 600; color: #1a1a1a; }
.xhs-cc-desc { font-size: 11.5px; color: #9CA3AF; }

/* ===== Data Tabs ===== */
.xhs-tabs-row { display: flex; gap: 4px; }
.xhs-tab { padding: 6px 14px; border-radius: 8px; font-size: 13px; font-weight: 500; border: none; background: transparent; color: #6B7280; cursor: pointer; transition: all 0.15s; }
.xhs-tab:hover { color: #374151; }
.xhs-tab-active { color: #1a1a1a; font-weight: 600; }

/* ===== Period Bar ===== */
.xhs-period-bar { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; font-size: 12px; color: #9CA3AF; }
.xhs-period-toggle { display: flex; gap: 2px; background: #F3F4F6; border-radius: 6px; padding: 2px; }
.xhs-pbtn { padding: 4px 12px; border-radius: 4px; font-size: 11px; font-weight: 500; border: none; background: transparent; color: #6B7280; cursor: pointer; transition: all 0.15s; }
.xhs-pbtn:hover { color: #374151; }
.xhs-pbtn-active { background: #fff; color: #FF2442; box-shadow: 0 1px 2px rgba(0,0,0,0.06); }

/* ===== Metrics Grid (10 columns like XHS) ===== */
.xhs-metrics-grid { display: grid; grid-template-columns: repeat(5, 1fr); gap: 0; }
@media (max-width: 1100px) { .xhs-metrics-grid { grid-template-columns: repeat(3, 1fr); } }
@media (max-width: 700px) { .xhs-metrics-grid { grid-template-columns: repeat(2, 1fr); } }
.xhs-metric { padding: 14px 12px; border-right: 1px solid #F3F4F6; border-bottom: 1px solid #F3F4F6; }
.xhs-metric:nth-child(5n) { border-right: none; }
.xhs-metric:nth-last-child(-n+5) { border-bottom: none; }
.xhs-metric-label { font-size: 12px; color: #9CA3AF; display: block; margin-bottom: 4px; }
.xhs-metric-value { font-size: 22px; font-weight: 700; color: #1a1a1a; line-height: 1.2; display: block; }
.xhs-metric-change { font-size: 11px; display: block; margin-top: 2px; }
.xhs-up { color: #EF4444; }
.xhs-down { color: #10B981; }
.xhs-flat { color: #D1D5DB; }

/* ===== Latest Notes ===== */
.xhs-note-update-time { font-size: 11.5px; color: #9CA3AF; margin-bottom: 14px; letter-spacing: 0.3px; }
.xhs-note-list { display: flex; flex-direction: column; gap: 18px; }
.xhs-note-card {
  border: 1px solid rgba(240,240,240,0.8);
  border-radius: 14px; overflow: hidden;
  background:
    linear-gradient(135deg, rgba(255,255,255,0.98) 0%, rgba(253,251,249,0.95) 100%);
  box-shadow:
    0 1px 2px rgba(0,0,0,0.02),
    0 4px 16px rgba(0,0,0,0.03);
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
}
.xhs-note-card:hover {
  box-shadow:
    0 4px 8px rgba(0,0,0,0.04),
    0 10px 30px rgba(0,0,0,0.06);
  transform: translateY(-1px);
}
.xhs-note-top { display: flex; align-items: center; justify-content: space-between; padding: 10px 16px; background: #FAFAFA; border-bottom: 1px solid #F0F0F0; }
.xhs-note-tags { display: flex; gap: 6px; }
.xhs-tag { font-size: 11px; color: #6B7280; background: #fff; padding: 2px 8px; border-radius: 4px; border: 1px solid #E5E7EB; }
.xhs-note-tabs { display: flex; gap: 2px; }
.xhs-ntab { padding: 3px 10px; border-radius: 4px; font-size: 11px; font-weight: 500; border: none; background: transparent; color: #9CA3AF; cursor: pointer; transition: all 0.15s; }
.xhs-ntab:hover { color: #6B7280; }
.xhs-ntab-active { background: #EFF6FF; color: #3B82F6; }
.xhs-note-body { display: flex; gap: 14px; padding: 14px 16px; cursor: pointer; transition: background 0.15s; }
.xhs-note-body:hover { background: #FAFAFA; }
.xhs-note-cover { width: 88px; height: 88px; border-radius: 8px; overflow: hidden; flex-shrink: 0; background: #F3F4F6; }
.xhs-note-cover img { width: 100%; height: 100%; object-fit: cover; }
.xhs-note-cover-empty { display: flex; align-items: center; justify-content: center; color: #D1D5DB; }
.xhs-note-info { flex: 1; min-width: 0; display: flex; flex-direction: column; justify-content: center; gap: 4px; }
.xhs-note-title { font-size: 15px; font-weight: 600; color: #1a1a1a; margin: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.xhs-note-desc { font-size: 12.5px; color: #6B7280; margin: 0; line-height: 1.5; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.xhs-note-chart { height: 100px; padding: 0 8px 8px; }
.xhs-chart-svg { width: 100%; height: 100%; }

/* Empty state */
.xhs-notes-empty { text-align: center; padding: 50px 0; color: #9CA3AF; }
.xhs-empty-icon { color: #D1D5DB; margin-bottom: 12px; }
.xhs-notes-empty p { font-size: 13px; margin: 0 0 16px; }
</style>