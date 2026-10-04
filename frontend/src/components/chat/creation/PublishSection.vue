<template>
  <div class="wdp-section">
    <div class="wdp-section-title">平台</div>
    <div class="wdp-platform-select">
      <button
        v-for="p in PLATFORMS"
        :key="p.key"
        class="wdp-platform-option"
        :class="{ 'wdp-platform-option-active': platform === p.key }"
        @click="$emit('update-platform', p.key)"
      >
        {{ p.label }}
      </button>
    </div>
  </div>
  <div class="wdp-section">
    <div class="wdp-section-title">发布前检查</div>
    <div class="wdp-actions">
      <button class="wdp-action-btn" @click="$emit('chat-action', 'publish_checklist')">
        <ListChecks :size="14" /> 完整性检查
      </button>
      <button class="wdp-action-btn" @click="$emit('chat-action', 'persona_check')">
        <Lightbulb :size="14" /> 人设一致性
      </button>
      <button class="wdp-action-btn" @click="$emit('chat-action', 'quality_gate')">
        <ShieldCheck :size="14" /> 质量门禁
      </button>
      <button class="wdp-action-btn" @click="$emit('chat-action', 'risk_scanner')">
        <Search :size="14" /> 风险扫描
      </button>
      <button v-if="showRepurposing" class="wdp-action-btn" @click="$emit('chat-action', 'content_repurposing')">
        <Dna :size="14" /> 一稿多发改写
      </button>
    </div>
  </div>
  <div class="wdp-section">
    <div class="wdp-section-title">发布</div>
    <div class="wdp-actions">
      <button class="wdp-action-btn wdp-action-primary" @click="$emit('chat-action', 'publish')">
        <Send :size="14" /> 发布到平台
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import './panel-shared.css'
import { ListChecks, Lightbulb, ShieldCheck, Search, Dna, Send } from 'lucide-vue-next'

const PLATFORMS = [
  { key: 'xiaohongshu', label: '小红书' },
  { key: 'douyin', label: '抖音' },
  { key: 'kuaishou', label: '快手' },
  { key: 'bilibili', label: 'B站' },
  { key: 'wechat_video', label: '视频号' },
]

withDefaults(defineProps<{
  platform: string
  showRepurposing?: boolean
}>(), {
  showRepurposing: true,
})

defineEmits<{
  'chat-action': [action: string]
  'update-platform': [platform: string]
}>()
</script>