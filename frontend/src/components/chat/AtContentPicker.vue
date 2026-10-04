<template>
  <div class="at-picker" v-if="visible" @click.stop>
    <div class="at-picker-header">
      <input
        v-model="filter"
        class="at-picker-filter"
        placeholder="搜索内容…"
        ref="filterRef"
        @keydown.down.prevent="moveSelection(1)"
        @keydown.up.prevent="moveSelection(-1)"
        @keydown.enter.prevent="confirmSelection()"
        @keydown.escape.prevent="$emit('close')"
      />
    </div>
    <div class="at-picker-groups">
      <div v-for="group in filteredGroups" :key="group.key" class="at-group">
        <div class="at-group-label">{{ group.label }}</div>
        <button
          v-for="item in group.items"
          :key="item.id"
          class="at-item"
          :class="{ 'at-item-active': item.id === activeId }"
          @click="onSelect(group.key, item)"
          @mouseenter="activeId = item.id"
        >
          <component :is="group.icon" :size="13" :stroke-width="1.8" class="at-item-icon" />
          <span class="at-item-label">{{ item.label }}</span>
          <span class="at-item-hint" v-if="item.hint">{{ item.hint }}</span>
        </button>
        <div v-if="group.items.length === 0" class="at-group-empty">暂无</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted } from 'vue'
import {
  FileText, TrendingUp, Globe, Flame, Brain, BookOpen, Bot
} from 'lucide-vue-next'
import { useWorkStore } from '@/stores/work'
import { useChatContextStore } from '@/stores/chatContext'

interface AgentItem {
  agent_id: string
  role: string
}

const props = defineProps<{
  visible: boolean
  agents?: AgentItem[]
}>()

const emit = defineEmits<{
  select: [type: string, item: any]
  close: []
}>()

const workStore = useWorkStore()
const ctxStore = useChatContextStore()

const filter = ref('')
const filterRef = ref<HTMLInputElement | null>(null)
const activeId = ref('')

watch(() => props.visible, (v) => {
  if (v) {
    filter.value = ''
    activeId.value = ''
    nextTick(() => filterRef.value?.focus())
  }
})

interface AtItem {
  id: string
  label: string
  hint?: string
  data: any
}

interface AtGroup {
  key: string
  label: string
  icon: any
  items: AtItem[]
}

const filteredGroups = computed<AtGroup[]>(() => {
  const q = filter.value.toLowerCase().trim()

  const works: AtItem[] = workStore.works
    .filter(w => !q || (w.title || '').toLowerCase().includes(q))
    .slice(0, 8)
    .map(w => ({
      id: `work-${w.id}`,
      label: w.title || '未命名作品',
      hint: workStore.getPlatformLabel(w.platform),
      data: w,
    }))

  const memories: AtItem[] = ctxStore.styleMemories
    .filter(m => !q || m.content.toLowerCase().includes(q))
    .slice(0, 5)
    .map(m => ({
      id: `mem-${m.id}`,
      label: m.content,
      hint: m.source === 'ai-auto' ? 'AI' : '你',
      data: m,
    }))

  const hotItems: AtItem[] = !q ? [
    { id: 'hot-trending', label: '当前热点趋势', hint: '实时', data: { type: 'trending' } },
    { id: 'hot-topics', label: '热门话题', hint: '实时', data: { type: 'topics' } },
  ] : []

  const ruleItems: AtItem[] = !q ? [
    { id: 'rule-xhs', label: '小红书创作规范', hint: '平台', data: { type: 'xhs_rule' } },
    { id: 'rule-dy', label: '抖音创作规范', hint: '平台', data: { type: 'dy_rule' } },
  ] : []

  const agentItems: AtItem[] = (props.agents || [])
    .filter(a => a.agent_id !== 'chat_agent')
    .filter(a => !q || a.agent_id.toLowerCase().includes(q) || (a.role || '').toLowerCase().includes(q))
    .slice(0, 8)
    .map(a => ({
      id: `agent-${a.agent_id}`,
      label: a.role || a.agent_id,
      hint: a.agent_id,
      data: a,
    }))

  const groups: AtGroup[] = [
    { key: 'agent', label: '智能体', icon: Bot, items: agentItems },
    { key: 'work', label: '笔记 / 作品', icon: FileText, items: works },
    { key: 'hot', label: '热点', icon: Flame, items: hotItems },
    { key: 'memory', label: '风格记忆', icon: Brain, items: memories },
    { key: 'rule', label: '创作规范', icon: BookOpen, items: ruleItems },
  ]

  return groups
})

function moveSelection(dir: number) {
  const all = filteredGroups.value.flatMap(g => g.items)
  if (all.length === 0) return
  const idx = all.findIndex(i => i.id === activeId.value)
  const next = Math.max(0, Math.min(all.length - 1, idx + dir))
  activeId.value = all[next].id
}

function confirmSelection() {
  if (!activeId.value) return
  for (const group of filteredGroups.value) {
    const item = group.items.find(i => i.id === activeId.value)
    if (item) {
      onSelect(group.key, item)
      return
    }
  }
}

function onSelect(groupKey: string, item: AtItem) {
  emit('select', groupKey, item.data)
}
</script>

<style scoped>
.at-picker {
  position: absolute;
  bottom: 100%;
  left: 0;
  right: 0;
  max-height: 280px;
  background: #fff;
  border: 1px solid rgba(0,0,0,0.1);
  border-radius: 10px;
  box-shadow: 0 4px 16px rgba(0,0,0,0.1);
  overflow-y: auto;
  z-index: 100;
  scrollbar-width: thin;
  scrollbar-color: rgba(0,0,0,0.12) transparent;
}
.at-picker::-webkit-scrollbar { width: 4px; }
.at-picker::-webkit-scrollbar-thumb { background: rgba(0,0,0,0.12); border-radius: 2px; }

.at-picker-header {
  padding: 8px 10px;
  border-bottom: 1px solid rgba(0,0,0,0.06);
  position: sticky;
  top: 0;
  background: #fff;
  z-index: 1;
}
.at-picker-filter {
  width: 100%;
  font-size: 12px;
  padding: 5px 8px;
  border: 1px solid rgba(0,0,0,0.08);
  border-radius: 6px;
  outline: none;
  background: #fafafa;
}
.at-picker-filter:focus { border-color: #3b82f6; background: #fff; }

.at-picker-groups { padding: 4px 0; }
.at-group { }
.at-group-label {
  font-size: 10px;
  font-weight: 600;
  color: #888;
  padding: 6px 12px 2px;
  text-transform: uppercase;
  letter-spacing: 0.3px;
}
.at-item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 6px 12px;
  border: none;
  background: none;
  cursor: pointer;
  text-align: left;
  font-size: 12px;
  color: #333;
  transition: background 0.1s;
}
.at-item:hover, .at-item-active { background: rgba(59, 130, 246, 0.06); }
.at-item-icon { flex-shrink: 0; color: #888; }
.at-item-label { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.at-item-hint {
  font-size: 10px;
  color: #aaa;
  flex-shrink: 0;
}
.at-group-empty {
  font-size: 11px;
  color: #bbb;
  padding: 2px 12px 6px;
}
</style>