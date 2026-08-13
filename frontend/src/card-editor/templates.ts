/**
 * 卡片模板系统：3 套预置模板 × 装饰层 × 4 种 page type
 *
 * 设计原则：
 * - 模板只定义"视觉骨架"（配色、字号、布局），内容由用户/LLM 填充
 * - 装饰层叠加在背景上方、文字下方，提供视觉丰富度（渐变光斑/几何/纹理等）
 * - 4 种 page type 覆盖小红书常见场景：封面/正文/金句/清单
 * - 画布固定 1080×1440（3:4），导出时 html2canvas 2x 缩放
 */

export type PageType = 'cover' | 'content' | 'quote' | 'list'

export interface CardPage {
  id: string
  type: PageType
  title: string
  subtitle?: string
  content: string
  footer?: string
  listItems?: string[]
}

export interface TemplateTheme {
  id: string
  name: string
  description: string
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

/** 3 套预置模板 */
export const TEMPLATES: TemplateTheme[] = [
  {
    id: 'minimal_white',
    name: '极简白底',
    description: '白底黑字红色点缀，适合干货清单、知识科普',
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
    bg: '#0F172A',
    surface: '#1E293B',
    text: '#F1F5F9',
    subtext: '#94A3B8',
    accent: '#10B981',
    accentSoft: '#064E3B',
    fontSize: 48,
    fontFamily: "'PingFang SC', 'JetBrains Mono', 'Microsoft YaHei', sans-serif",
  },
]

/** page type 中文标签 */
export const PAGE_TYPE_LABELS: Record<PageType, string> = {
  cover: '封面',
  content: '正文',
  quote: '金句',
  list: '清单',
}

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