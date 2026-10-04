<template>
  <template v-if="tab === 'discover'">
    <DiscoverSection
      :hint="'AI 扫描热点话题和竞品长文，发现选题机会'"
      :show-rss="true"
      @chat-action="$emit('chat-action', $event)"
    />
  </template>

  <template v-if="tab === 'plan'">
    <div class="wdp-section">
      <div class="wdp-section-title">选题策划</div>
      <p class="wdp-hint">AI 分析热点，生成长文选题和大纲</p>
      <div class="wdp-actions">
        <button class="wdp-action-btn" @click="$emit('chat-action', 'content_matrix')">
          <ListChecks :size="14" /> 生成选题矩阵
        </button>
        <button class="wdp-action-btn" @click="$emit('chat-action', 'topic_evaluator')">
          <Star :size="14" /> 选题评分
        </button>
        <button class="wdp-action-btn wdp-action-primary" @click="$emit('chat-action', 'article_outline')">
          <FileText :size="14" /> 生成文章大纲
        </button>
      </div>
    </div>
    <div class="wdp-section">
      <div class="wdp-section-title">人设与定位</div>
      <div class="wdp-actions">
        <button class="wdp-action-btn" @click="$emit('chat-action', 'voice_builder')">
          <Dna :size="14" /> 构建人设画像
        </button>
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
      <input class="wdp-draft-input" :value="work.title" @input="onUpdate('title', ($event.target as HTMLInputElement).value)" placeholder="输入文章标题..." />
    </div>
    <div class="wdp-section">
      <div class="wdp-section-title">长文撰写</div>
      <div class="wdp-actions">
        <button class="wdp-action-btn wdp-action-primary" @click="$emit('chat-action', 'copywriting')">
          <Wand2 :size="14" /> AI撰写长文
        </button>
        <button class="wdp-action-btn" @click="$emit('chat-action', 'novel_writer')">
          <BookOpen :size="14" /> 小说连载
        </button>
        <button class="wdp-action-btn" @click="$emit('chat-action', 'paper_explainer')">
          <GraduationCap :size="14" /> 论文解读
        </button>
      </div>
    </div>
    <div class="wdp-section">
      <div class="wdp-section-title">正文</div>
      <textarea class="wdp-draft-textarea" :value="work.contentText" @input="onUpdate('contentText', ($event.target as HTMLTextAreaElement).value)" placeholder="输入正文内容..." rows="10"></textarea>
    </div>
    <div class="wdp-section">
      <div class="wdp-section-title">改写与润色</div>
      <div class="wdp-actions">
        <button class="wdp-action-btn" @click="$emit('chat-action', 'text_polisher')">
          <Sparkles :size="14" /> 文案润色
        </button>
        <button class="wdp-action-btn" @click="$emit('chat-action', 'text_condenser')">
          <Minimize2 :size="14" /> 压缩精简
        </button>
        <button class="wdp-action-btn" @click="$emit('chat-action', 'style_transfer')">
          <Palette :size="14" /> 风格迁移
        </button>
        <button class="wdp-action-btn" @click="$emit('chat-action', 'post_formatter')">
          <Layout :size="14" /> 帖子框架化
        </button>
      </div>
    </div>
    <div class="wdp-section">
      <div class="wdp-section-title">视觉辅助</div>
      <div class="wdp-actions">
        <button class="wdp-action-btn" @click="$emit('chat-action', 'mindmap')">
          <GitBranch :size="14" /> 思维导图
        </button>
        <button class="wdp-action-btn" @click="$emit('chat-action', 'gzh_design')">
          <LayoutGrid :size="14" /> 公众号排版
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
  X, Dna, Lightbulb, Sparkles, ListChecks, Star, Wand2, FileText,
  BookOpen, GraduationCap, Minimize2, Palette, Layout, GitBranch,
  LayoutGrid
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