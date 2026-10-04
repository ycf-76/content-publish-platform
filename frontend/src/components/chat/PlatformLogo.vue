<template>
  <img :src="svgSrc" :alt="name" class="plogo" />
</template>

<script setup lang="ts">
const props = defineProps<{
  platform: string
  name: string
}>()

const ICON_MAP: Record<string, string> = {
  xiaohongshu: '/icons/xiaohongshu-app.png',
  wechat: '/icons/wechat-app.svg',
  wechat_video: '/icons/wechat-app.svg',
  douyin: '/icons/douyin-app.png',
  kuaishou: '/icons/kuaishou-app.svg',
  bilibili: '/icons/bilibili-app.png',
  zhihu: '/icons/zhihu-app.svg',
}

const svgSrc = ICON_MAP[props.platform] || `/icons/${props.platform}-app.svg`
</script>

<style scoped>
.plogo {
  width: 20px;
  height: 20px;
  border-radius: 4px;
  object-fit: contain;
}
</style>