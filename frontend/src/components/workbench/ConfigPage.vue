<template>
  <div class="cfg-page">
    <div class="mint-hero mint-glass">
      <div>
        <h1 class="font-cal mint-hero-title">配置管理</h1>
        <p class="mint-hero-sub">管理平台各项参数与模型配置</p>
      </div>
    </div>

    <div class="cfg-cards">
      <!-- DeepSeek LLM 配置 -->
      <div class="mint-wf-card cfg-card">
        <div class="cfg-card-header" @click="cfgDeepseek = !cfgDeepseek">
          <div class="mint-wf-title-row">
            <div class="mint-wf-step"><i data-lucide="cpu" style="width:16px;height:16px;"></i></div>
            <div>
              <div class="mint-wf-title">DeepSeek 模型配置</div>
              <div class="mint-wf-desc">Esther 工厂 & 工作流共用的文本生成模型</div>
            </div>
          </div>
          <svg class="cfg-chevron" :class="{ 'cfg-chevron-open': cfgDeepseek }" xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"></polyline></svg>
        </div>
        <div class="cfg-card-body" v-if="cfgDeepseek">
          <div class="cfg-section">
            <div class="mint-config-label">API Key</div>
            <div class="cfg-key-row">
              <input :type="showDeepseekKey ? 'text' : 'password'" class="mint-input cfg-key-input" v-model="deepseekApiKey" :placeholder="deepseekKeySet ? '已配置（输入可覆盖）' : '输入 DeepSeek API Key...'" />
              <button class="cfg-key-toggle" @click="showDeepseekKey = !showDeepseekKey" type="button">
                <i :data-lucide="showDeepseekKey ? 'eye-off' : 'eye'" style="width:16px;height:16px;"></i>
              </button>
            </div>
            <div class="cfg-key-status" :class="{ 'cfg-key-set': deepseekKeySet }">
              {{ deepseekKeySet ? '✓ 已配置' : '✗ 未配置' }}
            </div>
          </div>
          <div class="cfg-section">
            <div class="mint-config-label">Base URL</div>
            <input type="text" class="mint-input" v-model="deepseekBaseUrl" placeholder="https://api.deepseek.com" />
          </div>
          <div class="cfg-section">
            <div class="mint-config-label">V3 模型（文本生成）</div>
            <input type="text" class="mint-input" v-model="deepseekModelV3" placeholder="如 deepseek-chat" />
            <div class="cfg-options cfg-options-compact">
              <button v-for="m in deepseekV3Models" :key="m" class="cfg-option" :class="{ 'cfg-option-active': deepseekModelV3 === m }" @click.stop="deepseekModelV3 = m" type="button">{{ m }}</button>
            </div>
          </div>
          <div class="cfg-section">
            <div class="mint-config-label">R1 模型（推理）</div>
            <input type="text" class="mint-input" v-model="deepseekModelR1" placeholder="如 deepseek-reasoner" />
            <div class="cfg-options cfg-options-compact">
              <button v-for="m in deepseekR1Models" :key="m" class="cfg-option" :class="{ 'cfg-option-active': deepseekModelR1 === m }" @click.stop="deepseekModelR1 = m" type="button">{{ m }}</button>
            </div>
          </div>
          <div class="mint-wf-footer">
            <button class="mint-btn mint-btn-outline" @click="resetDeepseek">重置</button>
            <button class="mint-btn mint-btn-primary" @click="saveDeepseek"><i data-lucide="save" style="width:16px;height:16px;"></i> 保存配置</button>
          </div>
        </div>
      </div>

      <!-- 阿里云百炼配置 -->
      <div class="mint-wf-card cfg-card">
        <div class="cfg-card-header" @click="cfgDashscope = !cfgDashscope">
          <div class="mint-wf-title-row">
            <div class="mint-wf-step"><i data-lucide="image" style="width:16px;height:16px;"></i></div>
            <div>
              <div class="mint-wf-title">阿里云百炼配置</div>
              <div class="mint-wf-desc">通义千问 VL 视觉理解 & 通义万相文生图</div>
            </div>
          </div>
          <svg class="cfg-chevron" :class="{ 'cfg-chevron-open': cfgDashscope }" xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"></polyline></svg>
        </div>
        <div class="cfg-card-body" v-if="cfgDashscope">
          <div class="cfg-section">
            <div class="mint-config-label">API Key</div>
            <div class="cfg-key-row">
              <input :type="showDashscopeKey ? 'text' : 'password'" class="mint-input cfg-key-input" v-model="dashscopeApiKey" :placeholder="dashscopeKeySet ? '已配置（输入可覆盖）' : '输入阿里云百炼 API Key...'" />
              <button class="cfg-key-toggle" @click="showDashscopeKey = !showDashscopeKey" type="button">
                <i :data-lucide="showDashscopeKey ? 'eye-off' : 'eye'" style="width:16px;height:16px;"></i>
              </button>
            </div>
            <div class="cfg-key-status" :class="{ 'cfg-key-set': dashscopeKeySet }">
              {{ dashscopeKeySet ? '✓ 已配置' : '✗ 未配置' }}
            </div>
          </div>
          <div class="cfg-section">
            <div class="mint-config-label">通义千问 VL 模型</div>
            <input type="text" class="mint-input" v-model="qwenVlModel" placeholder="如 qwen-vl-max" />
            <div class="cfg-options cfg-options-compact">
              <button v-for="m in qwenVlModels" :key="m" class="cfg-option" :class="{ 'cfg-option-active': qwenVlModel === m }" @click.stop="qwenVlModel = m" type="button">{{ m }}</button>
            </div>
          </div>
          <div class="cfg-section">
            <div class="mint-config-label">通义万相文生图模型</div>
            <input type="text" class="mint-input" v-model="wanxModel" placeholder="如 wanx2.1-t2i-turbo" />
            <div class="cfg-options cfg-options-compact">
              <button v-for="m in wanxModels" :key="m" class="cfg-option" :class="{ 'cfg-option-active': wanxModel === m }" @click.stop="wanxModel = m" type="button">{{ m }}</button>
            </div>
          </div>
          <div class="mint-wf-footer">
            <button class="mint-btn mint-btn-outline" @click="resetDashscope">重置</button>
            <button class="mint-btn mint-btn-primary" @click="saveDashscope"><i data-lucide="save" style="width:16px;height:16px;"></i> 保存配置</button>
          </div>
        </div>
      </div>

    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick, onMounted, watch } from 'vue'
import { createIcons, icons } from 'lucide'
import apiClient from '@/api/client'

const cfgDeepseek = ref(true)
const cfgDashscope = ref(false)

const deepseekV3Models = ['deepseek-chat', 'deepseek-v3-0324', 'deepseek-v3']
const deepseekR1Models = ['deepseek-reasoner', 'deepseek-r1-0528', 'deepseek-r1']
const qwenVlModels = ['qwen-vl-max', 'qwen-vl-plus', 'qwen-vl-max-latest']
const wanxModels = ['wanx2.1-t2i-turbo', 'wanx2.1-t2i-plus', 'wan2.2-t2i-flash']

const deepseekApiKey = ref('')
const deepseekKeySet = ref(false)
const showDeepseekKey = ref(false)
const deepseekBaseUrl = ref('https://api.deepseek.com')
const deepseekModelV3 = ref('deepseek-chat')
const deepseekModelR1 = ref('deepseek-reasoner')

const dashscopeApiKey = ref('')
const dashscopeKeySet = ref(false)
const showDashscopeKey = ref(false)
const qwenVlModel = ref('qwen-vl-max')
const wanxModel = ref('wanx2.1-t2i-turbo')

async function loadLLMConfig() {
  try {
    const res = await apiClient.get('/agents/llm-config')
    const data = res?.data ?? res
    if (data) {
      deepseekKeySet.value = data.deepseek_api_key_set ?? false
      deepseekBaseUrl.value = data.deepseek_base_url ?? 'https://api.deepseek.com'
      deepseekModelV3.value = data.deepseek_model_v3 ?? 'deepseek-chat'
      deepseekModelR1.value = data.deepseek_model_r1 ?? 'deepseek-reasoner'
      dashscopeKeySet.value = data.dashscope_api_key_set ?? false
      qwenVlModel.value = data.qwen_vl_model ?? 'qwen-vl-max'
      wanxModel.value = data.wanx_model ?? 'wanx2.1-t2i-turbo'
    }
  } catch (e) {
    // LLM 配置加载失败
  }
}

function resetDeepseek() {
  deepseekApiKey.value = ''
  deepseekBaseUrl.value = 'https://api.deepseek.com'
  deepseekModelV3.value = 'deepseek-chat'
  deepseekModelR1.value = 'deepseek-reasoner'
}

async function saveDeepseek() {
  try {
    await apiClient.put('/agents/llm-config/deepseek', {
      deepseek_api_key: deepseekApiKey.value,
      deepseek_base_url: deepseekBaseUrl.value,
      deepseek_model_v3: deepseekModelV3.value,
      deepseek_model_r1: deepseekModelR1.value,
    })
    if (deepseekApiKey.value) deepseekKeySet.value = true
    alert('DeepSeek 配置已保存')
  } catch (e) {
    console.error('[ConfigPage] DeepSeek 配置保存失败', e)
    alert('保存失败，请检查后端服务')
  }
}

function resetDashscope() {
  dashscopeApiKey.value = ''
  qwenVlModel.value = 'qwen-vl-max'
  wanxModel.value = 'wanx2.1-t2i-turbo'
}

async function saveDashscope() {
  try {
    await apiClient.put('/agents/llm-config/dashscope', {
      dashscope_api_key: dashscopeApiKey.value,
      qwen_vl_model: qwenVlModel.value,
      wanx_model: wanxModel.value,
    })
    if (dashscopeApiKey.value) dashscopeKeySet.value = true
    alert('阿里云百炼配置已保存')
  } catch (e) {
    console.error('[ConfigPage] 阿里云百炼配置保存失败', e)
    alert('保存失败，请检查后端服务')
  }
}

function refreshIcons() {
  nextTick(() => {
    try { createIcons({ icons }) } catch {}
  })
}

watch([cfgDeepseek, cfgDashscope], refreshIcons)
onMounted(() => {
  loadLLMConfig()
  refreshIcons()
})
</script>

<style scoped>
.cfg-key-row {
  display: flex;
  gap: 8px;
  align-items: center;
}

.cfg-key-input {
  flex: 1;
}

.cfg-key-toggle {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border: 1px solid var(--ma-border-default, #E5E7EB);
  border-radius: 8px;
  background: var(--ma-bg-elevated, #FFFFFF);
  cursor: pointer;
  color: var(--ma-text-tertiary, #9CA3AF);
  transition: all 0.15s ease;
}

.cfg-key-toggle:hover {
  border-color: #2B7FD8;
  color: #2B7FD8;
}

.cfg-key-status {
  margin-top: 6px;
  font-size: 12px;
  color: #EF4444;
}

.cfg-key-status.cfg-key-set {
  color: #10B981;
}

.cfg-hint {
  margin-top: 6px;
  font-size: 12px;
  color: var(--ma-text-tertiary, #9CA3AF);
  line-height: 1.4;
}
</style>