<template>
  <div class="mint-custom-select" :class="{ 'mint-custom-select-disabled': disabled }" ref="wrapperRef">
    <div class="mint-custom-select-trigger" @click="toggle">
      <span class="mint-custom-select-text">{{ displayLabel }}</span>
      <svg class="mint-custom-select-arrow" :class="{ 'mint-custom-select-arrow-open': isOpen }" xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"></polyline></svg>
    </div>
    <Transition name="mint-select-dropdown">
      <div v-if="isOpen" class="mint-custom-select-dropdown">
        <div
          v-for="opt in options"
          :key="opt.value"
          class="mint-custom-select-option"
          :class="{ 'mint-custom-select-option-active': opt.value === modelValue }"
          @click="select(opt.value)"
          :title="opt.title"
        >
          {{ opt.label }}
        </div>
      </div>
    </Transition>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'

export interface SelectOption {
  label: string
  value: string | number
  title?: string
}

const props = withDefaults(defineProps<{
  modelValue: string | number
  options: SelectOption[]
  disabled?: boolean
}>(), {
  disabled: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: string | number]
}>()

const isOpen = ref(false)
const wrapperRef = ref<HTMLElement | null>(null)

const displayLabel = computed(() => {
  const found = props.options.find(o => o.value === props.modelValue)
  return found ? found.label : String(props.modelValue)
})

function toggle() {
  if (props.disabled) return
  isOpen.value = !isOpen.value
}

function select(val: string | number) {
  emit('update:modelValue', val)
  isOpen.value = false
}

function onClickOutside(e: MouseEvent) {
  if (wrapperRef.value && !wrapperRef.value.contains(e.target as Node)) {
    isOpen.value = false
  }
}

onMounted(() => {
  document.addEventListener('click', onClickOutside)
})

onBeforeUnmount(() => {
  document.removeEventListener('click', onClickOutside)
})
</script>

<style scoped>
.mint-custom-select {
  position: relative;
  width: 100%;
}

.mint-custom-select-disabled {
  opacity: 0.5;
  pointer-events: none;
}

.mint-custom-select-trigger {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 32px 8px 12px;
  background: var(--ma-secondary, #EEF0F4);
  border: 1px solid transparent;
  border-radius: 9999px;
  font-size: 14px;
  color: #111827;
  cursor: pointer;
  transition: background-color 0.2s, border-color 0.2s;
  user-select: none;
  position: relative;
}

.mint-custom-select-trigger:hover {
  border-color: #D1D5DB;
}

.mint-custom-select-trigger:focus,
.mint-custom-select.mint-custom-select--focused .mint-custom-select-trigger {
  border-color: #D1D5DB;
  outline: none;
}

.mint-custom-select-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
}

.mint-custom-select-arrow {
  position: absolute;
  right: 12px;
  top: 50%;
  transform: translateY(-50%);
  transition: transform 0.2s;
  color: #6B7280;
  flex-shrink: 0;
}

.mint-custom-select-arrow-open {
  transform: translateY(-50%) rotate(180deg);
}

.mint-custom-select-dropdown {
  position: absolute;
  top: calc(100% + 4px);
  left: 0;
  right: 0;
  background: #FFFFFF;
  border: 1px solid #E5E7EB;
  border-radius: 12px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.08), 0 1px 4px rgba(0, 0, 0, 0.04);
  z-index: 1000;
  max-height: 240px;
  overflow-y: auto;
  padding: 4px;
}

.mint-custom-select-option {
  padding: 8px 12px;
  font-size: 14px;
  color: #374151;
  border-radius: 8px;
  cursor: pointer;
  transition: background-color 0.15s;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.mint-custom-select-option:hover {
  background: var(--ma-secondary, #EEF0F4);
}

.mint-custom-select-option-active {
  background: var(--ma-secondary, #EEF0F4);
  color: #111827;
  font-weight: 500;
}

.mint-select-dropdown-enter-active,
.mint-select-dropdown-leave-active {
  transition: opacity 0.15s ease, transform 0.15s ease;
}

.mint-select-dropdown-enter-from,
.mint-select-dropdown-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}
</style>