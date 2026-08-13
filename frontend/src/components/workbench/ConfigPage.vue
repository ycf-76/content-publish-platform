<template>
  <div class="cfg-page">
    <div class="mint-hero mint-glass">
      <div>
        <h1 class="font-cal mint-hero-title">配置管理</h1>
        <p class="mint-hero-sub">管理平台各项参数与模型配置</p>
      </div>
    </div>

    <div class="cfg-cards">
      <!-- 模型配置 -->
      <div class="mint-wf-card cfg-card">
        <div class="cfg-card-header" @click="cfgModel = !cfgModel">
          <div class="mint-wf-title-row">
            <div class="mint-wf-step"><i data-lucide="cpu" style="width:16px;height:16px;"></i></div>
            <div>
              <div class="mint-wf-title">模型配置</div>
              <div class="mint-wf-desc">配置 AI 模型参数与 API 密钥</div>
            </div>
          </div>
          <svg class="cfg-chevron" :class="{ 'cfg-chevron-open': cfgModel }" xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"></polyline></svg>
        </div>
        <div class="cfg-card-body" v-if="cfgModel">
          <div class="cfg-section">
            <div class="mint-config-label">文本生成模型</div>
            <div class="cfg-options">
              <button v-for="m in textModels" :key="m" class="cfg-option" :class="{ 'cfg-option-active': selTextModel === m }" @click.stop="selTextModel = m">{{ m }}</button>
            </div>
          </div>
          <div class="cfg-section">
            <div class="mint-config-label">图片生成模型</div>
            <div class="cfg-options">
              <button v-for="m in imgModels" :key="m" class="cfg-option" :class="{ 'cfg-option-active': selImgModel === m }" @click.stop="selImgModel = m">{{ m }}</button>
            </div>
          </div>
          <div class="cfg-section">
            <div class="mint-config-label">API 密钥</div>
            <input type="password" class="mint-input" placeholder="输入 API 密钥..." value="sk-xxxxxxxxxxxx">
          </div>
          <div class="mint-wf-footer">
            <button class="mint-btn mint-btn-outline">重置</button>
            <button class="mint-btn mint-btn-primary"><i data-lucide="save" style="width:16px;height:16px;"></i> 保存配置</button>
          </div>
        </div>
      </div>

      <!-- 内容风格 -->
      <div class="mint-wf-card cfg-card">
        <div class="cfg-card-header" @click="cfgStyle = !cfgStyle">
          <div class="mint-wf-title-row">
            <div class="mint-wf-step"><i data-lucide="palette" style="width:16px;height:16px;"></i></div>
            <div>
              <div class="mint-wf-title">内容风格</div>
              <div class="mint-wf-desc">设置生成内容的默认风格与语气</div>
            </div>
          </div>
          <svg class="cfg-chevron" :class="{ 'cfg-chevron-open': cfgStyle }" xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"></polyline></svg>
        </div>
        <div class="cfg-card-body" v-if="cfgStyle">
          <div class="cfg-section">
            <div class="mint-config-label">内容语气</div>
            <div class="cfg-options">
              <button v-for="t in tones" :key="t" class="cfg-option" :class="{ 'cfg-option-active': selTone === t }" @click.stop="selTone = t">{{ t }}</button>
            </div>
          </div>
          <div class="cfg-section">
            <div class="mint-config-label">默认标签</div>
            <input type="text" class="mint-input" placeholder="输入默认标签，逗号分隔..." value="穿搭,好物推荐,日常">
          </div>
          <div class="cfg-section">
            <div class="mint-toggle">
              <span class="mint-config-label">自动添加话题标签</span>
              <div class="mint-switch" :class="{ active: autoTag }" @click.stop="autoTag = !autoTag"></div>
            </div>
          </div>
          <div class="mint-wf-footer">
            <button class="mint-btn mint-btn-primary"><i data-lucide="check" style="width:16px;height:16px;"></i> 应用设置</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick, onMounted, watch } from 'vue'
import { createIcons, icons } from 'lucide'

const cfgModel = ref(true)
const cfgStyle = ref(true)

const textModels = ['GPT-4o', 'Claude 3.5 Sonnet', '通义千问 Max', 'DeepSeek V3']
const imgModels = ['DALL-E 3', 'Midjourney', 'Stable Diffusion XL']
const tones = ['亲切活泼', '专业严谨', '文艺清新', '幽默风趣']

const selTextModel = ref('DeepSeek V3')
const selImgModel = ref('DALL-E 3')
const selTone = ref('亲切活泼')
const autoTag = ref(true)

function refreshIcons() {
  nextTick(() => {
    try { createIcons({ icons }) } catch {}
  })
}

watch([cfgModel, cfgStyle], refreshIcons)
onMounted(refreshIcons)
</script>