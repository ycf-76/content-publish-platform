<template>
  <div class="dynamic-form">
    <!-- 无 Schema 时显示提示 -->
    <div v-if="!schema || Object.keys(schema).length === 0" class="no-schema">
      <i data-lucide="file-json"></i>
      <p>此节点无需额外配置</p>
    </div>

    <!-- 有 Schema 时动态渲染 -->
    <template v-else>
      <!-- 遍历 properties -->
      <div 
        v-for="(propSchema, propName, idx) in schema.properties" 
        :key="idx"
        class="form-group"
      >
        <!-- 字段标签 -->
        <label class="form-label">
          {{ propSchema.title || formatLabel(propName) }}
          
          <span v-if="isRequired(propName)" class="required-mark">*</span>
          
          <span 
            v-if="propSchema.description" 
            class="field-desc"
            :title="propSchema.description"
          >
            <i data-lucide="info"></i>
          </span>
        </label>

        <!-- 根据类型渲染不同的输入控件 -->

        <!-- String 类型 -->
        <input
          v-if="propSchema.type === 'string' && !propSchema.enum"
          type="text"
          :value="modelValue[propName]"
          @input="updateField(propName, ($event.target as HTMLInputElement).value)"
          :placeholder="propSchema.description || '请输入' + formatLabel(propName)"
          :class="{ 'has-error': hasError(propName) }"
          class="form-input"
        />

        <!-- Enum/Select 类型 -->
        <select
          v-else-if="propSchema.type === 'string' && propSchema.enum"
          :value="modelValue[propName] || ''"
          @change="updateField(propName, ($event.target as HTMLSelectElement).value)"
          class="form-select"
        >
          <option value="" disabled>请选择{{ formatLabel(propName) }}</option>
          <option 
            v-for="option in propSchema.enum" 
            :key="option"
            :value="option"
          >
            {{ option }}
          </option>
        </select>

        <!-- Number / Integer 类型 -->
        <input
          v-else-if="propSchema.type === 'number' || propSchema.type === 'integer'"
          type="number"
          :value="modelValue[propName]"
          @input="updateField(propName, Number(($event.target as HTMLInputElement).value))"
          :min="propSchema.minimum"
          :max="propSchema.maximum"
          :step="propSchema.type === 'integer' ? 1 : 0.1"
          :placeholder="`请输入数字`"
          class="form-input form-number"
        />

        <!-- Boolean 类型 -->
        <label 
          v-else-if="propSchema.type === 'boolean'" 
          class="form-checkbox-wrapper"
        >
          <input
            type="checkbox"
            :checked="modelValue[propName]"
            @change="updateField(propName, ($event.target as HTMLInputElement).checked)"
            class="form-checkbox"
          />
          <span>{{ propSchema.default ? '是' : '否' }}</span>
        </label>

        <!-- Array 类型（简单数组） -->
        <div v-else-if="propSchema.type === 'array'" class="form-array">
          <div 
            v-for="(item, index) in (modelValue[strKey(propName)] || [])" 
            :key="index"
            class="array-item"
          >
            <input
              type="text"
              :value="item"
              @input="updateArrayItem(propName, index, ($event.target as HTMLInputElement).value)"
              class="form-input array-input"
            />
            <button 
              class="remove-item-btn"
              @click="removeArrayItem(propName, index)"
              title="删除此项"
            >
              <i data-lucide="x"></i>
            </button>
          </div>
          
          <button 
            class="add-item-btn"
            @click="addArrayItem(propName)"
          >
            <i data-lucide="plus"></i>
            添加项
          </button>
        </div>

        <!-- Object 类型（嵌套对象 - 简化处理） -->
        <div v-else-if="propSchema.type === 'object'" class="form-object">
          <pre class="json-preview">{{ JSON.stringify(modelValue[propName] || {}, null, 2) }}</pre>
          <p class="object-hint">复杂对象暂不支持可视化编辑</p>
        </div>

        <!-- 默认：文本框 -->
        <textarea
          v-else
          :value="JSON.stringify(modelValue[propName], null, 2)"
          @input="tryParseJson(propName, ($event.target as HTMLTextAreaElement).value)"
          rows="3"
          placeholder='请输入值（支持JSON格式）'
          class="form-textarea"
        ></textarea>

        <!-- 错误信息 -->
        <div v-if="hasError(propName)" class="error-message">
          {{ getError(propName) }}
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'

// Props
const props = defineProps<{
  schema: Record<string, any>  // JSON Schema 对象
  modelValue: Record<string, any>  // v-model 绑定的数据对象
}>()

// Emits
const emit = defineEmits<{
  (e: 'update:modelValue', value: Record<string, any>): void
}>()

// 本地错误状态
const errors = ref<Record<string, string>>({})

// ===== 方法 =====

function strKey(key: string | number): string {
  return String(key)
}

// 更新字段值
function updateField(fieldName: string | number, value: any) {
  const key = strKey(fieldName)
  const newData = { ...props.modelValue }
  
  if (value === '' || value === undefined || value === null) {
    delete newData[key]
  } else {
    newData[key] = value
  }
  
  // 清除该字段的错误
  if (errors.value[key]) {
    const newErrors = { ...errors.value }
    delete newErrors[key]
    errors.value = newErrors
  }
  
  emit('update:modelValue', newData)
}

// 更新数组元素
function updateArrayItem(fieldName: string | number, index: string | number, value: any) {
  const key = strKey(fieldName)
  const arr = [...(props.modelValue[key] || [])]
  arr[Number(index)] = value
  updateField(key, arr)
}

// 添加数组元素
function addArrayItem(fieldName: string | number) {
  const key = strKey(fieldName)
  const arr = [...(props.modelValue[key] || []), '']
  updateField(key, arr)
}

// 删除数组元素
function removeArrayItem(fieldName: string | number, index: string | number) {
  const key = strKey(fieldName)
  const arr = [...(props.modelValue[key] || [])]
  arr.splice(Number(index), 1)
  updateField(key, arr)
}

// 尝试解析 JSON 输入
function tryParseJson(fieldName: string | number, textValue: string) {
  const key = strKey(fieldName)
  try {
    const parsed = JSON.parse(textValue)
    updateField(key, parsed)
    
    if (errors.value[key]) {
      const newErrors = { ...errors.value }
      delete newErrors[key]
      errors.value = newErrors
    }
  } catch {
    updateField(key, textValue)
  }
}

// 判断字段是否必填
function isRequired(fieldName: string | number): boolean {
  return props.schema.required?.includes(fieldName) || false
}

// 判断是否有错误
function hasError(fieldName: string | number): boolean {
  return !!errors.value[strKey(fieldName)]
}

function getError(fieldName: string | number): string {
  return errors.value[strKey(fieldName)] || ''
}

function formatLabel(name: string | number): string {
  return String(name)
    .replace(/_/g, ' ')
    .replace(/\b\w/g, l => l.toUpperCase())
}

// 监听 schema 变化时重置错误
watch(() => props.schema, () => {
  errors.value = {}
}, { deep: true })
</script>

<style scoped>
.dynamic-form {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

/* 无 Schema 提示 */
.no-schema {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 24px;
  color: #9ca3af;
  background: #f9fafb;
  border-radius: 8px;
  border: 1px dashed #e5e7eb;
}

.no-svg svg {
  width: 32px;
  height: 32px;
  opacity: 0.5;
}

.no-schema p {
  margin: 0;
  font-size: 13px;
}

/* 表单组 */
.form-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

/* 标签 */
.form-label {
  font-size: 13px;
  font-weight: 500;
  color: #374151;
  display: flex;
  align-items: center;
  gap: 4px;
}

.required-mark {
  color: #ef4444;
  font-weight: 600;
}

.field-desc {
  color: #9ca3af;
  cursor: help;
  display: inline-flex;
}

.field-desc svg {
  width: 14px;
  height: 14px;
}

/* 输入控件通用样式 */
.form-input,
.form-select,
.form-textarea {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  font-size: 13px;
  color: #374151;
  background: white;
  transition: all 0.2s;
  outline: none;
  font-family: inherit;
}

.form-input:focus,
.form-select:focus,
.form-textarea:focus {
  border-color: #667eea;
  box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
}

.form-input.has-error,
.form-select.has-error,
.form-textarea.has-error {
  border-color: #ef4444;
  box-shadow: 0 0 0 3px rgba(239, 68, 68, 0.05);
}

/* 数字输入 */
.form-number {
  font-family: 'Consolas', monospace;
}

/* 下拉选择 */
.form-select {
  cursor: pointer;
  appearance: none;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 20 20'%3E%3Cpath stroke='%236B7280' stroke-linecap='round' stroke-linejoin='round' stroke-width='1.5' d='M6 8l4 4 4-4'/%3E%3C/svg%3E");
  background-position: right 8px center;
  background-repeat: no-repeat;
  background-size: 16px;
  padding-right: 32px;
}

/* 复选框 */
.form-checkbox-wrapper {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 0;
  cursor: pointer;
}

.form-checkbox {
  width: 16px;
  height: 16px;
  accent-color: #667eea;
  cursor: pointer;
}

/* 数组类型 */
.form-array {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.array-item {
  display: flex;
  gap: 6px;
  align-items: center;
}

.array-input {
  flex: 1;
}

.remove-item-btn {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  background: #fef2f2;
  color: #dc2626;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.2s;
  padding: 0;
}

.remove-item-btn:hover {
  background: #fee2e2;
}

.remove-item-btn svg {
  width: 14px;
  height: 14px;
}

.add-item-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  padding: 6px 12px;
  border: 1px dashed #d1d5db;
  border-radius: 6px;
  background: transparent;
  color: #6b7280;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;
}

.add-item-btn:hover {
  border-color: #667eea;
  color: #667eea;
  background: rgba(102, 126, 234, 0.03);
}

.add-item-btn svg {
  width: 14px;
  height: 14px;
}

/* 对象类型 */
.form-object {
  padding: 12px;
  background: #f9fafb;
  border-radius: 6px;
  border: 1px solid #e5e7eb;
}

.json-preview {
  margin: 0;
  padding: 10px;
  background: #1e1e1e;
  color: #d4d4d4;
  border-radius: 4px;
  font-size: 11px;
  line-height: 1.5;
  max-height: 150px;
  overflow: auto;
  font-family: 'Consolas', monospace;
}

.object-hint {
  margin: 8px 0 0 0;
  font-size: 11px;
  color: #9ca3af;
  text-align: center;
}

/* 文本域 */
.form-textarea {
  resize: vertical;
  min-height: 60px;
  font-family: 'Consolas', monospace;
  line-height: 1.4;
}

/* 错误信息 */
.error-message {
  font-size: 11px;
  color: #dc2626;
  padding: 4px 8px;
  background: #fef2f2;
  border-radius: 4px;
}
</style>