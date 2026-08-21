<template>
  <div class="recovery-decision-card">
    <div class="recovery-decision-head">
      <span class="recovery-decision-icon">⚑</span>
      <span class="recovery-decision-title">{{ title }}</span>
    </div>
    <div v-if="description" class="recovery-decision-desc">{{ description }}</div>
    <div class="recovery-decision-actions">
      <button class="recovery-decision-confirm" @click="$emit('decide', 'confirm')">继续</button>
      <button class="recovery-decision-cancel" @click="$emit('decide', 'cancel')">取消</button>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  title: string
  description?: string
}>()

defineEmits<{
  decide: [action: 'confirm' | 'cancel']
}>()
</script>

<style scoped>
.recovery-decision-card {
  border: 1px solid #fde68a;
  background: #fffbeb;
  border-radius: 10px;
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.recovery-decision-head {
  display: flex;
  align-items: center;
  gap: 7px;
  color: #92400e;
}

.recovery-decision-icon {
  font-weight: 700;
  color: #d97706;
}

.recovery-decision-title {
  font-size: 14px;
  font-weight: 600;
}

.recovery-decision-desc {
  font-size: 13px;
  color: #b45309;
  line-height: 1.5;
}

.recovery-decision-actions {
  display: flex;
  gap: 8px;
}

.recovery-decision-actions button {
  padding: 5px 14px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  border: 1px solid transparent;
}

.recovery-decision-confirm {
  background: #d97706;
  color: #fff;
}

.recovery-decision-confirm:hover {
  background: #b45309;
}

.recovery-decision-cancel {
  background: #fff;
  border-color: #fde68a !important;
  color: #b45309;
}

.recovery-decision-cancel:hover {
  background: #fef3c7;
}
</style>
