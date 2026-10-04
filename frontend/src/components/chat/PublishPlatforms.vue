<template>
  <div class="pub-row" v-if="showPublish">
    <span class="pub-label">发布</span>
    <button
      v-for="p in platforms"
      :key="p.key"
      class="pub-chip"
      :class="{ 'pub-published': p.published }"
      @click="onPublish(p.key)"
    >
      <PlatformLogo :platform="p.key" :name="p.name" />
      <span>{{ p.name }}</span>
      <Check v-if="p.published" :size="10" class="pub-check" />
    </button>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Check } from 'lucide-vue-next'
import PlatformLogo from './PlatformLogo.vue'
import type { WorkItem } from '@/stores/work'

const props = defineProps<{
  work: WorkItem
}>()

const emit = defineEmits<{
  'chat-action': [action: string]
}>()

const showPublish = computed(() => props.work.isDraft)

const PLATFORMS = [
  { key: 'xiaohongshu', name: '小红书', action: 'publish_xiaohongshu' },
  { key: 'douyin', name: '抖音', action: 'publish_douyin' },
  { key: 'kuaishou', name: '快手', action: 'publish_kuaishou' },
  { key: 'bilibili', name: 'B站', action: 'publish_bilibili' },
  { key: 'zhihu', name: '知乎', action: 'publish_zhihu' },
  { key: 'wechat_video', name: '视频号', action: 'publish_wechat' },
]

const platforms = computed(() => {
  const publishedPlatforms: string[] = props.work.publishedPlatforms || []
  return PLATFORMS.map(p => ({
    ...p,
    published: publishedPlatforms.includes(p.key),
  }))
})

function onPublish(key: string) {
  const p = PLATFORMS.find(x => x.key === key)
  if (p) emit('chat-action', p.action)
}
</script>

<style scoped>
.pub-row {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  border-top: 1px solid rgba(0, 0, 0, 0.04);
  flex-wrap: wrap;
}
.pub-label {
  font-size: 11px;
  font-weight: 600;
  color: #888;
  flex-shrink: 0;
}
.pub-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 8px 3px 4px;
  border: 1px solid rgba(0, 0, 0, 0.06);
  border-radius: 14px;
  background: #fafafa;
  font-size: 11px;
  color: #555;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
  white-space: nowrap;
}
.pub-chip:hover {
  border-color: rgba(0, 0, 0, 0.12);
  background: #f0f0f0;
}
.pub-published {
  opacity: 0.5;
}
.pub-check {
  color: #10b981;
}
</style>