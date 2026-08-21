<template>
  <div class="wf-stepper" role="tablist" aria-label="工作流分组导航">
    <button
      v-for="(g, i) in groups"
      :key="g.key"
      class="wf-step"
      :class="{
        'is-done': g.state === 'done',
        'is-active': g.state === 'active',
        'is-pending': g.state === 'pending',
      }"
      role="tab"
      :aria-selected="g.state === 'active'"
      :aria-disabled="g.state === 'pending' && !allowJump"
      :tabindex="g.state === 'pending' && !allowJump ? -1 : 0"
      @click="onStepClick(g, i)"
      type="button"
    >
      <span class="wf-step-circle">
        <template v-if="g.state === 'done'">
          <Check />
        </template>
        <template v-else>{{ i + 1 }}</template>
      </span>
      <span class="wf-step-label">
        <span class="wf-step-name">{{ g.name }}</span>
        <span class="wf-step-node-list">{{ g.nodeLabels.join(' · ') }}</span>
      </span>
    </button>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Check } from 'lucide-vue-next'

interface GroupDef {
  key: string
  name: string
  nodes: string[]  // node keys
  nodeLabels: string[]  // 中文标签
}

const props = withDefaults(defineProps<{
  groups: GroupDef[]
  current: number  // 当前组索引 0-based
  groupStates: Array<'done' | 'active' | 'pending'>
  allowJump?: boolean  // 是否允许跳转未开始组
}>(), {
  allowJump: true,
})

const emit = defineEmits<{
  (e: 'jump', index: number): void
}>()

const groups = computed(() =>
  props.groups.map((g, i) => ({
    ...g,
    state: props.groupStates[i] || 'pending',
  }))
)

function onStepClick(_g: GroupDef, i: number) {
  // 未开始组且不允许跳转 → 忽略
  if (props.groupStates[i] === 'pending' && !props.allowJump) return
  emit('jump', i)
}
</script>

<style scoped>
.wf-stepper {
  display: flex;
  align-items: stretch;
  gap: 0;
  padding: 12px 24px;
  background: #ffffff;
  border: 1px solid #E5E7EB;
  border-radius: 12px;
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04);
  flex-shrink: 0;
}
.wf-step {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  background: transparent;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  font-family: inherit;
  transition: background 0.15s ease;
  position: relative;
  min-width: 0;
}
.wf-step:hover:not(.is-pending) {
  background: #F8FAFC;
}
.wf-step.is-pending {
  cursor: not-allowed;
  opacity: 0.55;
}
.wf-step.is-pending:hover {
  background: transparent;
}

/* 连接线：每个步骤前（首个除外） */
.wf-step:not(:first-child)::before {
  content: '';
  position: absolute;
  left: -6px;
  top: 50%;
  transform: translateY(-50%);
  width: 12px;
  height: 2px;
  background: #E5E7EB;
  border-radius: 1px;
}
.wf-step.is-done:not(:first-child)::before,
.wf-step.is-active:not(:first-child)::before {
  background: #FF2442;
}

.wf-step-circle {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 15px;
  font-weight: 600;
  border: 1.5px solid #E5E7EB;
  background: #fff;
  color: #9CA3AF;
  flex-shrink: 0;
  transition: all 0.2s ease;
}
.wf-step.is-done .wf-step-circle {
  background: #FF2442;
  border-color: #FF2442;
  color: #fff;
}
.wf-step.is-active .wf-step-circle {
  background: #FF2442;
  border-color: #FF2442;
  color: #fff;
  box-shadow: 0 0 0 4px rgba(255, 36, 66, 0.12);
}
.wf-step.is-done .wf-step-circle svg {
  width: 14px;
  height: 14px;
}

.wf-step-label {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
  text-align: left;
}
.wf-step-name {
  font-size: 14px;
  font-weight: 600;
  color: #6B7280;
  line-height: 1.3;
}
.wf-step.is-active .wf-step-name {
  color: #111827;
}
.wf-step.is-done .wf-step-name {
  color: #111827;
}
.wf-step-node-list {
  font-size: 14px;
  color: #9CA3AF;
  line-height: 1.3;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

@media (max-width: 900px) {
  .wf-stepper {
    padding: 10px 12px;
    gap: 4px;
  }
  .wf-step {
    padding: 6px 8px;
    gap: 6px;
  }
  .wf-step-name { font-size: 15px; }
  .wf-step-node-list { font-size: 15px; }
  .wf-step-circle { width: 24px; height: 24px; font-size: 14px; }
}
</style>