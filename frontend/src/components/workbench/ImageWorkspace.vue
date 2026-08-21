<template>
  <div class="ws-overlay">
    <div class="ws-panel">
      <!-- 顶部工具栏 -->
      <header class="ws-header">
        <div class="ws-header-left">
          <h3 class="ws-title">图片工作区</h3>
          <div class="ws-header-controls">
            <div class="ws-control">
              <label>平台</label>
              <select v-model="selectedPlatform">
                <option v-for="profile in platformProfiles" :key="profile.platform" :value="profile.platform">
                  {{ profile.display_name }}
                </option>
              </select>
            </div>
            <div class="ws-control">
              <label>尺寸</label>
              <select v-model="selectedFormat">
                <option v-for="(_, format) in currentFormats" :key="format" :value="format">
                  {{ format }}
                </option>
              </select>
            </div>
          </div>
        </div>
        <div class="ws-header-right">
          <div v-if="brandConfig" class="ws-brand">
            <span class="ws-brand-name">{{ brandConfig.brand_name || '品牌 Kit' }}</span>
            <span class="ws-brand-dot" :style="{ background: brandConfig.primary }"></span>
            <span class="ws-brand-dot" :style="{ background: brandConfig.accent }"></span>
            <span class="ws-brand-dot" :style="{ background: brandConfig.spot }"></span>
          </div>
          <button type="button" class="ws-close" @click="$emit('close')" title="关闭">✕</button>
        </div>
      </header>

      <!-- 主体三栏 -->
      <div class="ws-body">
        <!-- 左侧资源栏 -->
        <aside class="ws-left" :class="{ collapsed: leftCollapsed }">
          <button class="ws-left-toggle" @click="leftCollapsed = !leftCollapsed" :title="leftCollapsed ? '展开' : '收起'">
            {{ leftCollapsed ? '▸' : '◂' }}
          </button>
          <div v-if="!leftCollapsed" class="ws-left-content">
            <div class="ws-tabs">
              <button
                v-for="tab in leftTabs"
                :key="tab.key"
                class="ws-tab"
                :class="{ active: leftTab === tab.key }"
                @click="leftTab = tab.key"
              >{{ tab.label }}</button>
            </div>
            <div class="ws-tab-content">
              <PageList
                v-if="leftTab === 'pages'"
                :pages="editor.pages.value"
                :selected-page-id="editor.selectedPageId.value"
                @select="editor.selectPage"
                @move="editor.movePage"
                @delete="editor.deletePage"
                @duplicate="editor.duplicatePage"
                @add="editor.addPage"
                @reorder="editor.movePageByIndex"
              />
              <TemplateGallery
                v-else-if="leftTab === 'templates'"
                :current-template-id="editor.currentTemplateId.value"
                :selected-platform="selectedPlatform"
                @select="editor.selectTemplate"
              />
              <AssetGallery
                v-else-if="leftTab === 'assets'"
                @set-as-page="handleSetAssetAsPage"
                @set-as-background="handleSetAssetAsBackground"
              />
            </div>
          </div>
        </aside>

        <!-- 中间画布 -->
        <main class="ws-center">
          <div class="ws-mode-switch">
            <button :class="{ active: workspaceMode === 'template' }" @click="workspaceMode = 'template'">模板卡片</button>
            <button :class="{ active: workspaceMode === 'asset' }" @click="workspaceMode = 'asset'">本地图片</button>
          </div>

          <div class="ws-canvas-area">
            <template v-if="workspaceMode === 'template'">
              <CanvasPreview
                :pages="editor.pages.value"
                :selected-page-id="editor.selectedPageId.value"
                :current-template-id="editor.currentTemplateId.value"
                :effective-theme="editor.effectiveTheme.value"
                :current-decoration="editor.currentDecoration.value"
                :preview-scale="editor.previewScale.value"
                :box-width="editor.boxWidth.value"
                :box-height="editor.boxHeight.value"
                :set-grid-ref="setPreviewGrid"
                @select="editor.selectPage"
              />
            </template>

            <template v-else>
              <div class="ws-asset-mode">
                <div class="ws-asset-upload-area">
                  <input id="ws-asset-input" type="file" accept="image/*" multiple @change="handleAssetFiles" />
                  <label for="ws-asset-input">
                    {{ uploadingAssets ? '上传中...' : '点击上传本地图片' }}
                  </label>
                </div>
                <div v-if="assetImages.length > 0" class="ws-asset-grid">
                  <div v-for="(asset, i) in assetImages" :key="asset.asset_id" class="ws-asset-card">
                    <img :src="asset.thumbnail_url" :alt="asset.filename" />
                    <span class="ws-asset-idx">{{ i + 1 }}</span>
                  </div>
                </div>
              </div>
            </template>
          </div>
        </main>

        <!-- 右侧属性栏 -->
        <aside class="ws-right" :class="{ collapsed: rightCollapsed }">
          <button class="ws-right-toggle" @click="rightCollapsed = !rightCollapsed" :title="rightCollapsed ? '展开' : '收起'">
            {{ rightCollapsed ? '◂' : '▸' }}
          </button>
          <div v-if="!rightCollapsed" class="ws-right-content">
            <PropertyPanel
              :selected-page="editor.selectedPage.value"
              :current-template-id="editor.currentTemplateId.value"
              :current-template="editor.currentTemplate.value"
              :effective-theme="editor.effectiveTheme.value"
              :current-decoration="editor.currentDecoration.value"
              :custom-font-size="editor.customFontSize.value"
              :custom-bg="editor.customBg.value"
              :custom-accent="editor.customAccent.value"
              :filtered-deco-presets="editor.filteredDecoPresets.value"
              :card-draft="cardDraft"
              @change-page-type="editor.changePageType"
              @update:custom-font-size="editor.customFontSize.value = $event"
              @update:custom-bg="editor.customBg.value = $event"
              @update:custom-accent="editor.customAccent.value = $event"
              @update:decoration-type="editor.currentDecoration.value.type = $event; if ($event === 'none') editor.setDecorationNone()"
              @select-decoration="editor.selectDecoration"
              @decoration-none="editor.setDecorationNone"
              @reset-style="editor.resetCustomStyle"
              @redistribute="editor.redistributeContent"
              @add-list-item="editor.addListItem"
              @delete-list-item="editor.deleteListItem"
              @fill-copywrite="editor.fillPageFromCopywrite"
            />
          </div>
        </aside>
      </div>

      <!-- 底部操作条 -->
      <footer class="ws-footer">
        <button class="ws-footer-btn ws-footer-btn-secondary" @click="editor.undo()" :disabled="!editor.canUndo.value">
          撤销
        </button>
        <button class="ws-footer-btn ws-footer-btn-secondary" @click="editor.redo()" :disabled="!editor.canRedo.value">
          重做
        </button>
        <span class="ws-footer-sep"></span>
        <button class="ws-footer-btn ws-footer-btn-secondary" @click="handleRegenerate" :disabled="injecting">
          重新生成
        </button>
        <button class="ws-footer-btn ws-footer-btn-secondary" @click="handleSaveDraft" :disabled="injecting || savingDraft">
          {{ savingDraft ? '保存中...' : '保存草稿' }}
        </button>
        <button class="ws-footer-btn ws-footer-btn-primary" @click="handleGenerateAndInject" :disabled="injecting || editor.exporting.value">
          {{ injecting ? '注入中...' : editor.exporting.value ? (editor.exportProgress.value || '生成中...') : '生成并注入工作流' }}
        </button>
      </footer>

      <!-- 隐藏的导出容器 -->
      <div :ref="setExportContainer" class="ws-export-container" aria-hidden="true">
        <template v-for="page in editor.pages.value" :key="page.id">
          <EstherCardRenderer v-if="isEstherTemplate(editor.currentTemplateId.value)" :page="page" :theme="editor.effectiveTheme.value" :decoration="editor.currentDecoration.value" />
          <CardRenderer v-else :page="page as CardPage" :theme="editor.effectiveTheme.value" :decoration="editor.currentDecoration.value" />
        </template>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, nextTick, watch } from 'vue'
import CardRenderer from '@/components/CardRenderer.vue'
import EstherCardRenderer from '@/components/EstherCardRenderer.vue'
import { type CardPage, type DecorationConfig } from '@/card-editor/templates'
import { isEstherTemplate } from '@/card-editor/esther-templates'
import PageList from '@/components/card-editor/PageList.vue'
import CanvasPreview from '@/components/card-editor/CanvasPreview.vue'
import PropertyPanel from '@/components/card-editor/PropertyPanel.vue'
import TemplateGallery from '@/components/card-editor/TemplateGallery.vue'
import AssetGallery from '@/components/card-editor/AssetGallery.vue'
import { useCardEditor, type CardDraft } from '@/composables/useCardEditor'
import { workflowApi } from '@/api/workflow'
import { useWorkflowStore } from '@/stores/workflow'
import { listPlatformProfiles, type PlatformProfile } from '@/api/templates'
import { estherFactoryApi, type BrandConfig } from '@/api/esther_factory'
import { uploadAssets, type ImageAsset } from '@/api/assets'

const props = defineProps<{
  cardDraft: CardDraft
  workflowId: string
}>()

const emit = defineEmits<{
  close: []
}>()

const editor = useCardEditor(() => props.cardDraft)
const workflowStore = useWorkflowStore()

function setExportContainer(el: any) {
  editor.exportContainer.value = el
}

function setPreviewGrid(el: any) {
  editor.previewGrid.value = el
}

const injecting = ref(false)
const workspaceMode = ref<'template' | 'asset'>('template')
const uploadingAssets = ref(false)
const assetImages = ref<ImageAsset[]>([])
const platformProfiles = ref<PlatformProfile[]>([])
const selectedPlatform = ref('xiaohongshu')
const selectedFormat = ref('3:4')
const brandConfig = ref<BrandConfig | null>(null)
const leftCollapsed = ref(false)
const rightCollapsed = ref(false)
const leftTab = ref<'pages' | 'templates' | 'assets'>('pages')

const leftTabs = [
  { key: 'pages' as const, label: '页面' },
  { key: 'templates' as const, label: '模板' },
  { key: 'assets' as const, label: '素材' },
]

const currentProfile = computed(() => {
  return platformProfiles.value.find((profile) => profile.platform === selectedPlatform.value)
})

const currentFormats = computed(() => currentProfile.value?.formats || {})

onMounted(async () => {
  try {
    platformProfiles.value = await listPlatformProfiles()
    const first = platformProfiles.value[0]
    if (first) {
      selectedPlatform.value = first.platform
      selectedFormat.value = Object.keys(first.formats)[0] || '3:4'
    }
    brandConfig.value = await estherFactoryApi.getBrandConfig()
  } catch (e) {
    console.error('[ImageWorkspace] failed to load workspace config:', e)
  }
  editor.initPreviewResize()
  window.addEventListener('keydown', handleKeyboard)
})

onBeforeUnmount(() => {
  editor.destroyPreviewResize()
  window.removeEventListener('keydown', handleKeyboard)
})

function handleKeyboard(e: KeyboardEvent) {
  if ((e.ctrlKey || e.metaKey) && e.key === 'z' && !e.shiftKey) {
    e.preventDefault()
    editor.undo()
  }
  if ((e.ctrlKey || e.metaKey) && (e.key === 'y' || (e.key === 'z' && e.shiftKey))) {
    e.preventDefault()
    editor.redo()
  }
}

watch(() => selectedPlatform.value, () => {
  const profile = currentProfile.value
  selectedFormat.value = profile ? Object.keys(profile.formats)[0] || '3:4' : '3:4'
})

function handleSetAssetAsPage(asset: ImageAsset) {
  const imageUrl = asset.original_url || asset.thumbnail_url
  if (!imageUrl) return
  editor.addImagePage(imageUrl)
}

function handleSetAssetAsBackground(asset: ImageAsset) {
  const imageUrl = asset.original_url || asset.thumbnail_url
  if (!imageUrl) return
  const pageId = editor.selectedPageId.value
  editor.setPageBackground(pageId, imageUrl)
}

async function handleAssetFiles(event: Event) {
  const input = event.target as HTMLInputElement
  const files = Array.from(input.files || [])
  if (!files.length) return

  uploadingAssets.value = true
  try {
    const uploaded = await uploadAssets(files)
    assetImages.value = [...assetImages.value, ...uploaded]
  } catch (e) {
    console.error('[ImageWorkspace] asset upload failed:', e)
    alert('图片上传失败')
  } finally {
    uploadingAssets.value = false
    input.value = ''
  }
}

async function urlToBase64(url: string): Promise<string> {
  const response = await fetch(url)
  const blob = await response.blob()
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result).split(',')[1] || '')
    reader.onerror = reject
    reader.readAsDataURL(blob)
  })
}

function extractAxiosError(e: any): string {
  const data = e?.response?.data
  if (data) {
    return data.detail || data.message || JSON.stringify(data)
  }
  if (e?.code === 'ECONNABORTED' || e?.message?.includes('timeout')) {
    return '请求超时（图片数据可能过大，请减少卡片页数后重试）'
  }
  return e?.message || String(e)
}

async function injectToWorkflow(images: string[], planContext: Record<string, any>) {
  if (!props.workflowId) return

  injecting.value = true
  try {
    const resp: any = await workflowApi.injectCardImages(
      props.workflowId,
      images,
      [],
      '图片工作区',
      {
        ...planContext,
        platform: selectedPlatform.value,
        format: selectedFormat.value,
        brand: brandConfig.value || undefined,
      },
    )
    const ok = resp?.success || resp?.data?.success
    if (ok) {
      emit('close')
    } else {
      const msg = resp?.data?.message || resp?.message || '注入失败（未知原因）'
      alert('图片注入失败：' + msg)
    }
  } catch (e: any) {
    const errMsg = extractAxiosError(e)
    console.error('[ImageWorkspace] injectCardImages error:', e)
    alert('图片注入失败：' + errMsg)
  } finally {
    injecting.value = false
  }
}

async function handleGenerateAndInject() {
  const result = await editor.generateImages()
  if (result) {
    await injectToWorkflow(result.images, result.planContext)
  }
}

const savingDraft = ref(false)

function handleRegenerate() {
  // TODO: trigger LLM re-planning via workflow API
  alert('重新生成功能将在后续版本中实现')
}

async function handleSaveDraft() {
  if (!props.workflowId || savingDraft.value) return
  savingDraft.value = true
  try {
    const draft = {
      template: editor.currentTemplateId.value,
      accent: editor.customAccent.value,
      customFontSize: editor.customFontSize.value,
      customBg: editor.customBg.value,
      pages: editor.pages.value,
      decoration: editor.currentDecoration.value,
    }
    await workflowApi.saveDraft(props.workflowId, draft)
    workflowStore.pushNotification?.({
      type: 'workflow_info',
      message: '草稿已保存',
    })
  } catch (e: any) {
    console.error('[ImageWorkspace] saveDraft failed:', e)
    alert('保存草稿失败：' + (e?.response?.data?.detail || e?.message || '未知错误'))
  } finally {
    savingDraft.value = false
  }
}
</script>

<style scoped>
.ws-overlay {
  position: fixed;
  inset: 0;
  z-index: 9000;
  background: #0f172a;
}

.ws-panel {
  width: 100%;
  height: 100%;
  display: grid;
  grid-template-rows: 48px 1fr 52px;
  overflow: hidden;
}

/* ===== 顶部工具栏 ===== */
.ws-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 16px;
  background: #1e293b;
  border-bottom: 1px solid rgba(255,255,255,0.06);
}
.ws-header-left {
  display: flex;
  align-items: center;
  gap: 20px;
}
.ws-title {
  margin: 0;
  font-size: 15px;
  font-weight: 700;
  color: #e2e8f0;
  white-space: nowrap;
}
.ws-header-controls {
  display: flex;
  align-items: center;
  gap: 12px;
}
.ws-control {
  display: flex;
  align-items: center;
  gap: 6px;
}
.ws-control label {
  font-size: 11px;
  color: #64748b;
  font-weight: 500;
}
.ws-control select {
  padding: 4px 8px;
  border: 1px solid rgba(255,255,255,0.1);
  border-radius: 6px;
  background: #0f172a;
  color: #e2e8f0;
  font-size: 12px;
}
.ws-header-right {
  display: flex;
  align-items: center;
  gap: 14px;
}
.ws-brand {
  display: flex;
  align-items: center;
  gap: 6px;
}
.ws-brand-name {
  font-size: 11px;
  color: #94a3b8;
}
.ws-brand-dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  box-shadow: inset 0 0 0 1px rgba(255,255,255,0.1);
}
.ws-close {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border: 0;
  border-radius: 6px;
  background: rgba(255,255,255,0.06);
  color: #94a3b8;
  cursor: pointer;
  font-size: 13px;
  transition: all 0.12s;
}
.ws-close:hover { background: rgba(239,68,68,0.15); color: #f87171; }

/* ===== 主体三栏 ===== */
.ws-body {
  display: grid;
  grid-template-columns: auto 1fr auto;
  overflow: hidden;
  min-height: 0;
}

/* 左栏 */
.ws-left {
  display: flex;
  background: #1e293b;
  border-right: 1px solid rgba(255,255,255,0.06);
  transition: width 0.2s;
  width: 240px;
  position: relative;
}
.ws-left.collapsed { width: 24px; }
.ws-left-toggle {
  position: absolute;
  top: 50%;
  right: -1px;
  transform: translateY(-50%);
  z-index: 2;
  width: 20px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #1e293b;
  border: 1px solid rgba(255,255,255,0.06);
  border-left: none;
  border-radius: 0 6px 6px 0;
  color: #64748b;
  cursor: pointer;
  font-size: 10px;
}
.ws-left-toggle:hover { color: #93c5fd; }
.ws-left-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  overflow: hidden;
}
.ws-tabs {
  display: flex;
  border-bottom: 1px solid rgba(255,255,255,0.06);
  flex-shrink: 0;
}
.ws-tab {
  flex: 1;
  padding: 8px 4px;
  border: none;
  background: transparent;
  color: #64748b;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  border-bottom: 2px solid transparent;
  transition: all 0.12s;
}
.ws-tab:hover { color: #94a3b8; }
.ws-tab.active { color: #93c5fd; border-bottom-color: #2563eb; }
.ws-tab-content {
  flex: 1;
  overflow-y: auto;
  padding: 10px;
  min-height: 0;
}

/* 中间画布 */
.ws-center {
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: #0f172a;
}
.ws-mode-switch {
  display: flex;
  gap: 4px;
  padding: 8px 12px;
  border-bottom: 1px solid rgba(255,255,255,0.04);
  flex-shrink: 0;
}
.ws-mode-switch button {
  padding: 5px 12px;
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 6px;
  background: transparent;
  color: #64748b;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.12s;
}
.ws-mode-switch button.active {
  border-color: #2563eb;
  background: rgba(37,99,235,0.12);
  color: #93c5fd;
}
.ws-canvas-area {
  flex: 1;
  overflow: auto;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
}

/* 右栏 */
.ws-right {
  display: flex;
  background: #1e293b;
  border-left: 1px solid rgba(255,255,255,0.06);
  transition: width 0.2s;
  width: 280px;
  position: relative;
  height: 100%;
  min-height: 0;
  overflow: hidden;
}
.ws-right.collapsed { width: 24px; }
.ws-right-toggle {
  position: absolute;
  top: 50%;
  left: -1px;
  transform: translateY(-50%);
  z-index: 2;
  width: 20px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #1e293b;
  border: 1px solid rgba(255,255,255,0.06);
  border-right: none;
  border-radius: 6px 0 0 6px;
  color: #64748b;
  cursor: pointer;
  font-size: 10px;
}
.ws-right-toggle:hover { color: #93c5fd; }
.ws-right-content {
  flex: 1;
  height: 100%;
  min-height: 0;
  overflow: hidden;
  padding: 10px;
}

/* ===== 底部操作条 ===== */
.ws-footer {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 0 16px;
  background: #1e293b;
  border-top: 1px solid rgba(255,255,255,0.06);
}
.ws-footer-btn {
  padding: 7px 18px;
  border: none;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.12s;
  white-space: nowrap;
}
.ws-footer-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.ws-footer-btn-secondary {
  background: rgba(255,255,255,0.06);
  color: #94a3b8;
}
.ws-footer-btn-secondary:hover:not(:disabled) { background: rgba(255,255,255,0.1); color: #e2e8f0; }
.ws-footer-btn-primary {
  background: #2563eb;
  color: #fff;
}
.ws-footer-btn-primary:hover:not(:disabled) { background: #1d4ed8; }

.ws-footer-sep {
  width: 1px;
  height: 24px;
  background: rgba(255,255,255,0.15);
  margin: 0 4px;
}

/* ===== 资产模式 ===== */
.ws-asset-mode {
  display: flex;
  flex-direction: column;
  gap: 16px;
  width: 100%;
}
.ws-asset-upload-area {
  text-align: center;
}
.ws-asset-upload-area input { display: none; }
.ws-asset-upload-area label {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 12px 20px;
  border-radius: 8px;
  background: rgba(37,99,235,0.15);
  color: #93c5fd;
  font-size: 14px;
  cursor: pointer;
  border: 1px dashed rgba(37,99,235,0.3);
  transition: all 0.15s;
}
.ws-asset-upload-area label:hover { background: rgba(37,99,235,0.25); }
.ws-asset-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: 10px;
}
.ws-asset-card {
  position: relative;
  border-radius: 8px;
  overflow: hidden;
  background: rgba(255,255,255,0.04);
}
.ws-asset-card img {
  width: 100%;
  aspect-ratio: 3 / 4;
  object-fit: cover;
}
.ws-asset-idx {
  position: absolute;
  top: 4px;
  left: 4px;
  background: rgba(0,0,0,0.6);
  color: #fff;
  font-size: 10px;
  font-weight: 700;
  padding: 2px 6px;
  border-radius: 4px;
}

/* ===== 导出容器 ===== */
.ws-export-container { position: absolute; clip: rect(0, 0, 0, 0); width: 1080px; pointer-events: none; }

/* ===== 小屏适配 ===== */
@media (max-width: 1024px) {
  .ws-left { width: 200px; }
  .ws-right { width: 240px; }
}
@media (max-width: 768px) {
  .ws-left, .ws-right { width: 24px; }
  .ws-left .ws-left-content, .ws-right .ws-right-content { display: none; }
  .ws-header-controls { display: none; }
}
</style>