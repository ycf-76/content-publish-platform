/**
 * 卡片可视化编辑器
 *
 * 三栏布局：
 * - 左侧：模板选择 + 页面列表（增删排序）
 * - 中间：4 张卡片实时预览（1080×1440 缩放显示）
 * - 右侧：当前页面属性编辑（类型/文案）+ 模板样式调整（字号/配色）
 *
 * 导出：html2canvas 截图隐藏的高分辨率画布，生成 PNG
 */
<script setup lang="ts">
import { ref, computed, nextTick } from 'vue'
import html2canvas from 'html2canvas'
import CardRenderer from '@/components/CardRenderer.vue'
import { useRouter } from 'vue-router'
import {
  TEMPLATES,
  PAGE_TYPE_LABELS,
  createDefaultPage,
  createDefaultPages,
  type CardPage,
  type PageType,
  type TemplateTheme,
} from '@/card-editor/templates'

const router = useRouter()

// ===== 状态 =====
const currentTemplateId = ref<string>('minimal_white')
const pages = ref<CardPage[]>(createDefaultPages())
const selectedPageId = ref<string>(pages.value[0].id)

// 用户可覆盖模板默认值的样式调整（空则用模板默认）
const customFontSize = ref<number | null>(null)
const customBg = ref<string>('')
const customAccent = ref<string>('')

// 导出状态
const exporting = ref(false)
const exportProgress = ref('')
const exportError = ref('')
const exportedImages = ref<string[]>([]) // base64 dataUrl
const showExportPanel = ref(false)

// ===== 计算属性 =====
const currentTemplate = computed<TemplateTheme>(() => {
  return TEMPLATES.find(t => t.id === currentTemplateId.value) || TEMPLATES[0]
})

/** 合并模板默认值 + 用户自定义 */
const effectiveTheme = computed<TemplateTheme>(() => {
  return {
    ...currentTemplate.value,
    fontSize: customFontSize.value ?? currentTemplate.value.fontSize,
    bg: customBg.value || currentTemplate.value.bg,
    accent: customAccent.value || currentTemplate.value.accent,
  }
})

const selectedPage = computed<CardPage>(() => {
  return pages.value.find(p => p.id === selectedPageId.value) || pages.value[0]
})

const selectedIndex = computed(() => {
  return pages.value.findIndex(p => p.id === selectedPageId.value)
})

// ===== 页面操作 =====
function selectPage(id: string) {
  selectedPageId.value = id
}

function addPage(type: PageType) {
  const newPage = createDefaultPage(type, pages.value.length)
  pages.value.push(newPage)
  selectedPageId.value = newPage.id
}

function deletePage(id: string) {
  if (pages.value.length <= 1) {
    exportError.value = '至少保留 1 张卡片'
    setTimeout(() => (exportError.value = ''), 2000)
    return
  }
  const idx = pages.value.findIndex(p => p.id === id)
  pages.value.splice(idx, 1)
  if (selectedPageId.value === id) {
    selectedPageId.value = pages.value[Math.max(0, idx - 1)].id
  }
}

function movePage(id: string, direction: 'up' | 'down') {
  const idx = pages.value.findIndex(p => p.id === id)
  if (idx < 0) return
  const targetIdx = direction === 'up' ? idx - 1 : idx + 1
  if (targetIdx < 0 || targetIdx >= pages.value.length) return
  const tmp = pages.value[idx]
  pages.value[idx] = pages.value[targetIdx]
  pages.value[targetIdx] = tmp
}

function changePageType(id: string, newType: PageType) {
  const page = pages.value.find(p => p.id === id)
  if (!page) return
  // 切换类型时保留 title/content，补齐新类型所需字段
  page.type = newType
  if (newType === 'list' && !page.listItems) {
    page.listItems = ['第一项', '第二项', '第三项']
  }
  if (newType !== 'list') {
    delete page.listItems
  }
  if (newType === 'cover' && !page.subtitle) {
    page.subtitle = '副标题'
  }
}

// ===== 列表项操作（仅 list 类型） =====
function addListItem() {
  if (!selectedPage.value.listItems) {
    selectedPage.value.listItems = []
  }
  selectedPage.value.listItems.push('新要点')
}

function deleteListItem(index: number) {
  selectedPage.value.listItems?.splice(index, 1)
}

// ===== 模板切换 =====
function selectTemplate(id: string) {
  currentTemplateId.value = id
  // 切换模板时重置自定义样式
  customFontSize.value = null
  customBg.value = ''
  customAccent.value = ''
}

function resetCustomStyle() {
  customFontSize.value = null
  customBg.value = ''
  customAccent.value = ''
}

// ===== 导出 PNG =====
/** 隐藏的高分辨率渲染容器，导出时用 */
const exportContainer = ref<HTMLElement | null>(null)

async function exportToPng() {
  if (exporting.value) return
  exporting.value = true
  exportError.value = ''
  exportProgress.value = '准备渲染...'
  exportedImages.value = []
  showExportPanel.value = true

  try {
    await nextTick()
    if (!exportContainer.value) {
      throw new Error('渲染容器未就绪')
    }

    const cardEls = exportContainer.value.querySelectorAll('.card-canvas')
    if (cardEls.length === 0) {
      throw new Error('没有可导出的卡片')
    }

    const images: string[] = []
    for (let i = 0; i < cardEls.length; i++) {
      exportProgress.value = `正在生成第 ${i + 1}/${cardEls.length} 张...`
      await nextTick()

      const canvas = await html2canvas(cardEls[i] as HTMLElement, {
        scale: 2, // 2x 高清
        useCORS: true,
        backgroundColor: effectiveTheme.value.bg,
        logging: false,
        width: 1080,
        height: 1440,
        windowWidth: 1080,
        windowHeight: 1440,
      })

      const dataUrl = canvas.toDataURL('image/png')
      images.push(dataUrl)
      exportedImages.value = [...images]
    }

    exportProgress.value = `完成，共 ${images.length} 张`
  } catch (e) {
    exportError.value = `导出失败：${e instanceof Error ? e.message : String(e)}`
    exportProgress.value = ''
  } finally {
    exporting.value = false
  }
}

function downloadImage(index: number) {
  const dataUrl = exportedImages.value[index]
  if (!dataUrl) return
  const link = document.createElement('a')
  link.href = dataUrl
  link.download = `card_${index + 1}.png`
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
}

function downloadAll() {
  exportedImages.value.forEach((_, i) => {
    setTimeout(() => downloadImage(i), i * 300)
  })
}

/** 把导出的图片 base64 存到 sessionStorage，工作台读取后注入 image_gen 节点 */
function injectToWorkflow() {
  if (exportedImages.value.length === 0) return
  sessionStorage.setItem('card_editor_images', JSON.stringify(exportedImages.value))
  sessionStorage.setItem('card_editor_pages', JSON.stringify(pages.value.length))
  router.push('/workbench')
}

function closeExportPanel() {
  showExportPanel.value = false
}

// ===== 预览缩放 =====
// 预览区每张卡片宽度约 280px，1080 → 280 缩放比 0.259
const previewScale = 0.26
</script>

<template>
  <div class="card-editor">
    <!-- 顶部导航 -->
    <header class="ce-header">
      <div class="ce-header-left">
        <button class="ce-back-btn" @click="router.push('/workbench')">← 返回工作台</button>
        <h1 class="ce-title">卡片编辑器</h1>
      </div>
      <div class="ce-header-right">
        <button class="ce-export-btn" :disabled="exporting" @click="exportToPng">
          {{ exporting ? '生成中...' : '导出 PNG' }}
        </button>
      </div>
    </header>

    <div class="ce-body">
      <!-- 左侧：模板 + 页面列表 -->
      <aside class="ce-left">
        <section class="ce-panel">
          <h3 class="ce-panel-title">模板选择</h3>
          <div class="ce-template-list">
            <button
              v-for="tpl in TEMPLATES"
              :key="tpl.id"
              class="ce-template-item"
              :class="{ active: tpl.id === currentTemplateId }"
              @click="selectTemplate(tpl.id)"
            >
              <div class="ce-template-preview" :style="{ background: tpl.bg, color: tpl.text, borderColor: tpl.id === currentTemplateId ? tpl.accent : 'transparent' }">
                <span class="ce-template-preview-text" :style="{ color: tpl.accent }">Aa</span>
              </div>
              <div class="ce-template-info">
                <div class="ce-template-name">{{ tpl.name }}</div>
                <div class="ce-template-desc">{{ tpl.description }}</div>
              </div>
            </button>
          </div>
        </section>

        <section class="ce-panel">
          <h3 class="ce-panel-title">页面列表（{{ pages.length }} 张）</h3>
          <div class="ce-page-list">
            <div
              v-for="(page, i) in pages"
              :key="page.id"
              class="ce-page-item"
              :class="{ active: page.id === selectedPageId }"
              @click="selectPage(page.id)"
            >
              <span class="ce-page-num">{{ i + 1 }}</span>
              <span class="ce-page-type">{{ PAGE_TYPE_LABELS[page.type] }}</span>
              <span class="ce-page-title">{{ page.title || page.content.slice(0, 12) }}</span>
              <div class="ce-page-actions">
                <button class="ce-icon-btn" :disabled="i === 0" @click.stop="movePage(page.id, 'up')">↑</button>
                <button class="ce-icon-btn" :disabled="i === pages.length - 1" @click.stop="movePage(page.id, 'down')">↓</button>
                <button class="ce-icon-btn ce-icon-btn-danger" @click.stop="deletePage(page.id)">×</button>
              </div>
            </div>
          </div>
          <div class="ce-add-page">
            <button v-for="type in (['cover','content','quote','list'] as PageType[])" :key="type" class="ce-add-btn" @click="addPage(type)">
              + {{ PAGE_TYPE_LABELS[type] }}
            </button>
          </div>
        </section>
      </aside>

      <!-- 中间：预览区 -->
      <main class="ce-center">
        <div class="ce-preview-grid">
          <div
            v-for="(page, i) in pages"
            :key="page.id"
            class="ce-preview-card"
            :class="{ active: page.id === selectedPageId }"
            @click="selectPage(page.id)"
          >
            <div class="ce-preview-wrapper" :style="{ transform: `scale(${previewScale})` }">
              <CardRenderer :page="page" :theme="effectiveTheme" />
            </div>
            <div class="ce-preview-label">第 {{ i + 1 }} 张 · {{ PAGE_TYPE_LABELS[page.type] }}</div>
          </div>
        </div>
      </main>

      <!-- 右侧：属性编辑 -->
      <aside class="ce-right">
        <section class="ce-panel">
          <h3 class="ce-panel-title">当前页面编辑</h3>
          <div class="ce-form">
            <div class="ce-form-row">
              <label class="ce-label">页面类型</label>
              <select class="ce-select" :value="selectedPage.type" @change="changePageType(selectedPage.id, ($event.target as HTMLSelectElement).value as PageType)">
                <option v-for="(label, key) in PAGE_TYPE_LABELS" :key="key" :value="key">{{ label }}</option>
              </select>
            </div>

            <div v-if="selectedPage.type !== 'quote'" class="ce-form-row">
              <label class="ce-label">标题</label>
              <input class="ce-input" v-model="selectedPage.title" placeholder="输入标题" />
            </div>

            <div v-if="selectedPage.type === 'cover'" class="ce-form-row">
              <label class="ce-label">副标题</label>
              <input class="ce-input" v-model="selectedPage.subtitle" placeholder="副标题（可选）" />
            </div>

            <div v-if="selectedPage.type === 'content' || selectedPage.type === 'quote'" class="ce-form-row">
              <label class="ce-label">{{ selectedPage.type === 'quote' ? '金句内容' : '正文（支持换行）' }}</label>
              <textarea class="ce-textarea" v-model="selectedPage.content" :rows="selectedPage.type === 'quote' ? 3 : 6" placeholder="输入正文"></textarea>
            </div>

            <!-- 列表项编辑 -->
            <div v-if="selectedPage.type === 'list'" class="ce-form-row">
              <label class="ce-label">清单项</label>
              <div class="ce-list-editor">
                <div v-for="(item, i) in selectedPage.listItems" :key="i" class="ce-list-edit-item">
                  <span class="ce-list-edit-num">{{ i + 1 }}</span>
                  <input class="ce-input ce-list-edit-input" v-model="selectedPage.listItems![i]" />
                  <button class="ce-icon-btn ce-icon-btn-danger" @click="deleteListItem(i)">×</button>
                </div>
                <button class="ce-add-list-btn" @click="addListItem">+ 添加一项</button>
              </div>
            </div>

            <div class="ce-form-row">
              <label class="ce-label">页脚</label>
              <input class="ce-input" v-model="selectedPage.footer" placeholder="页脚文字（可选）" />
            </div>
          </div>
        </section>

        <section class="ce-panel">
          <h3 class="ce-panel-title">
            样式调整
            <button class="ce-reset-btn" @click="resetCustomStyle">重置为模板默认</button>
          </h3>
          <div class="ce-form">
            <div class="ce-form-row">
              <label class="ce-label">字号（{{ effectiveTheme.fontSize }}px）</label>
              <input type="range" class="ce-range" min="32" max="72" step="2" v-model.number="customFontSize" :placeholder="String(currentTemplate.fontSize)" />
            </div>
            <div class="ce-form-row">
              <label class="ce-label">背景色</label>
              <div class="ce-color-row">
                <input type="color" class="ce-color" v-model="customBg" />
                <input class="ce-input ce-color-text" v-model="customBg" :placeholder="currentTemplate.bg" />
              </div>
            </div>
            <div class="ce-form-row">
              <label class="ce-label">强调色</label>
              <div class="ce-color-row">
                <input type="color" class="ce-color" v-model="customAccent" />
                <input class="ce-input ce-color-text" v-model="customAccent" :placeholder="currentTemplate.accent" />
              </div>
            </div>
          </div>
        </section>
      </aside>
    </div>

    <!-- 隐藏的导出容器：1080×1440 原始尺寸，html2canvas 截图用 -->
    <div ref="exportContainer" class="ce-export-container" aria-hidden="true">
      <CardRenderer
        v-for="page in pages"
        :key="page.id"
        :page="page"
        :theme="effectiveTheme"
      />
    </div>

    <!-- 导出结果面板 -->
    <Teleport to="body">
      <div v-if="showExportPanel" class="ce-export-overlay" @click.self="closeExportPanel">
        <div class="ce-export-modal">
          <div class="ce-export-modal-header">
            <h3>导出结果</h3>
            <button class="ce-export-close" @click="closeExportPanel">×</button>
          </div>
          <div class="ce-export-modal-body">
            <p v-if="exportProgress" class="ce-export-progress">{{ exportProgress }}</p>
            <p v-if="exportError" class="ce-export-error">{{ exportError }}</p>
            <div v-if="exportedImages.length > 0" class="ce-export-grid">
              <div v-for="(img, i) in exportedImages" :key="i" class="ce-export-thumb">
                <img :src="img" :alt="`卡片 ${i + 1}`" />
                <button class="ce-download-btn" @click="downloadImage(i)">下载第 {{ i + 1 }} 张</button>
              </div>
            </div>
          </div>
          <div class="ce-export-modal-footer" v-if="exportedImages.length > 0">
            <button class="ce-action-btn ce-action-btn-secondary" @click="downloadAll">全部下载</button>
            <button class="ce-action-btn ce-action-btn-primary" @click="injectToWorkflow">注入工作流</button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.card-editor {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: #EEF0F4;
  color: #1A1A1A;
  font-family: 'PingFang SC', 'Microsoft YaHei', sans-serif;
}

/* ===== 顶部导航 ===== */
.ce-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 24px;
  background: #FFFFFF;
  border-bottom: 1px solid #E5E7EB;
  flex-shrink: 0;
}
.ce-header-left {
  display: flex;
  align-items: center;
  gap: 16px;
}
.ce-back-btn {
  padding: 6px 12px;
  background: transparent;
  border: 1px solid #E5E7EB;
  border-radius: 6px;
  color: #6B7280;
  cursor: pointer;
  font-size: 14px;
  transition: all 0.2s;
}
.ce-back-btn:hover {
  border-color: #065F46;
  color: #065F46;
}
.ce-title {
  font-size: 20px;
  font-weight: 600;
  color: #065F46;
  margin: 0;
}
.ce-export-btn {
  padding: 8px 20px;
  background: #065F46;
  color: #FFFFFF;
  border: none;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.2s;
}
.ce-export-btn:hover:not(:disabled) {
  background: #047857;
}
.ce-export-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* ===== 三栏布局 ===== */
.ce-body {
  flex: 1;
  display: grid;
  grid-template-columns: 280px 1fr 320px;
  overflow: hidden;
}
.ce-left, .ce-right {
  background: #FFFFFF;
  border-right: 1px solid #E5E7EB;
  overflow-y: auto;
  padding: 16px;
}
.ce-right {
  border-right: none;
  border-left: 1px solid #E5E7EB;
}
.ce-center {
  overflow-y: auto;
  padding: 32px;
  display: flex;
  align-items: flex-start;
  justify-content: center;
}

/* ===== 面板通用 ===== */
.ce-panel {
  margin-bottom: 24px;
}
.ce-panel-title {
  font-size: 14px;
  font-weight: 600;
  color: #1A1A1A;
  margin: 0 0 12px 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

/* ===== 模板选择 ===== */
.ce-template-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.ce-template-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px;
  background: transparent;
  border: 1px solid #E5E7EB;
  border-radius: 12px;
  cursor: pointer;
  text-align: left;
  transition: all 0.2s;
}
.ce-template-item:hover {
  border-color: #065F46;
}
.ce-template-item.active {
  border-color: #065F46;
  background: #F0FDF4;
}
.ce-template-preview {
  width: 48px;
  height: 64px;
  border-radius: 4px;
  border: 2px solid transparent;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.ce-template-preview-text {
  font-size: 18px;
  font-weight: 700;
}
.ce-template-info {
  flex: 1;
  min-width: 0;
}
.ce-template-name {
  font-size: 14px;
  font-weight: 600;
  color: #1A1A1A;
  margin-bottom: 2px;
}
.ce-template-desc {
  font-size: 12px;
  color: #6B7280;
  line-height: 1.4;
}

/* ===== 页面列表 ===== */
.ce-page-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.ce-page-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border: 1px solid transparent;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s;
}
.ce-page-item:hover {
  background: #EEF0F4;
}
.ce-page-item.active {
  background: #F0FDF4;
  border-color: #065F46;
}
.ce-page-num {
  font-size: 12px;
  font-weight: 600;
  color: #6B7280;
  min-width: 16px;
}
.ce-page-type {
  font-size: 12px;
  padding: 2px 6px;
  background: #E5E7EB;
  border-radius: 3px;
  color: #6B7280;
  flex-shrink: 0;
}
.ce-page-item.active .ce-page-type {
  background: #065F46;
  color: #FFFFFF;
}
.ce-page-title {
  flex: 1;
  font-size: 13px;
  color: #1A1A1A;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}
.ce-page-actions {
  display: flex;
  gap: 2px;
  opacity: 0;
  transition: opacity 0.15s;
}
.ce-page-item:hover .ce-page-actions,
.ce-page-item.active .ce-page-actions {
  opacity: 1;
}
.ce-icon-btn {
  width: 22px;
  height: 22px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: none;
  border-radius: 3px;
  color: #6B7280;
  cursor: pointer;
  font-size: 14px;
  transition: all 0.15s;
}
.ce-icon-btn:hover:not(:disabled) {
  background: #E5E7EB;
  color: #1A1A1A;
}
.ce-icon-btn:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}
.ce-icon-btn-danger:hover {
  background: #FEE2E2;
  color: #DC2626;
}
.ce-add-page {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 6px;
  margin-top: 12px;
}
.ce-add-btn {
  padding: 6px;
  background: transparent;
  border: 1px dashed #E5E7EB;
  border-radius: 6px;
  color: #6B7280;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s;
}
.ce-add-btn:hover {
  border-color: #065F46;
  color: #065F46;
}

/* ===== 预览区 ===== */
.ce-preview-grid {
  display: grid;
  grid-template-columns: repeat(2, 300px);
  gap: 24px;
}
.ce-preview-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 10px;
  border: 2px solid transparent;
  border-radius: 12px;
  cursor: pointer;
  transition: border-color 0.15s;
}
.ce-preview-card:hover {
  border-color: #E5E7EB;
}
.ce-preview-card.active {
  border-color: #065F46;
}
.ce-preview-wrapper {
  width: 1080px;
  height: 1440px;
  transform-origin: top left;
  pointer-events: none;
}
.ce-preview-wrapper > :deep(.card-canvas) {
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}
.ce-preview-label {
  font-size: 13px;
  color: #6B7280;
}

/* ===== 表单 ===== */
.ce-form {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.ce-form-row {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.ce-label {
  font-size: 12px;
  font-weight: 500;
  color: #6B7280;
}
.ce-input, .ce-select, .ce-textarea {
  padding: 8px 10px;
  border: 1px solid #E5E7EB;
  border-radius: 6px;
  font-size: 14px;
  color: #1A1A1A;
  background: #FFFFFF;
  font-family: inherit;
  transition: border-color 0.15s;
}
.ce-input:focus, .ce-select:focus, .ce-textarea:focus {
  outline: none;
  border-color: #065F46;
}
.ce-textarea {
  resize: vertical;
  line-height: 1.5;
}
.ce-color-row {
  display: flex;
  gap: 8px;
  align-items: center;
}
.ce-color {
  width: 40px;
  height: 36px;
  padding: 2px;
  border: 1px solid #E5E7EB;
  border-radius: 6px;
  cursor: pointer;
  background: #FFFFFF;
}
.ce-color-text {
  flex: 1;
}
.ce-range {
  width: 100%;
  accent-color: #065F46;
}
.ce-reset-btn {
  font-size: 11px;
  font-weight: 400;
  padding: 2px 8px;
  background: transparent;
  border: 1px solid #E5E7EB;
  border-radius: 4px;
  color: #6B7280;
  cursor: pointer;
}
.ce-reset-btn:hover {
  border-color: #065F46;
  color: #065F46;
}

/* ===== 列表项编辑 ===== */
.ce-list-editor {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.ce-list-edit-item {
  display: flex;
  align-items: center;
  gap: 6px;
}
.ce-list-edit-num {
  font-size: 12px;
  font-weight: 600;
  color: #6B7280;
  min-width: 20px;
}
.ce-list-edit-input {
  flex: 1;
}
.ce-add-list-btn {
  padding: 6px;
  background: transparent;
  border: 1px dashed #E5E7EB;
  border-radius: 6px;
  color: #6B7280;
  font-size: 13px;
  cursor: pointer;
}
.ce-add-list-btn:hover {
  border-color: #065F46;
  color: #065F46;
}

/* ===== 隐藏导出容器 ===== */
.ce-export-container {
  position: fixed;
  left: -99999px;
  top: 0;
  pointer-events: none;
}

/* ===== 导出弹窗 ===== */
.ce-export-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
}
.ce-export-modal {
  background: #FFFFFF;
  border-radius: 12px;
  width: 90vw;
  max-width: 960px;
  max-height: 85vh;
  display: flex;
  flex-direction: column;
}
.ce-export-modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid #E5E7EB;
}
.ce-export-modal-header h3 {
  font-size: 16px;
  font-weight: 600;
  color: #1A1A1A;
  margin: 0;
}
.ce-export-close {
  width: 28px;
  height: 28px;
  background: transparent;
  border: none;
  font-size: 20px;
  color: #6B7280;
  cursor: pointer;
  border-radius: 4px;
}
.ce-export-close:hover {
  background: #EEF0F4;
}
.ce-export-modal-body {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
}
.ce-export-progress {
  font-size: 14px;
  color: #065F46;
  margin-bottom: 12px;
}
.ce-export-error {
  font-size: 14px;
  color: #DC2626;
  margin-bottom: 12px;
}
.ce-export-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 16px;
}
.ce-export-thumb {
  display: flex;
  flex-direction: column;
  gap: 8px;
  align-items: center;
}
.ce-export-thumb img {
  width: 100%;
  border: 1px solid #E5E7EB;
  border-radius: 6px;
}
.ce-download-btn {
  padding: 6px 12px;
  background: transparent;
  border: 1px solid #065F46;
  border-radius: 6px;
  color: #065F46;
  font-size: 13px;
  cursor: pointer;
}
.ce-download-btn:hover {
  background: #F0FDF4;
}
.ce-export-modal-footer {
  display: flex;
  gap: 12px;
  justify-content: flex-end;
  padding: 16px 20px;
  border-top: 1px solid #E5E7EB;
}
.ce-action-btn {
  padding: 8px 20px;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  border: none;
}
.ce-action-btn-secondary {
  background: #EEF0F4;
  color: #1A1A1A;
}
.ce-action-btn-secondary:hover {
  background: #E5E7EB;
}
.ce-action-btn-primary {
  background: #065F46;
  color: #FFFFFF;
}
.ce-action-btn-primary:hover {
  background: #047857;
}
</style>