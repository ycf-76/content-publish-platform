<template>
  <template v-if="tab === 'discover'">
    <DiscoverSection
      :hint="'AI 扫描热点视频和竞品，发现短视频选题机会'"
      @chat-action="$emit('chat-action', $event)"
    />
  </template>

  <template v-if="tab === 'plan'">
    <div class="wdp-section">
      <div class="wdp-section-title">视频策划</div>
      <p class="wdp-hint">AI 分析热点视频和竞品，生成视频选题方向</p>
      <div class="wdp-actions">
        <button class="wdp-action-btn" @click="$emit('chat-action', 'content_matrix')">
          <ListChecks :size="14" /> 生成选题矩阵
        </button>
        <button class="wdp-action-btn" @click="$emit('chat-action', 'video_strategy')">
          <BarChart3 :size="14" /> 视频策略
        </button>
        <button class="wdp-action-btn" @click="$emit('chat-action', 'topic_evaluator')">
          <Star :size="14" /> 选题评分
        </button>
        <button class="wdp-action-btn" @click="$emit('chat-action', 'hook_generator')">
          <Sparkles :size="14" /> Hook生成
        </button>
      </div>
    </div>
    <div class="wdp-section">
      <div class="wdp-section-title">脚本与分镜</div>
      <div class="wdp-actions">
        <button class="wdp-action-btn wdp-action-primary" @click="$emit('chat-action', 'video_script')">
          <Wand2 :size="14" /> AI生成脚本
        </button>
        <button class="wdp-action-btn" @click="$emit('chat-action', 'article_outline')">
          <FileText :size="14" /> 分镜脚本
        </button>
      </div>
    </div>
    <div class="wdp-section">
      <div class="wdp-section-title">人设检查</div>
      <div class="wdp-actions">
        <button class="wdp-action-btn" @click="$emit('chat-action', 'persona_check')">
          <Lightbulb :size="14" /> 人设一致性检查
        </button>
      </div>
    </div>
  </template>

  <template v-if="tab === 'produce'">
    <WorkPreview :work="work" />
    <div class="wdp-section">
      <div class="wdp-section-title">标题</div>
      <input class="wdp-draft-input" :value="work.title" @input="onUpdate('title', ($event.target as HTMLInputElement).value)" placeholder="输入视频标题..." />
    </div>
    <div class="wdp-section">
      <div class="wdp-section-title">视频脚本</div>
      <textarea class="wdp-draft-textarea" :value="work.scriptText || work.contentText" @input="onUpdate('scriptText', ($event.target as HTMLTextAreaElement).value)" placeholder="输入视频脚本..." rows="8"></textarea>
    </div>
    <div class="wdp-section">
      <div class="wdp-section-title">AI视频生成</div>
      <div class="wdp-actions">
        <button class="wdp-action-btn wdp-action-primary" @click="$emit('chat-action', 'ai_video_gen')">
          <Wand2 :size="14" /> AI生成视频
        </button>
        <button class="wdp-action-btn" @click="$emit('chat-action', 'auto_short_video')">
          <PlayCircle :size="14" /> 一键成片
        </button>
      </div>
    </div>
    <div class="wdp-section">
      <div class="wdp-section-title">剪辑与特效</div>
      <div class="wdp-actions">
        <button class="wdp-action-btn" @click="$emit('chat-action', 'video_editing')">
          <Scissors :size="14" /> 视频剪辑
        </button>
        <button class="wdp-action-btn" @click="$emit('chat-action', 'video_reframe')">
          <Smartphone :size="14" /> 横竖版转换
        </button>
        <button class="wdp-action-btn" @click="$emit('chat-action', 'beat_sync')">
          <Clapperboard :size="14" /> 音乐卡点
        </button>
        <button class="wdp-action-btn" @click="$emit('chat-action', 'slideshow_video')">
          <ImageIcon :size="14" /> 相册视频
        </button>
      </div>
    </div>
    <div class="wdp-section">
      <div class="wdp-section-title">封面与字幕</div>
      <div class="wdp-actions">
        <button class="wdp-action-btn" @click="$emit('chat-action', 'design_cover')">
          <ImageIcon :size="14" /> AI设计封面
        </button>
        <button class="wdp-action-btn" @click="$emit('chat-action', 'auto_subtitle')">
          <Type :size="14" /> 自动字幕
        </button>
        <button class="wdp-action-btn" @click="$emit('chat-action', 'tts_voiceover')">
          <Mic :size="14" /> TTS旁白
        </button>
      </div>
    </div>
    <div class="wdp-section">
      <div class="wdp-section-title">标签</div>
      <div class="wdp-tags" v-if="work.tags?.length">
        <span class="wdp-tag" v-for="tag in work.tags" :key="tag">
          #{{ tag }}
          <button class="wdp-tag-remove" @click="removeTag(tag)"><X :size="10" /></button>
        </span>
      </div>
      <div class="wdp-tag-add-row">
        <input class="wdp-draft-input wdp-tag-input" v-model="newTag" @keydown.enter="addTag" placeholder="添加标签..." />
        <button class="wdp-tag-add-btn" @click="addTag">添加</button>
      </div>
    </div>
  </template>

  <template v-if="tab === 'publish'">
    <PublishSection
      :platform="work.platform"
      @chat-action="$emit('chat-action', $event)"
      @update-platform="onUpdate('platform', $event)"
    />
  </template>

  <template v-if="tab === 'attribute'">
    <AttributeSection @chat-action="$emit('chat-action', $event)" />
  </template>
</template>

<script setup lang="ts">
import './panel-shared.css'
import { ref } from 'vue'
import {
  X, Type, Image as ImageIcon, Lightbulb, Sparkles, ListChecks, Star, Wand2,
  FileText, BarChart3, PlayCircle, Scissors, Smartphone, Clapperboard, Mic
} from 'lucide-vue-next'
import { useWorkStore, type WorkItem } from '@/stores/work'
import DiscoverSection from './DiscoverSection.vue'
import PublishSection from './PublishSection.vue'
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
const newTag = ref('')

function onUpdate(field: string, value: string) {
  workStore.updateDraft(props.work.id, { [field]: value })
}

function addTag() {
  if (!newTag.value.trim()) return
  const tags = [...(props.work.tags || []), newTag.value.trim()]
  workStore.updateDraft(props.work.id, { tags })
  newTag.value = ''
}

function removeTag(tag: string) {
  const tags = (props.work.tags || []).filter(t => t !== tag)
  workStore.updateDraft(props.work.id, { tags })
}
</script>