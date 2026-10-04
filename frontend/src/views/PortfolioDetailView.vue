<template>
<div class="min-h-screen" style="position: relative;">

  <div class="mint-shell mint-right-collapsed" :class="{ 'mint-collapsed': isSidebarCollapsed, 'is-left-resizing': isLeftResizing }" :style="{ '--left-sidebar-width': leftSidebarWidth + 'px' }">

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

    <div
      v-if="!isSidebarCollapsed"
      class="mint-left-resize-handle"
      :class="{ 'is-left-resizing': isLeftResizing }"
      @mousedown="startLeftResize"
      @dblclick.prevent="resetLeftSidebarWidth"
    >
      <div class="mint-resize-line"></div>
    </div>

    <main class="da-page">
      <div class="da-content-card-wrapper">
      <div class="da-content-card">

        <div class="da-topbar">
          <button class="da-btn da-btn-ghost" @click="goBack">
            <Icon icon="ph:caret-left" width="14" />
            返回作品集
          </button>
          <div class="da-topbar-right">
            <span class="da-work-badge" :class="sourceBadgeClass">{{ sourceLabel }}</span>
            <span class="da-topbar-time">{{ formatFullDate(artifact?.updated_at || 0) }}</span>
          </div>
        </div>

        <div class="da-container">
          <div v-if="pageLoading" class="da-loading">
            <Icon icon="ph:spinner-gap" width="20" class="pf-spin" />
            <span>加载中...</span>
          </div>

          <div v-else-if="!artifact" class="da-empty-state">
            <Icon icon="ph:warning-circle-duotone" width="40" style="color: #D1D5DB" />
            <p class="da-empty-title">作品不存在</p>
            <button class="da-btn" @click="goBack" style="margin-top: 12px;">返回作品集</button>
          </div>

          <template v-else>

            <div class="dt-header">
              <h1 class="dt-title">{{ artifact.brief?.title || '未命名作品' }}</h1>
              <p class="dt-topic" v-if="artifact.brief?.topic">{{ artifact.brief.topic }}</p>
            </div>

            <div class="dt-pages" v-if="artifact.storyboard?.length">
              <div class="dt-pages-label">共 {{ artifact.storyboard.length }} 页</div>
              <div class="dt-pages-grid">
                <div v-for="(page, idx) in artifact.storyboard" :key="idx" class="dt-page-wrap">
                  <div class="dt-page" :ref="(el) => setPageRef(el, idx)">
                    <img v-if="page.image_url" :src="page.image_url" :alt="'第' + (idx+1) + '页'" loading="lazy" />
                    <div v-else-if="getPageHtml(page)" class="dt-page-scaler">
                      <iframe
                        :srcdoc="getPageHtml(page)"
                        class="dt-page-iframe"
                        sandbox="allow-same-origin allow-scripts"
                        scrolling="no"
                      />
                    </div>
                    <div v-else class="dt-page-fallback">
                      <span>{{ idx + 1 }}</span>
                    </div>
                  </div>
                  <div class="dt-page-info">
                    <span class="dt-page-role">{{ page.role_label || `第${idx+1}页` }}</span>
                  </div>
                </div>
              </div>
            </div>

            <div class="dt-meta" v-if="artifact.brief">
              <div class="dt-meta-item" v-if="artifact.brief.goal">
                <span class="dt-meta-key">目标</span>
                <span class="dt-meta-val">{{ artifact.brief.goal }}</span>
              </div>
              <div class="dt-meta-item" v-if="artifact.brief.audience">
                <span class="dt-meta-key">受众</span>
                <span class="dt-meta-val">{{ artifact.brief.audience }}</span>
              </div>
              <div class="dt-meta-item" v-if="artifact.brief.tone">
                <span class="dt-meta-key">语气</span>
                <span class="dt-meta-val">{{ artifact.brief.tone }}</span>
              </div>
              <div class="dt-meta-item" v-if="artifact.brief.visual_direction">
                <span class="dt-meta-key">视觉方向</span>
                <span class="dt-meta-val">{{ artifact.brief.visual_direction }}</span>
              </div>
              <div class="dt-meta-item" v-if="artifact.brief.keep_patterns?.length">
                <span class="dt-meta-key">保留模式</span>
                <div class="dt-meta-tags">
                  <span v-for="t in artifact.brief.keep_patterns" :key="t" class="dt-tag dt-tag-keep">{{ t }}</span>
                </div>
              </div>
              <div class="dt-meta-item" v-if="artifact.brief.avoid_patterns?.length">
                <span class="dt-meta-key">避免模式</span>
                <div class="dt-meta-tags">
                  <span v-for="t in artifact.brief.avoid_patterns" :key="t" class="dt-tag dt-tag-avoid">{{ t }}</span>
                </div>
              </div>
            </div>

            <div class="dt-actions">
              <button class="da-btn" @click="onEdit">
                <Icon icon="ph:pencil-simple" width="14" />
                编辑
              </button>
              <button class="da-btn da-btn-primary" @click="onPublish" v-if="source === 'draft' || source === 'artifact'" :disabled="publishing">
                <Icon icon="ph:paper-plane-tilt" width="14" />
                {{ publishing ? '发布中...' : '发布' }}
              </button>
              <button class="da-btn da-btn-danger" @click="onDelete" :disabled="deleting">
                <Icon icon="ph:trash" width="14" />
                {{ deleting ? '删除中...' : '删除' }}
              </button>
            </div>

          </template>

        </div>

      </div>
      </div>
    </main>

  </div>

</div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { Icon } from '@iconify/vue'
import SidebarNav from '@/components/workbench/SidebarNav.vue'
import { useWorkStore } from '@/stores/work'
import { useUIState } from '@/composables/useUIState'
import { getCreativeArtifact, deleteCreativeArtifact } from '@/api/creativeArtifact'
import type { CreativeArtifact } from '@/types/creativeArtifact'

const router = useRouter()
const route = useRoute()
const workStore = useWorkStore()
const { isSidebarCollapsed, toggleSidebar: toggleSidebarBase } = useUIState()

const artifactId = computed(() => route.params.id as string)
const source = computed(() => (route.query.source as string) || 'artifact')

const pageLoading = ref(true)
const artifact = ref<CreativeArtifact | null>(null)
const publishing = ref(false)
const deleting = ref(false)

function toggleSidebar() { toggleSidebarBase() }

function handleNavClick(pageName: string) {
  if (pageName === 'home') { router.push('/').catch(() => {}); return }
  if (pageName === 'portfolio') { router.push('/portfolio').catch(() => {}); return }
  if (pageName === 'topic-pool') { router.push('/topic-pool').catch(() => {}); return }
  if (pageName === 'my-works') { router.push('/my-works').catch(() => {}); return }
  if (pageName === 'task-plans') { router.push('/task-plans').catch(() => {}); return }
  router.push({ path: '/workbench', query: { page: pageName } })
}

function goToEco() { router.push('/eco') }
function openSettings() {
  window.dispatchEvent(new Event('open-settings'))
}
function goToWorkbench() { router.push({ path: '/workbench', query: { page: 'workflow' } }) }
function goToChat() { router.push('/workbench') }
function goBack() { router.push('/portfolio').catch(() => {}) }

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

const sourceLabel = computed(() => {
  if (source.value === 'draft') return '草稿'
  if (source.value === 'artifact') return '创作'
  if (source.value === 'published') return '已发布'
  return '未知'
})

const sourceBadgeClass = computed(() => {
  if (source.value === 'draft') return 'da-badge-draft'
  if (source.value === 'artifact') return 'da-badge-artifact'
  if (source.value === 'published') return 'da-badge-published'
  return ''
})

function getPageHtml(page: any): string {
  if (!page) return ''
  if (page.content?.htmlContent) return page.content.htmlContent
  if (page.htmlContent) return page.htmlContent
  return ''
}

const NATIVE_W = 1080
const NATIVE_H = 1440
const pageRefs = new Map<number, HTMLElement>()
let pageRO: ResizeObserver | null = null

function setPageRef(el: unknown, idx: number) {
  if (!el || !(el instanceof HTMLElement)) return
  pageRefs.set(idx, el)
  if (pageRO) pageRO.observe(el)
}

function applyPageScale(entries: ResizeObserverEntry[]) {
  for (const entry of entries) {
    const scaler = entry.target.querySelector('.dt-page-scaler') as HTMLElement | null
    if (!scaler) continue
    const w = entry.contentBoxSize?.[0]?.inlineSize ?? entry.contentRect.width
    const scale = w / NATIVE_W
    scaler.style.transform = `scale(${scale})`
    scaler.style.transformOrigin = 'top left'
    scaler.style.width = `${NATIVE_W}px`
    scaler.style.height = `${NATIVE_H}px`
  }
}

function formatFullDate(ts: number): string {
  if (!ts) return '-'
  const d = new Date(ts * 1000)
  if (isNaN(d.getTime())) return '-'
  return d.toLocaleString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

function onEdit() {
  if (source.value === 'draft' || source.value === 'published') {
    workStore.setActiveWork(artifactId.value)
    router.push('/workbench').catch(() => {})
  }
}

async function onPublish() {
  publishing.value = true
  try {
    if (source.value === 'draft') {
      const work = workStore.works.find(w => w.id === artifactId.value)
      if (work) {
        workStore.updateDraft(artifactId.value, { contentStatus: 'published' } as any)
      }
    }
    router.push('/portfolio').catch(() => {})
  } finally {
    publishing.value = false
  }
}

async function onDelete() {
  deleting.value = true
  try {
    if (source.value === 'artifact') {
      await deleteCreativeArtifact(artifactId.value)
      await workStore.fetchOutputWorks()
    } else {
      await workStore.deleteWork(artifactId.value)
    }
    router.push('/portfolio').catch(() => {})
  } finally {
    deleting.value = false
  }
}

async function loadArtifact() {
  pageLoading.value = true
  try {
    if (source.value === 'artifact') {
      artifact.value = await getCreativeArtifact(artifactId.value)
    } else {
      const work = workStore.works.find(w => w.id === artifactId.value)
      if (work?.cardDraft?.pages?.length) {
        artifact.value = {
          artifact_id: artifactId.value,
          version: 1,
          created_at: 0,
          updated_at: new Date(work.dataCollectedAt).getTime() / 1000,
          source: {},
          analysis: {},
          brief: { goal: '', audience: '', tone: '', topic: work.description || '', title: work.title || '', visual_direction: '', template_id: '', keep_patterns: [], avoid_patterns: [] },
          storyboard: work.cardDraft.pages.map((p: any, idx: number) => ({
            page_id: p.id || `page-${idx}`,
            index: idx,
            role: p.role || '',
            role_label: p.role_label || `第${idx+1}页`,
            rationale: '',
            source_evidence: '',
            visual_goal: '',
            component: { page_type: p.type || '' },
            image_role: '',
            content: p.content || {},
            image_url: p.imageUrl || '',
            html_url: p.htmlUrl || '',
          })),
          review: { score: 0, issues: [], suggestions: [] },
          history: [],
        } as any
      }
    }
  } catch {
    artifact.value = null
  } finally {
    pageLoading.value = false
  }
}

onMounted(() => {
  pageRO = new ResizeObserver(applyPageScale)
  for (const el of pageRefs.values()) pageRO.observe(el)
  loadArtifact()
})

onBeforeUnmount(() => {
  pageRO?.disconnect()
  pageRO = null
})
</script>

<style scoped>
.da-page { flex: 1; min-width: 0; height: 100%; display: flex; flex-direction: column; overflow: hidden; padding: 56px 20px 16px; }
.da-content-card-wrapper { display: flex; flex-direction: column; flex: 1; min-height: 0; min-width: 0; overflow: hidden; }
.da-content-card { flex: 1; min-height: 0; min-width: 0; background: #FFFFFF; border-radius: 16px; border: 1px solid var(--ma-border-default); box-shadow: 0 1px 3px rgba(0,0,0,0.04); display: flex; flex-direction: column; overflow: hidden; }
.da-container { flex: 1; overflow-y: auto; padding: 20px 24px; }

.da-topbar { display: flex; align-items: center; justify-content: space-between; padding: 14px 24px; border-bottom: 1px solid var(--ma-border-default); flex-shrink: 0; background: var(--ma-bg-base); }
.da-topbar-right { display: flex; align-items: center; gap: 10px; }
.da-topbar-time { font-size: 12px; color: #9CA3AF; }

.da-btn { display: inline-flex; align-items: center; gap: 6px; padding: 7px 14px; border-radius: 8px; cursor: pointer; font-size: 13px; border: 1px solid #E5E7EB; background: #fff; color: #374151; transition: all 0.15s; white-space: nowrap; }
.da-btn:hover { border-color: #D1D5DB; background: #F9FAFB; }
.da-btn-ghost { background: transparent; border-color: #E5E7EB; }
.da-btn-ghost:hover { background: #F9FAFB; }
.da-btn-primary { background: #FF2442; color: #fff; border-color: #FF2442; }
.da-btn-primary:hover { background: #E0203A; border-color: #E0203A; }
.da-btn-danger { background: transparent; border-color: #FCA5A5; color: #EF4444; }
.da-btn-danger:hover { background: #FEF2F2; border-color: #F87171; }
.da-btn:disabled { opacity: 0.4; cursor: not-allowed; }

.da-work-badge { display: inline-block; font-size: 10px; padding: 1px 6px; border-radius: 4px; font-weight: 500; }
.da-badge-draft { background: #FEF3C7; color: #D97706; }
.da-badge-artifact { background: #EDE9FE; color: #7C3AED; }
.da-badge-published { background: #D1FAE5; color: #059669; }

.da-loading { display: flex; align-items: center; justify-content: center; gap: 8px; padding: 60px 0; color: #9CA3AF; font-size: 13px; }
.da-empty-state { text-align: center; padding: 80px 0; display: flex; flex-direction: column; align-items: center; gap: 8px; }
.da-empty-title { font-size: 16px; font-weight: 600; color: #1a1a1a; margin: 0; }

.pf-spin { animation: pf-spin-anim 1s linear infinite; }
@keyframes pf-spin-anim { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }

.dt-header { margin-bottom: 24px; }
.dt-title { font-size: 22px; font-weight: 700; color: #1a1a1a; margin: 0 0 6px; }
.dt-topic { font-size: 14px; color: #6B7280; margin: 0; }

.dt-pages { margin-bottom: 24px; }
.dt-pages-label { font-size: 12px; color: #9CA3AF; margin-bottom: 12px; font-weight: 500; }
.dt-pages-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 16px; }
.dt-page-wrap { border-radius: 10px; overflow: hidden; background: #F9FAFB; border: 1px solid #E5E7EB; }
.dt-page { position: relative; aspect-ratio: 3 / 4; overflow: hidden; }
.dt-page img { width: 100%; height: 100%; object-fit: cover; display: block; }
.dt-page-scaler { position: absolute; top: 0; left: 0; }
.dt-page-iframe { width: 1080px; height: 1440px; border: none; display: block; background: #F3F4F6; }
.dt-page-fallback { width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; font-size: 28px; font-weight: 600; color: #9CA3AF; background: linear-gradient(135deg, #F3F4F6, #E5E7EB); }
.dt-page-info { padding: 8px 12px; border-top: 1px solid #E5E7EB; }
.dt-page-role { font-size: 12px; color: #6B7280; }

.dt-meta { margin-bottom: 24px; display: flex; flex-direction: column; gap: 12px; padding: 16px; background: #F9FAFB; border-radius: 10px; }
.dt-meta-item { display: flex; gap: 12px; align-items: flex-start; }
.dt-meta-key { font-size: 12px; color: #9CA3AF; min-width: 72px; flex-shrink: 0; padding-top: 2px; }
.dt-meta-val { font-size: 13px; color: #374151; }
.dt-meta-tags { display: flex; flex-wrap: wrap; gap: 4px; }
.dt-tag { font-size: 11px; padding: 2px 8px; border-radius: 4px; }
.dt-tag-keep { background: #D1FAE5; color: #059669; }
.dt-tag-avoid { background: #FEE2E2; color: #DC2626; }

.dt-actions { display: flex; gap: 8px; padding-top: 16px; border-top: 1px solid #E5E7EB; }
</style>