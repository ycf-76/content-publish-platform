<template>
  <div class="page-container" id="page-history">
    <div class="mint-hero mint-glass">
      <div>
        <h1 class="font-cal mint-hero-title">工作流历史</h1>
        <p class="mint-hero-sub">查看所有工作流执行记录</p>
      </div>
      <div style="display:flex; gap:8px;">
        <select class="mint-select" style="width:140px;">
          <option>全部状态</option>
          <option>执行中</option>
          <option>待审核</option>
          <option>已完成</option>
          <option>已终止</option>
        </select>
        <input type="text" class="mint-input" placeholder="搜索主题..." style="width:200px;">
      </div>
    </div>

    <div class="mint-workflow-cards mint-workflow-cards-bento bento-grid bento-grid-4 overflow-y-auto">
      <div class="mint-wf-card">
        <div class="mint-wf-header">
          <div class="mint-wf-title-row">
            <div class="mint-wf-step" style="background:#10B981;">✓</div>
            <div>
              <div class="mint-wf-title">夏日穿搭攻略</div>
              <div class="mint-wf-desc">2026-07-28 14:30 · 已完成</div>
            </div>
          </div>
          <span class="mint-badge badge-mint">
            <span class="mint-status-dot" style="background:#059669;"></span>
            已完成
          </span>
        </div>
        <div style="display:flex; gap:12px; padding:8px 0;">
          <div style="font-size: 14px; color:#6B7280;">
            <i data-lucide="user" style="width:12px;height:12px;margin-right:4px;"></i>
            林知夏的穿搭日记
          </div>
          <div style="font-size: 14px; color:#6B7280;">
            <i data-lucide="clock" style="width:12px;height:12px;margin-right:4px;"></i>
            耗时 8 分钟
          </div>
          <div style="font-size: 14px; color:#6B7280;">
            <i data-lucide="zap" style="width:12px;height:12px;margin-right:4px;"></i>
            2,340 tokens
          </div>
        </div>
        <div class="mint-wf-footer">
          <button class="mint-btn mint-btn-ghost">
            <i data-lucide="external-link" style="width:16px;height:16px;"></i>
            查看详情
          </button>
          <button class="mint-btn mint-btn-outline">
            <i data-lucide="copy" style="width:16px;height:16px;"></i>
            复制工作流
          </button>
        </div>
      </div>

      <div class="mint-wf-card">
        <div class="mint-wf-header">
          <div class="mint-wf-title-row">
            <div class="mint-wf-step" style="background:#3B6CF6;">
              <i data-lucide="loader-2" style="width:14px;height:14px;animation:spin 1s linear infinite;"></i>
            </div>
            <div>
              <div class="mint-wf-title">周末旅行攻略</div>
              <div class="mint-wf-desc">2026-07-28 15:00 · 执行中</div>
            </div>
          </div>
          <span class="mint-badge badge-sky">
            <span class="mint-status-dot" style="background:#3B6CF6;"></span>
            执行中
          </span>
        </div>
        <div style="display:flex; gap:12px; padding:8px 0;">
          <div style="font-size: 14px; color:#6B7280;">
            <i data-lucide="user" style="width:12px;height:12px;margin-right:4px;"></i>
            夏日美食探店
          </div>
          <div style="font-size: 14px; color:#6B7280;">
            <i data-lucide="git-branch" style="width:12px;height:12px;margin-right:4px;"></i>
            当前节点: 图片生成
          </div>
        </div>
        <div class="mint-wf-footer">
          <button class="mint-btn mint-btn-ghost">
            <i data-lucide="external-link" style="width:16px;height:16px;"></i>
            查看详情
          </button>
          <button class="mint-btn mint-btn-outline">
            <i data-lucide="pause" style="width:16px;height:16px;"></i>
            暂停
          </button>
        </div>
      </div>

      <div class="mint-wf-card bento-col-2">
        <div class="mint-wf-header">
          <div class="mint-wf-title-row">
            <div class="mint-wf-step" style="background:#F59E0B;">审</div>
            <div>
              <div class="mint-wf-title">防晒好物推荐</div>
              <div class="mint-wf-desc">2026-07-28 13:45 · 待审核</div>
            </div>
          </div>
          <span class="mint-badge badge-cream">
            <span class="mint-status-dot" style="background:#F59E0B;"></span>
            待审核
          </span>
        </div>
        <div style="display:flex; gap:12px; padding:8px 0;">
          <div style="font-size: 14px; color:#6B7280;">
            <i data-lucide="user" style="width:12px;height:12px;margin-right:4px;"></i>
            林知夏的穿搭日记
          </div>
          <div style="font-size: 14px; color:#6B7280;">
            <i data-lucide="git-branch" style="width:12px;height:12px;margin-right:4px;"></i>
            当前节点: 终审发布
          </div>
        </div>
        <div class="mint-wf-footer">
          <button class="mint-btn mint-btn-ghost">
            <i data-lucide="external-link" style="width:16px;height:16px;"></i>
            查看详情
          </button>
          <button class="mint-btn mint-btn-primary">
            <i data-lucide="clipboard-check" style="width:16px;height:16px;"></i>
            去审核
          </button>
        </div>
      </div>

      <div class="mint-wf-card">
        <div class="mint-wf-header">
          <div class="mint-wf-title-row">
            <div class="mint-wf-step" style="background:#EF4444;">✕</div>
            <div>
              <div class="mint-wf-title">健身餐食谱</div>
              <div class="mint-wf-desc">2026-07-27 18:20 · 已终止</div>
            </div>
          </div>
          <span class="mint-badge" style="background:#FEE2E2; color:#991B1B;">
            <span class="mint-status-dot" style="background:#EF4444;"></span>
            已终止
          </span>
        </div>
        <div style="display:flex; gap:12px; padding:8px 0;">
          <div style="font-size: 14px; color:#6B7280;">
            <i data-lucide="user" style="width:12px;height:12px;margin-right:4px;"></i>
            夏日美食探店
          </div>
          <div style="font-size: 14px; color:#6B7280;">
            <i data-lucide="info" style="width:12px;height:12px;margin-right:4px;"></i>
            用户手动终止
          </div>
        </div>
        <div class="mint-wf-footer">
          <button class="mint-btn mint-btn-ghost">
            <i data-lucide="external-link" style="width:16px;height:16px;"></i>
            查看详情
          </button>
          <button class="mint-btn mint-btn-outline">
            <i data-lucide="rotate-ccw" style="width:16px;height:16px;"></i>
            重新执行
          </button>
        </div>
      </div>
    </div>
  </div>
</template>