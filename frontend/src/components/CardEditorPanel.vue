/**
 * 卡片编辑器面板（可复用组件）
 *
 * 与独立页面 CardEditorView 不同，本组件：
 * - 接收 cardDraft prop（image_plan 生成的文案初稿）
 * - 暴露 generate 事件（html2canvas 出图后，把 base64 列表传给父组件）
 * - 去掉路由导航、下载按钮，聚焦"编辑→生成图片→注入工作流"
 */
<script setup lang="ts">
import { ref, computed, nextTick, watch, onMounted, onBeforeUnmount } from 'vue'
import html2canvas from 'html2canvas'
import CardRenderer from '@/components/CardRenderer.vue'
import {
  TEMPLATES,
  PAGE_TYPE_LABELS,
  DECORATION_PRESETS,
  DECORATION_TYPE_LABELS,
  createDefaultPage,
  createDefaultPages,
  createDefaultDecoration,
  type CardPage,
  type PageType,
  type TemplateTheme,
  type DecorationConfig,
  type DecorationType,
} from '@/card-editor/templates'

const props = defineProps<{
  /** image_plan 生成的文案初稿 */
  cardDraft?: {
    pages?: Array<{
      type: string
      title?: string
      subtitle?: string
      content?: string
      footer?: string
      listItems?: string[]
    }>
    suggested_template?: string
    /** LLM 推荐的强调色（十六进制），覆盖模板默认 accent */
    custom_accent?: string
    /** LLM 推荐的装饰配置 */
    suggested_decoration?: DecorationConfig
  }
  /** 父组件正在将图片注入工作流 */
  injecting?: boolean
}>()

const emit = defineEmits<{
  /** html2canvas 出图完成，把 base64 列表 + plan_context 传给父组件 */
  generate: [images: string[], planContext: {
    template: string
    accent: string
    page_count: number
    page_types: string[]
    decoration: DecorationConfig
  }]
}>()

// ===== 状态 =====
const currentTemplateId = ref<string>('minimal_white')
const currentDecoration = ref<DecorationConfig>(createDefaultDecoration())
const pages = ref<CardPage[]>(createDefaultPages())
const selectedPageId = ref<string>(pages.value[0].id)
const customFontSize = ref<number | null>(null)
const customBg = ref<string>('')
const customAccent = ref<string>('')
const exporting = ref(false)
const exportProgress = ref('')

// ===== 加载 cardDraft =====
// 用签名判断 draft 是否真正变化，避免父组件 computed 引用变化时覆盖用户手动选择
const lastDraftSignature = ref<string>('')

watch(() => props.cardDraft, (draft) => {
  if (!draft || !draft.pages || draft.pages.length === 0) return

  // 计算签名：pages 数量 + 首页标题 + 建议模板 + 强调色
  // 同一个 draft 仅引用变化时（SSE 推送导致），签名相同，跳过覆盖
  const signature = `${draft.pages.length}|${draft.pages[0]?.title || ''}|${draft.suggested_template || ''}|${draft.custom_accent || ''}`
  if (signature === lastDraftSignature.value) return
  lastDraftSignature.value = signature

  // 用 image_plan 生成的文案初稿替换默认页面
  pages.value = draft.pages.map((p, i) => ({
    id: `page_draft_${i}`,
    type: (p.type as PageType) || 'content',
    title: p.title || '',
    subtitle: p.subtitle,
    content: p.content || '',
    footer: p.footer,
    listItems: p.listItems,
  }))
  selectedPageId.value = pages.value[0].id
  // 应用建议的模板
  if (draft.suggested_template && TEMPLATES.find(t => t.id === draft.suggested_template)) {
    currentTemplateId.value = draft.suggested_template
  }
  // 应用 LLM 推荐的强调色（覆盖模板默认 accent）
  if (draft.custom_accent) {
    customAccent.value = draft.custom_accent
  }
  // 应用 LLM 推荐的装饰配置
  if (draft.suggested_decoration) {
    currentDecoration.value = draft.suggested_decoration
  }
}, { immediate: true })

// ===== 计算属性 =====
const currentTemplate = computed<TemplateTheme>(() => {
  return TEMPLATES.find(t => t.id === currentTemplateId.value) || TEMPLATES[0]
})

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

const filteredDecoPresets = computed(() => {
  if (currentDecoration.value.type === 'none') return []
  return DECORATION_PRESETS.filter(p => p.type === currentDecoration.value.type)
})

// ===== 页面操作 =====
function selectPage(id: string) { selectedPageId.value = id }

function addPage(type: PageType) {
  const newPage = createDefaultPage(type, pages.value.length)
  pages.value.push(newPage)
  selectedPageId.value = newPage.id
}

function deletePage(id: string) {
  if (pages.value.length <= 1) return
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
  page.type = newType
  if (newType === 'list' && !page.listItems) {
    page.listItems = ['第一项', '第二项', '第三项']
  }
  if (newType !== 'list') delete page.listItems
  if (newType === 'cover' && !page.subtitle) page.subtitle = '副标题'
}

function addListItem() {
  if (!selectedPage.value.listItems) selectedPage.value.listItems = []
  selectedPage.value.listItems.push('新要点')
}

function deleteListItem(index: number) {
  selectedPage.value.listItems?.splice(index, 1)
}

function selectTemplate(id: string) {
  currentTemplateId.value = id
  customFontSize.value = null
  customBg.value = ''
  customAccent.value = ''
  currentDecoration.value = createDefaultDecoration()
}

function resetCustomStyle() {
  customFontSize.value = null
  customBg.value = ''
  customAccent.value = ''
  currentDecoration.value = createDefaultDecoration()
}

function selectDecoration(preset: DecorationConfig & { name?: string; description?: string }) {
  currentDecoration.value = {
    type: preset.type,
    color1: preset.color1,
    color2: preset.color2,
    opacity: preset.opacity,
    param1: preset.param1,
    param2: preset.param2,
  }
}

function setDecorationNone() {
  currentDecoration.value = createDefaultDecoration()
}

// ===== 导出 PNG =====
const exportContainer = ref<HTMLElement | null>(null)

async function generateImages() {
  if (exporting.value) return
  exporting.value = true
  exportProgress.value = '准备渲染...'
  console.log('[CardEditorPanel] generateImages called')

  try {
    await nextTick()
    if (!exportContainer.value) throw new Error('渲染容器未就绪')

    const cardEls = exportContainer.value.querySelectorAll('.card-canvas')
    if (cardEls.length === 0) throw new Error('没有可导出的卡片')
    console.log('[CardEditorPanel] found', cardEls.length, 'cards to export')

    const images: string[] = []
    for (let i = 0; i < cardEls.length; i++) {
      exportProgress.value = `正在生成第 ${i + 1}/${cardEls.length} 张...`
      await nextTick()

      const canvas = await html2canvas(cardEls[i] as HTMLElement, {
        scale: 2,
        useCORS: true,
        backgroundColor: effectiveTheme.value.bg,
        logging: false,
        width: 1080,
        height: 1440,
        windowWidth: 1080,
        windowHeight: 1440,
      })
      images.push(canvas.toDataURL('image/png'))
    }

    exportProgress.value = ''
    const pureBase64 = images.map(d => d.replace(/^data:image\/png;base64,/, ''))
    const planContext = {
      template: currentTemplateId.value,
      accent: customAccent.value || currentTemplate.value.accent,
      page_count: pages.value.length,
      page_types: pages.value.map(p => p.type),
      decoration: currentDecoration.value,
    }
    emit('generate', pureBase64, planContext)
    console.log('[CardEditorPanel] emitted generate, images:', pureBase64.length, 'planContext:', planContext)
  } catch (e) {
    exportProgress.value = ''
    console.error('generateImages failed:', e)
    alert(`生成图片失败：${e instanceof Error ? e.message : String(e)}`)
  } finally {
    exporting.value = false
  }
}

defineExpose({
  generateImages,
  currentTemplateId,
  customAccent,
  pages,
  currentDecoration,
})

// ===== 卡片预览尺寸：根据容器宽度自动缩放 =====
const previewScale = ref(0.22)
const boxWidth = ref(240)
const boxHeight = ref(320)
const previewGrid = ref<HTMLElement | null>(null)

function recalcPreviewSize() {
  const grid = previewGrid.value
  if (!grid) return
  const containerWidth = grid.clientWidth
  if (containerWidth <= 0) return
  const count = pages.value.length || 1
  const gap = 12
  const available = containerWidth - gap * (count - 1)
  const maxBoxW = Math.floor(available / count)
  const clampedW = Math.max(100, Math.min(360, maxBoxW))
  boxWidth.value = clampedW
  boxHeight.value = Math.floor(clampedW * 1440 / 1080)
  previewScale.value = clampedW / 1080
}

let resizeObserver: ResizeObserver | null = null

onMounted(() => {
  const init = () => {
    if (previewGrid.value && previewGrid.value.clientWidth > 0) {
      resizeObserver = new ResizeObserver(() => recalcPreviewSize())
      resizeObserver.observe(previewGrid.value)
      recalcPreviewSize()
    } else {
      setTimeout(init, 100)
    }
  }
  nextTick(init)
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
})

watch(() => pages.value.length, () => nextTick(recalcPreviewSize))

// ===== 模板候选条带：顶部横向展示所有模板封面，点击切换，零渲染成本（DOM scale）=====
const tplThumbWidth = 48                                              // 缩略图宽 px
const tplThumbScale = tplThumbWidth / 1080                            // ≈ 0.044
const tplThumbHeight = Math.floor(tplThumbWidth * 1440 / 1080)        // 64px
</script>

<template>
  <div class="cep">
    <!-- 工具栏 -->
    <div class="cep-toolbar">
      <div class="cep-toolbar-left">
        <label class="cep-toolbar-label">模板：</label>
        <select class="cep-select" v-model="currentTemplateId" @change="selectTemplate(($event.target as HTMLSelectElement).value)">
          <option v-for="tpl in TEMPLATES" :key="tpl.id" :value="tpl.id">{{ tpl.name }}</option>
        </select>
      </div>
    </div>

    <div class="cep-body">
      <!-- 左侧：页面列表 -->
      <aside class="cep-left">
        <div class="cep-left-content">
          <div class="cep-page-list">
            <div
              v-for="(page, i) in pages"
              :key="page.id"
              class="cep-page-item"
              :class="{ active: page.id === selectedPageId }"
              @click="selectPage(page.id)"
            >
              <span class="cep-page-num">{{ i + 1 }}</span>
              <span class="cep-page-type">{{ PAGE_TYPE_LABELS[page.type] }}</span>
              <span class="cep-page-title">{{ page.title || page.content.slice(0, 10) }}</span>
              <div class="cep-page-actions">
                <button class="cep-icon-btn" :disabled="i === 0" @click.stop="movePage(page.id, 'up')">↑</button>
                <button class="cep-icon-btn" :disabled="i === pages.length - 1" @click.stop="movePage(page.id, 'down')">↓</button>
                <button class="cep-icon-btn cep-icon-btn-danger" @click.stop="deletePage(page.id)">×</button>
              </div>
            </div>
          </div>
          <div class="cep-add-page">
            <button v-for="type in (['cover','content','quote','list'] as PageType[])" :key="type" class="cep-add-btn" @click="addPage(type)">
              + {{ PAGE_TYPE_LABELS[type] }}
            </button>
          </div>
        </div>
      </aside>

      <!-- 中间：预览区 -->
      <main class="cep-center">
        <!-- 模板候选条带：横向展示所有模板封面，点击切换，当前选中高亮 -->
        <div class="cep-template-strip">
          <div
            v-for="tpl in TEMPLATES"
            :key="tpl.id"
            class="cep-tpl-thumb"
            :class="{ active: tpl.id === currentTemplateId }"
            :title="tpl.description"
            @click="selectTemplate(tpl.id)"
          >
            <div class="cep-tpl-thumb-box" :style="{ width: tplThumbWidth + 'px', height: tplThumbHeight + 'px' }">
              <div class="cep-tpl-thumb-inner" :style="{ transform: `scale(${tplThumbScale})` }">
                <CardRenderer v-if="pages[0]" :page="pages[0]" :theme="tpl" :decoration="currentDecoration" />
              </div>
            </div>
            <div class="cep-tpl-thumb-name">{{ tpl.name }}</div>
          </div>
        </div>

        <div class="cep-preview-grid" ref="previewGrid">
          <div
            v-for="(page, i) in pages"
            :key="page.id"
            class="cep-preview-card"
            :class="{ active: page.id === selectedPageId }"
            @click="selectPage(page.id)"
          >
            <!-- 固定宽高容器：JS 算出精确像素值内联，确保布局正确 -->
            <div
              class="cep-preview-box"
              :style="{ width: boxWidth + 'px', height: boxHeight + 'px' }"
            >
              <!-- 内层：原尺寸 1080x1440，absolute 定位 + transform scale 缩放到容器大小 -->
              <div class="cep-preview-inner" :style="{ transform: `scale(${previewScale})` }">
                <CardRenderer :page="page" :theme="effectiveTheme" :decoration="currentDecoration" />
              </div>
            </div>
            <div class="cep-preview-label">{{ i + 1 }} · {{ PAGE_TYPE_LABELS[page.type] }}</div>
          </div>
        </div>
      </main>

      <!-- 右侧：属性编辑 -->
      <aside class="cep-right">
        <div class="cep-right-content">
        <section class="cep-panel">
          <h4 class="cep-panel-title">当前页面</h4>
          <div class="cep-form">
            <div class="cep-form-row">
              <label class="cep-label">类型</label>
              <select class="cep-select" :value="selectedPage.type" @change="changePageType(selectedPage.id, ($event.target as HTMLSelectElement).value as PageType)">
                <option v-for="(label, key) in PAGE_TYPE_LABELS" :key="key" :value="key">{{ label }}</option>
              </select>
            </div>
            <div v-if="selectedPage.type !== 'quote'" class="cep-form-row">
              <label class="cep-label">标题</label>
              <input class="cep-input" v-model="selectedPage.title" />
            </div>
            <div v-if="selectedPage.type === 'cover'" class="cep-form-row">
              <label class="cep-label">副标题</label>
              <input class="cep-input" v-model="selectedPage.subtitle" />
            </div>
            <div v-if="selectedPage.type === 'content' || selectedPage.type === 'quote'" class="cep-form-row">
              <label class="cep-label">{{ selectedPage.type === 'quote' ? '金句' : '正文' }}</label>
              <textarea class="cep-textarea" v-model="selectedPage.content" :rows="selectedPage.type === 'quote' ? 3 : 5"></textarea>
            </div>
            <div v-if="selectedPage.type === 'list'" class="cep-form-row">
              <label class="cep-label">清单项</label>
              <div class="cep-list-editor">
                <div v-for="(item, i) in selectedPage.listItems" :key="i" class="cep-list-edit-item">
                  <span class="cep-list-edit-num">{{ i + 1 }}</span>
                  <input class="cep-input cep-list-edit-input" v-model="selectedPage.listItems![i]" />
                  <button class="cep-icon-btn cep-icon-btn-danger" @click="deleteListItem(i)">×</button>
                </div>
                <button class="cep-add-list-btn" @click="addListItem">+ 添加</button>
              </div>
            </div>
            <div class="cep-form-row">
              <label class="cep-label">页脚</label>
              <input class="cep-input" v-model="selectedPage.footer" />
            </div>
          </div>
        </section>

        <section class="cep-panel">
          <h4 class="cep-panel-title">
            样式
            <button class="cep-reset-btn" @click="resetCustomStyle">重置</button>
          </h4>
          <div class="cep-form">
            <div class="cep-form-row">
              <label class="cep-label">字号（{{ effectiveTheme.fontSize }}px）</label>
              <input type="range" class="cep-range" min="32" max="72" step="2" v-model.number="customFontSize" />
            </div>
            <div class="cep-form-row">
              <label class="cep-label">背景色</label>
              <div class="cep-color-row">
                <input type="color" class="cep-color" v-model="customBg" />
                <input class="cep-input" v-model="customBg" :placeholder="currentTemplate.bg" />
              </div>
            </div>
            <div class="cep-form-row">
              <label class="cep-label">强调色</label>
              <div class="cep-color-row">
                <input type="color" class="cep-color" v-model="customAccent" />
                <input class="cep-input" v-model="customAccent" :placeholder="currentTemplate.accent" />
              </div>
            </div>
          </div>
        </section>

        <section class="cep-panel">
          <h4 class="cep-panel-title">
            装饰
            <button class="cep-reset-btn" @click="setDecorationNone">清除</button>
          </h4>
          <div class="cep-form">
            <div class="cep-form-row">
              <label class="cep-label">类型</label>
              <select class="cep-select" :value="currentDecoration.type" @change="currentDecoration.type = ($event.target as HTMLSelectElement).value as DecorationType; if (currentDecoration.type === 'none') setDecorationNone()">
                <option v-for="(label, key) in DECORATION_TYPE_LABELS" :key="key" :value="key">{{ label }}</option>
              </select>
            </div>
            <div v-if="currentDecoration.type !== 'none'" class="cep-form-row">
              <label class="cep-label">预设方案</label>
              <div class="cep-deco-presets">
                <button
                  v-for="preset in filteredDecoPresets"
                  :key="preset.name"
                  class="cep-deco-preset-btn"
                  :class="{ active: preset.type === currentDecoration.type && preset.color1 === currentDecoration.color1 && preset.color2 === currentDecoration.color2 }"
                  @click="selectDecoration(preset)"
                  :title="preset.description"
                >
                  <span class="cep-deco-swatch" :style="{ background: `linear-gradient(135deg, ${preset.color1}, ${preset.color2})` }"></span>
                  <span class="cep-deco-preset-name">{{ preset.name }}</span>
                </button>
              </div>
            </div>
            <div v-if="currentDecoration.type !== 'none'" class="cep-form-row">
              <label class="cep-label">强度（{{ Math.round(currentDecoration.opacity * 100) }}%）</label>
              <input type="range" class="cep-range" min="0.05" max="0.8" step="0.05" v-model.number="currentDecoration.opacity" />
            </div>
            <div v-if="currentDecoration.type !== 'none'" class="cep-form-row">
              <label class="cep-label">颜色 1</label>
              <div class="cep-color-row">
                <input type="color" class="cep-color" v-model="currentDecoration.color1" />
                <input class="cep-input" v-model="currentDecoration.color1" />
              </div>
            </div>
            <div v-if="currentDecoration.type !== 'none'" class="cep-form-row">
              <label class="cep-label">颜色 2</label>
              <div class="cep-color-row">
                <input type="color" class="cep-color" v-model="currentDecoration.color2" />
                <input class="cep-input" v-model="currentDecoration.color2" />
              </div>
            </div>
          </div>
        </section>
        </div>
      </aside>
    </div>

    <!-- 底部生成按钮 -->
    <div class="cep-footer">
      <button class="cep-gen-btn" :disabled="exporting || props.injecting" @click="generateImages">
        {{ props.injecting ? '注入中...' : exporting ? (exportProgress || '生成中...') : '生成图片并注入工作流' }}
      </button>
    </div>

    <!-- 隐藏的导出容器 -->
    <div ref="exportContainer" class="cep-export-container" aria-hidden="true">
      <CardRenderer v-for="page in pages" :key="page.id" :page="page" :theme="effectiveTheme" :decoration="currentDecoration" />
    </div>
  </div>
</template>

<style scoped>
.cep {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #FFFFFF;
  border: none;
  border-radius: 0;
  overflow: hidden;
}

/* 工具栏 */
.cep-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 16px;
  background: #FFFFFF;
  border-bottom: none;
  flex-shrink: 0;
}
.cep-toolbar-left {
  display: flex;
  align-items: center;
  gap: 8px;
}
.cep-toolbar-label {
  font-size: 16px;
  color: #9CA3AF;
  font-weight: 700;
}

/* 底部生成按钮 */
.cep-footer {
  display: flex;
  justify-content: center;
  align-items: center;
  padding: 12px 16px;
  background: #FFFFFF;
  flex-shrink: 0;
}
.cep-gen-btn {
  padding: 7px 18px;
  background: #FF2442;
  color: #FFFFFF;
  border: none;
  border-radius: 20px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  white-space: nowrap;
}
.cep-gen-btn:hover:not(:disabled) { background: #E01F3B; }
.cep-gen-btn:disabled { opacity: 0.6; cursor: not-allowed; }

/* 三栏：左右固定宽度 + 中间预览区填满 */
.cep-body {
  flex: 1;
  display: grid;
  grid-template-columns: 140px minmax(0, 1fr) 180px;
  overflow: hidden;
  min-height: 0;
}
.cep-left, .cep-right {
  background: #FFFFFF;
  overflow-x: hidden;
  overflow-y: auto;
  padding: 10px;
}
.cep-left { border-right: none; }
.cep-right { border-left: none; }
.cep-left-content, .cep-right-content {
  padding-top: 4px;
}
.cep-center {
  overflow-y: auto;
  padding: 16px;
  display: block;
  width: 100%;
  min-width: 0;
  background: #F3F4F6;
  border-radius: 12px;
}

/* 模板候选条带：横向排列所有模板封面缩略图 */
.cep-template-strip {
  display: flex;
  gap: 10px;
  padding: 12px;
  border-bottom: none;
  margin-bottom: 14px;
  background: #F3F4F6;
  border-radius: 8px;
}
.cep-tpl-thumb {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 5px;
  cursor: pointer;
  padding: 5px;
  border: none;
  border-radius: 6px;
  flex-shrink: 0;
  transition: background 0.15s;
}
.cep-tpl-thumb:hover { background: #F3F4F6; }
.cep-tpl-thumb.active { background: #F0FDF4; }
.cep-tpl-thumb-box {
  position: relative;
  overflow: hidden;
  border-radius: 4px;
  background: #FFFFFF;
}
.cep-tpl-thumb-inner {
  position: absolute;
  top: 0;
  left: 0;
  width: 1080px;
  height: 1440px;
  transform-origin: top left;
  pointer-events: none;
}
.cep-tpl-thumb-name {
  font-size: 11px;
  color: #4B5563;
  white-space: nowrap;
}
.cep-tpl-thumb.active .cep-tpl-thumb-name { color: #065F46; font-weight: 600; }

/* 页面列表 */
.cep-page-list { display: flex; flex-direction: column; gap: 3px; }
.cep-page-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 8px;
  border: none;
  border-radius: 5px;
  cursor: pointer;
  transition: all 0.15s;
}
.cep-page-item:hover { background: #F3F4F6; }
.cep-page-item.active { background: #F3F4F6; }
.cep-page-num { font-size: 11px; font-weight: 600; color: #6B7280; min-width: 14px; }
.cep-page-type {
  font-size: 11px;
  padding: 1px 5px;
  background: #E5E7EB;
  border-radius: 3px;
  color: #4B5563;
  flex-shrink: 0;
}
.cep-page-item.active .cep-page-type { background: #065F46; color: #FFFFFF; }
.cep-page-title {
  flex: 1;
  font-size: 12px;
  color: #1A1A1A;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}
.cep-page-actions { display: flex; gap: 1px; opacity: 0; transition: opacity 0.15s; }
.cep-page-item:hover .cep-page-actions,
.cep-page-item.active .cep-page-actions { opacity: 1; }
.cep-icon-btn {
  width: 20px; height: 20px;
  display: flex; align-items: center; justify-content: center;
  background: transparent; border: none; border-radius: 3px;
  color: #6B7280; cursor: pointer; font-size: 13px;
}
.cep-icon-btn:hover:not(:disabled) { background: #E5E7EB; color: #1A1A1A; }
.cep-icon-btn:disabled { opacity: 0.3; cursor: not-allowed; }
.cep-icon-btn-danger:hover { background: #FEE2E2; color: #DC2626; }
.cep-add-page { display: grid; grid-template-columns: 1fr 1fr; gap: 4px; margin-top: 8px; }
.cep-add-btn {
  padding: 4px;
  background: #F3F4F6;
  border: none;
  border-radius: 5px;
  color: #6B7280;
  font-size: 11px;
  cursor: pointer;
}
.cep-add-btn:hover { color: #065F46; }

/* 预览：横向 flex，卡片自动缩放，放不下时滚动 */
.cep-preview-grid {
  display: flex;
  gap: 12px;
  overflow-x: auto;
  overflow-y: hidden;
  padding: 4px 2px 12px 2px;
  width: 100%;
  scroll-behavior: smooth;
  -webkit-overflow-scrolling: touch;
  justify-content: safe center;
}
.cep-preview-grid::-webkit-scrollbar { height: 6px; }
.cep-preview-grid::-webkit-scrollbar-track { background: #F3F4F6; border-radius: 3px; }
.cep-preview-grid::-webkit-scrollbar-thumb { background: #CBD5E1; border-radius: 3px; }
.cep-preview-grid::-webkit-scrollbar-thumb:hover { background: #94A3B8; }
.cep-preview-card {
  display: flex; flex-direction: column; align-items: center; gap: 4px;
  padding: 6px; border: 2px solid transparent; border-radius: 6px; cursor: pointer;
  flex-shrink: 0;
}
.cep-preview-card:hover { border-color: #D1D5DB; }
.cep-preview-card.active { border-color: #065F46; }
/* 卡片容器：固定像素尺寸，不依赖容器宽度 */
.cep-preview-box {
  position: relative;
  overflow: hidden;
  border-radius: 4px;
  background: #FFFFFF;
}
/* 内层：原尺寸 1080x1440，absolute + transform scale 缩放到容器大小 */
.cep-preview-inner {
  position: absolute;
  top: 0;
  left: 0;
  width: 1080px;
  height: 1440px;
  transform-origin: top left;
  pointer-events: none;
}
.cep-preview-inner :deep(.card-canvas) { box-shadow: 0 2px 8px rgba(0,0,0,0.1); }
.cep-preview-label { font-size: 12px; color: #6B7280; white-space: nowrap; }

/* 表单 */
.cep-panel { margin-bottom: 16px; }
.cep-panel-title {
  font-size: 13px; font-weight: 600; color: #1A1A1A; margin: 0 0 10px 0;
  display: flex; align-items: center; justify-content: space-between;
}
.cep-form { display: flex; flex-direction: column; gap: 10px; }
.cep-form-row { display: flex; flex-direction: column; gap: 4px; }
.cep-label { font-size: 11px; font-weight: 500; color: #4B5563; }
.cep-input, .cep-select, .cep-textarea {
  padding: 6px 8px; border: none; border-radius: 5px;
  font-size: 13px; color: #1A1A1A; background: #F3F4F6; font-family: inherit;
}
.cep-input:focus, .cep-select:focus, .cep-textarea:focus { outline: none; background: #F3F4F6; }
.cep-textarea { resize: vertical; line-height: 1.5; }
.cep-color-row { display: flex; gap: 6px; align-items: center; }
.cep-color { width: 32px; height: 30px; padding: 2px; border: none; border-radius: 5px; cursor: pointer; background: #F3F4F6; }
.cep-range { width: 100%; accent-color: #065F46; }
.cep-reset-btn {
  font-size: 11px; padding: 2px 6px; background: #F3F4F6;
  border: none; border-radius: 4px; color: #6B7280; cursor: pointer;
}
.cep-reset-btn:hover { color: #065F46; }

/* 列表编辑 */
.cep-list-editor { display: flex; flex-direction: column; gap: 4px; }
.cep-list-edit-item { display: flex; align-items: center; gap: 4px; }
.cep-list-edit-num { font-size: 11px; font-weight: 600; color: #6B7280; min-width: 16px; }
.cep-list-edit-input { flex: 1; }
.cep-add-list-btn {
  padding: 4px; background: #F3F4F6; border: none;
  border-radius: 5px; color: #6B7280; font-size: 12px; cursor: pointer;
}
.cep-add-list-btn:hover { color: #065F46; }

/* 隐藏导出容器：用 absolute + clip 保证 html2canvas 能正确渲染（fixed + left:-99999px 会导致空白） */
.cep-export-container { position: absolute; clip: rect(0, 0, 0, 0); width: 1080px; pointer-events: none; }

/* 装饰预设选择 */
.cep-deco-presets {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.cep-deco-preset-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 3px 6px;
  border: none;
  border-radius: 5px;
  background: #F3F4F6;
  cursor: pointer;
  font-size: 11px;
  color: #4B5563;
  transition: all 0.15s;
}
.cep-deco-preset-btn:hover { color: #065F46; }
.cep-deco-preset-btn.active { background: #F3F4F6; color: #065F46; font-weight: 600; }
.cep-deco-swatch {
  width: 14px;
  height: 14px;
  border-radius: 3px;
  flex-shrink: 0;
}
.cep-deco-preset-name {
  white-space: nowrap;
}
</style>