<template>
  <div class="dsh-chat-layout">
  <div class="dsh-chat" :class="{ 'is-dark': darkTheme, 'is-hero': heroMode }">

    <!-- SVG 滤镜：马克笔背景层手绘笔触效果（仅作用于伪元素背景，不伤文字） -->
    <svg style="position:absolute;width:0;height:0" aria-hidden="true">
      <defs>
        <filter id="dsh-marker-filter">
          <feTurbulence type="turbulence" baseFrequency="0.04" numOctaves="4" result="noise" seed="3" />
          <feDisplacementMap in="SourceGraphic" in2="noise" scale="2" xChannelSelector="R" yChannelSelector="G" />
        </filter>
      </defs>
    </svg>

    <div v-if="activeWork && !heroMode" class="dsh-work-bar">
      <div class="dsh-work-bar-info">
        <FileText :size="13" :stroke-width="1.8" class="dsh-work-bar-icon" />
        <span class="dsh-work-bar-title">{{ activeWork.title || '未命名作品' }}</span>
        <span v-if="activeWork.platform" class="dsh-work-bar-platform">{{ activeWork.platform }}</span>
        <span v-if="activeWork.performanceTier && activeWork.performanceTier !== '-'" class="dsh-work-bar-metrics">{{ activeWork.performanceTier }}</span>
      </div>
      <div class="dsh-work-bar-actions">
        <button class="dsh-work-bar-btn" @click="exitWorkContext" title="解除作品关联">
          <X :size="14" />
        </button>
      </div>
    </div>

    <div v-if="workStore.analysisContext && !heroMode" class="dsh-analysis-bar">
      <div class="dsh-analysis-bar-info">
        <img src="/icons/分析.svg" class="dsh-analysis-bar-icon" />
        <span class="dsh-analysis-bar-label">分析已联动</span>
        <span class="dsh-analysis-bar-detail">{{ workStore.analysisContext.overview?.total || 0 }}篇数据 · 归因{{ ({ low: '低', medium: '中', high: '高' } as Record<string,string>)[workStore.analysisContext.confidence] || workStore.analysisContext.confidence }}置信</span>
      </div>
      <div class="dsh-analysis-bar-actions">
        <button class="dsh-work-bar-btn dsh-analysis-create" @click="handoffOpen = true" title="基于分析开启创作">
          <Sparkles :size="13" />
          开启创作
        </button>
        <button class="dsh-work-bar-btn" @click="ctxStore.unlinkAnalysis()" title="解除联动">
          <X :size="14" />
        </button>
      </div>
    </div>

    <CreationHandoffCard
      v-if="handoffOpen && workStore.analysisContext"
      :analysis="workStore.analysisContext"
      @close="handoffOpen = false"
      @start="onHandoffStart"
    />

    <div v-if="activeFile && !heroMode" class="dsh-file-bar">
      <div class="dsh-file-bar-info">
        <component :is="getFileIconComponent(activeFile.type)" :size="13" :stroke-width="1.6" class="dsh-file-bar-icon" />
        <span class="dsh-file-bar-name">{{ activeFile.name }}</span>
        <span class="dsh-file-bar-size">{{ fileStore.formatFileSize(activeFile.size) }}</span>
      </div>
      <div class="dsh-file-bar-actions">
        <button class="dsh-work-bar-btn" @click="fileStore.setActiveFile(null)" title="移除文件">
          <X :size="14" />
        </button>
      </div>
    </div>

    <!-- 侧边栏开关浮动按钮 -->
    <button
      v-if="!ctxStore.sidebarVisible"
      class="dsh-sidebar-toggle"
      @click="toggleWorkDetail"
      title="打开工作台面板"
    >
      <PanelRight :size="18" :stroke-width="1.8" />
    </button>

    <!-- 滚动主体 -->
    <div
      class="dsh-scroll-body"
      :class="{ 'dsh-scroll-hidden': heroMode }"
      ref="scrollBodyRef"
      @scroll="onScroll"
    >
      <div v-if="!heroMode" class="dsh-column">
        <!--
          Turn 状态指示行 — 基于 Codex submission_loop 生命周期
          Turn: idle → thinking → planning → executing → responding → done
          Chat 模式下只显示轻量提示，Codex 模式下显示详细信息
        -->
        <div v-if="isStreaming" class="dsh-turn-status">
          <span class="dsh-turn-status-shimmer-text">
            <template v-if="isChatMode">
              {{ currentStatusIndicator.header || (streamingThinking ? '思考中…' : streamingHasContent ? '生成回复中…' : '思考中…') }}
            </template>
            <template v-else>
              <template v-if="!streamingThinking && !streamingHasContent">Thinking…</template>
              <template v-else-if="streamingThinking">{{ currentStatusIndicator.header || 'Reasoning…' }}</template>
              <template v-else>Writing…</template>
            </template>
          </span>
          <span class="dsh-turn-status-clock" v-if="streamingClock">{{ streamingClock }}s</span>
          <!-- Governance status indicators -->
          <span v-if="isCodexMode && streamingMsg?.agentMeta?.governance?.retrying" class="dsh-governance-badge dsh-governance-retry">
            Retrying ({{ streamingMsg.agentMeta.governance.retryCount }}x)
          </span>
          <span v-if="isCodexMode && streamingMsg?.agentMeta?.governance?.compacted" class="dsh-governance-badge dsh-governance-compact">
            Context compressed
          </span>
          <span v-if="isCodexMode && streamingMsg?.agentMeta?.governance?.budgetWarning" class="dsh-governance-badge dsh-governance-budget">
            Budget low
          </span>
          <span v-if="isCodexMode && streamingMsg?.agentMeta?.collab?.activeCount" class="dsh-governance-badge dsh-collab-badge">
            {{ streamingMsg.agentMeta.collab.activeCount }} agent{{ streamingMsg.agentMeta.collab.activeCount > 1 ? 's' : '' }}
          </span>
          <span v-if="isCodexMode" class="dsh-turn-status-hint">esc to interrupt</span>
        </div>

        <div
          v-for="(msg, idx) in currentMessages"
          :key="idx"
          class="dsh-flow-item"
          :data-user-idx="msg.role === 'user' ? minimapUserIndices.indexOf(idx) : undefined"
        >
          <!-- ═══ UserCell ═══ -->
          <UserMessageCell v-if="msg.role === 'user'" :msg="msg" />

          <!-- ═══ AssistantCell ═══ -->
          <AssistantMessageCell v-else-if="msg.role === 'assistant'" :msg="msg" :idx="idx" :sse-session-id="sse.activeSessionId.value || ''" />
        </div>
      </div>


      <!-- 回到底部浮动钮 -->
      <div v-if="showToBottom && !heroMode" class="dsh-to-bottom-slot">
        <button class="dsh-to-bottom" @click="scrollToBottom(true)" title="回到底部">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>
        </button>
      </div>
    </div>

    <!-- Minimap 锚点导航栏 -->
    <div
      v-if="minimapDots.length > 1 && !heroMode"
      class="dsh-minimap"
    >
      <button
        v-for="(dot, di) in minimapDots"
        :key="di"
        class="dsh-minimap-dot"
        :class="{ 'dsh-minimap-active': di === minimapActiveIndex }"
        :title="dot.preview"
        @click="minimapScrollTo(di)"
      ></button>
    </div>

    <!-- HERO 区 -->
    <div v-if="heroMode" class="dsh-hero-zone" aria-hidden="false">
      <div class="dsh-hero-stack">
        <div class="dsh-hero-brand">
          <div class="dsh-hero-logo-wrap">
            <img src="/icons/logo2.svg" alt="Pulse Studio" class="dsh-hero-logo-crab" />
            <div class="dsh-hero-logo-shimmer"></div>
          </div>
          <h2 class="dsh-hero-title">{{ activeWork ? activeWork.title : '为你开启智能创作之旅' }}</h2>
          <span class="dsh-hero-badge">测试版</span>
        </div>
        <div class="dsh-hero-workspace-row">
          <div class="dsh-hero-ws-wrap">
            <button class="dsh-hero-chip" type="button" @click="toggleHeroWorkspaceList">
              <span>{{ workspaceStore.activeWorkspace ? workspaceStore.activeWorkspace.name : '选择一个工作区开始' }}</span>
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>
            </button>
            <Transition name="dsh-slide-up">
              <div v-if="showHeroWorkspaceList" class="dsh-hero-ws-dropdown" @click.stop>
                <div class="dsh-hero-ws-dropdown-header">
                  <span class="dsh-hero-ws-dropdown-title">侧边栏工作区</span>
                </div>
                <div class="dsh-hero-ws-dropdown-list">
                  <button
                    v-for="ws in workspaceStore.workspaces"
                    :key="ws.id"
                    class="dsh-hero-ws-dropdown-item"
                    :class="{ 'dsh-hero-ws-dropdown-selected': ws.id === workspaceStore.activeWorkspaceId }"
                    @click="onHeroWorkspaceSelect(ws.id)"
                  >
                    <FolderOpen :size="14" :stroke-width="2" />
                    <div class="dsh-hero-ws-item-info">
                      <span class="dsh-hero-ws-item-name">{{ ws.name }}</span>
                      <span class="dsh-hero-ws-item-path">{{ ws.local_path }}</span>
                    </div>
                    <span v-if="ws.id === workspaceStore.activeWorkspaceId" class="dsh-hero-ws-item-check">
                      <Check :size="12" />
                    </span>
                  </button>
                  <div v-if="workspaceStore.workspaces.length === 0" class="dsh-hero-ws-dropdown-empty">
                    暂无工作区，请先在侧边栏导入文件夹
                  </div>
                </div>
              </div>
            </Transition>
          </div>
          <button class="dsh-hero-chip" type="button">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
            <span>标准模式</span>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>
          </button>
        </div>
      </div>
    </div>

    <!-- 输入卡 -->
    <div class="dsh-composer-seat" :class="{ 'dsh-composer-hero': heroMode }">
      <svg v-if="heroMode" class="dsh-hero-glow" viewBox="0 0 900 400" fill="none" aria-hidden="true">
        <defs>
          <filter id="dsh-hero-glow-blur" x="0" y="0" width="900" height="400" filterUnits="userSpaceOnUse" color-interpolation-filters="sRGB">
            <feFlood flood-opacity="0" result="BackgroundImageFix" />
            <feBlend mode="normal" in="SourceGraphic" in2="BackgroundImageFix" result="shape" />
            <feGaussianBlur stdDeviation="40" result="effect1_foregroundBlur" />
          </filter>
        </defs>
        <g filter="url(#dsh-hero-glow-blur)">
          <ellipse cx="450" cy="200" rx="360" ry="120" fill="#7C3AED" fill-opacity="0.18" />
        </g>
      </svg>
      <div class="dsh-composer-card">
        <!-- 已选智能体标签行 -->
        <div v-if="selectedAgentId" class="dsh-agent-tag-row">
          <span class="dsh-agent-tag">
            <img src="/icons/智能体.svg" class="dsh-agent-tag-icon" />
            <span class="dsh-agent-tag-name">{{ selectedAgentLabel }}</span>
            <button class="dsh-agent-tag-close" @click="clearSelectedAgent" title="取消选择">
              <X :size="10" />
            </button>
          </span>
        </div>
        <div class="dsh-at-picker-wrap">
          <AtContentPicker
            :visible="showAtContentPicker"
            :agents="availableAgents"
            @select="onAtContentSelect"
            @close="showAtContentPicker = false"
          />
        </div>
        <textarea
          ref="inputRef"
          v-model="inputText"
          class="dsh-input"
          :disabled="isStreaming"
          :placeholder="isStreaming ? '等待回复中…' : (selectedAgentId ? `向 ${selectedAgentLabel} 发送消息…` : '给 Pulse Studio 发送消息（@ 智能体 / 内容 / 技能）')"
          rows="2"
          @keydown="onKeyDown"
          @input="onUserInput"
          @focus="onUserInput"
        ></textarea>
        <div class="dsh-composer-row">
          <div class="dsh-tools">
          <div class="dsh-plus-wrap">
            <button class="dsh-add" :class="{ 'dsh-add-active': highlightEnabled }" :disabled="isStreaming" @click="toggleHighlight" title="划重点">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>
              </button>
            </div>
            <!-- 绑定文件夹按钮 -->
            <div class="dsh-ws-pick-wrap">
              <button class="dsh-ws-pick-btn" :class="{ 'dsh-ws-pick-active': workspaceStore.activeWorkspace }" :disabled="workspaceStore.binding" @click="workspaceStore.workspaces.length > 0 ? toggleWorkspaceList() : onPickFolder()" title="绑定本地文件夹（智能体可直接操控）">
                <FolderOpen :size="14" :stroke-width="2" />
              </button>
              <!-- 已绑定工作区下拉列表 -->
              <Transition name="dsh-slide-up">
                <div v-if="showWorkspaceList" class="dsh-ws-dropdown" @click.stop>
                  <div class="dsh-ws-dropdown-header">
                    <span class="dsh-ws-dropdown-title">已绑定的工作区</span>
                    <button class="dsh-ws-dropdown-add" @click="onPickFolder" :disabled="workspaceStore.binding">
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
                      绑定新文件夹
                    </button>
                  </div>
                  <div class="dsh-ws-dropdown-list">
                    <button
                      v-for="ws in workspaceStore.workspaces"
                      :key="ws.id"
                      class="dsh-ws-dropdown-item"
                      :class="{ 'dsh-ws-dropdown-selected': ws.id === workspaceStore.activeWorkspaceId }"
                      @click="switchToFolder('ws-' + ws.id); showWorkspaceList = false"
                    >
                      <FolderOpen :size="14" :stroke-width="2" />
                      <div class="dsh-ws-item-info">
                        <span class="dsh-ws-item-name">{{ ws.name }}</span>
                        <span class="dsh-ws-item-path">{{ ws.local_path }}</span>
                      </div>
                      <span v-if="ws.id === workspaceStore.activeWorkspaceId" class="dsh-ws-item-check">
                        <Check :size="12" />
                      </span>
                      <button class="dsh-ws-item-unbind" @click.stop="workspaceStore.unbind(ws.id)" title="解绑">
                        <X :size="10" />
                      </button>
                    </button>
                    <div v-if="workspaceStore.workspaces.length === 0" class="dsh-ws-dropdown-empty">
                      尚未绑定任何文件夹
                    </div>
                  </div>
                </div>
              </Transition>
            </div>
            <!-- 智能体召唤按钮 -->
            <div class="dsh-agent-pick-wrap">
              <button class="dsh-agent-pick-btn" :class="{ 'dsh-agent-pick-active': showAgentPicker }" @click="toggleAgentPicker" title="选择智能体（快捷键 @）">
                <img src="/icons/智能体.svg" class="dsh-agent-btn-icon" />
                <ChevronDown :size="10" />
              </button>
              <!-- 智能体选择下拉面板 -->
              <Transition name="dsh-slide-up">
                <div v-if="showAgentPicker" class="dsh-agent-dropdown" @click.stop>
                  <div class="dsh-agent-dropdown-header">
                    <input
                      v-model="agentPickerFilter"
                      class="dsh-agent-search"
                      placeholder="搜索智能体…"
                      @keydown.escape.stop="closeAgentPicker"
                      @keydown.enter.prevent="() => { const f = filteredAgents[0]; if (f) selectAgent(f) }"
                      ref="agentSearchRef"
                    />
                  </div>
                  <div class="dsh-agent-dropdown-list">
                    <button
                      v-for="a in filteredAgents"
                      :key="a.agent_id"
                      class="dsh-agent-dropdown-item"
                      :class="{ 'dsh-agent-dropdown-selected': a.agent_id === selectedAgentId }"
                      @click="selectAgent(a)"
                    >
                      <img src="/icons/智能体.svg" class="dsh-agent-item-svg" />
                      <div class="dsh-agent-item-info">
                        <span class="dsh-agent-item-role">{{ a.role || a.agent_id }}</span>
                        <span class="dsh-agent-item-id">{{ a.agent_id }}</span>
                      </div>
                      <span v-if="a.agent_id === selectedAgentId" class="dsh-agent-item-check">
                        <Check :size="12" />
                      </span>
                    </button>
                    <div v-if="filteredAgents.length === 0" class="dsh-agent-dropdown-empty">
                      没有匹配的智能体
                    </div>
                  </div>
                  <div class="dsh-agent-dropdown-footer">
                    <span class="dsh-agent-dropdown-hint">输入 @ 快速召唤</span>
                  </div>
                </div>
              </Transition>
            </div>
            <!-- 技能召唤按钮 -->
            <div class="dsh-skill-pick-wrap">
              <button class="dsh-skill-pick-btn" :class="{ 'dsh-skill-pick-active': showSkillPicker }" @click="toggleSkillPicker" title="选择技能（快捷键 /）">
                <span class="dsh-skill-pick-slash">/</span>
                <ChevronDown :size="10" />
              </button>
              <!-- 技能选择下拉面板 -->
              <Transition name="dsh-slide-up">
                <div v-if="showSkillPicker" class="dsh-skill-dropdown" @click.stop>
                  <div class="dsh-skill-dropdown-header">
                    <input
                      v-model="skillPickerFilter"
                      class="dsh-skill-search"
                      placeholder="搜索技能…"
                      @keydown.escape.stop="closeSkillPicker"
                      @keydown.enter.prevent="() => { const f = filteredSkills[0]; if (f) insertSkillToInput(f) }"
                      ref="skillSearchRef"
                    />
                  </div>
                  <div class="dsh-skill-dropdown-list">
                    <button
                      v-for="s in filteredSkills"
                      :key="s.node_type + '.' + s.name"
                      class="dsh-skill-dropdown-item"
                      @click="insertSkillToInput(s)"
                    >
                      <span class="dsh-skill-item-slash">/</span>
                      <div class="dsh-skill-item-info">
                        <span class="dsh-skill-item-name">{{ s.display_name }}</span>
                        <span class="dsh-skill-item-desc">{{ s.description }}</span>
                      </div>
                      <span class="dsh-skill-item-tag">{{ s.node_type }}</span>
                    </button>
                    <div v-if="filteredSkills.length === 0" class="dsh-skill-dropdown-empty">
                      没有匹配的技能
                    </div>
                  </div>
                  <div class="dsh-skill-dropdown-footer">
                    <span class="dsh-skill-dropdown-hint">输入 / 快速召唤 · 选中后插入到输入框</span>
                  </div>
                </div>
              </Transition>
            </div>
            <!-- 创作方向选择按钮 -->
            <div class="dsh-creation-pick-wrap">
              <button class="dsh-creation-pick-btn" :class="{ 'dsh-creation-pick-active': showCreationPicker }" @click="toggleCreationPicker" title="选择创作方向">
                <Sparkles :size="14" />
                <ChevronDown :size="10" />
              </button>
              <Transition name="dsh-slide-up">
                <div v-if="showCreationPicker" class="dsh-creation-dropdown" @click.stop>
                  <div class="dsh-creation-dropdown-header">
                    <span class="dsh-creation-dropdown-title">选择创作方向</span>
                  </div>
                  <div class="dsh-creation-dropdown-list">
                    <button
                      v-for="ct in creationTypeOptions"
                      :key="ct.key"
                      class="dsh-creation-dropdown-item"
                      :class="{ 'dsh-creation-dropdown-selected': workStore.activeCreationType === ct.key }"
                      @click="onSelectCreationType(ct.key)"
                    >
                      <component :is="ct.icon" :size="16" />
                      <div class="dsh-creation-item-info">
                        <span class="dsh-creation-item-name">{{ ct.label }}</span>
                        <span class="dsh-creation-item-desc">{{ ct.desc }}</span>
                      </div>
                    </button>
                  </div>
                </div>
              </Transition>
            </div>
            <!-- 自动放行切换按钮 -->
            <div class="dsh-auto-approve-wrap">
              <button
                class="dsh-auto-approve-btn"
                :class="{ 'dsh-auto-approve-on': autoApproveEnabled }"
                @click="toggleAutoApprove"
                :title="autoApproveEnabled ? '工具调用自动放行中，点击切换为需要确认' : '工具调用需要确认，点击切换为自动放行'"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
                <span class="dsh-auto-approve-label">{{ autoApproveEnabled ? '自动放行' : '需确认' }}</span>
              </button>
            </div>
          </div>
          <div class="dsh-trailing">
            <div class="dsh-model-pick-wrap">
              <button class="dsh-model-pill" :class="{ 'dsh-model-pick-active': showModelPicker }" @click="toggleModelPicker" :title="(currentModelMeta?.name || currentModel) + ' · ' + (currentModelMeta?.providerName || '')">
                <span class="dsh-model-pill-icon" v-html="currentModelMeta?.icon || ''" />
                <span class="dsh-model-pill-name">{{ currentModelMeta?.name || currentModel }}</span>
                <ChevronDown :size="10" />
              </button>
              <Transition name="dsh-slide-up">
                <div v-if="showModelPicker" class="dsh-model-dropdown" @click.stop>
                  <button
                    v-for="m in modelOptions"
                    :key="m.id"
                    class="dsh-model-dropdown-item"
                    :class="{ 'dsh-model-dropdown-selected': m.id === currentModel }"
                    @click="selectModel(m.id)"
                  >
                    <Check v-if="m.id === currentModel" :size="12" class="dsh-model-check" />
                    <span v-else class="dsh-model-check-placeholder" />
                    <span class="dsh-model-dropdown-icon" v-html="m.icon" />
                    <span class="dsh-model-dropdown-text">
                      <span class="dsh-model-dropdown-name">
                        {{ m.name }}
                        <span class="dsh-model-dropdown-provider">{{ m.providerName }}</span>
                      </span>
                      <span class="dsh-model-dropdown-desc">{{ m.description }}</span>
                    </span>
                  </button>
                </div>
              </Transition>
            </div>
            <button v-if="!isStreaming" class="dsh-primary" :disabled="!inputText.trim()" @click="sendMessage" title="发送">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>
            </button>
            <button v-else class="dsh-stop" @click="stopStreaming" title="停止生成">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="6" y="6" width="12" height="12" rx="2"/></svg>
            </button>
          </div>
        </div>
      </div>

      <div class="dsh-composer-footer" v-if="!heroMode && lastStats">
        <span class="dsh-stats-line">
          {{ lastStats.turns }} 轮 · {{ lastStats.tokens }} tokens · {{ lastStats.latency }}ms
        </span>
      </div>
    </div>

    <CrabCompanion
      :show="!heroMode && crabVisible && pluginStore.isEnabled(CRAB_PLUGIN_ID)"
      :input-rect="crabInputRect"
    />
    <CatCompanion
      :show="!heroMode && crabVisible && pluginStore.isEnabled(CAT_PLUGIN_ID)"
      :input-rect="crabInputRect"
    />
    <SpongeBobCompanion
      :show="!heroMode && crabVisible && pluginStore.isEnabled(SPONGEBOB_PLUGIN_ID)"
      :input-rect="crabInputRect"
    />

    <ConfirmDialog
      :visible="dangerDialog.visible"
      :title="dangerDialog.title"
      :message="dangerDialog.message"
      confirm-text="确定重置"
      cancel-text="等待恢复"
      danger
      @confirm="onDangerConfirm"
      @cancel="onDangerCancel"
    />

  </div>

  <!-- 右侧上下文侧边栏 -->
  <div
    class="dsh-ctx-slide"
    :class="{ 'dsh-ctx-slide-open': ctxStore.sidebarVisible }"
  >
    <div
      class="dsh-ctx-resize-bar"
      title="拖拽调整面板宽度 · 双击恢复默认"
      @mousedown="startCtxResize"
      @dblclick.prevent="resetCtxWidth"
    ></div>
    <ContextSidebar
      ref="contextSidebarRef"
      :class="{ 'is-dark': darkTheme }"
      @chat-action="onWorkChatAction"
    />
  </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, nextTick, onMounted, watch, onUnmounted, defineAsyncComponent, provide } from 'vue'

import { useAuthStore } from '@/stores/auth'
import { usePluginStore } from '@/stores/plugin'
import { useWorkStore } from '@/stores/work'
import { useFileStore } from '@/stores/files'
import { useWorkspaceStore } from '@/stores/workspace'
import { useChatContextStore } from '@/stores/chatContext'
import AtContentPicker from './AtContentPicker.vue'

import ConfirmDialog from '@/components/common/ConfirmDialog.vue'
import { renderMarkdown, renderThinkingText } from './markdown-renderer'
import type { ChatMessage, Conversation, ChatStats, AgentMeta, TurnPhase, StatusIndicator, DisplayItem } from './cell-types'
import { provideChatRenderContext } from './chat-context'
import UserMessageCell from './UserMessageCell.vue'
import AssistantMessageCell from './AssistantMessageCell.vue'
import { getThinkingSummary, getThinkingPreview, getThinkingLiveLines, getChatStatusText, getPlanPreviewText, getToolDisplayLabel, getNodeDisplayLabel, sanitizeContent } from './cell-types'

const props = defineProps<{
  modelSettings?: Record<string, any>
}>()

function extractFirstBold(text: string): string {
  if (!text) return ''
  const match = text.match(/\*\*(.+?)\*\*/)
  if (match) return match[1]
  const lines = text.split('\n').map(l => l.trim()).filter(Boolean)
  if (lines.length > 0) {
    const last = lines[lines.length - 1]
    const cleaned = last.replace(/^\[(decision|progress|done|error|start|hint|circuit|skipped|rollback)\]\s*/, '').replace(/^\[\d+\]\s*/, '')
    return cleaned.length > 40 ? cleaned.slice(0, 37) + '…' : cleaned
  }
  return ''
}

function extractThinkingHeader(text: string): string {
  if (!text) return '思考中'
  const boldHeader = extractFirstBold(text)
  if (boldHeader) return boldHeader
  const lines = text.split('\n').map(l => l.trim()).filter(Boolean)
  const decisions = lines.filter(l => l.startsWith('[decision]'))
  if (decisions.length > 0) {
    const last = decisions[decisions.length - 1]
    const cleaned = last.replace(/^\[decision\]\s*/, '').replace(/^\[\d+\]\s*/, '')
    const boldMatch = cleaned.match(/\*\*(.+?)\*\*/)
    if (boldMatch) return boldMatch[1]
    return cleaned.length > 60 ? cleaned.slice(0, 57) + '…' : cleaned
  }
  const progressLines = lines.filter(l => l.startsWith('[progress]') || l.startsWith('[done]'))
  if (progressLines.length > 0) {
    const last = progressLines[progressLines.length - 1]
    return last.replace(/^\[(progress|done)\]\s*/, '')
  }
  return '思考中'
}

function getThinkingStepCount(text: string): string {
  if (!text) return ''
  const steps = text.split('\n').filter(l => l.trim().startsWith('[decision]')).length
  if (steps <= 1) return ''
  return `(${steps}步)`
}

function isThinkingExpanded(msg: any): boolean {
  return !!msg._thinkingExpanded
}

function toggleThinkingExpand(msg: any) {
  msg._thinkingExpanded = !msg._thinkingExpanded
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(1)}s`
}
import { formatAgentOutput, AGENT_NODE_LABELS } from './agent-output-formatter'
import { useChatStream } from './composables/useChatStream'
import { useChatExpandable } from './composables/useChatExpandable'
import { useChatPickers } from './composables/useChatPickers'
import { useChatSSE, _ingestContentDelta } from './composables/useChatSSE'
import { useChatActions } from './composables/useChatActions'
import { useChatInteractions } from './composables/useChatInteractions'
import { useNotificationSSE } from './composables/useNotificationSSE'
import { useChatWork } from './composables/useChatWork'
import { toTagList, isLastAssistant, getResultLineCount, renderDiff, escapeHtml } from './chat-helpers'
import { useChatSend } from './composables/useChatSend'
import { useChatInit } from './composables/useChatInit'
import { useChatAgent } from './composables/useChatAgent'

const emit = defineEmits<{
  'open-image-workspace': [draft?: any]
  'start-cover-workflow': [topic: string]
  'draft-panel-update': [data: any]
}>()
import { useChatHistory } from '@/composables/useChatHistory'
import { X, BarChart3, Image as ImageIcon, File as FileIcon, FolderOpen, Music, Video, FileText, Code, FileSpreadsheet, ChevronDown, Check, Rocket, Sparkles, PanelRight, Scissors, Mic, Radio } from 'lucide-vue-next'
import { agentsApi, type AgentSummary } from '@/api/agents'
import { workflowApi } from '@/api/workflow'
import { authFetch, tryRefreshToken } from '@/api/client'
import * as chatSessionsApi from '@/api/chatSessions'

import { normalizeCardDraft, pickCoverUrl, pickImages } from '@/composables/cardDraft'
import CreationHandoffCard from './CreationHandoffCard.vue'
import ChatConfirmCard from './ChatConfirmCard.vue'

// P2：分析到创作的沉浸式承接卡开关
const handoffOpen = ref(false)

function onHandoffStart(payload: {
  direction: string
  proposedStructure: string[]
  analysis: Record<string, any> | null
}) {
  const planLabel =
    payload.direction === 'reuse' ? '沿用结构' : payload.direction === 'remix' ? '改造结构' : '全新表达'
  const structureText = payload.proposedStructure.join(' → ')
  const best = payload.analysis?.writing_prescription?.best_patterns?.[0]?.name
  const avoid = payload.analysis?.writing_prescription?.avoid_patterns?.[0]?.name
  const parts = [
    `基于刚才的作品分析，帮我创作一篇新图文。`,
    `创作方向：${planLabel}。`,
    `建议分镜结构（供参考，生成时请过质量门禁细化）：${structureText}。`,
  ]
  if (best) parts.push(`请延续已验证模式「${best}」。`)
  if (avoid) parts.push(`请规避「${avoid}」。`)
  parts.push(`分析上下文已自动带入，直接产出 card_draft 即可。`)
  inputText.value = parts.join('\n')
  handoffOpen.value = false
  sendMessage()
}

const CrabCompanion = defineAsyncComponent(() => import('./CrabCompanion.vue'))
const CatCompanion = defineAsyncComponent(() => import('./CatCompanion.vue'))
const SpongeBobCompanion = defineAsyncComponent(() => import('./SpongeBobCompanion.vue'))
const RecoveryStatusCard = defineAsyncComponent(() => import('./RecoveryStatusCard.vue'))
const RecoveryDecisionCard = defineAsyncComponent(() => import('./RecoveryDecisionCard.vue'))
const WorkDetailPanel = defineAsyncComponent(() => import('./WorkDetailPanel.vue'))
const ContextSidebar = defineAsyncComponent(() => import('./ContextSidebar.vue'))
const AgentProgressCard = defineAsyncComponent(() => import('./AgentProgressCard.vue'))
const ChatReviewCard = defineAsyncComponent(() => import('./ChatReviewCard.vue'))

const authStore = useAuthStore()
const pluginStore = usePluginStore()
const workStore = useWorkStore()
const fileStore = useFileStore()
const workspaceStore = useWorkspaceStore()
const ctxStore = useChatContextStore()

const CRAB_PLUGIN_ID = 'crab-companion'
const CAT_PLUGIN_ID = 'cat-companion'
const SPONGEBOB_PLUGIN_ID = 'spongebob-companion'
const darkTheme = ref(false)

const contextSidebarRef = ref<InstanceType<typeof ContextSidebar> | null>(null)

function openExternalUrl(url: string) {
  window.open(url, '_blank', 'noopener,noreferrer')
}

const { addConversation, updateTitle, getSessionId, findBySessionId, removeConversation, getConversationsForFolder, getConversationsForWork, loaded: chatHistoryLoaded } = useChatHistory()

const scrollBodyRef = ref<HTMLElement | null>(null)
const inputRef = ref<HTMLTextAreaElement | null>(null)
const agentSearchRef = ref<HTMLInputElement | null>(null)
const skillSearchRef = ref<HTMLInputElement | null>(null)
const inputText = ref('')
const activeConvId = ref('')
const showAtContentPicker = ref(false)

const crabVisible = ref(false)
const crabInputRect = ref<DOMRect | null>(null)
let crabRafId: number | null = null

function updateCrabPosition() {
  const seat = document.querySelector('.dsh-composer-seat:not(.dsh-composer-hero)')
  if (seat) {
    crabInputRect.value = seat.getBoundingClientRect()
  }
  if (crabVisible.value) {
    crabRafId = requestAnimationFrame(updateCrabPosition)
  }
}

watch(crabVisible, (v) => {
  if (v) {
    crabRafId = requestAnimationFrame(updateCrabPosition)
  } else if (crabRafId) {
    cancelAnimationFrame(crabRafId)
    crabRafId = null
  }
})

const stream = useChatStream()
const expand = useChatExpandable()
const pickers = useChatPickers()

const {
  isStreaming, streamingHasContent, streamingThinking, streamingClock,
  streamingMsg,
} = stream
const {
  isExecExpanded, toggleExec,
  isDiffExpanded, toggleDiff, expandedAgentId, toggleAgentExpand,
} = expand
const {
  selectedAgentId, selectedAgentLabel, showAgentPicker, showSkillPicker,
  showModelPicker, currentModel, filteredAgents, filteredSkills,
  agentPickerFilter, skillPickerFilter, showWorkspaceList, thinkingDepth,
  thinkingLabel, allSkills, availableAgents, modelOptions, currentModelMeta,
  selectAgent, clearSelectedAgent, toggleAgentPicker, closeAgentPicker,
  toggleSkillPicker, closeSkillPicker, toggleModelPicker, selectModel,
  cycleThinking, toggleWorkspaceList,
} = pickers

let _skillInsertGuard = false

function insertSkillToInput(skill: { node_type: string; name: string; display_name: string; description: string }) {
  _skillInsertGuard = true
  pickers.insertSkillToInput(skill, inputText, inputRef)
  setTimeout(() => { _skillInsertGuard = false }, 50)
}

const currentTurnPhase = ref<TurnPhase>('idle')
const currentStatusIndicator = ref<StatusIndicator>({ header: '' })

function _transitionTurn(phase: TurnPhase, statusHeader?: string) {
  currentTurnPhase.value = phase
  if (statusHeader !== undefined) {
    currentStatusIndicator.value = { header: statusHeader }
  }
  if (stream.streamingMsg.value?.agentMeta) {
    stream.streamingMsg.value.agentMeta.turnPhase = phase
    if (statusHeader !== undefined) {
      stream.streamingMsg.value.agentMeta.statusIndicator = { header: statusHeader }
    }
  }
}

const isChatMode = computed(() => {
  return !heroMode.value
})

const isCodexMode = computed(() => {
  return false
})

const sse = useChatSSE({
  transitionTurn: _transitionTurn,
  emit: (event: string, draft?: any) => {
    if (event === 'draft-panel-update') {
      emit('draft-panel-update', draft)
      return
    }
    emit(event as 'open-image-workspace', draft)
  },
  isCodexMode: () => isCodexMode.value,
  isChatMode: () => isChatMode.value,
  streamingThinking: stream.streamingThinking,
  streamingHasContent: stream.streamingHasContent,
  persistAssistantMessage: (content: string, agentMeta: any) => {
    const sid = sse.activeSessionId.value
    if (sid) {
      chatSessionsApi.addMessage(sid, 'assistant', content, agentMeta).catch(() => {})
    }
  },
  onSseComplete: () => {
    stream.notifySseComplete()
  },
  onContentReady: () => {
    stream.notifySseComplete()
  },
  onStreamDelta: () => {
    stream.touchStream()
    if (!showToBottom.value && !_scrollRafPending) {
      _scrollRafPending = true
      requestAnimationFrame(() => {
        _scrollRafPending = false
        if (!showToBottom.value) {
          void scrollToBottom()
        }
      })
    }
  },
})

let _scrollRafPending = false

onUnmounted(() => {
  if (crabRafId) cancelAnimationFrame(crabRafId)
  document.removeEventListener('click', onDocumentClick)
  stopNotificationSSE()
})

function onDocumentClick(e: MouseEvent) {
  const target = e.target as HTMLElement
  if (pickers.showAgentPicker.value && !target.closest('.dsh-agent-pick-wrap')) {
    pickers.closeAgentPicker()
  }
  if (pickers.showSkillPicker.value && !target.closest('.dsh-skill-pick-wrap')) {
    pickers.closeSkillPicker()
  }
  if (pickers.showModelPicker.value && !target.closest('.dsh-model-pick-wrap')) {
    pickers.showModelPicker.value = false
  }
  if (pickers.showWorkspaceList.value && !target.closest('.dsh-ws-pick-wrap')) {
    pickers.showWorkspaceList.value = false
  }
  if (showHeroWorkspaceList.value && !target.closest('.dsh-hero-ws-wrap')) {
    showHeroWorkspaceList.value = false
  }
}

const lastStats = ref<ChatStats | null>(null)

const conversations = ref<Conversation[]>([])

const heroMode = ref(true)

const actions = useChatActions({
  conversations,
  activeConvId,
  inputText,
  lastStats,
  heroMode,
  activeSessionId: sse.activeSessionId,
  chatSseController: sse.chatSseController,
  workflowSseController: sse.workflowSseController,
  scrollBodyRef,
  inputRef,
  resetExpandAll: () => expand.resetAll(),
})
const {
  newConversation, deleteConversation, switchToConversation,
  switchToFolder, onSwitchConv, enterHeroMode, resetToInitial,
  scrollToBottom: actionsScrollToBottom, normalizeAgentMeta: actionsNormalizeAgentMeta,
} = actions

const showToBottom = ref(false)
const highlightEnabled = ref(false)
const autoApproveEnabled = ref(true)
const showHeroWorkspaceList = ref(false)

let _autoApproveToastTimer: number | null = null

function toggleAutoApprove() {
  autoApproveEnabled.value = !autoApproveEnabled.value
  const existing = document.querySelector('.dsh-copy-toast')
  if (existing) existing.remove()
  if (_autoApproveToastTimer !== null) window.clearTimeout(_autoApproveToastTimer)
  const el = document.createElement('div')
  el.className = 'dsh-copy-toast'
  el.textContent = autoApproveEnabled.value
    ? '已开启自动放行：工具调用将直接执行'
    : '已切换为需确认：工具调用将暂停等待您批准'
  document.body.appendChild(el)
  _autoApproveToastTimer = window.setTimeout(() => {
    el.remove()
    _autoApproveToastTimer = null
  }, 2000)
}

function toggleHeroWorkspaceList() {
  showHeroWorkspaceList.value = !showHeroWorkspaceList.value
}

function onHeroWorkspaceSelect(wsId: string) {
  workspaceStore.setActive(wsId)
  switchToFolder('ws-' + wsId)
  showHeroWorkspaceList.value = false
}

async function onPickFolder() {
  pickers.showWorkspaceList.value = false
  const result = await workspaceStore.pickAndBind()
  if (result) {
    pickers.showWorkspaceList.value = false
  }
}

const currentMessages = computed(() => {
  const conv = conversations.value.find(c => c.id === activeConvId.value)
  return conv ? conv.messages.filter(m => m.role !== 'system') : []
})

const sendMessageRef = ref<() => Promise<void>>(async () => {})

const interactions = useChatInteractions({
  conversations,
  activeConvId,
  inputText,
  currentMessages,
  activeSessionId: sse.activeSessionId,
  chatSseController: sse.chatSseController,
  workflowSseController: sse.workflowSseController,
  activeWorkflowId: sse.activeWorkflowId,
  workflowSseLastEventId: sse.workflowSseLastEventId,
  isStreaming: stream.isStreaming,
  streamingMsg: stream.streamingMsg,
  streamingHasContent: stream.streamingHasContent,
  streamingThinking: stream.streamingThinking,
  abort: () => stream.abort(),
  notifyImmediateComplete: () => stream.notifyImmediateComplete(),
  resumeFromPause: () => stream.resumeFromPause(),
  subscribeChatSSE: (sessionId: string, assistantMsg: ChatMessage) => sse.subscribeChatSSE(sessionId, assistantMsg),
  sendMessageRef,
})
const {
  onRecoveryDecide, getReviewType, onChatReviewed, onChatConfirmed, onChatClarified, onConfirmationExpired,
  retryWorkflow, switchCollabMode, interruptAgent, confirmAction,
  stopStreaming, retryLastMessage,
  dangerDialog, showDangerConfirm, onDangerConfirm, onDangerCancel,
  copyMessage,
} = interactions

const chatWork = useChatWork({
  inputText,
  isStreaming: stream.isStreaming,
  stopStreaming,
  sendMessageRef,
  emitStartCoverWorkflow: (topic: string) => emit('start-cover-workflow', topic),
})
const {
  activeWork, showWorkDetail, detailWidth,
  startDetailResize, resetDetailWidth, exitWorkContext, onWorkChatAction, getFileIconComponent,
} = chatWork

function startCtxResize(e: MouseEvent) {
  e.preventDefault()
  const startX = e.clientX
  const startW = ctxStore.sidebarWidth
  let rafId = 0
  function onMove(ev: MouseEvent) {
    const delta = startX - ev.clientX
    cancelAnimationFrame(rafId)
    rafId = requestAnimationFrame(() => {
      ctxStore.setSidebarWidth(startW + delta)
    })
  }
  function onUp() {
    cancelAnimationFrame(rafId)
    document.removeEventListener('mousemove', onMove)
    document.removeEventListener('mouseup', onUp)
    document.body.style.cursor = ''
    document.body.style.userSelect = ''
    document.body.classList.remove('is-ctx-resizing')
  }
  document.addEventListener('mousemove', onMove)
  document.addEventListener('mouseup', onUp)
  document.body.style.cursor = 'col-resize'
  document.body.style.userSelect = 'none'
  document.body.classList.add('is-ctx-resizing')
}

function resetCtxWidth() {
  ctxStore.setSidebarWidth(Math.max(280, Math.min(420, Math.floor(window.innerWidth / 4))))
}

const CREATION_TYPE_LABELS: Record<string, string> = {
  image_text: '图文',
  video: '视频',
  ai_edit: 'AI剪辑',
}

const creationTypeLabel = computed(() => CREATION_TYPE_LABELS[workStore.activeCreationType] || '图文')

const creationTypeIcon = computed(() => {
  const map: Record<string, any> = { image_text: FileText, video: Video, ai_edit: Scissors }
  return map[workStore.activeCreationType] || FileText
})

const showCreationPicker = ref(false)

const creationTypeOptions = [
  { key: 'image_text' as const, label: '图文', desc: '小红书笔记、图文卡片', icon: ImageIcon },
  { key: 'voiceover' as const, label: '口播', desc: '口播脚本与提词器', icon: Mic },
  { key: 'short_video' as const, label: '短视频', desc: '抖音/快手短视频脚本', icon: Video },
  { key: 'ai_edit' as const, label: 'AI剪辑', desc: 'AI辅助视频剪辑', icon: Scissors },
  { key: 'long_article' as const, label: '长文', desc: '知乎/公众号长文', icon: FileText },
  { key: 'live_clip' as const, label: '直播切片', desc: '直播精彩片段剪辑', icon: Radio },
]

function toggleCreationPicker() {
  showCreationPicker.value = !showCreationPicker.value
}

function onSelectCreationType(typeKey: string) {
  workStore.activeCreationType = typeKey as any
  showCreationPicker.value = false
  const existingDraft = workStore.works.find(
    (w: any) => w.isDraft && w.contentType === typeKey
  )
  if (existingDraft) {
    workStore.setActiveWork(existingDraft.id)
  } else {
    workStore.createDraft(typeKey)
  }
  showWorkDetail.value = true
  ctxStore.setSidebarVisible(true)
}

function toggleWorkDetail() {
  if (ctxStore.sidebarVisible) {
    ctxStore.setSidebarVisible(false)
  } else {
    ctxStore.setSidebarVisible(true)
  }
  showWorkDetail.value = ctxStore.sidebarVisible
}

const chatSend = useChatSend({
  activeWork,
  workStore,
  currentModel: pickers.currentModel,
  thinkingDepth: pickers.thinkingDepth,
  getAbortController: () => stream.getAbortController(),
  streamingHasContent: stream.streamingHasContent,
  streamingThinking: stream.streamingThinking,
  streamingMsg: stream.streamingMsg,
  isStreaming: stream.isStreaming,
  notifySseComplete: () => stream.notifySseComplete(),
  notifyImmediateComplete: () => stream.notifyImmediateComplete(),
  notifyAgentLoopDone: (graceMs: number) => stream.notifyAgentLoopDone(graceMs),
  chatSseController: sse.chatSseController,
  scrollToBottom: async () => scrollToBottom(),
  transitionTurn: (phase: string, label?: string) => _transitionTurn(phase as any, label || ''),
  highlightEnabled,
  lastStats,
})
const { sendMessageReal } = chatSend

function getRunningToolLabel(msg: ChatMessage): string {
  const running = msg.toolCalls?.filter(tc => tc.status === 'running') || []
  if (running.length === 0) return ''
  const names = running.map(tc => {
    const { label } = getToolDisplayLabel(tc.name)
    return `${label}中`
  })
  return names.join(' · ')
}

function getWorkflowStepLabel(msg: ChatMessage): string {
  return getChatStatusText(msg.agentMeta)
}

function toggleHighlight() {
  highlightEnabled.value = !highlightEnabled.value
}

function autoResize() {
  const el = inputRef.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = Math.min(el.scrollHeight, 336) + 'px'
}

provideChatRenderContext({
  isChatMode,
  isCodexMode,
  isStreaming,
  streamingMsg,
  streamingThinking,
  streamingHasContent,
  streamingClock,
  currentStatusIndicator,
  isExecExpanded,
  toggleExec,
  isDiffExpanded,
  toggleDiff,
  isThinkingExpanded: (idx: number) => expand.isThinkingExpanded(idx),
  toggleThinking: expand.toggleThinking,
  expandedAgentId,
  toggleAgentExpand,
  copyMessage,
  retryLastMessage,
  retryWorkflow,
  interruptAgent,
  onRecoveryDecide,
  onChatReviewed,
  onChatConfirmed,
  onChatClarified,
  onConfirmationExpired,
  switchCollabMode,
  sendMessage,
  openInBrowser: (url: string) => { ctxStore.setSidebarVisible(true); contextSidebarRef.value?.navigateToUrl(url) },
})

function onUserInput() {
  autoResize()
  const text = inputText.value
  const cursorPos = inputRef.value?.selectionStart ?? text.length
  const before = text.slice(0, cursorPos)
  const atMatch = before.match(/@([^@\s]*)$/)
  if (atMatch) {
    showAtContentPicker.value = true
  } else {
    showAtContentPicker.value = false
  }

  const slashMatch = before.match(/\/([^\s]*)$/)
  if (slashMatch && !_skillInsertGuard) {
    const beforeSlash = before.slice(0, before.lastIndexOf('/'))
    if (!beforeSlash.match(/https?:$/)) {
      if (!showSkillPicker.value) {
        showSkillPicker.value = true
      }
      skillPickerFilter.value = slashMatch[1] || ''
    } else {
      if (showSkillPicker.value) {
        showSkillPicker.value = false
        skillPickerFilter.value = ''
      }
    }
  } else {
    if (showSkillPicker.value) {
      showSkillPicker.value = false
      skillPickerFilter.value = ''
    }
  }
}

function onAtContentSelect(type: string, data: any) {
  showAtContentPicker.value = false
  if (type === 'agent') {
    selectAgent(data)
    const atMatch = inputText.value.match(/@([^@\s]*)$/)
    if (atMatch) {
      inputText.value = inputText.value.replace(/@([^@\s]*)$/, '')
    }
    return
  }
  if (type === 'work') {
    ctxStore.linkWork(data.id)
  } else if (type === 'memory') {
    ctxStore.addStyleMemory({ content: data.content, source: data.source || 'user-set' })
  } else if (type === 'hot') {
    ctxStore.addContextItem({
      type: 'analysis',
      label: data.type === 'trending' ? '当前热点趋势' : '热门话题',
      summary: '实时数据',
      pinned: true,
      meta: { refId: `hot-${data.type}`, hotType: data.type },
    })
  } else if (type === 'rule') {
    ctxStore.addContextItem({
      type: 'rule',
      label: data.type === 'xhs_rule' ? '小红书创作规范' : '抖音创作规范',
      summary: '平台规范',
      pinned: true,
      meta: { refId: `rule-${data.type}`, ruleName: data.type === 'xhs_rule' ? '小红书创作规范' : '抖音创作规范' },
    })
  }
  const atMatch = inputText.value.match(/@([^@\s]*)$/)
  if (atMatch) {
    inputText.value = inputText.value.replace(/@([^@\s]*)$/, '')
  }
}

function onScroll() {
  const el = scrollBodyRef.value
  if (!el) return
  const dist = el.scrollHeight - el.scrollTop - el.clientHeight
  showToBottom.value = dist > 120
  updateMinimapActive()
}

const minimapUserIndices = computed(() => {
  return currentMessages.value
    .map((m, i) => m.role === 'user' ? i : -1)
    .filter(i => i !== -1)
})

const minimapDots = computed(() => {
  return minimapUserIndices.value.map(idx => {
    const msg = currentMessages.value[idx]
    const text = typeof msg.content === 'string' ? msg.content : ''
    const preview = text.length > 30 ? text.slice(0, 30) + '…' : text
    return { msgIdx: idx, preview }
  })
})

const minimapActiveIndex = ref(-1)

function updateMinimapActive() {
  const el = scrollBodyRef.value
  if (!el || minimapUserIndices.value.length === 0) return
  const viewportMid = el.scrollTop + el.clientHeight / 2
  let active = -1
  const items = el.querySelectorAll('.dsh-flow-item[data-user-idx]')
  items.forEach((item) => {
    const idxStr = (item as HTMLElement).dataset.userIdx
    if (idxStr === undefined || idxStr === '') return
    const idx = parseInt(idxStr, 10)
    if (isNaN(idx)) return
    const rect = item.getBoundingClientRect()
    const containerRect = el.getBoundingClientRect()
    const itemTop = rect.top - containerRect.top + el.scrollTop
    if (itemTop <= viewportMid) {
      active = idx
    }
  })
  minimapActiveIndex.value = active
}

function minimapScrollTo(dotIndex: number) {
  const el = scrollBodyRef.value
  if (!el) return
  const target = el.querySelector(`.dsh-flow-item[data-user-idx="${dotIndex}"]`)
  if (target) {
    target.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }
}

watch(currentMessages, () => {
  nextTick(() => updateMinimapActive())
})

const scrollToBottom = actionsScrollToBottom

function onKeyDown(e: KeyboardEvent) {
  if (e.key === 'Escape') {
    if (pickers.showAgentPicker.value) {
      pickers.closeAgentPicker()
      return
    }
    if (pickers.showSkillPicker.value) {
      pickers.closeSkillPicker()
      return
    }
    if (pickers.showModelPicker.value) {
      pickers.showModelPicker.value = false
      return
    }
    if (sse.workflowSseController.value) {
      sse.workflowSseController.value.abort()
      sse.workflowSseController.value = null
      return
    }
    if (stream.isStreaming.value) {
      stream.abort()
      return
    }
  }
  if (e.key === 'Enter' && !e.shiftKey) {
    if (pickers.showAgentPicker.value) {
      e.preventDefault()
      const first = pickers.filteredAgents.value[0]
      if (first) pickers.selectAgent(first)
      return
    }
    if (pickers.showSkillPicker.value) {
      e.preventDefault()
      const first = pickers.filteredSkills.value[0]
      if (first) pickers.insertSkillToInput(first, inputText, inputRef)
      return
    }
    e.preventDefault()
    sendMessage()
  }
  if (e.key === '@' && !pickers.showAgentPicker.value && !pickers.showSkillPicker.value && !showAtContentPicker.value && inputText.value === '') {
    e.preventDefault()
    pickers.toggleAgentPicker()
  }
  if (e.key === '/' && !pickers.showSkillPicker.value && !pickers.showAgentPicker.value && !showAtContentPicker.value && inputText.value === '') {
    e.preventDefault()
    pickers.toggleSkillPicker()
  }
}

async function sendMessage() {
  const text = inputText.value.trim()
  if (!text) return
  if (stream.isStreaming.value) {
    return
  }
  stream.isStreaming.value = true
  inputText.value = ''
  if (!chatHistoryLoaded.value) {
    const start = Date.now()
    while (!chatHistoryLoaded.value && Date.now() - start < 15000) {
      await new Promise(resolve => setTimeout(resolve, 120))
    }
    if (!chatHistoryLoaded.value) {
      // 旧实现在这里静默 return——历史加载一旦超时（后端卡顿/网络慢时很容易发生），
      // 用户的发送就凭空消失：没报错、没弹窗、没反应。这是「点了发送没动静」的根因。
      // 历史加载只影响展示连续性，不阻塞发送。
      console.warn('[ChatAgent] 历史会话加载超时（15s），跳过等待直接发送')
    }
  }

  try {
    const circuitStatus = await chatSessionsApi.getLLMCircuitStatus()
    if (circuitStatus.state === 'open' || circuitStatus.state === 'half_open') {
      const probeResult = await chatSessionsApi.probeLLMCircuit()
      if (probeResult.recovered) {
        console.info('[ChatAgent] LLM circuit auto-recovered via probe')
      } else {
        const shouldReset = await showDangerConfirm(
          'LLM 服务不可用',
          `LLM API 当前不可用（${circuitStatus.open_reason || circuitStatus.state}）\n\n` +
          `探针结果：${probeResult.detail}\n\n` +
          `如果您已充值或更换了 API Key，点击"确定"强制重置后重试。\n` +
          `点击"取消"等待自动恢复（每 ${Math.round(circuitStatus.recovery_timeout)}s 自动探针一次）。`
        )
        if (shouldReset) {
          try {
            await chatSessionsApi.resetLLMCircuit()
          } catch {}
        } else {
          stream.isStreaming.value = false
          return
        }
      }
    }
  } catch {}

  let conv = conversations.value.find(c => c.id === activeConvId.value)
  if (!conv) {
    await newConversation()
    conv = conversations.value.find(c => c.id === activeConvId.value)
    if (!conv) {
      conv = conversations.value[0]
    }
  }
  if (!conv) {
    stream.isStreaming.value = false
    return
  }

  conv.messages.push({ role: 'user', content: text })
  if (conv.messages.filter(m => m.role === 'user').length === 1) {
    conv.title = text.length > 200 ? text.slice(0, 200) + '…' : text
    updateTitle(conv.id, conv.title)
    const sid = sse.activeSessionId.value || getSessionId(conv.id)
    if (sid) {
      chatSessionsApi.updateSession(sid, conv.title).catch(() => {})
    }
  }

  if (inputRef.value) {
    inputRef.value.style.height = 'auto'
  }

  heroMode.value = false
  crabVisible.value = true
  stream.streamingHasContent.value = false
  stream.streamingThinking.value = false
  stream.startClock()
  stream.createAbortController()
  stream.setBeforeFinish(() => {
    const msg = stream.streamingMsg.value
    if (msg) sse.flushStreamDelta(msg)
  })
  stream.beginStream(() => {
    stream.resetStreamState()
    _transitionTurn('idle', '')
    stream.stopClock()
    scrollToBottom()
  })
  await scrollToBottom()

  const startTime = Date.now()

  try {
    await sendAgentMessage(conv, text, startTime)
  } catch (err: any) {
    const lastMsg = conv.messages[conv.messages.length - 1]
    if (lastMsg && lastMsg.role === 'assistant' && !lastMsg.content) {
      lastMsg.content = `请求失败: ${err.message || '未知错误'}`
      lastMsg.isError = true
    } else {
      conv.messages.push({
        role: 'assistant',
        content: `请求失败: ${err.message || '未知错误'}`,
        isError: true,
      })
    }
    const errSid = sse.activeSessionId.value || getSessionId(conv.id)
    if (errSid) {
      chatSessionsApi.addMessage(errSid, 'assistant', `请求失败: ${err.message || '未知错误'}`).catch(() => {})
    }
    stream.notifyImmediateComplete()
  } finally {
    if (stream.isStreaming.value) {
      // Codex turn 生命周期：SSE 终态才是唯一结束信号。
      // POST /api/v1/chat/agent 是非流式端点（loop 跑完才返回），返回时 SSE 播放器
      // 可能仍在追赶积压 delta——立即收尾会表现为「回复没显示完就结束」。
      // 改为宽限期收尾：等 SSE 真正关闭，最多再等 10s 兜底。
      stream.notifyAgentLoopDone(10_000)
    }
  }
}

sendMessageRef.value = sendMessage

function normalizeAgentMeta(raw: any): any {
  return actionsNormalizeAgentMeta(raw)
}

function mergeLoadedHistory(conv: Conversation, apiMsgs: any[]) {
  const loaded = apiMsgs.map(m => ({
    role: m.role as 'user' | 'assistant' | 'system',
    content: m.content,
    agentMeta: actionsNormalizeAgentMeta(m.agent_meta || undefined) as any,
  })).filter(m => m.role !== 'system')
  // 防御性降级：历史中残留的 awaiting_clarification 消息已不可能再交互，
  // 降级为 completed 避免渲染出无法操作的澄清卡片
  for (const m of loaded) {
    if (m.role === 'assistant' && m.agentMeta?.workflowStatus === 'awaiting_clarification') {
      m.agentMeta.workflowStatus = 'completed'
    }
  }
  const existing = new Set(conv.messages.map(m => `${m.role}:${m.content}`))
  const fresh = loaded.filter(m => !existing.has(`${m.role}:${m.content}`))
  conv.messages = [
    ...fresh,
    ...conv.messages.filter(m => m.role !== 'system'),
  ]
}

const notificationSSE = useNotificationSSE()
const startNotificationSSE = notificationSSE.start
const stopNotificationSSE = notificationSSE.stop

const chatInit = useChatInit({
  conversations,
  activeConvId,
  heroMode,
  chatHistoryLoaded,
  crabVisible,
  sse,
  fileStore,
  pluginStore,
  workspaceStore,
  pickers,
  addConversation,
  mergeLoadedHistory,
  startNotificationSSE,
  onDocumentClick,
  CRAB_PLUGIN_ID,
})

onMounted(() => chatInit.init())

watch(activeConvId, async (newId) => {
  if (!newId) return
  const conv = conversations.value.find(c => c.id === newId)
  if (conv && conv.messages.length === 0) {
    heroMode.value = true
    const sid = getSessionId(newId) || newId
    sse.activeSessionId.value = sid
    try {
      const msgs = await chatSessionsApi.listMessages(sid)
      mergeLoadedHistory(conv, msgs)
      if (conv.messages.length > 0) heroMode.value = false
    } catch {
      // failed to load messages
    }
  } else {
    heroMode.value = false
  }
  const sid = getSessionId(newId) || newId
  sse.activeSessionId.value = sid
  await fileStore.loadFilesForSession(sid)
  void scrollToBottom()
})

watch(pickers.showAgentPicker, (val) => {
  if (val) {
    nextTick(() => {
      agentSearchRef.value?.focus()
    })
  }
})

watch(pickers.showSkillPicker, (val) => {
  if (val) {
    nextTick(() => {
      skillSearchRef.value?.focus()
    })
  }
})

const activeFile = computed(() => fileStore.activeFile)
const creativePhase = ref<string>('idle')

const chatAgent = useChatAgent({
  activeWork,
  activeFile,
  workStore,
  fileStore,
  workspaceStore,
  pickers,
  sse,
  stream,
  showWorkDetail,
  creativePhase,
  modelSettings: props.modelSettings,
  autoApproveEnabled,
  sendMessageReal,
  transitionTurn: (phase: string, label?: string) => _transitionTurn(phase as any, label || ''),
})
const { sendAgentMessage } = chatAgent

watch(activeWork, async (newWork, oldWork) => {
  if (newWork) {
    showWorkDetail.value = true
    ctxStore.setSidebarVisible(true)
    ctxStore.linkWork(newWork.id)
    if (newWork.id !== oldWork?.id) {
      await switchToWorkConversation(newWork.id)
    }
  } else {
    showWorkDetail.value = false
  }
})

async function switchToWorkConversation(workId: string) {
  const workConvs = getConversationsForWork(workId)
  if (workConvs.length > 0) {
    const latest = workConvs[0]
    await switchToConversation(latest.id)
    return
  }
  // 内存缓存未命中（如页面刷新后），向后端查询该作品已有的会话
  try {
    const sessions = await chatSessionsApi.listSessions(workId)
    if (sessions.length > 0) {
      for (const sess of sessions) {
        const exists = conversations.value.find(c => c.id === sess.id)
        if (!exists) {
          conversations.value.push({
            id: sess.id,
            title: sess.title || '新会话',
            messages: [],
            createdAt: sess.created_at ? new Date(sess.created_at).getTime() : Date.now(),
          })
        }
        addConversation(sess.id, sess.title || '新会话', sess.folder_id || 'chat-files', sess.id, sess.work_id)
      }
      conversations.value.sort((a, b) => b.createdAt - a.createdAt)
      // 后端按 updated_at 倒序返回，sessions[0] 即最新会话
      const latest = conversations.value.find(c => c.id === sessions[0].id)
      if (latest) {
        await switchToConversation(latest.id)
        return
      }
    }
  } catch {
    // 后端查询失败时回退：新建会话
  }
  await newConversation(undefined, workId)
}

function _resetToInitial() {
  resetToInitial()
  showWorkDetail.value = false
  ctxStore.setSidebarVisible(false)
  ctxStore.clearAll()
}

defineExpose({ newConversation, deleteConversation, onWorkChatAction, resetToInitial: _resetToInitial, enterHeroMode, switchToConversation, switchToFolder, showWorkDetail, toggleWorkDetail })
</script>

<style>
@import 'highlight.js/styles/github.css';

.dsh-chat.is-dark .hljs {
  background: transparent;
  color: #c9d1d9;
}
.dsh-chat.is-dark .dsh-md img {
  background: rgba(255, 255, 255, 0.04);
  border-color: rgba(255, 255, 255, 0.10);
}
.dsh-chat {
  background: #fff !important;
}
.dsh-chat.is-dark {
  background: #111 !important;
}
body.is-detail-resizing .dsh-chat-layout > .wdp {
  transition: none !important;
}
body.is-detail-resizing .dsh-chat-layout > .dsh-chat {
  transition: none !important;
}
body.is-detail-resizing * {
  cursor: col-resize !important;
}

/* 统一 Markdown 输出层：所有 LLM 回复、用户消息和推理链都套用同一套尺寸与排版约束 */
.dsh-md {
  max-width: 100%;
  word-break: break-word;
  overflow-wrap: anywhere;
  color: inherit;
  font-size: inherit;
  line-height: inherit;
}

.dsh-user-row {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
}

.dsh-user-stack {
  min-width: 0;
  max-width: min(525px, 82%);
}

.dsh-bubble {
  max-width: 100%;
  background: #f0f0f0;
  color: #1a1a1a;
  border: 1px solid #e0e0e0;
  border-radius: 16px 16px 4px 16px;
  padding: 10px 14px;
  font-size: 14px;
  line-height: 1.6;
  word-break: break-word;
  text-align: left;
}

.dsh-bubble p {
  margin: 0;
}

.dsh-bubble p + p {
  margin-top: 6px;
}
.dsh-md p {
  margin: 0 0 16px 0;
  line-height: 1.625;
  color: #374151;
  font-size: 14px;
}
.dsh-md p:last-child {
  margin-bottom: 0;
}
.dsh-md h1 {
  margin: 24px 0 12px 0;
  font-size: 16px;
  font-weight: 700;
  line-height: 24px;
  color: #111827;
  padding-bottom: 8px;
  border-bottom: 1px solid #e5e7eb;
}
.dsh-md h2 {
  margin: 24px 0 12px 0;
  font-size: 16px;
  font-weight: 700;
  line-height: 24px;
  color: #111827;
}
.dsh-md h3,
.dsh-md h4 {
  margin: 24px 0 12px 0;
  font-size: 16px;
  font-weight: 700;
  line-height: 24px;
  color: #111827;
}
.dsh-md ul,
.dsh-md ol {
  margin: 0 0 16px 0;
  padding-left: 0;
}
.dsh-md ul {
  list-style: none;
  padding-left: 20px;
}
.dsh-md ul li {
  margin: 8px 0;
  line-height: 1.625;
  padding-left: 14px;
  position: relative;
}
.dsh-md ul li::before {
  content: '›';
  position: absolute;
  left: 0;
  top: 1px;
  color: var(--dsh-accent);
  font-size: 13px;
  font-weight: 700;
  line-height: 18px;
}
.dsh-md ol {
  padding-left: 20px;
  list-style: decimal;
}
.dsh-md ol li {
  margin: 8px 0;
  line-height: 1.625;
  padding-left: 4px;
}
.dsh-md img {
  max-width: 100%;
  height: auto;
  max-height: 240px;
  object-fit: contain;
  border-radius: 6px;
  margin: 6px 0;
  display: block;
  background: #f5f5f5;
  border: 1px solid #e0e0e0;
  padding: 4px;
}
.dsh-md table {
  border-collapse: collapse;
  margin: 16px 0;
  font-size: 14px;
  width: 100%;
  max-width: 100%;
  display: block;
  overflow-x: auto;
  border: none;
  border-radius: 0;
}
.dsh-md th,
.dsh-md td {
  border-bottom: 1px solid #f3f4f6;
  padding: 10px;
  text-align: left;
  max-width: 420px;
  overflow-wrap: anywhere;
  word-break: break-word;
}
.dsh-md th {
  background: #f9fafb;
  border-bottom: 1px solid #e5e7eb;
  font-weight: 500;
  color: #4b5563;
}
.dsh-md td {
  color: #374151;
}
.dsh-md a {
  color: var(--dsh-accent);
  text-decoration: none;
}
.dsh-md a:hover {
  color: var(--dsh-text-1);
  text-decoration: underline;
}
.dsh-md blockquote {
  margin: 16px 0;
  padding: 12px;
  border-left: 4px solid #60a5fa;
  border-radius: 0 8px 8px 0;
  background: rgba(239, 246, 255, 0.3);
  color: #4b5563;
  font-size: 14px;
}
.dsh-md .dsh-kv-list {
  margin: 16px 0;
  padding: 0;
  font-size: 14px;
}
.dsh-md .dsh-kv-list dt {
  font-weight: 600;
  color: #374151;
  margin-top: 10px;
  padding-left: 0;
}
.dsh-md .dsh-kv-list dt:first-child {
  margin-top: 0;
}
.dsh-md .dsh-kv-list dd {
  margin: 2px 0 0 0;
  color: #6b7280;
  font-family: 'SF Mono', 'JetBrains Mono', 'Fira Code', Consolas, Menlo, monospace;
  font-size: 13px;
  word-break: break-all;
}
.dsh-md .dsh-code-block {
  margin: 16px 0;
  overflow: hidden;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #f8fafc;
  color: #1e293b;
  font-family: 'SF Mono', 'JetBrains Mono', 'Fira Code', Consolas, Menlo, monospace;
  box-shadow: none;
}
.dsh-md .dsh-code-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 34px;
  padding: 0 10px 0 14px;
  background: #f1f5f9;
  border-bottom: 1px solid #e2e8f0;
}
.dsh-md .dsh-code-lang {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.7px;
  text-transform: uppercase;
  color: #64748b;
}
.dsh-md .dsh-code-actions {
  display: inline-flex;
  align-items: center;
}
.dsh-md .dsh-code-copy-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 24px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: #94a3b8;
  cursor: pointer;
  opacity: 0.72;
  padding: 0;
  transition: opacity 0.15s ease, color 0.15s ease, background 0.15s ease;
}
.dsh-md .dsh-code-copy-btn:hover {
  opacity: 1;
  color: #475569;
  background: rgba(0, 0, 0, 0.05);
}
.dsh-md .dsh-code-copy-btn .dsh-copy-icon-check {
  display: none;
}
.dsh-md .dsh-code-copy-btn.dsh-copy-success {
  opacity: 1;
  color: #16a34a;
}
.dsh-md .dsh-code-copy-btn.dsh-copy-success .dsh-copy-icon-default {
  display: none;
}
.dsh-md .dsh-code-copy-btn.dsh-copy-success .dsh-copy-icon-check {
  display: block;
}
.dsh-md .dsh-code-body {
  display: flex;
  align-items: flex-start;
  max-height: 480px;
  overflow: auto;
}
.dsh-md .dsh-code-gutter {
  position: sticky;
  left: 0;
  z-index: 1;
  flex-shrink: 0;
  min-width: 38px;
  padding: 16px 10px 16px 14px;
  text-align: right;
  background: #f1f5f9;
  border-right: 1px solid #e2e8f0;
  color: #94a3b8;
  font-family: inherit;
  font-size: 12px;
  line-height: 1.65;
  white-space: pre;
  user-select: none;
}
.dsh-md .dsh-code-body code.hljs {
  display: block;
  flex: 1 1 auto;
  min-width: max-content;
  margin: 0;
  padding: 16px;
  background: transparent;
  color: #1e293b;
  font-family: inherit;
  font-size: 12px;
  line-height: 1.65;
  white-space: pre;
}
.dsh-md .dsh-code-body .hljs-comment,
.dsh-md .dsh-code-body .hljs-quote {
  color: #6a737d;
}
.dsh-md .dsh-code-body .hljs-keyword,
.dsh-md .dsh-code-body .hljs-selector-tag,
.dsh-md .dsh-code-body .hljs-literal,
.dsh-md .dsh-code-body .hljs-doctag,
.dsh-md .dsh-code-body .hljs-title.section {
  color: #d73a49;
}
.dsh-md .dsh-code-body .hljs-string,
.dsh-md .dsh-code-body .hljs-regexp,
.dsh-md .dsh-code-body .hljs-addition,
.dsh-md .dsh-code-body .hljs-attr,
.dsh-md .dsh-code-body .hljs-variable,
.dsh-md .dsh-code-body .hljs-template-variable,
.dsh-md .dsh-code-body .hljs-selector-attr,
.dsh-md .dsh-code-body .hljs-selector-pseudo {
  color: #032f62;
}
.dsh-md .dsh-code-body .hljs-number,
.dsh-md .dsh-code-body .hljs-symbol,
.dsh-md .dsh-code-body .hljs-bullet,
.dsh-md .dsh-code-body .hljs-link,
.dsh-md .dsh-code-body .hljs-meta,
.dsh-md .dsh-code-body .hljs-selector-id,
.dsh-md .dsh-code-body .hljs-title {
  color: #005cc5;
}
.dsh-md .dsh-code-body .hljs-built_in,
.dsh-md .dsh-code-body .hljs-type,
.dsh-md .dsh-code-body .hljs-title.class_ {
  color: #6f42c1;
}
.dsh-md .dsh-code-body .hljs-attribute,
.dsh-md .dsh-code-body .hljs-name,
.dsh-md .dsh-code-body .hljs-tag {
  color: #22863a;
}
.dsh-md .dsh-code-body .hljs-section,
.dsh-md .dsh-code-body .hljs-selector-class,
.dsh-md .dsh-code-body .hljs-deletion {
  color: #24292e;
}
.dsh-md .dsh-inline-code {
  font-family: 'SF Mono', 'JetBrains Mono', 'Fira Code', Consolas, Menlo, monospace;
  font-size: 0.9em;
  background: transparent;
  border: none;
  border-radius: 0;
  padding: 0;
  color: #3b82f6;
  font-weight: 600;
  cursor: pointer;
  transition: color 0.15s ease;
}
.dsh-md .dsh-inline-code:hover {
  color: #2563eb;
}
.dsh-md .dsh-card-html-wrap {
  margin: 12px 0;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid #e5e7eb;
  background: #fff;
}
.dsh-md .dsh-card-iframe {
  display: block;
  width: 100%;
  min-height: 200px;
  border: none;
  margin: 0;
  padding: 0;
}

.dsh-cell-reasoning {
  background: transparent;
  border: none;
}
.dsh-cell-reasoning .dsh-cell-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 0;
  color: var(--dsh-text-3);
  font-size: 12px;
  letter-spacing: 0.02em;
  cursor: default;
}
.dsh-cell-reasoning .dsh-cell-icon {
  color: var(--dsh-text-3);
  flex-shrink: 0;
}
.dsh-cell-reasoning .dsh-cell-label {
  color: var(--dsh-text-3);
  font-weight: 500;
  white-space: nowrap;
}
.dsh-cell-reasoning .dsh-cell-streaming-preview {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--dsh-text-3);
  font-size: 12px;
  line-height: 1.4;
  opacity: 0.7;
}
.dsh-cell-reasoning .dsh-cell-streaming-preview--settled {
  opacity: 0.55;
  font-style: italic;
}

.dsh-cell-reasoning-streaming .dsh-cell-streaming-preview::after {
  content: '▍';
  margin-left: 2px;
  color: var(--dsh-text-3);
  animation: dsh-md-reasoning-cursor 1s step-end infinite;
}

.dsh-cell-reasoning-streaming .dsh-cell-icon {
  animation: dsh-md-reasoning-pulse 1.5s ease-in-out infinite;
}

@keyframes dsh-md-reasoning-cursor {
  0%, 50% { opacity: 1; }
  51%, 100% { opacity: 0; }
}

@keyframes dsh-md-reasoning-pulse {
  0%, 100% { opacity: 0.45; }
  50% { opacity: 1; }
}

.dsh-copy-toast {
  position: fixed;
  z-index: 1000;
  left: 50%;
  bottom: 28px;
  transform: translateX(-50%);
  padding: 8px 14px;
  border-radius: 8px;
  background: rgba(17, 24, 39, 0.92);
  color: #e5e7eb;
  font-size: 12px;
  line-height: 18px;
  box-shadow: 0 10px 28px rgba(0, 0, 0, 0.24);
  animation: dsh-copy-toast-in 0.18s ease-out;
}

@keyframes dsh-copy-toast-in {
  from {
    opacity: 0;
    transform: translate(-50%, 8px);
  }
  to {
    opacity: 1;
    transform: translate(-50%, 0);
  }
}

/* ═══ 消息操作栏 ═══ */
.dsh-msg-actions {
  display: flex;
  justify-content: flex-start;
  align-items: center;
  gap: 20px;
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px solid rgba(0, 0, 0, 0.04);
  opacity: 0;
  pointer-events: none;
  transform: translateY(4px);
  transition: opacity 0.2s ease, transform 0.2s ease;
}

.dsh-assistant-row:hover .dsh-msg-actions {
  opacity: 1;
  pointer-events: auto;
  transform: translateY(0);
}

.dsh-msg-btn {
  all: unset;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: #9ca3af;
  cursor: pointer;
  transition: color 0.15s ease;
}

.dsh-msg-btn:hover {
  color: #374151;
}

.dsh-msg-btn:active {
  color: #111827;
}

.dsh-msg-btn--liked {
  color: #ef4444 !important;
}

.dsh-like-count {
  font-size: 11px;
  font-weight: 600;
  color: #ef4444;
  margin-left: 2px;
  line-height: 1;
}

.dsh-msg-btn--disliked {
  color: #6b7280 !important;
}

.dsh-theme-scene {
  position: absolute;
  inset: 0;
  pointer-events: none;
  z-index: 0;
  overflow: hidden;
}
</style>

<style scoped src="./chat-view.css"></style>