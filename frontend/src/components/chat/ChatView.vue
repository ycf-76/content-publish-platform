<template>
  <div class="rl-chat-layout">
  <div class="rl-chat" :class="{ 'is-dark': darkTheme, 'is-hero': heroMode }">

    <!-- SVG 滤镜：马克笔背景层手绘笔触效果（仅作用于伪元素背景，不伤文字） -->
    <svg style="position:absolute;width:0;height:0" aria-hidden="true">
      <defs>
        <filter id="rl-marker-filter">
          <feTurbulence type="turbulence" baseFrequency="0.04" numOctaves="4" result="noise" seed="3" />
          <feDisplacementMap in="SourceGraphic" in2="noise" scale="2" xChannelSelector="R" yChannelSelector="G" />
        </filter>
      </defs>
    </svg>

    <div v-if="activeWork && !heroMode" class="rl-work-bar">
      <div class="rl-work-bar-info">
        <FileText :size="13" :stroke-width="1.8" class="rl-work-bar-icon" />
        <span class="rl-work-bar-title">{{ activeWork.title || '未命名作品' }}</span>
        <span v-if="activeWork.platform" class="rl-work-bar-platform">{{ activeWork.platform }}</span>
        <span v-if="activeWork.performanceTier && activeWork.performanceTier !== '-'" class="rl-work-bar-metrics">{{ activeWork.performanceTier }}</span>
      </div>
      <div class="rl-work-bar-actions">
        <button class="rl-work-bar-btn" @click="exitWorkContext" title="解除作品关联">
          <X :size="14" />
        </button>
      </div>
    </div>

    <div v-if="workStore.analysisContext && !heroMode" class="rl-analysis-bar">
      <div class="rl-analysis-bar-info">
        <img src="/icons/分析.svg" class="rl-analysis-bar-icon" />
        <span class="rl-analysis-bar-label">分析已联动</span>
        <span class="rl-analysis-bar-detail">{{ workStore.analysisContext.overview?.total || 0 }}篇数据 · 归因{{ ({ low: '低', medium: '中', high: '高' } as Record<string,string>)[workStore.analysisContext.confidence] || workStore.analysisContext.confidence }}置信</span>
      </div>
      <div class="rl-analysis-bar-actions">
        <button class="rl-work-bar-btn rl-analysis-create" @click="handoffOpen = true" title="基于分析开启创作">
          <Sparkles :size="13" />
          开启创作
        </button>
        <button class="rl-work-bar-btn" @click="ctxStore.unlinkAnalysis()" title="解除联动">
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

    <div v-if="activeFile && !heroMode" class="rl-file-bar">
      <div class="rl-file-bar-info">
        <component :is="getFileIconComponent(activeFile.type)" :size="13" :stroke-width="1.6" class="rl-file-bar-icon" />
        <span class="rl-file-bar-name">{{ activeFile.name }}</span>
        <span class="rl-file-bar-size">{{ fileStore.formatFileSize(activeFile.size) }}</span>
      </div>
      <div class="rl-file-bar-actions">
        <button class="rl-work-bar-btn" @click="fileStore.setActiveFile(null)" title="移除文件">
          <X :size="14" />
        </button>
      </div>
    </div>

    <!-- 侧边栏开关浮动按钮 -->
    <button
      v-if="!ctxStore.sidebarVisible"
      class="rl-sidebar-toggle"
      @click="toggleWorkDetail"
      title="打开工作台面板"
    >
      <PanelRight :size="18" :stroke-width="1.8" />
    </button>

    <!-- 滚动主体 -->
    <div
      class="rl-scroll-body"
      :class="{ 'rl-scroll-hidden': heroMode }"
      ref="scrollBodyRef"
      @scroll="onScroll"
    >
      <div v-if="!heroMode" class="rl-column">
        <!--
          Turn 状态指示行 — 基于 Codex submission_loop 生命周期
          Turn: idle → thinking → planning → executing → responding → done
          Chat 模式下只显示轻量提示，Codex 模式下显示详细信息
        -->
        <div v-if="isStreaming" class="rl-turn-status" :class="{ 'rl-turn-status--thinking': streamingThinking || !streamingHasContent }">
          <span class="rl-turn-status-dot" />
          <span class="rl-turn-status-shimmer-text">
            <template v-if="isChatMode">
              {{ currentStatusIndicator.header || (streamingThinking ? '思考中…' : streamingHasContent ? '生成回复中…' : '思考中…') }}
            </template>
            <template v-else>
              <template v-if="!streamingThinking && !streamingHasContent">Thinking…</template>
              <template v-else-if="streamingThinking">{{ currentStatusIndicator.header || 'Reasoning…' }}</template>
              <template v-else>Writing…</template>
            </template>
          </span>
          <span class="rl-turn-status-clock" v-if="isStreaming">{{ streamingClock }}s</span>
          <!-- Governance status indicators -->
          <span v-if="isCodexMode && streamingMsg?.agentMeta?.governance?.retrying" class="rl-governance-badge rl-governance-retry">
            Retrying ({{ streamingMsg.agentMeta.governance.retryCount }}x)
          </span>
          <span v-if="isCodexMode && streamingMsg?.agentMeta?.governance?.compacted" class="rl-governance-badge rl-governance-compact">
            Context compressed
          </span>
          <span v-if="isCodexMode && streamingMsg?.agentMeta?.governance?.budgetWarning" class="rl-governance-badge rl-governance-budget">
            Budget low
          </span>
          <span v-if="isCodexMode && streamingMsg?.agentMeta?.collab?.activeCount" class="rl-governance-badge rl-collab-badge">
            {{ streamingMsg.agentMeta.collab.activeCount }} agent{{ streamingMsg.agentMeta.collab.activeCount > 1 ? 's' : '' }}
          </span>
          <span v-if="isCodexMode" class="rl-turn-status-hint">esc to interrupt</span>
        </div>

        <div
          v-for="(msg, idx) in currentMessages"
          :key="idx"
          class="rl-flow-item"
          :data-user-idx="msg.role === 'user' ? minimapUserIndices.indexOf(idx) : undefined"
        >
          <!-- ═══ UserCell ═══ -->
          <UserMessageCell v-if="msg.role === 'user'" :msg="msg" />

          <!-- ═══ AssistantCell ═══ -->
          <AssistantMessageCell v-else-if="msg.role === 'assistant'" :msg="msg" :idx="idx" :sse-session-id="sse.activeSessionId.value || ''" />
        </div>
      </div>


      <!-- 回到底部浮动钮 -->
      <div v-if="showToBottom && !heroMode" class="rl-to-bottom-slot">
        <button class="rl-to-bottom" @click="scrollToBottom(true)" title="回到底部">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>
        </button>
      </div>
    </div>

    <!-- Minimap 锚点导航栏 -->
    <div
      v-if="minimapDots.length > 1 && !heroMode"
      class="rl-minimap"
    >
      <button
        v-for="(dot, di) in minimapDots"
        :key="di"
        class="rl-minimap-dot"
        :class="{ 'rl-minimap-active': di === minimapActiveIndex }"
        :title="dot.preview"
        @click="minimapScrollTo(di)"
      ></button>
    </div>

    <!-- HERO 区 -->
    <div v-if="heroMode" class="rl-hero-zone" aria-hidden="false">
      <div class="rl-hero-stack">
        <div class="rl-hero-brand">
          <div class="rl-hero-logo-wrap">
            <img src="/icons/logo2.svg" alt="Pulse Studio" class="rl-hero-logo-crab" />
          </div>
          <h2 class="rl-hero-title">{{ activeWork ? activeWork.title : '为你开启智能创作之旅' }}</h2>
          <span class="rl-hero-badge">测试版</span>
        </div>
        <div class="rl-hero-workspace-row">
          <div class="rl-hero-ws-wrap">
            <button class="rl-hero-chip" type="button" @click="toggleHeroWorkspaceList">
              <span>{{ workspaceStore.activeWorkspace ? workspaceStore.activeWorkspace.name : '选择一个工作区开始' }}</span>
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>
            </button>
            <Transition name="rl-slide-up">
              <div v-if="showHeroWorkspaceList" class="rl-hero-ws-dropdown" @click.stop>
                <div class="rl-hero-ws-dropdown-header">
                  <span class="rl-hero-ws-dropdown-title">侧边栏工作区</span>
                </div>
                <div class="rl-hero-ws-dropdown-list">
                  <button
                    v-for="ws in workspaceStore.workspaces"
                    :key="ws.id"
                    class="rl-hero-ws-dropdown-item"
                    :class="{ 'rl-hero-ws-dropdown-selected': ws.id === workspaceStore.activeWorkspaceId }"
                    @click="onHeroWorkspaceSelect(ws.id)"
                  >
                    <FolderOpen :size="14" :stroke-width="2" />
                    <div class="rl-hero-ws-item-info">
                      <span class="rl-hero-ws-item-name">{{ ws.name }}</span>
                      <span class="rl-hero-ws-item-path">{{ ws.local_path }}</span>
                    </div>
                    <span v-if="ws.id === workspaceStore.activeWorkspaceId" class="rl-hero-ws-item-check">
                      <Check :size="12" />
                    </span>
                  </button>
                  <div v-if="workspaceStore.workspaces.length === 0" class="rl-hero-ws-dropdown-empty">
                    暂无工作区，请先在侧边栏导入文件夹
                  </div>
                </div>
              </div>
            </Transition>
          </div>
          <button class="rl-hero-chip" type="button">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
            <span>标准模式</span>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>
          </button>
        </div>
      </div>
    </div>

    <!-- 输入卡 -->
    <div class="rl-composer-seat" :class="{ 'rl-composer-hero': heroMode }">
      <div class="rl-composer-card">
        <!-- 已选智能体标签行 -->
        <div v-if="selectedAgentId" class="rl-agent-tag-row">
          <span class="rl-agent-tag">
            <img src="/icons/智能体.svg" class="rl-agent-tag-icon" />
            <span class="rl-agent-tag-name">{{ selectedAgentLabel }}</span>
            <button class="rl-agent-tag-close" @click="clearSelectedAgent" title="取消选择">
              <X :size="10" />
            </button>
          </span>
        </div>
        <div class="rl-at-picker-wrap">
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
          class="rl-input"
          :disabled="isStreaming"
          :placeholder="isStreaming ? '等待回复中…' : (selectedAgentId ? `向 ${selectedAgentLabel} 发送消息…` : '给 Pulse Studio 发送消息（@ 智能体 / 内容 / 技能）')"
          rows="2"
          @keydown="onKeyDown"
          @input="onUserInput"
          @focus="onUserInput"
        ></textarea>
        <div v-if="cardAttachments.length" style="display:flex;gap:8px;flex-wrap:wrap;padding:6px 12px" aria-label="已添加的卡片图片">
          <span v-for="asset in cardAttachments" :key="asset.asset_id" style="display:inline-flex;align-items:center;gap:6px;border:1px solid #d2d6df;border-radius:6px;padding:3px 8px;font-size:12px">
            <img :src="asset.thumbnail_url" :alt="asset.filename" style="width:28px;height:28px;object-fit:cover" />
            {{ asset.filename }}
            <button type="button" :disabled="isStreaming" :aria-label="`移除 ${asset.filename}`" @click="cardAttachments = cardAttachments.filter(item => item.asset_id !== asset.asset_id)">×</button>
          </span>
        </div>
        <div class="rl-composer-row">
          <div class="rl-tools">
          <div v-if="!isCodexMode" class="rl-plus-wrap">
            <input ref="cardImageInput" type="file" accept="image/png,image/jpeg,image/webp,image/gif" multiple style="display:none" @change="onCardImageSelected" />
            <button type="button" class="rl-add" :disabled="isStreaming || uploadingCardImages" :title="uploadingCardImages ? '上传中…' : '上传图片用于图文卡片（最多三张）'" aria-label="上传卡片图片" @click="cardImageInput?.click()">
              <ImageIcon :size="14" />
            </button>
          </div>
          <div class="rl-plus-wrap">
            <!-- 图片上传按钮 -->
            <div class="rl-img-upload-wrap">
              <button class="rl-img-upload-btn" :class="{ 'rl-img-upload-active': pendingImageAssets.length > 0 }" :disabled="isStreaming" @click="triggerImageUpload" title="上传图片（视频生成等 Skill 可直接使用）">
                <ImageIcon :size="14" :stroke-width="2" />
                <span v-if="pendingImageAssets.length > 0" class="rl-img-badge">{{ pendingImageAssets.length }}</span>
              </button>
              <input ref="imageUploadRef" type="file" accept="image/*" multiple class="rl-hidden-input" @change="onImageFilesSelected" />
              <!-- 已选图片缩略图条 -->
              <Transition name="rl-slide-up">
                <div v-if="pendingImageAssets.length > 0" class="rl-img-preview-bar">
                  <div v-for="(img, idx) in pendingImageAssets" :key="img.asset_id" class="rl-img-thumb-item">
                    <img :src="img.thumbnail_url || img.original_url" class="rl-img-thumb" />
                    <button class="rl-img-thumb-remove" @click="removePendingImage(idx)" title="移除">&times;</button>
                  </div>
                  <button class="rl-img-clear-all" @click="pendingImageAssets = []" title="清空全部">清空</button>
                </div>
              </Transition>
            </div>
            <button class="rl-add" :class="{ 'rl-add-active': highlightEnabled }" :disabled="isStreaming" @click="toggleHighlight" title="划重点">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>
              </button>
            </div>
            <!-- 绑定文件夹按钮 -->
            <div class="rl-ws-pick-wrap">
              <button class="rl-ws-pick-btn" :class="{ 'rl-ws-pick-active': workspaceStore.activeWorkspace }" :disabled="workspaceStore.binding" @click="workspaceStore.workspaces.length > 0 ? toggleWorkspaceList() : onPickFolder()" title="绑定本地文件夹（智能体可直接操控）">
                <FolderOpen :size="14" :stroke-width="2" />
              </button>
              <!-- 已绑定工作区下拉列表 -->
              <Transition name="rl-slide-up">
                <div v-if="showWorkspaceList" class="rl-ws-dropdown" @click.stop>
                  <div class="rl-ws-dropdown-header">
                    <span class="rl-ws-dropdown-title">已绑定的工作区</span>
                    <button class="rl-ws-dropdown-add" @click="onPickFolder" :disabled="workspaceStore.binding">
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
                      绑定新文件夹
                    </button>
                  </div>
                  <div class="rl-ws-dropdown-list">
                    <button
                      v-for="ws in workspaceStore.workspaces"
                      :key="ws.id"
                      class="rl-ws-dropdown-item"
                      :class="{ 'rl-ws-dropdown-selected': ws.id === workspaceStore.activeWorkspaceId }"
                      @click="switchToFolder('ws-' + ws.id); showWorkspaceList = false"
                    >
                      <FolderOpen :size="14" :stroke-width="2" />
                      <div class="rl-ws-item-info">
                        <span class="rl-ws-item-name">{{ ws.name }}</span>
                        <span class="rl-ws-item-path">{{ ws.local_path }}</span>
                      </div>
                      <span v-if="ws.id === workspaceStore.activeWorkspaceId" class="rl-ws-item-check">
                        <Check :size="12" />
                      </span>
                      <button class="rl-ws-item-unbind" @click.stop="workspaceStore.unbind(ws.id)" title="解绑">
                        <X :size="10" />
                      </button>
                    </button>
                    <div v-if="workspaceStore.workspaces.length === 0" class="rl-ws-dropdown-empty">
                      尚未绑定任何文件夹
                    </div>
                  </div>
                </div>
              </Transition>
            </div>
            <!-- 智能体召唤按钮 -->
            <div class="rl-agent-pick-wrap">
              <button class="rl-agent-pick-btn" :class="{ 'rl-agent-pick-active': showAgentPicker }" @click="toggleAgentPicker" title="选择智能体（快捷键 @）">
                <img src="/icons/智能体.svg" class="rl-agent-btn-icon" />
                <ChevronDown :size="10" />
              </button>
              <!-- 智能体选择下拉面板 -->
              <Transition name="rl-slide-up">
                <div v-if="showAgentPicker" class="rl-agent-dropdown" @click.stop>
                  <div class="rl-agent-dropdown-header">
                    <input
                      v-model="agentPickerFilter"
                      class="rl-agent-search"
                      placeholder="搜索智能体…"
                      @keydown.escape.stop="closeAgentPicker"
                      @keydown.enter.prevent="() => { const f = filteredAgents[0]; if (f) selectAgent(f) }"
                      ref="agentSearchRef"
                    />
                  </div>
                  <div class="rl-agent-dropdown-list">
                    <button
                      v-for="a in filteredAgents"
                      :key="a.agent_id"
                      class="rl-agent-dropdown-item"
                      :class="{ 'rl-agent-dropdown-selected': a.agent_id === selectedAgentId }"
                      @click="selectAgent(a)"
                    >
                      <img src="/icons/智能体.svg" class="rl-agent-item-svg" />
                      <div class="rl-agent-item-info">
                        <span class="rl-agent-item-role">{{ a.role || a.agent_id }}</span>
                        <span class="rl-agent-item-id">{{ a.agent_id }}</span>
                      </div>
                      <span v-if="a.agent_id === selectedAgentId" class="rl-agent-item-check">
                        <Check :size="12" />
                      </span>
                    </button>
                    <div v-if="filteredAgents.length === 0" class="rl-agent-dropdown-empty">
                      没有匹配的智能体
                    </div>
                  </div>
                  <div class="rl-agent-dropdown-footer">
                    <span class="rl-agent-dropdown-hint">输入 @ 快速召唤</span>
                  </div>
                </div>
              </Transition>
            </div>
            <!-- 技能召唤按钮 -->
            <div class="rl-skill-pick-wrap">
              <button class="rl-skill-pick-btn" :class="{ 'rl-skill-pick-active': showSkillPicker }" @click="toggleSkillPicker" title="选择技能（快捷键 /）">
                <span class="rl-skill-pick-slash">/</span>
                <ChevronDown :size="10" />
              </button>
              <!-- 技能选择下拉面板 -->
              <Transition name="rl-slide-up">
                <div v-if="showSkillPicker" class="rl-skill-dropdown" @click.stop>
                  <div class="rl-skill-dropdown-header">
                    <input
                      v-model="skillPickerFilter"
                      class="rl-skill-search"
                      placeholder="搜索技能…"
                      @keydown.escape.stop="closeSkillPicker"
                      @keydown.enter.prevent="() => { const f = filteredSkills[0]; if (f) insertSkillToInput(f) }"
                      ref="skillSearchRef"
                    />
                  </div>
                  <div class="rl-skill-dropdown-list">
                    <button
                      v-for="s in filteredSkills"
                      :key="s.node_type + '.' + s.name"
                      class="rl-skill-dropdown-item"
                      @click="insertSkillToInput(s)"
                    >
                      <span class="rl-skill-item-slash">/</span>
                      <div class="rl-skill-item-info">
                        <span class="rl-skill-item-name">{{ s.display_name }}</span>
                        <span class="rl-skill-item-desc">{{ s.description }}</span>
                      </div>
                      <span class="rl-skill-item-tag">{{ s.node_type }}</span>
                    </button>
                    <div v-if="filteredSkills.length === 0" class="rl-skill-dropdown-empty">
                      没有匹配的技能
                    </div>
                  </div>
                  <div class="rl-skill-dropdown-footer">
                    <span class="rl-skill-dropdown-hint">输入 / 快速召唤 · 选中后插入到输入框</span>
                  </div>
                </div>
              </Transition>
            </div>
            <!-- 创作方向选择按钮 -->
            <div class="rl-creation-pick-wrap">
              <button class="rl-creation-pick-btn" :class="{ 'rl-creation-pick-active': showCreationPicker }" @click="toggleCreationPicker" title="选择创作方向">
                <Sparkles :size="14" />
                <ChevronDown :size="10" />
              </button>
              <Transition name="rl-slide-up">
                <div v-if="showCreationPicker" class="rl-creation-dropdown" @click.stop>
                  <div class="rl-creation-dropdown-header">
                    <span class="rl-creation-dropdown-title">选择创作方向</span>
                  </div>
                  <div class="rl-creation-dropdown-list">
                    <button
                      v-for="ct in creationTypeOptions"
                      :key="ct.key"
                      class="rl-creation-dropdown-item"
                      :class="{ 'rl-creation-dropdown-selected': workStore.activeCreationType === ct.key }"
                      @click="onSelectCreationType(ct.key)"
                    >
                      <component :is="ct.icon" :size="16" />
                      <div class="rl-creation-item-info">
                        <span class="rl-creation-item-name">{{ ct.label }}</span>
                        <span class="rl-creation-item-desc">{{ ct.desc }}</span>
                      </div>
                    </button>
                  </div>
                </div>
              </Transition>
            </div>
            <!-- 自动放行切换按钮 -->
            <div class="rl-auto-approve-wrap">
              <button
                class="rl-auto-approve-btn"
                :class="{ 'rl-auto-approve-on': autoApproveEnabled }"
                @click="toggleAutoApprove"
                :title="autoApproveEnabled ? '工具调用自动放行中，点击切换为需要确认' : '工具调用需要确认，点击切换为自动放行'"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
                <span class="rl-auto-approve-label">{{ autoApproveEnabled ? '自动放行' : '需确认' }}</span>
              </button>
            </div>
          </div>
          <div class="rl-trailing">
            <div class="rl-model-pick-wrap">
              <button class="rl-model-pill" :class="{ 'rl-model-pick-active': showModelPicker }" @click="toggleModelPicker" :title="(currentModelMeta?.name || currentModel) + ' · ' + (currentModelMeta?.providerName || '')">
                <span class="rl-model-pill-icon" v-html="currentModelMeta?.icon || ''" />
                <span class="rl-model-pill-name">{{ currentModelMeta?.name || currentModel }}</span>
                <ChevronDown :size="10" />
              </button>
              <Transition name="rl-slide-up">
                <div v-if="showModelPicker" class="rl-model-dropdown" @click.stop>
                  <button
                    v-for="m in modelOptions"
                    :key="m.id"
                    class="rl-model-dropdown-item"
                    :class="{ 'rl-model-dropdown-selected': m.id === currentModel }"
                    @click="selectModel(m.id)"
                  >
                    <Check v-if="m.id === currentModel" :size="12" class="rl-model-check" />
                    <span v-else class="rl-model-check-placeholder" />
                    <span class="rl-model-dropdown-icon" v-html="m.icon" />
                    <span class="rl-model-dropdown-text">
                      <span class="rl-model-dropdown-name">
                        {{ m.name }}
                        <span class="rl-model-dropdown-provider">{{ m.providerName }}</span>
                      </span>
                      <span class="rl-model-dropdown-desc">{{ m.description }}</span>
                    </span>
                  </button>
                </div>
              </Transition>
            </div>
            <button v-if="!isStreaming" class="rl-primary" :disabled="!inputText.trim()" @click="sendMessage" title="发送">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>
            </button>
            <button v-else class="rl-stop" @click="stopStreaming" title="停止生成">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="6" y="6" width="12" height="12" rx="2"/></svg>
            </button>
          </div>
        </div>
      </div>

      <div class="rl-composer-footer" v-if="!heroMode && lastStats">
        <span class="rl-stats-line">
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
    class="rl-ctx-slide"
    :class="{ 'rl-ctx-slide-open': ctxStore.sidebarVisible }"
  >
    <div
      class="rl-ctx-resize-bar"
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
import { uploadAssets, type ImageAsset } from '@/api/assets'
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
const cardImageInput = ref<HTMLInputElement | null>(null)
const cardAttachments = ref<ImageAsset[]>([])
const uploadingCardImages = ref(false)
const pendingImageAssets = ref<ImageAsset[]>([])
const imageUploadRef = ref<HTMLInputElement | null>(null)

async function onCardImageSelected(event: Event) {
  const input = event.target as HTMLInputElement
  const files = Array.from(input.files || [])
  input.value = ''
  if (!files.length) return
  if (cardAttachments.value.length + files.length > 3) {
    alert('一组图文卡片最多附带三张图片')
    return
  }
  uploadingCardImages.value = true
  try {
    const assets = await uploadAssets(files)
    cardAttachments.value = [...cardAttachments.value, ...assets]
  } catch (error) {
    alert(`图片上传失败：${error instanceof Error ? error.message : String(error)}`)
  } finally {
    uploadingCardImages.value = false
  }
}

function triggerImageUpload() {
  imageUploadRef.value?.click()
}

async function onImageFilesSelected(event: Event) {
  const input = event.target as HTMLInputElement
  const files = Array.from(input.files || [])
  input.value = ''
  if (!files.length) return
  if (pendingImageAssets.value.length + files.length > 10) {
    alert('最多附带 10 张图片')
    return
  }
  try {
    const assets = await uploadAssets(files)
    pendingImageAssets.value = [...pendingImageAssets.value, ...assets]
  } catch (error) {
    alert(`图片上传失败：${error instanceof Error ? error.message : String(error)}`)
  }
}

function removePendingImage(idx: number) {
  pendingImageAssets.value.splice(idx, 1)
}

const activeConvId = ref('')
const showAtContentPicker = ref(false)

const crabVisible = ref(false)
const crabInputRect = ref<DOMRect | null>(null)
let crabRafId: number | null = null

function updateCrabPosition() {
  const seat = document.querySelector('.rl-composer-seat:not(.rl-composer-hero)')
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
  if (pickers.showAgentPicker.value && !target.closest('.rl-agent-pick-wrap')) {
    pickers.closeAgentPicker()
  }
  if (pickers.showSkillPicker.value && !target.closest('.rl-skill-pick-wrap')) {
    pickers.closeSkillPicker()
  }
  if (pickers.showModelPicker.value && !target.closest('.rl-model-pick-wrap')) {
    pickers.showModelPicker.value = false
  }
  if (pickers.showWorkspaceList.value && !target.closest('.rl-ws-pick-wrap')) {
    pickers.showWorkspaceList.value = false
  }
  if (showHeroWorkspaceList.value && !target.closest('.rl-hero-ws-wrap')) {
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
  ensureSession,
  scrollToBottom: actionsScrollToBottom, normalizeAgentMeta: actionsNormalizeAgentMeta,
} = actions

const showToBottom = ref(false)
const highlightEnabled = ref(false)
const autoApproveEnabled = ref(true)
const showHeroWorkspaceList = ref(false)

let _autoApproveToastTimer: number | null = null

function toggleAutoApprove() {
  autoApproveEnabled.value = !autoApproveEnabled.value
  const existing = document.querySelector('.rl-copy-toast')
  if (existing) existing.remove()
  if (_autoApproveToastTimer !== null) window.clearTimeout(_autoApproveToastTimer)
  const el = document.createElement('div')
  el.className = 'rl-copy-toast'
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
  // 渲染层 L3：chat 直连路径的 delta 也灌进同一个播放引擎（问题 1：两条流式路径速率一致）
  pushStreamDelta: (msg: ChatMessage, delta: string) => sse.pushStreamDelta?.(msg, delta),
  pushReasoningDelta: (msg: ChatMessage, delta: string) => sse.pushReasoningDelta?.(msg, delta),
  finishStream: (msg: ChatMessage, onDone?: () => void) => sse.finishStream?.(msg, onDone),
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
  const items = el.querySelectorAll('.rl-flow-item[data-user-idx]')
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
  const target = el.querySelector(`.rl-flow-item[data-user-idx="${dotIndex}"]`)
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
  const rawText = inputText.value.trim()
  if (!rawText || uploadingCardImages.value) return
  const attachedIds = cardAttachments.value.map(asset => asset.asset_id)
  const text = attachedIds.length
    ? `${rawText}\n\n[本次配图素材] 使用结构化图文卡片能力，asset_ids=${JSON.stringify(attachedIds)}；这些是我已上传的图片，请优先使用，不要重新生成。`
    : rawText
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

  // 会话惰性落库：只有用户真的发出请求，草稿才转成后端 session 并进入历史列表。
  // 顺序必须在 push user 消息之前——落库后 conv.id 会换成真实 sessionId，
  // 后面 updateTitle / 后端 updateSession 才能对得上。
  let ensuredSid: string | null = null
  try {
    ensuredSid = await ensureSession(
      conv.messages.filter(m => m.role === 'user').length === 0
        ? (rawText.length > 200 ? rawText.slice(0, 200) + '…' : rawText)
        : undefined,
    )
  } catch {
    ensuredSid = null
  }

  conv.messages.push({ role: 'user', content: text, timestamp: Date.now() })
  if (conv.messages.filter(m => m.role === 'user').length === 1) {
    conv.title = text.length > 200 ? text.slice(0, 200) + '…' : text
    updateTitle(conv.id, conv.title)
    const sid = ensuredSid || sse.activeSessionId.value || getSessionId(conv.id)
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
    const imageAssetIds = pendingImageAssets.value.map(a => a.asset_id)
    await sendAgentMessage(conv, text, startTime, imageAssetIds)
    cardAttachments.value = cardAttachments.value.filter(asset => !attachedIds.includes(asset.asset_id))
    pendingImageAssets.value = []
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
  // 草稿会话尚未落库：后端没有对应记录，别拿 draft_xxx 去查消息/文件
  if (conv?._isDraft) {
    sse.activeSessionId.value = null
    heroMode.value = conv.messages.length === 0
    void scrollToBottom()
    return
  }
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
  ensureSession,
  // 兜底：后端返回 session_id 时把仍处于草稿态的会话对上号（进历史、不再丢消息）
  linkSession: (sid: string) => {
    const conv = conversations.value.find(c => c.id === activeConvId.value)
    if (conv && conv._isDraft) {
      conv.id = sid
      conv._isDraft = false
      activeConvId.value = sid
      addConversation(sid, conv.title || '新会话', conv._folderId || 'chat-files', sid, conv._workId ?? null)
    }
    sse.activeSessionId.value = sid
  },
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
  // 当前已经是空草稿时复用它（草稿未落库，workConvs / 后端都查不到），
  // 否则每次点同一个作品都会丢弃用户已输入的内容。
  const current = conversations.value.find(c => c.id === activeConvId.value)
  if (current && current._isDraft && current.messages.length === 0) {
    current._workId = workId
    heroMode.value = true
    return
  }
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

.rl-chat.is-dark .hljs {
  background: transparent;
  color: #c9d1d9;
}
.rl-chat.is-dark .rl-md img {
  background: rgba(255, 255, 255, 0.04);
  border-color: rgba(255, 255, 255, 0.10);
}
.rl-chat {
  background: #fff !important;
}
.rl-chat.is-dark {
  background: #111 !important;
}
body.is-detail-resizing .rl-chat-layout > .wdp {
  transition: none !important;
}
body.is-detail-resizing .rl-chat-layout > .rl-chat {
  transition: none !important;
}
body.is-detail-resizing * {
  cursor: col-resize !important;
}

/* 统一 Markdown 输出层：所有 LLM 回复、用户消息和推理链都套用同一套尺寸与排版约束 */
.rl-md {
  max-width: 100%;
  word-break: break-word;
  overflow-wrap: anywhere;
  color: inherit;
  font-size: inherit;
  line-height: inherit;
}

.rl-user-row {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
}

.rl-user-stack {
  min-width: 0;
  max-width: min(525px, 82%);
}

.rl-bubble {
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

.rl-bubble p {
  margin: 0;
}

.rl-bubble p + p {
  margin-top: 6px;
}

.rl-msg-time {
  font-size: 11px;
  color: #9ca3af;
  margin-top: 4px;
  padding-right: 2px;
  text-align: right;
  opacity: 0;
  transition: opacity 0.2s ease;
  pointer-events: none;
  user-select: none;
  white-space: nowrap;
}

.rl-user-row:hover .rl-msg-time,
.rl-assistant-row:hover .rl-msg-time {
  opacity: 1;
  pointer-events: auto;
}

.rl-msg-time--assistant {
  text-align: left;
  padding-left: 2px;
  padding-right: 0;
}

.rl-chat.is-dark .rl-msg-time {
  color: #6b7280;
}

.rl-md p {
  margin: 0 0 16px 0;
  line-height: 1.625;
  color: #374151;
  font-size: 14px;
}
.rl-md p:last-child {
  margin-bottom: 0;
}
.rl-md h1 {
  margin: 24px 0 12px 0;
  font-size: 16px;
  font-weight: 700;
  line-height: 24px;
  color: #111827;
  padding-bottom: 8px;
  border-bottom: 1px solid #e5e7eb;
}
.rl-md h2 {
  margin: 24px 0 12px 0;
  font-size: 16px;
  font-weight: 700;
  line-height: 24px;
  color: #111827;
}
.rl-md h3,
.rl-md h4 {
  margin: 24px 0 12px 0;
  font-size: 16px;
  font-weight: 700;
  line-height: 24px;
  color: #111827;
}
.rl-md ul,
.rl-md ol {
  margin: 0 0 16px 0;
  padding-left: 0;
}
.rl-md ul {
  list-style: none;
  padding-left: 20px;
}
.rl-md ul li {
  margin: 8px 0;
  line-height: 1.625;
  padding-left: 14px;
  position: relative;
}
.rl-md ul li::before {
  content: '›';
  position: absolute;
  left: 0;
  top: 1px;
  color: var(--rl-accent);
  font-size: 13px;
  font-weight: 700;
  line-height: 18px;
}
.rl-md ol {
  padding-left: 20px;
  list-style: decimal;
}
.rl-md ol li {
  margin: 8px 0;
  line-height: 1.625;
  padding-left: 4px;
}
.rl-md img {
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
.rl-md table {
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
.rl-md th,
.rl-md td {
  border-bottom: 1px solid #f3f4f6;
  padding: 10px;
  text-align: left;
  max-width: 420px;
  overflow-wrap: anywhere;
  word-break: break-word;
}
.rl-md th {
  background: #f9fafb;
  border-bottom: 1px solid #e5e7eb;
  font-weight: 500;
  color: #4b5563;
}
.rl-md td {
  color: #374151;
}
.rl-md a {
  color: var(--rl-accent);
  text-decoration: none;
}
.rl-md a:hover {
  color: var(--rl-text-1);
  text-decoration: underline;
}
.rl-md blockquote {
  margin: 16px 0;
  padding: 12px;
  /* 原本是 #60a5fa 天蓝边框 + rgba(239,246,255,.3) 蓝底，与整体中性配色冲突。
     改为淡灰，并走主题变量，深色模式自动提亮。 */
  border-left: 4px solid var(--rl-md-rule, #d1d5db);
  border-radius: 0 8px 8px 0;
  background: var(--rl-md-quote-bg, rgba(0, 0, 0, .025));
  color: #4b5563;
  font-size: 14px;
}
.rl-md .rl-kv-list {
  margin: 16px 0;
  padding: 0;
  font-size: 14px;
}
.rl-md .rl-kv-list dt {
  font-weight: 600;
  color: #374151;
  margin-top: 10px;
  padding-left: 0;
}
.rl-md .rl-kv-list dt:first-child {
  margin-top: 0;
}
.rl-md .rl-kv-list dd {
  margin: 2px 0 0 0;
  color: #6b7280;
  font-family: 'SF Mono', 'JetBrains Mono', 'Fira Code', Consolas, Menlo, monospace;
  font-size: 13px;
  word-break: break-all;
}
.rl-md .rl-code-block {
  margin: 16px 0;
  overflow: hidden;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #f8fafc;
  color: #1e293b;
  font-family: 'SF Mono', 'JetBrains Mono', 'Fira Code', Consolas, Menlo, monospace;
  box-shadow: none;
}
.rl-md .rl-code-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 34px;
  padding: 0 10px 0 14px;
  background: #f1f5f9;
  border-bottom: 1px solid #e2e8f0;
}
.rl-md .rl-code-lang {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.7px;
  text-transform: uppercase;
  color: #64748b;
}
.rl-md .rl-code-actions {
  display: inline-flex;
  align-items: center;
}
.rl-md .rl-code-copy-btn {
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
.rl-md .rl-code-copy-btn:hover {
  opacity: 1;
  color: #475569;
  background: rgba(0, 0, 0, 0.05);
}
.rl-md .rl-code-copy-btn .rl-copy-icon-check {
  display: none;
}
.rl-md .rl-code-copy-btn.rl-copy-success {
  opacity: 1;
  color: #16a34a;
}
.rl-md .rl-code-copy-btn.rl-copy-success .rl-copy-icon-default {
  display: none;
}
.rl-md .rl-code-copy-btn.rl-copy-success .rl-copy-icon-check {
  display: block;
}
.rl-md .rl-code-body {
  display: flex;
  align-items: flex-start;
  max-height: 480px;
  overflow: auto;
}
.rl-md .rl-code-gutter {
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
.rl-md .rl-code-body code.hljs {
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
.rl-md .rl-code-body .hljs-comment,
.rl-md .rl-code-body .hljs-quote {
  color: #6a737d;
}
.rl-md .rl-code-body .hljs-keyword,
.rl-md .rl-code-body .hljs-selector-tag,
.rl-md .rl-code-body .hljs-literal,
.rl-md .rl-code-body .hljs-doctag,
.rl-md .rl-code-body .hljs-title.section {
  color: #d73a49;
}
.rl-md .rl-code-body .hljs-string,
.rl-md .rl-code-body .hljs-regexp,
.rl-md .rl-code-body .hljs-addition,
.rl-md .rl-code-body .hljs-attr,
.rl-md .rl-code-body .hljs-variable,
.rl-md .rl-code-body .hljs-template-variable,
.rl-md .rl-code-body .hljs-selector-attr,
.rl-md .rl-code-body .hljs-selector-pseudo {
  color: #032f62;
}
.rl-md .rl-code-body .hljs-number,
.rl-md .rl-code-body .hljs-symbol,
.rl-md .rl-code-body .hljs-bullet,
.rl-md .rl-code-body .hljs-link,
.rl-md .rl-code-body .hljs-meta,
.rl-md .rl-code-body .hljs-selector-id,
.rl-md .rl-code-body .hljs-title {
  color: #005cc5;
}
.rl-md .rl-code-body .hljs-built_in,
.rl-md .rl-code-body .hljs-type,
.rl-md .rl-code-body .hljs-title.class_ {
  color: #6f42c1;
}
.rl-md .rl-code-body .hljs-attribute,
.rl-md .rl-code-body .hljs-name,
.rl-md .rl-code-body .hljs-tag {
  color: #22863a;
}
.rl-md .rl-code-body .hljs-section,
.rl-md .rl-code-body .hljs-selector-class,
.rl-md .rl-code-body .hljs-deletion {
  color: #24292e;
}
.rl-md .rl-inline-code {
  font-family: 'SF Mono', 'JetBrains Mono', 'Fira Code', Consolas, Menlo, monospace;
  font-size: 0.9em;
  background: transparent;
  border: none;
  border-radius: 0;
  padding: 0;
  /* 原为 #3b82f6 蓝，改用主题文本色变量：亮色 #555 / 暗色 #999 */
  color: var(--rl-text-2, #555);
  font-weight: 600;
  cursor: pointer;
  transition: color 0.15s ease;
}
.rl-md .rl-inline-code:hover {
  color: var(--rl-text-1, #1a1a1a);
}
.rl-md .rl-card-html-wrap {
  margin: 12px 0;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid #e5e7eb;
  background: #fff;
}
.rl-md .rl-card-iframe {
  display: block;
  width: 100%;
  min-height: 200px;
  border: none;
  margin: 0;
  padding: 0;
}

.rl-cell-reasoning {
  background: transparent;
  border: none;
}
.rl-cell-reasoning .rl-cell-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 0;
  color: var(--rl-text-3);
  font-size: 12px;
  letter-spacing: 0.02em;
  cursor: default;
}
.rl-cell-reasoning .rl-cell-icon {
  color: var(--rl-text-3);
  flex-shrink: 0;
}
.rl-cell-reasoning .rl-cell-label {
  color: var(--rl-text-3);
  font-weight: 500;
  white-space: nowrap;
}
.rl-cell-reasoning .rl-cell-streaming-preview {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--rl-text-3);
  font-size: 12px;
  line-height: 1.4;
  opacity: 0.7;
}
.rl-cell-reasoning .rl-cell-streaming-preview--settled {
  opacity: 0.55;
  font-style: italic;
}

.rl-cell-reasoning-streaming .rl-cell-streaming-preview::after {
  content: '▍';
  margin-left: 2px;
  color: var(--rl-text-3);
  animation: rl-md-reasoning-cursor 1s step-end infinite;
}

.rl-cell-reasoning-streaming .rl-cell-icon {
  animation: rl-md-reasoning-pulse 1.5s ease-in-out infinite;
}

/* ── 思考阶段的氛围表达 ──
   旧语言用紫光呼吸 aura 兜底（思考期 content 为空时）。rl 语言里氛围色只属于
   思考盒本身（rl-think）：无思考摘要时由顶部状态行的琥珀 pulse 点承担等待感，
   外壳不再额外发光。 */
.rl-cell-reasoning-streaming .rl-cell-header {
  padding: 5px 0;
}
.rl-cell-reasoning-streaming .rl-cell-label {
  font-weight: 600;
}
.rl-cell-reasoning-streaming .rl-cell-streaming-preview {
  opacity: 0.85;
}

/* ── 顶部状态行的思考态强调 ──
   思考期只做「字重+色阶」的轻强调（weight 500 + text-2），不再用紫光呼吸 pill——
   rl 语言里氛围色只属于思考盒本身，外壳保持安静。 */
.rl-turn-status--thinking .rl-turn-status-shimmer-text {
  color: var(--rl-text-2);
  font-weight: 500;
}

@keyframes rl-md-reasoning-cursor {
  0%, 50% { opacity: 1; }
  51%, 100% { opacity: 0; }
}

@keyframes rl-md-reasoning-pulse {
  0%, 100% { opacity: 0.45; }
  50% { opacity: 1; }
}

.rl-copy-toast {
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
  animation: rl-copy-toast-in 0.18s ease-out;
}

@keyframes rl-copy-toast-in {
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
.rl-msg-actions {
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

.rl-assistant-row:hover .rl-msg-actions {
  opacity: 1;
  pointer-events: auto;
  transform: translateY(0);
}

.rl-msg-btn {
  all: unset;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: #9ca3af;
  cursor: pointer;
  transition: color 0.15s ease;
}

.rl-msg-btn:hover {
  color: #374151;
}

.rl-msg-btn:active {
  color: #111827;
}

.rl-msg-btn--liked {
  color: #ef4444 !important;
}

.rl-like-count {
  font-size: 11px;
  font-weight: 600;
  color: #ef4444;
  margin-left: 2px;
  line-height: 1;
}

.rl-msg-btn--disliked {
  color: #6b7280 !important;
}

/* ═══ 点踩维度选择弹层 ═══ */
.rl-dislike-dimensions {
  position: absolute;
  bottom: calc(100% + 10px);
  left: 0;
  z-index: 100;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 14px 16px;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.10);
  animation: rl-dislike-dimensions-in 0.18s ease-out;
}

@keyframes rl-dislike-dimensions-in {
  from {
    opacity: 0;
    transform: translateY(6px) scale(0.98);
  }
  to {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}

.rl-dislike-dimensions-title {
  font-size: 12px;
  font-weight: 600;
  color: #374151;
  padding-bottom: 2px;
  border-bottom: 1px solid #f3f4f6;
}

.rl-dislike-dimension-options {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.rl-dislike-dimension-btn {
  all: unset;
  font-size: 12px;
  color: #4b5563;
  padding: 6px 8px;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.12s ease, color 0.12s ease;
}

.rl-dislike-dimension-btn:hover {
  background: #fef2f2;
  color: #ef4444;
}

.rl-dislike-cancel {
  all: unset;
  font-size: 11px;
  color: #9ca3af;
  padding: 4px 8px;
  border-radius: 6px;
  cursor: pointer;
  transition: color 0.12s ease;
  align-self: flex-end;
}

.rl-dislike-cancel:hover {
  color: #6b7280;
}

.rl-theme-scene {
  position: absolute;
  inset: 0;
  pointer-events: none;
  z-index: 0;
  overflow: hidden;
}

/* ══════════════════════════════════════════════════════════════
   流式氛围（rl 语言）
   A 层：流式中给真正输出的文字一层极轻暖灰辉光；落地后自然回落
   B 层：打字头呼吸光点（琥珀色，与状态行 pulse 点同源=「进行中」语义）
   ══════════════════════════════════════════════════════════════ */

.rl-md blockquote,
.rl-md th,
.rl-md td,
.rl-md .rl-inline-code,
.rl-md .rl-code-block,
.rl-md .rl-code-header {
  transition: border-color .7s ease, background .7s ease, box-shadow .7s ease, color .7s ease;
}

/* 流式时给「真正输出的文字」一抹柔和辉光（暖灰，不用紫）。 */
.rl-streaming-light {
  text-shadow: 0 0 1px rgba(44, 44, 42, 0.10), 0 0 8px rgba(44, 44, 42, 0.05);
}

/* ── B 层：打字头呼吸光点 ── */
.rl-aura-tail {
  display: inline-block;
  width: .40em;
  height: 1.00em;
  margin-left: .14em;
  vertical-align: -.17em;
  border-radius: 50%;
  background: radial-gradient(circle at 50% 55%,
    rgba(186, 117, 23, .85) 0%,
    rgba(186, 117, 23, .35) 45%,
    rgba(186, 117, 23, 0) 72%);
  filter: blur(1.2px);
  animation: rl-aura-tail-breathe 1900ms ease-in-out infinite;
  will-change: opacity, transform;
}

@keyframes rl-aura-tail-breathe {
  0%, 100% { opacity: .42; transform: scale(.86) translateY(.6px); }
  50%      { opacity: .95; transform: scale(1.20) translateY(-1.2px); }
}


@media (prefers-reduced-motion: reduce) {
  .rl-aura-tail { animation: none; opacity: .7; }
}
</style>

<style scoped src="./chat-view.css"></style>