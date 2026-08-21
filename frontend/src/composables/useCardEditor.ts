import { ref, computed, nextTick, watch, onMounted, onBeforeUnmount } from 'vue'
import html2canvas from 'html2canvas'
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

const ALL_TEMPLATES = [...TEMPLATES, ...ESTHER_TEMPLATES]
const ALL_DECORATION_PRESETS = [...DECORATION_PRESETS, ...ESTHER_DECORATION_PRESETS]

export type CardDraft = {
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
    imageUrl?: string
    backgroundImage?: string
    imageFilter?: string
    qaPairs?: Array<{ q: string; a: string }>
    timelineItems?: Array<{ date: string; event: string }>
    statItems?: Array<{ value: string; label: string; unit?: string }>
    avatarUrl?: string
    name?: string
    role?: string
    bio?: string
  }>
  suggested_template?: string
  custom_accent?: string
  suggested_decoration?: DecorationConfig
  copywrite_context?: {
    title: string
    content: string
    tags: string[]
  }
}

export type PlanContext = {
  template: string
  accent: string
  page_count: number
  page_types: string[]
  decoration: DecorationConfig
}

export function useCardEditor(cardDraft: () => CardDraft | undefined) {
  const currentTemplateId = ref<string>('minimal_white')
  const currentDecoration = ref<DecorationConfig>(createDefaultDecoration())
  const pages = ref<EstherCardPage[]>(createDefaultPages() as EstherCardPage[])
  const selectedPageId = ref<string>(pages.value[0].id)
  const customFontSize = ref<number | null>(null)
  const customBg = ref<string>('')
  const customAccent = ref<string>('')
  const exporting = ref(false)
  const exportProgress = ref('')
  const exportContainer = ref<HTMLElement | null>(null)

  const MAX_UNDO = 30
  const undoStack = ref<string[]>([])
  const redoStack = ref<string[]>([])

  function pushUndoSnapshot() {
    undoStack.value.push(JSON.stringify(pages.value))
    if (undoStack.value.length > MAX_UNDO) undoStack.value.shift()
    redoStack.value = []
  }

  function undo() {
    if (undoStack.value.length === 0) return
    redoStack.value.push(JSON.stringify(pages.value))
    const snapshot = JSON.parse(undoStack.value.pop()!) as EstherCardPage[]
    pages.value = snapshot
    if (!pages.value.find(p => p.id === selectedPageId.value)) {
      selectedPageId.value = pages.value[0]?.id || ''
    }
  }

  function redo() {
    if (redoStack.value.length === 0) return
    undoStack.value.push(JSON.stringify(pages.value))
    const snapshot = JSON.parse(redoStack.value.pop()!) as EstherCardPage[]
    pages.value = snapshot
    if (!pages.value.find(p => p.id === selectedPageId.value)) {
      selectedPageId.value = pages.value[0]?.id || ''
    }
  }

  const canUndo = computed(() => undoStack.value.length > 0)
  const canRedo = computed(() => redoStack.value.length > 0)

  const lastDraftSignature = ref<string>('')

  watch(cardDraft, (draft) => {
    if (!draft || !draft.pages || draft.pages.length === 0) return

    const signature = `${draft.pages.length}|${draft.pages[0]?.title || ''}|${draft.suggested_template || ''}|${draft.custom_accent || ''}|${(draft as Record<string, unknown>).customFontSize || ''}|${(draft as Record<string, unknown>).customBg || ''}`
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
      if (esther.imageUrl) base.imageUrl = esther.imageUrl as string
      if (esther.backgroundImage) base.backgroundImage = esther.backgroundImage as string
      if (esther.imageFilter) base.imageFilter = esther.imageFilter as string
      if (esther.qaPairs) base.qaPairs = esther.qaPairs as Array<{ q: string; a: string }>
      if (esther.timelineItems) base.timelineItems = esther.timelineItems as Array<{ date: string; event: string }>
      if (esther.statItems) base.statItems = esther.statItems as Array<{ value: string; label: string; unit?: string }>
      if (esther.avatarUrl) base.avatarUrl = esther.avatarUrl as string
      if (esther.name) base.name = esther.name as string
      if (esther.role) base.role = esther.role as string
      if (esther.bio) base.bio = esther.bio as string
      return base
    })
    selectedPageId.value = pages.value[0].id
    if (draft.suggested_template && ALL_TEMPLATES.find(t => t.id === draft.suggested_template)) {
      currentTemplateId.value = draft.suggested_template
    }
    if (draft.custom_accent) {
      customAccent.value = draft.custom_accent
    }
    if (draft.suggested_decoration) {
      currentDecoration.value = draft.suggested_decoration
    }
    // 恢复草稿保存的自定义样式
    const draftData = draft as Record<string, unknown>
    if (draftData.customFontSize != null) {
      customFontSize.value = draftData.customFontSize as number
    }
    if (draftData.customBg) {
      customBg.value = draftData.customBg as string
    }
    if (draftData.decoration) {
      currentDecoration.value = draftData.decoration as DecorationConfig
    }
    if (draftData.accent && !draft.custom_accent) {
      customAccent.value = draftData.accent as string
    }
    if (draftData.template && !draft.suggested_template) {
      const tid = draftData.template as string
      if (ALL_TEMPLATES.find(t => t.id === tid)) {
        currentTemplateId.value = tid
      }
    }
  }, { immediate: true, deep: true })

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

  const isEsther = computed(() => isEstherTemplate(currentTemplateId.value))

  function selectPage(id: string) { selectedPageId.value = id }

  function addPage(type: FullPageType) {
    pushUndoSnapshot()
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
    pushUndoSnapshot()
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
    pushUndoSnapshot()
    const tmp = pages.value[idx]
    pages.value[idx] = pages.value[targetIdx]
    pages.value[targetIdx] = tmp
  }

  function movePageByIndex(fromIndex: number, toIndex: number) {
    if (fromIndex === toIndex) return
    if (fromIndex < 0 || fromIndex >= pages.value.length) return
    if (toIndex < 0 || toIndex >= pages.value.length) return
    pushUndoSnapshot()
    const [moved] = pages.value.splice(fromIndex, 1)
    pages.value.splice(toIndex, 0, moved)
  }

  function duplicatePage(id: string) {
    pushUndoSnapshot()
    const idx = pages.value.findIndex(p => p.id === id)
    if (idx < 0) return
    const source = pages.value[idx]
    const copy: EstherCardPage = { ...source, id: `page_${Date.now()}_${pages.value.length}` }
    if (source.listItems) copy.listItems = [...source.listItems]
    if (source.steps) copy.steps = source.steps.map(s => ({ ...s }))
    if (source.numberedItems) copy.numberedItems = source.numberedItems.map(n => ({ ...n }))
    if (source.iconTextPairs) copy.iconTextPairs = source.iconTextPairs.map(p => ({ ...p }))
    if (source.newspaperCols) copy.newspaperCols = source.newspaperCols.map(c => ({ ...c }))
    if (source.compareLeftItems) copy.compareLeftItems = [...source.compareLeftItems]
    if (source.compareRightItems) copy.compareRightItems = [...source.compareRightItems]
    if (source.qaPairs) copy.qaPairs = source.qaPairs.map(p => ({ ...p }))
    if (source.timelineItems) copy.timelineItems = source.timelineItems.map(t => ({ ...t }))
    if (source.statItems) copy.statItems = source.statItems.map(s => ({ ...s }))
    pages.value.splice(idx + 1, 0, copy)
    selectedPageId.value = copy.id
  }

  function pageCharCount(page: any): number {
    const parts = [page.title || '', page.subtitle || '', page.content || '', ...(page.listItems || [])]
    return parts.join('').length
  }

  function redistributeContent() {
    const ctx = cardDraft()?.copywrite_context
    if (!ctx || !ctx.content) return

    let paragraphs = ctx.content.split('\n').filter((p: string) => p.trim())
    if (paragraphs.length <= 1) {
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

    const contentPages = pages.value.filter(p =>
      ['content', 'list', 'dark_panel', 'quote', 'big_quote'].includes(p.type)
    )

    if (contentPages.length === 0) return

    const perPage = Math.max(1, Math.ceil(paragraphs.length / contentPages.length))
    let paraIdx = 0

    for (const page of contentPages) {
      if (paraIdx >= paragraphs.length) {
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
    pushUndoSnapshot()
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
    if (newType === 'image_page') {
      page.imageUrl = page.imageUrl || ''
      page.content = ''
    }
    if (newType === 'qa' && !page.qaPairs) {
      page.qaPairs = [
        { q: '第一个问题？', a: '回答。' },
        { q: '第二个问题？', a: '回答。' },
      ]
    }
    if (newType === 'timeline' && !page.timelineItems) {
      page.timelineItems = [
        { date: '2024.01', event: '事件一' },
        { date: '2024.06', event: '事件二' },
      ]
    }
    if (newType === 'stat_card' && !page.statItems) {
      page.statItems = [
        { value: '100', label: '指标一', unit: '' },
        { value: '99', label: '指标二', unit: '%' },
      ]
    }
    if (newType === 'profile') {
      page.name = page.name || '作者名称'
      page.role = page.role || '职业/标签'
      page.bio = page.bio || '自我介绍'
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

  function addImagePage(imageUrl: string) {
    pushUndoSnapshot()
    const newPage: EstherCardPage = {
      id: `page_img_${Date.now()}_${pages.value.length}`,
      type: 'image_page',
      title: '',
      content: '',
      imageUrl,
      footer: '',
    }
    pages.value.push(newPage)
    selectedPageId.value = newPage.id
  }

  function setPageBackground(pageId: string, imageUrl: string) {
    pushUndoSnapshot()
    const page = pages.value.find(p => p.id === pageId)
    if (page) {
      page.backgroundImage = imageUrl
    }
  }

  function fillPageFromCopywrite(pageId: string) {
    const ctx = cardDraft()?.copywrite_context
    if (!ctx) return false
    const page = pages.value.find(p => p.id === pageId)
    if (!page) return false
    pushUndoSnapshot()
    if (ctx.title && !page.title) {
      page.title = ctx.title
    }
    if (ctx.content) {
      if (page.type === 'list' || page.type === 'icon_text') {
        if (!page.listItems || page.listItems.length === 0) {
          page.listItems = ctx.content.split(/\n|。/).filter((s: string) => s.trim()).map((s: string) => s.trim())
        }
      } else if (page.type === 'qa') {
        if (!page.qaPairs || page.qaPairs.length === 0) {
          const lines = ctx.content.split(/\n/).filter((s: string) => s.trim())
          page.qaPairs = []
          for (let i = 0; i < lines.length; i += 2) {
            page.qaPairs.push({ q: lines[i]?.trim() || '问题', a: lines[i + 1]?.trim() || '回答' })
          }
          if (page.qaPairs.length === 0) page.qaPairs = [{ q: ctx.title || '问题', a: ctx.content }]
        }
      } else if (page.type === 'steps') {
        if (!page.steps || page.steps.length === 0) {
          const lines = ctx.content.split(/\n|。/).filter((s: string) => s.trim())
          page.steps = lines.map((s: string, i: number) => ({ title: `步骤${i + 1}`, desc: s.trim() }))
        }
      } else if (page.type === 'numbered_cards') {
        if (!page.numberedItems || page.numberedItems.length === 0) {
          const lines = ctx.content.split(/\n|。/).filter((s: string) => s.trim())
          page.numberedItems = lines.map((s: string, i: number) => ({ title: `${i + 1}`, desc: s.trim() }))
        }
      } else if (page.type === 'timeline') {
        if (!page.timelineItems || page.timelineItems.length === 0) {
          const lines = ctx.content.split(/\n/).filter((s: string) => s.trim())
          page.timelineItems = lines.map((s: string, i: number) => ({ date: `${i + 1}`, event: s.trim() }))
        }
      } else if (page.type === 'stat_card') {
        if (!page.statItems || page.statItems.length === 0) {
          const nums = ctx.content.match(/[\d.]+[%+]?/g)
          if (nums) {
            page.statItems = nums.slice(0, 4).map(n => ({ value: n, label: '指标' }))
          }
        }
      } else if (page.type === 'quote' || page.type === 'big_quote') {
        if (!page.content) page.content = ctx.content
      } else {
        if (!page.content) page.content = ctx.content
      }
    }
    if (ctx.tags && ctx.tags.length > 0 && !page.footer) {
      page.footer = ctx.tags.map((t: string) => `#${t}`).join(' ')
    }
    return true
  }

  async function generateImages(): Promise<{ images: string[]; planContext: PlanContext } | null> {
    if (exporting.value) return null
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
      const planContext: PlanContext = {
        template: currentTemplateId.value,
        accent: customAccent.value || currentTemplate.value.accent,
        page_count: pages.value.length,
        page_types: pages.value.map(p => p.type),
        decoration: currentDecoration.value,
      }
      return { images: pureBase64, planContext }
    } catch (e) {
      exportProgress.value = ''
      console.error('generateImages failed:', e)
      alert(`生成图片失败：${e instanceof Error ? e.message : String(e)}`)
      return null
    } finally {
      exporting.value = false
    }
  }

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

  function initPreviewResize() {
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
  }

  function destroyPreviewResize() {
    resizeObserver?.disconnect()
  }

  watch(() => pages.value.length, () => nextTick(recalcPreviewSize))

  const tplThumbWidth = 48
  const tplThumbScale = tplThumbWidth / 1080
  const tplThumbHeight = Math.floor(tplThumbWidth * 1440 / 1080)

  return {
    ALL_TEMPLATES,
    ALL_DECORATION_PRESETS,
    currentTemplateId,
    currentDecoration,
    pages,
    selectedPageId,
    customFontSize,
    customBg,
    customAccent,
    exporting,
    exportProgress,
    exportContainer,
    currentTemplate,
    effectiveTheme,
    selectedPage,
    filteredDecoPresets,
    isEsther,
    previewScale,
    boxWidth,
    boxHeight,
    previewGrid,
    tplThumbWidth,
    tplThumbScale,
    tplThumbHeight,
    selectPage,
    addPage,
    deletePage,
    movePage,
    duplicatePage,
    pageCharCount,
    redistributeContent,
    changePageType,
    addListItem,
    deleteListItem,
    selectTemplate,
    resetCustomStyle,
    selectDecoration,
    setDecorationNone,
    addImagePage,
    setPageBackground,
    movePageByIndex,
    undo,
    redo,
    canUndo,
    canRedo,
    fillPageFromCopywrite,
    generateImages,
    initPreviewResize,
    destroyPreviewResize,
    recalcPreviewSize,
  }
}