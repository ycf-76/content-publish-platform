<script setup lang="ts">
import { onMounted, onBeforeUnmount } from 'vue'
import CardRenderer from '@/components/CardRenderer.vue'
import EstherCardRenderer from '@/components/EstherCardRenderer.vue'
import { type CardPage, type DecorationConfig } from '@/card-editor/templates'
import { isEstherTemplate, type EstherCardPage } from '@/card-editor/esther-templates'
import PageList from '@/components/card-editor/PageList.vue'
import CanvasPreview from '@/components/card-editor/CanvasPreview.vue'
import PropertyPanel from '@/components/card-editor/PropertyPanel.vue'
import { useCardEditor, type CardDraft } from '@/composables/useCardEditor'

const props = defineProps<{
  cardDraft?: CardDraft
  injecting?: boolean
}>()

const emit = defineEmits<{
  generate: [images: string[], planContext: {
    template: string
    accent: string
    page_count: number
    page_types: string[]
    decoration: DecorationConfig
  }]
}>()

const editor = useCardEditor(() => props.cardDraft)

function setExportContainer(el: any) {
  editor.exportContainer.value = el
}

function setPreviewGrid(el: any) {
  editor.previewGrid.value = el
}

onMounted(() => editor.initPreviewResize())
onBeforeUnmount(() => editor.destroyPreviewResize())

async function handleGenerate() {
  const result = await editor.generateImages()
  if (result) {
    emit('generate', result.images, result.planContext)
  }
}

defineExpose({
  generateImages: handleGenerate,
  currentTemplateId: editor.currentTemplateId,
  customAccent: editor.customAccent,
  pages: editor.pages,
  currentDecoration: editor.currentDecoration,
})
</script>

<template>
  <div class="cep">
    <div class="cep-body">
      <aside class="cep-left">
        <PageList
          :pages="editor.pages.value"
          :selected-page-id="editor.selectedPageId.value"
          @select="editor.selectPage"
          @move="editor.movePage"
          @delete="editor.deletePage"
          @duplicate="editor.duplicatePage"
          @add="editor.addPage"
        />
      </aside>

      <main class="cep-center">
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
      </main>

      <aside class="cep-right">
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
        />
      </aside>
    </div>

    <div class="cep-footer">
      <button class="cep-gen-btn" :disabled="editor.exporting.value || props.injecting" @click="handleGenerate">
        {{ props.injecting ? '注入中...' : editor.exporting.value ? (editor.exportProgress.value || '生成中...') : '生成图片并注入工作流' }}
      </button>
    </div>

    <div :ref="setExportContainer" class="cep-export-container" aria-hidden="true">
      <template v-for="page in editor.pages.value" :key="page.id">
        <EstherCardRenderer v-if="isEstherTemplate(editor.currentTemplateId.value)" :page="page" :theme="editor.effectiveTheme.value" :decoration="editor.currentDecoration.value" />
        <CardRenderer v-else :page="page as CardPage" :theme="editor.effectiveTheme.value" :decoration="editor.currentDecoration.value" />
      </template>
    </div>
  </div>
</template>

<style scoped>
.cep {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #1e293b;
  overflow: hidden;
}

.cep-body {
  flex: 1;
  display: grid;
  grid-template-columns: 200px minmax(0, 1fr) 220px;
  overflow: hidden;
  min-height: 0;
}

.cep-left, .cep-right {
  background: #1e293b;
  overflow-x: hidden;
  overflow-y: auto;
  padding: 10px;
}

.cep-left { border-right: 1px solid rgba(255,255,255,0.06); }
.cep-right { border-left: 1px solid rgba(255,255,255,0.06); }

.cep-center {
  overflow-y: auto;
  padding: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  min-width: 0;
  background: #0f172a;
}

.cep-footer {
  display: flex;
  justify-content: center;
  align-items: center;
  padding: 12px 16px;
  background: #1e293b;
  border-top: 1px solid rgba(255,255,255,0.06);
  flex-shrink: 0;
}

.cep-gen-btn {
  padding: 8px 24px;
  background: #2563eb;
  color: #FFFFFF;
  border: none;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
  transition: all 0.15s;
}
.cep-gen-btn:hover:not(:disabled) { background: #1d4ed8; }
.cep-gen-btn:disabled { opacity: 0.5; cursor: not-allowed; }

.cep-export-container { position: absolute; clip: rect(0, 0, 0, 0); width: 1080px; pointer-events: none; }
</style>