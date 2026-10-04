import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { authFetch } from '@/api/client'
import type { CardPage } from '@/card-editor/templates'

export interface WorkItem {
  id: string
  platform: string
  contentType: string
  title: string
  description?: string
  contentText?: string
  scriptText?: string
  coverUrl?: string
  images?: string[]
  videoUrl?: string
  tags?: string[]
  url: string
  likes: number
  comments: number
  shares: number
  collects: number
  views: number
  playCount?: number
  completionRate?: number
  interactionRate: number
  viralScore: number
  performanceTier: string
  viralType?: string
  aiDiagnosis?: {
    performanceReason: string
    boostFactors: Array<{ factor: string; evidence: string; dimension: string }>
    dragFactors: Array<{ factor: string; evidence: string; dimension: string }>
    comparisonInsight: string
    nextAction: string
  }
  publishedAt?: string
  dataCollectedAt: string
  isDraft?: boolean
  publishedPlatforms?: string[]
  contentStatus?: 'draft' | 'published' | 'collected'
  titlePattern?: string
  emotionTrigger?: string
  contentStructure?: string
  firstPageHtml?: string
  allPageHtmls?: string[]
  cardDraft?: {
    title?: string
    template?: string
    pages: Array<Partial<CardPage> & { type: string }>
    htmlUrls?: string[]
    pngUrls?: string[]
  }
}

export interface WorkContext {
  workId: string
  title: string
  platform: string
  contentType: string
  performanceTier: string
  contentText?: string
  scriptText?: string
  tags?: string[]
  cardDraft?: WorkItem['cardDraft']
  metrics: {
    likes: number
    views: number
    interactionRate: number
    completionRate?: number
  }
  diagnosis?: WorkItem['aiDiagnosis']
}

const PLATFORM_LABELS: Record<string, string> = {
  xiaohongshu: '小红书',
  douyin: '抖音',
  kuaishou: '快手',
  bilibili: 'B站',
  wechat_video: '视频号',
}

const CONTENT_TYPE_LABELS: Record<string, string> = {
  image_text: '图文',
  short_video: '短视频',
  long_video: '长视频',
  image_gallery: '图集',
  live_clip: '直播切片',
  ai_edit: 'AI剪辑',
  voiceover: '口播',
  long_article: '长文',
}

const TIER_COLORS: Record<string, string> = {
  S: '#ef4444',
  A: '#f97316',
  B: '#eab308',
  C: '#6b7280',
}

export const useWorkStore = defineStore('work', () => {
  const works = ref<WorkItem[]>([])
  const activeWorkId = ref<string | null>(null)
  const isLoading = ref(false)
  const creationNavExpanded = ref(false)
  const workSearchQuery = ref('')
  const sidebarTab = ref<'chat' | 'content'>('chat')
  const activeCreationType = ref<'image_text' | 'voiceover' | 'short_video' | 'ai_edit' | 'long_article' | 'live_clip'>('image_text')
  const showWorkDetail = ref(false)

  const activeWork = computed(() =>
    works.value.find(w => w.id === activeWorkId.value) ||
    outputWorks.value.find(w => w.id === activeWorkId.value) ||
    null
  )

  const filteredWorks = computed(() => {
    if (!workSearchQuery.value) return works.value
    const q = workSearchQuery.value.toLowerCase()
    return works.value.filter(w =>
      w.title.toLowerCase().includes(q) ||
      w.tags?.some(t => t.toLowerCase().includes(q))
    )
  })

  const worksByType = computed(() => {
    const groups: Record<string, WorkItem[]> = {}
    for (const w of works.value) {
      const key = w.contentType || 'image_text'
      if (!groups[key]) groups[key] = []
      groups[key].push(w)
    }
    for (const key of Object.keys(groups)) {
      groups[key].sort((a, b) => {
        const tierOrder: Record<string, number> = { S: 0, A: 1, B: 2, C: 3 }
        return (tierOrder[a.performanceTier] ?? 3) - (tierOrder[b.performanceTier] ?? 3)
      })
    }
    return groups
  })

  function setActiveWork(workId: string | null) {
    activeWorkId.value = workId
  }

  function createDraft(contentType: string = 'image_text'): WorkItem {
    const draft: WorkItem = {
      id: 'draft-' + Date.now(),
      platform: 'xiaohongshu',
      contentType,
      title: '未命名创作',
      description: '',
      contentText: '',
      coverUrl: '',
      tags: [],
      url: '',
      likes: 0,
      comments: 0,
      shares: 0,
      collects: 0,
      views: 0,
      interactionRate: 0,
      viralScore: 0,
      performanceTier: '-',
      dataCollectedAt: new Date().toISOString(),
      isDraft: true,
    }
    works.value.unshift(draft)
    activeWorkId.value = draft.id
    return draft
  }

  async function deleteWork(workId: string) {
    const idx = works.value.findIndex(w => w.id === workId)
    if (idx !== -1) {
      works.value.splice(idx, 1)
      if (activeWorkId.value === workId) {
        activeWorkId.value = null
      }
      return
    }
    const oIdx = outputWorks.value.findIndex(w => w.id === workId)
    if (oIdx !== -1) {
      const { deleteCreativeArtifact } = await import('@/api/creativeArtifact')
      await deleteCreativeArtifact(workId).catch(() => {})
      outputWorks.value.splice(oIdx, 1)
      if (activeWorkId.value === workId) {
        activeWorkId.value = null
      }
    }
  }

  function updateDraft(workId: string, updates: Partial<WorkItem>) {
    const idx = works.value.findIndex(w => w.id === workId)
    if (idx !== -1) {
      works.value[idx] = { ...works.value[idx], ...updates }
    }
  }

  function extractFirstPageHtml(cardDraft: WorkItem['cardDraft']): string {
    if (!cardDraft?.pages?.length) return ''
    const first = cardDraft.pages[0] as any
    return first?.content?.htmlContent || first?.htmlContent || ''
  }

  function saveCardAsDraft(cardDraft: WorkItem['cardDraft'], title?: string, coverUrl?: string, images?: string[]): WorkItem {
    const firstPageHtml = extractFirstPageHtml(cardDraft)
    const draft: WorkItem = {
      id: 'draft-' + Date.now(),
      platform: 'xiaohongshu',
      contentType: 'image_text',
      title: title || cardDraft?.title || '视觉组图草稿',
      description: '',
      contentText: '',
      coverUrl: coverUrl || '',
      images: images || [],
      tags: [],
      url: '',
      likes: 0,
      comments: 0,
      shares: 0,
      collects: 0,
      views: 0,
      interactionRate: 0,
      viralScore: 0,
      performanceTier: '-',
      dataCollectedAt: new Date().toISOString(),
      isDraft: true,
      contentStatus: 'draft',
      cardDraft,
      firstPageHtml,
    }
    works.value.unshift(draft)
    return draft
  }

  function toggleCreationNav() {
    creationNavExpanded.value = !creationNavExpanded.value
  }

  function getPlatformLabel(platform: string): string {
    return PLATFORM_LABELS[platform] || platform
  }

  function getContentTypeLabel(contentType: string): string {
    return CONTENT_TYPE_LABELS[contentType] || contentType
  }

  function getTierColor(tier: string): string {
    return TIER_COLORS[tier] || '#6b7280'
  }

  function formatNumber(n: number): string {
    if (n >= 10000) return (n / 10000).toFixed(1) + '万'
    if (n >= 1000) return (n / 1000).toFixed(1) + 'k'
    return String(n)
  }

  const MOCK_WORKS: WorkItem[] = [
    {
      id: 'w1',
      platform: 'xiaohongshu',
      contentType: 'image_text',
      title: '5个让PPT瞬间高级的排版技巧',
      description: '职场人必备的PPT排版秘籍，学会这5招让你的汇报脱颖而出',
      contentText: '很多人做PPT就是套模板，但其实只要掌握几个排版原则，就能让PPT瞬间高级起来：\n\n1. 留白比填充更重要\n2. 字体不超过2种\n3. 配色用60-30-10法则\n4. 对齐是第一生产力\n5. 一页只讲一个观点\n\n记住：少即是多，克制就是高级。',
      coverUrl: 'https://picsum.photos/seed/ppt-tips/400/300',
      images: ['https://picsum.photos/seed/ppt-tips/400/300'],
      tags: ['PPT', '职场技能', '排版设计', '办公效率'],
      url: 'https://www.xiaohongshu.com/explore/w1',
      likes: 12400,
      comments: 892,
      shares: 3200,
      collects: 8600,
      views: 156000,
      interactionRate: 16.1,
      viralScore: 92,
      performanceTier: 'S',
      viralType: 'collect_driven',
      aiDiagnosis: {
        performanceReason: '收藏率极高（5.5%），说明内容实用性强，用户愿意反复查看',
        boostFactors: [
          { factor: '收藏率远超均值', evidence: '收藏8600/浏览156000=5.5%，同类均值1.2%', dimension: '收藏' },
          { factor: '标题数字钩子', evidence: '"5个"提供明确预期，降低决策成本', dimension: '标题' },
          { factor: '标签精准', evidence: '4个标签均属高搜索量职场类目', dimension: '分发' },
        ],
        dragFactors: [
          { factor: '评论区互动不足', evidence: '评论892/点赞12400=7.2%，低于10%均值', dimension: '互动' },
        ],
        comparisonInsight: '同类型职场技巧笔记平均互动率8%，本篇16.1%属于头部水平，主要靠收藏驱动',
        nextAction: '建议在文末加互动引导问题，如"你最常用哪一招？"提升评论率',
      },
      publishedAt: '2026-08-15',
      dataCollectedAt: '2026-08-20',
      contentStatus: 'collected',
    },
    {
      id: 'w2',
      platform: 'xiaohongshu',
      contentType: 'image_text',
      title: '周末在家做的懒人甜品',
      description: '零失败的3款免烤甜品，新手也能一次成功',
      contentText: '周末不想出门？在家也能做出颜值超高的甜品！\n\n🍓 草莓慕斯杯\n- 淡奶油200ml + 炼乳30g 打发\n- 底层饼干碎 + 中层慕斯 + 顶层草莓\n- 冷藏2小时即可\n\n🥭 芒果椰汁西米露\n- 西米煮透过冷水\n- 椰浆200ml + 炼乳20g\n- 芒果切丁铺顶\n\n🍫 巧克力能量球\n- 燕麦片100g + 花生酱40g + 蜂蜜30g\n- 揉成小球冷藏定型\n- 外层裹可可粉',
      coverUrl: 'https://picsum.photos/seed/lazy-dessert/400/300',
      images: ['https://picsum.photos/seed/lazy-dessert/400/300'],
      tags: ['懒人甜品', '免烤甜品', '周末食谱', '新手烘焙'],
      url: 'https://www.xiaohongshu.com/explore/w2',
      likes: 8900,
      comments: 1200,
      shares: 1800,
      collects: 5200,
      views: 98000,
      interactionRate: 17.5,
      viralScore: 85,
      performanceTier: 'A',
      aiDiagnosis: {
        performanceReason: '评论率突出（13.5%），食谱类内容引发大量讨论和晒图',
        boostFactors: [
          { factor: '评论率远超均值', evidence: '评论1200/点赞8900=13.5%，同类均值7%', dimension: '互动' },
          { factor: '内容结构清晰', evidence: '3款甜品分步骤呈现，易跟做', dimension: '内容' },
        ],
        dragFactors: [
          { factor: '收藏率偏低', evidence: '收藏5200/浏览98000=5.3%，低于同类头部6%+', dimension: '收藏' },
          { factor: '封面吸引力不足', evidence: '点击率预估低于同类均值15%', dimension: '封面' },
        ],
        comparisonInsight: '互动强但收藏偏弱，属于"看了就聊但不太存"的类型',
        nextAction: '优化封面为成品俯拍+文字标注，提升点击率和收藏意愿',
      },
      publishedAt: '2026-08-10',
      dataCollectedAt: '2026-08-20',
      contentStatus: 'collected',
    },
    {
      id: 'w3',
      platform: 'douyin',
      contentType: 'short_video',
      title: '30秒学会手机修图调色',
      description: '一招调出日系胶片感',
      scriptText: '【开场】\n（手机录屏画面）\n看到这张普通照片吧？30秒让它变成日系胶片感。\n\n【步骤1】\n打开Snapseed，点"工具"→"调整图片"\n亮度+20 对比度-10 饱和度-15 氛围+30\n\n【步骤2】\n点"工具"→"晕影"\n外部亮度-30\n\n【步骤3】\n点"滤镜"→"复古"→选第3个\n强度调到60\n\n【结尾】\n（对比图展示）\n是不是完全不一样了？收藏这条，下次拍照直接用！',
      coverUrl: 'https://picsum.photos/seed/photo-edit/400/300',
      images: ['https://picsum.photos/seed/photo-edit/400/300'],
      tags: ['手机修图', '调色教程', '日系风格', 'Snapseed'],
      url: 'https://www.douyin.com/video/w3',
      likes: 45000,
      comments: 3200,
      shares: 12000,
      collects: 28000,
      views: 1200000,
      playCount: 1200000,
      completionRate: 68,
      interactionRate: 7.3,
      viralScore: 88,
      performanceTier: 'A',
      viralType: 'share_driven',
      aiDiagnosis: {
        performanceReason: '完播率68%+分享率1%，教程类爆款典型特征',
        boostFactors: [
          { factor: '完播率极高', evidence: '68%远超短视频均值35%', dimension: '留存' },
          { factor: '分享驱动', evidence: '分享12000/播放120万=1%，高于均值0.5%', dimension: '传播' },
        ],
        dragFactors: [
          { factor: '评论区引导不足', evidence: '评论3200/点赞45000=7.1%，互动深度可提升', dimension: '互动' },
        ],
        comparisonInsight: '完播率和分享率双高，属于"看完就转"型内容',
        nextAction: '在结尾加"你平时用什么修图APP？"引导评论，提升互动深度',
      },
      publishedAt: '2026-08-05',
      dataCollectedAt: '2026-08-20',
      contentStatus: 'collected',
    },
    {
      id: 'w4',
      platform: 'xiaohongshu',
      contentType: 'image_text',
      title: '我的租房改造记录',
      description: '2000元把出租屋变成ins风小窝',
      contentText: '搬进新租的房子，房东留下的家具又旧又丑…\n但我不想将就！预算2000，开搞！\n\n🛋️ 改造清单：\n- 奶油色墙纸 ×3面墙 ¥280\n- 仿木纹地板贴 ¥320\n- 铁艺落地灯 ¥158\n- 白色纱帘+遮光帘 ¥180\n- 地毯 160×230 ¥220\n- 挂画3幅 ¥90\n- 绿植（仿真）¥65\n- 收纳盒6个 ¥78\n- 桌布+靠垫 ¥110\n\n总计：¥1501 还剩500买花！\n\n改造前vs改造后见图👆',
      coverUrl: 'https://picsum.photos/seed/room-makeover/400/300',
      images: ['https://picsum.photos/seed/room-makeover/400/300'],
      tags: ['租房改造', 'ins风', '出租屋改造', '低成本装修'],
      url: 'https://www.xiaohongshu.com/explore/w4',
      likes: 3200,
      comments: 180,
      shares: 420,
      collects: 2100,
      views: 28000,
      interactionRate: 21.1,
      viralScore: 62,
      performanceTier: 'B',
      aiDiagnosis: {
        performanceReason: '互动率不错但总量偏低，属于"小而美"内容',
        boostFactors: [
          { factor: '互动率极高', evidence: '21.1%远超图文均值8%', dimension: '互动' },
          { factor: '内容实用', evidence: '具体价格+清单，可复制性强', dimension: '内容' },
        ],
        dragFactors: [
          { factor: '标题缺乏数字钩子', evidence: '无具体数字，点击率低于同类30%', dimension: '标题' },
          { factor: '发布时间不佳', evidence: '工作日下午发布，错过晚高峰', dimension: '分发' },
          { factor: '封面构图普通', evidence: '改造前照片作封面吸引力弱', dimension: '封面' },
        ],
        comparisonInsight: '内容质量不差但曝光不足，属于被算法低估的潜力内容',
        nextAction: '1.改标题为"2000元出租屋改造！房东看了都夸" 2.换改造后照片作封面 3.晚上8点重发',
      },
      publishedAt: '2026-08-18',
      dataCollectedAt: '2026-08-20',
      contentStatus: 'published',
    },
    {
      id: 'w5',
      platform: 'bilibili',
      contentType: 'long_video',
      title: '从零开始学Notion全攻略',
      description: '2小时带你从入门到搭建个人管理系统',
      scriptText: '【0:00-5:00】Notion是什么？为什么选它\n【5:00-25:00】基础操作：块、页面、数据库\n【25:00-50:00】进阶：关系属性与公式\n【50:00-80:00】实战：搭建个人知识库\n【80:00-100:00】实战：项目管理看板\n【100:00-120:00】模板分享与常见问题',
      coverUrl: 'https://picsum.photos/seed/notion-guide/400/300',
      images: ['https://picsum.photos/seed/notion-guide/400/300'],
      tags: ['Notion', '效率工具', '知识管理', '教程'],
      url: 'https://www.bilibili.com/video/w5',
      likes: 18000,
      comments: 4500,
      shares: 6000,
      collects: 42000,
      views: 580000,
      playCount: 580000,
      completionRate: 42,
      interactionRate: 12.2,
      viralScore: 90,
      performanceTier: 'S',
      viralType: 'collect_driven',
      aiDiagnosis: {
        performanceReason: '收藏率7.2%极高，长教程类内容的典型爆款模式',
        boostFactors: [
          { factor: '收藏率极高', evidence: '收藏42000/播放580000=7.2%，同类均值2%', dimension: '收藏' },
          { factor: '完播率优秀', evidence: '2小时视频完播42%，远超长视频均值18%', dimension: '留存' },
          { factor: '时间戳结构', evidence: '分章节时间戳降低观看门槛', dimension: '内容' },
        ],
        dragFactors: [
          { factor: '弹幕互动偏低', evidence: '弹幕密度低于同类头部30%', dimension: '互动' },
        ],
        comparisonInsight: 'B站长教程类顶流水平，收藏是核心驱动力',
        nextAction: '可拆分为系列短视频，在抖音/小红书二次分发，扩大覆盖面',
      },
      publishedAt: '2026-07-28',
      dataCollectedAt: '2026-08-20',
      contentStatus: 'published',
    },
    {
      id: 'w6',
      platform: 'kuaishou',
      contentType: 'short_video',
      title: '农村土灶做红烧肉',
      description: '奶奶的秘方，肥而不腻',
      coverUrl: 'https://picsum.photos/seed/braised-pork/400/300',
      images: ['https://picsum.photos/seed/braised-pork/400/300'],
      tags: ['农村美食', '红烧肉', '家常菜', '土灶'],
      url: 'https://www.kuaishou.com/short-video/w6',
      likes: 6200,
      comments: 380,
      shares: 560,
      collects: 1800,
      views: 85000,
      playCount: 85000,
      completionRate: 52,
      interactionRate: 10.5,
      viralScore: 55,
      performanceTier: 'C',
      aiDiagnosis: {
        performanceReason: '完播率尚可但互动和传播均低于均值，内容同质化严重',
        boostFactors: [
          { factor: '完播率合格', evidence: '52%高于短视频均值35%', dimension: '留存' },
        ],
        dragFactors: [
          { factor: '标题同质化', evidence: '"农村土灶做XX"类内容在快手超10万条', dimension: '标题' },
          { factor: '缺乏人设', evidence: '无固定出镜人物，难以形成粉丝粘性', dimension: '人设' },
          { factor: '互动引导缺失', evidence: '视频无任何互动引导话术', dimension: '互动' },
        ],
        comparisonInsight: '快手美食类竞争激烈，本条无明显差异化优势',
        nextAction: '1.打造固定人设（如"奶奶的厨房"）2.加悬念开头"这道菜我学了3年"3.结尾加互动引导',
      },
      publishedAt: '2026-08-12',
      dataCollectedAt: '2026-08-20',
      contentStatus: 'published',
    },
  ]

  async function fetchWorks() {
    isLoading.value = true
    try {
      const { listMyWorks } = await import('@/api/my_works')
      const result = await listMyWorks({ page_size: 200 })
      works.value = result.items.map(mapApiToWorkItem)
    } catch {
      try {
        const { listMyWorks } = await import('@/api/my_works')
        const result = await listMyWorks({ page_size: 200 })
        works.value = result.items.map(mapApiToWorkItem)
      } catch {
        works.value = MOCK_WORKS
      }
    } finally {
      isLoading.value = false
    }
  }

  function mapApiToWorkItem(item: any): WorkItem {
    const tier = item.is_replicated ? 'S' :
      item.performance_score != null ? (
        item.performance_score >= 0.7 ? 'A' :
        item.performance_score >= 0.4 ? 'B' : 'C'
      ) : '-'
    const noteType = item.note_type || item.content_type || 'image_text'
    const contentType = noteType === 'video' ? 'short_video' :
      noteType === 'short_video' ? 'short_video' :
      noteType === 'long_video' ? 'long_video' : 'image_text'
    const platform = item.platform || 'xiaohongshu'
    let url = ''
    if (item.note_url) url = item.note_url
    else if (platform === 'douyin' && item.note_id) url = `https://www.douyin.com/video/${item.note_id}`
    else if (platform === 'bilibili' && item.note_id) url = `https://www.bilibili.com/video/${item.note_id}`
    else if (item.published_note_id) url = `https://www.xiaohongshu.com/explore/${item.published_note_id}`
    return {
      id: item.id,
      platform,
      contentType,
      title: item.title || item.topic || '未命名',
      description: '',
      contentText: item.content_text || '',
      coverUrl: item.cover_img_url || '',
      images: Array.isArray(item.images) ? item.images : [],
      videoUrl: item.video_url || '',
      tags: Array.isArray(item.tags) ? item.tags : [],
      url,
      likes: item.collected_likes || item.likes || 0,
      comments: item.collected_comments || item.comments || 0,
      shares: item.collected_shares || item.shares || 0,
      collects: item.collected_collects || item.collects || 0,
      views: item.collected_views || item.views || 0,
      interactionRate: (item.collected_likes || item.likes) && (item.collected_collects || item.collects)
        ? (((item.collected_likes || item.likes) + (item.collected_collects || item.collects) + (item.collected_comments || item.comments || 0)) / Math.max(1, item.collected_likes || item.likes)) * 100 / 10
        : 0,
      viralScore: item.performance_score != null ? Math.round(item.performance_score * 100) : 0,
      performanceTier: tier,
      dataCollectedAt: item.collected_at || item.published_at || new Date().toISOString(),
      publishedAt: item.published_at || undefined,
      isDraft: item.content_status === 'draft',
      contentStatus: item.content_status || undefined,
      titlePattern: item.title_pattern || undefined,
      emotionTrigger: item.emotion_trigger || undefined,
      contentStructure: item.content_structure || undefined,
      cardDraft: item.card_draft || undefined,
      firstPageHtml: item.first_page_html || undefined,
    }
  }

  const worksByStatus = computed(() => {
    const draft: WorkItem[] = []
    const published: WorkItem[] = []
    const collected: WorkItem[] = []
    for (const w of works.value) {
      const status = (w as any).contentStatus as string | undefined
      if (status === 'draft' || w.isDraft) draft.push(w)
      else if (status === 'collected' || (!status && w.dataCollectedAt && !w.isDraft && !(w as any).publishedAt)) collected.push(w)
      else published.push(w)
    }
    return { draft, published, collected }
  })

  async function addWorkByLink(url: string): Promise<WorkItem> {
    const res = await authFetch('/api/my-works/collect', {
      method: 'POST',
      body: JSON.stringify({ note_url: url, platform: 'auto' }),
    })
    const data = await res.json()
    if (data.success && data.data) {
      const raw = data.data
      const mapped = mapApiToWorkItem({
        ...raw,
        published_note_id: raw.note_id,
        collected_likes: raw.likes,
        collected_collects: raw.collects,
        collected_comments: raw.comments,
        collected_shares: raw.shares,
        collected_at: new Date().toISOString(),
        published_at: new Date().toISOString(),
        content_status: 'collected',
      })
      works.value.unshift(mapped)
      return mapped
    }
    throw new Error(data.message || '采集失败')
  }

  async function diagnoseWork(workId: string) {
    const res = await authFetch(`/api/my-works/${workId}/diagnose`, {
      method: 'POST',
    })
    if (res.ok) {
      const diagnosis = await res.json()
      const idx = works.value.findIndex(w => w.id === workId)
      if (idx !== -1) {
        works.value[idx].aiDiagnosis = diagnosis
      }
      return diagnosis
    }
    throw new Error('诊断失败')
  }

  function buildWorkContext(): WorkContext | null {
    const work = activeWork.value
    if (!work) return null
    return {
      workId: work.id,
      title: work.title,
      platform: work.platform,
      contentType: work.contentType,
      performanceTier: work.performanceTier,
      contentText: work.contentText,
      scriptText: work.scriptText,
      tags: work.tags,
      cardDraft: work.cardDraft,
      metrics: {
        likes: work.likes,
        views: work.views || work.playCount || 0,
        interactionRate: work.interactionRate,
        completionRate: work.completionRate,
      },
      diagnosis: work.aiDiagnosis,
    }
  }

  const outputWorks = ref<WorkItem[]>([])
  const outputLoading = ref(false)

  async function fetchOutputWorks() {
    outputLoading.value = true
    try {
      const { listCreativeArtifacts } = await import('@/api/creativeArtifact')
      const artifacts = await listCreativeArtifacts(100)
      outputWorks.value = artifacts.map((a: any) => {
        const cardDraft = a.card_draft || undefined
        const allPageHtmls: string[] = a.all_page_htmls || []
        const firstPageHtml = a.first_page_html || (allPageHtmls.length > 0 ? allPageHtmls[0] : '')
        const images: string[] = a.page_images?.filter(Boolean) || []
        if (cardDraft?.pages?.length) {
          for (const p of cardDraft.pages) {
            const page = p as any
            if (page?.imageUrl && !images.includes(page.imageUrl)) images.push(page.imageUrl)
            if (Array.isArray(page?.pngUrls)) {
              for (const u of page.pngUrls) if (u && !images.includes(u)) images.push(u)
            }
          }
        }
        return {
          id: a.artifact_id,
          platform: 'xiaohongshu',
          contentType: 'image_text',
          title: a.title || '未命名作品',
          description: a.topic || '',
          contentText: '',
          coverUrl: a.cover_url || (images.length > 0 ? images[0] : ''),
          images,
          tags: a.tags || [],
          url: '',
          likes: 0,
          comments: 0,
          shares: 0,
          collects: 0,
          views: 0,
          interactionRate: 0,
          viralScore: 0,
          performanceTier: '-',
          dataCollectedAt: new Date(a.updated_at || Date.now()).toISOString(),
          isDraft: true,
          contentStatus: 'draft' as const,
          cardDraft,
          firstPageHtml,
          allPageHtmls,
        }
      })
    } catch {
      outputWorks.value = []
    } finally {
      outputLoading.value = false
    }
  }

  const analysisContext = ref<Record<string, any> | null>(null)

  function setAnalysisContext(data: Record<string, any> | null) {
    analysisContext.value = data
  }

  function buildAnalysisPrompt(): string | null {
    const ctx = analysisContext.value
    if (!ctx) return null
    const lines: string[] = ['[数据分析报告上下文]']
    if (ctx.overview) {
      const o = ctx.overview
      lines.push(`数据概览：共${o.total}篇内容，爆款${o.replicated}篇，高表现${o.high_performers}篇，均分${(o.avg_score * 100).toFixed(0)}分`)
    }
    if (ctx.writing_prescription) {
      const wp = ctx.writing_prescription
      if (wp.best_patterns?.length) {
        lines.push('最佳模式：' + wp.best_patterns.map((p: any) => `${p.name}(均分${(p.avg_score * 100).toFixed(0)})`).join('、'))
      }
      if (wp.avoid_patterns?.length) {
        lines.push('避坑模式：' + wp.avoid_patterns.map((p: any) => `${p.name}(均分${(p.avg_score * 100).toFixed(0)})`).join('、'))
      }
    }
    if (ctx.action_items?.length) {
      lines.push('行动建议：' + ctx.action_items.map((a: any) => a.action).join('；'))
    }
    if (ctx.platform_comparison?.length) {
      lines.push('跨平台：' + ctx.platform_comparison.map((p: any) => `${p.platform}均分${(p.avg_score * 100).toFixed(0)}爆款率${(p.replicated_rate * 100).toFixed(0)}%`).join('，'))
    }
    if (ctx.pattern_ranking?.length) {
      lines.push('标题模式排行：' + ctx.pattern_ranking.slice(0, 3).map((p: any) => `${p.name}(${p.count}篇)`).join(' > '))
    }
    if (ctx.top_performers?.length) {
      lines.push('最佳作品：' + ctx.top_performers.map((t: any) => `"${t.title}"${t.score ? (t.score * 100).toFixed(0) + '分' : ''}`).join('、'))
    }
    return lines.join('\n')
  }

  return {
    works, activeWorkId, activeWork, isLoading,
    creationNavExpanded, worksByType, worksByStatus, workSearchQuery, filteredWorks,
    analysisContext, sidebarTab, activeCreationType, showWorkDetail,
    outputWorks, outputLoading,
    setActiveWork, toggleCreationNav, createDraft, deleteWork, updateDraft, saveCardAsDraft,
    extractFirstPageHtml,
    getPlatformLabel, getContentTypeLabel, getTierColor, formatNumber,
    fetchWorks, addWorkByLink, diagnoseWork, buildWorkContext,
    fetchOutputWorks,
    setAnalysisContext, buildAnalysisPrompt,
  }
})