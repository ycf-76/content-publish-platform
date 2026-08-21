/**
 * Esther Design System 卡片模板系统
 *
 * 基于 esther-design-system 规范，提供：
 * - 3 套 esther 品牌模板（品牌三色/深色墨韵/暖阳奶白）
 * - 9 种 esther 页面类型（深色面板/尾页/对比/图标文字/步骤流程/代码面板/编号卡片/报纸多栏/大字金句）
 * - 品牌三色装饰条 + oversized 装饰数字 + 网格质感
 * - 与原有 templates.ts 完全兼容，可独立引入
 *
 * 设计来源：esther-design-system
 * - 品牌三色：主色(#2B7FD8)60% + 强调色(#F4D758)30% + 点缀色(#E84A5F)10%
 * - 暖底背景：#fefcf6(奶白) / #faf6eb(深奶)
 * - 墨色文字：#1A1A2E（非纯黑）
 * - 字体混搭：标题衬线(Noto Serif SC) + 正文无衬线(Noto Sans SC) + 装饰(Fraunces)
 * - 52种组件精选：步骤流程(#7)、代码面板(#5)、编号卡片(#34)、报纸多栏(#23)、大字金句(#38)
 */

import type { TemplateTheme, DecorationConfig, PageType, CardPage } from './templates'
import { createDefaultDecoration } from './templates'

// ===== 页面类型 =====

export type EstherPageType =
  | 'dark_panel'
  | 'end_page'
  | 'compare'
  | 'icon_text'
  | 'steps'
  | 'code_panel'
  | 'numbered_cards'
  | 'newspaper'
  | 'big_quote'

/** 完整页面类型 = PageType（已包含全部 13 种） */
export type FullPageType = PageType

/** esther 新增页面类型的中文标签 */
export const ESTHER_PAGE_TYPE_LABELS: Record<EstherPageType, string> = {
  dark_panel: '深色面板',
  end_page: '尾页',
  compare: '对比',
  icon_text: '图标文字',
  steps: '步骤流程',
  code_panel: '代码面板',
  numbered_cards: '编号卡片',
  newspaper: '报纸多栏',
  big_quote: '大字金句',
}

/** 完整页面类型标签（合并原有 + esther） */
export const FULL_PAGE_TYPE_LABELS: Record<FullPageType, string> = {
  cover: '封面',
  content: '正文',
  quote: '金句',
  list: '清单',
  ...ESTHER_PAGE_TYPE_LABELS,
}

// ===== esther 扩展 CardPage 字段 =====

/** EstherCardPage = CardPage（字段已统一，直接复用） */
export type EstherCardPage = CardPage

// ===== 品牌三色常量 =====

export const ESTHER_BRAND = {
  blue: '#2B7FD8',
  yellow: '#F4D758',
  red: '#E84A5F',
  cream: '#fefcf6',
  creamDark: '#faf6eb',
  ink: '#1A1A2E',
  inkLight: '#4A4A5A',
  inkFaint: '#8A8A9A',
} as const

export const ESTHER_TRICOLOR_GRADIENT =
  `linear-gradient(90deg, ${ESTHER_BRAND.blue} 60%, ${ESTHER_BRAND.yellow} 80%, ${ESTHER_BRAND.red} 100%)`

// ===== 3 套 esther 模板 =====

export const ESTHER_TEMPLATES: TemplateTheme[] = [
  {
    id: 'esther_brand',
    name: 'Esther品牌',
    description: '品牌三色+奶白底+衬线标题，适合知识科普、干货分享',
    bg: ESTHER_BRAND.cream,
    surface: ESTHER_BRAND.creamDark,
    text: ESTHER_BRAND.ink,
    subtext: ESTHER_BRAND.inkLight,
    accent: ESTHER_BRAND.blue,
    accentSoft: '#D6E9F8',
    fontSize: 48,
    fontFamily: "'Noto Serif SC', 'Songti SC', 'Georgia', 'PingFang SC', serif",
  },
  {
    id: 'esther_dark',
    name: 'Esther墨韵',
    description: '深色墨底+金色强调+衬线标题，适合科技、AI、编程',
    bg: ESTHER_BRAND.ink,
    surface: '#2A2A3E',
    text: '#E8E4DE',
    subtext: ESTHER_BRAND.inkFaint,
    accent: ESTHER_BRAND.yellow,
    accentSoft: '#3A3A4E',
    fontSize: 48,
    fontFamily: "'Noto Serif SC', 'Songti SC', 'Georgia', 'PingFang SC', serif",
  },
  {
    id: 'esther_warm',
    name: 'Esther暖阳',
    description: '暖奶底+橙棕强调+圆润字体，适合生活方式、美食、旅行',
    bg: '#FFF8F0',
    surface: '#FFE8D6',
    text: '#3E2F23',
    subtext: '#8B7355',
    accent: '#D97706',
    accentSoft: '#FDE68A',
    fontSize: 48,
    fontFamily: "'Noto Sans SC', 'PingFang SC', 'Microsoft YaHei', sans-serif",
  },
]

// ===== esther 专属装饰预设 =====

export const ESTHER_DECORATION_PRESETS: Array<DecorationConfig & { name: string; description: string }> = [
  {
    type: 'gradient_orbs',
    name: '品牌光斑',
    description: '品牌蓝+金渐变光斑',
    color1: ESTHER_BRAND.blue,
    color2: ESTHER_BRAND.yellow,
    opacity: 0.25,
    param1: 0.3,
    param2: 0.7,
  },
  {
    type: 'gradient_orbs',
    name: '暖日光斑',
    description: '金色+粉色暖光斑',
    color1: ESTHER_BRAND.yellow,
    color2: ESTHER_BRAND.red,
    opacity: 0.2,
    param1: 0.25,
    param2: 0.6,
  },
  {
    type: 'dots',
    name: '品牌波点',
    description: '品牌蓝波点阵列',
    color1: ESTHER_BRAND.blue,
    color2: ESTHER_BRAND.yellow,
    opacity: 0.15,
    param1: 56,
    param2: 8,
  },
  {
    type: 'wave',
    name: '品牌波浪',
    description: '品牌蓝+金波浪',
    color1: ESTHER_BRAND.blue,
    color2: ESTHER_BRAND.yellow,
    opacity: 0.18,
    param1: 3,
    param2: 45,
  },
  {
    type: 'geometric',
    name: '品牌圆弧',
    description: '品牌蓝+金圆弧色块',
    color1: ESTHER_BRAND.blue,
    color2: ESTHER_BRAND.yellow,
    opacity: 0.15,
    param1: 0.7,
    param2: 30,
  },
]

// ===== 创建 esther 新增类型的默认页面 =====

export function createEstherDefaultPage(type: EstherPageType, index: number): EstherCardPage {
  const id = `page_esther_${Date.now()}_${index}`
  switch (type) {
    case 'dark_panel':
      return {
        id, type,
        title: '核心要点',
        content: '',
        emoji: '🚀',
        decoNumber: '01',
        listItems: ['第一项关键洞察', '第二项关键洞察', '第三项关键洞察'],
      }
    case 'end_page':
      return {
        id, type,
        title: '',
        content: '一句让人记住你的话。',
        footer: '@你的小红书昵称',
        ctaText: '关注我，获取更多',
        decoNumber: '"',
      }
    case 'compare':
      return {
        id, type,
        title: '对比分析',
        content: '',
        compareLeftTitle: '传统做法',
        compareRightTitle: '新方法',
        compareLeftItems: ['效率低', '成本高', '难维护'],
        compareRightItems: ['效率高', '成本低', '易维护'],
      }
    case 'icon_text':
      return {
        id, type,
        title: '核心能力',
        content: '',
        iconTextPairs: [
          { icon: '🎯', text: '精准定位目标用户' },
          { icon: '⚡', text: '快速迭代产品方案' },
          { icon: '🔧', text: '灵活调整运营策略' },
          { icon: '📊', text: '数据驱动决策优化' },
        ],
      }
    case 'steps':
      return {
        id, type,
        title: '操作步骤',
        content: '',
        steps: [
          { title: '准备阶段', desc: '收集资料，明确目标' },
          { title: '执行阶段', desc: '按计划推进，记录过程' },
          { title: '复盘阶段', desc: '总结经验，优化流程' },
        ],
        decoNumber: '01',
      }
    case 'code_panel':
      return {
        id, type,
        title: '核心代码',
        content: '',
        codeContent: 'def hello():\n    print("Hello, World!")\n    return True',
        codeLang: 'python',
        decoNumber: '02',
      }
    case 'numbered_cards':
      return {
        id, type,
        title: '关键要点',
        content: '',
        numberedItems: [
          { title: '第一要点', desc: '简要说明这个要点的核心内容' },
          { title: '第二要点', desc: '简要说明这个要点的核心内容' },
          { title: '第三要点', desc: '简要说明这个要点的核心内容' },
        ],
        decoNumber: '03',
      }
    case 'newspaper':
      return {
        id, type,
        title: '',
        content: '',
        masthead: 'THE DAILY BRIEF',
        newspaperCols: [
          { headline: '核心发现', body: '这里放核心发现的简要描述，信息密度高，像报纸一样紧凑。' },
          { headline: '关键数据', body: '这里放关键数据支撑，用数字说话更有说服力。' },
          { headline: '行动建议', body: '这里放具体的行动建议，让读者知道下一步该做什么。' },
        ],
        decoNumber: '04',
      }
    case 'big_quote':
      return {
        id, type,
        title: '',
        content: '一句足够大的话，大到让人无法忽视。',
        footer: '@灵犀工坊',
        decoNumber: '"',
      }
  }
}

/** esther 风格默认5页（封面+步骤流程+编号卡片+大字金句+尾页） */
export function createEstherDefaultPages(): EstherCardPage[] {
  return [
    {
      id: 'page_esther_default_0',
      type: 'cover',
      title: '5个让你效率翻倍的工作法',
      subtitle: '打工人必备 · 实操验证',
      highlight: '效率翻倍',
      tag: '干货分享',
      content: '',
      footer: '@灵犀工坊',
    },
    {
      id: 'page_esther_default_1',
      type: 'steps',
      title: '三步搞定',
      steps: [
        { title: '列清单', desc: '每天早上花10分钟列出3件最重要的事' },
        { title: '番茄钟', desc: '专注25分钟，休息5分钟，4个番茄后长休' },
        { title: '周回顾', desc: '每周五回顾，砍掉无效习惯' },
      ],
      decoNumber: '01',
      content: '',
    },
    {
      id: 'page_esther_default_2',
      type: 'numbered_cards',
      title: '核心要点',
      numberedItems: [
        { title: '先完成再完美', desc: '别在细节上卡住，先跑起来' },
        { title: '二八法则', desc: '20%的投入决定80%的产出' },
        { title: '批量处理', desc: '同类任务集中做，减少切换成本' },
      ],
      decoNumber: '02',
      content: '',
    },
    {
      id: 'page_esther_default_3',
      type: 'big_quote',
      title: '',
      content: '高效不是做更多事，而是做对的事。',
      footer: '@灵犀工坊',
      decoNumber: '"',
    },
    {
      id: 'page_esther_default_4',
      type: 'end_page',
      title: '',
      content: '关注我，每周一个效率技巧。',
      footer: '@灵犀工坊',
      ctaText: '关注我，获取更多',
      decoNumber: '"',
    },
  ]
}

/** 判断是否为 esther 模板 */
export function isEstherTemplate(templateId: string): boolean {
  return ESTHER_TEMPLATES.some(t => t.id === templateId)
}

/** 判断是否为 esther 新增页面类型 */
export function isEstherPageType(type: string): type is EstherPageType {
  return type in ESTHER_PAGE_TYPE_LABELS
}