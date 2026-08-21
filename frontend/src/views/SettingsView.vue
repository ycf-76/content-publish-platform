<template>
  <div style="position:fixed;inset:0;z-index:100000;background:rgba(0,0,0,0.25);backdrop-filter:blur(2px);display:flex;align-items:center;justify-content:center;" @click.self="close">
    <div style="width:960px;max-width:92vw;height:680px;max-height:85vh;background:#FFFFFF;border-radius:16px;display:flex;overflow:hidden;box-shadow:0 20px 60px rgba(0,0,0,0.15);">
      <div style="width:220px;flex-shrink:0;background:#F9FAFB;display:flex;flex-direction:column;border-right:1px solid #EDEDED;">
        <div style="display:flex;align-items:center;gap:10px;padding:20px 20px 16px;color:#1A1A1A;font-size:var(--text-body);font-weight:var(--weight-semibold);">
          <span>设置</span>
        </div>
        <nav style="flex:1;padding:0 10px;display:flex;flex-direction:column;gap:2px;">
          <button v-for="sec in sections" :key="sec.key"
            style="display:flex;align-items:center;gap:10px;padding:10px 12px;border:none;background:transparent;color:#4B4B4B;font-size:var(--text-sm);cursor:pointer;border-radius:8px;text-align:left;width:100%;"
            :style="{ background: activeSection === sec.key ? '#F5F5F5' : 'transparent', color: activeSection === sec.key ? '#1A1A1A' : '#4B4B4B', fontWeight: activeSection === sec.key ? 600 : 400 }"
            @click="activeSection = sec.key">
            {{ sec.label }}
          </button>
        </nav>
        <div style="padding:12px 10px 16px;border-top:1px solid #EDEDED;">
          <button @click="close" style="display:flex;align-items:center;gap:8px;padding:8px 12px;border:none;background:transparent;color:#9A9A9A;font-size:var(--text-xs);cursor:pointer;border-radius:8px;width:100%;">
            返回工作台
          </button>
        </div>
      </div>
      <div style="flex:1;display:flex;flex-direction:column;min-width:0;">
        <div style="padding:20px 24px 0;flex-shrink:0;">
          <h2 style="margin:0 0 4px;color:#1A1A1A;font-size:var(--text-h2);font-weight:var(--weight-semibold);">{{ currentTitle }}</h2>
          <p style="margin:0;color:#9A9A9A;font-size:var(--text-sm);">{{ currentDesc }}</p>
        </div>
        <div style="flex:1;padding:16px 24px 24px;overflow-y:auto;min-height:0;">
          <div v-if="childError" style="color:#EF4444;padding:20px;background:rgba(239,68,68,0.08);border-radius:8px;font-size:var(--text-sm);word-break:break-all;">
            {{ childError }}
          </div>
          <div v-else-if="activeSection === 'wechat'" style="color:#374151;">
            <WeChatBotSettings />
          </div>
          <div v-else-if="activeSection === 'plugins'" style="color:#374151;">
            <PluginDetailView
              v-if="selectedPlugin"
              :plugin="selectedPlugin"
              @back="selectedPlugin = null"
            />
            <template v-else>
              <p>插件管理区域（加载中...）</p>
              <PluginManagerInline @select-plugin="selectedPlugin = $event" />
            </template>
          </div>
          <div v-else-if="activeSection === 'skills'" style="color:#374151;">
            <p>Skills 技能区域（加载中...）</p>
            <SkillsManager />
          </div>
          <div v-else-if="activeSection === 'config'" style="color:#374151;">
            <p>模型配置区域（加载中...）</p>
            <ConfigPage />
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onErrorCaptured } from 'vue'
import ConfigPage from '@/components/workbench/ConfigPage.vue'
import PluginManagerInline from '@/components/settings/PluginManagerInline.vue'
import PluginDetailView from '@/components/settings/PluginDetailView.vue'
import SkillsManager from '@/components/settings/SkillsManager.vue'
import WeChatBotSettings from '@/components/settings/WeChatBotSettings.vue'
import type { Plugin } from '@/api/plugins'

const emit = defineEmits<{ close: [] }>()

const activeSection = ref('')
const childError = ref('')
const selectedPlugin = ref<Plugin | null>(null)

onErrorCaptured((err, instance, info) => {
  console.error('[SettingsView] ERROR CAPTURED:', err, info)
  childError.value = String(err)
  return false
})

onMounted(() => {
})

const sections = [
  { key: 'wechat', label: '微信机器人', desc: '连接微信，收发消息' },
  { key: 'plugins', label: '插件管理', desc: '管理和配置您的插件' },
  { key: 'skills', label: 'Skills 技能', desc: '管理 Skill 技能配置' },
  { key: 'config', label: '模型配置', desc: '管理模型配置' },
]

const currentTitle = computed(() => sections.find(s => s.key === activeSection.value)?.label ?? '')
const currentDesc = computed(() => sections.find(s => s.key === activeSection.value)?.desc ?? '')

function close() {
  emit('close')
}
</script>