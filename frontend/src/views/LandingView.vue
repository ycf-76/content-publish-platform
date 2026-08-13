<template>
  <div class="landing-page">
    <header class="landing-header mint-glass">
      <div class="landing-header-content">
        <div class="landing-logo">
          <div class="landing-logo-icon">
            <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="m12 3-1.912 5.813a2 2 0 0 1-1.275 1.275L3 12l5.813 1.912a2 2 0 0 1 1.275 1.275L12 21l1.912-5.813a2 2 0 0 1 1.275-1.275L21 12l-5.813-1.912a2 2 0 0 1-1.275-1.275L12 3Z"/>
              <path d="M5 3v4"/>
              <path d="M19 17v4"/>
              <path d="M3 5h4"/>
              <path d="M17 19h4"/>
            </svg>
          </div>
          <span class="landing-logo-text">灵犀工坊</span>
        </div>
        
        <nav class="landing-nav">
          <a href="#features" class="landing-nav-link">功能特性</a>
          <a href="#pricing" class="landing-nav-link">定价方案</a>
          <a href="#cases" class="landing-nav-link">成功案例</a>
          <a href="#faq" class="landing-nav-link">常见问题</a>
        </nav>
        
        <div class="landing-header-actions">
          <button class="mint-btn mint-btn-ghost" @click="goToLogin">登录</button>
          <button class="mint-btn mint-btn-primary" @click="goToRegister">免费试用</button>
        </div>
      </div>
    </header>

    <section class="landing-hero">
      <div class="landing-hero-content">
        <div class="landing-hero-badge">
          <span class="mint-status-dot" style="background:#FF2442;"></span>
          小红书内容智能生产平台
        </div>
        
        <h1 class="landing-hero-title font-cal">
          让每一篇内容<br/>
          都成为爆款
        </h1>
        
        <p class="landing-hero-desc">
          灵犀工坊是专为小红书创作者打造的智能内容生产流水线。<br/>
          从热点捕捉、图片生成、文案撰写到终审发布，全流程AI辅助，效率提升10倍。
        </p>
        
        <div class="landing-hero-actions">
          <button class="landing-hero-cta mint-btn mint-btn-primary" @click="goToRegister">
            <i data-lucide="rocket" style="width:18px;height:18px;"></i>
            开始免费试用
          </button>
          <button class="landing-hero-demo mint-btn mint-btn-outline">
            <i data-lucide="play-circle" style="width:18px;height:18px;"></i>
            观看演示视频
          </button>
        </div>
        
        <div class="landing-hero-stats">
          <div class="landing-stat">
            <div class="landing-stat-num">10,000+</div>
            <div class="landing-stat-label">创作者使用</div>
          </div>
          <div class="landing-stat-divider"></div>
          <div class="landing-stat">
            <div class="landing-stat-num">500万+</div>
            <div class="landing-stat-label">内容产出</div>
          </div>
          <div class="landing-stat-divider"></div>
          <div class="landing-stat">
            <div class="landing-stat-num">92%</div>
            <div class="landing-stat-label">爆款率提升</div>
          </div>
        </div>
      </div>
      
      <div class="landing-hero-visual">
        <div class="landing-hero-card mint-glass">
          <div class="landing-hero-card-header">
            <div class="landing-hero-card-icon">
              <i data-lucide="sparkles"></i>
            </div>
            <span>实时热点追踪</span>
          </div>
          <div class="landing-hero-card-body">
            <div class="landing-hero-trend">
              <span class="landing-hero-trend-keyword">#夏日穿搭</span>
              <span class="mint-badge badge-mint">12.3w 搜索</span>
            </div>
            <div class="landing-hero-trend">
              <span class="landing-hero-trend-keyword">#好物推荐</span>
              <span class="mint-badge badge-cream">8.7w 搜索</span>
            </div>
            <div class="landing-hero-trend">
              <span class="landing-hero-trend-keyword">#生活美学</span>
              <span class="mint-badge badge-laven">6.2w 搜索</span>
            </div>
          </div>
        </div>
      </div>
    </section>

    <section id="features" class="landing-features">
      <div class="landing-section-header">
        <h2 class="landing-section-title font-cal">四大核心能力</h2>
        <p class="landing-section-desc">从选题到发布，全流程AI赋能，让创作更高效</p>
      </div>
      
      <div class="landing-features-grid bento-grid bento-grid-4">
        <div class="landing-feature-card mint-glass bento-col-2 bento-row-2">
          <div class="landing-feature-icon" style="background: linear-gradient(135deg, #FF2442, #FF2442);">
            <i data-lucide="search"></i>
          </div>
          <h3 class="landing-feature-title">智能热点捕捉</h3>
          <p class="landing-feature-desc">
            实时追踪小红书热门话题，AI分析趋势走向，推荐高潜力选题，让你的内容始终踩在流量风口。
          </p>
          <ul class="landing-feature-list">
            <li><i data-lucide="check-circle-2"></i> 实时热点追踪</li>
            <li><i data-lucide="check-circle-2"></i> 竞争度分析</li>
            <li><i data-lucide="check-circle-2"></i> 选题推荐</li>
          </ul>
        </div>

        <div class="landing-feature-card mint-glass">
          <div class="landing-feature-icon" style="background: linear-gradient(135deg, #F59E0B, #EF4444);">
            <i data-lucide="image"></i>
          </div>
          <h3 class="landing-feature-title">AI 图片生成</h3>
          <p class="landing-feature-desc">
            基于最新AI绘图模型，一键生成符合小红书风格的精美配图，支持多种风格切换，省时又省心。
          </p>
          <ul class="landing-feature-list">
            <li><i data-lucide="check-circle-2"></i> 多风格模板</li>
            <li><i data-lucide="check-circle-2"></i> 批量生成</li>
            <li><i data-lucide="check-circle-2"></i> 智能裁剪</li>
          </ul>
        </div>

        <div class="landing-feature-card mint-glass">
          <div class="landing-feature-icon" style="background: linear-gradient(135deg, #FF2442, #FF2442);">
            <i data-lucide="pen-line"></i>
          </div>
          <h3 class="landing-feature-title">智能文案撰写</h3>
          <p class="landing-feature-desc">
            深度学习小红书爆款文案，自动生成标题、正文、标签，支持多种语气风格，让每一篇都充满吸引力。
          </p>
          <ul class="landing-feature-list">
            <li><i data-lucide="check-circle-2"></i> 多版本对比</li>
            <li><i data-lucide="check-circle-2"></i> 风格定制</li>
            <li><i data-lucide="check-circle-2"></i> 标签优化</li>
          </ul>
        </div>

        <div class="landing-feature-card mint-glass bento-col-2">
          <div class="landing-feature-icon" style="background: linear-gradient(135deg, #EC4899, #F43F5E);">
            <i data-lucide="send"></i>
          </div>
          <h3 class="landing-feature-title">智能终审发布</h3>
          <p class="landing-feature-desc">
            内置合规检查、敏感词过滤、质量评分，人工终审后一键发布，确保内容安全又优质。
          </p>
          <ul class="landing-feature-list">
            <li><i data-lucide="check-circle-2"></i> 合规检查</li>
            <li><i data-lucide="check-circle-2"></i> 质量评分</li>
            <li><i data-lucide="check-circle-2"></i> 定时发布</li>
          </ul>
        </div>
      </div>
    </section>

    <section class="landing-workflow">
      <div class="landing-section-header">
        <h2 class="landing-section-title font-cal">工作流全览</h2>
        <p class="landing-section-desc">四大节点无缝衔接，从选题到发布一气呵成</p>
      </div>
      
      <div class="landing-workflow-canvas">
        <div class="landing-workflow-node">
          <div class="landing-workflow-node-icon">
            <i data-lucide="search"></i>
          </div>
          <div class="landing-workflow-node-content">
            <h4>搜索热点</h4>
            <p>实时抓取热门话题</p>
          </div>
        </div>
        
        <div class="landing-workflow-arrow">
          <i data-lucide="arrow-right"></i>
        </div>
        
        <div class="landing-workflow-node">
          <div class="landing-workflow-node-icon">
            <i data-lucide="image"></i>
          </div>
          <div class="landing-workflow-node-content">
            <h4>图片生成</h4>
            <p>AI自动生成配图</p>
          </div>
        </div>
        
        <div class="landing-workflow-arrow">
          <i data-lucide="arrow-right"></i>
        </div>
        
        <div class="landing-workflow-node">
          <div class="landing-workflow-node-icon">
            <i data-lucide="pen-line"></i>
          </div>
          <div class="landing-workflow-node-content">
            <h4>编辑撰写</h4>
            <p>智能生成文案</p>
          </div>
        </div>
        
        <div class="landing-workflow-arrow">
          <i data-lucide="arrow-right"></i>
        </div>
        
        <div class="landing-workflow-node">
          <div class="landing-workflow-node-icon">
            <i data-lucide="send"></i>
          </div>
          <div class="landing-workflow-node-content">
            <h4>终审发布</h4>
            <p>一键发布上线</p>
          </div>
        </div>
      </div>
    </section>

    <section id="pricing" class="landing-pricing">
      <div class="landing-section-header">
        <h2 class="landing-section-title font-cal">选择适合你的方案</h2>
        <p class="landing-section-desc">灵活定价，按需选择，随时升级</p>
      </div>
      
      <div class="landing-pricing-grid bento-grid bento-grid-4">
        <div class="landing-pricing-card mint-glass">
          <div class="landing-pricing-header">
            <h3 class="landing-pricing-name">体验版</h3>
            <p class="landing-pricing-desc">适合个人创作者尝鲜</p>
          </div>
          <div class="landing-pricing-price">
            <span class="landing-pricing-currency">¥</span>
            <span class="landing-pricing-amount">0</span>
            <span class="landing-pricing-period">/月</span>
          </div>
          <ul class="landing-pricing-features">
            <li><i data-lucide="check"></i> 每月10次工作流执行</li>
            <li><i data-lucide="check"></i> 基础热点追踪</li>
            <li><i data-lucide="check"></i> 标准图片生成</li>
            <li><i data-lucide="check"></i> 基础文案生成</li>
            <li class="landing-pricing-feature-disabled"><i data-lucide="x"></i> 批量操作</li>
            <li class="landing-pricing-feature-disabled"><i data-lucide="x"></i> 定时发布</li>
          </ul>
          <button class="mint-btn mint-btn-outline landing-pricing-cta" @click="goToRegister">
            免费开始
          </button>
        </div>

        <div class="landing-pricing-card mint-glass landing-pricing-card-popular bento-col-2 bento-row-2">
          <div class="landing-pricing-badge">最受欢迎</div>
          <div class="landing-pricing-header">
            <h3 class="landing-pricing-name">专业版</h3>
            <p class="landing-pricing-desc">适合全职创作者</p>
          </div>
          <div class="landing-pricing-price">
            <span class="landing-pricing-currency">¥</span>
            <span class="landing-pricing-amount">299</span>
            <span class="landing-pricing-period">/月</span>
          </div>
          <ul class="landing-pricing-features">
            <li><i data-lucide="check"></i> 每月100次工作流执行</li>
            <li><i data-lucide="check"></i> 高级热点分析</li>
            <li><i data-lucide="check"></i> 高清图片生成</li>
            <li><i data-lucide="check"></i> 多风格文案</li>
            <li><i data-lucide="check"></i> 批量操作</li>
            <li><i data-lucide="check"></i> 定时发布</li>
          </ul>
          <button class="mint-btn mint-btn-primary landing-pricing-cta" @click="goToRegister">
            立即订阅
          </button>
        </div>

        <div class="landing-pricing-card mint-glass">
          <div class="landing-pricing-header">
            <h3 class="landing-pricing-name">团队版</h3>
            <p class="landing-pricing-desc">适合MCN机构和团队</p>
          </div>
          <div class="landing-pricing-price">
            <span class="landing-pricing-currency">¥</span>
            <span class="landing-pricing-amount">999</span>
            <span class="landing-pricing-period">/月</span>
          </div>
          <ul class="landing-pricing-features">
            <li><i data-lucide="check"></i> 无限工作流执行</li>
            <li><i data-lucide="check"></i> 全部热点功能</li>
            <li><i data-lucide="check"></i> 4K图片生成</li>
            <li><i data-lucide="check"></i> 团队协作</li>
            <li><i data-lucide="check"></i> 数据分析</li>
            <li><i data-lucide="check"></i> 专属客服</li>
          </ul>
          <button class="mint-btn mint-btn-outline landing-pricing-cta" @click="goToRegister">
            联系销售
          </button>
        </div>
      </div>
    </section>

    <section id="cases" class="landing-cases">
      <div class="landing-section-header">
        <h2 class="landing-section-title font-cal">他们都在用灵犀工坊</h2>
        <p class="landing-section-desc">来自真实用户的反馈和成果</p>
      </div>
      
      <div class="landing-cases-grid bento-grid bento-grid-3">
        <div class="landing-case-card mint-glass bento-col-2">
          <div class="landing-case-header">
            <div class="landing-case-avatar" style="background: linear-gradient(135deg, #FF2442, #FF2442);">王</div>
            <div>
              <div class="landing-case-name">王美琪</div>
              <div class="landing-case-title">生活美学 · 15.2w粉丝</div>
            </div>
          </div>
          <p class="landing-case-content">
            "作为MCN机构运营，灵犀工坊帮我们团队节省了大量人力成本。现在10个人的工作量，3个人就能完成。"
          </p>
          <div class="landing-case-stats">
            <div>
              <div class="landing-case-stat-num">70%</div>
              <div class="landing-case-stat-label">成本节省</div>
            </div>
            <div>
              <div class="landing-case-stat-num">2000+</div>
              <div class="landing-case-stat-label">月产出内容</div>
            </div>
          </div>
        </div>

        <div class="landing-case-card mint-glass">
          <div class="landing-case-header">
            <div class="landing-case-avatar">林</div>
            <div>
              <div class="landing-case-name">林知夏</div>
              <div class="landing-case-title">穿搭博主 · 12.8w粉丝</div>
            </div>
          </div>
          <p class="landing-case-content">
            "用了灵犀工坊后，我的内容产出效率提升了3倍！以前一天只能发1篇，现在轻松发3篇，而且爆款率从15%提升到了40%。"
          </p>
          <div class="landing-case-stats">
            <div>
              <div class="landing-case-stat-num">3倍</div>
              <div class="landing-case-stat-label">效率提升</div>
            </div>
            <div>
              <div class="landing-case-stat-num">40%</div>
              <div class="landing-case-stat-label">爆款率</div>
            </div>
          </div>
        </div>

        <div class="landing-case-card mint-glass">
          <div class="landing-case-header">
            <div class="landing-case-avatar" style="background: linear-gradient(135deg, #F59E0B, #EF4444);">陈</div>
            <div>
              <div class="landing-case-name">陈思远</div>
              <div class="landing-case-title">好物分享 · 8.5w粉丝</div>
            </div>
          </div>
          <p class="landing-case-content">
            "AI生成的图片和文案质量超出预期！特别是文案风格，完全符合小红书的调性，粉丝互动率提升了60%。"
          </p>
          <div class="landing-case-stats">
            <div>
              <div class="landing-case-stat-num">60%</div>
              <div class="landing-case-stat-label">互动率提升</div>
            </div>
            <div>
              <div class="landing-case-stat-num">500+</div>
              <div class="landing-case-stat-label">月产出内容</div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <section id="faq" class="landing-faq">
      <div class="landing-section-header">
        <h2 class="landing-section-title font-cal">常见问题</h2>
        <p class="landing-section-desc">关于灵犀工坊，你可能想知道的</p>
      </div>
      
      <div class="landing-faq-list">
        <div class="landing-faq-item mint-glass" :class="{ 'landing-faq-item-active': activeFaq === 0 }" @click="toggleFaq(0)">
          <div class="landing-faq-question">
            <span>灵犀工坊适合哪些人使用？</span>
            <i :data-lucide="activeFaq === 0 ? 'minus' : 'plus'"></i>
          </div>
          <div class="landing-faq-answer" v-show="activeFaq === 0">
            灵犀工坊适合所有小红书创作者，包括个人博主、MCN机构、品牌方运营团队。无论你是刚起步的新人，还是粉丝百万的大V，都能找到适合的使用场景。
          </div>
        </div>
        
        <div class="landing-faq-item mint-glass" :class="{ 'landing-faq-item-active': activeFaq === 1 }" @click="toggleFaq(1)">
          <div class="landing-faq-question">
            <span>AI生成的内容会被平台判定为违规吗？</span>
            <i :data-lucide="activeFaq === 1 ? 'minus' : 'plus'"></i>
          </div>
          <div class="landing-faq-answer" v-show="activeFaq === 1">
            不会。灵犀工坊内置了小红书平台合规检查，所有生成内容都会经过敏感词过滤和合规审核。同时，我们建议用户在终审环节进行人工把关，确保内容100%安全。
          </div>
        </div>
        
        <div class="landing-faq-item mint-glass" :class="{ 'landing-faq-item-active': activeFaq === 2 }" @click="toggleFaq(2)">
          <div class="landing-faq-question">
            <span>支持哪些AI模型？</span>
            <i :data-lucide="activeFaq === 2 ? 'minus' : 'plus'"></i>
          </div>
          <div class="landing-faq-answer" v-show="activeFaq === 2">
            我们支持主流AI模型，包括GPT-4o、Claude 3.5 Sonnet、通义千问、DeepSeek等文本模型，以及FLUX.1 Pro、Stable Diffusion 3、Midjourney等图片模型。用户可以根据需求自由选择。
          </div>
        </div>
        
        <div class="landing-faq-item mint-glass" :class="{ 'landing-faq-item-active': activeFaq === 3 }" @click="toggleFaq(3)">
          <div class="landing-faq-question">
            <span>如何保护我的账号安全？</span>
            <i :data-lucide="activeFaq === 3 ? 'minus' : 'plus'"></i>
          </div>
          <div class="landing-faq-answer" v-show="activeFaq === 3">
            我们采用企业级安全标准，所有数据传输加密存储，小红书账号信息采用独立加密通道。同时，我们承诺不会在未经授权的情况下操作您的账号，所有发布操作都需要您最终确认。
          </div>
        </div>
      </div>
    </section>

    <section class="landing-cta">
      <div class="landing-cta-content mint-glass">
        <h2 class="landing-cta-title font-cal">准备好提升你的内容生产力了吗？</h2>
        <p class="landing-cta-desc">立即注册，免费体验灵犀工坊的强大功能</p>
        <div class="landing-cta-actions">
          <button class="mint-btn mint-btn-primary landing-cta-btn" @click="goToRegister">
            <i data-lucide="rocket" style="width:18px;height:18px;"></i>
            免费开始使用
          </button>
          <button class="mint-btn mint-btn-outline landing-cta-btn">
            <i data-lucide="message-circle" style="width:18px;height:18px;"></i>
            联系我们
          </button>
        </div>
      </div>
    </section>

    <footer class="landing-footer">
      <div class="landing-footer-content">
        <div class="landing-footer-brand">
          <div class="landing-logo">
            <div class="landing-logo-icon">
              <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="m12 3-1.912 5.813a2 2 0 0 1-1.275 1.275L3 12l5.813 1.912a2 2 0 0 1 1.275 1.275L12 21l1.912-5.813a2 2 0 0 1 1.275-1.275L21 12l-5.813-1.912a2 2 0 0 1-1.275-1.275L12 3Z"/>
                <path d="M5 3v4"/>
                <path d="M19 17v4"/>
                <path d="M3 5h4"/>
                <path d="M17 19h4"/>
              </svg>
            </div>
            <span class="landing-logo-text">灵犀工坊</span>
          </div>
          <p class="landing-footer-desc">让每一篇内容都成为爆款</p>
        </div>
        
        <div class="landing-footer-links">
          <div class="landing-footer-column">
            <h4>产品</h4>
            <a href="#features">功能特性</a>
            <a href="#pricing">定价方案</a>
            <a href="#cases">成功案例</a>
          </div>
          <div class="landing-footer-column">
            <h4>资源</h4>
            <a href="#">帮助中心</a>
            <a href="#">API文档</a>
            <a href="#">博客</a>
          </div>
          <div class="landing-footer-column">
            <h4>公司</h4>
            <a href="#">关于我们</a>
            <a href="#">加入我们</a>
            <a href="#">联系我们</a>
          </div>
        </div>
      </div>
      
      <div class="landing-footer-bottom">
        <p>© 2026 灵犀工坊. All rights reserved.</p>
        <div class="landing-footer-legal">
          <a href="#">隐私政策</a>
          <a href="#">服务条款</a>
        </div>
      </div>
    </footer>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { createIcons, icons } from 'lucide'

const router = useRouter()
const activeFaq = ref<number | null>(null)

function goToLogin() {
  router.push('/login')
}

function goToRegister() {
  router.push('/login?register=true')
}

function toggleFaq(index: number) {
  if (activeFaq.value === index) {
    activeFaq.value = null
  } else {
    activeFaq.value = index
  }
  
  setTimeout(() => {
    try {
      createIcons({ icons })
    } catch (e) {
      console.warn('lucide createIcons warning:', e)
    }
  }, 0)
}

onMounted(() => {
  try {
    createIcons({ icons })
  } catch (e) {
    console.warn('lucide createIcons warning:', e)
  }
})
</script>

<style scoped>
.landing-page {
  min-height: 100vh;
  background: linear-gradient(135deg, #F0FDF4 0%, #ECFDF5 100%);
}

.landing-header {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 100;
  padding: 16px 40px;
  border-bottom: 1px solid rgba(16, 185, 129, 0.1);
}

.landing-header-content {
  max-width: 1400px;
  margin: 0 auto;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.landing-logo {
  display: flex;
  align-items: center;
  gap: 12px;
}

.landing-logo-icon {
  width: 40px;
  height: 40px;
  border-radius: 12px;
  background: var(--mint-gradient-3d, linear-gradient(135deg, #ECFDF5 0%, #A7F3D0 22%, #6EE7B7 50%, #34D399 78%, #059669 100%));
  box-shadow:
    0 1px 2px rgba(5,150,105,0.18),
    0 3px 7px rgba(16,185,129,0.22),
    0 6px 14px rgba(16,185,129,0.12),
    inset 0 1.5px 1px rgba(255,255,255,0.7),
    inset 0 -2px 3px rgba(6,95,70,0.28),
    inset 0 0 0 0.5px rgba(255,255,255,0.35);
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1), box-shadow 0.3s ease;
}
.landing-logo:hover .landing-logo-icon {
  transform: translateY(-1px) scale(1.03);
  box-shadow:
    0 2px 4px rgba(5,150,105,0.22),
    0 5px 10px rgba(16,185,129,0.28),
    0 10px 20px rgba(16,185,129,0.18),
    inset 0 1.5px 1px rgba(255,255,255,0.8),
    inset 0 -2px 3px rgba(6,95,70,0.3),
    inset 0 0 0 0.5px rgba(255,255,255,0.4);
}
.landing-logo-icon svg { filter: drop-shadow(0 1px 1px rgba(6,95,70,0.35)); }

.landing-logo-text {
  font-family: 'LXGW WenKai', 'PingFang SC', cursive;
  font-size: 20px;
  font-weight: 700;
  color: #111827;
  letter-spacing: 1px;
}

.landing-nav {
  display: flex;
  gap: 32px;
}

.landing-nav-link {
  font-size: 15px;
  color: #374151;
  text-decoration: none;
  transition: color 0.2s;
}

.landing-nav-link:hover {
  color: #FF2442;
}

.landing-header-actions {
  display: flex;
  gap: 12px;
}

.landing-hero {
  max-width: 1400px;
  margin: 0 auto;
  padding: 140px 40px 80px;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 60px;
  align-items: center;
}

.landing-hero-badge {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  background: rgba(16, 185, 129, 0.1);
  border-radius: 9999px;
  font-size: 14px;
  color: #FF2442;
  margin-bottom: 24px;
}

.landing-hero-title {
  font-size: 64px;
  line-height: 1.1;
  color: #111827;
  margin-bottom: 24px;
}

.landing-hero-desc {
  font-size: 18px;
  color: #6B7280;
  line-height: 1.6;
  margin-bottom: 32px;
}

.landing-hero-actions {
  display: flex;
  gap: 16px;
  margin-bottom: 48px;
}

.landing-hero-cta,
.landing-hero-demo {
  padding: 14px 28px;
  font-size: 16px;
}

.landing-hero-stats {
  display: flex;
  align-items: center;
  gap: 32px;
}

.landing-stat {
  text-align: center;
}

.landing-stat-num {
  font-size: 32px;
  font-weight: 700;
  color: #FF2442;
}

.landing-stat-label {
  font-size: 14px;
  color: #6B7280;
  margin-top: 4px;
}

.landing-stat-divider {
  width: 1px;
  height: 40px;
  background: rgba(16, 185, 129, 0.2);
}

.landing-hero-visual {
  display: flex;
  justify-content: center;
}

.landing-hero-card {
  width: 100%;
  max-width: 420px;
  padding: 24px;
  border-radius: 16px;
}

.landing-hero-card-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 20px;
  font-size: 16px;
  font-weight: 600;
  color: #FF2442;
}

.landing-hero-card-icon {
  width: 40px;
  height: 40px;
  border-radius: 12px;
  background: var(--mint-gradient);
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
}

.landing-hero-card-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.landing-hero-trend {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  background: rgba(255, 255, 255, 0.5);
  border-radius: 12px;
}

.landing-hero-trend-keyword {
  font-size: 15px;
  font-weight: 600;
  color: #111827;
}

.landing-section-header {
  text-align: center;
  margin-bottom: 60px;
}

.landing-section-title {
  font-size: 48px;
  color: #111827;
  margin-bottom: 12px;
}

.landing-section-desc {
  font-size: 18px;
  color: #6B7280;
}

.landing-features {
  max-width: 1400px;
  margin: 0 auto;
  padding: 80px 40px;
}

.landing-features-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 24px;
}

.landing-feature-card {
  padding: 32px;
  border-radius: 16px;
  transition: all 0.3s;
}

.landing-feature-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 12px 40px rgba(255, 36, 66, 0.15);
}

.landing-feature-icon {
  width: 56px;
  height: 56px;
  border-radius: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  margin-bottom: 20px;
}

.landing-feature-title {
  font-size: 22px;
  font-weight: 600;
  color: #111827;
  margin-bottom: 12px;
}

.landing-feature-desc {
  font-size: 15px;
  color: #6B7280;
  line-height: 1.6;
  margin-bottom: 20px;
}

.landing-feature-list {
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.landing-feature-list li {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 14px;
  color: #374151;
}

.landing-feature-list li i {
  width: 18px;
  height: 18px;
  color: #FF2442;
}

.landing-workflow {
  max-width: 1400px;
  margin: 0 auto;
  padding: 80px 40px;
  background: rgba(255, 255, 255, 0.3);
}

.landing-workflow-canvas {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 24px;
  flex-wrap: wrap;
}

.landing-workflow-node {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 20px 24px;
  background: rgba(255, 255, 255, 0.8);
  border: 2px solid rgba(16, 185, 129, 0.2);
  border-radius: 12px;
  transition: all 0.3s;
}

.landing-workflow-node:hover {
  border-color: #FF2442;
  box-shadow: 0 4px 20px rgba(255, 36, 66, 0.2);
}

.landing-workflow-node-icon {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  background: var(--mint-gradient);
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
}

.landing-workflow-node-content h4 {
  font-size: 16px;
  font-weight: 600;
  color: #111827;
  margin-bottom: 4px;
}

.landing-workflow-node-content p {
  font-size: 13px;
  color: #6B7280;
}

.landing-workflow-arrow {
  color: #FF2442;
}

.landing-pricing {
  max-width: 1400px;
  margin: 0 auto;
  padding: 80px 40px;
}

.landing-pricing-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 24px;
}

.landing-pricing-card {
  padding: 32px;
  border-radius: 16px;
  position: relative;
  transition: all 0.3s;
}

.landing-pricing-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 12px 40px rgba(255, 36, 66, 0.15);
}

.landing-pricing-card-popular {
  border: 2px solid #FF2442;
}

.landing-pricing-badge {
  position: absolute;
  top: -12px;
  left: 50%;
  transform: translateX(-50%);
  padding: 6px 16px;
  background: linear-gradient(135deg, #FF2442 0%, #FF2442 100%);
  color: #fff;
  font-size: 12px;
  font-weight: 600;
  border-radius: 9999px;
}

.landing-pricing-header {
  text-align: center;
  margin-bottom: 24px;
}

.landing-pricing-name {
  font-size: 24px;
  font-weight: 600;
  color: #111827;
  margin-bottom: 8px;
}

.landing-pricing-desc {
  font-size: 14px;
  color: #6B7280;
}

.landing-pricing-price {
  text-align: center;
  margin-bottom: 32px;
}

.landing-pricing-currency {
  font-size: 24px;
  font-weight: 600;
  color: #FF2442;
}

.landing-pricing-amount {
  font-size: 48px;
  font-weight: 700;
  color: #FF2442;
}

.landing-pricing-period {
  font-size: 16px;
  color: #6B7280;
}

.landing-pricing-features {
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 32px;
}

.landing-pricing-features li {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 14px;
  color: #374151;
}

.landing-pricing-features li i {
  width: 18px;
  height: 18px;
  color: #FF2442;
}

.landing-pricing-feature-disabled {
  color: #9CA3AF !important;
}

.landing-pricing-feature-disabled i {
  color: #9CA3AF !important;
}

.landing-pricing-cta {
  width: 100%;
  justify-content: center;
  padding: 12px;
}

.landing-cases {
  max-width: 1400px;
  margin: 0 auto;
  padding: 80px 40px;
}

.landing-cases-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 24px;
}

.landing-case-card {
  padding: 28px;
  border-radius: 16px;
}

.landing-case-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}

.landing-case-avatar {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  background: linear-gradient(135deg, #FF2442, #FF6B6B);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  font-weight: 600;
}

.landing-case-name {
  font-size: 16px;
  font-weight: 600;
  color: #111827;
}

.landing-case-title {
  font-size: 13px;
  color: #6B7280;
}

.landing-case-content {
  font-size: 15px;
  color: #374151;
  line-height: 1.6;
  margin-bottom: 20px;
}

.landing-case-stats {
  display: flex;
  gap: 24px;
  padding-top: 16px;
  border-top: 1px solid rgba(16, 185, 129, 0.1);
}

.landing-case-stat-num {
  font-size: 20px;
  font-weight: 700;
  color: #FF2442;
}

.landing-case-stat-label {
  font-size: 12px;
  color: #6B7280;
}

.landing-faq {
  max-width: 800px;
  margin: 0 auto;
  padding: 80px 40px;
}

.landing-faq-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.landing-faq-item {
  padding: 20px 24px;
  border-radius: 12px;
  cursor: pointer;
  transition: all 0.2s;
}

.landing-faq-item:hover {
  background: rgba(255, 255, 255, 0.8);
}

.landing-faq-question {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 16px;
  font-weight: 600;
  color: #111827;
}

.landing-faq-question i {
  width: 20px;
  height: 20px;
  color: #FF2442;
}

.landing-faq-answer {
  margin-top: 16px;
  font-size: 15px;
  color: #6B7280;
  line-height: 1.6;
}

.landing-cta {
  max-width: 1400px;
  margin: 0 auto;
  padding: 80px 40px;
}

.landing-cta-content {
  padding: 60px;
  border-radius: 20px;
  text-align: center;
}

.landing-cta-title {
  font-size: 44px;
  color: #111827;
  margin-bottom: 12px;
}

.landing-cta-desc {
  font-size: 18px;
  color: #6B7280;
  margin-bottom: 32px;
}

.landing-cta-actions {
  display: flex;
  gap: 16px;
  justify-content: center;
}

.landing-cta-btn {
  padding: 14px 28px;
  font-size: 16px;
}

.landing-footer {
  background: rgba(255, 255, 255, 0.5);
  padding: 60px 40px 32px;
  border-top: 1px solid rgba(16, 185, 129, 0.1);
}

.landing-footer-content {
  max-width: 1400px;
  margin: 0 auto;
  display: flex;
  justify-content: space-between;
  margin-bottom: 40px;
}

.landing-footer-desc {
  font-size: 14px;
  color: #6B7280;
  margin-top: 12px;
}

.landing-footer-links {
  display: flex;
  gap: 80px;
}

.landing-footer-column h4 {
  font-size: 14px;
  font-weight: 600;
  color: #111827;
  margin-bottom: 16px;
}

.landing-footer-column a {
  display: block;
  font-size: 14px;
  color: #6B7280;
  text-decoration: none;
  margin-bottom: 12px;
  transition: color 0.2s;
}

.landing-footer-column a:hover {
  color: #FF2442;
}

.landing-footer-bottom {
  max-width: 1400px;
  margin: 0 auto;
  padding-top: 32px;
  border-top: 1px solid rgba(16, 185, 129, 0.1);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.landing-footer-bottom p {
  font-size: 13px;
  color: #6B7280;
}

.landing-footer-legal {
  display: flex;
  gap: 24px;
}

.landing-footer-legal a {
  font-size: 13px;
  color: #6B7280;
  text-decoration: none;
  transition: color 0.2s;
}

.landing-footer-legal a:hover {
  color: #FF2442;
}

@media (max-width: 1024px) {
  .landing-hero {
    grid-template-columns: 1fr;
    padding: 120px 20px 60px;
  }
  
  .landing-hero-visual {
    order: -1;
  }
  
  .landing-features-grid,
  .landing-pricing-grid,
  .landing-cases-grid {
    grid-template-columns: 1fr;
  }
  
  .landing-nav {
    display: none;
  }
}
</style>