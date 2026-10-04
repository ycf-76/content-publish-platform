<template>
  <div class="wdp-section">
    <div class="wdp-section-title">发现</div>
    <p class="wdp-hint">{{ hint }}</p>
    <div class="wdp-actions">
      <button class="wdp-action-btn" @click="$emit('chat-action', 'trending_topics')">
        <Sparkles :size="14" /> 热点雷达
      </button>
      <button class="wdp-action-btn" @click="$emit('chat-action', 'competitor_analysis')">
        <BarChart3 :size="14" /> 竞品分析
      </button>
      <button class="wdp-action-btn" @click="$emit('chat-action', 'content_gap_analysis')">
        <Search :size="14" /> 内容缺口
      </button>
      <button v-if="showRss" class="wdp-action-btn" @click="$emit('chat-action', 'rss_aggregator')">
        <Rss :size="14" /> RSS聚合
      </button>
      <button v-if="showUgc" class="wdp-action-btn" @click="$emit('chat-action', 'ugc_discovery')">
        <Users :size="14" /> UGC发现
      </button>
      <button v-if="showAlgorithm" class="wdp-action-btn" @click="$emit('chat-action', 'algorithm_updates')">
        <Zap :size="14" /> 算法动态
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import './panel-shared.css'
import { Sparkles, BarChart3, Search, Rss, Users, Zap } from 'lucide-vue-next'

withDefaults(defineProps<{
  hint?: string
  showRss?: boolean
  showUgc?: boolean
  showAlgorithm?: boolean
}>(), {
  hint: 'AI 全网扫描热点、竞品和内容缺口',
  showRss: false,
  showUgc: false,
  showAlgorithm: false,
})

defineEmits<{
  'chat-action': [action: string]
}>()
</script>