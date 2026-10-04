<template>
  <template v-if="tab === 'discover'">
    <div class="wdp-section">
      <div class="wdp-section-title">素材来源</div>
      <p class="wdp-hint">从已有长视频或直播录像出发，AI 自动分析并规划剪辑方案</p>
      <div class="wdp-actions">
        <button class="wdp-action-btn wdp-action-primary" @click="$emit('chat-action', 'upload_material')">
          <Upload :size="14" /> 上传素材
        </button>
        <button class="wdp-action-btn" @click="$emit('chat-action', 'select_from_library')">
          <FolderOpen :size="14" /> 从素材库选择
        </button>
      </div>
    </div>
  </template>

  <template v-if="tab === 'plan'">
    <div class="wdp-section">
      <div class="wdp-section-title">剪辑策划</div>
      <p class="wdp-hint">AI 分析视频素材，规划剪辑方案</p>
      <div class="wdp-actions">
        <button class="wdp-action-btn wdp-action-primary" @click="$emit('chat-action', 'video_highlights')">
          <Sparkles :size="14" /> 提取高光片段
        </button>
        <button class="wdp-action-btn" @click="$emit('chat-action', 'video_chapters')">
          <ListChecks :size="14" /> 章节切分
        </button>
        <button class="wdp-action-btn" @click="$emit('chat-action', 'clipify')">
          <Scissors :size="14" /> 长转短剪辑
        </button>
      </div>
    </div>
    <div class="wdp-section">
      <div class="wdp-section-title">标题</div>
      <input class="wdp-draft-input" :value="work.title" @input="onUpdate('title', ($event.target as HTMLInputElement).value)" placeholder="输入剪辑标题..." />
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
    <div class="wdp-section" v-if="work.scriptText">
      <div class="wdp-section-title">参考脚本</div>
      <div class="wdp-content-text">{{ work.scriptText }}</div>
    </div>
    <div class="wdp-section">
      <div class="wdp-section-title">AI剪辑工具</div>
      <div class="wdp-actions">
        <button class="wdp-action-btn wdp-action-primary" @click="$emit('chat-action', 'ai_clip')">
          <Scissors :size="14" /> AI智能剪辑
        </button>
        <button class="wdp-action-btn" @click="$emit('chat-action', 'auto_subtitle')">
          <Type :size="14" /> 自动字幕
        </button>
        <button class="wdp-action-btn" @click="$emit('chat-action', 'beat_sync')">
          <Clapperboard :size="14" /> 卡点视频
        </button>
        <button class="wdp-action-btn" @click="$emit('chat-action', 'video_reframe')">
          <Smartphone :size="14" /> 9:16竖版重框
        </button>
        <button class="wdp-action-btn" @click="$emit('chat-action', 'silence_remove')">
          <VolumeX :size="14" /> 静音移除
        </button>
        <button class="wdp-action-btn" @click="$emit('chat-action', 'video_intro_outro')">
          <Film :size="14" /> 片头片尾
        </button>
        <button class="wdp-action-btn" @click="$emit('chat-action', 'design_cover')">
          <ImageIcon :size="14" /> 设计封面
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
  Clapperboard, Smartphone, VolumeX, PlayCircle, Send, Search,
  Upload, FolderOpen
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