import { ref, computed, nextTick, type Ref, type ComputedRef } from 'vue'
import { useWorkStore } from '@/stores/work'
import { useChatContextStore } from '@/stores/chatContext'
import { useResizeHandle } from '@/composables/useResizeHandle'
import { X, BarChart3, Image as ImageIcon, File as FileIcon, FolderOpen, Music, Video, FileText, Code, FileSpreadsheet } from 'lucide-vue-next'

export interface ChatWorkDeps {
  inputText: Ref<string>
  isStreaming: Ref<boolean>
  stopStreaming: () => void
  sendMessageRef: Ref<() => Promise<void>>
  emitStartCoverWorkflow: (topic: string) => void
}

export function useChatWork(deps: ChatWorkDeps) {
  const { inputText, isStreaming, stopStreaming, sendMessageRef, emitStartCoverWorkflow } = deps

  const workStore = useWorkStore()

  const activeWork = computed(() => workStore.activeWork)
  const showWorkDetail = computed({
    get: () => workStore.showWorkDetail,
    set: (v) => {
      workStore.showWorkDetail = v
      const ctxStore = useChatContextStore()
      ctxStore.setSidebarVisible(v)
    }
  })
  function calcDefaultDetailWidth() {
    return Math.max(280, Math.min(600, Math.floor(window.innerWidth / 3)))
  }
  const detailResize = useResizeHandle({
    direction: 'left',
    minWidth: 280,
    maxWidth: 600,
    storageKey: 'mint-detail-width-v2',
    defaultWidth: calcDefaultDetailWidth,
  })
  const detailWidth = detailResize.width
  const startDetailResize = detailResize.startResize
  const resetDetailWidth = detailResize.resetWidth

  function exitWorkContext() {
    const ctxStore = useChatContextStore()
    ctxStore.unlinkWork()
    showWorkDetail.value = false
    ctxStore.setSidebarVisible(false)
  }

  async function onWorkChatAction(action: string) {
    if (action === 'design_cover') {
      const workCtx = workStore.buildWorkContext()
      const topic = workCtx?.title || workCtx?.contentText?.slice(0, 30) || inputText.value.trim() || '封面设计'
      emitStartCoverWorkflow(topic)
      return
    }
    if (action.startsWith('reorganize_cards:')) {
      const instruction = action.slice('reorganize_cards:'.length).trim()
      inputText.value = `请根据当前视觉组图重新编排卡片内容：${instruction}`
      nextTick(() => sendMessageRef.value())
      return
    }
    const actionMap: Record<string, string> = {
      analyze: '帮我分析一下这篇作品为什么是这个表现等级',
      optimize_title: '帮我优化这篇作品的标题，给出3个方案',
      rewrite: '帮我改写这篇作品的内容',
      evolve: '从这篇作品中提炼可复用的创作模式',
      reference: '帮我分析同类爆款作品，提取可复用的创作模式',
      generate_tags: '帮我为这篇作品生成合适的标签',
      publish: '帮我检查这篇作品是否可以发布，给出发布建议',

      trending_topics: '帮我发现当前小红书的热门话题和趋势',
      competitor_analysis: '帮我分析竞品账号的内容策略和表现',
      content_gap_analysis: '帮我找出当前领域的内容缺口和机会',
      rss_aggregator: '帮我聚合相关领域的RSS资讯和Newsletter',
      ugc_discovery: '帮我发现用户生成内容中的优质素材和灵感',
      algorithm_updates: '帮我追踪小红书平台的算法和规则变化',

      content_matrix: '帮我生成选题矩阵，按内容支柱和格式排列选题方向',
      topic_evaluator: '帮我评估当前选题的潜力和可行性',
      hook_generator: '帮我生成开头钩子的多种变体，吸引读者停留',
      carousel_planner: '帮我策划小红书轮播图的分页结构和节奏',
      voice_builder: '帮我构建创作者声音画像，提炼独特的表达风格',
      persona_check: '帮我检查当前内容是否符合我的创作者人设',
      positioning_analysis: '帮我分析账号定位和差异化方向',
      content_strategy: '帮我制定内容策略，规划内容方向和节奏',
      audience_profiler: '帮我分析目标受众画像，了解读者偏好',

      xhs_note_creator: '帮我创建一篇完整的小红书笔记，包括标题、正文、标签和封面建议',
      copywriting: '帮我撰写营销文案，提炼卖点，生成FAB文案',
      social_content: '帮我生成适合社交媒体发布的内容',
      card_xiaohongshu: '帮我生成小红书知识卡片的HTML和视觉方案',
      card_quote: '帮我生成横版金句卡片',
      card_design: '帮我设计卡片的视觉风格和排版方案',
      infographic: '帮我生成信息图的HTML和视觉方案',
      poster_hero: '帮我生成营销海报的HTML和视觉方案',
      comparison_card: '帮我生成对比图或一图流卡片',
      style_transfer: '帮我把当前内容改写为另一种风格',
      text_polisher: '帮我去除AI感，改写得更自然、更像真人写的',
      text_condenser: '帮我压缩当前文案的字数，保留核心信息',
      caption_hashtag: '帮我生成小红书caption和hashtag',
      post_formatter: '帮我按小红书格式排版当前内容',

      video_script: '帮我撰写短视频脚本，包含分镜、旁白和字幕',
      video_strategy: '帮我制定视频内容策略',
      article_outline: '帮我生成文章大纲',
      novel_writer: '帮我撰写长篇小说或网文连载',
      paper_explainer: '帮我解读科研论文，用通俗语言重述核心发现',
      mindmap: '帮我生成思维导图',
      gzh_design: '帮我排版微信公众号文章',

      tts_voiceover: '帮我用TTS生成旁白配音',
      auto_subtitle: '帮我自动生成字幕',
      multi_voice_dubbing: '帮我生成多人配音方案',
      voice_clone: '帮我克隆声音',
      video_intro_outro: '帮我生成片头片尾',
      ai_video_gen: '帮我用AI生成视频',
      auto_short_video: '帮我自动生成短视频',
      video_editing: '帮我编辑视频',
      video_reframe: '帮我将视频重框为9:16竖版',
      beat_sync: '帮我制作卡点视频',
      slideshow_video: '帮我把图文转成视频',
      video_highlights: '帮我提取视频高光片段',
      video_chapters: '帮我切分视频章节',
      clipify: '帮我把长视频剪辑成短视频',
      livestream: '帮我策划直播方案和话术',
      silence_remove: '帮我移除视频中的静音片段',

      upload_material: '我需要上传素材，请指导我操作',
      upload_livestream: '我需要上传直播录像，请指导我操作',
      select_from_library: '我想从素材库选择已有素材',
      ai_clip: '帮我用AI智能剪辑当前素材',

      publish_checklist: '帮我做发布前完整性检查',
      quality_gate: '帮我做质量门禁检查，确保内容达标',
      risk_scanner: '帮我扫描内容的原创度和版权风险',
      content_repurposing: '帮我把当前内容改写为一稿多发版本',

      data_tracker: '帮我追踪发布后的数据表现',
      comment_insights: '帮我分析评论区的洞察和舆情',
      content_postmortem: '帮我做内容复盘，总结经验教训',
      strategy_advisor: '帮我做策略迭代建议',

      export_douyin: '帮我导出适配抖音的格式',
      export_xhs: '帮我导出适配小红书的格式',
      export_bilibili: '帮我导出适配B站的格式',
    }
    const prompt = actionMap[action]
    if (prompt) {
      if (isStreaming.value) {
        stopStreaming()
        await new Promise(r => setTimeout(r, 400))
      }
      inputText.value = prompt
      nextTick(() => sendMessageRef.value())
    }
  }

  function getFileIconComponent(type?: string) {
    if (!type) return FileIcon
    if (type.startsWith('image/')) return ImageIcon
    if (type.startsWith('video/')) return Video
    if (type.startsWith('audio/')) return Music
    if (type.includes('pdf')) return FileText
    if (type.includes('json') || type.includes('javascript')) return Code
    if (type.includes('csv') || type.includes('spreadsheet')) return FileSpreadsheet
    return FileIcon
  }

  return {
    activeWork,
    showWorkDetail,
    detailWidth,
    startDetailResize,
    resetDetailWidth,
    exitWorkContext,
    onWorkChatAction,
    getFileIconComponent,
  }
}