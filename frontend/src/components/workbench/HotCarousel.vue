<template>
  <div>
    <div
      class="hot-carousel"
      @mouseenter="stopHotTimer"
      @mouseleave="startHotTimer"
      v-if="hotSlides.length > 0"
    >
      <div class="hot-slide" v-if="currentHot" @click="$emit('slide-click', currentHot)" :title="`点击使用「${currentHot.title.slice(0,20)}」发起工作流`">
        <div class="hot-slide-body">
          <div class="hot-slide-title">{{ currentHot.title }}</div>
          <div class="hot-slide-meta">
            <span class="hot-meta-platform">{{ currentHot.platform }}</span>
            <span class="hot-meta-sep">·</span>
            <span class="hot-meta-heat" v-if="currentHot.auto_source === 'monitor'">热度 {{ currentHot.heat_score.toFixed(1) }}</span>
            <span class="hot-meta-likes" v-else>赞 {{ currentHot.likes }}</span>
            <span class="hot-meta-sep" v-if="currentHot.dimensions?.emotion">·</span>
            <span class="hot-meta-dim" v-if="currentHot.dimensions?.emotion">{{ currentHot.dimensions.emotion }}</span>
          </div>
        </div>
        <div class="hot-slide-badge" v-if="currentHot.auto_source === 'monitor'">监控</div>
      </div>

      <div class="hot-dots" v-if="hotSlides.length > 1">
        <span
          v-for="(_, i) in hotSlides"
          :key="i"
          class="hot-dot"
          :class="{ 'is-active': i === hotIndex }"
          @click="hotGo(i)"
        ></span>
      </div>
    </div>

    <!-- 空状态：选题池暂无数据 -->
    <div class="hot-carousel hot-carousel-empty" v-else>
      <i data-lucide="radar"></i>
      <span>选题池暂无热点数据，可前往「选题池」抓取内容</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, nextTick } from 'vue'
import { createIcons, icons } from 'lucide'
import { useHotCarousel } from '@/composables/useHotCarousel'
import type { TopicPoolItem } from '@/api/topic_pool'

defineProps<{}>()

defineEmits<{
  'slide-click': [item: TopicPoolItem]
}>()

const {
  hotSlides,
  hotIndex,
  currentHot,
  loadHotSlides,
  hotGo,
  startHotTimer,
  stopHotTimer,
} = useHotCarousel()

onMounted(async () => {
  await loadHotSlides()
  startHotTimer()
  nextTick(() => createIcons({ icons }))
})
</script>

<style scoped>
.hot-carousel {
  position: relative;
  padding: 10px 16px;
  background: #fff;
  border: 1px solid #E5E7EB;
  border-radius: 10px;
  overflow: hidden;
  min-height: 56px;
  flex-shrink: 0;
}
.hot-slide {
  display: flex;
  align-items: center;
  justify-content: space-between;
  cursor: pointer;
  gap: 12px;
}
.hot-slide-body {
  flex: 1;
  min-width: 0;
}
.hot-slide-title {
  font-size: 14px;
  font-weight: 600;
  color: #1d2129;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-bottom: 2px;
}
.hot-slide-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  color: #86909c;
}
.hot-meta-platform {
  color: #5b4cdb;
  font-weight: 500;
}
.hot-meta-sep {
  color: #d1d5db;
}
.hot-meta-heat {
  color: #FF2442;
}
.hot-meta-dim {
  color: #86909c;
}
.hot-slide-badge {
  flex-shrink: 0;
  font-size: 15px;
  padding: 2px 8px;
  border-radius: 999px;
  background: #FFF1F3;
  color: #FF2442;
}
.hot-dots {
  display: flex;
  gap: 4px;
  justify-content: center;
  margin-top: 8px;
}
.hot-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #E5E7EB;
  cursor: pointer;
  transition: all 0.2s;
}
.hot-dot.is-active {
  background: #5b4cdb;
  width: 16px;
  border-radius: 3px;
}
.hot-carousel-empty {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #9CA3AF;
  font-size: 15px;
  justify-content: center;
}
.hot-carousel-empty i {
  width: 16px;
  height: 16px;
}
:root[data-widget-theme="dark"] .hot-carousel,
[data-theme="dark"] .hot-carousel {
  background: #1e1f24;
  border-color: #3a3b40;
}
:root[data-widget-theme="dark"] .hot-slide-title,
[data-theme="dark"] .hot-slide-title {
  color: #e5e6eb;
}
</style>
