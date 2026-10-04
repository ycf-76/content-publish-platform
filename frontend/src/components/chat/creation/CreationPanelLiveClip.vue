<template>
  <template v-if="tab === 'discover'">
    <div class="wdp-section">
      <div class="wdp-section-title">录像来源</div>
      <p class="wdp-hint">从直播录像出发，AI 自动提取高光和章节</p>
      <div class="wdp-actions">
        <button class="wdp-action-btn wdp-action-primary" @click="$emit('chat-action', 'upload_livestream')">
          <Upload :size="14" /> 上传播录像
        </button>
        <button class="wdp-action-btn" @click="$emit('chat-action', 'select_from_library')">
          <FolderOpen :size="14" /> 从素材库选择
        </button>
      </div>
    </div>
  </template>

  <template v-if="tab === 'plan'">
    <div class="wdp-section">
      <div class="wdp-section-title">直播策划</div>
      <p class="wdp-hint">AI 分析直播录像，提取高光和章节</p>
      <div class="wdp-actions">
        <button class="wdp-action-btn wdp-action-primary" @click="$emit('chat-action', 'video_highlights')">
          <Sparkles :size="14" /> 提取高光片段
        </button>
        <button class="wdp-action-btn" @click="$emit('chat-action', 'video_chapters')">
          <ListChecks :size="14" /> 章节切分
        </button>
        <button class="wdp-action-btn" @click="$emit('chat-action', 'livestream')">
          <Radio :size="14" /> 直播策划
        </button>
      </div>
    </div>
    <div class="wdp-section">
      <div class="wdp-section-title">标题</div>
      <input class="wdp-draft-input" :value="work.title" @input="onUpdate('title', ($event.target as HTMLInputElement).value)" placeholder="输入切片标题..." />
    </div>
  </template>

  <template v-if="tab === 'produce'">
    <WorkPreview :work="work" />
    <div class="wdp-section">
      <div class="wdp-section-title">剪辑时间线</div>
      <div class="wdp-timeline-placeholder">
        <Film :size="28" :stroke-width="1.2" class="wdp-timeline-icon" />
        <span class="wdp-timeline-hint">在对话中输入剪辑指令，AI 将自动生成时间线</span>
      </div>
    </div>
    <div class="wdp-section">
      <div class="wdp-section-title">AI剪辑工具</div>
      <div class="wdp-actions">
        <button class="wdp-action-btn wdp-action-primary" @click="$emit('chat-action', 'clipify')">
          <Scissors :size="14" /> AI智能剪辑
        </button>
        <button class="wdp-action-btn" @click="$emit('chat-action', 'auto_subtitle')">
          <Type :size="14" /> 自动字幕
        </button>
        <button class="wdp-action-btn" @click="$emit('chat-action', 'beat_sync')">
          <Clapperboard :size="14" /> 卡点视频
        </button>
        <button class="wdp-action-btn" @click="$emit('chat-action', 'video_reframe')">
          <Smartphone :size="14" /> 横竖版转换
        </button>
      </div>
    </div>
  </template>

  <template v-if="tab === 'publish'">
    <div class="wdp-section">
      <div class="wdp-section-title">导出设置</div>
      <p class="wdp-hint">选择目标平台，AI 自动适配分辨率和格式</p>
      <div class="wdp-actions">
        <button class="wdp-action-btn" @click="$emit('chat-action', 'export_douyin')">
          <PlayCircle :size="14" /> 导出抖音
        </button>
        <button class="wdp-action-btn" @click="$emit('chat-action', 'export_xhs')">
          <ImageIcon :size="14" /> 导出小红书
        </button>
        <button class="wdp-action-btn" @click="$emit('chat-action', 'export_bilibili')">
          <Send :size="14" /> 导出B站
        </button>
      </div>
    </div>
    <div class="wdp-section">
      <div class="wdp-section-title">质量检查</div>
      <div class="wdp-actions">
        <button class="wdp-action-btn" @click="$emit('chat-action', 'quality_gate')">
          <ListChecks :size="14" /> 质量门禁
        </button>
        <button class="wdp-action-btn" @click="$emit('chat-action', 'risk_scanner')">
          <Search :size="14" /> 风险扫描
        </button>
      </div>
    </div>
  </template>

  <template v-if="tab === 'attribute'">
    <AttributeSection @chat-action="$emit('chat-action', $event)" />
  </template>
</template>

<script setup lang="ts">
import './panel-shared.css'
import {
  Type, Image as ImageIcon, Sparkles, ListChecks, Scissors, Film,
  Clapperboard, Smartphone, PlayCircle, Send, Search,
  Upload, FolderOpen, Radio
} from 'lucide-vue-next'
import { useWorkStore, type WorkItem } from '@/stores/work'
import AttributeSection from './AttributeSection.vue'
import WorkPreview from './WorkPreview.vue'

const props = defineProps<{
  work: WorkItem
  tab: string
}>()

defineEmits<{
  'chat-action': [action: string]
}>()

const workStore = useWorkStore()

function onUpdate(field: string, value: string) {
  workStore.updateDraft(props.work.id, { [field]: value })
}
</script>