<template>
  <div class="wdp-section">
    <div class="wdp-section-title">归因</div>
    <p class="wdp-hint">发布后追踪数据、洞察评论、复盘优化</p>
    <div class="wdp-actions">
      <button class="wdp-action-btn" @click="$emit('chat-action', 'data_tracker')">
        <TrendingUp :size="14" /> 数据追踪
      </button>
      <button class="wdp-action-btn" @click="$emit('chat-action', 'comment_insights')">
        <MessageCircle :size="14" /> 评论洞察
      </button>
      <button class="wdp-action-btn" @click="$emit('chat-action', 'content_postmortem')">
        <FileSearch :size="14" /> 内容复盘
      </button>
      <button class="wdp-action-btn" @click="$emit('chat-action', 'strategy_advisor')">
        <Compass :size="14" /> 策略迭代
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import './panel-shared.css'
import { TrendingUp, MessageCircle, FileSearch, Compass } from 'lucide-vue-next'

defineEmits<{
  'chat-action': [action: string]
}>()
</script>