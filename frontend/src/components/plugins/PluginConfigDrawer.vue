<template>
  <div class="config-drawer-overlay" @click.self="$emit('close')">
    <div class="config-drawer" :class="{ 'is-open': true }">
      <!-- 抽屉头部 -->
      <div class="cd-header">
        <h2 class="cd-title">插件配置</h2>
        <button @click="$emit('close')" class="cd-close-btn">
          <i data-lucide="x"></i>
        </button>
      </div>

      <!-- 插件信息 -->
      <div class="cd-plugin-info">
        <div 
          class="cd-plugin-icon"
          :style="{ background: getCategoryColor(plugin.category) }"
        >
          {{ plugin.display_icon || getDefaultIcon(plugin.category) }}
        </div>
        <div class="cd-plugin-meta">
          <h3 class="cd-plugin-name">{{ plugin.name }}</h3>
          <p class="cd-plugin-id">ID: {{ plugin.id }}</p>
        </div>
      </div>

      <!-- 配置表单 -->
      <div class="cd-body">
        <!-- 加载状态 -->
        <div v-if="loading" class="cd-loading">
          <div class="cd-spinner"></div>
          <p>加载配置中...</p>
        </div>

        <!-- 配置表单（动态渲染） -->
        <form v-else @submit.prevent="handleSave" class="cd-form">
          <!-- 通用开关：启用/禁用 -->
          <div class="cd-field cd-field-toggle">
            <label class="cd-label">启用状态</label>
            <div class="cd-switch-wrapper">
              <span class="cd-switch-label">{{ localConfig.is_enabled ? '已启用' : '已禁用' }}</span>
              <label class="cd-switch">
                <input 
                  type="checkbox" 
                  v-model="localConfig.is_enabled"
                  class="cd-switch-input"
                />
                <span class="cd-slider"></span>
              </label>
            </div>
          </div>

          <!-- 动态配置字段（基于config_schema） -->
          <div v-if="configSchema && configSchema.properties" class="cd-fields">
            <div
              v-for="(schema, key) in configSchema.properties as Record<string, any>"
              :key="key"
              class="cd-field"
            >
              <label class="cd-label">
                {{ schema.title || formatKey(key) }}
                <span v-if="isRequired(key)" class="cd-required">*</span>
              </label>
              
              <!-- 文本输入 -->
              <input
                v-if="schema.type === 'string' && !schema.enum"
                type="text"
                v-model="localConfig[key]"
                :placeholder="schema.description || `请输入${formatKey(key)}`"
                class="cd-input"
              />
              
              <!-- 多行文本 -->
              <textarea
                v-else-if="schema.type === 'string' && schema.format === 'multiline'"
                v-model="localConfig[key]"
                :placeholder="schema.description || `请输入${formatKey(key)}`"
                rows="4"
                class="cd-textarea"
              ></textarea>
              
              <!-- 数字输入 -->
              <input
                v-else-if="schema.type === 'number' || schema.type === 'integer'"
                type="number"
                v-model.number="localConfig[key]"
                :min="schema.minimum"
                :max="schema.maximum"
                :step="schema.type === 'integer' ? 1 : 0.1"
                class="cd-input"
              />
              
              <!-- 布尔值开关 -->
              <div v-else-if="schema.type === 'boolean'" class="cd-switch-wrapper">
                <label class="cd-switch">
                  <input 
                    type="checkbox" 
                    v-model="localConfig[key]"
                    class="cd-switch-input"
                  />
                  <span class="cd-slider"></span>
                </label>
                <span class="cd-switch-hint">{{ localConfig[key] ? '开启' : '关闭' }}</span>
              </div>
              
              <!-- 下拉选择 -->
              <select
                v-else-if="schema.enum"
                v-model="localConfig[key]"
                class="cd-select"
              >
                <option value="">请选择</option>
                <option 
                  v-for="option in schema.enum" 
                  :key="option" 
                  :value="option"
                >
                  {{ option }}
                </option>
              </select>
              
              <!-- JSON对象编辑器 -->
              <div v-else-if="schema.type === 'object'" class="cd-json-editor">
                <textarea
                  v-model="jsonEditors[key]"
                  placeholder='{"key": "value"}'
                  rows="6"
                  class="cd-textarea cd-code"
                  @blur="validateJson(key)"
                ></textarea>
                <p v-if="jsonErrors[key]" class="cd-error">{{ jsonErrors[key] }}</p>
              </div>
              
              <!-- 数组编辑器 -->
              <div v-else-if="schema.type === 'array'" class="cd-array-editor">
                <div 
                  v-for="(item, index) in (localConfig[key] || [])" 
                  :key="index"
                  class="cd-array-item"
                >
                  <input 
                    type="text" 
                    v-model="localConfig[key][index]"
                    class="cd-input"
                  />
                  <button 
                    type="button"
                    @click="removeArrayItem(key, index)"
                    class="cd-btn-remove"
                  >
                    <i data-lucide="x"></i>
                  </button>
                </div>
                <button 
                  type="button"
                  @click="addArrayItem(key)"
                  class="cd-btn-add"
                >
                  <i data-lucide="plus"></i>
                  添加项
                </button>
              </div>
              
              <!-- 不支持的类型提示 -->
              <div v-else class="cd-unsupported">
                <i data-lucide="alert-triangle"></i>
                暂不支持 {{ schema.type }} 类型的编辑，请使用JSON格式
              </div>
              
              <!-- 字段描述 -->
              <p v-if="schema.description" class="cd-description">
                {{ schema.description }}
              </p>
              
              <!-- 默认值提示 -->
              <p v-if="schema.default !== undefined && !localConfig[key]" class="cd-default">
                默认值: {{ JSON.stringify(schema.default) }}
              </p>
            </div>
          </div>

          <!-- 无配置Schema的提示 -->
          <div v-else class="cd-no-schema">
            <i data-lucide="settings"></i>
            <h3>该插件无需配置</h3>
            <p>此插件没有可自定义的配置选项。</p>
          </div>
        </form>
      </div>

      <!-- 抽屉底部操作区 -->
      <div class="cd-footer">
        <button 
          type="button"
          @click="$emit('close')"
          class="cd-btn cd-btn-cancel"
        >
          取消
        </button>
        <button 
          type="submit"
          @click="handleSave"
          :disabled="loading || hasErrors"
          class="cd-btn cd-btn-save"
        >
          <i data-lucide="save"></i>
          保存配置
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import type { Plugin, PluginCategory } from '@/api/plugins'

// ==================== Props & Emits ====================
interface Props {
  plugin: Plugin
  config: Record<string, any>
}

const props = defineProps<Props>()

const emit = defineEmits<{
  close: []
  saveConfig: [pluginId: string, config: Record<string, any>]
}>()

// ==================== State ====================
const loading = ref(false)
const localConfig = reactive<Record<string, any>>({})
const jsonEditors = reactive<Record<string, string>>({})
const jsonErrors = reactive<Record<string, string>>({})

// 从plugin.json中提取config_schema（这里简化处理，实际应从API获取）
const configSchema = computed(() => {
  // TODO: 实际应该从API获取完整的plugin.json内容
  // 这里返回一个示例schema用于演示
  if (props.plugin.category === 'platform') {
    return {
      type: 'object',
      properties: {
        publish_mode: {
          type: 'string',
          title: '发布模式',
          enum: ['auto', 'semi_auto', 'manual'],
          default: 'semi_auto',
          description: '选择内容的发布方式',
        },
        client_preference: {
          type: 'string',
          title: '客户端偏好',
          enum: ['plugin_first', 'local_only'],
          default: 'plugin_first',
          description: '优先使用的客户端类型',
        },
      },
      required: ['publish_mode'],
    }
  }
  
  if (props.plugin.category === 'datasource') {
    return {
      type: 'object',
      properties: {
        refresh_interval_minutes: {
          type: 'integer',
          title: '刷新间隔(分钟)',
          minimum: 5,
          maximum: 60,
          default: 15,
          description: '数据源自动刷新的时间间隔',
        },
        max_results_per_source: {
          type: 'integer',
          title: '每源最大结果数',
          minimum: 10,
          maximum: 100,
          default: 20,
          description: '每个数据源返回的最大结果数量',
        },
        enable_auto_classify: {
          type: 'boolean',
          title: '自动分类',
          default: true,
          description: '是否启用AI自动分类功能',
        },
      },
    }
  }
  
  if (props.plugin.category === 'workflow_node') {
    return {
      type: 'object',
      properties: {
        model_name: {
          type: 'string',
          title: '模型名称',
          default: 'gpt-4o-mini',
          description: '使用的LLM模型名称',
        },
        writing_style: {
          type: 'string',
          title: '写作风格',
          enum: ['爆款标题党', '种草安利', '避坑指南', '情感共鸣', '科普干货'],
          default: '爆款标题党',
          description: '默认文案写作风格',
        },
        content_length: {
          type: 'integer',
          title: '内容长度',
          minimum: 100,
          maximum: 2000,
          default: 500,
          description: '生成文案的目标字数',
        },
      },
    }
  }
  
  return null
})

// ==================== Computed ====================
const hasErrors = computed(() => Object.values(jsonErrors).some(e => e))

// ==================== Methods ====================
function getDefaultIcon(category: PluginCategory): string {
  const icons: Record<PluginCategory, string> = {
    platform: '📱',
    datasource: '🔍',
    workflow_node: '⚙️',
    ui_theme: '🎨',
    analytics: '📊',
    utility: '🛠️',
    integration: '🔗',
    ai_model: '🤖',
    tool: '🔧',
    theme: '🎨',
  }
  return icons[category] || '📦'
}

function getCategoryColor(category: PluginCategory): string {
  const colors: Record<PluginCategory, string> = {
    platform: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
    datasource: 'linear-gradient(135deg, #f093fb 0%, #f5576c 100%)',
    workflow_node: 'linear-gradient(135deg, #4facfe 0%, #00f2fe 100%)',
    ui_theme: 'linear-gradient(135deg, #43e97b 0%, #38f9d7 100%)',
    analytics: 'linear-gradient(135deg, #fa709a 0%, #fee140 100%)',
    utility: 'linear-gradient(135deg, #30cfd0 0%, #330867 100%)',
    integration: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
    ai_model: 'linear-gradient(135deg, #a18cd1 0%, #fbc2eb 100%)',
    tool: 'linear-gradient(135deg, #ffecd2 0%, #fcb69f 100%)',
    theme: 'linear-gradient(135deg, #ff9a9e 0%, #fecfef 100%)',
  }
  return colors[category] || '#6366f1'
}

function formatKey(key: string): string {
  return key
    .replace(/_/g, ' ')
    .replace(/\b\w/g, l => l.toUpperCase())
}

function isRequired(key: string): boolean {
  return configSchema.value?.required?.includes(key) || false
}

function validateJson(key: string): void {
  try {
    if (jsonEditors[key]) {
      JSON.parse(jsonEditors[key])
      localConfig[key] = JSON.parse(jsonEditors[key])
      delete jsonErrors[key]
    }
  } catch (error: any) {
    jsonErrors[key] = `JSON格式错误: ${error.message}`
  }
}

function addArrayItem(key: string): void {
  if (!localConfig[key]) {
    localConfig[key] = []
  }
  localConfig[key].push('')
}

function removeArrayItem(key: string | number, index: string | number): void {
  const k = String(key)
  localConfig[k].splice(Number(index), 1)
}

async function handleSave(): Promise<void> {
  if (hasErrors.value) {
    alert('请修正表单中的错误')
    return
  }

  loading.value = true
  
  try {
    // 构建要保存的配置对象（排除is_enabled，它单独处理）
    const configToSave = { ...localConfig }
    
    emit('saveConfig', props.plugin.id, configToSave)
    
  } catch (error: any) {
    alert(`保存失败: ${error.message}`)
  } finally {
    loading.value = false
  }
}

// ==================== Lifecycle ====================
onMounted(() => {
  // 初始化本地配置状态
  Object.assign(localConfig, props.config || {})
  
  // 初始化JSON编辑器内容
  if (configSchema.value?.properties) {
    for (const [key, schema] of Object.entries(configSchema.value.properties)) {
      if ((schema as any).type === 'object') {
        jsonEditors[key] = JSON.stringify(localConfig[key] || {}, null, 2)
      }
    }
  }
})
</script>

<style scoped>
.config-drawer-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  z-index: 1000;
  display: flex;
  justify-content: flex-end;
  animation: fadeIn 0.2s ease;
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

.config-drawer {
  width: 560px;
  max-width: 90vw;
  height: 100vh;
  background: white;
  box-shadow: -8px 0 24px rgba(0, 0, 0, 0.12);
  display: flex;
  flex-direction: column;
  animation: slideInRight 0.3s ease;
}

@keyframes slideInRight {
  from { transform: translateX(100%); }
  to { transform: translateX(0); }
}

/* Header */
.cd-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 24px 28px;
  border-bottom: 1px solid #e5e7eb;
}

.cd-title {
  font-size: 22px;
  font-weight: 700;
  color: #111827;
}

.cd-close-btn {
  width: 36px;
  height: 36px;
  border: none;
  background: #f3f4f6;
  border-radius: 8px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}

.cd-close-btn:hover {
  background: #e5e7eb;
  color: #dc2626;
}

/* Plugin Info */
.cd-plugin-info {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 24px 28px;
  background: linear-gradient(to bottom right, #f9fafb, #ffffff);
  border-bottom: 1px solid #e5e7eb;
}

.cd-plugin-icon {
  width: 64px;
  height: 64px;
  border-radius: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 32px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
}

.cd-plugin-name {
  font-size: 18px;
  font-weight: 700;
  color: #111827;
  margin-bottom: 4px;
}

.cd-plugin-id {
  font-size: 13px;
  color: #9ca3af;
  font-family: monospace;
}

/* Body */
.cd-body {
  flex: 1;
  overflow-y: auto;
  padding: 28px;
}

/* Loading */
.cd-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 200px;
  color: #9ca3af;
  gap: 16px;
}

.cd-spinner {
  width: 40px;
  height: 40px;
  border: 3px solid #e5e7eb;
  border-top-color: #6366f1;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* Form */
.cd-form {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.cd-field {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.cd-label {
  font-size: 14px;
  font-weight: 600;
  color: #374151;
  display: flex;
  align-items: center;
  gap: 4px;
}

.cd-required {
  color: #ef4444;
  font-size: 16px;
}

.cd-input,
.cd-select,
.cd-textarea {
  width: 100%;
  height: 44px;
  border: 1px solid #d1d5db;
  border-radius: 10px;
  padding: 0 16px;
  font-size: 15px;
  transition: all 0.2s;
  background: white;
}

.cd-textarea {
  height: auto;
  min-height: 88px;
  padding: 12px 16px;
  resize: vertical;
  line-height: 1.5;
}

.cd-code {
  font-family: 'Monaco', 'Menlo', monospace;
  font-size: 13px;
  background: #f9fafb;
}

.cd-input:focus,
.cd-select:focus,
.cd-textarea:focus {
  outline: none;
  border-color: #6366f1;
  box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.1);
}

/* Toggle Switch */
.cd-field-toggle {
  flex-direction: row;
  align-items: center;
  justify-content: space-between;
  padding: 16px 0;
  border-top: 1px solid #e5e7eb;
  border-bottom: 1px solid #e5e7eb;
}

.cd-switch-wrapper {
  display: flex;
  align-items: center;
  gap: 12px;
}

.cd-switch-label {
  font-size: 14px;
  color: #6b7280;
  font-weight: 500;
}

.cd-switch {
  position: relative;
  display: inline-block;
  width: 52px;
  height: 28px;
}

.cd-switch-input {
  opacity: 0;
  width: 0;
  height: 0;
}

.cd-slider {
  position: absolute;
  cursor: pointer;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: #d1d5db;
  transition: 0.3s;
  border-radius: 28px;
}

.cd-slider:before {
  position: absolute;
  content: "";
  height: 22px;
  width: 22px;
  left: 3px;
  bottom: 3px;
  background-color: white;
  transition: 0.3s;
  border-radius: 50%;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
}

.cd-switch-input:checked + .cd-slider {
  background-color: #10b981;
}

.cd-switch-input:checked + .cd-slider:before {
  transform: translateX(24px);
}

.cd-switch-hint {
  font-size: 13px;
  color: #9ca3af;
}

/* Description & Default */
.cd-description {
  font-size: 13px;
  color: #6b7280;
  margin-top: -4px;
}

.cd-default {
  font-size: 12px;
  color: #9ca3af;
  font-style: italic;
}

/* Error */
.cd-error {
  font-size: 13px;
  color: #dc2626;
  margin-top: 4px;
}

/* Array Editor */
.cd-array-editor {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.cd-array-item {
  display: flex;
  gap: 8px;
  align-items: center;
}

.cd-array-item .cd-input {
  flex: 1;
}

.cd-btn-remove,
.cd-btn-add {
  width: 36px;
  height: 36px;
  border: 1px solid #d1d5db;
  border-radius: 8px;
  background: white;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
  color: #6b7280;
}

.cd-btn-remove:hover {
  border-color: #fecaca;
  color: #dc2626;
  background: #fef2f2;
}

.cd-btn-add:hover {
  border-color: #c7d2fe;
  color: #6366f1;
  background: #eef2ff;
}

/* Unsupported Type */
.cd-unsupported {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px;
  background: #fffbeb;
  border: 1px solid #fde68a;
  border-radius: 8px;
  color: #92400e;
  font-size: 13px;
}

/* No Schema */
.cd-no-schema {
  text-align: center;
  padding: 48px 24px;
  color: #9ca3af;
}

.cd-no-schema i {
  width: 48px;
  height: 48px;
  margin-bottom: 16px;
  opacity: 0.5;
}

.cd-no-schema h3 {
  font-size: 16px;
  font-weight: 600;
  color: #6b7280;
  margin-bottom: 8px;
}

.cd-no-schema p {
  font-size: 14px;
}

/* Footer */
.cd-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding: 20px 28px;
  border-top: 1px solid #e5e7eb;
  background: #f9fafb;
}

.cd-btn {
  height: 42px;
  padding: 0 24px;
  border-radius: 10px;
  font-size: 15px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  border: none;
}

.cd-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.cd-btn-cancel {
  background: white;
  color: #374151;
  border: 1px solid #d1d5db;
}

.cd-btn-cancel:hover:not(:disabled) {
  background: #f9fafb;
}

.cd-btn-save {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  box-shadow: 0 2px 8px rgba(102, 126, 234, 0.25);
}

.cd-btn-save:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(102, 126, 234, 0.35);
}
</style>