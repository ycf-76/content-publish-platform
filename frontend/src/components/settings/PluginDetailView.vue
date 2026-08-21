<template>
  <div class="pdv-wrap">
    <div class="pdv-header">
      <button class="pdv-back" @click="$emit('back')">
        <i data-lucide="arrow-left" style="width:16px;height:16px;"></i>
        <span>返回插件管理</span>
      </button>
    </div>

    <div v-if="!plugin" class="pdv-empty">
      <i data-lucide="package-open" style="width:32px;height:32px;opacity:0.4;"></i>
      <p>插件不存在</p>
    </div>

    <template v-else>
      <div class="pdv-hero">
        <div class="pdv-hero-icon">
          <span v-if="plugin.display_icon" class="pdv-hero-emoji">{{ plugin.display_icon }}</span>
          <i v-else data-lucide="puzzle" style="width:32px;height:32px;"></i>
        </div>
        <div class="pdv-hero-info">
          <div class="pdv-hero-name">{{ plugin.name }}</div>
          <div class="pdv-hero-meta">
            <span class="pdv-tag">{{ categoryLabel }}</span>
            <span class="pdv-tag pdv-tag-builtin" v-if="plugin.is_builtin">内置</span>
            <span class="pdv-tag pdv-tag-tp" v-else>第三方</span>
            <span class="pdv-version">v{{ plugin.version }}</span>
            <span class="pdv-author" v-if="plugin.author_name">
              <i data-lucide="user" style="width:12px;height:12px;"></i>
              {{ plugin.author_name }}
            </span>
          </div>
        </div>
        <div class="pdv-hero-actions">
          <button
            v-if="!pluginStore.isInstalled(plugin.id)"
            class="pdv-action-btn pdv-action-install"
            @click="handleInstall"
          >
            <i data-lucide="download" style="width:14px;height:14px;"></i>
            <span>安装</span>
          </button>
          <template v-else>
            <button
              class="pdv-action-btn"
              :class="pluginStore.isEnabled(plugin.id) ? 'pdv-action-on' : 'pdv-action-off'"
              @click="handleToggleEnable(!pluginStore.isEnabled(plugin.id))"
            >
              <i :data-lucide="pluginStore.isEnabled(plugin.id) ? 'power' : 'power-off'" style="width:14px;height:14px;"></i>
              <span>{{ pluginStore.isEnabled(plugin.id) ? '运行中' : '启动' }}</span>
            </button>
            <button
              v-if="!plugin.is_builtin"
              class="pdv-action-btn pdv-action-danger"
              @click="handleUninstall"
            >
              <i data-lucide="trash-2" style="width:14px;height:14px;"></i>
              <span>卸载</span>
            </button>
            <button
              class="pdv-action-btn pdv-action-secondary"
              @click="openConfig"
            >
              <i data-lucide="settings" style="width:14px;height:14px;"></i>
              <span>配置</span>
            </button>
          </template>
        </div>
      </div>

      <div class="pdv-body">
        <div class="pdv-section">
          <div class="pdv-section-title">插件说明</div>
          <div class="pdv-desc">{{ plugin.description || '暂无描述' }}</div>
        </div>

        <div class="pdv-section">
          <div class="pdv-section-title">使用说明</div>
          <div class="pdv-usage" v-html="usageHtml"></div>
        </div>

        <div class="pdv-section">
          <div class="pdv-section-title">使用详情</div>
          <div class="pdv-screenshots">
            <template v-if="screenshots.length > 0">
              <div
                v-for="(img, idx) in screenshots"
                :key="idx"
                class="pdv-screenshot-item"
              >
                <img :src="img" :alt="`截图 ${idx + 1}`" @click="previewImage(img)" />
              </div>
            </template>
            <div v-else class="pdv-no-screenshots">
              <i data-lucide="image" style="width:28px;height:28px;opacity:0.3;"></i>
              <span>暂无使用详情图片</span>
            </div>
          </div>
        </div>

        <div class="pdv-section" v-if="plugin.capabilities && plugin.capabilities.length > 0">
          <div class="pdv-section-title">功能特性</div>
          <div class="pdv-caps">
            <span v-for="cap in plugin.capabilities" :key="cap" class="pdv-cap-tag">{{ cap }}</span>
          </div>
        </div>

        <div class="pdv-section" v-if="plugin.permissions_required && plugin.permissions_required.length > 0">
          <div class="pdv-section-title">所需权限</div>
          <div class="pdv-perms">
            <span v-for="perm in plugin.permissions_required" :key="perm" class="pdv-perm-tag">{{ perm }}</span>
          </div>
        </div>
      </div>
    </template>

    <transition name="slide-left">
      <PluginConfigDrawer
        v-if="showConfig"
        :plugin="plugin!"
        :config="pluginStore.getConfig(plugin!.id) || {}"
        @close="showConfig = false"
        @save-config="handleSaveConfig"
      />
    </transition>

    <transition name="fade">
      <div v-if="previewImg" class="pdv-preview-overlay" @click="previewImg = null">
        <img :src="previewImg" class="pdv-preview-img" />
      </div>
    </transition>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, nextTick } from 'vue'
import { createIcons, icons } from 'lucide'
import { usePluginStore } from '@/stores/plugin'
import type { Plugin } from '@/api/plugins'
import PluginConfigDrawer from '@/components/plugins/PluginConfigDrawer.vue'

const props = defineProps<{ plugin: Plugin | null }>()
const emit = defineEmits<{ back: [] }>()

const pluginStore = usePluginStore()
const showConfig = ref(false)
const previewImg = ref<string | null>(null)

const CATEGORY_LABELS: Record<string, string> = {
  UI_THEME: 'UI 主题',
  PLATFORM: '平台发布',
  DATASOURCE: '数据源',
  WORKFLOW_NODE: '工作流节点',
  ANALYTICS: '数据分析',
  UTILITY: '工具类',
}

const PLUGIN_USAGE: Record<string, { usage: string; screenshots: string[] }> = {
  'crab-companion': {
    usage: `<ol>
<li>在聊天页面中，螃蟹会自动出现在输入框上方</li>
<li>拖拽螃蟹到任意位置，松手后若靠近输入框会自动吸回</li>
<li>点击螃蟹可以触发交互反馈（气泡对话）</li>
<li>在插件管理中启用/禁用螃蟹插件</li>
</ol>`,
    screenshots: [],
  },
  'cat-companion': {
    usage: `<ol>
<li>在聊天页面中，小猫会趴在输入框上方</li>
<li>小猫会随机打哈欠、伸懒腰，非常慵懒</li>
<li>拖拽小猫到任意位置，松手后若靠近输入框会自动吸回</li>
<li>点击小猫触发互动（喵叫、呼噜声等）</li>
<li>鼠标悬停时小猫会撒娇回应</li>
<li>可在配置中调整猫咪大小和慵懒程度</li>
</ol>`,
    screenshots: [],
  },
}

const categoryLabel = computed(() => {
  if (!props.plugin) return ''
  return CATEGORY_LABELS[(props.plugin.category || '').toUpperCase()] || props.plugin.category || ''
})

const usageHtml = computed(() => {
  if (!props.plugin) return ''
  const custom = PLUGIN_USAGE[props.plugin.id]
  if (custom) return custom.usage
  return `<p>安装并启用此插件后，相关功能将自动集成到系统中。可在插件管理页面随时启用或禁用。</p>`
})

const screenshots = computed(() => {
  if (!props.plugin) return []
  const custom = PLUGIN_USAGE[props.plugin.id]
  if (custom) return custom.screenshots
  const manifest = (props.plugin as any).manifest_json
  if (manifest?.screenshots && Array.isArray(manifest.screenshots)) {
    return manifest.screenshots
  }
  return []
})

function previewImage(src: string) {
  previewImg.value = src
}

async function handleInstall() {
  if (!props.plugin) return
  try {
    await pluginStore.installPlugin(props.plugin.id)
    await pluginStore.loadInstalledPlugins()
  } catch (e: any) { alert('安装失败: ' + e.message) }
}

async function handleUninstall() {
  if (!props.plugin || props.plugin.is_builtin) return
  if (!confirm(`确定要卸载 "${props.plugin.name}" 吗？`)) return
  try {
    await pluginStore.uninstallPlugin(props.plugin.id)
    await pluginStore.loadInstalledPlugins()
  } catch (e: any) { alert('卸载失败: ' + e.message) }
}

async function handleToggleEnable(enable: boolean) {
  if (!props.plugin) return
  try { await pluginStore.togglePluginEnabled(props.plugin.id, enable) }
  catch (e: any) { alert('操作失败: ' + e.message) }
}

function openConfig() {
  if (!props.plugin) return
  showConfig.value = true
  pluginStore.loadPluginConfig(props.plugin.id)
}

async function handleSaveConfig(pluginId: string, config: Record<string, any>) {
  try {
    await pluginStore.updatePluginConfig(pluginId, { config_json: config })
    showConfig.value = false
  } catch (e: any) { alert('保存失败: ' + e.message) }
}

onMounted(() => {
  nextTick(() => { try { createIcons({ icons }) } catch {} })
})
</script>

<style scoped>
.pdv-wrap {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.pdv-header {
  flex-shrink: 0;
}

.pdv-back {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  border: 1px solid var(--ma-border, #E5E7EB);
  border-radius: 8px;
  background: var(--ma-bg-subtle, #EEF0F4);
  color: var(--ma-text-secondary, #6B7280);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.15s;
}

.pdv-back:hover {
  color: var(--ma-text-primary, #111827);
  background: var(--ma-accent, rgba(59, 108, 246, 0.08));
}

.pdv-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 60px 0;
  color: var(--ma-text-tertiary, #6B7280);
  font-size: 13px;
}

/* ===== Hero ===== */

.pdv-hero {
  display: flex;
  align-items: flex-start;
  gap: 16px;
  padding: 20px;
  background: var(--ma-bg-subtle, #EEF0F4);
  border: 1px solid var(--ma-border, #E5E7EB);
  border-radius: 12px;
}

.pdv-hero-icon {
  width: 56px;
  height: 56px;
  border-radius: 12px;
  background: var(--ma-accent, rgba(59, 108, 246, 0.12));
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--ma-primary, #3B6CF6);
  flex-shrink: 0;
}

.pdv-hero-emoji {
  font-size: 32px;
  line-height: 1;
}

.pdv-hero-info {
  flex: 1;
  min-width: 0;
}

.pdv-hero-name {
  font-size: 18px;
  font-weight: 700;
  color: var(--ma-text-primary, #111827);
}

.pdv-hero-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 6px;
  flex-wrap: wrap;
}

.pdv-tag {
  font-size: 11px;
  padding: 2px 10px;
  border-radius: 9999px;
  background: var(--ma-bg-subtle, #EEF0F4);
  color: var(--ma-text-secondary, #6B7280);
  border: 1px solid var(--ma-border, #E5E7EB);
}

.pdv-tag-builtin {
  background: var(--ma-accent, rgba(59, 108, 246, 0.12));
  color: var(--ma-primary, #3B6CF6);
  border-color: rgba(59, 108, 246, 0.2);
}

.pdv-tag-tp {
  background: rgba(245, 158, 11, 0.1);
  color: #F59E0B;
  border-color: rgba(245, 158, 11, 0.2);
}

.pdv-version {
  font-size: 11px;
  color: var(--ma-text-tertiary, #6B7280);
}

.pdv-author {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: var(--ma-text-tertiary, #6B7280);
}

.pdv-hero-actions {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-shrink: 0;
  flex-wrap: wrap;
}

/* ===== Action Buttons ===== */

.pdv-action-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  border: none;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
  white-space: nowrap;
}

.pdv-action-on {
  background: rgba(16, 185, 129, 0.12);
  color: #10B981;
  border: 1px solid rgba(16, 185, 129, 0.25);
}

.pdv-action-on:hover { background: rgba(16, 185, 129, 0.2); }

.pdv-action-off {
  background: var(--ma-primary, #3B6CF6);
  color: #FFFFFF;
  border: 1px solid var(--ma-primary, #3B6CF6);
}

.pdv-action-off:hover { background: #2563EB; }

.pdv-action-install {
  background: var(--ma-primary, #3B6CF6);
  color: #FFFFFF;
  border: 1px solid var(--ma-primary, #3B6CF6);
}

.pdv-action-install:hover { background: #2563EB; }

.pdv-action-danger {
  background: rgba(239, 68, 68, 0.08);
  color: var(--ma-destructive, #EF4444);
  border: 1px solid rgba(239, 68, 68, 0.2);
}

.pdv-action-danger:hover { background: rgba(239, 68, 68, 0.15); }

.pdv-action-secondary {
  background: var(--ma-bg-subtle, #EEF0F4);
  color: var(--ma-text-secondary, #6B7280);
  border: 1px solid var(--ma-border, #E5E7EB);
}

.pdv-action-secondary:hover { background: var(--ma-accent, rgba(59, 108, 246, 0.08)); color: var(--ma-text-primary, #111827); }

/* ===== Body ===== */

.pdv-body {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.pdv-section {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.pdv-section-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--ma-text-primary, #111827);
  padding-bottom: 8px;
  border-bottom: 1px solid var(--ma-border, #E5E7EB);
}

.pdv-desc {
  font-size: 13px;
  line-height: 1.8;
  color: var(--ma-text-secondary, #374151);
}

.pdv-usage {
  font-size: 13px;
  line-height: 1.8;
  color: var(--ma-text-secondary, #374151);
}

.pdv-usage :deep(ol),
.pdv-usage :deep(ul) { padding-left: 20px; margin: 0; }
.pdv-usage :deep(li) { margin-bottom: 6px; }
.pdv-usage :deep(p) { margin: 0; }

.pdv-screenshots {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 10px;
}

.pdv-screenshot-item {
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid var(--ma-border, #E5E7EB);
  cursor: pointer;
  transition: all 0.15s;
}

.pdv-screenshot-item:hover {
  border-color: var(--ma-primary, #3B6CF6);
  box-shadow: 0 2px 12px rgba(59, 108, 246, 0.15);
}

.pdv-screenshot-item img { width: 100%; display: block; }

.pdv-no-screenshots {
  grid-column: 1 / -1;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 32px 0;
  color: var(--ma-text-tertiary, #6B7280);
  font-size: 12px;
}

.pdv-caps, .pdv-perms {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.pdv-cap-tag {
  font-size: 11px;
  padding: 3px 10px;
  border-radius: 9999px;
  background: rgba(59, 108, 246, 0.08);
  color: var(--ma-primary, #3B6CF6);
  border: 1px solid rgba(59, 108, 246, 0.15);
}

.pdv-perm-tag {
  font-size: 11px;
  padding: 3px 10px;
  border-radius: 9999px;
  background: rgba(245, 158, 11, 0.08);
  color: #D97706;
  border: 1px solid rgba(245, 158, 11, 0.15);
}

/* ===== Image Preview ===== */

.pdv-preview-overlay {
  position: fixed;
  inset: 0;
  z-index: 2000;
  background: rgba(0, 0, 0, 0.85);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
}

.pdv-preview-img {
  max-width: 90vw;
  max-height: 90vh;
  border-radius: 8px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
}

/* ===== Transitions ===== */

.slide-left-enter-active, .slide-left-leave-active { transition: transform 0.3s ease; }
.slide-left-enter-from, .slide-left-leave-to { transform: translateX(100%); }

.fade-enter-active, .fade-leave-active { transition: opacity 0.2s ease; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>