<template>
  <div class="dsh-user-row">
    <div class="dsh-user-stack">
      <div class="dsh-bubble" v-html="renderUserHtml(msg.content)"></div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { renderUserHtml } from './chat-content-renderer'
import type { ChatMessage } from './cell-types'

defineProps<{
  msg: ChatMessage
}>()
</script>