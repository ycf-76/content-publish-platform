<template>
  <div class="modal-overlay" @click.self="$emit('close')">
    <div class="modal-container" :class="{ 'is-open': true }">
      <!-- 模态框头部 -->
      <div class="modal-header">
        <div class="mh-left">
          <div 
            class="mh-icon"
            :style="{ background: getCategoryColor(plugin.category) }"
          >
            {{ plugin.display_icon || getDefaultIcon(plugin.category) }}
          </div>
          <div>
            <h2 class="mh-title">{{ plugin.name }}</h2>
            <p class="mh-version">v{{ plugin.version }} · {{ getCategoryLabel(plugin.category) }}</p>
          </div>
        </div>

        <button @click="$emit('close')" class="mh-close-btn">
          <i data-lucide="x"></i>
        </button>
      </div>

      <!-- 模态框内容 -->
      <div class="modal-body">
        <!-- 标签区 -->
        <div class="md-tags">
          <span v-if="plugin.is_builtin" class="md-tag md-tag-builtin">🔒 内置插件</span>
          <span 
            class="md-tag md-tag-price"
            :class="`price-${plugin.pricing_model}`"
          >
            {{ getPriceLabel(plugin.pricing_model) }}
          </span>
          <span v-if="plugin.status === 'active'" class="md-tag md-tag-status-active">✅ 正常运行</span>
          <span v-else-if="plugin.status === 'deprecated'" class="md-tag md-tag-status-deprecated">⚠️ 已弃用</span>
          
          <!-- 能力标签 -->
          <span 
            v-for="capability in plugin.capabilities.slice(0, 5)" 
            :key="capability"
            class="md-tag md-tag-capability"
          >
            {{ formatCapability(capability) }}
          </span>
        </div>

        <!-- 描述 -->
        <section class="md-section">
          <h3 class="md-section-title">📝 简介</h3>
          <p class="md-description">{{ plugin.description }}</p>
        </section>

        <!-- 统计信息（如果有） -->
        <section v-if="plugin.stats" class="md-section md-stats-grid">
          <div class="md-stat-item">
            <i data-lucide="download"></i>
            <div>
              <strong>{{ formatNumber(plugin.stats.install_count) }}</strong>
              <span>安装量</span>
            </div>
          </div>
          <div class="md-stat-item">
            <i data-lucide="users"></i>
            <div>
              <strong>{{ formatNumber(plugin.stats.active_users) }}</strong>
              <span>活跃用户</span>
            </div>
          </div>
          <div class="md-stat-item">
            <i data-lucide="star"></i>
            <div>
              <strong>{{ plugin.stats.avg_rating?.toFixed(1) || '-' }}</strong>
              <span>平均评分</span>
            </div>
          </div>
          <div class="md-stat-item">
            <i data-lucide="message-square"></i>
            <div>
              <strong>{{ plugin.stats.review_count || 0 }}</strong>
              <span>评价数</span>
            </div>
          </div>
        </section>

        <!-- 作者信息 -->
        <section class="md-section">
          <h3 class="md-section-title">👤 开发者</h3>
          <div class="md-author-info">
            <div class="md-avatar">
              {{ (plugin.author_name || '?').charAt(0).toUpperCase() }}
            </div>
            <div>
              <p class="md-author-name">{{ plugin.author_name || '未知作者' }}</p>
              <p v-if="plugin.author_email" class="md-author-email">{{ plugin.author_email }}</p>
            </div>
          </div>
        </section>

        <!-- 权限要求 -->
        <section v-if="plugin.permissions_required?.length > 0" class="md-section">
          <h3 class="md-section-title">🔐 权限要求</h3>
          <div class="md-permissions">
            <div 
              v-for="permission in plugin.permissions_required" 
              :key="permission"
              class="md-permission-item"
            >
              <i data-lucide="shield-check"></i>
              <code>{{ permission }}</code>
            </div>
          </div>
        </section>

        <!-- 事件订阅/发布 -->
        <section 
          v-if="hasEvents"
          class="md-section"
        >
          <h3 class="md-section-title">📡 事件通信</h3>
          
          <!-- 订阅的事件 -->
          <div v-if="eventsSubscribes.length > 0" class="md-event-group">
            <h4 class="md-event-label">📥 订阅事件:</h4>
            <div class="md-events-list">
              <code 
                v-for="event in eventsSubscribes" 
                :key="event"
                class="md-event-badge event-subscribe"
              >
                {{ event }}
              </code>
            </div>
          </div>

          <!-- 发布的事件 -->
          <div v-if="eventsEmits.length > 0" class="md-event-group">
            <h4 class="md-event-label">📤 发布事件:</h4>
            <div class="md-events-list">
              <code 
                v-for="event in eventsEmits" 
                :key="event"
                class="md-event-badge event-emit"
              >
                {{ event }}
              </code>
            </div>
          </div>
        </section>

        <!-- 版本历史（简化版） -->
        <section class="md-section">
          <h3 class="md-section-title">📅 更新时间</h3>
          <div class="md-time-info">
            <div class="md-time-item">
              <span class="md-time-label">首次发布</span>
              <time class="md-time-value">{{ formatDate(plugin.created_at) }}</time>
            </div>
            <div class="md-time-item">
              <span class="md-time-label">最近更新</span>
              <time class="md-time-value">{{ formatDate(plugin.updated_at) }}</time>
            </div>
          </div>
        </section>
      </div>

      <!-- 模态框底部操作区 -->
      <div class="modal-footer">
        <button 
          type="button"
          @click="$emit('close')"
          class="mf-btn mf-btn-cancel"
        >
          关闭
        </button>

        <template v-if="!isInstalled">
          <button 
            type="button"
            @click="$emit('install')"
            class="mf-btn mf-btn-primary"
          >
            <i data-lucide="download"></i>
            立即安装
          </button>
        </template>

        <template v-else>
          <button 
            type="button"
            @click="$emit('configure')"
            class="mf-btn mf-btn-secondary"
          >
            <i data-lucide="settings"></i>
            配置插件
          </button>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { Plugin, PluginCategory, PricingModel } from '@/api/plugins'

// ==================== Props & Emits ====================
interface Props {
  plugin: Plugin
  isInstalled?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  isInstalled: false,
})

defineEmits<{
  close: []
  install: []
  configure: []
}>()

// ==================== Computed ====================

/**
 * 从plugin对象中提取事件信息（简化处理）
 * 实际应该从完整的plugin.json中读取
 */
const eventsSubscribes = computed(() => {
  // TODO: 从API获取完整manifest
  // 这里返回示例数据用于演示
  if (props.plugin.category === 'platform') {
    return ['workflow:node_completed:*']
  }
  if (props.plugin.category === 'datasource') {
    return ['system:timer:*', 'datasource:refresh']
  }
  return []
})

const eventsEmits = computed(() => {
  // TODO: 同上
  if (props.plugin.category === 'platform') {
    return ['content:published', 'content:publish_failed']
  }
  if (props.plugin.category === 'workflow_node') {
    return ['workflow:node_started:copywrite', 'workflow:node_completed:copywrite']
  }
  return []
})

const hasEvents = computed(() => 
  eventsSubscribes.value.length > 0 || eventsEmits.value.length > 0
)

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

function formatCapability(capability: string): string {
  const labels: Record<string, string> = {
    authenticate: '认证管理',
    publish: '内容发布',
    get_analytics: '数据分析',
    delete_content: '内容删除',
    search_trending: '趋势搜索',
    get_trending: '热点抓取',
    execute: '执行任务',
    health_check: '健康检查',
  }
  
  return labels[capability] || capability.replace(/_/g, ' ')
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

function formatDate(dateStr: string): string {
  try {
    const date = new Date(dateStr)
    return date.toLocaleDateString('zh-CN', {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
    })
  } catch {
    return dateStr
  }
}
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.6);
  z-index: 2000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
  animation: fadeIn 0.25s ease;
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

.modal-container {
  width: 720px;
  max-width: 100%;
  max-height: 90vh;
  background: white;
  border-radius: 24px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  animation: scaleIn 0.3s ease;
}

@keyframes scaleIn {
  from { 
    opacity: 0;
    transform: scale(0.95);
  }
  to { 
    opacity: 1;
    transform: scale(1);
  }
}

/* Header */
.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 28px 32px;
  border-bottom: 1px solid #e5e7eb;
  background: linear-gradient(to bottom right, #f9fafb, #ffffff);
}

.mh-left {
  display: flex;
  align-items: center;
  gap: 16px;
}

.mh-icon {
  width: 72px;
  height: 72px;
  border-radius: 18px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 36px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
}

.mh-title {
  font-size: 26px;
  font-weight: 800;
  color: #111827;
  margin-bottom: 4px;
}

.mh-version {
  font-size: 14px;
  color: #6b7280;
  font-weight: 500;
}

.mh-close-btn {
  width: 40px;
  height: 40px;
  border: none;
  background: #f3f4f6;
  border-radius: 10px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}

.mh-close-btn:hover {
  background: #e5e7eb;
  color: #dc2626;
  transform: rotate(90deg);
}

/* Body */
.modal-body {
  flex: 1;
  overflow-y: auto;
  padding: 32px;
}

/* Tags */
.md-tags {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 28px;
}

.md-tag {
  font-size: 12px;
  font-weight: 600;
  padding: 6px 12px;
  border-radius: 8px;
  text-transform: uppercase;
  letter-spacing: 0.3px;
}

.md-tag-builtin {
  background: #fef3c7;
  color: #92400e;
}

.price-free {
  background: #d1fae5;
  color: #065f46;
  border: 1px solid #10b981;
}

.price-freemium {
  background: #fef3c7;
  color: #92400e;
  border: 1px solid #f59e0b;
}

.price-paid {
  background: #fee2e2;
  color: #991b1b;
  border: 1px solid #ef4444;
}

.price-subscription {
  background: #ede9fe;
  color: #5b21b6;
  border: 1px solid #8b5cf6;
}

.md-tag-status-active {
  background: #d1fae5;
  color: #065f46;
}

.md-tag-status-deprecated {
  background: #fee2e2;
  color: #991b1b;
}

.md-tag-capability {
  background: #eef2ff;
  color: #3730a3;
  border: 1px solid #c7d2fe;
}

/* Sections */
.md-section {
  margin-bottom: 28px;
}

.md-section:last-child {
  margin-bottom: 0;
}

.md-section-title {
  font-size: 17px;
  font-weight: 700;
  color: #111827;
  margin-bottom: 14px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.md-description {
  font-size: 15px;
  line-height: 1.7;
  color: #4b5563;
}

/* Stats Grid */
.md-stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 16px;
  background: linear-gradient(135deg, #f9fafb 0%, #ffffff 100%);
  border: 1px solid #e5e7eb;
  border-radius: 16px;
  padding: 24px;
}

.md-stat-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  background: white;
  border-radius: 12px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
}

.md-stat-item i {
  width: 32px;
  height: 32px;
  color: #6366f1;
}

.md-stat-item strong {
  display: block;
  font-size: 22px;
  font-weight: 800;
  color: #111827;
  line-height: 1.2;
}

.md-stat-item span {
  font-size: 13px;
  color: #6b7280;
}

/* Author */
.md-author-info {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 20px;
  background: #f9fafb;
  border-radius: 12px;
}

.md-avatar {
  width: 56px;
  height: 56px;
  border-radius: 50%;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
  font-weight: 700;
}

.md-author-name {
  font-size: 16px;
  font-weight: 600;
  color: #111827;
  margin-bottom: 4px;
}

.md-author-email {
  font-size: 14px;
  color: #6b7280;
}

/* Permissions */
.md-permissions {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.md-permission-item {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  background: #fffbeb;
  border: 1px solid #fde68a;
  border-radius: 10px;
  font-size: 14px;
  color: #92400e;
}

.md-permission-item i {
  width: 18px;
  height: 18px;
  color: #f59e0b;
  flex-shrink: 0;
}

.md-permission-item code {
  font-family: 'Monaco', monospace;
  font-size: 13px;
  background: none;
  color: inherit;
}

/* Events */
.md-event-group {
  margin-bottom: 16px;
}

.md-event-group:last-child {
  margin-bottom: 0;
}

.md-event-label {
  font-size: 14px;
  font-weight: 600;
  color: #374151;
  margin-bottom: 10px;
}

.md-events-list {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.md-event-badge {
  font-size: 12px;
  font-weight: 600;
  padding: 6px 12px;
  border-radius: 8px;
  font-family: 'Monaco', 'Menlo', monospace;
}

.event-subscribe {
  background: #dbeafe;
  color: #1e40af;
  border: 1px solid #93c5fd;
}

.event-emit {
  background: #fce7f3;
  color: #9d174d;
  border: 1px solid #f9a8d4;
}

/* Time Info */
.md-time-info {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
}

.md-time-item {
  padding: 16px;
  background: #f9fafb;
  border-radius: 10px;
}

.md-time-label {
  display: block;
  font-size: 13px;
  color: #6b7280;
  margin-bottom: 6px;
}

.md-time-value {
  font-size: 15px;
  font-weight: 600;
  color: #111827;
}

/* Footer */
.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding: 24px 32px;
  border-top: 1px solid #e5e7eb;
  background: #f9fafb;
}

.mf-btn {
  height: 46px;
  padding: 0 28px;
  border-radius: 12px;
  font-size: 15px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  border: none;
}

.mf-btn-cancel {
  background: white;
  color: #374151;
  border: 1px solid #d1d5db;
}

.mf-btn-cancel:hover {
  background: #f9fafb;
}

.mf-btn-secondary {
  background: #f3f4f6;
  color: #374151;
  border: 1px solid #d1d5db;
}

.mf-btn-secondary:hover {
  background: #e5e7eb;
}

.mf-btn-primary {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  box-shadow: 0 4px 12px rgba(102, 126, 234, 0.35);
}

.mf-btn-primary:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 16px rgba(102, 126, 234, 0.45);
}

/* Scrollbar */
.modal-body::-webkit-scrollbar {
  width: 8px;
}

.modal-body::-webkit-scrollbar-track {
  background: #f1f1f1;
  border-radius: 4px;
}

.modal-body::-webkit-scrollbar-thumb {
  background: #c1c1c1;
  border-radius: 4px;
}

.modal-body::-webkit-scrollbar-thumb:hover {
  background: #a8a8a8;
}
</style>