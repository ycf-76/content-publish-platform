<template>
  <div class="cp-wrap">
    <!-- 加载态 -->
    <div v-if="loading" class="cp-loading">
      <div class="cp-spinner"></div>
      <span>加载画像...</span>
    </div>

    <!-- 错误态 -->
    <div v-else-if="errorMsg" class="cp-error">
      <AlertCircle :size="18" />
      <span>{{ errorMsg }}</span>
      <button @click="loadProfile" class="cp-retry-btn">重试</button>
    </div>

    <!-- 表单 -->
    <div v-else class="cp-form">
      <!-- 主领域（必填） -->
      <div class="cp-form-row">
        <label class="cp-label">
          主领域 <span class="cp-required">*</span>
        </label>
        <select v-model="form.primary_domain" class="cp-select">
          <option v-for="d in domainOptions" :key="d.value" :value="d.value">
            {{ d.label }}
          </option>
        </select>
      </div>

      <!-- 子领域 -->
      <div class="cp-form-row">
        <label class="cp-label">子领域</label>
        <input
          v-model="form.sub_domain"
          class="cp-input"
          placeholder="如：AI 编程、Python 教程"
          maxlength="50"
        />
      </div>

      <!-- 调性 -->
      <div class="cp-form-row">
        <label class="cp-label">内容调性</label>
        <div class="cp-tag-group">
          <button
            v-for="t in toneOptions"
            :key="t.value"
            type="button"
            class="cp-tag-btn"
            :class="{ 'cp-tag-active': form.tone === t.value }"
            @click="form.tone = t.value"
          >
            {{ t.label }}
          </button>
        </div>
      </div>

      <!-- 视觉风格 -->
      <div class="cp-form-row">
        <label class="cp-label">视觉风格</label>
        <div class="cp-tag-group">
          <button
            v-for="v in visualOptions"
            :key="v.value"
            type="button"
            class="cp-tag-btn"
            :class="{ 'cp-tag-active': form.visual_style === v.value }"
            @click="form.visual_style = v.value"
          >
            {{ v.label }}
          </button>
        </div>
      </div>

      <!-- 身份定位 -->
      <div class="cp-section-title">身份与定位</div>
      <div class="cp-form-row">
        <label class="cp-label">身份定位</label>
        <input
          v-model="form.identity"
          class="cp-input"
          placeholder="一句话描述你的核心定位，如：AI编程领域的实战派博主"
          maxlength="200"
        />
      </div>
      <div class="cp-form-row">
        <label class="cp-label">差异化</label>
        <input
          v-model="form.differentiation"
          class="cp-input"
          placeholder="跟同类账号比，你的独特之处"
          maxlength="200"
        />
      </div>
      <div class="cp-form-row">
        <label class="cp-label">内容方向</label>
        <input
          v-model="form.content_direction"
          class="cp-input"
          placeholder="主要做什么类型的内容，如：教程+实战+工具推荐"
          maxlength="200"
        />
      </div>

      <!-- 受众画像 -->
      <div class="cp-section-title">受众画像</div>
      <div class="cp-form-row">
        <label class="cp-label">核心人群</label>
        <input
          v-model="form.target_audience"
          class="cp-input"
          placeholder="年龄段/职业/特征，如：25-35岁互联网从业者"
          maxlength="200"
        />
      </div>
      <div class="cp-form-row">
        <label class="cp-label">受众痛点</label>
        <input
          v-model="form.audience_pain_points"
          class="cp-input"
          placeholder="什么场景下会搜索/刷到你的内容"
          maxlength="200"
        />
      </div>

      <!-- 写作风格 -->
      <div class="cp-section-title">写作风格</div>
      <div class="cp-form-row">
        <label class="cp-label">开头结构</label>
        <div class="cp-tag-group">
          <button
            v-for="o in openingOptions"
            :key="o.value"
            type="button"
            class="cp-tag-btn"
            :class="{ 'cp-tag-active': form.opening_style === o.value }"
            @click="form.opening_style = o.value"
          >
            {{ o.label }}
          </button>
        </div>
      </div>
      <div class="cp-form-row">
        <label class="cp-label">内容节奏</label>
        <div class="cp-tag-group">
          <button
            v-for="r in rhythmOptions"
            :key="r.value"
            type="button"
            class="cp-tag-btn"
            :class="{ 'cp-tag-active': form.content_rhythm === r.value }"
            @click="form.content_rhythm = r.value"
          >
            {{ r.label }}
          </button>
        </div>
      </div>
      <div class="cp-form-row">
        <label class="cp-label">标志元素</label>
        <input
          v-model="form.signature_elements"
          class="cp-input"
          placeholder="口头禅/固定栏目/BGM等辨识度元素"
          maxlength="200"
        />
      </div>

      <!-- 禁忌话题 -->
      <div class="cp-form-row">
        <label class="cp-label">禁忌话题</label>
        <p class="cp-hint">不涉及的话题，回车添加</p>
        <div class="cp-input-tags">
          <span v-for="(t, i) in form.taboo_topics" :key="'tp' + i" class="cp-chip cp-chip-topic">
            {{ t }}
            <button type="button" class="cp-chip-remove" @click="removeItem('taboo_topics', i)">
              <X :size="11" />
            </button>
          </span>
          <input
            v-model="topicInput"
            class="cp-input-tag"
            placeholder="输入后回车"
            @keydown.enter.prevent="addItem('taboo_topics', topicInput); topicInput = ''"
          />
        </div>
      </div>

      <!-- 禁忌用词 -->
      <div class="cp-form-row">
        <label class="cp-label">禁忌用词</label>
        <p class="cp-hint">不使用的词语，回车添加</p>
        <div class="cp-input-tags">
          <span v-for="(w, i) in form.taboo_words" :key="'tw' + i" class="cp-chip cp-chip-word">
            {{ w }}
            <button type="button" class="cp-chip-remove" @click="removeItem('taboo_words', i)">
              <X :size="11" />
            </button>
          </span>
          <input
            v-model="wordInput"
            class="cp-input-tag"
            placeholder="输入后回车"
            @keydown.enter.prevent="addItem('taboo_words', wordInput); wordInput = ''"
          />
        </div>
      </div>

      <!-- 操作按钮 -->
      <div class="cp-actions">
        <button
          @click="handleSave"
          class="cp-save-btn"
          :disabled="!canSave || saving"
        >
          <Check :size="14" />
          <span>{{ saving ? '保存中...' : '保存画像' }}</span>
        </button>
        <button @click="resetForm" class="cp-cancel-btn">重置</button>
      </div>

      <!-- 保存结果提示 -->
      <transition name="cp-fade">
        <div v-if="saveMsg" class="cp-toast" :class="{ 'cp-toast-error': saveError }">
          <Check v-if="!saveError" :size="14" />
          <AlertCircle v-else :size="14" />
          <span>{{ saveMsg }}</span>
        </div>
      </transition>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { Check, X, AlertCircle } from 'lucide-vue-next'
import {
  profileApi,
  type UserProfile,
  type UpdateProfileRequest,
  type PrimaryDomain,
  type CreatorTone,
  type VisualStyle,
} from '@/api/profile'

const loading = ref(true)
const errorMsg = ref('')
const saving = ref(false)
const saveMsg = ref('')
const saveError = ref(false)
const topicInput = ref('')
const wordInput = ref('')

const domainOptions = [
  { value: 'tech' as PrimaryDomain, label: '科技' },
  { value: 'beauty' as PrimaryDomain, label: '美妆' },
  { value: 'food' as PrimaryDomain, label: '美食' },
  { value: 'travel' as PrimaryDomain, label: '旅行' },
  { value: 'education' as PrimaryDomain, label: '教育' },
  { value: 'parenting' as PrimaryDomain, label: '母婴' },
  { value: 'fitness' as PrimaryDomain, label: '健身' },
  { value: 'finance' as PrimaryDomain, label: '财经' },
  { value: 'other' as PrimaryDomain, label: '其他' },
]

const toneOptions = [
  { value: 'professional' as CreatorTone, label: '专业' },
  { value: 'friendly' as CreatorTone, label: '亲和' },
  { value: 'lively' as CreatorTone, label: '活泼' },
  { value: 'serious' as CreatorTone, label: '严肃' },
  { value: 'humorous' as CreatorTone, label: '幽默' },
]

const visualOptions = [
  { value: 'warm' as VisualStyle, label: '暖色调' },
  { value: 'cool' as VisualStyle, label: '冷色调' },
  { value: 'minimal' as VisualStyle, label: '极简' },
  { value: 'rich' as VisualStyle, label: '丰富' },
]

const openingOptions = [
  { value: 'question', label: '提问式' },
  { value: 'conflict', label: '冲突式' },
  { value: 'story', label: '故事式' },
  { value: 'direct', label: '直入主题' },
  { value: 'data', label: '数据开场' },
]

const rhythmOptions = [
  { value: 'short_fast', label: '短平快' },
  { value: 'medium', label: '中等' },
  { value: 'deep_long', label: '深度长内容' },
  { value: 'image_text', label: '图文为主' },
]

const form = ref<UpdateProfileRequest>({
  primary_domain: 'tech',
  sub_domain: null,
  tone: 'professional',
  visual_style: 'warm',
  taboo_topics: [],
  taboo_words: [],
  identity: null,
  differentiation: null,
  content_direction: null,
  target_audience: null,
  audience_pain_points: null,
  opening_style: null,
  content_rhythm: null,
  signature_elements: null,
})

const canSave = computed(() => {
  const d = form.value.primary_domain
  return d !== null && d !== undefined && String(d).trim() !== ''
})

async function loadProfile() {
  loading.value = true
  errorMsg.value = ''
  try {
    const profile = await profileApi.get()
    if (profile) {
      form.value = {
        primary_domain: profile.primary_domain,
        sub_domain: profile.sub_domain,
        tone: profile.tone,
        visual_style: profile.visual_style,
        taboo_topics: [...profile.taboo_topics],
        taboo_words: [...profile.taboo_words],
        identity: profile.identity,
        differentiation: profile.differentiation,
        content_direction: profile.content_direction,
        target_audience: profile.target_audience,
        audience_pain_points: profile.audience_pain_points,
        opening_style: profile.opening_style,
        content_rhythm: profile.content_rhythm,
        signature_elements: profile.signature_elements,
      }
    }
  } catch (e: any) {
    // 404 = 尚未设置画像，不报错
    if (e?.response?.status !== 404) {
      errorMsg.value = e?.message || '加载画像失败'
    }
  } finally {
    loading.value = false
  }
}

function addItem(field: 'taboo_topics' | 'taboo_words', value: string) {
  const v = value.trim()
  if (!v) return
  const arr = form.value[field]
  if (arr) {
    const seen = new Set(arr.map((s: string) => s.toLowerCase()))
    if (!seen.has(v.toLowerCase())) {
      arr.push(v.slice(0, 100))
    }
  }
}

function removeItem(field: 'taboo_topics' | 'taboo_words', index: number) {
  const arr = form.value[field]
  if (arr) arr.splice(index, 1)
}

function resetForm() {
  form.value = {
    primary_domain: 'tech',
    sub_domain: null,
    tone: 'professional',
    visual_style: 'warm',
    taboo_topics: [],
    taboo_words: [],
    identity: null,
    differentiation: null,
    content_direction: null,
    target_audience: null,
    audience_pain_points: null,
    opening_style: null,
    content_rhythm: null,
    signature_elements: null,
  }
  topicInput.value = ''
  wordInput.value = ''
  saveMsg.value = ''
}

let toastTimer: ReturnType<typeof setTimeout> | null = null
function showToast(msg: string, isError = false) {
  saveMsg.value = msg
  saveError.value = isError
  if (toastTimer) clearTimeout(toastTimer)
  toastTimer = setTimeout(() => { saveMsg.value = '' }, 3000)
}

async function handleSave() {
  if (!canSave.value) return
  saving.value = true
  try {
    const payload: UpdateProfileRequest = {
      primary_domain: form.value.primary_domain,
      sub_domain: form.value.sub_domain?.trim() || null,
      tone: form.value.tone,
      visual_style: form.value.visual_style,
      taboo_topics: form.value.taboo_topics || [],
      taboo_words: form.value.taboo_words || [],
      identity: form.value.identity?.trim() || null,
      differentiation: form.value.differentiation?.trim() || null,
      content_direction: form.value.content_direction?.trim() || null,
      target_audience: form.value.target_audience?.trim() || null,
      audience_pain_points: form.value.audience_pain_points?.trim() || null,
      opening_style: form.value.opening_style || null,
      content_rhythm: form.value.content_rhythm || null,
      signature_elements: form.value.signature_elements?.trim() || null,
    }
    await profileApi.update(payload)
    showToast('画像已保存，后续生成将自动应用')
  } catch (e: any) {
    const detail = e?.response?.data?.detail || e?.response?.data?.message
    showToast(detail || '保存失败，请重试', true)
  } finally {
    saving.value = false
  }
}

onMounted(loadProfile)
</script>

<style scoped>
.cp-wrap {
  font-size: 14px;
  color: #374151;
}

/* loading */
.cp-loading {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 40px 0;
  justify-content: center;
  color: #9CA3AF;
}
.cp-spinner {
  width: 20px;
  height: 20px;
  border: 2px solid #E5E7EB;
  border-top-color: #3B6CF6;
  border-radius: 50%;
  animation: cp-spin 0.7s linear infinite;
}
@keyframes cp-spin { to { transform: rotate(360deg); } }

/* error */
.cp-error {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 16px;
  background: rgba(239, 68, 68, 0.06);
  border-radius: 8px;
  color: #EF4444;
}
.cp-retry-btn {
  margin-left: auto;
  padding: 4px 12px;
  border: 1px solid #EF4444;
  background: transparent;
  color: #EF4444;
  border-radius: 6px;
  font-size: 12px;
  cursor: pointer;
}
.cp-retry-btn:hover { background: rgba(239, 68, 68, 0.08); }

/* form */
.cp-form {
  display: flex;
  flex-direction: column;
  gap: 20px;
}
.cp-form-row {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.cp-section-title {
  font-size: 14px;
  font-weight: 600;
  color: #1A1A1A;
  padding-top: 8px;
  border-top: 1px solid #F3F4F6;
  margin-top: 4px;
}
.cp-label {
  font-size: 13px;
  font-weight: 500;
  color: #1A1A1A;
}
.cp-required {
  color: #EF4444;
}
.cp-hint {
  margin: 0;
  font-size: 12px;
  color: #9CA3AF;
}

/* select */
.cp-select {
  height: 36px;
  padding: 0 10px;
  border: 1px solid #E5E7EB;
  border-radius: 8px;
  font-size: 13px;
  color: #1A1A1A;
  background: #FFFFFF;
  cursor: pointer;
  outline: none;
  transition: border-color 0.15s;
}
.cp-select:focus { border-color: #3B6CF6; }

/* input */
.cp-input {
  height: 36px;
  padding: 0 10px;
  border: 1px solid #E5E7EB;
  border-radius: 8px;
  font-size: 13px;
  color: #1A1A1A;
  outline: none;
  transition: border-color 0.15s;
}
.cp-input:focus { border-color: #3B6CF6; }

/* tag group (tone / visual style) */
.cp-tag-group {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.cp-tag-btn {
  padding: 6px 14px;
  border: 1px solid #E5E7EB;
  background: #FFFFFF;
  color: #4B4B4B;
  border-radius: 8px;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.15s;
}
.cp-tag-btn:hover {
  border-color: #3B6CF6;
  color: #3B6CF6;
}
.cp-tag-active {
  border-color: #3B6CF6;
  background: #3B6CF6;
  color: #FFFFFF;
}
.cp-tag-active:hover {
  border-color: #3B6CF6;
  color: #FFFFFF;
}

/* input with chips */
.cp-input-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 6px;
  border: 1px solid #E5E7EB;
  border-radius: 8px;
  background: #FFFFFF;
  min-height: 36px;
  align-items: center;
}
.cp-input-tag {
  flex: 1;
  min-width: 120px;
  border: none;
  outline: none;
  font-size: 13px;
  padding: 4px 6px;
  background: transparent;
}
.cp-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 8px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 500;
}
.cp-chip-topic {
  background: #FEF3C7;
  color: #92400E;
}
.cp-chip-word {
  background: #FEE2E2;
  color: #991B1B;
}
.cp-chip-remove {
  display: flex;
  align-items: center;
  border: none;
  background: transparent;
  color: inherit;
  cursor: pointer;
  padding: 0;
  opacity: 0.6;
}
.cp-chip-remove:hover { opacity: 1; }

/* actions */
.cp-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 4px;
}
.cp-save-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 20px;
  border: none;
  background: #3B6CF6;
  color: #FFFFFF;
  font-size: 13px;
  font-weight: 500;
  border-radius: 8px;
  cursor: pointer;
  transition: opacity 0.15s;
}
.cp-save-btn:hover { opacity: 0.85; }
.cp-save-btn:disabled {
  background: #9CA3AF;
  cursor: not-allowed;
}
.cp-cancel-btn {
  padding: 8px 16px;
  border: 1px solid #E5E7EB;
  background: #FFFFFF;
  color: #6B7280;
  font-size: 13px;
  border-radius: 8px;
  cursor: pointer;
}
.cp-cancel-btn:hover { background: #F3F4F6; }

/* toast */
.cp-toast {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  background: #ECFDF5;
  color: #059669;
  border-radius: 8px;
  font-size: 13px;
}
.cp-toast-error {
  background: #FEF2F2;
  color: #EF4444;
}
.cp-fade-enter-active,
.cp-fade-leave-active {
  transition: opacity 0.2s;
}
.cp-fade-enter-from,
.cp-fade-leave-to {
  opacity: 0;
}
</style>