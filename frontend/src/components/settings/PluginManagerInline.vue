<template>
  <div class="pmi-wrap">
    <div class="pmi-toolbar">
      <div class="pmi-search-box">
        <Search :size="14" />
        <input
          type="text"
          v-model="pluginStore.filters.q"
          placeholder="搜索插件..."
          @input="debouncedSearch"
          class="pmi-search-input"
        />
        <button v-if="pluginStore.filters.q" @click="clearSearch" class="pmi-search-clear">
          <X :size="12" />
        </button>
      </div>
      <button @click="refreshPlugins" :disabled="pluginStore.loading" class="pmi-icon-btn" title="刷新">
        <RefreshCw :size="14" :class="{ spinning: pluginStore.loading }" />
      </button>
      <button @click="showGithubInstallModal = true" class="pmi-icon-btn pmi-github-btn" title="从 GitHub 安装插件">
        <img src="/icons/github-logo.svg?v=4" alt="GitHub" style="width:18px;height:18px;filter:brightness(0) invert(1);" />
      </button>
      <button @click="triggerUpload" class="pmi-icon-btn pmi-upload-btn" title="上传第三方插件">
        <Upload :size="14" />
      </button>
      <input
        ref="fileInputRef"
        type="file"
        accept=".zip"
        style="display:none"
        @change="handleFileUpload"
      />
    </div>

    <!-- GitHub 安装弹窗 ⭐新增 -->
    <div v-if="showGithubInstallModal" class="pmi-modal-overlay" @click.self="closeGithubModal">
      <div class="pmi-modal">
        <div class="pmi-modal-header">
          <h3 class="pmi-modal-title"><img src="/icons/github-logo.svg?v=4" alt="GitHub" style="width:22px;height:22px;vertical-align:middle;margin-right:8px;" />从 GitHub 安装插件</h3>
          <button @click="closeGithubModal" class="pmi-modal-close"><X :size="16" /></button>
        </div>
        
        <div class="pmi-modal-body">
          <div class="pmi-form-group">
            <label class="pmi-form-label">GitHub 仓库 URL</label>
            <input
              type="url"
              v-model="githubForm.repoUrl"
              placeholder="https://github.com/username/plugin-repo"
              class="pmi-form-input"
              @keyup.enter="handleGithubInstall"
            />
            <p class="pmi-form-hint">支持 GitHub 公开仓库，将下载最新版本的插件</p>
          </div>

          <div class="pmi-form-group">
            <label class="pmi-form-label">分支名（可选）</label>
            <input
              type="text"
              v-model="githubForm.branch"
              placeholder="main"
              class="pmi-form-input"
            />
          </div>

          <div class="pmi-form-group">
            <label class="pmi-checkbox-wrapper">
              <input type="checkbox" v-model="githubForm.useGitClone" class="pmi-checkbox" />
              <span>使用 Git Clone 模式（需要本地安装 Git）</span>
            </label>
            <p class="pmi-form-hint">启用后可使用 git pull 快速更新，但需要系统已安装 Git</p>
          </div>
        </div>

        <div class="pmi-modal-footer">
          <button @click="closeGithubModal" class="pmi-btn pmi-btn-secondary">取消</button>
          <button 
            @click="handleGithubInstall" 
            class="pmi-btn pmi-btn-primary"
            :disabled="githubInstalling || !githubForm.repoUrl"
          >
            <Loader v-if="githubInstalling" :size="14" class="spinning" />
            <Download v-else :size="14" />
            {{ githubInstalling ? '安装中...' : '开始安装' }}
          </button>
        </div>

        <!-- 安装结果 -->
        <div v-if="githubInstallResult" class="pmi-install-result" :class="githubInstallResult.success ? 'success' : 'error'">
          <CheckCircle v-if="githubInstallResult.success" :size="16" />
          <AlertCircle v-else :size="16" />
          <div>
            <p class="pmi-result-message">{{ githubInstallResult.message }}</p>
            <p v-if="githubInstallResult.plugin_name" class="pmi-result-details">
              插件：{{ githubInstallResult.plugin_name }} v{{ githubInstallResult.version }}
            </p>
          </div>
        </div>
      </div>
    </div>

    <div v-if="uploadStatus" class="pmi-upload-status" :class="uploadStatus.type">
      <CheckCircle v-if="uploadStatus.type === 'success'" :size="14" />
      <AlertCircle v-else-if="uploadStatus.type === 'error'" :size="14" />
      <Loader v-else :size="14" />
      <span>{{ uploadStatus.message }}</span>
      <button @click="uploadStatus = null" class="pmi-error-close"><X :size="12" /></button>
    </div>

    <div v-if="pluginStore.error" class="pmi-error">
      <AlertCircle :size="14" />
      <span>{{ pluginStore.error }}</span>
      <button @click="pluginStore.clearError()" class="pmi-error-close"><X :size="12" /></button>
    </div>

    <div v-if="pluginStore.loading && pluginStore.allPlugins.length === 0" class="pmi-loading">
      <div class="pmi-spinner"></div>
      <span>加载中...</span>
    </div>

    <div v-else-if="!pluginStore.loading && pluginStore.allPlugins.length === 0" class="pmi-empty">
      <PackageOpen :size="32" style="opacity:0.4" />
      <p>暂无插件</p>
    </div>

    <div v-else class="pmi-categories">
      <div
        v-for="group in groupedPlugins"
        :key="group.key"
        class="pmi-category"
      >
        <div class="pmi-category-header">
          <span class="pmi-category-label">{{ group.label }}</span>
        </div>
        <div class="pmi-grid">
          <div
            v-for="plugin in group.plugins"
            :key="plugin.id"
            class="pmi-card"
            :class="{
              'pmi-card-enabled': pluginStore.isEnabled(plugin.id)
            }"
          >
            <div class="pmi-card-top" @click="openDetail(plugin)">
              <div class="pmi-card-icon">
                <span v-if="plugin.display_icon" class="pmi-card-emoji">{{ plugin.display_icon }}</span>
                <Puzzle v-else :size="18" />
              </div>
              <div class="pmi-card-info">
                <div class="pmi-card-name">{{ plugin.name }}</div>
                <div class="pmi-card-desc">{{ plugin.description }}</div>
              </div>
              <div class="pmi-card-expand-icon">
                <ChevronRight :size="14" />
              </div>
            </div>

            <div class="pmi-card-bottom">
              <div class="pmi-card-tags">
                <span class="pmi-card-tag pmi-card-tag-builtin" v-if="plugin.is_builtin">内置</span>
                <span class="pmi-card-tag pmi-card-tag-tp" v-else>第三方</span>
              </div>
              <div class="pmi-card-actions">
                <button
                  v-if="!pluginStore.isInstalled(plugin.id)"
                  class="pmi-enable-btn pmi-enable-btn-install"
                  @click="handleInstall(plugin)"
                >
                  <Download :size="12" />
                  <span>安装</span>
                </button>
                <template v-else>
                  <button
                    class="pmi-enable-btn"
                    :class="pluginStore.isEnabled(plugin.id) ? 'pmi-enable-btn-on' : 'pmi-enable-btn-off'"
                    @click="handleToggleEnable(plugin, !pluginStore.isEnabled(plugin.id))"
                  >
                    <Power v-if="pluginStore.isEnabled(plugin.id) " :size="12" /><PowerOff v-else :size="12" />
                    <span>{{ pluginStore.isEnabled(plugin.id) ? '运行中' : '启动' }}</span>
                  </button>
                  <button
                    v-if="!plugin.is_builtin"
                    class="pmi-card-btn pmi-card-btn-danger"
                    @click="handleUninstall(plugin)"
                    title="卸载"
                  >
                    <Trash2 :size="13" />
                  </button>
                  <button
                    class="pmi-card-btn"
                    @click="openConfigPanel(plugin)"
                    title="配置"
                  >
                    <Settings :size="13" />
                  </button>
                </template>
              </div>
            </div>

          </div>
        </div>
      </div>
    </div>

    <transition name="slide-left">
      <PluginConfigDrawer
        v-if="configPlugin"
        :plugin="configPlugin"
        :config="pluginStore.getConfig(configPlugin.id) || {}"
        @close="configPlugin = null"
        @save-config="handleSaveConfig"
      />
    </transition>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, reactive } from 'vue'
import {
  AlertCircle, CheckCircle, ChevronRight, Download,
  Github, Loader, PackageOpen, Power, PowerOff, Puzzle,
  RefreshCw, Search, Settings, Trash2, Upload, X,
} from 'lucide-vue-next'
import { usePluginStore } from '@/stores/plugin'
import type { Plugin } from '@/api/plugins'
import pluginsApi from '@/api/plugins'
import PluginConfigDrawer from '@/components/plugins/PluginConfigDrawer.vue'

const pluginStore = usePluginStore()
const configPlugin = ref<Plugin | null>(null)
const fileInputRef = ref<HTMLInputElement | null>(null)
const uploadStatus = ref<{ type: 'success' | 'error' | 'loading'; message: string } | null>(null)

// GitHub 安装相关状态 ⭐新增
const showGithubInstallModal = ref(false)
const githubInstalling = ref(false)
const githubInstallResult = ref<{
  success: boolean
  plugin_id?: string
  plugin_name?: string
  version?: string
  message: string
  install_method?: string
} | null>(null)

const githubForm = reactive({
  repoUrl: '',
  branch: 'main',
  useGitClone: false,
})

const emit = defineEmits<{ selectPlugin: [plugin: Plugin] }>()

const CATEGORY_META: Record<string, { label: string; icon: string; order: number }> = {
  UI_THEME:     { label: 'UI 主题',   icon: '🎨', order: 1 },
  PLATFORM:     { label: '平台发布',   icon: '🚀', order: 2 },
  DATASOURCE:   { label: '数据源',     icon: '🔗', order: 3 },
  WORKFLOW_NODE:{ label: '工作流节点', icon: '⚡', order: 4 },
  ANALYTICS:    { label: '数据分析',   icon: '📊', order: 5 },
  UTILITY:      { label: '工具类',     icon: '🔧', order: 6 },
}

function openDetail(plugin: Plugin) {
  emit('selectPlugin', plugin)
}

const filteredPlugins = computed(() => {
  let list = pluginStore.allPlugins
  if (pluginStore.filters.q) {
    const keyword = pluginStore.filters.q.toLowerCase()
    list = list.filter(p =>
      p.name.toLowerCase().includes(keyword) ||
      p.description.toLowerCase().includes(keyword)
    )
  }
  return list
})

const groupedPlugins = computed(() => {
  const map = new Map<string, Plugin[]>()
  for (const p of filteredPlugins.value) {
    const cat = (p.category || 'UTILITY').toUpperCase()
    if (!map.has(cat)) map.set(cat, [])
    map.get(cat)!.push(p)
  }
  const groups: { key: string; label: string; icon: string; order: number; plugins: Plugin[] }[] = []
  for (const [cat, plugins] of map) {
    const meta = CATEGORY_META[cat] || { label: cat, icon: '📦', order: 99 }
    groups.push({ key: cat, ...meta, plugins })
  }
  groups.sort((a, b) => a.order - b.order)
  return groups
})

let searchTimeout: ReturnType<typeof setTimeout> | null = null
function debouncedSearch() {
  if (searchTimeout) clearTimeout(searchTimeout)
  searchTimeout = setTimeout(() => pluginStore.loadPlugins(), 300)
}
function clearSearch() {
  pluginStore.filters.q = ''
  pluginStore.loadPlugins()
}
async function refreshPlugins() {
  try {
    await Promise.all([pluginStore.loadPlugins(), pluginStore.loadInstalledPlugins()])
    
  } catch (e) { console.error('Failed to refresh:', e) }
}

async function handleInstall(plugin: Plugin) {
  try {
    await pluginStore.installPlugin(plugin.id)
    await refreshPlugins()
  } catch (e: any) { alert('安装失败: ' + e.message) }
}
async function handleUninstall(plugin: Plugin) {
  if (plugin.is_builtin) return
  if (!confirm(`确定要卸载 "${plugin.name}" 吗？`)) return
  try {
    await pluginStore.uninstallPlugin(plugin.id)
    await refreshPlugins()
  } catch (e: any) { alert('卸载失败: ' + e.message) }
}
async function handleToggleEnable(plugin: Plugin, enable: boolean) {
  try { await pluginStore.togglePluginEnabled(plugin.id, enable) }
  catch (e: any) { alert('操作失败: ' + e.message) }
}
function openConfigPanel(plugin: Plugin) {
  configPlugin.value = plugin
  pluginStore.loadPluginConfig(plugin.id)
}
async function handleSaveConfig(pluginId: string, config: Record<string, any>) {
  try {
    await pluginStore.updatePluginConfig(pluginId, { config_json: config })
    configPlugin.value = null
  } catch (e: any) { alert('保存失败: ' + e.message) }
}

function triggerUpload() {
  fileInputRef.value?.click()
}

async function handleFileUpload(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  input.value = ''

  if (!file.name.endsWith('.zip')) {
    uploadStatus.value = { type: 'error', message: '仅支持 .zip 格式的插件包' }
    
    return
  }

  uploadStatus.value = { type: 'loading', message: `正在上传 ${file.name}...` }

  try {
    const result = await pluginsApi.upload(file)
    if (result.success) {
      uploadStatus.value = {
        type: 'success',
        message: `插件 "${result.name || result.plugin_id}" v${result.version || '?'} 安装成功！`,
      }
      await refreshPlugins()
    } else {
      uploadStatus.value = { type: 'error', message: result.message || '上传失败' }
    }
  } catch (e: any) {
    const detail = e.response?.data?.detail || e.message || '上传失败'
    uploadStatus.value = { type: 'error', message: detail }
  }

  setTimeout(() => { uploadStatus.value = null }, 5000)
}

// GitHub 安装相关函数 ⭐新增
function closeGithubModal() {
  showGithubInstallModal.value = false
  githubForm.repoUrl = ''
  githubForm.branch = 'main'
  githubForm.useGitClone = false
  githubInstallResult.value = null
}

async function handleGithubInstall() {
  if (!githubForm.repoUrl.trim()) {
    githubInstallResult.value = {
      success: false,
      message: '请输入 GitHub 仓库 URL',
    }
    return
  }

  // 简单的 URL 验证
  const urlPattern = /^https?:\/\/(www\.)?github\.com\/[^/]+\/[^/]+/
  if (!urlPattern.test(githubForm.repoUrl)) {
    githubInstallResult.value = {
      success: false,
      message: '无效的 GitHub URL，请使用格式：https://github.com/username/repo',
    }
    return
  }

  githubInstalling.value = true
  githubInstallResult.value = null

  try {
    const result = await pluginsApi.installFromGithub(
      githubForm.repoUrl,
      githubForm.branch || 'main',
      githubForm.useGitClone
    )

    githubInstallResult.value = result

    if (result.success) {
      // 安装成功，刷新插件列表
      await refreshPlugins()
      
      // 3秒后自动关闭弹窗
      setTimeout(() => {
        closeGithubModal()
      }, 3000)
    }
  } catch (e: any) {
    const detail = e.response?.data?.detail || e.message || '安装失败'
    githubInstallResult.value = {
      success: false,
      message: detail,
    }
  } finally {
    githubInstalling.value = false
  }
}

onMounted(async () => {
  try {
    await Promise.all([pluginStore.loadPlugins(), pluginStore.loadInstalledPlugins()])
    
  } catch (e) {
    console.error('[PluginManagerInline] Failed to init plugin manager:', e)
  }
})
</script>

<style scoped>
.pmi-wrap {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.pmi-toolbar {
  display: flex;
  gap: 8px;
  align-items: center;
}

.pmi-search-box {
  position: relative;
  flex: 1;
}

.pmi-search-input {
  width: 100%;
  height: 36px;
  border: 1px solid var(--ma-border, #E5E7EB);
  border-radius: var(--ma-radius-md, 8px);
  padding: 0 32px 0 32px;
  font-size: 13px;
  background: var(--ma-bg-subtle, #EEF0F4);
  color: var(--ma-text-primary, #111827);
  transition: all 0.15s;
}

.pmi-search-input::placeholder { color: var(--ma-text-tertiary, #6B7280); }
.pmi-search-input:focus {
  outline: none;
  border-color: var(--ma-primary, #3B6CF6);
  box-shadow: 0 0 0 2px rgba(59, 108, 246, 0.15);
}

.pmi-search-box svg:first-child {
  position: absolute;
  left: 10px;
  top: 50%;
  transform: translateY(-50%);
  color: var(--ma-text-tertiary, #6B7280);
}

.pmi-search-clear {
  position: absolute;
  right: 6px;
  top: 50%;
  transform: translateY(-50%);
  background: none;
  border: none;
  color: var(--ma-text-tertiary, #6B7280);
  cursor: pointer;
  padding: 2px;
  display: flex;
}

.pmi-icon-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border: 1px solid var(--ma-border, #E5E7EB);
  border-radius: var(--ma-radius-md, 8px);
  background: var(--ma-bg-subtle, #EEF0F4);
  color: var(--ma-text-secondary, #6B7280);
  cursor: pointer;
  transition: all 0.15s;
}

.pmi-icon-btn:hover:not(:disabled) { color: var(--ma-text-primary, #111827); background: var(--ma-accent, rgba(59, 108, 246, 0.08)); }
.pmi-icon-btn:disabled { opacity: 0.4; cursor: not-allowed; }

.pmi-upload-btn {
  color: var(--ma-primary, #3B6CF6);
  border-color: rgba(59, 108, 246, 0.3);
}

.pmi-upload-status {
  border-radius: var(--ma-radius-md, 8px);
  padding: 10px 14px;
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.pmi-upload-status.success { background: rgba(16, 185, 129, 0.08); border: 1px solid rgba(16, 185, 129, 0.2); color: #10B981; }
.pmi-upload-status.error { background: rgba(239, 68, 68, 0.08); border: 1px solid rgba(239, 68, 68, 0.2); color: var(--ma-destructive, #EF4444); }
.pmi-upload-status.loading { background: rgba(59, 108, 246, 0.08); border: 1px solid rgba(59, 108, 246, 0.2); color: var(--ma-primary, #3B6CF6); }

.pmi-error {
  background: rgba(239, 68, 68, 0.08);
  border: 1px solid rgba(239, 68, 68, 0.2);
  border-radius: var(--ma-radius-md, 8px);
  padding: 10px 14px;
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--ma-destructive, #EF4444);
  font-size: 13px;
}

.pmi-error-close {
  margin-left: auto;
  background: none;
  border: none;
  cursor: pointer;
  color: var(--ma-destructive, #EF4444);
  opacity: 0.7;
  display: flex;
}

.pmi-loading, .pmi-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
  color: var(--ma-text-tertiary, #6B7280);
  gap: 12px;
  font-size: 13px;
}

.pmi-spinner {
  width: 28px;
  height: 28px;
  border: 3px solid var(--ma-border, #E5E7EB);
  border-top-color: var(--ma-primary, #3B6CF6);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin { to { transform: rotate(360deg); } }
.spinning { animation: spin 1s linear infinite; }

/* ===== Category Groups ===== */

.pmi-categories {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.pmi-category-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}

.pmi-category-icon {
  font-size: 18px;
  line-height: 1;
}

.pmi-category-label {
  font-size: 14px;
  font-weight: 600;
  color: var(--ma-text-primary, #111827);
}

/* ===== Card Grid ===== */

.pmi-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 12px;
}

.pmi-card {
  background: var(--ma-bg-subtle, #EEF0F4);
  border: 1px solid var(--ma-border, #E5E7EB);
  border-radius: var(--ma-radius-md, 8px);
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  transition: all 0.15s;
}

.pmi-card:hover { border-color: var(--ma-border-strong, #D1D5DB); }
.pmi-card-enabled { border-color: rgba(16, 185, 129, 0.35); }
.pmi-card-expanded { border-color: rgba(59, 108, 246, 0.3); }

.pmi-card-top {
  display: flex;
  gap: 10px;
  cursor: pointer;
}

.pmi-card-icon {
  width: 36px;
  height: 36px;
  border-radius: var(--ma-radius-md, 8px);
  background: var(--ma-accent, rgba(59, 108, 246, 0.12));
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--ma-primary, #3B6CF6);
  flex-shrink: 0;
}

.pmi-card-emoji { font-size: 20px; line-height: 1; }

.pmi-card-info { flex: 1; min-width: 0; }

.pmi-card-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--ma-text-primary, #111827);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.pmi-card-desc {
  font-size: 11px;
  color: var(--ma-text-tertiary, #6B7280);
  margin-top: 2px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.pmi-card-expand-icon {
  display: flex;
  align-items: center;
  color: var(--ma-text-tertiary, #9CA3AF);
  flex-shrink: 0;
}

.pmi-card-bottom {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.pmi-card-tags {
  display: flex;
  gap: 4px;
  align-items: center;
}

.pmi-card-tag {
  font-size: 10px;
  padding: 2px 8px;
  border-radius: var(--ma-radius-full, 9999px);
  background: var(--ma-bg-subtle, #EEF0F4);
  color: var(--ma-text-secondary, #6B7280);
}

.pmi-card-tag-builtin {
  background: var(--ma-accent, rgba(59, 108, 246, 0.12));
  color: var(--ma-primary, #3B6CF6);
}

.pmi-card-tag-tp {
  background: rgba(245, 158, 11, 0.1);
  color: #F59E0B;
}

.pmi-card-actions {
  display: flex;
  gap: 6px;
  align-items: center;
}

/* ===== Enable Button (button style) ===== */

.pmi-enable-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 4px 12px;
  border: none;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
  white-space: nowrap;
}

.pmi-enable-btn-on {
  background: rgba(16, 185, 129, 0.12);
  color: #10B981;
  border: 1px solid rgba(16, 185, 129, 0.25);
}

.pmi-enable-btn-on:hover {
  background: rgba(16, 185, 129, 0.2);
}

.pmi-enable-btn-off {
  background: var(--ma-primary, #3B6CF6);
  color: #FFFFFF;
  border: 1px solid var(--ma-primary, #3B6CF6);
}

.pmi-enable-btn-off:hover {
  background: #2563EB;
}

.pmi-enable-btn-install {
  background: var(--ma-primary, #3B6CF6);
  color: #FFFFFF;
  border: 1px solid var(--ma-primary, #3B6CF6);
}

.pmi-enable-btn-install:hover {
  background: #2563EB;
}

.pmi-card-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border: none;
  border-radius: 6px;
  background: var(--ma-bg-subtle, #EEF0F4);
  color: var(--ma-text-secondary, #6B7280);
  cursor: pointer;
  transition: all 0.12s;
}

.pmi-card-btn:hover { background: var(--ma-accent, rgba(59, 108, 246, 0.08)); color: var(--ma-text-primary, #111827); }
.pmi-card-btn-danger:hover { background: rgba(239, 68, 68, 0.1); color: var(--ma-destructive, #EF4444); }

/* ===== Transitions ===== */

.slide-left-enter-active, .slide-left-leave-active { transition: transform 0.3s ease; }
.slide-left-enter-from, .slide-left-leave-to { transform: translateX(100%); }

/* ===== GitHub Install Modal ⭐新增 ===== */

.pmi-github-btn {
  background: linear-gradient(135deg, #24292e 0%, #1a1e22 100%);
  color: white !important;
  border: 1px solid rgba(255, 255, 255, 0.1);
}

.pmi-github-btn:hover {
  background: linear-gradient(135deg, #2f363d 0%, #24292e 100%);
  border-color: rgba(255, 255, 255, 0.2);
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

.pmi-modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
  animation: pmi-fadeIn 0.2s ease;
}

@keyframes pmi-fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

.pmi-modal {
  background: white;
  border-radius: 16px;
  width: 90%;
  max-width: 560px;
  max-height: 85vh;
  overflow-y: auto;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
  animation: pmi-slideUp 0.3s ease;
}

@keyframes pmi-slideUp {
  from { 
    opacity: 0;
    transform: translateY(30px) scale(0.95);
  }
  to { 
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}

.pmi-modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 24px 28px 20px;
  border-bottom: 1px solid var(--ma-border, #E5E7EB);
}

.pmi-modal-title {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--ma-text-primary, #111827);
  display: flex;
  align-items: center;
  gap: 8px;
}

.pmi-modal-close {
  padding: 6px;
  border-radius: 8px;
  border: none;
  background: transparent;
  color: var(--ma-text-tertiary, #6B7280);
  cursor: pointer;
  transition: all 0.15s;
}

.pmi-modal-close:hover {
  background: var(--ma-bg-subtle, #F3F4F6);
  color: var(--ma-text-primary, #111827);
}

.pmi-modal-body {
  padding: 24px 28px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.pmi-form-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.pmi-form-label {
  font-size: 14px;
  font-weight: 500;
  color: var(--ma-text-primary, #111827);
}

.pmi-form-input {
  height: 42px;
  border: 1.5px solid var(--ma-border, #E5E7EB);
  border-radius: 10px;
  padding: 0 14px;
  font-size: 14px;
  color: var(--ma-text-primary, #111827);
  background: white;
  transition: all 0.2s;
}

.pmi-form-input:focus {
  outline: none;
  border-color: var(--ma-primary, #3B6CF6);
  box-shadow: 0 0 0 3px rgba(59, 108, 246, 0.12);
}

.pmi-form-input::placeholder {
  color: var(--ma-text-tertiary, #9CA3AF);
}

.pmi-form-hint {
  margin: 0;
  font-size: 12px;
  color: var(--ma-text-tertiary, #6B7280);
  line-height: 1.5;
}

.pmi-checkbox-wrapper {
  display: flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;
  font-size: 14px;
  color: var(--ma-text-secondary, #374151);
}

.pmi-checkbox {
  width: 18px;
  height: 18px;
  cursor: pointer;
  accent-color: var(--ma-primary, #3B6CF6);
}

.pmi-modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding: 20px 28px 24px;
  border-top: 1px solid var(--ma-border, #E5E7EB);
  background: var(--ma-bg-subtle, #F9FAFB);
  border-radius: 0 0 16px 16px;
}

.pmi-btn {
  height: 40px;
  padding: 0 20px;
  border-radius: 10px;
  border: none;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 8px;
  transition: all 0.2s;
}

.pmi-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.pmi-btn-secondary {
  background: white;
  color: var(--ma-text-secondary, #374151);
  border: 1.5px solid var(--ma-border, #E5E7EB);
}

.pmi-btn-secondary:hover:not(:disabled) {
  background: var(--ma-bg-subtle, #F9FAFB);
  border-color: var(--ma-text-tertiary, #9CA3AF);
}

.pmi-btn-primary {
  background: linear-gradient(135deg, #3B6CF6 0%, #2563EB 100%);
  color: white;
  box-shadow: 0 4px 12px rgba(59, 108, 246, 0.25);
}

.pmi-btn-primary:hover:not(:disabled) {
  background: linear-gradient(135deg, #2563EB 0%, #1D4ED8 100%);
  box-shadow: 0 6px 16px rgba(59, 108, 246, 0.35);
  transform: translateY(-1px);
}

.pmi-install-result {
  margin: 0 28px 24px;
  padding: 16px 20px;
  border-radius: 12px;
  display: flex;
  align-items: flex-start;
  gap: 12px;
  animation: pmi-fadeIn 0.3s ease;
}

.pmi-install-result.success {
  background: linear-gradient(135deg, #ECFDF5 0%, #D1FAE5 100%);
  border: 1px solid #10B981;
  color: #065F46;
}

.pmi-install-result.error {
  background: linear-gradient(135deg, #FEF2F2 0%, #FEE2E2 100%);
  border: 1px solid #EF4444;
  color: #991B1B;
}

.pmi-result-message {
  margin: 0 0 4px 0;
  font-weight: 600;
  font-size: 14px;
}

.pmi-result-details {
  margin: 0;
  font-size: 13px;
  opacity: 0.9;
}
</style>