<template>
  <div class="mint-shell ef-shell" :class="{ 'mint-collapsed': isSidebarCollapsed }">

    <SidebarNav
      current-page="esther-factory"
      :is-collapsed="isSidebarCollapsed"
      @nav-click="handleNavClick"
      @toggle-sidebar="toggleSidebar"
    />

    <div
      v-if="!isSidebarCollapsed"
      class="ef-sidebar-resizer"
      @mousedown="startSidebarResize"
    ><div class="ef-sidebar-resizer-line"></div></div>

    <main class="ef-page">
      <div class="ef-content-card-wrapper">
        <div class="ef-content-card">

          <div class="ef-body">

            <div class="ef-toolbar-card">
              <button class="ef-produce-toggle" :class="{ 'is-active': producePanelOpen }" @click="producePanelOpen = !producePanelOpen" type="button" title="模板工坊">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>
                </svg>
              </button>

              <button class="ef-library-toggle-btn" :class="{ 'is-active': libraryOpen }" @click="libraryOpen = !libraryOpen" type="button" title="模板库">
                <FolderOpen :size="18" />
              </button>

              <div class="ef-top-device-select" :class="{ 'is-open': deviceDropdownOpen }">
                <button class="ef-top-device-trigger" @click="deviceDropdownOpen = !deviceDropdownOpen" type="button">
                  <Smartphone :size="14" />
                  <span>{{ currentDevice.name }}</span>
                  <ChevronDown :size="12" class="ef-top-device-arrow" :class="{ 'is-open': deviceDropdownOpen }" />
                </button>
                <Transition name="ef-dropdown">
                  <div class="ef-top-device-dropdown" v-if="deviceDropdownOpen">
                    <div
                      v-for="d in DEVICE_PRESETS"
                      :key="d.id"
                      class="ef-top-device-option"
                      :class="{ 'is-active': selectedDevice === d.id }"
                      @click="selectedDevice = d.id; deviceDropdownOpen = false"
                    >
                      <span>{{ d.name }}</span>
                      <span class="ef-top-device-size">{{ d.width }}×{{ d.height }}</span>
                    </div>
                  </div>
                </Transition>
              </div>
            </div>

            <Transition name="ef-card-slide">
              <div v-if="producePanelOpen" class="ef-left-col ef-floating-card"
                :style="{ left: cardX + 'px', top: cardY + 'px', width: cardW + 'px' }"
              >
                <div class="ef-card-drag-bar" @mousedown="onCardDragStart">
                  <span class="ef-card-drag-dot"></span>
                  <span class="ef-card-drag-dot"></span>
                  <span class="ef-card-drag-dot"></span>
                </div>

                <section class="ef-panel ef-produce-panel">
                  <div class="ef-panel-header">
                    <div class="ef-panel-title">
                      <h2>模板工坊</h2>
                    </div>
                    <button class="ef-card-close-btn" @click="producePanelOpen = false" type="button" title="收起">
                      <X :size="14" />
                    </button>
                  </div>
                <div class="ef-panel-body ef-produce-body">

                  <div class="ef-brand-section" :class="{ 'ef-brand-section-open': showBrandConfig }">
                    <div class="ef-brand-section-toggle" @click="showBrandConfig = !showBrandConfig">
                      <div class="ef-brand-section-left">
                        <span class="ef-brand-dot" :class="{ 'ef-brand-dot-active': brandConfig.brand_name || brandConfig.avatar_url }"></span>
                        <span class="ef-brand-section-label">品牌配置</span>
                        <span class="ef-brand-section-status" v-if="brandConfig.brand_name || brandConfig.avatar_url">已配置</span>
                        <span class="ef-brand-section-status ef-brand-section-optional" v-else>可选</span>
                      </div>
                      <ChevronDown :size="14" class="ef-brand-chevron" :class="{ 'ef-brand-chevron-open': showBrandConfig }" />
                    </div>
                    <Transition name="ef-collapse">
                      <div class="ef-brand-section-body" v-if="showBrandConfig">
                        <div class="ef-brand-row">
                          <div class="ef-brand-avatar" @click="($refs.avatarInput as HTMLInputElement)?.click()">
                            <img :src="displayAvatarUrl" alt="头像" />
                            <div class="ef-avatar-overlay"><Camera :size="14" /></div>
                            <input ref="avatarInput" type="file" accept="image/*" class="ef-file-input" @change="handleAvatarUpload" />
                          </div>
                          <div class="ef-brand-fields">
                            <div class="ef-brand-field">
                              <label>品牌 / IP 名称</label>
                              <input v-model="brandConfig.brand_name" class="ef-input" placeholder="留空使用默认样式" @blur="saveBrandConfig" />
                            </div>
                            <div class="ef-brand-field">
                              <label>默认头像</label>
                              <div class="ef-gender-select">
                                <button class="ef-gender-btn" :class="{ 'ef-gender-btn-active': brandConfig.gender === 'man' }" @click="brandConfig.gender = 'man'; saveBrandConfig()" type="button">男生</button>
                                <button class="ef-gender-btn" :class="{ 'ef-gender-btn-active': brandConfig.gender === 'woman' }" @click="brandConfig.gender = 'woman'; saveBrandConfig()" type="button">女生</button>
                              </div>
                            </div>
                            <div class="ef-brand-colors">
                              <div class="ef-color-item">
                                <input type="color" v-model="brandConfig.primary" class="ef-color-picker" @change="saveBrandConfig" />
                                <span>主色</span>
                              </div>
                              <div class="ef-color-item">
                                <input type="color" v-model="brandConfig.accent" class="ef-color-picker" @change="saveBrandConfig" />
                                <span>强调色</span>
                              </div>
                              <div class="ef-color-item">
                                <input type="color" v-model="brandConfig.spot" class="ef-color-picker" @change="saveBrandConfig" />
                                <span>点缀色</span>
                              </div>
                            </div>
                          </div>
                        </div>
                        <div class="ef-brand-tip">
                          品牌名和头像为可选项。本系统开源的是设计方法论，不是身份授权。
                        </div>
                      </div>
                    </Transition>
                  </div>

                  <div class="ef-form-row">
                    <div class="ef-form-group ef-form-group-grow">
                      <label class="ef-label">模板 ID</label>
                      <input v-model="templateId" class="ef-input" placeholder="如 esther_steps_v2" />
                    </div>
                    <div class="ef-form-group">
                      <label class="ef-label">场景</label>
                      <div class="ef-scene-select" :class="{ 'is-open': sceneDropdownOpen }">
                        <button class="ef-scene-select-trigger" @click="sceneDropdownOpen = !sceneDropdownOpen" type="button">
                          <span class="ef-scene-select-value">{{ scenes.find(s => s.id === selectedScene)?.name || '场景' }}</span>
                          <ChevronDown :size="12" class="ef-scene-select-arrow" :class="{ 'is-open': sceneDropdownOpen }" />
                        </button>
                        <Transition name="ef-dropdown">
                          <div class="ef-scene-select-dropdown" v-if="sceneDropdownOpen">
                            <div
                              v-for="s in scenes"
                              :key="s.id"
                              class="ef-scene-select-option"
                              :class="{ 'is-active': selectedScene === s.id }"
                              @click="selectedScene = s.id; sceneDropdownOpen = false"
                            >{{ s.name }}</div>
                          </div>
                        </Transition>
                      </div>
                    </div>
                  </div>

                  <div class="ef-form-group">
                    <label class="ef-label">需求描述</label>
                    <textarea v-model="description" class="ef-textarea" rows="3"
                      placeholder="描述你想要的模板，如：步骤流程卡片，3-5个步骤，每个步骤有标题和描述..."></textarea>
                  </div>

                  <div class="ef-form-group">
                    <label class="ef-label">额外指令 <span class="ef-label-optional">可选</span></label>
                    <textarea v-model="extraInstructions" class="ef-textarea" rows="2"
                      placeholder="如：用更紧凑的间距，加一个页脚..."></textarea>
                  </div>

                  <button class="ef-produce-btn" @click="handleProduce" :disabled="producing || !templateId.trim() || !description.trim()" type="button">
                    <Loader2 v-if="producing" class="ef-spin" :size="16" />
                    <Wand2 v-else :size="16" />
                    <span>{{ producing ? '生产中...' : '开始生产' }}</span>
                  </button>

                  <div v-if="produceResult" class="ef-result" :class="{ 'ef-result-success': produceResult.success, 'ef-result-error': hasErrors }">
                    <div class="ef-result-icon">{{ produceResult.success ? '✓' : '✗' }}</div>
                    <div class="ef-result-body">
                      <div class="ef-result-title">{{ produceResult.success ? '模板生产成功' : '生产失败' }}</div>
                      <div v-if="produceResult.issues.length > 0" class="ef-issues">
                        <div v-for="(issue, idx) in produceResult.issues" :key="idx" class="ef-issue" :class="'ef-issue-' + issue.level">
                          <span class="ef-issue-level">{{ issue.level === 'error' ? '错误' : '警告' }}</span>
                          <span>{{ issue.message }}</span>
                        </div>
                      </div>
                      <div v-if="produceResult.error" class="ef-error-text">{{ produceResult.error }}</div>
                    </div>
                  </div>
                </div>
              </section>

            </div>
            </Transition>

            <div class="ef-right-col">

              <section class="ef-panel ef-preview-panel">
                <div class="ef-preview-canvas-area">
                  <div class="ef-preview-canvas-title">
                    <h2>智能画布</h2>
                    <span v-if="selectedTemplateId" class="ef-preview-id">{{ selectedTemplateId }}</span>
                  </div>
                  <div v-if="!selectedTemplateId" class="ef-empty ef-empty-preview">
                    <img src="/icons/logo3.svg" alt="Esther" class="ef-canvas-logo" />
                    <span class="ef-canvas-hint">选择一个模板来预览</span>
                  </div>
                  <div v-else-if="previewLoading" class="ef-empty ef-empty-preview">
                    <Loader2 class="ef-spin" :size="16" />
                    <span>加载预览...</span>
                  </div>
                  <div v-else-if="previewHtml" class="ef-preview-frame-wrapper"
                    @wheel="onCanvasWheel"
                    @mousedown="onCanvasMouseDown"
                    @mousemove="onCanvasMouseMove"
                    @mouseup="onCanvasMouseUp"
                    @mouseleave="onCanvasMouseUp"
                  >
                    <div class="ef-canvas-content" :style="{ transform: `translate(${canvasOffsetX}px, ${canvasOffsetY}px) scale(${canvasScale})` }">
                      <iframe class="ef-preview-frame ef-preview-frame-raw" :srcdoc="previewHtml" sandbox="allow-same-origin" :style="{ width: currentDevice.width + 'px', height: currentDevice.height + 'px' }"></iframe>
                    </div>
                    <div class="ef-canvas-controls">
                      <button class="ef-canvas-btn" @click="resetCanvasView" title="重置视图" type="button">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/></svg>
                      </button>
                      <span class="ef-canvas-zoom">{{ Math.round(canvasScale * 100) }}%</span>
                      <button class="ef-canvas-btn" @click="canvasScale = Math.min(3, canvasScale + 0.15)" title="放大" type="button">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/><line x1="11" y1="8" x2="11" y2="14"/><line x1="8" y1="11" x2="14" y2="11"/></svg>
                      </button>
                      <button class="ef-canvas-btn" @click="canvasScale = Math.max(0.3, canvasScale - 0.15)" title="缩小" type="button">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/><line x1="8" y1="11" x2="14" y2="11"/></svg>
                      </button>
                    </div>
                  </div>
                  <div v-else class="ef-empty ef-empty-preview">
                    <span>暂无预览</span>
                  </div>
                </div>

                <div class="ef-library-panel" :class="{ 'is-collapsed': !libraryOpen }">
                  <Transition name="ef-collapse">
                    <div class="ef-library-body" v-if="libraryOpen">
                      <div class="ef-library-toolbar">
                        <button class="ef-action-btn" @click="showImportModal = true" type="button">
                          <Upload :size="13" />
                          <span>导入</span>
                        </button>
                        <button
                          class="ef-action-btn"
                          :disabled="!selectedTemplateId"
                          @click="handleExport"
                          type="button"
                        >
                          <Download :size="13" />
                          <span>导出</span>
                        </button>
                      </div>
                      <div v-if="!templatesLoaded" class="ef-empty">
                        <Loader2 class="ef-spin" :size="16" />
                        <span>加载中...</span>
                      </div>
                      <div v-else-if="templates.length === 0" class="ef-empty">
                        <PackageOpen :size="28" />
                        <span>还没有模板</span>
                        <span class="ef-empty-hint">生产或导入你的第一个吧</span>
                      </div>
                      <div v-else class="ef-template-list">
                        <div
                          v-for="tpl in templates"
                          :key="tpl.id"
                          class="ef-template-card"
                          :class="{ 'is-active': selectedTemplateId === tpl.id }"
                          @click="selectedTemplateId = tpl.id"
                        >
                          <div class="ef-tpl-icon">
                            <LayoutTemplate :size="16" />
                          </div>
                          <div class="ef-tpl-info">
                            <div class="ef-tpl-name">{{ tpl.name }}</div>
                            <div class="ef-tpl-meta">
                              <span class="ef-tpl-scene">{{ tpl.scene }}</span>
                              <span class="ef-tpl-sep">·</span>
                              <span class="ef-tpl-fields">{{ tpl.fields_count }} 字段</span>
                            </div>
                          </div>
                          <button class="ef-tpl-delete" @click.stop="handleDelete(tpl.id)" type="button">
                            <X :size="14" />
                          </button>
                        </div>
                      </div>
                    </div>
                  </Transition>
                </div>
              </section>

            </div>

            <div v-if="showImportModal" class="ef-modal-overlay" @click.self="showImportModal = false">
              <div class="ef-modal">
                <div class="ef-modal-header">
                  <h3>导入模板</h3>
                  <button class="ef-modal-close" @click="showImportModal = false" type="button">
                    <X :size="16" />
                  </button>
                </div>
                <div class="ef-modal-body">
                  <div class="ef-modal-tabs">
                    <button
                      class="ef-modal-tab"
                      :class="{ 'is-active': importTab === 'file' }"
                      @click="importTab = 'file'"
                      type="button"
                    >上传文件</button>
                    <button
                      class="ef-modal-tab"
                      :class="{ 'is-active': importTab === 'paste' }"
                      @click="importTab = 'paste'"
                      type="button"
                    >粘贴 JSON</button>
                  </div>

                  <div v-if="importTab === 'file'" class="ef-import-tab">
                    <div
                      class="ef-drop-zone"
                      :class="{ 'is-dragover': isDragOver }"
                      @dragover.prevent="isDragOver = true"
                      @dragleave="isDragOver = false"
                      @drop.prevent="handleFileDrop"
                      @click="($refs.fileInput as HTMLInputElement)?.click()"
                    >
                      <Upload :size="24" />
                      <p>拖拽模板包 JSON 文件到此处</p>
                      <p class="ef-drop-hint">或点击选择文件</p>
                      <input ref="fileInput" type="file" accept=".json" class="ef-file-input" @change="handleFileSelect" />
                    </div>
                  </div>

                  <div v-if="importTab === 'paste'" class="ef-import-tab">
                    <textarea
                      v-model="importJsonText"
                      class="ef-textarea ef-import-textarea"
                      placeholder='粘贴模板包 JSON，格式：{"template_id":"...","schema":{...},"template_html":"...","meta":{...}}'
                      rows="10"
                    />
                  </div>

                  <div v-if="importError" class="ef-import-error">{{ importError }}</div>
                  <div v-if="importSuccess" class="ef-import-success">{{ importSuccess }}</div>
                </div>
                <div class="ef-modal-footer">
                  <label class="ef-overwrite-label">
                    <input v-model="importOverwrite" type="checkbox" />
                    覆盖已有同名模板
                  </label>
                  <button class="ef-btn-primary" :disabled="importing" @click="handleImport" type="button">
                    <Loader2 v-if="importing" class="ef-spin" :size="14" />
                    {{ importing ? '导入中...' : '确认导入' }}
                  </button>
                </div>
              </div>
            </div>

          </div>
        </div>
      </div>
    </main>

    <SettingsView v-if="showSettings" @close="showSettings = false" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { Wand2, Loader2, X, Upload, Download, ChevronDown, Camera, Sparkles, FolderOpen, PackageOpen, LayoutTemplate, Eye, Monitor, Smartphone } from 'lucide-vue-next'
import SidebarNav from '@/components/workbench/SidebarNav.vue'
import SettingsView from '@/views/SettingsView.vue'
import { estherFactoryApi, type SceneInfo, type TemplateInfo, type ProduceResult, type BrandConfig } from '@/api/esther_factory'

const router = useRouter()

const showSettings = ref(false)
function openSettings() {
  showSettings.value = true
}

// ===== Sidebar state =====
const SK_COLLAPSED = 'mint_sidebar_collapsed'
const isSidebarCollapsed = ref(localStorage.getItem(SK_COLLAPSED) === '1')

function toggleSidebar() {
  isSidebarCollapsed.value = !isSidebarCollapsed.value
  localStorage.setItem(SK_COLLAPSED, isSidebarCollapsed.value ? '1' : '0')
}

function handleNavClick(pageName: string) {
  if (pageName === 'esther-factory') return
  router.push({ path: '/workbench', query: pageName === 'workflow' ? {} : { page: pageName } })
}

// ===== Sidebar resize =====
const SK_SIDEBAR_WIDTH = 'mint_sidebar_width'
function applySidebarWidth(w: number) {
  const sidebar = document.querySelector('.ef-shell .mint-sidebar') as HTMLElement | null
  const wrapper = document.querySelector('.ef-shell .mint-sidebar-wrapper') as HTMLElement | null
  if (sidebar) sidebar.style.width = w + 'px'
  if (wrapper) wrapper.style.width = (w + 4) + 'px'
}
function startSidebarResize(e: MouseEvent) {
  e.preventDefault()
  const shell = document.querySelector('.ef-shell') as HTMLElement | null
  if (shell) shell.classList.add('ef-resizing')
  const startX = e.clientX
  const sidebarEl = document.querySelector('.ef-shell .mint-sidebar') as HTMLElement | null
  const startW = sidebarEl ? sidebarEl.offsetWidth : 192
  document.body.style.cursor = 'col-resize'
  document.body.style.userSelect = 'none'
  const onMove = (ev: MouseEvent) => {
    const delta = ev.clientX - startX
    const newW = Math.min(600, Math.max(170, startW + delta))
    applySidebarWidth(newW)
  }
  const onUp = () => {
    if (shell) shell.classList.remove('ef-resizing')
    document.body.style.cursor = ''
    document.body.style.userSelect = ''
    const cur = (document.querySelector('.ef-shell .mint-sidebar') as HTMLElement | null)?.offsetWidth || 192
    localStorage.setItem(SK_SIDEBAR_WIDTH, String(cur))
    document.removeEventListener('mousemove', onMove)
    document.removeEventListener('mouseup', onUp)
  }
  document.addEventListener('mousemove', onMove)
  document.addEventListener('mouseup', onUp)
}

// ===== Factory state =====
const FALLBACK_SCENES: SceneInfo[] = [
  { id: 'cards', name: '图文卡片' },
  { id: 'wechat', name: '公众号' },
  { id: 'tutorial', name: '教程页' },
  { id: 'landing', name: 'Landing页' },
  { id: 'app', name: 'App页面' },
]

interface DevicePreset {
  id: string
  name: string
  width: number
  height: number
}

const DEVICE_PRESETS: DevicePreset[] = [
  { id: 'xhs', name: '小红书', width: 375, height: 812 },
  { id: 'wechat', name: '微信公众号', width: 677, height: 812 },
  { id: 'phone', name: '通用手机', width: 375, height: 667 },
  { id: 'tablet', name: '平板', width: 768, height: 1024 },
  { id: 'free', name: '自适应', width: 540, height: 720 },
]

const scenes = ref<SceneInfo[]>([...FALLBACK_SCENES])
const templates = ref<TemplateInfo[]>([])
const producing = ref(false)
const previewHtml = ref('')
const previewLoading = ref(false)

const selectedScene = ref('cards')
const sceneDropdownOpen = ref(false)
const selectedDevice = ref('xhs')
const deviceDropdownOpen = ref(false)
const currentDevice = computed(() => DEVICE_PRESETS.find(d => d.id === selectedDevice.value) || DEVICE_PRESETS[0])
const libraryOpen = ref(false)
const templateId = ref('')
const description = ref('')
const extraInstructions = ref('')

const showBrandConfig = ref(false)
const brandConfig = ref<BrandConfig>({
  brand_name: '',
  avatar_url: '',
  gender: 'man',
  primary: '#2B7FD8',
  accent: '#F4D758',
  spot: '#E84A5F',
})

const defaultAvatarUrl = computed(() => {
  const g = brandConfig.value.gender || 'man'
  return `/images/avatar/@${g}.svg`
})

const displayAvatarUrl = computed(() => {
  return brandConfig.value.avatar_url || defaultAvatarUrl.value
})

const produceResult = ref<ProduceResult | null>(null)
const selectedTemplateId = ref('')

const canvasScale = ref(1)
const canvasOffsetX = ref(0)
const canvasOffsetY = ref(0)
const isDragging = ref(false)
const dragStartX = ref(0)
const dragStartY = ref(0)
const dragStartOffsetX = ref(0)
const dragStartOffsetY = ref(0)

const cardX = ref(24)
const cardY = ref(24)
const cardW = ref(380)
const producePanelOpen = ref(false)
const isCardDragging = ref(false)
const cardDragStartX = ref(0)
const cardDragStartY = ref(0)
const cardDragStartCardX = ref(0)
const cardDragStartCardY = ref(0)

function onCardDragStart(e: MouseEvent) {
  isCardDragging.value = true
  cardDragStartX.value = e.clientX
  cardDragStartY.value = e.clientY
  cardDragStartCardX.value = cardX.value
  cardDragStartCardY.value = cardY.value
  e.preventDefault()
}

function onCardMouseMove(e: MouseEvent) {
  if (!isCardDragging.value) return
  cardX.value = cardDragStartCardX.value + (e.clientX - cardDragStartX.value)
  cardY.value = cardDragStartCardY.value + (e.clientY - cardDragStartY.value)
}

function onCardMouseUp() {
  isCardDragging.value = false
}

function onCanvasWheel(e: WheelEvent) {
  e.preventDefault()
  const delta = e.deltaY > 0 ? -0.08 : 0.08
  canvasScale.value = Math.min(3, Math.max(0.3, canvasScale.value + delta))
}

function onCanvasMouseDown(e: MouseEvent) {
  if ((e.target as HTMLElement).closest('.ef-preview-frame-raw')) return
  isDragging.value = true
  dragStartX.value = e.clientX
  dragStartY.value = e.clientY
  dragStartOffsetX.value = canvasOffsetX.value
  dragStartOffsetY.value = canvasOffsetY.value
  e.preventDefault()
}

function onCanvasMouseMove(e: MouseEvent) {
  if (!isDragging.value) return
  canvasOffsetX.value = dragStartOffsetX.value + (e.clientX - dragStartX.value)
  canvasOffsetY.value = dragStartOffsetY.value + (e.clientY - dragStartY.value)
}

function onCanvasMouseUp() {
  isDragging.value = false
}

function resetCanvasView() {
  const wrapper = document.querySelector('.ef-preview-frame-wrapper') as HTMLElement | null
  if (wrapper) {
    const ww = wrapper.clientWidth
    const wh = wrapper.clientHeight
    const dw = currentDevice.value.width
    const dh = currentDevice.value.height
    const padding = 48
    const scaleX = (ww - padding) / dw
    const scaleY = (wh - padding) / dh
    canvasScale.value = Math.min(scaleX, scaleY, 1)
  } else {
    canvasScale.value = 1
  }
  canvasOffsetX.value = 0
  canvasOffsetY.value = 0
}

const templatesLoaded = ref(false)

onMounted(async () => {
  await loadBrandConfig()
  await loadScenes()
  await loadTemplates()
  document.addEventListener('click', handleDocClick)
  document.addEventListener('mousemove', onCardMouseMove)
  document.addEventListener('mouseup', onCardMouseUp)
  const savedW = localStorage.getItem(SK_SIDEBAR_WIDTH)
  if (savedW && !isSidebarCollapsed.value) applySidebarWidth(Number(savedW))
})

onBeforeUnmount(() => {
  document.removeEventListener('click', handleDocClick)
  document.removeEventListener('mousemove', onCardMouseMove)
  document.removeEventListener('mouseup', onCardMouseUp)
})

function handleDocClick(e: MouseEvent) {
  const target = e.target as HTMLElement
  if (!target.closest('.ef-scene-select')) {
    sceneDropdownOpen.value = false
  }
  if (!target.closest('.ef-top-device-select')) {
    deviceDropdownOpen.value = false
  }
}

async function loadBrandConfig() {
  try {
    const data = await estherFactoryApi.getBrandConfig()
    if (data) {
      brandConfig.value = { ...brandConfig.value, ...data }
    }
  } catch (e) {
    // 品牌配置加载失败，使用默认值
  }
}

async function saveBrandConfig() {
  try {
    await estherFactoryApi.saveBrandConfig(brandConfig.value)
  } catch (e) {
    console.error('Save brand config failed:', e)
  }
}

async function handleAvatarUpload(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  try {
    const result = await estherFactoryApi.uploadAvatar(file)
    brandConfig.value.avatar_url = result.avatar_url
    await saveBrandConfig()
  } catch (e) {
    console.error('Avatar upload failed:', e)
    alert('头像上传失败：' + (e as any)?.message || '未知错误')
  }
}

async function loadScenes() {
  try {
    const data = await estherFactoryApi.listScenes()
    if (Array.isArray(data) && data.length > 0) {
      scenes.value = data
    }
  } catch (e: any) {
    // Failed to load scenes, using fallback
  }
}

async function loadTemplates() {
  try {
    const data = await estherFactoryApi.listTemplates()
    templates.value = Array.isArray(data) ? data : []
    templatesLoaded.value = true
  } catch (e: any) {
    templatesLoaded.value = true
  }
}

async function handleProduce() {
  if (!templateId.value.trim() || !description.value.trim()) return

  producing.value = true
  produceResult.value = null
  previewHtml.value = ''

  try {
    const result = await estherFactoryApi.produce({
      scene: selectedScene.value,
      description: description.value,
      template_id: templateId.value.trim(),
      extra_instructions: extraInstructions.value,
    })
    produceResult.value = result
    if (result.success) {
      await loadTemplates()
      selectedTemplateId.value = templateId.value.trim()
      await loadPreview()
    }
  } catch (e: any) {
    const status = e?.response?.status
    let errMsg = e?.message || '生产失败'
    if (status === 401) errMsg = '登录已过期，请重新登录'
    else if (status === 404) errMsg = 'API 端点未找到，请检查后端服务是否正常运行'
    else if (status === 500) errMsg = '后端服务内部错误，请查看后端日志'
    else if (status === 0 || !status) errMsg = '无法连接到后端服务，请确认服务已启动'
    produceResult.value = {
      success: false,
      template_id: templateId.value,
      issues: [],
      error: errMsg,
    }
  } finally {
    producing.value = false
  }
}

async function loadPreview() {
  if (!selectedTemplateId.value) return

  previewLoading.value = true
  try {
    const schema = await estherFactoryApi.getSchema(selectedTemplateId.value)
    const sampleData = buildSampleData(schema?.template_schema ?? schema?.schema ?? schema)
    const html = await estherFactoryApi.render({
      template_id: selectedTemplateId.value,
      data: sampleData,
    })
    previewHtml.value = html
    nextTick(() => resetCanvasView())
  } catch (e: any) {
    console.error('Preview failed:', e)
    const status = e?.response?.status
    if (status === 404) previewHtml.value = '<div style="padding:24px;color:#991B1B;font-size:14px;">模板不存在，可能已被删除</div>'
    else if (status === 401) previewHtml.value = '<div style="padding:24px;color:#991B1B;font-size:14px;">登录已过期，请重新登录</div>'
    else if (status === 500) previewHtml.value = '<div style="padding:24px;color:#991B1B;font-size:14px;">后端服务错误，请查看日志</div>'
    else previewHtml.value = ''
  } finally {
    previewLoading.value = false
  }
}

function buildSampleData(schema: any): Record<string, any> {
  if (!schema?.fields) return {}
  const data: Record<string, any> = {}
  for (const field of schema.fields) {
    if (field.type === 'string') {
      data[field.key] = field.label || field.key
    } else if (field.type === 'array') {
      const items = field.items || []
      data[field.key] = [
        buildSampleData({ fields: items }),
        buildSampleData({ fields: items }),
        buildSampleData({ fields: items }),
      ]
    } else if (field.type === 'number') {
      data[field.key] = 1
    } else if (field.type === 'boolean') {
      data[field.key] = true
    }
  }
  return data
}

watch(selectedTemplateId, () => {
  loadPreview()
})

watch(selectedDevice, () => {
  resetCanvasView()
})

async function handleDelete(tplId: string) {
  try {
    await estherFactoryApi.deleteTemplate(tplId)
    await loadTemplates()
    if (selectedTemplateId.value === tplId) {
      selectedTemplateId.value = ''
      previewHtml.value = ''
    }
  } catch (e) {
    console.error('Delete failed:', e)
  }
}

// ===== Import / Export =====
const showImportModal = ref(false)
const importTab = ref<'file' | 'paste'>('file')
const importJsonText = ref('')
const importOverwrite = ref(false)
const importing = ref(false)
const importError = ref('')
const importSuccess = ref('')
const isDragOver = ref(false)
const importFileData = ref<any>(null)

function resetImportState() {
  importJsonText.value = ''
  importOverwrite.value = false
  importError.value = ''
  importSuccess.value = ''
  importFileData.value = null
  isDragOver.value = false
}

watch(showImportModal, (v) => {
  if (v) resetImportState()
})

function handleFileSelect(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (file) parseImportFile(file)
}

function handleFileDrop(e: DragEvent) {
  isDragOver.value = false
  const file = e.dataTransfer?.files?.[0]
  if (file) parseImportFile(file)
}

function parseImportFile(file: File) {
  importError.value = ''
  importSuccess.value = ''
  const reader = new FileReader()
  reader.onload = (e) => {
    try {
      const json = JSON.parse(e.target?.result as string)
      if (!json.template_id || !json.schema || !json.template_html) {
        importError.value = 'JSON 格式不正确，需要包含 template_id、schema、template_html 字段'
        return
      }
      importFileData.value = json
      importSuccess.value = `已解析文件：${json.template_id}`
    } catch {
      importError.value = 'JSON 解析失败，请检查文件格式'
    }
  }
  reader.readAsText(file)
}

async function handleImport() {
  importError.value = ''
  importSuccess.value = ''

  let data: any = null
  if (importTab.value === 'file') {
    data = importFileData.value
    if (!data) {
      importError.value = '请先选择或拖拽文件'
      return
    }
  } else {
    if (!importJsonText.value.trim()) {
      importError.value = '请粘贴模板包 JSON'
      return
    }
    try {
      data = JSON.parse(importJsonText.value)
    } catch {
      importError.value = 'JSON 解析失败，请检查格式'
      return
    }
    if (!data.template_id || !data.schema || !data.template_html) {
      importError.value = 'JSON 格式不正确，需要包含 template_id、schema、template_html 字段'
      return
    }
  }

  importing.value = true
  try {
    const result = await estherFactoryApi.importTemplate({
      template_id: data.template_id,
      template_schema: data.schema,
      template_html: data.template_html,
      meta: data.meta || {},
      overwrite: importOverwrite.value,
    })
    if (result.success) {
      importSuccess.value = `模板「${result.template_id}」导入成功！`
      await loadTemplates()
      selectedTemplateId.value = result.template_id
      setTimeout(() => { showImportModal.value = false }, 1200)
    } else {
      importError.value = result.error || '导入失败'
    }
  } catch (e: any) {
    const status = e?.response?.status
    if (status === 401) importError.value = '登录已过期，请重新登录'
    else if (status === 404) importError.value = 'API 端点未找到，请检查后端服务'
    else if (status === 500) importError.value = '后端内部错误，请查看日志'
    else importError.value = e?.response?.data?.detail || e?.message || '导入请求失败'
  } finally {
    importing.value = false
  }
}

async function handleExport() {
  if (!selectedTemplateId.value) return
  try {
    const result = await estherFactoryApi.exportTemplate(selectedTemplateId.value)
    const blob = new Blob(
      [JSON.stringify(result, null, 2)],
      { type: 'application/json' },
    )
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${result.template_id}.json`
    a.click()
    URL.revokeObjectURL(url)
  } catch (e: any) {
    const status = e?.response?.status
    if (status === 404) alert('模板不存在，可能已被删除')
    else if (status === 401) alert('登录已过期，请重新登录')
    else alert('导出失败：' + (e?.message || '未知错误'))
  }
}

const hasErrors = computed(() => {
  return produceResult.value?.issues?.some(i => i.level === 'error') ?? false
})
</script>

<style scoped>
.ef-shell {
  grid-template-columns: auto auto 1fr !important;
}

.ef-shell.mint-collapsed {
  grid-template-columns: 56px 1fr !important;
}

.ef-page {
  flex: 1;
  min-width: 0;
  height: 100%;
  background: #F5F5F7;
  font-family: var(--ma-font-sans);
  color: var(--ma-text-primary);
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  padding: 56px 20px 16px 20px;
}

.ef-content-card-wrapper {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  min-width: 0;
  overflow: hidden;
}

.ef-content-card {
  flex: 1;
  min-height: 0;
  min-width: 0;
  background: #FFFFFF;
  border-radius: 16px;
  border: 1px solid var(--ma-border-default, #E5E7EB);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* ===== Brand Config Section (inside produce panel) ===== */
.ef-brand-section {
  margin-bottom: 16px;
  border: 1px solid var(--ma-border-default, #E5E7EB);
  border-radius: 12px;
  overflow: hidden;
}

.ef-brand-section-toggle {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  cursor: pointer;
  user-select: none;
  transition: background 0.15s ease;
}

.ef-brand-section-toggle:hover {
  background: var(--ma-bg-subtle, #F7F8FA);
}

.ef-brand-section-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.ef-brand-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--ma-border-default, #E5E7EB);
  flex-shrink: 0;
  transition: all 0.2s ease;
}

.ef-brand-dot-active {
  background: #10B981;
  box-shadow: 0 0 0 3px rgba(16, 185, 129, 0.15), 0 0 8px rgba(16, 185, 129, 0.2);
}

.ef-brand-section-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--ma-text-secondary, #6B7280);
}

.ef-brand-section-status {
  font-size: 10px;
  padding: 1px 8px;
  border-radius: 10px;
  font-weight: 600;
  letter-spacing: 0.02em;
}

.ef-brand-section-status:not(.ef-brand-section-optional) {
  background: rgba(16, 185, 129, 0.1);
  color: #059669;
}

.ef-brand-section-optional {
  background: var(--ma-bg-subtle, #F7F8FA);
  color: var(--ma-text-tertiary, #9CA3AF);
}

.ef-brand-chevron {
  color: var(--ma-text-tertiary, #9CA3AF);
  transition: transform 0.25s cubic-bezier(0.4, 0, 0.2, 1);
}

.ef-brand-chevron-open {
  transform: rotate(180deg);
}

.ef-brand-section-body {
  padding: 14px 14px 16px;
}

@keyframes ef-slide-down {
  from { opacity: 0; transform: translateY(-6px); }
  to { opacity: 1; transform: translateY(0); }
}

.ef-brand-row {
  display: flex;
  gap: 20px;
  align-items: flex-start;
}

.ef-brand-avatar {
  width: 60px;
  height: 60px;
  border-radius: 16px;
  border: 2px dashed var(--ma-border-default, #E5E7EB);
  overflow: hidden;
  cursor: pointer;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--ma-bg-subtle, #F7F8FA);
  transition: all 0.2s ease;
  position: relative;
}

.ef-brand-avatar:hover {
  border-color: #2B7FD8;
  background: rgba(43, 127, 216, 0.04);
  box-shadow: 0 0 0 3px rgba(43, 127, 216, 0.08);
}

.ef-brand-avatar:hover .ef-avatar-overlay {
  opacity: 1;
}

.ef-brand-avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.ef-avatar-overlay {
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.35);
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  opacity: 0;
  transition: opacity 0.2s ease;
  border-radius: 14px;
}

.ef-avatar-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 3px;
  color: var(--ma-text-tertiary, #9CA3AF);
  font-size: 9px;
}

.ef-gender-select {
  display: flex;
  gap: 6px;
}

.ef-gender-btn {
  padding: 4px 14px;
  border-radius: 8px;
  border: 1px solid var(--ma-border-default, #E5E7EB);
  background: var(--ma-bg-elevated, #FFFFFF);
  font-size: 12px;
  color: var(--ma-text-secondary, #6B7280);
  cursor: pointer;
  transition: all 0.15s ease;
}

.ef-gender-btn:hover {
  border-color: #2B7FD8;
  color: #2B7FD8;
}

.ef-gender-btn-active {
  background: #2B7FD8;
  border-color: #2B7FD8;
  color: white;
}

.ef-brand-fields {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.ef-brand-field label {
  display: block;
  font-size: 12px;
  font-weight: 600;
  color: var(--ma-text-tertiary, #9CA3AF);
  margin-bottom: 5px;
}

.ef-brand-colors {
  display: flex;
  gap: 16px;
}

.ef-color-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: var(--ma-text-tertiary, #9CA3AF);
}

.ef-color-picker {
  width: 28px;
  height: 28px;
  border: 2px solid var(--ma-border-default, #E5E7EB);
  border-radius: 8px;
  cursor: pointer;
  background: transparent;
  padding: 2px;
  transition: all 0.15s ease;
}

.ef-color-picker:hover {
  border-color: #2B7FD8;
  box-shadow: 0 0 0 2px rgba(43, 127, 216, 0.1);
}

.ef-brand-tip {
  margin-top: 12px;
  font-size: 11px;
  color: var(--ma-text-tertiary, #9CA3AF);
  line-height: 1.6;
  padding: 8px 12px;
  background: var(--ma-bg-subtle, #F7F8FA);
  border-radius: 8px;
}

/* ===== Two-column body ===== */
.ef-body {
  position: relative;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.ef-left-col {
  display: flex;
  flex-direction: column;
  gap: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
}

.ef-floating-card {
  position: absolute;
  z-index: 20;
  background: var(--ma-bg-elevated, #FFFFFF);
  border-radius: 16px;
  box-shadow:
    0 8px 32px rgba(0, 0, 0, 0.12),
    0 2px 8px rgba(0, 0, 0, 0.06);
  max-height: calc(100% - 48px);
  overflow: hidden;
  transition: box-shadow 0.2s ease;
}

.ef-floating-card:hover {
  box-shadow:
    0 12px 40px rgba(0, 0, 0, 0.15),
    0 4px 12px rgba(0, 0, 0, 0.08);
}

.ef-card-drag-bar {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  padding: 8px 0 4px;
  cursor: grab;
  user-select: none;
}

.ef-card-drag-bar:active {
  cursor: grabbing;
}

.ef-card-drag-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--ma-border-default, #E5E7EB);
  transition: background 0.15s ease;
}

.ef-card-drag-bar:hover .ef-card-drag-dot {
  background: var(--ma-text-tertiary, #9CA3AF);
}

.ef-toolbar-card {
  position: absolute;
  left: 12px;
  top: 12px;
  z-index: 25;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px;
  background: rgba(255, 255, 255, 0.08);
  border-radius: 14px;
  backdrop-filter: blur(8px);
}

.ef-produce-toggle {
  width: 40px;
  height: 40px;
  border-radius: 10px;
  border: none;
  background: transparent;
  color: #9CA3AF;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s ease;
}

.ef-produce-toggle:hover {
  background: rgba(255, 255, 255, 0.1);
  color: #FF2442;
}

.ef-produce-toggle.is-active {
  color: #FF2442;
  background: rgba(255, 36, 66, 0.12);
}

.ef-card-close-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 8px;
  border: none;
  background: transparent;
  color: var(--ma-text-tertiary, #9CA3AF);
  cursor: pointer;
  transition: all 0.15s ease;
}

.ef-card-close-btn:hover {
  background: var(--ma-bg-subtle, #F7F8FA);
  color: var(--ma-text-secondary, #6B7280);
}

/* Card slide transition */
.ef-card-slide-enter-active {
  transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
}

.ef-card-slide-leave-active {
  transition: all 0.2s cubic-bezier(0.4, 0, 1, 1);
}

.ef-card-slide-enter-from {
  opacity: 0;
  transform: translateX(-30px) scale(0.95);
}

.ef-card-slide-leave-to {
  opacity: 0;
  transform: translateX(-20px) scale(0.97);
}

.ef-right-col {
  display: flex;
  flex-direction: column;
  gap: 0;
  overflow: hidden;
  min-width: 0;
  width: 100%;
  height: 100%;
}

.ef-right-col .ef-preview-panel {
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.ef-preview-canvas-area {
  flex: 1;
  min-height: 0;
  position: relative;
  background: #FFFFFF;
  display: flex;
  flex-direction: column;
}

.ef-preview-canvas-title {
  position: absolute;
  top: 12px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 20;
  display: flex;
  align-items: center;
  gap: 8px;
}

.ef-preview-canvas-title h2 {
  font-size: 13px;
  font-weight: 600;
  color: rgba(107, 114, 128, 0.5);
  margin: 0;
  letter-spacing: 0.02em;
  white-space: nowrap;
}

.ef-library-panel {
  flex: 0 0 auto;
  min-width: 0;
  border-top: none;
  background: var(--ma-bg-elevated, #FFFFFF);
}

.ef-template-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

/* ===== Panel ===== */
.ef-panel {
  display: flex;
  flex-direction: column;
}

.ef-panel-header {
  padding: 14px 24px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: var(--ma-bg-elevated, #FFFFFF);
  flex-shrink: 0;
}

.ef-panel-title {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--ma-text-tertiary, #9CA3AF);
}

.ef-panel-title h2 {
  font-size: 16px;
  font-weight: 700;
  color: var(--ma-text-secondary, #6B7280);
  margin: 0;
  letter-spacing: -0.01em;
}

.ef-toolbar-card .ef-top-device-dropdown {
  background: #2A2A2E;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.3), 0 2px 8px rgba(0, 0, 0, 0.2);
}

.ef-toolbar-card .ef-top-device-option {
  color: #9CA3AF;
}

.ef-toolbar-card .ef-top-device-option:hover {
  background: rgba(255, 255, 255, 0.08);
  color: #E5E7EB;
}

.ef-toolbar-card .ef-top-device-option.is-active {
  background: rgba(43, 127, 216, 0.12);
  color: #93C5FD;
}

.ef-toolbar-card .ef-top-device-size {
  color: rgba(156, 163, 175, 0.5);
}

.ef-toolbar-card .ef-top-device-option.is-active .ef-top-device-size {
  color: rgba(147, 197, 253, 0.5);
}

.ef-preview-title-centered {
  position: absolute;
  left: 50%;
  transform: translateX(-50%);
}

.ef-preview-id {
  font-size: 11px;
  color: rgba(156, 163, 175, 0.5);
  font-family: var(--ma-font-mono, 'SF Mono', 'Fira Code', monospace);
  background: rgba(255, 255, 255, 0.06);
  padding: 3px 10px;
  border-radius: 8px;
  letter-spacing: 0.02em;
  margin-left: auto;
}

.ef-library-toggle-btn {
  width: 40px;
  height: 40px;
  border-radius: 10px;
  border: none;
  background: transparent;
  color: #9CA3AF;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s ease;
}

.ef-library-toggle-btn:hover {
  background: rgba(255, 255, 255, 0.1);
  color: #2B7FD8;
}

.ef-library-toggle-btn.is-active {
  color: #2B7FD8;
  background: rgba(43, 127, 216, 0.12);
}

/* ===== Top Device Select ===== */
.ef-top-device-select {
  position: relative;
}
.ef-top-device-trigger {
  display: flex;
  align-items: center;
  gap: 6px;
  height: 40px;
  padding: 0 14px;
  border-radius: 10px;
  border: none;
  background: transparent;
  color: #9CA3AF;
  font-size: 12px;
  font-weight: 600;
  font-family: inherit;
  cursor: pointer;
  transition: all 0.2s ease;
}
.ef-top-device-trigger:hover {
  background: rgba(255, 255, 255, 0.1);
  color: #E5E7EB;
}
.ef-top-device-arrow {
  transition: transform 0.2s ease;
}
.ef-top-device-arrow.is-open {
  transform: rotate(180deg);
}
.ef-top-device-dropdown {
  position: absolute;
  top: calc(100% + 6px);
  left: 0;
  min-width: 180px;
  background: var(--ma-bg-elevated, #FFFFFF);
  border-radius: 10px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12), 0 2px 8px rgba(0, 0, 0, 0.06);
  padding: 4px;
  z-index: 30;
}
.ef-top-device-option {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  font-size: 12px;
  font-weight: 500;
  color: var(--ma-text-secondary, #6B7280);
  border-radius: 7px;
  cursor: pointer;
  transition: all 0.15s ease;
}
.ef-top-device-option:hover {
  background: var(--ma-bg-subtle, #F7F8FA);
  color: #2B7FD8;
}
.ef-top-device-option.is-active {
  background: rgba(43, 127, 216, 0.08);
  color: #2B7FD8;
  font-weight: 600;
}
.ef-top-device-size {
  font-size: 10px;
  color: var(--ma-text-tertiary, #9CA3AF);
  font-weight: 400;
}
.ef-top-device-option.is-active .ef-top-device-size {
  color: rgba(43, 127, 216, 0.6);
}

/* ===== Raw Preview Frame (no phone) ===== */
.ef-preview-frame-raw {
  border-radius: 12px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.08), 0 1px 4px rgba(0, 0, 0, 0.04);
  background: #fff;
}

.ef-panel-body {
  flex: 1;
  overflow-y: auto;
  padding: 20px 24px;
  overscroll-behavior: contain;
}

/* ===== Form ===== */
.ef-form-group {
  margin-bottom: 16px;
}

.ef-form-row {
  display: flex;
  gap: 12px;
}

.ef-form-group-grow {
  flex: 1;
}

.ef-label {
  display: block;
  font-size: 12px;
  font-weight: 600;
  color: var(--ma-text-tertiary, #9CA3AF);
  margin-bottom: 7px;
}

.ef-label-optional {
  font-weight: 400;
  text-transform: none;
  letter-spacing: 0;
  opacity: 0.7;
}

.ef-input {
  width: 100%;
  height: 38px;
  padding: 0 14px;
  border: none;
  border-radius: 12px;
  font-size: 13px;
  font-family: inherit;
  color: var(--ma-text-primary, #111827);
  background: var(--ma-bg-subtle, #F7F8FA);
  outline: none;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  box-sizing: border-box;
}

.ef-input:focus {
  background: var(--ma-bg-elevated, #FFFFFF);
  box-shadow: 0 0 0 2px rgba(43, 127, 216, 0.15);
}

.ef-input::placeholder {
  color: var(--ma-text-tertiary, #9CA3AF);
}

.ef-textarea {
  width: 100%;
  padding: 11px 14px;
  border: none;
  border-radius: 12px;
  font-size: 13px;
  font-family: inherit;
  color: var(--ma-text-primary, #111827);
  background: var(--ma-bg-subtle, #F7F8FA);
  outline: none;
  resize: vertical;
  line-height: 1.6;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  box-sizing: border-box;
}

.ef-textarea:focus {
  background: var(--ma-bg-elevated, #FFFFFF);
  box-shadow: 0 0 0 2px rgba(43, 127, 216, 0.15);
}

.ef-textarea::placeholder {
  color: var(--ma-text-tertiary, #9CA3AF);
}

/* ===== Scene Select Dropdown ===== */
.ef-scene-select {
  position: relative;
}

.ef-scene-select-trigger {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 9px 0;
  cursor: pointer;
  user-select: none;
  transition: color 0.15s ease;
}

.ef-scene-select-trigger:hover {
  color: #2B7FD8;
}

.ef-scene-select-value {
  font-size: 13px;
  font-weight: 600;
  color: var(--ma-text-primary, #111827);
  letter-spacing: -0.01em;
}

.ef-scene-select-arrow {
  color: var(--ma-text-tertiary, #9CA3AF);
  transition: transform 0.2s ease, color 0.15s ease;
  flex-shrink: 0;
}

.ef-scene-select-arrow.is-open {
  transform: rotate(180deg);
}

.ef-scene-select-dropdown {
  position: absolute;
  top: calc(100% + 4px);
  left: 0;
  right: 0;
  background: var(--ma-bg-elevated, #FFFFFF);
  border-radius: 10px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.08), 0 1px 4px rgba(0, 0, 0, 0.04);
  padding: 4px;
  z-index: 50;
  min-width: 140px;
}

.ef-scene-select-option {
  padding: 8px 12px;
  border-radius: 8px;
  font-size: 13px;
  color: var(--ma-text-secondary, #6B7280);
  cursor: pointer;
  transition: all 0.12s ease;
}

.ef-scene-select-option:hover {
  background: var(--ma-bg-subtle, #F7F8FA);
  color: #2B7FD8;
}

.ef-scene-select-option.is-active {
  background: rgba(43, 127, 216, 0.06);
  color: #2B7FD8;
  font-weight: 600;
}

/* Dropdown transition */
.ef-dropdown-enter-active,
.ef-dropdown-leave-active {
  transition: all 0.15s ease;
  transform-origin: top center;
}

.ef-dropdown-enter-from,
.ef-dropdown-leave-to {
  opacity: 0;
  transform: scaleY(0.95) translateY(-4px);
}

/* Produce button */
.ef-produce-btn {
  width: auto;
  min-width: 140px;
  padding: 11px 28px;
  border-radius: 20px;
  border: none;
  background: linear-gradient(135deg, #FF2442 0%, #E6203A 50%, #CC1A30 100%);
  color: #fff;
  font-size: 14px;
  font-weight: 700;
  font-family: inherit;
  cursor: pointer;
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  margin: 0 auto;
  box-shadow:
    0 4px 14px rgba(255, 36, 66, 0.3),
    0 1px 3px rgba(255, 36, 66, 0.2),
    inset 0 1px 0 rgba(255, 255, 255, 0.12);
  letter-spacing: 0.02em;
  position: relative;
  overflow: hidden;
}

.ef-produce-btn::before {
  content: '';
  position: absolute;
  top: 0;
  left: -100%;
  width: 100%;
  height: 100%;
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.08), transparent);
  transition: left 0.5s ease;
}

.ef-produce-btn:hover:not(:disabled)::before {
  left: 100%;
}

.ef-produce-btn:hover:not(:disabled) {
  box-shadow:
    0 6px 20px rgba(255, 36, 66, 0.4),
    0 2px 6px rgba(255, 36, 66, 0.25),
    inset 0 1px 0 rgba(255, 255, 255, 0.15);
  transform: translateY(-1px);
}

.ef-produce-btn:active:not(:disabled) {
  transform: translateY(0);
  box-shadow:
    0 2px 8px rgba(255, 36, 66, 0.25),
    inset 0 1px 0 rgba(255, 255, 255, 0.1);
}

.ef-produce-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
  box-shadow: none;
  transform: none;
}

/* Spinner */
.ef-spin {
  animation: ef-spin 0.7s linear infinite;
}

@keyframes ef-spin {
  to { transform: rotate(360deg); }
}

/* ===== Result ===== */
.ef-result {
  margin-top: 16px;
  padding: 14px 16px;
  border-radius: 12px;
  font-size: 12px;
  display: flex;
  gap: 12px;
  align-items: flex-start;
  animation: ef-result-in 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

@keyframes ef-result-in {
  from { opacity: 0; transform: translateY(-4px); }
  to { opacity: 1; transform: translateY(0); }
}

.ef-result-success {
  background: rgba(16, 185, 129, 0.06);
  border: 1px solid rgba(16, 185, 129, 0.15);
}

.ef-result-error {
  background: rgba(239, 68, 68, 0.06);
  border: 1px solid rgba(239, 68, 68, 0.15);
}

.ef-result-icon {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 700;
  flex-shrink: 0;
}

.ef-result-success .ef-result-icon {
  background: rgba(16, 185, 129, 0.15);
  color: #059669;
}

.ef-result-error .ef-result-icon {
  background: rgba(239, 68, 68, 0.15);
  color: #DC2626;
}

.ef-result-body {
  flex: 1;
  min-width: 0;
}

.ef-result-title {
  font-weight: 700;
  margin-bottom: 4px;
  color: var(--ma-text-primary, #111827);
}

.ef-issues {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.ef-issue {
  display: flex;
  gap: 6px;
  align-items: flex-start;
}

.ef-issue-level {
  font-size: 10px;
  padding: 2px 6px;
  border-radius: 4px;
  font-weight: 700;
  flex-shrink: 0;
}

.ef-issue-error .ef-issue-level {
  background: rgba(239, 68, 68, 0.12);
  color: #DC2626;
}

.ef-issue-warning .ef-issue-level {
  background: rgba(217, 119, 6, 0.12);
  color: #D97706;
}

.ef-error-text {
  margin-top: 4px;
  color: #DC2626;
}

/* ===== Library Panel (collapsible) ===== */
.ef-produce-body {
  flex: 0 0 auto !important;
  overflow-y: visible !important;
}

.ef-library-panel {
  flex: 0 0 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.ef-library-body {
  flex: 1;
  min-height: 0;
}

.ef-library-toggle {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 24px;
  cursor: pointer;
  user-select: none;
  transition: background 0.15s ease;
}

.ef-library-toggle:hover {
  background: var(--ma-bg-subtle, #F7F8FA);
}

.ef-library-toggle-left {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--ma-text-tertiary, #9CA3AF);
}

.ef-library-toggle-label {
  font-size: 13px;
  font-weight: 700;
  color: var(--ma-text-secondary, #6B7280);
  letter-spacing: -0.01em;
}

.ef-library-toggle-count {
  font-size: 11px;
  font-weight: 600;
  color: #2B7FD8;
  background: rgba(43, 127, 216, 0.08);
  padding: 1px 7px;
  border-radius: 10px;
}

.ef-library-toggle-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.ef-library-chevron {
  color: var(--ma-text-tertiary, #9CA3AF);
  transition: transform 0.2s ease;
  flex-shrink: 0;
}

.ef-library-chevron.is-open {
  transform: rotate(180deg);
}

.ef-library-body {
  padding: 12px 24px 16px;
  overflow-y: auto;
  overscroll-behavior: contain;
  max-height: 240px;
  border-top: 1px solid var(--ma-border-subtle, rgba(0, 0, 0, 0.06));
}

/* Collapse transition */
.ef-collapse-enter-active,
.ef-collapse-leave-active {
  transition: all 0.2s ease;
  overflow: hidden;
}

.ef-collapse-enter-from,
.ef-collapse-leave-to {
  max-height: 0;
  padding-top: 0;
  padding-bottom: 0;
  opacity: 0;
}

.ef-template-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.ef-template-card {
  padding: 12px 14px;
  border-radius: 12px;
  border: 1.5px solid transparent;
  background: var(--ma-bg-subtle, #F7F8FA);
  cursor: pointer;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  position: relative;
  display: flex;
  align-items: center;
  gap: 12px;
}

.ef-template-card:hover {
  background: var(--ma-bg-elevated, #FFFFFF);
  border-color: var(--ma-border-default, #E5E7EB);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
  transform: translateY(-1px);
}

.ef-template-card.is-active {
  border-color: #2B7FD8;
  background: rgba(43, 127, 216, 0.04);
  box-shadow: 0 2px 8px rgba(43, 127, 216, 0.1), 0 0 0 1px rgba(43, 127, 216, 0.06);
}

.ef-tpl-icon {
  width: 36px;
  height: 36px;
  border-radius: 10px;
  background: var(--ma-bg-elevated, #FFFFFF);
  border: 1px solid var(--ma-border-default, #E5E7EB);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--ma-text-tertiary, #9CA3AF);
  flex-shrink: 0;
  transition: all 0.2s ease;
}

.ef-template-card.is-active .ef-tpl-icon {
  background: linear-gradient(135deg, rgba(43, 127, 216, 0.1) 0%, rgba(27, 95, 181, 0.08) 100%);
  border-color: rgba(43, 127, 216, 0.2);
  color: #2B7FD8;
}

.ef-tpl-info {
  flex: 1;
  min-width: 0;
}

.ef-tpl-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--ma-text-primary, #111827);
  margin-bottom: 3px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.ef-tpl-meta {
  display: flex;
  gap: 5px;
  font-size: 11px;
  color: var(--ma-text-tertiary, #9CA3AF);
}

.ef-tpl-sep {
  opacity: 0.4;
}

.ef-tpl-delete {
  width: 26px;
  height: 26px;
  border-radius: 8px;
  border: none;
  background: transparent;
  color: var(--ma-text-tertiary, #9CA3AF);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s ease;
  opacity: 0;
  flex-shrink: 0;
}

.ef-template-card:hover .ef-tpl-delete {
  opacity: 1;
}

.ef-tpl-delete:hover {
  background: rgba(239, 68, 68, 0.08);
  color: #DC2626;
}

/* ===== Empty states ===== */
.ef-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 32px 0;
  color: var(--ma-text-tertiary, #9CA3AF);
  font-size: 13px;
}

.ef-empty-hint {
  font-size: 11px;
  opacity: 0.7;
}

.ef-empty-preview {
  height: 100%;
  padding: 0;
  gap: 16px;
  color: rgba(156, 163, 175, 0.5);
}

.ef-canvas-logo {
  width: 320px;
  height: auto;
  opacity: 0.15;
  filter: grayscale(0.3) brightness(1.2);
  pointer-events: none;
  user-select: none;
}

.ef-canvas-hint {
  font-size: 13px;
  opacity: 0.5;
}

/* ===== Preview ===== */
.ef-preview-frame-wrapper {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  position: relative;
  cursor: grab;
  user-select: none;
}
.ef-preview-frame-wrapper:active {
  cursor: grabbing;
}

.ef-preview-frame-wrapper::before {
  content: '';
  position: absolute;
  inset: 0;
  background-image:
    radial-gradient(circle, rgba(0, 0, 0, 0.08) 1px, transparent 1px);
  background-size: 24px 24px;
  pointer-events: none;
}

.ef-canvas-content {
  display: flex;
  align-items: center;
  justify-content: center;
  transition: transform 0.08s ease-out;
  will-change: transform;
  z-index: 1;
}

.ef-canvas-controls {
  position: absolute;
  bottom: 12px;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  gap: 4px;
  background: rgba(255,255,255,0.85);
  backdrop-filter: blur(8px);
  border: 1px solid rgba(0,0,0,0.06);
  border-radius: 8px;
  padding: 4px 8px;
  z-index: 10;
  box-shadow: 0 2px 8px rgba(0,0,0,0.05);
}

.ef-canvas-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  border: none;
  background: transparent;
  color: #6B7280;
  cursor: pointer;
  border-radius: 6px;
  transition: all 0.15s ease;
}
.ef-canvas-btn:hover {
  background: rgba(0,0,0,0.06);
  color: #111827;
}

.ef-canvas-zoom {
  font-size: 11px;
  font-weight: 500;
  color: #9CA3AF;
  min-width: 36px;
  text-align: center;
}

.ef-phone-frame {
  width: 290px;
  height: 580px;
  border-radius: 28px;
  background: #fff;
  box-shadow:
    0 0 0 1px rgba(0, 0, 0, 0.04),
    0 0 0 4px rgba(0, 0, 0, 0.03),
    0 12px 40px rgba(0, 0, 0, 0.1),
    0 4px 12px rgba(0, 0, 0, 0.06);
  overflow: hidden;
  display: flex;
  flex-direction: column;
  position: relative;
  z-index: 1;
  flex-shrink: 0;
}

.ef-phone-notch {
  width: 90px;
  height: 6px;
  border-radius: 4px;
  background: rgba(0, 0, 0, 0.06);
  margin: 10px auto 0;
  flex-shrink: 0;
}

.ef-preview-frame {
  width: 100%;
  flex: 1;
  border: none;
}

/* ===== Library Actions ===== */
.ef-library-actions {
  display: flex;
  gap: 6px;
}

.ef-action-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 5px 12px;
  border: 1.5px solid var(--ma-border-default, #E5E7EB);
  border-radius: 8px;
  background: var(--ma-bg-elevated, #FFFFFF);
  color: var(--ma-text-secondary, #6B7280);
  font-size: 11px;
  font-weight: 500;
  font-family: inherit;
  cursor: pointer;
  transition: all 0.15s ease;
}

.ef-action-btn:hover:not(:disabled) {
  border-color: #2B7FD8;
  color: #2B7FD8;
  background: rgba(43, 127, 216, 0.03);
}

.ef-action-btn:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

/* ===== Modal ===== */
.ef-modal-overlay {
  position: fixed;
  inset: 0;
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.45);
  backdrop-filter: blur(6px);
  animation: ef-overlay-in 0.2s ease;
}

@keyframes ef-overlay-in {
  from { opacity: 0; }
  to { opacity: 1; }
}

.ef-modal {
  width: 520px;
  max-height: 80vh;
  display: flex;
  flex-direction: column;
  background: #fff;
  border-radius: 20px;
  box-shadow:
    0 32px 80px rgba(0, 0, 0, 0.2),
    0 0 0 1px rgba(0, 0, 0, 0.04);
  overflow: hidden;
  animation: ef-modal-in 0.25s cubic-bezier(0.4, 0, 0.2, 1);
}

@keyframes ef-modal-in {
  from { opacity: 0; transform: scale(0.96) translateY(8px); }
  to { opacity: 1; transform: scale(1) translateY(0); }
}

.ef-modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 28px;
}

.ef-modal-header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 700;
  color: var(--ma-text-primary, #111827);
}

.ef-modal-close {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border: none;
  border-radius: 10px;
  background: transparent;
  color: var(--ma-text-tertiary, #9CA3AF);
  cursor: pointer;
  transition: all 0.15s ease;
}

.ef-modal-close:hover {
  background: var(--ma-bg-subtle, #F7F8FA);
  color: var(--ma-text-primary, #111827);
}

.ef-modal-body {
  flex: 1;
  padding: 24px 28px;
  overflow-y: auto;
}

.ef-modal-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 28px;
}

/* ===== Modal Tabs ===== */
.ef-modal-tabs {
  display: flex;
  gap: 4px;
  margin-bottom: 20px;
  padding: 4px;
  background: var(--ma-bg-subtle, #F7F8FA);
  border-radius: 12px;
}

.ef-modal-tab {
  flex: 1;
  padding: 8px 14px;
  border: none;
  border-radius: 9px;
  background: transparent;
  color: var(--ma-text-secondary, #6B7280);
  font-size: 12px;
  font-weight: 600;
  font-family: inherit;
  cursor: pointer;
  transition: all 0.2s ease;
}

.ef-modal-tab.is-active {
  background: #fff;
  color: #2B7FD8;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.08);
}

/* ===== Import Tab ===== */
.ef-import-tab {
  min-height: 120px;
}

.ef-drop-zone {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 40px 24px;
  border: 2px dashed var(--ma-border-default, #E5E7EB);
  border-radius: 16px;
  color: var(--ma-text-tertiary, #9CA3AF);
  cursor: pointer;
  transition: all 0.2s ease;
}

.ef-drop-zone:hover,
.ef-drop-zone.is-dragover {
  border-color: #2B7FD8;
  background: rgba(43, 127, 216, 0.03);
  color: #2B7FD8;
}

.ef-drop-zone p {
  margin: 0;
  font-size: 13px;
}

.ef-drop-hint {
  font-size: 11px !important;
  opacity: 0.6;
}

.ef-file-input {
  display: none;
}

.ef-import-textarea {
  font-family: 'SF Mono', 'Fira Code', monospace;
  font-size: 12px;
  line-height: 1.6;
  resize: vertical;
}

.ef-import-error {
  margin-top: 16px;
  padding: 12px 16px;
  border-radius: 12px;
  background: rgba(239, 68, 68, 0.06);
  border: 1px solid rgba(239, 68, 68, 0.12);
  color: #DC2626;
  font-size: 12px;
}

.ef-import-success {
  margin-top: 16px;
  padding: 12px 16px;
  border-radius: 12px;
  background: rgba(16, 185, 129, 0.06);
  border: 1px solid rgba(16, 185, 129, 0.12);
  color: #059669;
  font-size: 12px;
}

.ef-overwrite-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--ma-text-secondary, #6B7280);
  cursor: pointer;
}

.ef-overwrite-label input[type='checkbox'] {
  width: 15px;
  height: 15px;
  accent-color: #2B7FD8;
}

.ef-btn-primary {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 9px 22px;
  border: none;
  border-radius: 10px;
  background: linear-gradient(135deg, #2B7FD8 0%, #1B5FB5 100%);
  color: #fff;
  font-size: 13px;
  font-weight: 600;
  font-family: inherit;
  cursor: pointer;
  transition: all 0.2s ease;
  box-shadow: 0 2px 8px rgba(43, 127, 216, 0.25);
}

.ef-btn-primary:hover:not(:disabled) {
  box-shadow: 0 4px 14px rgba(43, 127, 216, 0.35);
  transform: translateY(-1px);
}

.ef-btn-primary:disabled {
  opacity: 0.4;
  cursor: not-allowed;
  box-shadow: none;
}

/* ===== Sidebar resizer (Codex style) ===== */
.ef-sidebar-resizer {
  position: relative;
  width: 6px;
  cursor: col-resize;
  flex-shrink: 0;
  align-self: stretch;
  z-index: 5;
  transition: background 0.15s ease;
}
.ef-sidebar-resizer-line {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: 2px;
  height: 40px;
  border-radius: 2px;
  background: #E5E7EB;
  transition: background 0.15s ease, height 0.15s ease;
}
.ef-sidebar-resizer:hover {
  background: rgba(59, 108, 246, 0.08);
}
.ef-sidebar-resizer:hover .ef-sidebar-resizer-line {
  background: #3B6CF6;
  height: 60px;
}
.ef-sidebar-resizer:active,
.ef-shell.ef-resizing .ef-sidebar-resizer {
  background: rgba(59, 108, 246, 0.12);
}
.ef-shell.ef-resizing .ef-sidebar-resizer-line {
  background: #3B6CF6;
  height: 60px;
}
.ef-shell.ef-resizing .mint-sidebar {
  transition: none !important;
}

/* ===== Dark theme overrides ===== */
.dark-theme .ef-brand-section {
  border-color: #2d2d3d;
}

.dark-theme .ef-brand-section-toggle:hover {
  background: #22223a;
}

.dark-theme .ef-brand-dot-active {
  background: #34D399;
  box-shadow: 0 0 0 3px rgba(52, 211, 153, 0.15), 0 0 8px rgba(52, 211, 153, 0.2);
}

.dark-theme .ef-brand-section-status:not(.ef-brand-section-optional) {
  background: rgba(52, 211, 153, 0.12);
  color: #6EE7B7;
}

.dark-theme .ef-brand-section-optional {
  background: #22223a;
  color: #6b7280;
}

.dark-theme .ef-brand-avatar {
  background: #22223a;
  border-color: #3d3d4d;
}

.dark-theme .ef-brand-avatar:hover {
  border-color: #93c5fd;
  background: rgba(147, 197, 253, 0.06);
  box-shadow: 0 0 0 3px rgba(147, 197, 253, 0.1);
}

.dark-theme .ef-brand-tip {
  background: #22223a;
  color: #6b7280;
}

.dark-theme .ef-color-picker {
  border-color: #3d3d4d;
}

.dark-theme .ef-color-picker:hover {
  border-color: #93c5fd;
  box-shadow: 0 0 0 2px rgba(147, 197, 253, 0.1);
}

.dark-theme .ef-input,
.dark-theme .ef-textarea {
  background: #1a1a2e;
  color: #e5e5e5;
}

.dark-theme .ef-input:focus,
.dark-theme .ef-textarea:focus {
  background: #22223a;
  box-shadow: 0 0 0 2px rgba(147, 197, 253, 0.15);
}

.dark-theme .ef-input::placeholder,
.dark-theme .ef-textarea::placeholder {
  color: #4b5563;
}

.dark-theme .ef-scene-select-value {
  color: #e2e8f0;
}

.dark-theme .ef-scene-select-trigger:hover {
  color: #93c5fd;
}

.dark-theme .ef-scene-select-dropdown {
  background: #22223a;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.3), 0 1px 4px rgba(0, 0, 0, 0.2);
}

.dark-theme .ef-scene-select-option {
  color: #9ca3af;
}

.dark-theme .ef-scene-select-option:hover {
  background: #2d2d4d;
  color: #93c5fd;
}

.dark-theme .ef-scene-select-option.is-active {
  background: rgba(147, 197, 253, 0.08);
  color: #93c5fd;
}

.dark-theme .ef-produce-btn {
  background: linear-gradient(135deg, #FF2442 0%, #E6203A 50%, #CC1A30 100%);
  box-shadow:
    0 4px 14px rgba(255, 36, 66, 0.3),
    0 1px 3px rgba(255, 36, 66, 0.2),
    inset 0 1px 0 rgba(255, 255, 255, 0.08);
}

.dark-theme .ef-produce-btn:hover:not(:disabled) {
  box-shadow:
    0 6px 20px rgba(255, 36, 66, 0.4),
    0 2px 6px rgba(255, 36, 66, 0.25),
    inset 0 1px 0 rgba(255, 255, 255, 0.1);
}

.dark-theme .ef-content-card {
  background: #1a1a2e;
  border-color: #2d2d3d;
}

.dark-theme .ef-floating-card {
  background: #1a1a2e;
  box-shadow:
    0 8px 32px rgba(0, 0, 0, 0.4),
    0 2px 8px rgba(0, 0, 0, 0.2);
}

.dark-theme .ef-floating-card:hover {
  box-shadow:
    0 12px 40px rgba(0, 0, 0, 0.5),
    0 4px 12px rgba(0, 0, 0, 0.3);
}

.dark-theme .ef-card-drag-dot {
  background: #3d3d4d;
}

.dark-theme .ef-card-drag-bar:hover .ef-card-drag-dot {
  background: #6b7280;
}

.dark-theme .ef-produce-toggle {
  background: transparent;
  color: #6b7280;
  box-shadow: none;
}

.dark-theme .ef-produce-toggle:hover {
  background: rgba(255, 255, 255, 0.08);
  color: #FF2442;
}

.dark-theme .ef-produce-toggle.is-active {
  color: #FF2442;
  background: rgba(255, 36, 66, 0.1);
}

.dark-theme .ef-toolbar-card {
  background: rgba(255, 255, 255, 0.06);
}

.dark-theme .ef-card-close-btn {
  color: #6b7280;
}

.dark-theme .ef-card-close-btn:hover {
  background: #2d2d4a;
  color: #9CA3AF;
}

.dark-theme .ef-left-col {
  border-color: #2d2d3d;
}

.dark-theme .ef-panel-header {
  background: #1a1a2e;
  border-color: #2d2d3d;
}

.dark-theme .ef-panel-title h2 {
  color: #9ca3af;
}

.dark-theme .ef-preview-id {
  background: rgba(255, 255, 255, 0.06);
  color: rgba(156, 163, 175, 0.5);
}

.dark-theme .ef-template-card {
  background: #1a1a2e;
}

.dark-theme .ef-template-card:hover {
  background: #22223a;
  border-color: #3d3d4d;
}

.dark-theme .ef-template-card.is-active {
  border-color: #93c5fd;
  background: rgba(147, 197, 253, 0.06);
  box-shadow: 0 2px 8px rgba(147, 197, 253, 0.1), 0 0 0 1px rgba(147, 197, 253, 0.06);
}

.dark-theme .ef-tpl-icon {
  background: #22223a;
  border-color: #3d3d4d;
}

.dark-theme .ef-template-card.is-active .ef-tpl-icon {
  background: linear-gradient(135deg, rgba(147, 197, 253, 0.1) 0%, rgba(96, 165, 250, 0.08) 100%);
  border-color: rgba(147, 197, 253, 0.2);
  color: #93c5fd;
}

.dark-theme .ef-tpl-name {
  color: #e5e5e5;
}

.dark-theme .ef-tpl-delete:hover {
  background: rgba(239, 68, 68, 0.12);
  color: #FCA5A5;
}

.dark-theme .ef-result-success {
  background: rgba(16, 185, 129, 0.08);
  border-color: rgba(16, 185, 129, 0.18);
}

.dark-theme .ef-result-success .ef-result-icon {
  background: rgba(16, 185, 129, 0.15);
  color: #6EE7B7;
}

.dark-theme .ef-result-success .ef-result-title {
  color: #6EE7B7;
}

.dark-theme .ef-result-error {
  background: rgba(239, 68, 68, 0.08);
  border-color: rgba(239, 68, 68, 0.18);
}

.dark-theme .ef-result-error .ef-result-icon {
  background: rgba(239, 68, 68, 0.15);
  color: #FCA5A5;
}

.dark-theme .ef-result-error .ef-result-title {
  color: #FCA5A5;
}

.dark-theme .ef-issue-error .ef-issue-level {
  background: rgba(239, 68, 68, 0.15);
  color: #FCA5A5;
}

.dark-theme .ef-issue-warning .ef-issue-level {
  background: rgba(217, 119, 6, 0.15);
  color: #FCD34D;
}

.dark-theme .ef-error-text {
  color: #FCA5A5;
}

.dark-theme .ef-preview-frame-wrapper {
  background: #16162a;
}

.dark-theme .ef-preview-frame-wrapper::before {
  background-image: radial-gradient(circle, rgba(255, 255, 255, 0.04) 1px, transparent 1px);
}

.dark-theme .ef-phone-frame {
  background: #1a1a2e;
  box-shadow:
    0 0 0 1px rgba(255, 255, 255, 0.04),
    0 0 0 4px rgba(255, 255, 255, 0.02),
    0 12px 40px rgba(0, 0, 0, 0.35),
    0 4px 12px rgba(0, 0, 0, 0.25);
}

.dark-theme .ef-phone-notch {
  background: rgba(255, 255, 255, 0.06);
}

.dark-theme .ef-canvas-controls {
  background: rgba(30, 30, 50, 0.9);
  border-color: rgba(255, 255, 255, 0.08);
}
.dark-theme .ef-canvas-btn {
  color: #9CA3AF;
}
.dark-theme .ef-canvas-btn:hover {
  background: rgba(255, 255, 255, 0.08);
  color: #e5e5e5;
}
.dark-theme .ef-canvas-zoom {
  color: #6B7280;
}

.dark-theme .ef-action-btn {
  background: #22223a;
  border-color: #3d3d4d;
  color: #9ca3af;
}

.dark-theme .ef-action-btn:hover:not(:disabled) {
  border-color: #93c5fd;
  color: #93c5fd;
  background: rgba(147, 197, 253, 0.04);
}

.dark-theme .ef-modal {
  background: #1e1e2e;
  box-shadow:
    0 32px 80px rgba(0, 0, 0, 0.4),
    0 0 0 1px rgba(255, 255, 255, 0.04);
}

.dark-theme .ef-modal-header {
  border-color: #2d2d3d;
}

.dark-theme .ef-modal-header h3 {
  color: #e5e5e5;
}

.dark-theme .ef-modal-close:hover {
  background: #22223a;
  color: #e5e5e5;
}

.dark-theme .ef-modal-footer {
  border-color: #2d2d3d;
}

.dark-theme .ef-modal-tabs {
  background: #22223a;
}

.dark-theme .ef-modal-tab {
  color: #9ca3af;
}

.dark-theme .ef-modal-tab.is-active {
  background: #2d2d3d;
  color: #93c5fd;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.2);
}

.dark-theme .ef-drop-zone {
  border-color: #3d3d4d;
  color: #6b7280;
}

.dark-theme .ef-drop-zone:hover,
.dark-theme .ef-drop-zone.is-dragover {
  border-color: #93c5fd;
  background: rgba(147, 197, 253, 0.04);
  color: #93c5fd;
}

.dark-theme .ef-import-error {
  background: rgba(239, 68, 68, 0.1);
  border-color: rgba(239, 68, 68, 0.2);
  color: #FCA5A5;
}

.dark-theme .ef-import-success {
  background: rgba(16, 185, 129, 0.1);
  border-color: rgba(16, 185, 129, 0.2);
  color: #86EFAC;
}

.dark-theme .ef-empty {
  color: #6b7280;
}

.dark-theme .ef-library-panel {
  border-color: #2d2d3d;
}

.dark-theme .ef-library-toggle:hover {
  background: #22223a;
}

.dark-theme .ef-library-toggle-label {
  color: #9ca3af;
}

.dark-theme .ef-library-toggle-btn {
  background: transparent;
  box-shadow: none;
}

.dark-theme .ef-library-toggle-btn:hover {
  background: rgba(255, 255, 255, 0.08);
  color: #93c5fd;
}

.dark-theme .ef-library-toggle-btn.is-active {
  color: #93c5fd;
  background: rgba(43, 127, 216, 0.12);
}

.dark-theme .ef-top-device-trigger {
  background: transparent;
  color: #9ca3af;
  box-shadow: none;
}
.dark-theme .ef-top-device-trigger:hover {
  background: rgba(255, 255, 255, 0.08);
  color: #93c5fd;
}
.dark-theme .ef-top-device-dropdown {
  background: #22223a;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.3), 0 2px 8px rgba(0, 0, 0, 0.2);
}
.dark-theme .ef-top-device-option {
  color: #9ca3af;
}
.dark-theme .ef-top-device-option:hover {
  background: rgba(255, 255, 255, 0.06);
  color: #93c5fd;
}
.dark-theme .ef-top-device-option.is-active {
  color: #93c5fd;
  background: rgba(43, 127, 216, 0.12);
}
.dark-theme .ef-top-device-size {
  color: rgba(156, 163, 175, 0.5);
}
.dark-theme .ef-top-device-option.is-active .ef-top-device-size {
  color: rgba(147, 197, 253, 0.5);
}
.dark-theme .ef-preview-frame-raw {
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.2), 0 1px 4px rgba(0, 0, 0, 0.1);
}

.dark-theme .ef-library-toggle-count {
  color: #93c5fd;
  background: rgba(147, 197, 253, 0.1);
}

.dark-theme .ef-btn-primary {
  background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
  box-shadow: 0 2px 8px rgba(59, 130, 246, 0.25);
}

.dark-theme .ef-btn-primary:hover:not(:disabled) {
  box-shadow: 0 4px 14px rgba(59, 130, 246, 0.35);
}

.dark-theme .ef-overwrite-label {
  color: #9ca3af;
}

.dark-theme .ef-overwrite-label input[type='checkbox'] {
  accent-color: #3b82f6;
}
</style>