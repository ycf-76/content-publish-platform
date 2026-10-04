<template>
  <template v-if="tab === 'discover'">
    <DiscoverSection
      :hint="'AI 全网扫描热点、竞品和内容缺口，发现图文选题机会'"
      :show-rss="true"
      :show-ugc="true"
      @chat-action="$emit('chat-action', $event)"
    />
  </template>

  <template v-if="tab === 'plan'">
    <div class="wdp-section">
      <div class="wdp-section-title">选题策划</div>
      <p class="wdp-hint">AI 分析热点和竞品，生成选题方向和内容矩阵</p>
      <div class="wdp-actions">
        <button class="wdp-action-btn" @click="$emit('chat-action', 'content_matrix')">
          <ListChecks :size="14" /> 生成选题矩阵
        </button>
        <button class="wdp-action-btn" @click="$emit('chat-action', 'topic_evaluator')">
          <Star :size="14" /> 选题评分
        </button>
        <button class="wdp-action-btn" @click="$emit('chat-action', 'hook_generator')">
          <Sparkles :size="14" /> Hook生成
        </button>
        <button class="wdp-action-btn" @click="$emit('chat-action', 'carousel_planner')">
          <LayoutGrid :size="14" /> 轮播图策划
        </button>
      </div>
    </div>
    <div class="wdp-section">
      <div class="wdp-section-title">人设与定位</div>
      <p class="wdp-hint">确保内容符合你的创作者人设和声音</p>
      <div class="wdp-actions">
        <button class="wdp-action-btn" @click="$emit('chat-action', 'voice_builder')">
          <Dna :size="14" /> 构建人设画像
        </button>
        <button class="wdp-action-btn" @click="$emit('chat-action', 'persona_check')">
          <Lightbulb :size="14" /> 人设一致性检查
        </button>
        <button class="wdp-action-btn" @click="$emit('chat-action', 'positioning_analysis')">
          <Target :size="14" /> 账号定位分析
        </button>
      </div>
    </div>
  </template>

  <template v-if="tab === 'produce'">
    <WorkPreview :work="work" />
    <div class="wdp-section">
      <div class="wdp-section-title">标题</div>
      <input class="wdp-draft-input" :value="work.title" @input="onUpdate('title', ($event.target as HTMLInputElement).value)" placeholder="输入作品标题..." />
    </div>
    <div class="wdp-section">
      <div class="wdp-section-title">小红书笔记</div>
      <div class="wdp-actions">
        <button class="wdp-action-btn wdp-action-primary" @click="$emit('chat-action', 'xhs_note_creator')">
          <Wand2 :size="14" /> AI生成笔记
        </button>
        <button class="wdp-action-btn" @click="$emit('chat-action', 'copywriting')">
          <PenLine :size="14" /> 撰写文案
        </button>
        <button class="wdp-action-btn" @click="$emit('chat-action', 'social_content')">
          <FileText :size="14" /> 社媒通用内容
        </button>
      </div>
    </div>
    <div class="wdp-section">
      <div class="wdp-section-title">视觉卡片</div>
      <div class="wdp-actions">
        <button class="wdp-action-btn" @click="$emit('chat-action', 'card_xiaohongshu')">
          <ImageIcon :size="14" /> 小红书知识卡
        </button>
        <button class="wdp-action-btn" @click="$emit('chat-action', 'card_quote')">
          <Quote :size="14" /> 金句卡
        </button>
        <button class="wdp-action-btn" @click="$emit('chat-action', 'card_design')">
          <Layout :size="14" /> 卡片设计
        </button>
        <button class="wdp-action-btn" @click="$emit('chat-action', 'infographic')">
          <BarChart3 :size="14" /> 信息图
        </button>
        <button class="wdp-action-btn" @click="$emit('chat-action', 'poster_hero')">
          <Frame :size="14" /> 海报
        </button>
        <button class="wdp-action-btn" @click="$emit('chat-action', 'comparison_card')">
          <Columns :size="14" /> 对比图
        </button>
      </div>
    </div>
    <div class="wdp-section">
      <div class="wdp-section-title">正文</div>
      <textarea class="wdp-draft-textarea" :value="work.contentText" @input="onUpdate('contentText', ($event.target as HTMLTextAreaElement).value)" placeholder="输入正文内容..." rows="6"></textarea>
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
    <div class="wdp-section">
      <div class="wdp-section-title">文案工具</div>
      <div class="wdp-actions">
        <button class="wdp-action-btn" @click="$emit('chat-action', 'optimize_title')">
          <Type :size="14" /> 生成标题
        </button>
        <button class="wdp-action-btn" @click="$emit('chat-action', 'generate_tags')">
          <Hash :size="14" /> 生成标签
        </button>
        <button class="wdp-action-btn" @click="$emit('chat-action', 'style_transfer')">
          <Palette :size="14" /> 风格迁移
        </button>
        <button class="wdp-action-btn" @click="$emit('chat-action', 'text_polisher')">
          <Sparkles :size="14" /> 去AI感改写
        </button>
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
  X, Type, Image as ImageIcon, Dna, Lightbulb, Sparkles, Hash, PenLine,
  ListChecks, Star, Wand2, FileText, BarChart3, Layout, Frame, Columns,
  Quote, Target, LayoutGrid, Palette
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

const emit = defineEmits<{
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