<template>
  <div class="page-container" id="page-accounts">
    <div class="mint-hero mint-glass">
      <div>
        <h1 class="font-cal mint-hero-title">账号管理</h1>
        <p class="mint-hero-sub">管理小红书账号与发布权限</p>
      </div>
      <button class="mint-btn mint-btn-primary">
        <i data-lucide="plus" style="width:16px;height:16px;"></i>
        添加账号
      </button>
    </div>

    <div class="mint-workflow-cards overflow-y-auto">
      <div class="mint-wf-card">
        <div class="mint-wf-header">
          <div style="display:flex; align-items:center; gap:12px;">
            <div style="width:48px; height:48px; border-radius:12px; background: linear-gradient(135deg, #FF2442, #FF6B6B); display:flex; align-items:center; justify-content:center; color:#fff; font-size:20px; font-weight:700;">林</div>
            <div>
              <div class="mint-wf-title">林知夏的穿搭日记</div>
              <div class="mint-wf-desc">小红书账号 · 已绑定</div>
            </div>
          </div>
          <span class="mint-badge badge-mint">
            <span class="mint-status-dot" style="background:#FF2442;"></span>
            运行中
          </span>
        </div>
        <div style="display:grid; grid-template-columns: repeat(3, 1fr); gap:12px; padding:12px 0;">
          <div style="text-align:center; padding:12px; background:rgba(255,228,232,0.5); border-radius: 12px;">
            <div style="font-size:20px; font-weight:700; color:#FF2442;">12.8w</div>
            <div style="font-size: 14px; color:#6B7280;">粉丝数</div>
          </div>
          <div style="text-align:center; padding:12px; background:rgba(255,228,232,0.5); border-radius: 12px;">
            <div style="font-size:20px; font-weight:700; color:#FF2442;">347</div>
            <div style="font-size: 14px; color:#6B7280;">本月发布</div>
          </div>
          <div style="text-align:center; padding:12px; background:rgba(255,228,232,0.5); border-radius: 12px;">
            <div style="font-size:20px; font-weight:700; color:#FF2442;">8.7%</div>
            <div style="font-size: 14px; color:#6B7280;">互动率</div>
          </div>
        </div>
        <div class="mint-wf-footer">
          <button class="mint-btn mint-btn-outline"><i data-lucide="settings" style="width:16px;height:16px;"></i> 配置</button>
          <button class="mint-btn mint-btn-ghost"><i data-lucide="bar-chart-3" style="width:16px;height:16px;"></i> 数据</button>
          <button class="mint-btn mint-btn-outline" style="color:#EF4444; border-color:#FECACA;">解绑</button>
        </div>
      </div>

      <div class="mint-wf-card">
        <div class="mint-wf-header">
          <div style="display:flex; align-items:center; gap:12px;">
            <div style="width:48px; height:48px; border-radius:12px; background: linear-gradient(135deg, #FF2442, #FF2442); display:flex; align-items:center; justify-content:center; color:#fff; font-size:20px; font-weight:700;">夏</div>
            <div>
              <div class="mint-wf-title">夏日美食探店</div>
              <div class="mint-wf-desc">小红书账号 · 已绑定</div>
            </div>
          </div>
          <span class="mint-badge badge-cream">
            <span class="mint-status-dot" style="background:#D97706;"></span>
            待审核
          </span>
        </div>
        <div style="display:grid; grid-template-columns: repeat(3, 1fr); gap:12px; padding:12px 0;">
          <div style="text-align:center; padding:12px; background:rgba(255,228,232,0.5); border-radius: 12px;">
            <div style="font-size:20px; font-weight:700; color:#FF2442;">5.2w</div>
            <div style="font-size: 14px; color:#6B7280;">粉丝数</div>
          </div>
          <div style="text-align:center; padding:12px; background:rgba(255,228,232,0.5); border-radius: 12px;">
            <div style="font-size:20px; font-weight:700; color:#FF2442;">89</div>
            <div style="font-size: 14px; color:#6B7280;">本月发布</div>
          </div>
          <div style="text-align:center; padding:12px; background:rgba(255,228,232,0.5); border-radius: 12px;">
            <div style="font-size:20px; font-weight:700; color:#FF2442;">6.3%</div>
            <div style="font-size: 14px; color:#6B7280;">互动率</div>
          </div>
        </div>
        <div class="mint-wf-footer">
          <button class="mint-btn mint-btn-outline"><i data-lucide="settings" style="width:16px;height:16px;"></i> 配置</button>
          <button class="mint-btn mint-btn-ghost"><i data-lucide="bar-chart-3" style="width:16px;height:16px;"></i> 数据</button>
          <button class="mint-btn mint-btn-outline" style="color:#EF4444; border-color:#FECACA;">解绑</button>
        </div>
      </div>

      <div class="mint-wf-card" style="border: 2px dashed rgba(255,36,66,0.3); background: rgba(255,228,232,0.3); display:flex; align-items:center; justify-content:center; min-height:120px; cursor:pointer;" @click="addAccount">
        <div style="text-align:center; color:#FF2442;">
          <i data-lucide="plus-circle" style="width:32px; height:32px; margin-bottom:8px;"></i>
          <div style="font-size:14px; font-weight:500;">添加新的小红书账号</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
function addAccount() {
  alert('添加新账号')
}
</script>