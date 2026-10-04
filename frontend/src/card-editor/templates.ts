/**
 * 卡片模板系统：3 套预置模板 × 装饰层 × 13 种 page type
 *
 * 设计原则：
 * - 模板只定义"视觉骨架"（配色、字号、布局），内容由用户/LLM 填充
 * - 装饰层叠加在背景上方、文字下方，提供视觉丰富度（渐变光斑/几何/纹理等）
 * - 13 种 page type 覆盖常见场景：封面/正文/金句/清单 + 扩展 9 种
 * - 画布固定 1080×1440（3:4），导出时 html2canvas 2x 缩放
 */

export type PageType =
  | 'cover' | 'content' | 'quote' | 'list'
  | 'dark_panel' | 'end_page' | 'compare' | 'icon_text'
  | 'steps' | 'code_panel' | 'numbered_cards' | 'newspaper' | 'big_quote'
  | 'image_page' | 'qa' | 'timeline' | 'stat_card' | 'profile'

/** 文字叠加块：在图片上指定位置渲染一段文字 */
export interface TextOverlayBlock {
  id: string
  text: string
  x: number
  y: number
  width: number
  fontSize: number
  color: string
  fontWeight: 'normal' | 'bold' | '900'
  textAlign: 'left' | 'center' | 'right'
  lineHeight?: number
  backgroundColor?: string
  borderRadius?: number
  padding?: number
  letterSpacing?: number
  textShadow?: string
}

/** 文字叠加模板：预设的文字块布局方案 */
export interface TextOverlayTemplate {
  id: string
  name: string
  description: string
  thumbnail: string
  blocks: Omit<TextOverlayBlock, 'text' | 'id'>[]
}

export interface CardPage {
  id: string
  type: PageType
  title: string
  subtitle?: string
  content: string
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
  textOverlayBlocks?: TextOverlayBlock[]
  textOverlayTemplateId?: string
}

export type TemplateVariant = 'default'

export interface TemplateTheme {
  id: string
  name: string
  description: string
  variant: TemplateVariant
  bg: string
  surface: string
  text: string
  subtext: string
  accent: string
  accentSoft: string
  fontSize: number
  fontFamily: string
}

// ===== 装饰层系统 =====

/**
 * 装饰类型枚举
 * - none:       无装饰（纯色背景）
 * - gradient_orbs:  模糊渐变光斑（glassmorphism 风格）
 * - grid_lines:     细网格线（科技/数据感）
 * - dots:           波点阵列（复古/可爱）
 * - wave:           波浪曲线（流动/自然）
 * - noise:          纸张噪点纹理（手工/文艺）
 * - geometric:      几何色块（现代/大胆）
 */
export type DecorationType =
  | 'none'
  | 'gradient_orbs'
  | 'grid_lines'
  | 'dots'
  | 'wave'
  | 'noise'
  | 'geometric'

/** 装饰层配置（参数化，LLM 可输出此结构） */
export interface DecorationConfig {
  type: DecorationType
  /** 主色 1（十六进制），通常取自模板 accent 或自定义 */
  color1: string
  /** 主色 2（十六进制） */
  color2: string
  /** 透明度 0-1，控制装饰层整体强度 */
  opacity: number
  /** 装饰专属参数（各类型含义不同，见预置注释） */
  param1?: number
  param2?: number
}

/** 装饰层预置：每种类型配 2 套配色方案，共 12 套 */
export const DECORATION_PRESETS: Array<DecorationConfig & { name: string; description: string }> = [
  // --- gradient_orbs: 模糊光斑 ---
  {
    type: 'gradient_orbs',
    name: '暖光斑',
    description: '暖色模糊光斑，玻璃拟态感',
    color1: '#FDE68A',
    color2: '#FCA5A5',
    opacity: 0.35,
    param1: 0.25,   // 光斑1 x 位置（归一化 0-1）
    param2: 0.65,   // 光斑2 x 位置
  },
  {
    type: 'gradient_orbs',
    name: '冷光斑',
    description: '冷色模糊光斑，通透感',
    color1: '#93C5FD',
    color2: '#C4B5FD',
    opacity: 0.3,
    param1: 0.7,
    param2: 0.3,
  },
  // --- grid_lines: 网格线 ---
  {
    type: 'grid_lines',
    name: '细网格',
    description: '细线网格，科技/数据感',
    color1: '#94A3B8',
    color2: '#475569',
    opacity: 0.12,
    param1: 80,     // 网格间距 px
    param2: 1,      // 线宽 px
  },
  {
    type: 'grid_lines',
    name: '粗网格',
    description: '粗线网格，建筑/结构感',
    color1: '#6B7280',
    color2: '#374151',
    opacity: 0.15,
    param1: 120,
    param2: 2,
  },
  // --- dots: 波点 ---
  {
    type: 'dots',
    name: '小波点',
    description: '小圆点阵列，复古可爱',
    color1: '#F9A8D4',
    color2: '#FDE68A',
    opacity: 0.25,
    param1: 48,     // 点间距 px
    param2: 6,      // 点半径 px
  },
  {
    type: 'dots',
    name: '大波点',
    description: '大圆点阵列，波普风',
    color1: '#FB923C',
    color2: '#A78BFA',
    opacity: 0.2,
    param1: 80,
    param2: 12,
  },
  // --- wave: 波浪 ---
  {
    type: 'wave',
    name: '柔波浪',
    description: '柔和波浪曲线，流动自然',
    color1: '#7DD3FC',
    color2: '#BAE6FD',
    opacity: 0.2,
    param1: 3,      // 波浪条数
    param2: 40,     // 振幅 px
  },
  {
    type: 'wave',
    name: '叠波浪',
    description: '多层波浪，海洋/流动感',
    color1: '#6EE7B7',
    color2: '#34D399',
    opacity: 0.25,
    param1: 5,
    param2: 50,
  },
  // --- noise: 噪点纹理 ---
  {
    type: 'noise',
    name: '纸张纹理',
    description: '细噪点，纸张/手工感',
    color1: '#92400E',
    color2: '#78716C',
    opacity: 0.06,
    param1: 0.5,    // 噪点强度
    param2: 1,      // 噪点密度（1=每像素）
  },
  {
    type: 'noise',
    name: '颗粒纹理',
    description: '粗颗粒，胶片/复古感',
    color1: '#1C1917',
    color2: '#44403C',
    opacity: 0.08,
    param1: 0.8,
    param2: 2,
  },
  // --- geometric: 几何色块 ---
  {
    type: 'geometric',
    name: '圆弧色块',
    description: '大圆弧色块，现代大胆',
    color1: '#FF6B6B',
    color2: '#4ECDC4',
    opacity: 0.18,
    param1: 0.8,    // 圆弧大小（归一化）
    param2: 30,     // 旋转角度
  },
  {
    type: 'geometric',
    name: '三角色块',
    description: '三角色块拼接，锐利现代',
    color1: '#818CF8',
    color2: '#F472B6',
    opacity: 0.15,
    param1: 0.6,
    param2: -15,
  },
]

/** 装饰类型中文标签 */
export const DECORATION_TYPE_LABELS: Record<DecorationType, string> = {
  none: '无装饰',
  gradient_orbs: '渐变光斑',
  grid_lines: '网格线',
  dots: '波点',
  wave: '波浪',
  noise: '噪点纹理',
  geometric: '几何色块',
}

/** 创建默认装饰配置（无装饰） */
export function createDefaultDecoration(): DecorationConfig {
  return { type: 'none', color1: '#FDE68A', color2: '#FCA5A5', opacity: 0.3 }
}

/** 文字叠加预设模板（画布 1080×1440） */
export const TEXT_OVERLAY_TEMPLATES: TextOverlayTemplate[] = [
  {
    id: 'overlay_bottom_bar',
    name: '底部横条',
    description: '底部半透明横条 + 标题 + 副文',
    thumbnail: '⬜+底部条',
    blocks: [
      { x: 64, y: 1100, width: 952, fontSize: 56, color: '#FFFFFF', fontWeight: 'bold', textAlign: 'left', lineHeight: 1.4, backgroundColor: 'rgba(0,0,0,0.45)', borderRadius: 0, padding: 40, textShadow: '0 2px 8px rgba(0,0,0,0.5)' },
      { x: 64, y: 1220, width: 952, fontSize: 32, color: 'rgba(255,255,255,0.8)', fontWeight: 'normal', textAlign: 'left', lineHeight: 1.5, padding: 0, textShadow: '0 1px 4px rgba(0,0,0,0.4)' },
    ],
  },
  {
    id: 'overlay_center_big',
    name: '居中大字',
    description: '正中大号标题 + 下方小字',
    thumbnail: '⬜+居中大字',
    blocks: [
      { x: 80, y: 520, width: 920, fontSize: 80, color: '#FFFFFF', fontWeight: '900', textAlign: 'center', lineHeight: 1.3, textShadow: '0 4px 16px rgba(0,0,0,0.6)' },
      { x: 80, y: 780, width: 920, fontSize: 36, color: 'rgba(255,255,255,0.75)', fontWeight: 'normal', textAlign: 'center', lineHeight: 1.5, textShadow: '0 2px 6px rgba(0,0,0,0.4)' },
    ],
  },
  {
    id: 'overlay_top_tag_bottom_title',
    name: '左上标签+底部标题',
    description: '左上角分类标签 + 底部大标题',
    thumbnail: '⬜+标签+标题',
    blocks: [
      { x: 64, y: 64, width: 320, fontSize: 28, color: '#FFFFFF', fontWeight: 'bold', textAlign: 'left', backgroundColor: 'rgba(0,0,0,0.6)', borderRadius: 8, padding: 16, letterSpacing: 2 },
      { x: 64, y: 1080, width: 952, fontSize: 64, color: '#FFFFFF', fontWeight: 'bold', textAlign: 'left', lineHeight: 1.35, textShadow: '0 3px 12px rgba(0,0,0,0.5)' },
      { x: 64, y: 1240, width: 952, fontSize: 30, color: 'rgba(255,255,255,0.7)', fontWeight: 'normal', textAlign: 'left', lineHeight: 1.5, textShadow: '0 1px 4px rgba(0,0,0,0.3)' },
    ],
  },
  {
    id: 'overlay_quote_card',
    name: '语录卡片',
    description: '居中引号 + 金句 + 署名',
    thumbnail: '⬜+引号+金句',
    blocks: [
      { x: 80, y: 400, width: 920, fontSize: 120, color: 'rgba(255,255,255,0.25)', fontWeight: '900', textAlign: 'left', lineHeight: 1 },
      { x: 120, y: 560, width: 840, fontSize: 52, color: '#FFFFFF', fontWeight: 'bold', textAlign: 'center', lineHeight: 1.6, textShadow: '0 2px 8px rgba(0,0,0,0.5)' },
      { x: 120, y: 1100, width: 840, fontSize: 30, color: 'rgba(255,255,255,0.6)', fontWeight: 'normal', textAlign: 'center', lineHeight: 1.5 },
    ],
  },
  {
    id: 'overlay_word_card',
    name: '单词/术语卡',
    description: '居中大词 + 音标/释义 + 底部例句',
    thumbnail: '⬜+单词卡',
    blocks: [
      { x: 80, y: 360, width: 920, fontSize: 96, color: '#FFFFFF', fontWeight: '900', textAlign: 'center', lineHeight: 1.2, textShadow: '0 4px 16px rgba(0,0,0,0.5)' },
      { x: 80, y: 560, width: 920, fontSize: 36, color: 'rgba(255,255,255,0.7)', fontWeight: 'normal', textAlign: 'center', lineHeight: 1.5 },
      { x: 80, y: 720, width: 920, fontSize: 32, color: 'rgba(255,255,255,0.85)', fontWeight: 'normal', textAlign: 'center', lineHeight: 1.6, backgroundColor: 'rgba(0,0,0,0.3)', borderRadius: 12, padding: 32, textShadow: '0 1px 4px rgba(0,0,0,0.3)' },
    ],
  },
  {
    id: 'overlay_multi_zone',
    name: '多区域标注',
    description: '标题区 + 正文区 + 底部署名，三段式',
    thumbnail: '⬜+三段式',
    blocks: [
      { x: 64, y: 80, width: 952, fontSize: 52, color: '#FFFFFF', fontWeight: 'bold', textAlign: 'left', lineHeight: 1.35, backgroundColor: 'rgba(0,0,0,0.4)', borderRadius: 0, padding: 32, textShadow: '0 2px 6px rgba(0,0,0,0.4)' },
      { x: 64, y: 600, width: 952, fontSize: 36, color: '#FFFFFF', fontWeight: 'normal', textAlign: 'left', lineHeight: 1.6, backgroundColor: 'rgba(0,0,0,0.35)', borderRadius: 0, padding: 32, textShadow: '0 1px 4px rgba(0,0,0,0.3)' },
      { x: 64, y: 1300, width: 952, fontSize: 28, color: 'rgba(255,255,255,0.6)', fontWeight: 'normal', textAlign: 'right', lineHeight: 1.5 },
    ],
  },
]

/** 根据叠加模板ID + 用户填写的文字，生成 TextOverlayBlock[] */
export function applyOverlayTemplate(
  templateId: string,
  texts: string[],
): TextOverlayBlock[] {
  const tpl = TEXT_OVERLAY_TEMPLATES.find(t => t.id === templateId)
  if (!tpl) return []
  return tpl.blocks.map((block, i) => ({
    ...block,
    id: `overlay_${i}`,
    text: texts[i] || '',
  }))
}

/** 3 套预置模板 */
export const TEMPLATES: TemplateTheme[] = [
  {
    id: 'minimal_white',
    name: '极简白底',
    description: '白底黑字红色点缀，适合干货清单、知识科普',
    variant: 'default',
    bg: '#FFFFFF',
    surface: '#F7F8FA',
    text: '#1A1A1A',
    subtext: '#6B7280',
    accent: '#FF2442',
    accentSoft: '#FFE8EC',
    fontSize: 48,
    fontFamily: "'PingFang SC', 'Microsoft YaHei', 'Helvetica Neue', sans-serif",
  },
  {
    id: 'warm_card',
    name: '暖色卡片',
    description: '米黄底深棕字，温馨感，适合生活方式、美食、旅行',
    variant: 'default',
    bg: '#FBF6EC',
    surface: '#F0E6D2',
    text: '#4A3728',
    subtext: '#8B7355',
    accent: '#D97706',
    accentSoft: '#FDE68A',
    fontSize: 48,
    fontFamily: "'PingFang SC', 'Songti SC', 'SimSun', serif",
  },
  {
    id: 'dark_tech',
    name: '深色科技',
    description: '深蓝底白字霓虹绿点缀，适合科技、AI、编程',
    variant: 'default',
    bg: '#0F172A',
    surface: '#1E293B',
    text: '#F1F5F9',
    subtext: '#94A3B8',
    accent: '#10B981',
    accentSoft: '#064E3B',
    fontSize: 48,
    fontFamily: "'PingFang SC', 'JetBrains Mono', 'Microsoft YaHei', sans-serif",
  },
  {
    id: 'forest_green',
    name: '森林绿',
    description: '深绿底白字金色点缀，适合自然、健康、环保',
    variant: 'default',
    bg: '#1A2E1A',
    surface: '#2A3E2A',
    text: '#F0F7F0',
    subtext: '#8BAF8B',
    accent: '#D4A843',
    accentSoft: '#3A4E3A',
    fontSize: 48,
    fontFamily: "'PingFang SC', 'Songti SC', 'Microsoft YaHei', serif",
  },
  {
    id: 'sunset_orange',
    name: '落日橙',
    description: '深橙底白字暖黄点缀，适合活力、运动、美食',
    variant: 'default',
    bg: '#4A1E0A',
    surface: '#5A2E1A',
    text: '#FFF5EB',
    subtext: '#D4A87A',
    accent: '#FBBF24',
    accentSoft: '#6A3E2A',
    fontSize: 48,
    fontFamily: "'PingFang SC', 'Microsoft YaHei', 'Helvetica Neue', sans-serif",
  },
  {
    id: 'lavender',
    name: '薰衣草',
    description: '浅紫底深紫字粉色点缀，适合美妆、时尚、浪漫',
    variant: 'default',
    bg: '#F5F0FF',
    surface: '#EDE5FF',
    text: '#3B1F6E',
    subtext: '#7C5BAE',
    accent: '#E879A8',
    accentSoft: '#F0D5F5',
    fontSize: 48,
    fontFamily: "'PingFang SC', 'Microsoft YaHei', 'Georgia', sans-serif",
  },
]

/** 全量模板：默认 6 套 */
export const ALL_TEMPLATES: TemplateTheme[] = [...TEMPLATES]

/** page type 中文标签 */
export const PAGE_TYPE_LABELS: Record<PageType, string> = {
  cover: '封面',
  content: '正文',
  quote: '金句',
  list: '清单',
  dark_panel: '深色面板',
  end_page: '尾页',
  compare: '对比',
  icon_text: '图标文字',
  steps: '步骤流程',
  code_panel: '代码面板',
  numbered_cards: '编号卡片',
  newspaper: '报纸多栏',
  big_quote: '大字金句',
  image_page: '图片页',
  qa: '问答',
  timeline: '时间轴',
  stat_card: '数据卡片',
  profile: '人物介绍',
}

export type FullPageType = PageType
export const FULL_PAGE_TYPE_LABELS: Record<string, string> = { ...PAGE_TYPE_LABELS }

/** 创建默认页面（用于"添加页面"按钮） */
export function createDefaultPage(type: PageType, index: number): CardPage {
  const id = `page_${Date.now()}_${index}`
  switch (type) {
    case 'cover':
      return {
        id, type,
        title: '点击编辑标题',
        subtitle: '副标题（可选）',
        content: '',
        footer: '@你的小红书昵称',
      }
    case 'content':
      return {
        id, type,
        title: '本页小标题',
        content: '这里是正文内容，支持多段。点击右侧编辑框修改文字。\n\n第二段正文，说明你的观点或方法。',
        footer: '',
      }
    case 'quote':
      return {
        id, type,
        title: '',
        content: '一句戳中读者的话，放在这里作为金句。',
        footer: '— 出处',
      }
    case 'list':
      return {
        id, type,
        title: '清单标题',
        content: '',
        listItems: ['第一项要点', '第二项要点', '第三项要点'],
        footer: '',
      }
    case 'dark_panel':
      return {
        id, type,
        title: '核心洞察',
        content: '',
        emoji: '💡',
        decoNumber: '01',
        listItems: ['洞察一', '洞察二', '洞察三'],
      }
    case 'end_page':
      return {
        id, type,
        title: '',
        content: '一句让人记住你的话',
        ctaText: '关注我，获取更多',
        footer: '@灵犀工坊',
        decoNumber: '"',
      }
    case 'compare':
      return {
        id, type,
        title: '对比分析',
        content: '',
        compareLeftTitle: '传统做法',
        compareRightTitle: '更好方式',
        compareLeftItems: ['痛点一', '痛点二'],
        compareRightItems: ['优势一', '优势二'],
      }
    case 'icon_text':
      return {
        id, type,
        title: '能力卡片',
        content: '',
        iconTextPairs: [
          { icon: '🎯', text: '精准定位' },
          { icon: '💡', text: '创新思维' },
          { icon: '⚡', text: '高效执行' },
          { icon: '🔥', text: '热情驱动' },
        ],
      }
    case 'steps':
      return {
        id, type,
        title: '操作步骤',
        content: '',
        decoNumber: '01',
        steps: [
          { title: '第一步', desc: '操作描述' },
          { title: '第二步', desc: '操作描述' },
          { title: '第三步', desc: '操作描述' },
        ],
      }
    case 'code_panel':
      return {
        id, type,
        title: '代码示例',
        content: '',
        codeContent: 'console.log("Hello World")',
        codeLang: 'javascript',
      }
    case 'numbered_cards':
      return {
        id, type,
        title: '核心要点',
        content: '',
        decoNumber: '01',
        numberedItems: [
          { title: '要点一', desc: '详细描述' },
          { title: '要点二', desc: '详细描述' },
          { title: '要点三', desc: '详细描述' },
        ],
      }
    case 'newspaper':
      return {
        id, type,
        title: '',
        content: '',
        masthead: 'THE DAILY BRIEF',
        newspaperCols: [
          { headline: '栏目标题一', body: '栏目正文内容' },
          { headline: '栏目标题二', body: '栏目正文内容' },
        ],
      }
    case 'big_quote':
      return {
        id, type,
        title: '',
        content: '一句震撼人心的话',
        footer: '@灵犀工坊',
        decoNumber: '"',
      }
    case 'image_page':
      return {
        id, type,
        title: '',
        content: '',
        imageUrl: '',
        footer: '',
      }
     case 'qa':
      return {
        id, type,
        title: '常见问题',
        content: '',
        qaPairs: [
          { q: '第一个问题是什么？', a: '这里是回答。' },
          { q: '第二个问题是什么？', a: '这里是回答。' },
          { q: '第三个问题是什么？', a: '这里是回答。' },
        ],
      }
    case 'timeline':
      return {
        id, type,
        title: '发展历程',
        content: '',
        timelineItems: [
          { date: '2024.01', event: '里程碑事件一' },
          { date: '2024.06', event: '里程碑事件二' },
          { date: '2025.01', event: '里程碑事件三' },
        ],
      }
    case 'stat_card':
      return {
        id, type,
        title: '关键数据',
        content: '',
        statItems: [
          { value: '10万+', label: '用户数', unit: '' },
          { value: '99.9', label: '可用性', unit: '%' },
          { value: '3秒', label: '响应时间', unit: '' },
        ],
      }
    case 'profile':
      return {
        id, type,
        title: '',
        content: '',
        name: '作者名称',
        role: '职业/标签',
        bio: '一段简短的自我介绍，让读者了解你。',
        avatarUrl: '',
      }
  }
}

/** 默认 4 张卡片（封面 + 正文 + 金句 + 清单），让用户打开就能看到效果 */
export function createDefaultPages(): CardPage[] {
  return [
    {
      id: 'page_default_0',
      type: 'cover',
      title: '独居打工人一周快手早餐',
      subtitle: '7 天不重样 · 15 分钟搞定',
      content: '',
      footer: '@灵犀工坊',
    },
    {
      id: 'page_default_1',
      type: 'content',
      title: '为什么坚持做早餐',
      content: '独居不代表凑合。一份热乎的早餐，是一天里唯一完全属于自己的仪式感。\n\n提前备料 + 周末批量采购，工作日 15 分钟就能端上桌。',
      footer: '',
    },
    {
      id: 'page_default_2',
      type: 'quote',
      title: '',
      content: '好好吃早餐，是对生活最基本的尊重。',
      footer: '— 一个独居五年的打工人',
    },
    {
      id: 'page_default_3',
      type: 'list',
      title: '本周菜单速览',
      content: '',
      listItems: [
        '周一：番茄鸡蛋三明治 + 燕麦拿铁',
        '周二：香蕉松饼 + 黑咖',
        '周三：蔬菜粥 + 水煮蛋',
        '周四：牛油果吐司 + 豆浆',
      ],
      footer: '详细做法见后续笔记',
    },
  ]
}