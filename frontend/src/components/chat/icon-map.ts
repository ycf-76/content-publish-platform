import {
  Brain,
  Lightbulb,
  Loader2,
  Search,
  PenLine,
  Palette,
  Rocket,
  BarChart3,
  ShieldCheck,
  Eye,
  FileText,
  Save,
  FolderSearch,
  ScanSearch,
  Beaker,
  FileCode,
  Film,
  Package,
  Scissors,
  Target,
  MessageCircle,
  Bird,
  CreditCard,
  Tag,
  ClipboardCheck,
  Send,
  Wrench,
  Users,
  UserPlus,
  Hourglass,
  Square,
  List,
  type LucideIcon,
} from 'lucide-vue-next'

export type IconEntry = { icon: LucideIcon; label: string }

const TOOL_ICON_MAP: Record<string, IconEntry> = {
  chat: { icon: MessageCircle, label: '对话' },
  trending_search: { icon: Search, label: '搜索热点' },
  viral_analysis: { icon: BarChart3, label: '分析爆款' },
  lively_girl: { icon: PenLine, label: '撰写文案' },
  elegant: { icon: PenLine, label: '撰写文案' },
  professional: { icon: PenLine, label: '撰写文案' },
  casual: { icon: PenLine, label: '撰写文案' },
  image_plan: { icon: Palette, label: '规划图片' },
  image_gen: { icon: Palette, label: '生成图片' },
  image_review: { icon: Eye, label: '审核图片' },
  content_audit: { icon: ShieldCheck, label: '审核内容' },
  file_read: { icon: FileText, label: '读取文件' },
  file_write: { icon: Save, label: '写入文件' },
  glob: { icon: FolderSearch, label: '搜索文件' },
  grep: { icon: ScanSearch, label: '搜索内容' },
  research: { icon: Search, label: '调研' },
  proposal: { icon: Lightbulb, label: '提案' },
  script: { icon: FileCode, label: '脚本' },
  scene_plan: { icon: Film, label: '分镜' },
  assets: { icon: Package, label: '素材' },
  edit: { icon: Scissors, label: '剪辑' },
  compose: { icon: Target, label: '合成' },
  spawn_agent: { icon: UserPlus, label: '派子智能体' },
  wait_agent: { icon: Hourglass, label: '等待子智能体' },
  send_message: { icon: Send, label: '发消息' },
  interrupt_agent: { icon: Square, label: '中断Agent' },
  list_agents: { icon: List, label: '列出Agent' },
}

const NODE_ICON_MAP: Record<string, IconEntry> = {
  chat: { icon: MessageCircle, label: '对话' },
  search: { icon: Search, label: '搜索爆款' },
  trending_search: { icon: Search, label: '搜索爆款' },
  analyze: { icon: BarChart3, label: '要素分析' },
  image_plan: { icon: Palette, label: '图片规划' },
  image_gen: { icon: Palette, label: '图片生成' },
  image_review: { icon: Eye, label: '图片审核' },
  copywrite: { icon: PenLine, label: '文案撰写' },
  audit: { icon: ShieldCheck, label: '合规审核' },
  content_audit: { icon: ShieldCheck, label: '合规审核' },
  cover_design: { icon: Palette, label: '封面设计' },
  tag_generation: { icon: Tag, label: '标签生成' },
  final_review: { icon: ClipboardCheck, label: '人工终审' },
  publish: { icon: Rocket, label: '发布' },
  wechat_push: { icon: Send, label: '微信推送' },
  feishu_push: { icon: Bird, label: '飞书推送' },
  card_gen: { icon: CreditCard, label: '卡片生成' },
  research: { icon: Search, label: '调研' },
  proposal: { icon: Lightbulb, label: '提案' },
  script: { icon: FileCode, label: '脚本' },
  scene_plan: { icon: Film, label: '分镜' },
  assets: { icon: Package, label: '素材' },
  edit: { icon: Scissors, label: '剪辑' },
  compose: { icon: Target, label: '合成' },
}

const DEFAULT_ENTRY: IconEntry = { icon: Wrench, label: '' }

export function getToolIcon(toolName: string): IconEntry {
  return TOOL_ICON_MAP[toolName] || { ...DEFAULT_ENTRY, label: toolName }
}

export function getNodeIcon(nodeKey: string): IconEntry {
  return NODE_ICON_MAP[nodeKey] || { ...DEFAULT_ENTRY, label: nodeKey }
}

export {
  Brain,
  Lightbulb,
  Loader2,
  Search,
  PenLine,
  Palette,
  Rocket,
  BarChart3,
  ShieldCheck,
  Eye,
  MessageCircle,
  Wrench,
}