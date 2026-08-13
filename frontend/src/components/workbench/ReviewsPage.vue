<template>
  <div class="page-container" id="page-reviews">
    <div class="mint-hero mint-glass">
      <div>
        <h1 class="font-cal mint-hero-title">审核中心</h1>
        <p class="mint-hero-sub">处理待审核内容，确保发布质量</p>
      </div>
      <div class="mint-hero-stats">
        <div class="mint-stat">
          <div class="mint-stat-num" style="color:#F59E0B;">3</div>
          <div class="mint-stat-label">待审核</div>
        </div>
        <div class="mint-stat">
          <div class="mint-stat-num">12</div>
          <div class="mint-stat-label">今日已审</div>
        </div>
      </div>
    </div>

    <div class="mint-workflow-cards mint-workflow-cards-bento bento-grid bento-grid-3 overflow-y-auto">
      <div class="mint-wf-card bento-col-2">
        <div class="mint-wf-header">
          <div class="mint-wf-title-row">
            <div class="mint-wf-step" style="background:#F59E0B;">审</div>
            <div>
              <div class="mint-wf-title">文案审核 #001</div>
              <div class="mint-wf-desc">工作流: 夏日穿搭攻略 · 编辑撰写节点</div>
            </div>
          </div>
          <span class="mint-badge badge-cream">
            <span class="mint-status-dot" style="background:#F59E0B;"></span>
            待审核
          </span>
        </div>
        <div style="padding:12px 0;">
          <div style="font-size:14px; font-weight:600; color:#111827; margin-bottom:8px;">夏日清凉穿搭 | 这5件单品让你美翻整个夏天</div>
          <div style="font-size: 15px; color:#6B7280; line-height:1.6;">姐妹们！夏天来了，衣橱该换季啦～今天分享5件让我疯狂心动的清凉单品，每一件都是反复回购的真爱！</div>
        </div>
        <div class="mint-wf-footer">
          <button class="mint-btn mint-btn-outline" style="color:#EF4444; border-color:#FECACA;">
            <i data-lucide="x" style="width:16px;height:16px;"></i>
            打回
          </button>
          <button class="mint-btn mint-btn-ghost">
            <i data-lucide="refresh-cw" style="width:16px;height:16px;"></i>
            重新生成
          </button>
          <button class="mint-btn mint-btn-primary">
            <i data-lucide="check" style="width:16px;height:16px;"></i>
            通过
          </button>
        </div>
      </div>

      <div class="mint-wf-card">
        <div class="mint-wf-header">
          <div class="mint-wf-title-row">
            <div class="mint-wf-step" style="background:#F59E0B;">审</div>
            <div>
              <div class="mint-wf-title">图片审核 #002</div>
              <div class="mint-wf-desc">工作流: 夏日穿搭攻略 · 图片生成节点</div>
            </div>
          </div>
          <span class="mint-badge badge-cream">
            <span class="mint-status-dot" style="background:#F59E0B;"></span>
            待审核
          </span>
        </div>
        <div class="mint-img-grid" style="grid-template-columns: repeat(2, 1fr);">
          <div class="mint-img-thumb">
            <img src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7" alt="生成图片1">
            <div class="mint-img-overlay">风格 · 清新自然</div>
          </div>
          <div class="mint-img-thumb">
            <img src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7" alt="生成图片2">
            <div class="mint-img-overlay">风格 · 日系胶片</div>
          </div>
        </div>
        <div class="mint-wf-footer">
          <button class="mint-btn mint-btn-outline" style="color:#EF4444; border-color:#FECACA;">
            <i data-lucide="x" style="width:16px;height:16px;"></i>
            打回
          </button>
          <button class="mint-btn mint-btn-ghost">
            <i data-lucide="refresh-cw" style="width:16px;height:16px;"></i>
            重新生成
          </button>
          <button class="mint-btn mint-btn-primary">
            <i data-lucide="check" style="width:16px;height:16px;"></i>
            通过
          </button>
        </div>
      </div>

      <div class="mint-wf-card">
        <div class="mint-wf-header">
          <div class="mint-wf-title-row">
            <div class="mint-wf-step" style="background:#F59E0B;">审</div>
            <div>
              <div class="mint-wf-title">终审 #003</div>
              <div class="mint-wf-desc">工作流: 夏日穿搭攻略 · 终审发布节点</div>
            </div>
          </div>
          <span class="mint-badge badge-cream">
            <span class="mint-status-dot" style="background:#F59E0B;"></span>
            待审核
          </span>
        </div>
        <div class="mint-checklist">
          <div class="mint-check-item">
            <div class="mint-check-icon" style="background:#D1FAE5;">
              <i data-lucide="check" style="width:12px; height:12px; color:#059669;"></i>
            </div>
            <span>平台合规检查 — 通过</span>
          </div>
          <div class="mint-check-item">
            <div class="mint-check-icon" style="background:#D1FAE5;">
              <i data-lucide="check" style="width:12px; height:12px; color:#059669;"></i>
            </div>
            <span>内容质量评分 — 92分</span>
          </div>
        </div>
        <div class="mint-wf-footer">
          <button class="mint-btn mint-btn-outline" style="color:#EF4444; border-color:#FECACA;">
            <i data-lucide="x" style="width:16px;height:16px;"></i>
            打回
          </button>
          <button class="mint-btn mint-btn-outline">
            <i data-lucide="eye" style="width:16px;height:16px;"></i>
            预览
          </button>
          <button class="mint-btn mint-btn-primary">
            <i data-lucide="check" style="width:16px;height:16px;"></i>
            通过并发布
          </button>
        </div>
      </div>
    </div>
  </div>
</template>