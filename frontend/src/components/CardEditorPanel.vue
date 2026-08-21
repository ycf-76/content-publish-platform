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
import EstherCardRenderer from '@/components/EstherCardRenderer.vue'
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
import {
  ESTHER_TEMPLATES,
  ESTHER_PAGE_TYPE_LABELS,
  ESTHER_DECORATION_PRESETS,
  FULL_PAGE_TYPE_LABELS,
  createEstherDefaultPage,
  createEstherDefaultPages,
  isEstherTemplate,
  isEstherPageType,
  type EstherCardPage,
  type EstherPageType,
  type FullPageType,
} from '@/card-editor/esther-templates'

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
      highlight?: string
      tag?: string
      emoji?: string
      decoNumber?: string
      ctaText?: string
      compareLeftTitle?: string
      compareRightTitle?: string
      compareLeftItems?: string[]
      compareRightItems?: string[]
      iconTextPairs?: Array<{ icon: string; text: string }>
      steps?: Array<{ title: string; desc: string }>
      codeContent?: string
      codeLang?: string
      numberedItems?: Array<{ title: string; desc: string }>
      newspaperCols?: Array<{ headline: string; body: string }>
      masthead?: string
    }>
    suggested_template?: string
    /** LLM 推荐的强调色（十六进制），覆盖模板默认 accent */
    custom_accent?: string
    /** LLM 推荐的装饰配置 */
    suggested_decoration?: DecorationConfig
    /** copywrite 原文上下文（后端 _ensure_copywrite_in_draft 注入） */
    copywrite_context?: {
      title: string
      content: string
      tags: string[]
    }
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

// ===== 合并模板列表（原有3套 + esther3套 = 6套） =====
const ALL_TEMPLATES = [...TEMPLATES, ...ESTHER_TEMPLATES]

// ===== 合并装饰预设 =====
const ALL_DECORATION_PRESETS = [...DECORATION_PRESETS, ...ESTHER_DECORATION_PRESETS]

// ===== 状态 =====
const currentTemplateId = ref<string>('minimal_white')
const currentDecoration = ref<DecorationConfig>(createDefaultDecoration())
const pages = ref<EstherCardPage[]>(createDefaultPages() as EstherCardPage[])
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

  pages.value = draft.pages.map((p, i) => {
    const base: EstherCardPage = {
      id: `page_draft_${i}`,
      type: (p.type as FullPageType) || 'content',
      title: p.title || '',
      subtitle: p.subtitle,
      content: p.content || '',
      footer: p.footer,
      listItems: p.listItems,
    }
    const esther = p as Record<string, unknown>
    if (esther.highlight) base.highlight = esther.highlight as string
    if (esther.tag) base.tag = esther.tag as string
    if (esther.emoji) base.emoji = esther.emoji as string
    if (esther.decoNumber) base.decoNumber = esther.decoNumber as string
    if (esther.ctaText) base.ctaText = esther.ctaText as string
    if (esther.compareLeftTitle) base.compareLeftTitle = esther.compareLeftTitle as string
    if (esther.compareRightTitle) base.compareRightTitle = esther.compareRightTitle as string
    if (esther.compareLeftItems) base.compareLeftItems = esther.compareLeftItems as string[]
    if (esther.compareRightItems) base.compareRightItems = esther.compareRightItems as string[]
    if (esther.iconTextPairs) base.iconTextPairs = esther.iconTextPairs as Array<{ icon: string; text: string }>
    if (esther.steps) base.steps = esther.steps as Array<{ title: string; desc: string }>
    if (esther.codeContent) base.codeContent = esther.codeContent as string
    if (esther.codeLang) base.codeLang = esther.codeLang as string
    if (esther.numberedItems) base.numberedItems = esther.numberedItems as Array<{ title: string; desc: string }>
    if (esther.newspaperCols) base.newspaperCols = esther.newspaperCols as Array<{ headline: string; body: string }>
    if (esther.masthead) base.masthead = esther.masthead as string
    return base
  })
  selectedPageId.value = pages.value[0].id
  // 应用建议的模板
  if (draft.suggested_template && ALL_TEMPLATES.find(t => t.id === draft.suggested_template)) {
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
  return ALL_TEMPLATES.find(t => t.id === currentTemplateId.value) || ALL_TEMPLATES[0]
})

const effectiveTheme = computed<TemplateTheme>(() => {
  return {
    ...currentTemplate.value,
    fontSize: customFontSize.value ?? currentTemplate.value.fontSize,
    bg: customBg.value || currentTemplate.value.bg,
    accent: customAccent.value || currentTemplate.value.accent,
  }
})

const selectedPage = computed<EstherCardPage>(() => {
  return pages.value.find(p => p.id === selectedPageId.value) || pages.value[0]
})

const filteredDecoPresets = computed(() => {
  if (currentDecoration.value.type === 'none') return []
  return ALL_DECORATION_PRESETS.filter(p => p.type === currentDecoration.value.type)
})

/** 判断当前模板是否为 esther 模板 */
const isEsther = computed(() => isEstherTemplate(currentTemplateId.value))

// ===== 页面操作 =====
function selectPage(id: string) { selectedPageId.value = id }

function addPage(type: FullPageType) {
  let newPage: EstherCardPage
  if (isEstherPageType(type)) {
    newPage = createEstherDefaultPage(type, pages.value.length)
  } else {
    newPage = createDefaultPage(type as PageType, pages.value.length) as EstherCardPage
  }
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

/** 计算单页文案字数 */
function pageCharCount(page: any): number {
  const parts = [page.title || '', page.subtitle || '', page.content || '', ...(page.listItems || [])]
  return parts.join('').length
}

/** 重新分配文案：把 copywrite 原文按段落拆分，均匀分配到各内容页 */
function redistributeContent() {
  const ctx = props.cardDraft?.copywrite_context
  if (!ctx || !ctx.content) return

  // 按段落拆分
  let paragraphs = ctx.content.split('\n').filter((p: string) => p.trim())
  if (paragraphs.length <= 1) {
    // 没有换行分段，按句号拆
    const sentences = ctx.content.split(/(?<=[。！？；])/).filter((s: string) => s.trim())
    paragraphs = []
    let chunk: string[] = []
    for (const s of sentences) {
      chunk.push(s)
      if (chunk.length >= 2) {
        paragraphs.push(chunk.join(''))
        chunk = []
      }
    }
    if (chunk.length) paragraphs.push(chunk.join(''))
  }
  if (!paragraphs.length) return

  // 找出可接收正文的页面
  const contentPages = pages.value.filter(p =>
    ['content', 'list', 'dark_panel', 'quote', 'big_quote'].includes(p.type)
  )

  if (contentPages.length === 0) return

  // 均匀分配
  const perPage = Math.max(1, Math.ceil(paragraphs.length / contentPages.length))
  let paraIdx = 0

  for (const page of contentPages) {
    if (paraIdx >= paragraphs.length) {
      // 清空多余页面的内容
      page.content = ''
      page.listItems = []
      continue
    }
    const chunk = paragraphs.slice(paraIdx, paraIdx + perPage)
    paraIdx += perPage

    if (page.type === 'list' || page.type === 'dark_panel') {
      page.listItems = [...chunk]
      page.content = ''
    } else {
      page.content = chunk.join('\n')
      page.listItems = []
    }
  }

  // 如果段落没分完，追加新页面
  while (paraIdx < paragraphs.length) {
    const chunk = paragraphs.slice(paraIdx, paraIdx + perPage)
    paraIdx += perPage
    const newPage = {
      id: `page_${Date.now()}_${pages.value.length}`,
      type: 'content' as FullPageType,
      title: '',
      subtitle: '',
      content: chunk.join('\n'),
      footer: '',
      listItems: [] as string[],
    }
    pages.value.push(newPage)
  }
}

function changePageType(id: string, newType: FullPageType) {
  const page = pages.value.find(p => p.id === id)
  if (!page) return
  page.type = newType
  if (newType === 'list' && !page.listItems) {
    page.listItems = ['第一项', '第二项', '第三项']
  }
  if (newType === 'dark_panel' && !page.listItems) {
    page.listItems = ['第一项关键洞察', '第二项关键洞察', '第三项关键洞察']
    page.emoji = '🚀'
    page.decoNumber = '01'
  }
  if (newType === 'end_page') {
    page.decoNumber = page.decoNumber || '"'
    page.ctaText = page.ctaText || '关注我，获取更多'
  }
  if (newType === 'compare' && !page.compareLeftItems) {
    page.compareLeftTitle = '传统做法'
    page.compareRightTitle = '新方法'
    page.compareLeftItems = ['效率低', '成本高']
    page.compareRightItems = ['效率高', '成本低']
  }
  if (newType === 'icon_text' && !page.iconTextPairs) {
    page.iconTextPairs = [
      { icon: '🎯', text: '第一项能力' },
      { icon: '⚡', text: '第二项能力' },
      { icon: '🔧', text: '第三项能力' },
      { icon: '📊', text: '第四项能力' },
    ]
  }
  if (!['list', 'dark_panel'].includes(newType)) delete page.listItems
  if (newType === 'cover' && !page.subtitle) page.subtitle = '副标题'
  if (newType === 'steps' && !page.steps) {
    page.steps = [
      { title: '第一步', desc: '描述这个步骤' },
      { title: '第二步', desc: '描述这个步骤' },
      { title: '第三步', desc: '描述这个步骤' },
    ]
    page.decoNumber = page.decoNumber || '01'
  }
  if (newType === 'code_panel') {
    page.codeContent = page.codeContent || 'def hello():\n    print("Hello, World!")'
    page.codeLang = page.codeLang || 'python'
    page.decoNumber = page.decoNumber || '02'
  }
  if (newType === 'numbered_cards' && !page.numberedItems) {
    page.numberedItems = [
      { title: '第一要点', desc: '简要说明' },
      { title: '第二要点', desc: '简要说明' },
      { title: '第三要点', desc: '简要说明' },
    ]
    page.decoNumber = page.decoNumber || '03'
  }
  if (newType === 'newspaper') {
    page.masthead = page.masthead || 'THE DAILY BRIEF'
    if (!page.newspaperCols) {
      page.newspaperCols = [
        { headline: '核心发现', body: '简要描述' },
        { headline: '关键数据', body: '简要描述' },
        { headline: '行动建议', body: '简要描述' },
      ]
    }
    page.decoNumber = page.decoNumber || '04'
  }
  if (newType === 'big_quote') {
    page.decoNumber = page.decoNumber || '"'
  }
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
  if (isEstherTemplate(id)) {
    pages.value = createEstherDefaultPages()
    selectedPageId.value = pages.value[0].id
  }
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

  try {
    await nextTick()
    if (!exportContainer.value) throw new Error('渲染容器未就绪')

    const cardEls = exportContainer.value.querySelectorAll('.card-canvas')
    if (cardEls.length === 0) throw new Error('没有可导出的卡片')

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
      images.push(canvas.toDataURL('image/jpeg', 0.92))
    }

    exportProgress.value = ''
    const pureBase64 = images.map(d => d.replace(/^data:image\/[a-z]+;base64,/, ''))
    const planContext = {
      template: currentTemplateId.value,
      accent: customAccent.value || currentTemplate.value.accent,
      page_count: pages.value.length,
      page_types: pages.value.map(p => p.type),
      decoration: currentDecoration.value,
    }
    emit('generate', pureBase64, planContext)
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
          <optgroup label="基础模板">
            <option v-for="tpl in TEMPLATES" :key="tpl.id" :value="tpl.id">{{ tpl.name }}</option>
          </optgroup>
          <optgroup label="Esther 设计系统">
            <option v-for="tpl in ESTHER_TEMPLATES" :key="tpl.id" :value="tpl.id">{{ tpl.name }}</option>
          </optgroup>
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
              <span class="cep-page-type">{{ FULL_PAGE_TYPE_LABELS[page.type as FullPageType] || page.type }}</span>
              <span class="cep-page-title">{{ page.title || (page.content || '').slice(0, 10) }}</span>
              <span class="cep-page-chars">{{ pageCharCount(page) }}字</span>
              <div class="cep-page-actions">
                <button class="cep-icon-btn" :disabled="i === 0" @click.stop="movePage(page.id, 'up')">↑</button>
                <button class="cep-icon-btn" :disabled="i === pages.length - 1" @click.stop="movePage(page.id, 'down')">↓</button>
                <button class="cep-icon-btn cep-icon-btn-danger" @click.stop="deletePage(page.id)">×</button>
              </div>
            </div>
          </div>
          <div class="cep-add-page">
            <button v-for="(label, key) in FULL_PAGE_TYPE_LABELS" :key="key" class="cep-add-btn" @click="addPage(key as FullPageType)">
              + {{ label }}
            </button>
          </div>
        </div>
      </aside>

      <!-- 中间：预览区 -->
      <main class="cep-center">
        <!-- 模板候选条带：横向展示所有模板封面，点击切换，当前选中高亮 -->
        <div class="cep-template-strip">
          <div
            v-for="tpl in ALL_TEMPLATES"
            :key="tpl.id"
            class="cep-tpl-thumb"
            :class="{ active: tpl.id === currentTemplateId }"
            :title="tpl.description"
            @click="selectTemplate(tpl.id)"
          >
            <div class="cep-tpl-thumb-box" :style="{ width: tplThumbWidth + 'px', height: tplThumbHeight + 'px' }">
              <div class="cep-tpl-thumb-inner" :style="{ transform: `scale(${tplThumbScale})` }">
                <EstherCardRenderer v-if="isEstherTemplate(tpl.id) && pages[0]" :page="pages[0]" :theme="tpl" :decoration="currentDecoration" />
                <CardRenderer v-else-if="pages[0]" :page="pages[0] as CardPage" :theme="tpl" :decoration="currentDecoration" />
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
                <EstherCardRenderer v-if="isEsther" :page="page" :theme="effectiveTheme" :decoration="currentDecoration" />
                <CardRenderer v-else :page="page as CardPage" :theme="effectiveTheme" :decoration="currentDecoration" />
              </div>
            </div>
            <div class="cep-preview-label">{{ i + 1 }} · {{ FULL_PAGE_TYPE_LABELS[page.type as FullPageType] || page.type }}</div>
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
              <select class="cep-select" :value="selectedPage.type" @change="changePageType(selectedPage.id, ($event.target as HTMLSelectElement).value as FullPageType)">
                <optgroup label="基础页面">
                  <option v-for="(label, key) in PAGE_TYPE_LABELS" :key="key" :value="key">{{ label }}</option>
                </optgroup>
                <optgroup label="Esther 页面">
                  <option v-for="(label, key) in ESTHER_PAGE_TYPE_LABELS" :key="key" :value="key">{{ label }}</option>
                </optgroup>
              </select>
            </div>
            <div v-if="!['quote'].includes(selectedPage.type)" class="cep-form-row">
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
            <div v-if="selectedPage.type === 'cover' && isEsther" class="cep-form-row">
              <label class="cep-label">高亮关键词</label>
              <input class="cep-input" v-model="(selectedPage as EstherCardPage).highlight" placeholder="标题中需高亮的关键词" />
            </div>
            <div v-if="selectedPage.type === 'cover' && isEsther" class="cep-form-row">
              <label class="cep-label">分类标签</label>
              <input class="cep-input" v-model="(selectedPage as EstherCardPage).tag" placeholder="如：干货分享" />
            </div>
            <div v-if="selectedPage.type === 'dark_panel'" class="cep-form-row">
              <label class="cep-label">装饰数字</label>
              <input class="cep-input" v-model="(selectedPage as EstherCardPage).decoNumber" placeholder="如 01、02" />
            </div>
            <div v-if="selectedPage.type === 'dark_panel'" class="cep-form-row">
              <label class="cep-label">Emoji</label>
              <input class="cep-input" v-model="(selectedPage as EstherCardPage).emoji" placeholder="如 🚀" />
            </div>
            <div v-if="selectedPage.type === 'list' || selectedPage.type === 'dark_panel'" class="cep-form-row">
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
            <div v-if="selectedPage.type === 'compare'" class="cep-form-row">
              <label class="cep-label">左侧标题</label>
              <input class="cep-input" v-model="(selectedPage as EstherCardPage).compareLeftTitle" />
            </div>
            <div v-if="selectedPage.type === 'compare'" class="cep-form-row">
              <label class="cep-label">右侧标题</label>
              <input class="cep-input" v-model="(selectedPage as EstherCardPage).compareRightTitle" />
            </div>
            <div v-if="selectedPage.type === 'compare'" class="cep-form-row">
              <label class="cep-label">左侧要点</label>
              <div class="cep-list-editor">
                <div v-for="(item, i) in (selectedPage as EstherCardPage).compareLeftItems" :key="'l'+i" class="cep-list-edit-item">
                  <span class="cep-list-edit-num">{{ i + 1 }}</span>
                  <input class="cep-input cep-list-edit-input" v-model="(selectedPage as EstherCardPage).compareLeftItems![i]" />
                  <button class="cep-icon-btn cep-icon-btn-danger" @click="(selectedPage as EstherCardPage).compareLeftItems?.splice(i, 1)">×</button>
                </div>
                <button class="cep-add-list-btn" @click="((selectedPage as EstherCardPage).compareLeftItems ??= []).push('新要点')">+ 添加</button>
              </div>
            </div>
            <div v-if="selectedPage.type === 'compare'" class="cep-form-row">
              <label class="cep-label">右侧要点</label>
              <div class="cep-list-editor">
                <div v-for="(item, i) in (selectedPage as EstherCardPage).compareRightItems" :key="'r'+i" class="cep-list-edit-item">
                  <span class="cep-list-edit-num">{{ i + 1 }}</span>
                  <input class="cep-input cep-list-edit-input" v-model="(selectedPage as EstherCardPage).compareRightItems![i]" />
                  <button class="cep-icon-btn cep-icon-btn-danger" @click="(selectedPage as EstherCardPage).compareRightItems?.splice(i, 1)">×</button>
                </div>
                <button class="cep-add-list-btn" @click="((selectedPage as EstherCardPage).compareRightItems ??= []).push('新要点')">+ 添加</button>
              </div>
            </div>
            <div v-if="selectedPage.type === 'icon_text'" class="cep-form-row">
              <label class="cep-label">图标文字对</label>
              <div class="cep-list-editor">
                <div v-for="(pair, i) in (selectedPage as EstherCardPage).iconTextPairs" :key="'p'+i" class="cep-list-edit-item">
                  <input class="cep-input cep-list-edit-input" style="width:40px" v-model="pair.icon" />
                  <input class="cep-input cep-list-edit-input" v-model="pair.text" />
                  <button class="cep-icon-btn cep-icon-btn-danger" @click="(selectedPage as EstherCardPage).iconTextPairs?.splice(i, 1)">×</button>
                </div>
                <button class="cep-add-list-btn" @click="((selectedPage as EstherCardPage).iconTextPairs ??= []).push({ icon: '🎯', text: '新项目' })">+ 添加</button>
              </div>
            </div>
            <div v-if="selectedPage.type === 'end_page'" class="cep-form-row">
              <label class="cep-label">装饰符号</label>
              <input class="cep-input" v-model="(selectedPage as EstherCardPage).decoNumber" placeholder="如 &quot; 或 ❞" />
            </div>
            <div v-if="selectedPage.type === 'end_page'" class="cep-form-row">
              <label class="cep-label">CTA 文字</label>
              <input class="cep-input" v-model="(selectedPage as EstherCardPage).ctaText" placeholder="如：关注我，获取更多" />
            </div>

            <!-- ===== 步骤流程编辑 ===== -->
            <div v-if="selectedPage.type === 'steps'" class="cep-form-row">
              <label class="cep-label">装饰数字</label>
              <input class="cep-input" v-model="(selectedPage as EstherCardPage).decoNumber" placeholder="如 01、02" />
            </div>
            <div v-if="selectedPage.type === 'steps'" class="cep-form-row">
              <label class="cep-label">步骤</label>
              <div class="cep-list-editor">
                <div v-for="(step, i) in (selectedPage as EstherCardPage).steps" :key="'s'+i" class="cep-step-edit-item">
                  <span class="cep-list-edit-num">{{ i + 1 }}</span>
                  <div class="cep-step-edit-fields">
                    <input class="cep-input" v-model="step.title" placeholder="步骤标题" />
                    <input class="cep-input" v-model="step.desc" placeholder="步骤描述" />
                  </div>
                  <button class="cep-icon-btn cep-icon-btn-danger" @click="(selectedPage as EstherCardPage).steps?.splice(i, 1)">×</button>
                </div>
                <button class="cep-add-list-btn" @click="((selectedPage as EstherCardPage).steps ??= []).push({ title: '新步骤', desc: '描述' })">+ 添加步骤</button>
              </div>
            </div>

            <!-- ===== 代码面板编辑 ===== -->
            <div v-if="selectedPage.type === 'code_panel'" class="cep-form-row">
              <label class="cep-label">装饰数字</label>
              <input class="cep-input" v-model="(selectedPage as EstherCardPage).decoNumber" placeholder="如 02" />
            </div>
            <div v-if="selectedPage.type === 'code_panel'" class="cep-form-row">
              <label class="cep-label">代码语言</label>
              <input class="cep-input" v-model="(selectedPage as EstherCardPage).codeLang" placeholder="如 python、javascript" />
            </div>
            <div v-if="selectedPage.type === 'code_panel'" class="cep-form-row">
              <label class="cep-label">代码内容</label>
              <textarea class="cep-textarea" v-model="(selectedPage as EstherCardPage).codeContent" :rows="6" placeholder="粘贴代码"></textarea>
            </div>

            <!-- ===== 编号卡片编辑 ===== -->
            <div v-if="selectedPage.type === 'numbered_cards'" class="cep-form-row">
              <label class="cep-label">装饰数字</label>
              <input class="cep-input" v-model="(selectedPage as EstherCardPage).decoNumber" placeholder="如 03" />
            </div>
            <div v-if="selectedPage.type === 'numbered_cards'" class="cep-form-row">
              <label class="cep-label">编号项</label>
              <div class="cep-list-editor">
                <div v-for="(item, i) in (selectedPage as EstherCardPage).numberedItems" :key="'n'+i" class="cep-step-edit-item">
                  <span class="cep-list-edit-num">{{ i + 1 }}</span>
                  <div class="cep-step-edit-fields">
                    <input class="cep-input" v-model="item.title" placeholder="要点标题" />
                    <input class="cep-input" v-model="item.desc" placeholder="要点描述" />
                  </div>
                  <button class="cep-icon-btn cep-icon-btn-danger" @click="(selectedPage as EstherCardPage).numberedItems?.splice(i, 1)">×</button>
                </div>
                <button class="cep-add-list-btn" @click="((selectedPage as EstherCardPage).numberedItems ??= []).push({ title: '新要点', desc: '简要说明' })">+ 添加要点</button>
              </div>
            </div>

            <!-- ===== 报纸多栏编辑 ===== -->
            <div v-if="selectedPage.type === 'newspaper'" class="cep-form-row">
              <label class="cep-label">报头</label>
              <input class="cep-input" v-model="(selectedPage as EstherCardPage).masthead" placeholder="如 THE DAILY BRIEF" />
            </div>
            <div v-if="selectedPage.type === 'newspaper'" class="cep-form-row">
              <label class="cep-label">栏目</label>
              <div class="cep-list-editor">
                <div v-for="(col, i) in (selectedPage as EstherCardPage).newspaperCols" :key="'np'+i" class="cep-step-edit-item">
                  <span class="cep-list-edit-num">{{ i + 1 }}</span>
                  <div class="cep-step-edit-fields">
                    <input class="cep-input" v-model="col.headline" placeholder="栏目标题" />
                    <input class="cep-input" v-model="col.body" placeholder="栏目正文" />
                  </div>
                  <button class="cep-icon-btn cep-icon-btn-danger" @click="(selectedPage as EstherCardPage).newspaperCols?.splice(i, 1)">×</button>
                </div>
                <button class="cep-add-list-btn" @click="((selectedPage as EstherCardPage).newspaperCols ??= []).push({ headline: '新栏目', body: '栏目内容' })">+ 添加栏目</button>
              </div>
            </div>

            <!-- ===== 大字金句编辑 ===== -->
            <div v-if="selectedPage.type === 'big_quote'" class="cep-form-row">
              <label class="cep-label">金句内容</label>
              <textarea class="cep-textarea" v-model="selectedPage.content" :rows="3" placeholder="一句足够大的话"></textarea>
            </div>
            <div v-if="selectedPage.type === 'big_quote'" class="cep-form-row">
              <label class="cep-label">装饰符号</label>
              <input class="cep-input" v-model="(selectedPage as EstherCardPage).decoNumber" placeholder='如 &quot; 或 ❞' />
            </div>

            <div class="cep-form-row">
              <label class="cep-label">页脚</label>
              <input class="cep-input" v-model="selectedPage.footer" />
            </div>
          </div>
        </section>

        <!-- 文案原文参考（来自 copywrite 节点） -->
        <section v-if="cardDraft?.copywrite_context" class="cep-panel">
          <h4 class="cep-panel-title">
            文案原文
            <button class="cep-redistribute-btn" @click="redistributeContent">重新分配</button>
          </h4>
          <div class="cep-form">
            <div class="cep-form-row">
              <label class="cep-label">标题</label>
              <div class="cep-readonly-text">{{ cardDraft.copywrite_context.title }}</div>
            </div>
            <div class="cep-form-row">
              <label class="cep-label">正文</label>
              <div class="cep-readonly-text cep-readonly-scroll">{{ cardDraft.copywrite_context.content }}</div>
            </div>
            <div v-if="cardDraft.copywrite_context.tags?.length" class="cep-form-row">
              <label class="cep-label">标签</label>
              <div class="cep-readonly-text">{{ cardDraft.copywrite_context.tags.join(' · ') }}</div>
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
      <template v-for="page in pages" :key="page.id">
        <EstherCardRenderer v-if="isEsther" :page="page" :theme="effectiveTheme" :decoration="currentDecoration" />
        <CardRenderer v-else :page="page as CardPage" :theme="effectiveTheme" :decoration="currentDecoration" />
      </template>
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
  grid-template-columns: 180px minmax(0, 1fr) 180px;
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
  background: #EEF0F4;
  border-radius: 12px;
}

/* 模板候选条带：横向排列所有模板封面缩略图 */
.cep-template-strip {
  display: flex;
  gap: 10px;
  padding: 12px;
  border-bottom: none;
  margin-bottom: 14px;
  background: #EEF0F4;
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
  gap: 4px;
  padding: 5px 4px;
  border: none;
  border-radius: 5px;
  cursor: pointer;
  transition: all 0.15s;
}
.cep-page-item:hover { background: #F3F4F6; }
.cep-page-item.active { background: #F3F4F6; }
.cep-page-num { font-size: 11px; font-weight: 600; color: #6B7280; min-width: 14px; flex-shrink: 0; }
.cep-page-type {
  font-size: 10px;
  padding: 1px 4px;
  background: #E5E7EB;
  border-radius: 3px;
  color: #4B5563;
  flex-shrink: 0;
  white-space: nowrap;
}
.cep-page-item.active .cep-page-type { background: #065F46; color: #FFFFFF; }
.cep-page-title {
  flex: 1;
  font-size: 11px;
  color: #1A1A1A;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}
.cep-page-actions { display: flex; gap: 1px; flex-shrink: 0; }
.cep-icon-btn {
  width: 18px; height: 18px;
  display: flex; align-items: center; justify-content: center;
  background: transparent; border: none; border-radius: 3px;
  color: #9CA3AF; cursor: pointer; font-size: 12px;
}
.cep-icon-btn:hover:not(:disabled) { background: #E5E7EB; color: #1A1A1A; }
.cep-icon-btn:disabled { opacity: 0.3; cursor: not-allowed; }
.cep-icon-btn-danger:hover { background: #FEE2E2; color: #DC2626; }
.cep-add-page { display: flex; flex-wrap: wrap; gap: 3px; margin-top: 8px; }
.cep-add-btn {
  padding: 3px 6px;
  background: #EEF0F4;
  border: none;
  border-radius: 5px;
  color: #6B7280;
  font-size: 10px;
  cursor: pointer;
  white-space: nowrap;
}
.cep-add-btn:hover { color: #065F46; background: #D1FAE5; }

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
.cep-preview-card:hover { border-color: #E5E7EB; }
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

/* 文案原文只读展示 */
.cep-readonly-text {
  font-size: 12px; line-height: 1.6; color: #374151;
  background: #F9FAFB; border-radius: 4px; padding: 6px 8px;
  word-break: break-all; white-space: pre-wrap;
}
.cep-readonly-scroll {
  max-height: 120px; overflow-y: auto;
}

/* 重新分配按钮 */
.cep-redistribute-btn {
  font-size: 11px; color: #059669; background: #ECFDF5;
  border: 1px solid #A7F3D0; border-radius: 4px;
  padding: 2px 8px; cursor: pointer; margin-left: auto;
  transition: all 0.15s;
}
.cep-redistribute-btn:hover { background: #D1FAE5; color: #047857; }

/* 页面字数统计 */
.cep-page-chars {
  font-size: 9px; color: #9CA3AF; flex-shrink: 0; white-space: nowrap;
}

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

.cep-step-edit-item {
  display: flex;
  align-items: flex-start;
  gap: 4px;
  padding: 4px 0;
}
.cep-step-edit-fields {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

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
  background: #EEF0F4;
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