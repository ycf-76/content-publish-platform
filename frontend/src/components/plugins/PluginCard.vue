<template>
  <div 
    class="plugin-card"
    :class="{
      'is-installed': isInstalled,
      'is-enabled': isEnabled,
      'is-selected': isSelected,
      'is-builtin': plugin.is_builtin,
    }"
  >
    <!-- 选择复选框（批量操作模式） -->
    <div class="pc-select" v-if="showSelectMode">
      <input 
        type="checkbox"
        :checked="isSelected"
        @change="$emit('toggle-select')"
        class="pc-checkbox"
      />
    </div>

    <!-- 卡片头部 -->
    <div class="pc-header">
      <!-- 插件图标 -->
      <div class="pc-icon" :style="{ background: getCategoryColor(plugin.category) }">
        {{ plugin.display_icon || getDefaultIcon(plugin.category) }}
      </div>

      <!-- 状态标签 -->
      <div class="pc-status-tags">
        <span v-if="plugin.is_builtin" class="pc-tag pc-tag-builtin">内置</span>
        <span v-else-if="isInstalled && !isEnabled" class="pc-tag pc-tag-disabled">已禁用</span>
        <span v-else-if="isInstalled" class="pc-tag pc-tag-active">运行中</span>
        <span v-else class="pc-tag pc-tag-available">可安装</span>
        
        <span 
          class="pc-tag pc-tag-price"
          :class="`price-${plugin.pricing_model}`"
        >
          {{ getPriceLabel(plugin.pricing_model) }}
        </span>
      </div>
    </div>

    <!-- 卡片内容 -->
    <div class="pc-body">
      <!-- 标题和版本 -->
      <h3 class="pc-title">{{ plugin.name }}</h3>
      <p class="pc-version">v{{ plugin.version }}</p>

      <!-- 描述 -->
      <p class="pc-description">{{ plugin.description }}</p>

      <!-- 分类和能力标签 -->
      <div class="pc-meta">
        <span class="pc-category">
          <i data-lucide="folder"></i>
          {{ getCategoryLabel(plugin.category) }}
        </span>
        <span class="pc-author">
          <i data-lucide="user"></i>
          {{ plugin.author_name || '未知作者' }}
        </span>
      </div>

      <!-- 统计信息（如果有） -->
      <div v-if="plugin.stats" class="pc-stats">
        <div class="pc-stat-item">
          <i data-lucide="download"></i>
          <span>{{ formatNumber(plugin.stats.install_count) }} 安装</span>
        </div>
        <div class="pc-stat-item">
          <i data-lucide="star"></i>
          <span>{{ plugin.stats.avg_rating?.toFixed(1) || '-' }}</span>
        </div>
      </div>
    </div>

    <!-- 卡片操作区 -->
    <div class="pc-actions">
      <!-- 已安装状态的操作按钮 -->
      <template v-if="isInstalled">
        <!-- 启用/禁用切换 -->
        <button
          @click="$emit('toggle-enable', !isEnabled)"
          class="pc-btn pc-btn-toggle"
          :class="{ active: isEnabled }"
          :disabled="plugin.is_builtin"
          :title="plugin.is_builtin ? '内置插件无法禁用' : (isEnabled ? '禁用插件' : '启用插件')"
        >
          <i :data-lucide="isEnabled ? 'power' : 'power-off'"></i>
          {{ isEnabled ? '运行中' : '已停止' }}
        </button>

        <!-- 配置按钮 -->
        <button
          @click="$emit('configure')"
          class="pc-btn pc-btn-config"
          title="配置插件"
        >
          <i data-lucide="settings"></i>
          配置
        </button>

        <!-- 卸载按钮（非内置） -->
        <button
          v-if="!plugin.is_builtin"
          @click="$emit('uninstall')"
          class="pc-btn pc-btn-danger"
          title="卸载插件"
        >
          <i data-lucide="trash-2"></i>
          卸载
        </button>
      </template>

      <!-- 未安装状态 -->
      <template v-else>
        <button
          @click="$emit('install')"
          class="pc-btn pc-btn-install"
        >
          <i data-lucide="download"></i>
          安装
        </button>

        <button
          @click="$emit('view-details')"
          class="pc-btn pc-btn-details"
        >
          <i data-lucide="info"></i>
          详情
        </button>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { Plugin, PluginCategory, PricingModel } from '@/api/plugins'

// ==================== Props ====================
interface Props {
  plugin: Plugin
  isInstalled: boolean
  isEnabled: boolean
  isSelected: boolean
  showSelectMode?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  showSelectMode: false,
})

// ==================== Emits ====================
defineEmits<{
  'toggle-select': []
  'install': []
  'uninstall': []
  'toggle-enable': [enable: boolean]
  'configure': []
  'view-details': []
}>()

// ==================== Helper Functions ====================
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

function getCategoryLabel(category: PluginCategory): string {
  const labels: Record<PluginCategory, string> = {
    platform: '平台发布',
    datasource: '数据源',
    workflow_node: '工作流节点',
    ui_theme: 'UI主题',
    analytics: '数据分析',
    utility: '工具类',
    integration: '集成类',
    ai_model: 'AI模型',
    tool: '工具',
    theme: '主题',
  }
  
  return labels[category] || category
}

function getPriceLabel(model: PricingModel): string {
  const labels: Record<PricingModel, string> = {
    free: '免费',
    freemium: '免费增值',
    paid: '付费',
    subscription: '订阅制',
  }
  
  return labels[model] || model
}

function formatNumber(num: number): string {
  if (num >= 10000) {
    return (num / 10000).toFixed(1) + 'w'
  }
  if (num >= 1000) {
    return (num / 1000).toFixed(1) + 'k'
  }
  return num.toString()
}
</script>

<style scoped>
.plugin-card {
  background: white;
  border-radius: 16px;
  border: 2px solid #e5e7eb;
  padding: 20px;
  transition: all 0.3s ease;
  position: relative;
  overflow: hidden;
}

.plugin-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 12px 24px rgba(0, 0, 0, 0.08);
  border-color: #d1d5db;
}

.plugin-card.is-installed {
  border-color: #10b981;
}

.plugin-card.is-enabled {
  background: linear-gradient(to bottom right, #ffffff, #f0fdf4);
}

.plugin-card.is-selected {
  border-color: #6366f1;
  box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.15);
}

.plugin-card.is-builtin {
  border-left: 4px solid #f59e0b;
}

/* Select Checkbox */
.pc-select {
  position: absolute;
  top: 16px;
  left: 16px;
  z-index: 10;
}

.pc-checkbox {
  width: 18px;
  height: 18px;
  cursor: pointer;
  accent-color: #6366f1;
}

/* Header */
.pc-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 16px;
}

.pc-icon {
  width: 56px;
  height: 56px;
  border-radius: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 28px;
  box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
}

.pc-status-tags {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

/* Tags */
.pc-tag {
  font-size: 11px;
  font-weight: 600;
  padding: 4px 8px;
  border-radius: 6px;
  text-transform: uppercase;
  letter-spacing: 0.3px;
}

.pc-tag-builtin {
  background: #fef3c7;
  color: #92400e;
}

.pc-tag-active {
  background: #d1fae5;
  color: #065f46;
}

.pc-tag-disabled {
  background: #fee2e2;
  color: #991b1b;
}

.pc-tag-available {
  background: #dbeafe;
  color: #1e40af;
}

.pc-tag-price {
  border: 1px solid currentColor;
  opacity: 0.8;
}

.price-free {
  color: #059669;
}

.price-freemium {
  color: #d97706;
}

.price-paid {
  color: #dc2626;
}

.price-subscription {
  color: #7c3aed;
}

/* Body */
.pc-body {
  margin-bottom: 16px;
}

.pc-title {
  font-size: 18px;
  font-weight: 700;
  color: #111827;
  margin-bottom: 4px;
  line-height: 1.3;
}

.pc-version {
  font-size: 13px;
  color: #9ca3af;
  margin-bottom: 8px;
}

.pc-description {
  font-size: 14px;
  color: #6b7280;
  line-height: 1.5;
  margin-bottom: 12px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.pc-meta {
  display: flex;
  gap: 16px;
  font-size: 13px;
  color: #9ca3af;
  margin-bottom: 12px;
}

.pc-category,
.pc-author {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.pc-stats {
  display: flex;
  gap: 16px;
  padding-top: 12px;
  border-top: 1px solid #f3f4f6;
}

.pc-stat-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  color: #6b7280;
}

/* Actions */
.pc-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.pc-btn {
  flex: 1;
  min-width: 80px;
  height: 36px;
  border: none;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
}

.pc-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.pc-btn-install {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  box-shadow: 0 2px 8px rgba(102, 126, 234, 0.25);
}

.pc-btn-install:hover:not(:disabled) {
  transform: scale(1.02);
  box-shadow: 0 4px 12px rgba(102, 126, 234, 0.35);
}

.pc-btn-toggle {
  background: white;
  color: #374151;
  border: 1px solid #d1d5db;
}

.pc-btn-toggle.active {
  background: #10b981;
  color: white;
  border-color: #10b981;
}

.pc-btn-toggle:hover:not(:disabled) {
  border-color: #9ca3af;
}

.pc-btn-config {
  background: #f3f4f6;
  color: #374151;
}

.pc-btn-config:hover:not(:disabled) {
  background: #e5e7eb;
}

.pc-btn-danger {
  background: white;
  color: #dc2626;
  border: 1px solid #fecaca;
}

.pc-btn-danger:hover:not(:disabled) {
  background: #fef2f2;
  border-color: #ef4444;
}

.pc-btn-details {
  background: white;
  color: #6366f1;
  border: 1px solid #c7d2fe;
}

.pc-btn-details:hover:not(:disabled) {
  background: #eef2ff;
  border-color: #6366f1;
}

/* Responsive */
@media (max-width: 480px) {
  .plugin-card {
    padding: 16px;
  }
  
  .pc-icon {
    width: 48px;
    height: 48px;
    font-size: 24px;
  }
  
  .pc-title {
    font-size: 16px;
  }
  
  .pc-actions {
    flex-direction: column;
  }
  
  .pc-btn {
    width: 100%;
  }
}
</style>