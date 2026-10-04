<template>
  <template v-if="tab === 'discover'">
    <DiscoverSection
      :hint="'AI 扫描热点话题和竞品口播视频，发现选题机会'"
      @chat-action="$emit('chat-action', $event)"
    />
  </template>

  <template v-if="tab === 'plan'">
    <div class="wdp-section">
      <div class="wdp-section-title">选题策划</div>
      <p class="wdp-hint">AI 分析热点，生成口播选题和脚本框架</p>
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
      </div>
    </div>
    <div class="wdp-section">
      <div class="wdp-section-title">口播脚本</div>
      <div class="wdp-actions">
        <button class="wdp-action-btn wdp-action-primary" @click="$emit('chat-action', 'video_script')">
          <Wand2 :size="14" /> AI生成口播脚本
        </button>
      </div>
    </div>
    <div class="wdp-section">
      <div class="wdp-section-title">人设检查</div>
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
      <input class="wdp-draft-input" :value="work.title" @input="onUpdate('title', ($event.target as HTMLInputElement).value)" placeholder="输入口播标题..." />
    </div>
    <div class="wdp-section">
      <div class="wdp-section-title">口播脚本</div>
      <textarea class="wdp-draft-textarea" :value="work.scriptText || work.contentText" @input="onUpdate('scriptText', ($event.target as HTMLTextAreaElement).value)" placeholder="输入口播脚本..." rows="8"></textarea>
    </div>
    <div class="wdp-section">
      <div class="wdp-section-title">配音与字幕</div>
      <div class="wdp-actions">
        <button class="wdp-action-btn wdp-action-primary" @click="$emit('chat-action', 'tts_voiceover')">
          <Mic :size="14" /> TTS配音
        </button>
        <button class="wdp-action-btn" @click="$emit('chat-action', 'auto_subtitle')">
          <Type :size="14" /> 自动字幕
        </button>
        <button class="wdp-action-btn" @click="$emit('chat-action', 'multi_voice_dubbing')">
          <Users :size="14" /> 多角色配音
        </button>
      </div>
    </div>
    <div class="wdp-section">
      <div class="wdp-section-title">片头片尾</div>
      <div class="wdp-actions">
        <button class="wdp-action-btn" @click="$emit('chat-action', 'video_intro_outro')">
          <Film :size="14" /> 片头片尾
        </button>
      </div>
    </div>
    <div class="wdp-section">
      <div class="wdp-section-title">改写工具</div>
      <div class="wdp-actions">
        <button class="wdp-action-btn" @click="$emit('chat-action', 'style_transfer')">
          <Palette :size="14" /> 口语化改写
        </button>
        <button class="wdp-action-btn" @click="$emit('chat-action', 'text_polisher')">
          <Sparkles :size="14" /> 去AI感
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
  X, Type, Dna, Lightbulb, Sparkles, ListChecks, Star, Wand2,
  Mic, Users, Film, Palette
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