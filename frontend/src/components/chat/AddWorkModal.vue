<template>
  <Teleport to="body">
    <div class="awm-overlay" v-if="visible" @click.self="$emit('close')">
      <div class="awm">
        <div class="awm-header">
          <span class="awm-title">添加作品</span>
          <button class="awm-close" @click="$emit('close')">
            <X :size="16" :stroke-width="1.8" />
          </button>
        </div>

        <div class="awm-body">
          <div class="awm-label">粘贴作品链接（支持批量，每行一个）</div>
          <div class="awm-platforms">
            <span>支持：小红书 · 抖音 · 快手 · B站 · 视频号</span>
          </div>
          <textarea
            class="awm-input"
            v-model="links"
            placeholder="https://www.xiaohongshu.com/explore/xxx&#10;https://www.douyin.com/video/yyy&#10;https://www.bilibili.com/video/BVzzz"
            rows="5"
            ref="inputRef"
          ></textarea>

          <div class="awm-divider">或</div>

          <div class="awm-label">导入 CSV 文件</div>
          <div class="awm-csv-area" @click="triggerFileInput" @dragover.prevent @drop.prevent="onDrop">
            <Upload :size="20" :stroke-width="1.5" />
            <span>点击选择文件 或 拖拽到此处</span>
          </div>
          <input type="file" ref="fileInputRef" accept=".csv,.xlsx" style="display:none" @change="onFileSelect" />
        </div>

        <div class="awm-footer">
          <button class="awm-btn awm-btn-cancel" @click="$emit('close')">取消</button>
          <button class="awm-btn awm-btn-primary" :disabled="!links.trim() || isCollecting" @click="startCollect">
            {{ isCollecting ? '采集中...' : '开始采集' }}
          </button>
        </div>

        <div class="awm-results" v-if="results.length > 0">
          <div class="awm-result" v-for="r in results" :key="r.url" :class="{ 'awm-result-ok': r.ok, 'awm-result-err': !r.ok }">
            <CheckCircle2 v-if="r.ok" :size="14" />
            <AlertCircle v-else :size="14" />
            <span class="awm-result-title">{{ r.title || r.url }}</span>
            <span class="awm-result-status">{{ r.ok ? '成功' : r.error }}</span>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, nextTick, watch } from 'vue'
import { X, Upload, CheckCircle2, AlertCircle } from 'lucide-vue-next'
import { useWorkStore } from '@/stores/work'

const props = defineProps<{
  visible: boolean
}>()

const emit = defineEmits<{
  close: []
}>()

const workStore = useWorkStore()
const links = ref('')
const isCollecting = ref(false)
const results = ref<Array<{ url: string; title: string; ok: boolean; error?: string }>>([])
const inputRef = ref<HTMLTextAreaElement | null>(null)
const fileInputRef = ref<HTMLInputElement | null>(null)

watch(() => props.visible, (v) => {
  if (v) {
    links.value = ''
    results.value = []
    isCollecting.value = false
    nextTick(() => inputRef.value?.focus())
  }
})

function triggerFileInput() {
  fileInputRef.value?.click()
}

function onFileSelect(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (file) {
    links.value = `[CSV: ${file.name}]`
  }
}

function onDrop(e: DragEvent) {
  const file = e.dataTransfer?.files[0]
  if (file) {
    links.value = `[CSV: ${file.name}]`
  }
}

async function startCollect() {
  const urls = links.value.split('\n').map(l => l.trim()).filter(Boolean)
  if (urls.length === 0) return

  isCollecting.value = true
  results.value = []

  for (const url of urls) {
    try {
      const work = await workStore.addWorkByLink(url)
      results.value.push({ url, title: work.title, ok: true })
    } catch (err: any) {
      results.value.push({ url, title: '', ok: false, error: err.message || '采集失败' })
    }
  }

  isCollecting.value = false
}
</script>

<style scoped>
.awm-overlay {
  position: fixed;
  top: 0;
  left: 0;
  width: 100vw;
  height: 100vh;
  background: rgba(0,0,0,0.3);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
}
.awm {
  width: 480px;
  max-height: 80vh;
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 8px 32px rgba(0,0,0,0.15);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.awm-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid rgba(0,0,0,0.06);
}
.awm-title {
  font-size: 15px;
  font-weight: 600;
  color: #1a1a1a;
}
.awm-close {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border: none;
  background: none;
  border-radius: 6px;
  color: #888;
  cursor: pointer;
}
.awm-close:hover {
  background: rgba(0,0,0,0.05);
}
.awm-body {
  padding: 20px;
  overflow-y: auto;
}
.awm-label {
  font-size: 13px;
  font-weight: 500;
  color: #333;
  margin-bottom: 6px;
}
.awm-platforms {
  font-size: 11px;
  color: #888;
  margin-bottom: 10px;
}
.awm-input {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid rgba(0,0,0,0.12);
  border-radius: 8px;
  font-size: 13px;
  font-family: 'SF Mono', 'JetBrains Mono', Consolas, monospace;
  resize: vertical;
  min-height: 80px;
  box-sizing: border-box;
  outline: none;
  background: #fff;
  transition: border-color 0.15s;
}
.awm-input:focus {
  border-color: #4a90d9;
}
.awm-divider {
  text-align: center;
  color: #aaa;
  font-size: 12px;
  margin: 16px 0;
  position: relative;
}
.awm-csv-area {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 20px;
  border: 2px dashed rgba(0,0,0,0.1);
  border-radius: 8px;
  color: #888;
  font-size: 13px;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
}
.awm-csv-area:hover {
  border-color: #4a90d9;
  background: rgba(74,144,217,0.04);
}
.awm-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 12px 20px;
  border-top: 1px solid rgba(0,0,0,0.06);
}
.awm-btn {
  padding: 8px 16px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  border: none;
  transition: all 0.15s;
}
.awm-btn-cancel {
  background: #f3f4f6;
  color: #555;
}
.awm-btn-cancel:hover {
  background: #e5e7eb;
}
.awm-btn-primary {
  background: #4a90d9;
  color: #fff;
}
.awm-btn-primary:hover:not(:disabled) {
  background: #3a7bc8;
}
.awm-btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.awm-results {
  padding: 0 20px 16px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.awm-result {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  border-radius: 6px;
  font-size: 12px;
}
.awm-result-ok {
  background: #f0fdf4;
  color: #2da44e;
}
.awm-result-err {
  background: #fef2f2;
  color: #cf222e;
}
.awm-result-title {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.awm-result-status {
  flex: none;
  font-size: 11px;
}
</style>