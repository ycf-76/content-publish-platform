<script setup lang="ts">
/**
 * PhoneFrame —— 可复用手机外框（P2）
 *
 * 把 FinalReviewCard「发布预览」节点的手机外框语言抽成独立组件，
 * 供多处复用：承接卡分镜预览、早期封面预览、终审预览等，
 * 保证「手机预览」在全链路视觉一致，且能提前到创作起点。
 *
 * variant:
 *  - full：完整外框（状态栏 + 刘海 + home 指示条），用于真实预览
 *  - mini：紧凑外框（仅圆角 + 小刘海），用于分镜条里的页面缩略预览
 */
defineProps<{
  variant?: 'full' | 'mini'
}>()
</script>

<template>
  <div class="pf" :class="variant === 'mini' ? 'pf-mini' : 'pf-full'">
    <template v-if="variant === 'mini'">
      <div class="pf-mini-notch"></div>
      <div class="pf-screen pf-mini-screen">
        <slot />
      </div>
    </template>
    <template v-else>
      <div class="pf-statusbar">
        <span class="pf-time">9:41</span>
        <div class="pf-notch"></div>
        <div class="pf-status-icons">
          <svg width="13" height="10" viewBox="0 0 16 12"><rect x="0" y="5" width="3" height="7" rx="1" fill="#1a1a1a"/><rect x="4.5" y="3" width="3" height="9" rx="1" fill="#1a1a1a"/><rect x="9" y="1" width="3" height="11" rx="1" fill="#1a1a1a"/><rect x="13" y="0" width="3" height="12" rx="1" fill="#1a1a1a" opacity="0.3"/></svg>
          <svg width="13" height="10" viewBox="0 0 16 12"><path d="M8 2C5.5 2 3.2 3 1.5 4.7L0 3.2C2.1 1.1 4.9 0 8 0s5.9 1.1 8 3.2L14.5 4.7C12.8 3 10.5 2 8 2z" fill="#1a1a1a"/><path d="M8 5.5c-1.7 0-3.2.7-4.3 1.8L2.2 5.8C3.7 4.3 5.7 3.5 8 3.5s4.3.8 5.8 2.3L12.3 7.3C11.2 6.2 9.7 5.5 8 5.5z" fill="#1a1a1a"/><path d="M8 9c-.8 0-1.6.3-2.1.9L8 12l2.1-2.1C9.6 9.3 8.8 9 8 9z" fill="#1a1a1a"/></svg>
          <svg width="22" height="10" viewBox="0 0 27 13"><rect x="0" y="1" width="23" height="11" rx="3.5" stroke="#1a1a1a" stroke-width="1" fill="none"/><rect x="24" y="4" width="2" height="5" rx="1" fill="#1a1a1a" opacity="0.4"/><rect x="2" y="3" width="17" height="7" rx="1.5" fill="#1a1a1a"/></svg>
        </div>
      </div>
      <div class="pf-screen">
        <slot />
      </div>
      <div class="pf-home-bar"></div>
    </template>
  </div>
</template>

<style scoped>
.pf-full {
  width: 325px;
  background: #1a1a1a;
  border-radius: 44px;
  padding: 3px;
  position: relative;
  border: 2.5px solid #1a1a1a;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06), 0 12px 40px rgba(0, 0, 0, 0.12);
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
}
.pf-full .pf-screen {
  border-radius: 41px;
  overflow: hidden;
  background: #ffffff;
  position: relative;
  height: 656px;
  display: flex;
  flex-direction: column;
}
.pf-statusbar {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  padding: 0 20px;
  background: #ffffff;
  height: 44px;
  position: relative;
}
.pf-time { font-size: 14px; font-weight: 600; color: #1a1a1a; width: 44px; padding-top: 14px; z-index: 1; }
.pf-notch {
  width: 120px;
  height: 26px;
  background: #1a1a1a;
  border-radius: 0 0 16px 16px;
  position: absolute;
  left: 50%;
  transform: translateX(-50%);
  top: 0;
}
.pf-status-icons { display: flex; align-items: center; gap: 4px; width: 72px; justify-content: flex-end; padding-top: 14px; z-index: 1; }
.pf-home-bar {
  width: 120px;
  height: 4px;
  background: #1a1a1a;
  border-radius: 2px;
  margin: 6px auto 6px;
  opacity: 0.18;
}

/* mini：分镜条缩略预览 */
.pf-mini {
  width: 58px;
  height: 82px;
  background: #1a1a1a;
  border-radius: 11px;
  padding: 2px;
  position: relative;
  border: 2px solid #1a1a1a;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
}
.pf-mini-notch {
  width: 22px;
  height: 5px;
  background: #1a1a1a;
  border-radius: 0 0 5px 5px;
  position: absolute;
  left: 50%;
  transform: translateX(-50%);
  top: 0;
  z-index: 2;
}
.pf-mini-screen {
  border-radius: 9px;
  background: #f8fafc;
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: 6px 4px;
  overflow: hidden;
}
</style>
