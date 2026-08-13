<template>
  <div class="wf-group-summary" :class="{ 'is-expanded': expanded }">
    <!-- 摘要条（始终可见） -->
    <button
      class="wf-summary-bar"
      type="button"
      @click="toggle"
      :aria-expanded="expanded"
    >
      <span class="wf-summary-icon">
        <CheckCircle2 v-if="allDone" />
        <Loader2 v-else-if="hasRunning" class="wf-spin" />
        <Info v-else />
      </span>
      <span class="wf-summary-text">
        来自<strong>{{ groupName }}</strong>
        <template v-if="summaryText">：{{ summaryText }}</template>
      </span>
      <span class="wf-summary-chips">
        <span
          v-for="n in nodes"
          :key="n.key"
          class="wf-summary-chip"
          :class="`is-${n.state}`"
        >
          {{ n.label }}
          <Check v-if="n.state === 'done'" class="wf-chip-icon" />
        </span>
      </span>
      <span class="wf-summary-toggle">
        {{ expanded ? '收起' : '展开' }}
        <ChevronDown class="wf-toggle-icon" :class="{ 'is-up': expanded }" />
      </span>
    </button>

    <!-- 展开后的详情区（插槽由父组件提供节点卡片内容） -->
    <transition name="wf-summary-expand">
      <div v-if="expanded" class="wf-summary-detail">
        <slot>
          <!-- 默认：展示每个节点的输出摘要 -->
          <div
            v-for="n in nodes"
            :key="n.key"
            class="wf-detail-node"
          >
            <div class="wf-detail-node-head">
              <span class="wf-detail-node-num">{{ n.num }}</span>
              <span class="wf-detail-node-name">{{ n.label }}</span>
              <span class="wf-detail-node-status" :class="`is-${n.state}`">{{ n.statusText }}</span>
            </div>
            <div class="wf-detail-node-body">{{ n.detail || '暂无输出' }}</div>
          </div>
        </slot>
      </div>
    </transition>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { Check, CheckCircle2, Loader2, Info, ChevronDown } from 'lucide-vue-next'

interface NodeInfo {
  key: string
  num: string
  label: string
  state: 'done' | 'running' | 'pending' | 'error'
  statusText: string
  detail?: string
}

const props = defineProps<{
  groupName: string
  nodes: NodeInfo[]
  summaryText?: string
  defaultExpanded?: boolean
}>()

const expanded = ref(props.defaultExpanded ?? false)

const allDone = computed(() => props.nodes.length > 0 && props.nodes.every(n => n.state === 'done'))
const hasRunning = computed(() => props.nodes.some(n => n.state === 'running'))

function toggle() {
  expanded.value = !expanded.value
}
</script>

<style scoped>
.wf-group-summary {
  flex-shrink: 0;
}
.wf-summary-bar {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  background: #FFF1F3;
  border: 1px solid #FFCDD5;
  border-radius: 8px;
  cursor: pointer;
  font-family: inherit;
  transition: background 0.15s ease, border-color 0.15s ease;
  text-align: left;
}
.wf-summary-bar:hover {
  background: #FFE4E8;
  border-color: #FF9AA7;
}
.wf-summary-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  color: #FF2442;
  flex-shrink: 0;
}
.wf-summary-icon svg {
  width: 16px;
  height: 16px;
}
.wf-summary-text {
  flex: 1;
  font-size: 15px;
  color: #4B5563;
  line-height: 1.4;
  min-width: 0;
}
.wf-summary-text strong {
  color: #333333;
  font-weight: 600;
}
.wf-summary-chips {
  display: flex;
  gap: 6px;
  flex-shrink: 0;
  flex-wrap: wrap;
}
.wf-summary-chip {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: 14px;
  padding: 2px 8px;
  background: #fff;
  border: 1px solid #E5E7EB;
  border-radius: 999px;
  color: #6B7280;
}
.wf-summary-chip.is-done {
  color: #10B981;
  border-color: #A7F3D0;
  background: #ECFDF5;
}
.wf-summary-chip.is-running {
  color: #FF2442;
  border-color: #FFCDD5;
  background: #FFF1F3;
}
.wf-summary-chip.is-error {
  color: #EF4444;
  border-color: #FECACA;
  background: #FEF2F2;
}
.wf-chip-icon {
  width: 10px;
  height: 10px;
}
.wf-summary-toggle {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: 14px;
  color: #FF2442;
  flex-shrink: 0;
  font-weight: 500;
}
.wf-toggle-icon {
  width: 12px;
  height: 12px;
  transition: transform 0.2s ease;
}
.wf-toggle-icon.is-up {
  transform: rotate(180deg);
}

.wf-spin {
  animation: wf-spin 1s linear infinite;
}
@keyframes wf-spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

/* 展开详情区 */
.wf-summary-detail {
  margin-top: 8px;
  padding: 12px 14px;
  background: #fff;
  border: 1px solid #E5E7EB;
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.wf-detail-node {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.wf-detail-node-head {
  display: flex;
  align-items: center;
  gap: 8px;
}
.wf-detail-node-num {
  font-size: 15px;
  font-weight: 600;
  color: #FF2442;
  background: #FFF1F3;
  padding: 1px 6px;
  border-radius: 999px;
}
.wf-detail-node-name {
  font-size: 15px;
  font-weight: 600;
  color: #333333;
}
.wf-detail-node-status {
  font-size: 15px;
  padding: 1px 7px;
  border-radius: 999px;
  border: 1px solid #E5E7EB;
  color: #6B7280;
  margin-left: auto;
}
.wf-detail-node-status.is-done { color: #10B981; border-color: #A7F3D0; background: #ECFDF5; }
.wf-detail-node-status.is-running { color: #FF2442; border-color: #FFCDD5; background: #FFF1F3; }
.wf-detail-node-status.is-error { color: #EF4444; border-color: #FECACA; background: #FEF2F2; }
.wf-detail-node-body {
  font-size: 14px;
  color: #6B7280;
  line-height: 1.5;
  padding-left: 28px;
}

/* 展开过渡动画 */
.wf-summary-expand-enter-active,
.wf-summary-expand-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}
.wf-summary-expand-enter-from,
.wf-summary-expand-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}
</style>