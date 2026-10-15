<template>
  <div style="display:flex;flex-direction:column;gap:16px;color:#374151;">
    <!-- ═══════════ 监控面板：反馈统计 ═══════════ -->
    <div>
      <h3 style="margin:0 0 10px;color:#1A1A1A;font-size:14px;font-weight:600;">任务监控（近 7 天）</h3>
      <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px;">
        <div style="background:#F9FAFB;border-radius:10px;padding:12px 14px;">
          <div style="color:#9CA3AF;font-size:12px;margin-bottom:4px;">点赞</div>
          <div style="color:#059669;font-size:22px;font-weight:700;font-variant-numeric:tabular-nums;">{{ stats?.likes ?? '—' }}</div>
        </div>
        <div style="background:#F9FAFB;border-radius:10px;padding:12px 14px;">
          <div style="color:#9CA3AF;font-size:12px;margin-bottom:4px;">点踩</div>
          <div style="color:#DC2626;font-size:22px;font-weight:700;font-variant-numeric:tabular-nums;">{{ stats?.dislikes ?? '—' }}</div>
        </div>
        <div style="background:#F9FAFB;border-radius:10px;padding:12px 14px;">
          <div style="color:#9CA3AF;font-size:12px;margin-bottom:4px;">重试</div>
          <div style="color:#D97706;font-size:22px;font-weight:700;font-variant-numeric:tabular-nums;">{{ stats?.retries ?? '—' }}</div>
        </div>
        <div style="background:#F9FAFB;border-radius:10px;padding:12px 14px;">
          <div style="color:#9CA3AF;font-size:12px;margin-bottom:4px;">重试率</div>
          <div style="color:#1A1A1A;font-size:22px;font-weight:700;font-variant-numeric:tabular-nums;">
            {{ stats ? (stats.retry_rate * 100).toFixed(1) + '%' : '—' }}
          </div>
        </div>
      </div>
      <div v-if="stats && Object.keys(stats.dislike_dimensions).length" style="margin-top:8px;display:flex;flex-wrap:wrap;gap:6px;align-items:center;">
        <span style="color:#9CA3AF;font-size:12px;">被踩维度：</span>
        <span v-for="(count, dim) in stats.dislike_dimensions" :key="dim"
          style="padding:2px 10px;background:#FEF2F2;color:#DC2626;font-size:12px;border-radius:10px;">
          {{ dim }} × {{ count }}
        </span>
      </div>
    </div>

    <!-- ═══════════ 进化建议列表 ═══════════ -->
    <div>
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px;">
        <h3 style="margin:0;color:#1A1A1A;font-size:14px;font-weight:600;">
          进化建议
          <span v-if="pendingCount > 0" style="margin-left:6px;padding:1px 8px;background:#FEF3C7;color:#D97706;font-size:11px;border-radius:10px;font-weight:500;">
            {{ pendingCount }} 条待人审
          </span>
        </h3>
        <div style="display:flex;gap:4px;">
          <button v-for="f in statusFilters" :key="f.value || 'all'"
            @click="activeFilter = f.value"
            :style="{
              padding: '5px 12px', border: 'none', borderRadius: '6px', fontSize: '12px', cursor: 'pointer',
              background: activeFilter === f.value ? '#1A1A1A' : '#F3F4F6',
              color: activeFilter === f.value ? '#FFFFFF' : '#6B7280',
            }">
            {{ f.label }}
          </button>
        </div>
      </div>

      <div v-if="loading" style="padding:24px;text-align:center;color:#9CA3AF;font-size:13px;">加载中…</div>
      <div v-else-if="!proposals.length" style="padding:32px 24px;text-align:center;background:#F9FAFB;border-radius:10px;">
        <div style="color:#9CA3AF;font-size:13px;">暂无进化建议</div>
        <div style="color:#C4C4C4;font-size:12px;margin-top:4px;">工作流出错或收到点踩后，智能体会自动复盘生成改进建议</div>
      </div>

      <div v-else style="display:flex;flex-direction:column;gap:8px;">
        <div v-for="p in proposals" :key="p.id"
          @click="openDetail(p)"
          style="display:flex;align-items:center;gap:12px;padding:12px 14px;background:#FFFFFF;border:1px solid #EDEDED;border-radius:10px;cursor:pointer;transition:border-color 0.15s;"
          @mouseenter="($event.currentTarget as HTMLElement).style.borderColor='#3B6CF6'"
          @mouseleave="($event.currentTarget as HTMLElement).style.borderColor='#EDEDED'">
          <span :style="{
            flexShrink: 0, display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
            width: '34px', height: '34px', borderRadius: '8px', fontSize: '16px',
            background: triggerMeta[p.trigger_source]?.bg || '#F3F4F6',
          }">{{ triggerMeta[p.trigger_source]?.icon || '🤖' }}</span>
          <div style="flex:1;min-width:0;">
            <div style="display:flex;align-items:center;gap:8px;">
              <span :style="{
                padding: '1px 8px', fontSize: '11px', borderRadius: '10px', fontWeight: 500,
                ...statusStyle[p.status],
              }">{{ statusLabel[p.status] || p.status }}</span>
              <span style="color:#9CA3AF;font-size:11px;">{{ triggerMeta[p.trigger_source]?.label || p.trigger_source }}</span>
            </div>
            <div style="margin-top:3px;color:#1A1A1A;font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">
              {{ p.trigger_reason }}
            </div>
          </div>
          <span style="flex-shrink:0;color:#C4C4C4;font-size:11px;">{{ formatTime(p.created_at) }}</span>
        </div>

        <div v-if="total > proposals.length" style="padding:8px;text-align:center;">
          <button @click="loadMore"
            style="padding:6px 20px;border:1px solid #E5E7EB;background:#FFFFFF;color:#6B7280;font-size:12px;cursor:pointer;border-radius:6px;">
            加载更多（{{ proposals.length }}/{{ total }}）
          </button>
        </div>
      </div>
    </div>

    <!-- ═══════════ 详情人审弹层 ═══════════ -->
    <div v-if="detail" style="position:fixed;inset:0;z-index:10010;background:rgba(0,0,0,0.35);display:flex;align-items:center;justify-content:center;" @click.self="detail = null">
      <div style="width:640px;max-width:90vw;max-height:80vh;background:#FFFFFF;border-radius:14px;display:flex;flex-direction:column;overflow:hidden;box-shadow:0 20px 60px rgba(0,0,0,0.2);">
        <div style="padding:14px 20px;border-bottom:1px solid #EDEDED;display:flex;align-items:center;gap:10px;flex-shrink:0;">
          <span style="color:#1A1A1A;font-size:15px;font-weight:600;">复盘分析报告</span>
          <span :style="{ padding: '1px 8px', fontSize: '11px', borderRadius: '10px', fontWeight: 500, ...statusStyle[detail.status] }">
            {{ statusLabel[detail.status] || detail.status }}
          </span>
          <span style="flex:1;"></span>
          <button @click="detail = null" style="border:none;background:transparent;color:#9CA3AF;font-size:18px;cursor:pointer;line-height:1;">×</button>
        </div>

        <div style="flex:1;overflow-y:auto;padding:16px 20px;">
          <div style="margin-bottom:12px;padding:10px 12px;background:#F9FAFB;border-radius:8px;font-size:12px;color:#6B7280;">
            <div style="margin-bottom:2px;">触发原因：{{ detail.trigger_reason }}</div>
            <div v-if="detail.workflow_id">工作流：{{ detail.workflow_id }}</div>
          </div>
          <div v-if="detailLoading" style="padding:24px;text-align:center;color:#9CA3AF;font-size:13px;">报告加载中…</div>
          <div v-else-if="detailHtml" class="evolution-md" v-html="detailHtml"></div>
          <div v-else style="padding:24px;text-align:center;color:#9CA3AF;font-size:13px;">（无建议内容）</div>
        </div>

        <div v-if="detail.status === 'pending_review'" style="padding:12px 20px;border-top:1px solid #EDEDED;display:flex;gap:10px;flex-shrink:0;">
          <input v-model="reviewComment" placeholder="审核备注（拒绝时建议填写原因，可选）"
            style="flex:1;padding:8px 12px;border:1px solid #E5E7EB;border-radius:8px;font-size:13px;outline:none;" />
          <button @click="review('reject')" :disabled="reviewing"
            style="padding:8px 18px;border:1px solid #FCA5A5;background:#FFFFFF;color:#DC2626;font-size:13px;font-weight:500;cursor:pointer;border-radius:8px;">
            {{ reviewing ? '…' : '拒绝' }}
          </button>
          <button @click="review('approve')" :disabled="reviewing"
            style="padding:8px 18px;border:none;background:#059669;color:#FFFFFF;font-size:13px;font-weight:500;cursor:pointer;border-radius:8px;">
            {{ reviewing ? '…' : '批准转正' }}
          </button>
        </div>
        <div v-else-if="detail.reviewed_at" style="padding:10px 20px;border-top:1px solid #EDEDED;color:#9CA3AF;font-size:12px;">
          已于 {{ formatTime(detail.reviewed_at) }} 完成人审{{ detail.review_comment ? `：${detail.review_comment}` : '' }}
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import {
  listEvolutionProposals,
  getEvolutionProposal,
  reviewEvolutionProposal,
  type EvolutionProposal,
  type EvolutionProposalStatus,
} from '@/api/evolution'
import { getFeedbackStats, type FeedbackStats } from '@/api/feedback'
import { renderMarkdown } from '@/components/chat/markdown-renderer'

const stats = ref<FeedbackStats | null>(null)
const proposals = ref<EvolutionProposal[]>([])
const total = ref(0)
const loading = ref(true)
const activeFilter = ref<EvolutionProposalStatus | null>(null)
const PAGE_SIZE = 20

const detail = ref<EvolutionProposal | null>(null)
const detailHtml = ref('')
const detailLoading = ref(false)
const reviewing = ref(false)
const reviewComment = ref('')

const pendingCount = computed(() => proposals.value.filter(p => p.status === 'pending_review').length)

const statusFilters = [
  { label: '全部', value: null as EvolutionProposalStatus | null },
  { label: '待人审', value: 'pending_review' as EvolutionProposalStatus },
  { label: '已批准', value: 'approved' as EvolutionProposalStatus },
  { label: '已拒绝', value: 'rejected' as EvolutionProposalStatus },
]

const triggerMeta: Record<string, { icon: string; label: string; bg: string }> = {
  auto_error: { icon: '❌', label: '出错自动复盘', bg: '#FEE2E2' },
  auto_dislike: { icon: '👎', label: '点踩自动复盘', bg: '#FEF3C7' },
  auto_suspended: { icon: '⏰', label: '挂起自动复盘', bg: '#E0E7FF' },
  manual: { icon: '🙋', label: '手动复盘', bg: '#ECFDF5' },
}

const statusLabel: Record<string, string> = {
  pending_review: '待人审',
  approved: '已批准',
  rejected: '已拒绝',
}

const statusStyle: Record<string, { background: string; color: string }> = {
  pending_review: { background: '#FEF3C7', color: '#D97706' },
  approved: { background: '#ECFDF5', color: '#059669' },
  rejected: { background: '#F3F4F6', color: '#9CA3AF' },
}

function formatTime(iso: string): string {
  try {
    const d = new Date(iso)
    const pad = (n: number) => String(n).padStart(2, '0')
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
  } catch {
    return iso
  }
}

async function loadProposals(reset = true) {
  loading.value = true
  try {
    const offset = reset ? 0 : proposals.value.length
    const result = await listEvolutionProposals({
      status: activeFilter.value,
      limit: PAGE_SIZE,
      offset,
    })
    if (result) {
      total.value = result.total
      proposals.value = reset ? result.items : [...proposals.value, ...result.items]
    } else if (reset) {
      proposals.value = []
      total.value = 0
    }
  } finally {
    loading.value = false
  }
}

function loadMore() {
  loadProposals(false)
}

async function openDetail(p: EvolutionProposal) {
  detail.value = p
  detailHtml.value = ''
  detailLoading.value = true
  reviewComment.value = ''
  try {
    const full = await getEvolutionProposal(p.id)
    if (full) {
      detail.value = full
      detailHtml.value = full.suggestion_md ? renderMarkdown(full.suggestion_md) : ''
    }
  } finally {
    detailLoading.value = false
  }
}

async function review(decision: 'approve' | 'reject') {
  if (!detail.value) return
  if (decision === 'reject' && !reviewComment.value.trim() && !confirm('未填写拒绝原因，确定直接拒绝吗？')) return
  reviewing.value = true
  try {
    const result = await reviewEvolutionProposal(detail.value.id, decision, reviewComment.value.trim() || undefined)
    if (result.ok) {
      const idx = proposals.value.findIndex(x => x.id === detail.value?.id)
      if (idx !== -1 && result.status) proposals.value[idx].status = result.status
      if (detail.value && result.status) detail.value.status = result.status
    } else {
      alert(result.message || '审核失败，请重试')
    }
  } finally {
    reviewing.value = false
  }
}

async function loadStats() {
  stats.value = await getFeedbackStats(7)
}

onMounted(() => {
  loadStats()
  loadProposals()
})
</script>

<style scoped>
.evolution-md {
  color: #374151;
  font-size: 13px;
  line-height: 1.7;
}
.evolution-md :deep(h2) {
  margin: 0 0 10px;
  color: #1A1A1A;
  font-size: 15px;
  font-weight: 600;
}
.evolution-md :deep(h3) {
  margin: 14px 0 6px;
  color: #1A1A1A;
  font-size: 13.5px;
  font-weight: 600;
}
.evolution-md :deep(ul),
.evolution-md :deep(ol) {
  margin: 4px 0;
  padding-left: 20px;
}
.evolution-md :deep(li) {
  margin: 3px 0;
}
.evolution-md :deep(strong) {
  color: #1A1A1A;
}
</style>
