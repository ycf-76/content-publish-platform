 import type { AgentMeta } from './cell-types'

const AGENT_NODE_LABELS: Record<string, string> = {
  search: '搜索爆款',
  trending_search: '搜索爆款',
  analyze: '要素分析',
  image_plan: '图片规划',
  image_gen: '图片生成',
  image_review: '图片审核',
  copywrite: '文案撰写',
  audit: '合规审核',
  content_audit: '合规审核',
  cover_design: '封面设计',
  final_review: '人工终审',
  publish: '发布',
  wechat_push: '微信推送',
  feishu_push: '飞书推送',
  card_gen: '卡片生成',
  tag_generation: '标签生成',
  research: '调研',
  proposal: '提案',
  script: '脚本',
  scene_plan: '分镜',
  assets: '素材',
  edit: '剪辑',
  compose: '合成',
}

export { AGENT_NODE_LABELS }

export function formatAgentOutput(output: Record<string, any>, isCodexMode = false): string {
  const INTERNAL_KEYS = new Set([
    '_token_usage', '_last_thought', '_iterations', '_duration_ms',
    '_model_used', '_message', '_error', '_awaiting_confirmation',
    '_confirmation_prompt', '_confirmation_skill', '_confirmation_arguments',
    '_awaiting_clarification', '_clarification_prompt', '_clarification_skill',
    '_clarification_arguments', '_clarification_batches',
    '_loop_state_path', '_loop_truncated', '_budget_exceeded', '_workflow_started',
  ])

  const parts: string[] = []

  if (output._message) {
    parts.push(output._message)
  }

  if (output.raw_text) {
    parts.push(output.raw_text)
  }

  if (output.title) {
    parts.push(`**${output.title}**`)
  }

  if (output.content) {
    parts.push(output.content)
  }

  if (output.summary) {
    parts.push(output.summary)
  }

  if (output.tags && Array.isArray(output.tags) && output.tags.length > 0) {
    parts.push(`标签: ${output.tags.join('、')}`)
  }

  if (output.recommendations && Array.isArray(output.recommendations)) {
    const recs = output.recommendations
      .slice(0, 5)
      .map((r: any) => `- ${r.topic_direction || r.title_template || r.direction || JSON.stringify(r)}`)
      .join('\n')
    parts.push(`### 推荐方向\n${recs}`)
  }

  if (output.key_findings && Array.isArray(output.key_findings)) {
    const findings = output.key_findings
      .map((f: any) => `- ${typeof f === 'string' ? f : f.finding || f.title || JSON.stringify(f)}`)
      .join('\n')
    parts.push(`### 关键发现\n${findings}`)
  }

  if (output.generated_copy) {
    const copy = output.generated_copy
    if (copy.title) parts.push(`**${copy.title}**`)
    if (copy.content) parts.push(copy.content)
  }

  if (output.topic && !output.generated_copy) {
    parts.push(`**主题: ${output.topic}**`)
  }

  if (output.analysis && typeof output.analysis === 'object') {
    const a = output.analysis
    const analysisParts: string[] = []
    if (a.is_topic_trend !== undefined) analysisParts.push(`趋势判断: ${a.is_topic_trend ? '是趋势' : '非趋势'}`)
    if (a.strength) analysisParts.push(`趋势强度: ${a.strength}`)
    if (a.patterns && Array.isArray(a.patterns)) {
      analysisParts.push(`爆款模式: ${a.patterns.map((p: any) => p.name || p.pattern || JSON.stringify(p)).join('、')}`)
    }
    if (a.triggers && Array.isArray(a.triggers)) {
      analysisParts.push(`触发因素: ${a.triggers.map((t: any) => t.name || t.trigger || JSON.stringify(t)).join('、')}`)
    }
    if (analysisParts.length > 0) {
      parts.push(`### 爆款分析\n${analysisParts.join('\n')}`)
    }
  }

  if (output.search_results_summary && typeof output.search_results_summary === 'string') {
    parts.push(output.search_results_summary)
  }

  const _HANDLED_KEYS = new Set([
    'raw_text', 'title', 'content', 'summary', 'tags',
    'recommendations', 'key_findings', 'generated_copy', 'analysis',
    'search_results_summary', 'topic', 'results', 'count', 'filter_stats',
    'platform',
  ])
  const userFacingKeys = Object.keys(output).filter(
    k => !INTERNAL_KEYS.has(k) && !k.startsWith('_') && !_HANDLED_KEYS.has(k)
  )
  if (parts.length === 0 && userFacingKeys.length > 0) {
    for (const key of userFacingKeys) {
      const val = output[key]
      if (val === null || val === undefined) continue
      if (typeof val === 'string') {
        parts.push(val)
      } else if (Array.isArray(val)) {
        if (val.length > 0 && typeof val[0] === 'string') {
          parts.push(val.map((v: string) => `- ${v}`).join('\n'))
        } else if (val.length > 0) {
          parts.push(val.map((v: any) => `- ${v.title || v.name || v.type || JSON.stringify(v)}`).join('\n'))
        }
      } else if (typeof val === 'object') {
        parts.push(`**${key}**: ${JSON.stringify(val, null, 2)}`)
      }
    }
  }

  if (parts.length === 0) {
    return '（处理完成）'
  }

  let result = parts.join('\n\n')

  if (isCodexMode) {
    const meta: string[] = []
    if (output._iterations) meta.push(`${output._iterations} 轮`)
    if (output._duration_ms) meta.push(`${(output._duration_ms / 1000).toFixed(1)}s`)
    if (output._model_used) meta.push(output._model_used)
    if (meta.length > 0) {
      result += `\n\n_${meta.join(' · ')}_`
    }
  }

  return result
}