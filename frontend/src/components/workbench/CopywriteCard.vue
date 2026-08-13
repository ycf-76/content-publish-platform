<template>
  <div class="mint-wf-card wf-node-card wf-node-copywrite" id="card-copywrite" :class="`wf-state-${nodeStatus}`">
    <div class="mint-wf-header">
      <div class="mint-wf-title-row">
        <div class="mint-wf-step">03</div>
        <div class="wf-node-title-block">
          <div class="mint-wf-title">
            <i data-lucide="pen-tool" class="wf-node-icon"></i>
            文案撰写
            <code class="wf-node-key">copywrite</code>
          </div>

        </div>
      </div>
      <span class="mint-badge wf-status-badge" :style="statusBadgeStyle">
        <span class="mint-status-dot" :style="{ background: statusColor }"></span>
        {{ statusLabel }}
      </span>
    </div>

    <div class="wf-node-body">
      <div v-if="nodeStatus === 'idle'" class="wf-empty-hint">
        <i data-lucide="info" style="width:14px; height:14px;"></i>
        等待分析节点完成后自动进入文案撰写
      </div>

      <div v-else-if="nodeStatus === 'running'" class="wf-copywrite-loading">
        <div class="mint-loader">
          <div class="mint-loader-ball"></div>
        </div>
        <div class="wf-copywrite-loading-text">正在生成文案...</div>
      </div>

      <div v-else-if="nodeStatus === 'error'" class="mint-search-error">
        <i data-lucide="alert-circle" style="width:20px; height:20px;"></i>
        <span>{{ errorMessage || '文案生成失败' }}</span>
      </div>

      <!-- completed: 左右分栏布局（文案+组件） -->
      <div v-else-if="nodeStatus === 'completed' && result" class="wf-copywrite-layout">
        <!-- ===== 左侧：主工作区（始终可编辑） ===== -->
        <div class="wf-copywrite-main">
          <div class="xhs-editor-edit">
            <input
              v-model="editTitle"
              class="xhs-title-input"
              placeholder="填写标题会有更多赞哦～"
              :maxlength="20"
            />
            <div class="xhs-title-counter">{{ editTitle.length }}/20</div>
            <div class="xhs-divider"></div>
            <textarea
              ref="contentTextareaRef"
              v-model="editContent"
              class="xhs-content-input"
              placeholder="添加正文"
              @input="autoResizeTextarea"
            ></textarea>
            <div class="xhs-content-counter">{{ editContent.length }} 字</div>
            <!-- 推荐话题：点击直接插入光标位置 -->
            <div v-if="suggestedTopics.length" class="xhs-topic-suggest">
              <span class="xhs-topic-suggest-label"># 话题</span>
              <button
                v-for="(t, i) in suggestedTopics"
                :key="i"
                class="xhs-topic-chip"
                :class="{ 'xhs-topic-chip-used': isTopicUsed(t) }"
                @click="insertTopicToCursor(t)"
              >#{{ t }}</button>
            </div>
          </div>

          <div v-if="displayData.review_feedback" class="wf-copywrite-feedback">
            <i data-lucide="message-square-warning" style="width:12px;height:12px;"></i>
            <span>上游反馈：{{ result.review_feedback }}</span>
          </div>

          <div v-if="saveError" class="wf-copywrite-feedback" style="background:#FEF2F2;border-color:#FCA5A5;color:#DC2626;">
            <i data-lucide="alert-circle" style="width:12px;height:12px;"></i>
            <span>{{ saveError }}</span>
          </div>
          <div v-if="saveSuccess" class="wf-copywrite-feedback" style="background:#F0FDF4;border-color:#86EFAC;color:#059669;">
            <i data-lucide="check-circle" style="width:12px;height:12px;"></i>
            <span>文案已保存，下游节点将使用更新后的内容</span>
          </div>
          <div v-if="regenerateError" class="wf-copywrite-feedback" style="background:#FEF2F2;border-color:#FCA5A5;color:#DC2626;">
            <i data-lucide="alert-circle" style="width:12px;height:12px;"></i>
            <span>{{ regenerateError }}</span>
          </div>
        </div>

        <!-- ===== 右侧：辅助工作区 ===== -->
        <div class="wf-copywrite-aux">
          <div class="wf-aux-header" @click="auxPanelOpen = !auxPanelOpen">
            <span>添加组件</span>
            <span class="wf-aux-toggle" :class="{ 'wf-aux-toggle-collapsed': !auxPanelOpen }">▾</span>
          </div>

          <div v-show="auxPanelOpen" class="wf-aux-body">
            <!-- 添加地点 -->
            <div class="wf-aux-component">
              <div class="wf-aux-comp-input-row">
                <input
                  v-model="locationInput"
                  class="wf-aux-input"
                  placeholder="添加地点"
                  @keyup.enter="addLocation"
                />
                <button class="wf-aux-add-btn" @click="addLocation" :disabled="!locationInput.trim()">+</button>
              </div>
              <div v-if="editLocations.length" class="wf-aux-chips">
                <span v-for="(loc, i) in editLocations" :key="i" class="wf-aux-chip wf-aux-chip-loc">
                  {{ loc }}
                  <button class="wf-aux-chip-remove" @click="removeLocation(i)">×</button>
                </span>
              </div>
            </div>

            <!-- 添加话题 -->
            <div class="wf-aux-component">
              <div class="wf-aux-comp-input-row">
                <input
                  v-model="topicInput"
                  class="wf-aux-input"
                  placeholder="添加话题"
                  @keyup.enter="addTopic"
                />
                <button class="wf-aux-add-btn" @click="addTopic" :disabled="!topicInput.trim()">+</button>
              </div>
              <div v-if="editTopics.length" class="wf-aux-chips">
                <span v-for="(t, i) in editTopics" :key="i" class="wf-aux-chip wf-aux-chip-topic">
                  #{{ t }}
                  <button class="wf-aux-chip-remove" @click="removeTopic(i)">×</button>
                </span>
              </div>
            </div>

            <!-- 导入本地文件 -->
            <div class="wf-aux-component">
              <button class="wf-aux-action-btn" @click="triggerFileInput">
                选择文件
              </button>
              <input
                ref="fileInputRef"
                type="file"
                class="wf-aux-file-hidden"
                accept=".txt,.md,.doc,.docx,.pdf,.csv,.json"
                multiple
                @change="handleFileImport"
              />
              <div v-if="importedFiles.length" class="wf-aux-chips">
                <span v-for="(f, i) in importedFiles" :key="i" class="wf-aux-chip wf-aux-chip-file">
                  {{ f.name }}
                  <button class="wf-aux-chip-remove" @click="removeFile(i)">×</button>
                </span>
              </div>
            </div>

            <!-- 导入表情包 -->
            <div class="wf-aux-component">
              <button class="wf-aux-action-btn" @click="emojiPanelOpen = !emojiPanelOpen">
                {{ emojiPanelOpen ? '收起表情' : '展开表情' }}
              </button>
              <div v-if="emojiPanelOpen" class="wf-aux-emoji-grid">
                <button
                  v-for="emoji in emojiList"
                  :key="emoji"
                  class="wf-aux-emoji-item"
                  @click="insertEmoji(emoji)"
                  :title="emoji"
                >{{ emoji }}</button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="mint-wf-footer" v-if="nodeStatus === 'completed'">
      <div class="wf-node-meta" v-if="nodeMeta">
        <span class="wf-meta-item"><i data-lucide="clock" style="width:12px;height:12px;"></i>{{ nodeMeta.duration }}</span>
        <span class="wf-meta-item"><i data-lucide="cpu" style="width:12px;height:12px;"></i>{{ nodeMeta.model }}</span>
        <span class="wf-meta-item"><i data-lucide="zap" style="width:12px;height:12px;"></i>{{ nodeMeta.tokens }} tokens</span>
      </div>
      <div class="wf-footer-actions">
        <button class="wf-edit-btn wf-edit-regenerate" @click="regenerateCopy" :disabled="regenerating">
          <i data-lucide="refresh-cw" style="width:14px;height:14px;"></i>
          {{ regenerating ? '重新生成中...' : '重新生成' }}
        </button>
        <button class="wf-edit-btn wf-edit-save" @click="saveEdit" :disabled="saving">
          <i data-lucide="check" style="width:14px;height:14px;"></i>
          {{ saving ? '保存中...' : '保存' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
import { createIcons, icons } from 'lucide'
import { workflowApi } from '@/api/workflow'

const props = defineProps<{
  nodeStatus: string
  nodeMeta: { duration: string; model: string; tokens: string } | null
  result: any
  errorMessage?: string
  /** 当前工作流 ID */
  workflowId?: string
}>()

watch(() => props.nodeStatus, () => nextTick(() => createIcons({ icons })))
watch(() => props.result, () => nextTick(() => createIcons({ icons })), { deep: true })

// ===== 编辑状态 =====
const displayData = ref<Record<string, any>>({})

watch(() => props.result, (newResult) => {
  if (newResult) {
    displayData.value = { ...newResult }
    editTitle.value = newResult.title || ''
    editContent.value = newResult.content || ''
    editTagsStr.value = (newResult.tags || []).join(', ')
    editLocations.value = [...(newResult.locations || [])]
    nextTick(() => autoResizeTextarea())
  }
}, { deep: true, immediate: true })

const saving = ref(false)
const saveError = ref('')
const saveSuccess = ref(false)
const regenerating = ref(false)
const regenerateError = ref('')

const editTitle = ref('')
const editContent = ref('')
const editTagsStr = ref('')

// ===== 右侧辅助组件状态 =====
const locationInput = ref('')
const topicInput = ref('')
const editLocations = ref<string[]>([])
const editTopics = ref<string[]>([])
const emojiPanelOpen = ref(false)
const auxPanelOpen = ref(true)
const contentTextareaRef = ref<HTMLTextAreaElement | null>(null)
const fileInputRef = ref<HTMLInputElement | null>(null)

interface ImportedFile {
  name: string
  content: string
}
const importedFiles = ref<ImportedFile[]>([])

function triggerFileInput() {
  fileInputRef.value?.click()
}

async function handleFileImport(event: Event) {
  const input = event.target as HTMLInputElement
  if (!input.files?.length) return

  for (const file of Array.from(input.files)) {
    const text = await readFileContent(file)
    if (text) {
      importedFiles.value.push({ name: file.name, content: text })
      insertFileContentToCursor(text)
    }
  }
  input.value = ''
}

function readFileContent(file: File): Promise<string> {
  return new Promise((resolve) => {
    const reader = new FileReader()
    reader.onload = (e) => {
      resolve((e.target?.result as string) || '')
    }
    reader.onerror = () => resolve('')
    reader.readAsText(file)
  })
}

function insertFileContentToCursor(text: string) {
  const textarea = contentTextareaRef.value
  const trimmed = text.trim()
  if (!trimmed) return

  const separator = editContent.value.length > 0 ? '\n\n' : ''
  const insert = separator + trimmed

  if (textarea) {
    const start = textarea.selectionStart
    const before = editContent.value.substring(0, start)
    const after = editContent.value.substring(textarea.selectionEnd)
    editContent.value = before + insert + after
    nextTick(() => {
      textarea.focus()
      const pos = start + insert.length
      textarea.setSelectionRange(pos, pos)
      autoResizeTextarea()
    })
  } else {
    editContent.value += insert
    nextTick(() => autoResizeTextarea())
  }
}

function removeFile(idx: number) {
  importedFiles.value.splice(idx, 1)
}

// ===== 推荐话题 =====
const suggestedTopics = computed(() => {
  const tags: string[] = displayData.value?.tags || []
  return tags.filter(t => t && t.trim().length > 0)
})

function isTopicUsed(topic: string): boolean {
  const content = editContent.value || ''
  return content.includes(`#${topic}`)
}

function insertTopicToCursor(topic: string) {
  const tag = `#${topic}`
  const textarea = contentTextareaRef.value
  if (textarea) {
    const start = textarea.selectionStart
    const end = textarea.selectionEnd
    const before = editContent.value.substring(0, start)
    const after = editContent.value.substring(end)
    const needSpace = before.length > 0 && !/\s$/.test(before) ? ' ' : ''
    editContent.value = before + needSpace + tag + ' ' + after
    nextTick(() => {
      textarea.focus()
      const pos = start + needSpace.length + tag.length + 1
      textarea.setSelectionRange(pos, pos)
      autoResizeTextarea()
    })
  } else {
    editContent.value += (editContent.value.length > 0 ? ' ' : '') + tag + ' '
    nextTick(() => autoResizeTextarea())
  }
}

function autoResizeTextarea() {
  const ta = contentTextareaRef.value
  if (!ta) return
  ta.style.height = 'auto'
  ta.style.height = ta.scrollHeight + 'px'
}

// 小红书常用表情（精简版）
const emojiList = [
  '😀','😃','😄','😁','😆','😅','🤣','😂','🙂','🙃',
  '😉','😊','😇','🥰','😍','🤩','😘','😗','😚','😙',
  '😋','😛','😜','🤪','😝','🤑','🤗','🤭','🤫','🤔',
  '❤️','🧡','💛','💚','💙','💜','🖤','🤍','🤎','💔',
  '👍','👎','👌','🤌','🤏','✌️','🤞','🤟','🤘','👏',
  '🙌','👐','🤲','🙏','✍️','💪','🔥','✨','🎉','🎊',
  '💯','💢','💥','💫','💦','💨','🕳️','💣','💬','🗨️',
  '📌','📍','📎','🏷️','✅','❌','⭐','🌟','⚡','💡',
]

function addLocation() {
  const val = locationInput.value.trim()
  if (!val) return
  if (!editLocations.value.includes(val)) {
    editLocations.value.push(val)
  }
  locationInput.value = ''
}
function removeLocation(idx: number) {
  editLocations.value.splice(idx, 1)
}

// ===== 话题操作 =====
function addTopic() {
  const val = topicInput.value.trim().replace(/^#/, '')
  if (!val) return
  if (!editTopics.value.includes(val)) {
    editTopics.value.push(val)
  }
  topicInput.value = ''
}
function removeTopic(idx: number) {
  editTopics.value.splice(idx, 1)
}

// ===== 表情插入 =====
function insertEmoji(emoji: string) {
  const textarea = contentTextareaRef.value
  if (textarea) {
    const start = textarea.selectionStart
    const end = textarea.selectionEnd
    editContent.value = editContent.value.substring(0, start) + emoji + editContent.value.substring(end)
    nextTick(() => {
      textarea.focus()
      const pos = start + emoji.length
      textarea.setSelectionRange(pos, pos)
      autoResizeTextarea()
    })
  } else {
    editContent.value += emoji
    nextTick(() => autoResizeTextarea())
  }
}

async function regenerateCopy() {
  if (!props.workflowId) {
    regenerateError.value = '缺少工作流 ID，无法重新生成'
    return
  }

  regenerating.value = true
  regenerateError.value = ''
  saveError.value = ''
  saveSuccess.value = false

  try {
    await workflowApi.rollback(props.workflowId, 'copywrite')
  } catch (e: any) {
    const errMsg = e?.response?.data?.detail || e?.message || String(e)
    regenerateError.value = '重新生成失败：' + errMsg
    console.error('[CopywriteCard] regenerateCopy error:', e)
  } finally {
    regenerating.value = false
  }
}

async function saveEdit() {
  if (!props.workflowId) {
    saveError.value = '缺少工作流 ID，无法保存'
    return
  }

  saving.value = true
  saveError.value = ''
  saveSuccess.value = false

  // 合并标签和话题
  const tagsFromStr = editTagsStr.value
    .split(/[,，]/)
    .map(t => t.trim())
    .filter(t => t.length > 0)
  const allTags = [...new Set([...tagsFromStr, ...editTopics.value])]

  const output: Record<string, any> = {
    title: editTitle.value.trim(),
    content: editContent.value.trim(),
    tags: allTags,
    locations: editLocations.value,
    // 保留上游透传字段
    key_points: displayData.value?.key_points,
    structured_items: displayData.value?.structured_items,
    review_feedback: displayData.value?.review_feedback,
    prompt_source: displayData.value?.prompt_source,
  }

  try {
    await workflowApi.updateNodeOutput(props.workflowId, 'copywrite', output)
    displayData.value = { ...displayData.value, ...output }
    saveSuccess.value = true
    emojiPanelOpen.value = false
    nextTick(() => createIcons({ icons }))
    setTimeout(() => { saveSuccess.value = false }, 3000)
  } catch (e: any) {
    const errMsg = e?.response?.data?.detail || e?.message || String(e)
    saveError.value = '保存失败：' + errMsg
    console.error('[CopywriteCard] saveEdit error:', e)
  } finally {
    saving.value = false
  }
}

const statusColor = computed(() => {
  const map: Record<string, string> = {
    idle: '#9CA3AF',
    running: '#FF2442',
    completed: '#60A5FA',
    error: '#EF4444',
  }
  return map[props.nodeStatus] || '#9CA3AF'
})

const statusLabel = computed(() => {
  const map: Record<string, string> = {
    idle: '待执行',
    running: '执行中',
    completed: '已完成',
    error: '失败',
  }
  return map[props.nodeStatus] || '待执行'
})

const statusBadgeStyle = computed(() => {
  if (props.nodeStatus === 'error') return { background: '#FEE2E2', color: '#DC2626' }
  if (props.nodeStatus === 'completed') return { background: '#DBEAFE', color: '#2563EB' }
  if (props.nodeStatus === 'running') return { background: '#FEE2E2', color: '#DC2626' }
  return { background: '#F1F5F9', color: '#64748B' }
})
</script>

<style scoped>
.wf-empty-hint {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 20px;
  color: #9CA3AF;
  font-size: 15px;
  justify-content: center;
}
.wf-copywrite-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  padding: 20px;
}
.wf-copywrite-loading-text {
  font-size: 15px;
  color: #6B7280;
}
.mint-search-error {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 16px;
  color: #EF4444;
  font-size: 15px;
}

/* ===== 左右分栏布局 ===== */
.wf-copywrite-layout {
  display: flex;
  gap: 16px;
  align-items: flex-start;
  width: 100%;
}
.wf-copywrite-main {
  flex: 1;
  min-width: 0;
}
.wf-copywrite-main-full {
  flex: 1;
}
.wf-copywrite-aux {
  flex: 0 0 200px;
  display: flex;
  flex-direction: column;
  gap: 0;
  padding: 12px;
  background: #fff;
  border: none;
  border-radius: 8px;
  max-height: 400px;
  position: relative;
}

/* ===== 右侧辅助工作区 ===== */
.wf-aux-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 15px;
  font-weight: 600;
  color: #9CA3AF;
  padding-bottom: 8px;
  border-bottom: 1px solid #F0F0F0;
  cursor: pointer;
  user-select: none;
  flex-shrink: 0;
}
.wf-aux-toggle {
  font-size: 16px;
  color: #9CA3AF;
  transition: transform 0.2s;
  line-height: 1;
}
.wf-aux-toggle-collapsed {
  transform: rotate(-90deg);
}
.wf-aux-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
  overflow-y: auto;
  overflow-x: hidden;
  padding-top: 12px;
  flex: 1;
  min-height: 0;
}
.wf-aux-component {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.wf-aux-comp-label {
  font-size: 15px;
  font-weight: 600;
  color: #475569;
}
.wf-aux-optional {
  margin-left: auto;
  font-size: 9px;
  color: #9CA3AF;
  background: #F1F5F9;
  padding: 1px 5px;
  border-radius: 3px;
  font-weight: 400;
}
.wf-aux-comp-input-row {
  display: flex;
  gap: 4px;
}
.wf-aux-input {
  flex: 1;
  min-width: 0;
  border: none;
  border-radius: 6px;
  padding: 6px 10px;
  font-size: 14px;
  color: #1F2937;
  background: #F3F4F6;
  font-family: inherit;
  outline: none;
  transition: background 0.15s;
  box-sizing: border-box;
}
.wf-aux-input:focus {
  background: #E5E7EB;
}
.wf-aux-input::placeholder { color: #9CA3AF; font-size: 15px; }
.wf-aux-add-btn {
  flex-shrink: 0;
  width: 28px;
  height: 28px;
  border: none;
  border-radius: 6px;
  background: #F3F4F6;
  color: #6B7280;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  font-weight: 500;
  transition: all 0.15s;
}
.wf-aux-add-btn:hover:not(:disabled) {
  background: #E5E7EB;
  color: #374151;
}
.wf-aux-add-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.wf-aux-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.wf-aux-chip {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 2px 6px;
  font-size: 15px;
  border-radius: 4px;
  font-weight: 500;
}
.wf-aux-chip-loc {
  background: #FEE2E2;
  color: #DC2626;
}
.wf-aux-chip-topic {
  background: #DBEAFE;
  color: #2563EB;
}
.wf-aux-chip-remove {
  border: none;
  background: none;
  color: inherit;
  cursor: pointer;
  font-size: 15px;
  line-height: 1;
  padding: 0 0 0 2px;
  opacity: 0.6;
}
.wf-aux-chip-remove:hover { opacity: 1; }
.wf-aux-action-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  padding: 6px 10px;
  border: none;
  border-radius: 6px;
  background: #F3F4F6;
  color: #6B7280;
  cursor: pointer;
  font-size: 15px;
  font-family: inherit;
  transition: all 0.15s;
  box-sizing: border-box;
}
.wf-aux-action-btn:hover {
  background: #E5E7EB;
  color: #374151;
}
.wf-aux-file-hidden {
  display: none;
}
.wf-aux-chip-file {
  background: #F0FDF4;
  color: #059669;
}
.wf-aux-emoji-grid {
  display: grid;
  grid-template-columns: repeat(8, 1fr);
  gap: 2px;
  max-height: 120px;
  overflow-y: auto;
  padding: 6px;
  background: #F3F4F6;
  border-radius: 6px;
}
.wf-aux-emoji-item {
  border: none;
  background: none;
  cursor: pointer;
  font-size: 15px;
  padding: 2px;
  border-radius: 3px;
  transition: background 0.1s;
  font-family: inherit;
}
.wf-aux-emoji-item:hover {
  background: #FEF3C7;
}

/* ===== 编辑工具栏（底部） ===== */
.wf-edit-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 5px 12px;
  border: 1px solid #E5E7EB;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  background: #fff;
  color: #374151;
  transition: all 0.15s;
}
.wf-edit-btn:hover:not(:disabled) {
  border-color: #93C5FD;
  color: #2563EB;
}
.wf-edit-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.wf-edit-save {
  background: #2563EB;
  border-color: #2563EB;
  color: #fff;
}
.wf-edit-save:hover:not(:disabled) {
  background: #1D4ED8;
  border-color: #1D4ED8;
  color: #fff;
}
.wf-edit-cancel {
  background: #F3F4F6;
  border-color: #E5E7EB;
  color: #6B7280;
}
.wf-edit-cancel:hover:not(:disabled) {
  background: #E5E7EB;
  color: #374151;
}

/* ===== 小红书创作平台风格 ===== */
.xhs-editor-edit {
  display: flex;
  flex-direction: column;
}
.xhs-title-input {
  width: 100%;
  border: none;
  outline: none;
  font-size: 18px;
  font-weight: 700;
  color: #333333;
  background: transparent;
  padding: 0;
  line-height: 1.5;
  font-family: inherit;
  box-sizing: border-box;
}
.xhs-title-input::placeholder {
  color: #C4C4C4;
  font-weight: 400;
}
.xhs-title-counter {
  font-size: 12px;
  color: #C4C4C4;
  text-align: right;
  padding: 2px 0 0 0;
}
.xhs-divider {
  height: 1px;
  background: #F0F0F0;
  margin: 10px 0;
}
.xhs-content-input {
  width: 100%;
  border: none;
  outline: none;
  font-size: 15px;
  color: #333;
  background: transparent;
  padding: 0;
  line-height: 1.8;
  resize: none;
  overflow: hidden;
  font-family: inherit;
  box-sizing: border-box;
  white-space: pre-wrap;
  word-break: break-word;
  min-height: 80px;
}
.xhs-content-input::placeholder {
  color: #C4C4C4;
}
.xhs-content-counter {
  font-size: 12px;
  color: #C4C4C4;
  text-align: right;
  padding: 2px 0 0 0;
}
.xhs-tags-edit-row {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 8px;
}
.xhs-tags-input-row {
  margin-top: 8px;
}
.xhs-tags-input {
  width: 100%;
  border: none;
  outline: none;
  font-size: 15px;
  color: #13386C;
  background: transparent;
  padding: 0;
  font-family: inherit;
  box-sizing: border-box;
}
.xhs-tags-input::placeholder {
  color: #C4C4C4;
}

/* 推荐话题 */
.xhs-topic-suggest {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px solid #F0F0F0;
}
.xhs-topic-suggest-label {
  font-size: 13px;
  color: #999;
  font-weight: 500;
  margin-right: 2px;
}
.xhs-topic-chip {
  display: inline-flex;
  align-items: center;
  padding: 4px 10px;
  border: 1px solid #E8E8E8;
  border-radius: 14px;
  background: #FAFAFA;
  color: #13386C;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
  font-family: inherit;
  line-height: 1.4;
}
.xhs-topic-chip:hover {
  background: #EDF2FC;
  border-color: #B8CCE8;
}
.xhs-topic-chip-used {
  background: #EDF2FC;
  border-color: #93B4E0;
  color: #2563EB;
}
.wf-copywrite-feedback {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 10px;
  background: #FFFBEB;
  border: 1px solid #FDE68A;
  border-radius: 6px;
  font-size: 14px;
  color: #92400E;
}
.wf-node-copywrite .mint-wf-footer {
  justify-content: space-between;
  align-items: center;
}
.wf-footer-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
.wf-edit-regenerate {
  background: #F3F4F6;
  border-color: #E5E7EB;
  color: #6B7280;
}
.wf-edit-regenerate:hover:not(:disabled) {
  background: #E5E7EB;
  border-color: #D1D5DB;
  color: #374151;
}
.wf-edit-regenerate:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>