<template>
  <div>
    <!-- Expanded -->
    <div
      ref="dialogEl"
      class="mint-dialog mint-glass"
      :class="{ 'mint-hidden': dialogState !== 'expanded' }"
      style="right:20px; bottom:20px;"
    >
      <div ref="dragHandle" class="mint-dialog-header">
        <div class="mint-dialog-icon"><i data-lucide="sparkles"></i></div>
        <span class="font-cal mint-dialog-title">灵犀助手</span>
        <span class="mint-dialog-online"></span>
        <button class="mint-dialog-btn" title="收起" @click="collapseDialog">
          <i data-lucide="minus"></i>
        </button>
        <button class="mint-dialog-btn" title="关闭" @click="closeDialog">
          <i data-lucide="x"></i>
        </button>
      </div>

      <div class="mint-dialog-body" ref="dialogBody">
        <div class="mint-chat-bubble mint-chat-assistant">
          你好，我是灵犀助手。可以帮你搜索热点、生成文案、优化标题，随时吩咐～
        </div>
        <div class="mint-chat-bubble mint-chat-user">
          帮我搜索夏日穿搭的热点
        </div>
        <div class="mint-chat-bubble mint-chat-assistant">
          已找到 3 个高热度关键词：「夏日清凉穿搭」12.3w搜索、「防晒好物推荐」8.7w搜索、「海边度假穿搭」6.2w搜索。已自动添加到工作流第一步。
        </div>
      </div>

      <div class="mint-quick-commands">
        <button class="mint-quick-cmd" @click="setQuickCmd($event)">生成文案</button>
        <button class="mint-quick-cmd" @click="setQuickCmd($event)">搜索热点</button>
        <button class="mint-quick-cmd" @click="setQuickCmd($event)">优化标题</button>
        <button class="mint-quick-cmd" @click="setQuickCmd($event)">检查合规</button>
      </div>

      <div class="mint-dialog-input-row">
        <input
          type="text"
          class="mint-dialog-input"
          placeholder="输入指令..."
          ref="dialogInput"
          @keydown.enter="sendMessage"
        >
        <button class="mint-send-btn" title="发送" @click="sendMessage">
          <i data-lucide="send"></i>
        </button>
      </div>
    </div>

    <!-- Collapsed state -->
    <div
      class="mint-dialog-collapsed mint-glass"
      :class="{ 'mint-hidden': dialogState !== 'collapsed' }"
      @click="expandDialog"
    >
      <div class="mint-dialog-collapsed-icon"><i data-lucide="sparkles"></i></div>
      <span class="mint-dialog-collapsed-text">灵犀助手 · 已收起</span>
      <i data-lucide="chevron-up" style="width:16px; height:16px; color:#FF2442;"></i>
    </div>

    <!-- Reopen FAB -->
    <button
      class="mint-dialog-reopen"
      :class="{ 'mint-hidden': dialogState !== 'closed' }"
      @click="expandDialog"
    >
      <i data-lucide="sparkles"></i>
    </button>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick } from 'vue'
import { createIcons, icons } from 'lucide'
import { useDialogDrag } from '@/composables/useDialogDrag'

const {
  dialogState,
  dialogEl,
  dragHandle,
  collapseDialog,
  closeDialog,
  expandDialog,
  restoreDialogPosition,
  setupDrag,
  destroyDrag,
} = useDialogDrag()

const dialogBody = ref<HTMLElement | null>(null)
const dialogInput = ref<HTMLInputElement | null>(null)

function sendMessage() {
  const inputField = dialogInput.value
  const body = dialogBody.value
  if (!inputField || !body) return
  const text = inputField.value.trim()
  if (!text) return
  const userBubble = document.createElement('div')
  userBubble.className = 'mint-chat-bubble mint-chat-user'
  userBubble.textContent = text
  body.appendChild(userBubble)
  inputField.value = ''
  body.scrollTop = body.scrollHeight
  setTimeout(() => {
    const responses = [
      '已收到指令，正在处理中...',
      '好的，我已将任务加入工作流队列。',
      '已完成分析，结果已同步到工作区。',
      '正在调用模型生成内容，请稍候。'
    ]
    const response = responses[Math.floor(Math.random() * responses.length)]
    const assistantBubble = document.createElement('div')
    assistantBubble.className = 'mint-chat-bubble mint-chat-assistant'
    assistantBubble.textContent = response
    body.appendChild(assistantBubble)
    body.scrollTop = body.scrollHeight
  }, 600)
}

function setQuickCmd(e: Event) {
  const inputField = dialogInput.value
  if (!inputField) return
  inputField.value = (e.currentTarget as HTMLElement).textContent || ''
  inputField.focus()
}

onMounted(() => {
  nextTick(() => {
    createIcons({ icons })
    restoreDialogPosition()
    setupDrag()
  })
})

onUnmounted(() => {
  destroyDrag()
})
</script>