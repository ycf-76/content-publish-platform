<script setup lang="ts">
import {
  PAGE_TYPE_LABELS,
  DECORATION_TYPE_LABELS,
  type DecorationConfig,
  type DecorationType,
  type TemplateTheme,
} from '@/card-editor/templates'
import {
  ESTHER_PAGE_TYPE_LABELS,
  FULL_PAGE_TYPE_LABELS,
  isEstherTemplate,
  type EstherCardPage,
  type FullPageType,
} from '@/card-editor/esther-templates'
import type { CardDraft } from '@/composables/useCardEditor'

const props = defineProps<{
  selectedPage: EstherCardPage
  currentTemplateId: string
  currentTemplate: TemplateTheme
  effectiveTheme: TemplateTheme
  currentDecoration: DecorationConfig
  customFontSize: number | null
  customBg: string
  customAccent: string
  filteredDecoPresets: Array<DecorationConfig & { name?: string; description?: string }>
  cardDraft?: CardDraft
}>()

const emit = defineEmits<{
  'change-page-type': [id: string, newType: FullPageType]
  'update:customFontSize': [value: number | null]
  'update:customBg': [value: string]
  'update:customAccent': [value: string]
  'update:decorationType': [value: DecorationType]
  'select-decoration': [preset: DecorationConfig & { name?: string; description?: string }]
  'decoration-none': []
  'reset-style': []
  'redistribute': []
  'add-list-item': []
  'delete-list-item': [index: number]
  'fill-copywrite': [pageId: string]
}>()

const isEsther = isEstherTemplate(props.currentTemplateId)
</script>

<template>
  <div class="property-panel">
    <section class="panel-section">
      <h4 class="panel-title">当前页面</h4>
      <div class="form">
        <div class="form-row">
          <label class="label">类型</label>
          <select class="select" :value="selectedPage.type" @change="emit('change-page-type', selectedPage.id, ($event.target as HTMLSelectElement).value as FullPageType)">
            <optgroup label="基础页面">
              <option v-for="(label, key) in PAGE_TYPE_LABELS" :key="key" :value="key">{{ label }}</option>
            </optgroup>
            <optgroup label="Esther 页面">
              <option v-for="(label, key) in ESTHER_PAGE_TYPE_LABELS" :key="key" :value="key">{{ label }}</option>
            </optgroup>
          </select>
        </div>
        <div v-if="cardDraft?.copywrite_context" class="form-row">
          <button class="ai-fill-btn" @click="emit('fill-copywrite', selectedPage.id)" title="用 AI 文案自动填充当前页面空字段">
            ✨ AI 填充
          </button>
        </div>
        <div v-if="!['quote'].includes(selectedPage.type)" class="form-row">
          <label class="label">标题</label>
          <input class="input" v-model="selectedPage.title" />
        </div>
        <div v-if="selectedPage.type === 'cover'" class="form-row">
          <label class="label">副标题</label>
          <input class="input" v-model="selectedPage.subtitle" />
        </div>
        <div v-if="selectedPage.type === 'content' || selectedPage.type === 'quote'" class="form-row">
          <label class="label">{{ selectedPage.type === 'quote' ? '金句' : '正文' }}</label>
          <textarea class="textarea" v-model="selectedPage.content" :rows="selectedPage.type === 'quote' ? 3 : 5"></textarea>
        </div>
        <div v-if="selectedPage.type === 'cover' && isEsther" class="form-row">
          <label class="label">高亮关键词</label>
          <input class="input" v-model="(selectedPage as EstherCardPage).highlight" placeholder="标题中需高亮的关键词" />
        </div>
        <div v-if="selectedPage.type === 'cover' && isEsther" class="form-row">
          <label class="label">分类标签</label>
          <input class="input" v-model="(selectedPage as EstherCardPage).tag" placeholder="如：干货分享" />
        </div>
        <div v-if="selectedPage.type === 'dark_panel'" class="form-row">
          <label class="label">装饰数字</label>
          <input class="input" v-model="(selectedPage as EstherCardPage).decoNumber" placeholder="如 01、02" />
        </div>
        <div v-if="selectedPage.type === 'dark_panel'" class="form-row">
          <label class="label">Emoji</label>
          <input class="input" v-model="(selectedPage as EstherCardPage).emoji" placeholder="如 🚀" />
        </div>
        <div v-if="selectedPage.type === 'list' || selectedPage.type === 'dark_panel'" class="form-row">
          <label class="label">清单项</label>
          <div class="list-editor">
            <div v-for="(item, i) in selectedPage.listItems" :key="i" class="list-edit-item">
              <span class="list-edit-num">{{ i + 1 }}</span>
              <input class="input list-edit-input" v-model="selectedPage.listItems![i]" />
              <button class="icon-btn icon-btn-danger" @click="emit('delete-list-item', i)">×</button>
            </div>
            <button class="add-list-btn" @click="emit('add-list-item')">+ 添加</button>
          </div>
        </div>
        <div v-if="selectedPage.type === 'compare'" class="form-row">
          <label class="label">左侧标题</label>
          <input class="input" v-model="(selectedPage as EstherCardPage).compareLeftTitle" />
        </div>
        <div v-if="selectedPage.type === 'compare'" class="form-row">
          <label class="label">右侧标题</label>
          <input class="input" v-model="(selectedPage as EstherCardPage).compareRightTitle" />
        </div>
        <div v-if="selectedPage.type === 'compare'" class="form-row">
          <label class="label">左侧要点</label>
          <div class="list-editor">
            <div v-for="(item, i) in (selectedPage as EstherCardPage).compareLeftItems" :key="'l'+i" class="list-edit-item">
              <span class="list-edit-num">{{ i + 1 }}</span>
              <input class="input list-edit-input" v-model="(selectedPage as EstherCardPage).compareLeftItems![i]" />
              <button class="icon-btn icon-btn-danger" @click="(selectedPage as EstherCardPage).compareLeftItems?.splice(i, 1)">×</button>
            </div>
            <button class="add-list-btn" @click="((selectedPage as EstherCardPage).compareLeftItems ??= []).push('新要点')">+ 添加</button>
          </div>
        </div>
        <div v-if="selectedPage.type === 'compare'" class="form-row">
          <label class="label">右侧要点</label>
          <div class="list-editor">
            <div v-for="(item, i) in (selectedPage as EstherCardPage).compareRightItems" :key="'r'+i" class="list-edit-item">
              <span class="list-edit-num">{{ i + 1 }}</span>
              <input class="input list-edit-input" v-model="(selectedPage as EstherCardPage).compareRightItems![i]" />
              <button class="icon-btn icon-btn-danger" @click="(selectedPage as EstherCardPage).compareRightItems?.splice(i, 1)">×</button>
            </div>
            <button class="add-list-btn" @click="((selectedPage as EstherCardPage).compareRightItems ??= []).push('新要点')">+ 添加</button>
          </div>
        </div>
        <div v-if="selectedPage.type === 'icon_text'" class="form-row">
          <label class="label">图标文字对</label>
          <div class="list-editor">
            <div v-for="(pair, i) in (selectedPage as EstherCardPage).iconTextPairs" :key="'p'+i" class="list-edit-item">
              <input class="input list-edit-input" style="width:40px" v-model="pair.icon" />
              <input class="input list-edit-input" v-model="pair.text" />
              <button class="icon-btn icon-btn-danger" @click="(selectedPage as EstherCardPage).iconTextPairs?.splice(i, 1)">×</button>
            </div>
            <button class="add-list-btn" @click="((selectedPage as EstherCardPage).iconTextPairs ??= []).push({ icon: '🎯', text: '新项目' })">+ 添加</button>
          </div>
        </div>
        <div v-if="selectedPage.type === 'end_page'" class="form-row">
          <label class="label">装饰符号</label>
          <input class="input" v-model="(selectedPage as EstherCardPage).decoNumber" placeholder='如 " 或 ❞' />
        </div>
        <div v-if="selectedPage.type === 'end_page'" class="form-row">
          <label class="label">CTA 文字</label>
          <input class="input" v-model="(selectedPage as EstherCardPage).ctaText" placeholder="如：关注我，获取更多" />
        </div>
        <div v-if="selectedPage.type === 'steps'" class="form-row">
          <label class="label">装饰数字</label>
          <input class="input" v-model="(selectedPage as EstherCardPage).decoNumber" placeholder="如 01、02" />
        </div>
        <div v-if="selectedPage.type === 'steps'" class="form-row">
          <label class="label">步骤</label>
          <div class="list-editor">
            <div v-for="(step, i) in (selectedPage as EstherCardPage).steps" :key="'s'+i" class="step-edit-item">
              <span class="list-edit-num">{{ i + 1 }}</span>
              <div class="step-edit-fields">
                <input class="input" v-model="step.title" placeholder="步骤标题" />
                <input class="input" v-model="step.desc" placeholder="步骤描述" />
              </div>
              <button class="icon-btn icon-btn-danger" @click="(selectedPage as EstherCardPage).steps?.splice(i, 1)">×</button>
            </div>
            <button class="add-list-btn" @click="((selectedPage as EstherCardPage).steps ??= []).push({ title: '新步骤', desc: '描述' })">+ 添加步骤</button>
          </div>
        </div>
        <div v-if="selectedPage.type === 'code_panel'" class="form-row">
          <label class="label">装饰数字</label>
          <input class="input" v-model="(selectedPage as EstherCardPage).decoNumber" placeholder="如 02" />
        </div>
        <div v-if="selectedPage.type === 'code_panel'" class="form-row">
          <label class="label">代码语言</label>
          <input class="input" v-model="(selectedPage as EstherCardPage).codeLang" placeholder="如 python、javascript" />
        </div>
        <div v-if="selectedPage.type === 'code_panel'" class="form-row">
          <label class="label">代码内容</label>
          <textarea class="textarea" v-model="(selectedPage as EstherCardPage).codeContent" :rows="6" placeholder="粘贴代码"></textarea>
        </div>
        <div v-if="selectedPage.type === 'numbered_cards'" class="form-row">
          <label class="label">装饰数字</label>
          <input class="input" v-model="(selectedPage as EstherCardPage).decoNumber" placeholder="如 03" />
        </div>
        <div v-if="selectedPage.type === 'numbered_cards'" class="form-row">
          <label class="label">编号项</label>
          <div class="list-editor">
            <div v-for="(item, i) in (selectedPage as EstherCardPage).numberedItems" :key="'n'+i" class="step-edit-item">
              <span class="list-edit-num">{{ i + 1 }}</span>
              <div class="step-edit-fields">
                <input class="input" v-model="item.title" placeholder="要点标题" />
                <input class="input" v-model="item.desc" placeholder="要点描述" />
              </div>
              <button class="icon-btn icon-btn-danger" @click="(selectedPage as EstherCardPage).numberedItems?.splice(i, 1)">×</button>
            </div>
            <button class="add-list-btn" @click="((selectedPage as EstherCardPage).numberedItems ??= []).push({ title: '新要点', desc: '简要说明' })">+ 添加要点</button>
          </div>
        </div>
        <div v-if="selectedPage.type === 'newspaper'" class="form-row">
          <label class="label">报头</label>
          <input class="input" v-model="(selectedPage as EstherCardPage).masthead" placeholder="如 THE DAILY BRIEF" />
        </div>
        <div v-if="selectedPage.type === 'newspaper'" class="form-row">
          <label class="label">栏目</label>
          <div class="list-editor">
            <div v-for="(col, i) in (selectedPage as EstherCardPage).newspaperCols" :key="'np'+i" class="step-edit-item">
              <span class="list-edit-num">{{ i + 1 }}</span>
              <div class="step-edit-fields">
                <input class="input" v-model="col.headline" placeholder="栏目标题" />
                <input class="input" v-model="col.body" placeholder="栏目正文" />
              </div>
              <button class="icon-btn icon-btn-danger" @click="(selectedPage as EstherCardPage).newspaperCols?.splice(i, 1)">×</button>
            </div>
            <button class="add-list-btn" @click="((selectedPage as EstherCardPage).newspaperCols ??= []).push({ headline: '新栏目', body: '栏目内容' })">+ 添加栏目</button>
          </div>
        </div>
        <div v-if="selectedPage.type === 'big_quote'" class="form-row">
          <label class="label">金句内容</label>
          <textarea class="textarea" v-model="selectedPage.content" :rows="3" placeholder="一句足够大的话"></textarea>
        </div>
        <div v-if="selectedPage.type === 'big_quote'" class="form-row">
          <label class="label">装饰符号</label>
          <input class="input" v-model="(selectedPage as EstherCardPage).decoNumber" placeholder='如 " 或 ❞' />
        </div>
        <div v-if="selectedPage.type === 'image_page'" class="form-row">
          <label class="label">图片地址</label>
          <input class="input" v-model="(selectedPage as EstherCardPage).imageUrl" placeholder="输入图片 URL 或从图片工作区选择" />
        </div>
        <div v-if="selectedPage.type === 'image_page'" class="form-row">
          <label class="label">图片说明</label>
          <textarea class="textarea" v-model="selectedPage.content" :rows="2" placeholder="图片描述（可选）"></textarea>
        </div>
        <div v-if="selectedPage.type === 'image_page'" class="form-row">
          <label class="label">滤镜</label>
          <select class="select" :value="(selectedPage as EstherCardPage).imageFilter || 'none'" @change="(selectedPage as EstherCardPage).imageFilter = ($event.target as HTMLSelectElement).value === 'none' ? '' : ($event.target as HTMLSelectElement).value">
            <option value="none">无</option>
            <option value="brightness(1.2)">亮度+</option>
            <option value="contrast(1.3)">对比度+</option>
            <option value="blur(2px)">模糊</option>
            <option value="grayscale(1)">灰度</option>
            <option value="sepia(0.3) saturate(1.3)">暖色</option>
          </select>
        </div>
        <div v-if="selectedPage.type === 'qa'" class="form-row">
          <label class="label">问答对</label>
          <div class="list-editor">
            <div v-for="(pair, i) in (selectedPage as EstherCardPage).qaPairs" :key="'qa'+i" class="step-edit-item">
              <span class="list-edit-num">Q{{ i + 1 }}</span>
              <div class="step-edit-fields">
                <input class="input" v-model="pair.q" placeholder="问题" />
                <input class="input" v-model="pair.a" placeholder="回答" />
              </div>
              <button class="icon-btn icon-btn-danger" @click="(selectedPage as EstherCardPage).qaPairs?.splice(i, 1)">×</button>
            </div>
            <button class="add-list-btn" @click="((selectedPage as EstherCardPage).qaPairs ??= []).push({ q: '新问题', a: '回答' })">+ 添加问答</button>
          </div>
        </div>
        <div v-if="selectedPage.type === 'timeline'" class="form-row">
          <label class="label">时间轴</label>
          <div class="list-editor">
            <div v-for="(item, i) in (selectedPage as EstherCardPage).timelineItems" :key="'tl'+i" class="step-edit-item">
              <span class="list-edit-num">{{ i + 1 }}</span>
              <div class="step-edit-fields">
                <input class="input" v-model="item.date" placeholder="日期" />
                <input class="input" v-model="item.event" placeholder="事件" />
              </div>
              <button class="icon-btn icon-btn-danger" @click="(selectedPage as EstherCardPage).timelineItems?.splice(i, 1)">×</button>
            </div>
            <button class="add-list-btn" @click="((selectedPage as EstherCardPage).timelineItems ??= []).push({ date: '2025.01', event: '新事件' })">+ 添加节点</button>
          </div>
        </div>
        <div v-if="selectedPage.type === 'stat_card'" class="form-row">
          <label class="label">数据项</label>
          <div class="list-editor">
            <div v-for="(item, i) in (selectedPage as EstherCardPage).statItems" :key="'st'+i" class="step-edit-item">
              <span class="list-edit-num">{{ i + 1 }}</span>
              <div class="step-edit-fields">
                <input class="input" v-model="item.value" placeholder="数值" />
                <input class="input" v-model="item.label" placeholder="标签" />
                <input class="input" style="width:60px" v-model="item.unit" placeholder="单位" />
              </div>
              <button class="icon-btn icon-btn-danger" @click="(selectedPage as EstherCardPage).statItems?.splice(i, 1)">×</button>
            </div>
            <button class="add-list-btn" @click="((selectedPage as EstherCardPage).statItems ??= []).push({ value: '0', label: '新指标', unit: '' })">+ 添加数据</button>
          </div>
        </div>
        <div v-if="selectedPage.type === 'profile'" class="form-row">
          <label class="label">头像地址</label>
          <input class="input" v-model="(selectedPage as EstherCardPage).avatarUrl" placeholder="头像图片 URL" />
        </div>
        <div v-if="selectedPage.type === 'profile'" class="form-row">
          <label class="label">姓名</label>
          <input class="input" v-model="(selectedPage as EstherCardPage).name" placeholder="作者名称" />
        </div>
        <div v-if="selectedPage.type === 'profile'" class="form-row">
          <label class="label">角色/标签</label>
          <input class="input" v-model="(selectedPage as EstherCardPage).role" placeholder="如：产品经理 / 美食博主" />
        </div>
        <div v-if="selectedPage.type === 'profile'" class="form-row">
          <label class="label">简介</label>
          <textarea class="textarea" v-model="(selectedPage as EstherCardPage).bio" :rows="3" placeholder="一段简短的自我介绍"></textarea>
        </div>
        <div class="form-row">
          <label class="label">背景图</label>
          <input class="input" v-model="(selectedPage as EstherCardPage).backgroundImage" placeholder="背景图 URL（可选，覆盖底色）" />
        </div>
        <div class="form-row">
          <label class="label">页脚</label>
          <input class="input" v-model="selectedPage.footer" />
        </div>
      </div>
    </section>

    <section v-if="cardDraft?.copywrite_context" class="panel-section">
      <h4 class="panel-title">
        文案原文
        <button class="redistribute-btn" @click="emit('redistribute')">重新分配</button>
      </h4>
      <div class="form">
        <div class="form-row">
          <label class="label">标题</label>
          <div class="readonly-text">{{ cardDraft.copywrite_context.title }}</div>
        </div>
        <div class="form-row">
          <label class="label">正文</label>
          <div class="readonly-text readonly-scroll">{{ cardDraft.copywrite_context.content }}</div>
        </div>
        <div v-if="cardDraft.copywrite_context.tags?.length" class="form-row">
          <label class="label">标签</label>
          <div class="readonly-text">{{ cardDraft.copywrite_context.tags.join(' · ') }}</div>
        </div>
      </div>
    </section>

    <section class="panel-section">
      <h4 class="panel-title">
        样式
        <button class="reset-btn" @click="emit('reset-style')">重置</button>
      </h4>
      <div class="form">
        <div class="form-row">
          <label class="label">字号（{{ effectiveTheme.fontSize }}px）</label>
          <input type="range" class="range" min="32" max="72" step="2" :value="customFontSize ?? currentTemplate.fontSize" @input="emit('update:customFontSize', ($event.target as HTMLInputElement).value ? Number(($event.target as HTMLInputElement).value) : null)" />
        </div>
        <div class="form-row">
          <label class="label">背景色</label>
          <div class="color-row">
            <input type="color" class="color" :value="customBg || currentTemplate.bg" @input="emit('update:customBg', ($event.target as HTMLInputElement).value)" />
            <input class="input" :value="customBg" @input="emit('update:customBg', ($event.target as HTMLInputElement).value)" :placeholder="currentTemplate.bg" />
          </div>
        </div>
        <div class="form-row">
          <label class="label">强调色</label>
          <div class="color-row">
            <input type="color" class="color" :value="customAccent || currentTemplate.accent" @input="emit('update:customAccent', ($event.target as HTMLInputElement).value)" />
            <input class="input" :value="customAccent" @input="emit('update:customAccent', ($event.target as HTMLInputElement).value)" :placeholder="currentTemplate.accent" />
          </div>
        </div>
      </div>
    </section>

    <section class="panel-section">
      <h4 class="panel-title">
        装饰
        <button class="reset-btn" @click="emit('decoration-none')">清除</button>
      </h4>
      <div class="form">
        <div class="form-row">
          <label class="label">类型</label>
          <select class="select" :value="currentDecoration.type" @change="emit('update:decorationType', ($event.target as HTMLSelectElement).value as DecorationType)">
            <option v-for="(label, key) in DECORATION_TYPE_LABELS" :key="key" :value="key">{{ label }}</option>
          </select>
        </div>
        <div v-if="currentDecoration.type !== 'none'" class="form-row">
          <label class="label">预设方案</label>
          <div class="deco-presets">
            <button
              v-for="preset in filteredDecoPresets"
              :key="preset.name"
              class="deco-preset-btn"
              :class="{ active: preset.type === currentDecoration.type && preset.color1 === currentDecoration.color1 && preset.color2 === currentDecoration.color2 }"
              @click="emit('select-decoration', preset)"
              :title="preset.description"
            >
              <span class="deco-swatch" :style="{ background: `linear-gradient(135deg, ${preset.color1}, ${preset.color2})` }"></span>
              <span class="deco-preset-name">{{ preset.name }}</span>
            </button>
          </div>
        </div>
        <div v-if="currentDecoration.type !== 'none'" class="form-row">
          <label class="label">强度（{{ Math.round(currentDecoration.opacity * 100) }}%）</label>
          <input type="range" class="range" min="0.05" max="0.8" step="0.05" v-model.number="currentDecoration.opacity" />
        </div>
        <div v-if="currentDecoration.type !== 'none'" class="form-row">
          <label class="label">颜色 1</label>
          <div class="color-row">
            <input type="color" class="color" v-model="currentDecoration.color1" />
            <input class="input" v-model="currentDecoration.color1" />
          </div>
        </div>
        <div v-if="currentDecoration.type !== 'none'" class="form-row">
          <label class="label">颜色 2</label>
          <div class="color-row">
            <input type="color" class="color" v-model="currentDecoration.color2" />
            <input class="input" v-model="currentDecoration.color2" />
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.property-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
  height: 100%;
  overflow-y: auto;
  padding: 12px 0;
}
.panel-section { margin-bottom: 4px; }
.panel-title {
  font-size: 12px; font-weight: 700; color: #e2e8f0; margin: 0 0 10px 0;
  display: flex; align-items: center; justify-content: space-between;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.form { display: flex; flex-direction: column; gap: 10px; }
.form-row { display: flex; flex-direction: column; gap: 4px; }
.label { font-size: 11px; font-weight: 500; color: #94a3b8; }
.input, .select, .textarea {
  padding: 6px 8px; border: 1px solid rgba(255,255,255,0.08); border-radius: 6px;
  font-size: 13px; color: #e2e8f0; background: rgba(255,255,255,0.05); font-family: inherit;
  transition: border-color 0.15s;
}
.input:focus, .select:focus, .textarea:focus { outline: none; border-color: #2563eb; }
.textarea { resize: vertical; line-height: 1.5; }
.color-row { display: flex; gap: 6px; align-items: center; }
.color { width: 32px; height: 30px; padding: 2px; border: none; border-radius: 6px; cursor: pointer; background: rgba(255,255,255,0.05); }
.range { width: 100%; accent-color: #2563eb; }
.reset-btn {
  font-size: 10px; padding: 2px 8px; background: rgba(255,255,255,0.06);
  border: none; border-radius: 4px; color: #94a3b8; cursor: pointer;
  transition: all 0.12s;
}
.reset-btn:hover { color: #93c5fd; background: rgba(37,99,235,0.15); }
.readonly-text {
  font-size: 12px; line-height: 1.6; color: #cbd5e1;
  background: rgba(255,255,255,0.04); border-radius: 4px; padding: 6px 8px;
  word-break: break-all; white-space: pre-wrap;
}
.readonly-scroll { max-height: 120px; overflow-y: auto; }
.redistribute-btn {
  font-size: 10px; color: #60a5fa; background: rgba(37,99,235,0.12);
  border: 1px solid rgba(37,99,235,0.2); border-radius: 4px;
  padding: 2px 8px; cursor: pointer; margin-left: auto;
  transition: all 0.12s;
}
.redistribute-btn:hover { background: rgba(37,99,235,0.2); color: #93c5fd; }
.list-editor { display: flex; flex-direction: column; gap: 4px; }
.list-edit-item { display: flex; align-items: center; gap: 4px; }
.list-edit-num { font-size: 11px; font-weight: 600; color: #64748b; min-width: 16px; }
.list-edit-input { flex: 1; }
.add-list-btn {
  padding: 4px; background: rgba(255,255,255,0.05); border: none;
  border-radius: 5px; color: #64748b; font-size: 12px; cursor: pointer;
  transition: all 0.12s;
}
.add-list-btn:hover { color: #93c5fd; }
.ai-fill-btn {
  width: 100%;
  padding: 8px 12px;
  background: linear-gradient(135deg, #7c3aed, #2563eb);
  border: none;
  border-radius: 6px;
  color: #fff;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
}
.ai-fill-btn:hover { filter: brightness(1.15); transform: translateY(-1px); }
.ai-fill-btn:active { transform: translateY(0); }
.icon-btn {
  width: 20px; height: 20px;
  display: flex; align-items: center; justify-content: center;
  background: transparent; border: none; border-radius: 4px;
  color: #64748b; cursor: pointer; font-size: 12px;
}
.icon-btn:hover:not(:disabled) { background: rgba(255,255,255,0.1); color: #e2e8f0; }
.icon-btn-danger:hover { background: rgba(239,68,68,0.2); color: #f87171; }
.step-edit-item {
  display: flex; align-items: flex-start; gap: 4px; padding: 4px 0;
}
.step-edit-fields { flex: 1; display: flex; flex-direction: column; gap: 4px; }
.deco-presets { display: flex; flex-wrap: wrap; gap: 4px; }
.deco-preset-btn {
  display: flex; align-items: center; gap: 4px;
  padding: 3px 6px; border: none; border-radius: 5px;
  background: rgba(255,255,255,0.05); cursor: pointer;
  font-size: 11px; color: #94a3b8; transition: all 0.12s;
}
.deco-preset-btn:hover { color: #93c5fd; }
.deco-preset-btn.active { background: rgba(37,99,235,0.15); color: #93c5fd; font-weight: 600; }
.deco-swatch { width: 14px; height: 14px; border-radius: 3px; flex-shrink: 0; }
.deco-preset-name { white-space: nowrap; }
</style>