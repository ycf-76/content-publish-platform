<template>
  <Teleport to="body">
    <Transition name="dsh-modal-fade">
      <div v-if="visible" class="dsh-confirm-overlay" @click.self="onCancel">
        <div
          class="dsh-confirm-dialog"
          :class="{ 'dsh-confirm-danger': danger }"
          role="alertdialog"
          aria-modal="true"
        >
          <div class="dsh-confirm-header">
            <span class="dsh-confirm-icon">{{ danger ? '⚠️' : 'ℹ️' }}</span>
            <span class="dsh-confirm-title">{{ title }}</span>
          </div>
          <div class="dsh-confirm-body">
            <p v-for="(line, i) in messageLines" :key="i" class="dsh-confirm-line">{{ line }}</p>
          </div>
          <div class="dsh-confirm-actions">
            <button class="dsh-confirm-btn dsh-confirm-cancel" @click="onCancel">{{ cancelText }}</button>
            <button
              class="dsh-confirm-btn dsh-confirm-ok"
              :class="{ 'dsh-confirm-ok-danger': danger }"
              @click="onConfirm"
            >
              {{ confirmText }}
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(
  defineProps<{
    visible: boolean
    title?: string
    message?: string
    confirmText?: string
    cancelText?: string
    danger?: boolean
  }>(),
  {
    title: '确认操作',
    message: '',
    confirmText: '确定',
    cancelText: '取消',
    danger: false,
  },
)

const emit = defineEmits<{
  (e: 'confirm'): void
  (e: 'cancel'): void
  (e: 'update:visible', value: boolean): void
}>()

const messageLines = computed(() => (props.message || '').split('\n'))

function onConfirm() {
  emit('update:visible', false)
  emit('confirm')
}

function onCancel() {
  emit('update:visible', false)
  emit('cancel')
}
</script>

<style scoped>
.dsh-confirm-overlay {
  position: fixed;
  inset: 0;
  background: rgba(17, 24, 39, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
  backdrop-filter: blur(2px);
}

.dsh-confirm-dialog {
  width: min(440px, 90vw);
  background: #ffffff;
  border-radius: 12px;
  padding: 20px 22px;
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.25);
  border-top: 4px solid var(--dsh-accent, #6366f1);
  font-family: inherit;
}

.dsh-confirm-dialog.dsh-confirm-danger {
  border-top-color: #ef4444;
}

.dsh-confirm-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.dsh-confirm-icon {
  font-size: 18px;
  line-height: 1;
}

.dsh-confirm-title {
  font-size: 16px;
  font-weight: 600;
  color: #1f2937;
}

.dsh-confirm-body {
  margin-bottom: 18px;
}

.dsh-confirm-line {
  margin: 0 0 4px;
  font-size: 13px;
  line-height: 1.6;
  color: #4b5563;
  white-space: pre-wrap;
  word-break: break-word;
}

.dsh-confirm-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

.dsh-confirm-btn {
  padding: 8px 18px;
  border-radius: 8px;
  font-size: 13px;
  cursor: pointer;
  border: 1px solid transparent;
  transition: all 0.15s ease;
}

.dsh-confirm-cancel {
  background: #f3f4f6;
  color: #374151;
  border-color: #e5e7eb;
}

.dsh-confirm-cancel:hover {
  background: #e5e7eb;
}

.dsh-confirm-ok {
  background: var(--dsh-accent, #6366f1);
  color: #ffffff;
}

.dsh-confirm-ok:hover {
  filter: brightness(1.05);
}

.dsh-confirm-ok-danger {
  background: #ef4444;
}

.dsh-confirm-ok-danger:hover {
  background: #dc2626;
}

.dsh-modal-fade-enter-active,
.dsh-modal-fade-leave-active {
  transition: opacity 0.18s ease;
}

.dsh-modal-fade-enter-from,
.dsh-modal-fade-leave-to {
  opacity: 0;
}
</style>
