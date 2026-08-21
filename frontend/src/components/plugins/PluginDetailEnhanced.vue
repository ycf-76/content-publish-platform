<template>
  <div class="detail-enhanced" @click.self="$emit('close')">
    <div class="de-container">
      <!-- 顶部Hero区域 -->
      <div class="de-hero" :style="{ background: getCategoryGradient(plugin.category) }">
        <div class="de-hero-content">
          <button @click="$emit('close')" class="de-close-btn">
            <i data-lucide="arrow-left"></i>
            返回市场
          </button>

          <div class="de-hero-main">
            <div class="de-icon-wrapper">
              <span class="de-plugin-icon">{{ plugin.display_icon || '📦' }}</span>
            </div>

            <div class="de-hero-info">
              <h1 class="de-title">{{ plugin.name }}</h1>
              <p class="de-subtitle">{{ plugin.description }}</p>

              <div class="de-meta-tags">
                <span v-if="plugin.is_builtin" class="de-tag de-tag-builtin">内置</span>
                <span class="de-tag de-tag-category">{{ getCategoryLabel(plugin.category) }}</span>
                <span class="de-tag" :class="`de-tag-price-${plugin.pricing_model}`">
                  {{ getPriceLabel(plugin.pricing_model) }}
                  <template v-if="(plugin.price_monthly ?? 0) > 0"> ¥{{ plugin.price_monthly }}/月</template>
                </span>
                <span class="de-tag de-tag-version">v{{ plugin.version }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 主内容区 -->
      <div class="de-body">
        <!-- 左侧主栏 -->
        <main class="de-main">
          <!-- 截图画廊 -->
          <section v-if="screenshots.length > 0" class="de-section">
            <h3 class="de-section-title">
              <i data-lucide="images"></i>
              插件截图
            </h3>
            <div class="de-screenshots">
              <div
                v-for="(shot, index) in screenshots"
                :key="index"
                class="de-screenshot"
                :class="{ active: currentScreenshot === index }"
                @click="currentScreenshot = index"
              >
                <img :src="shot.thumb" :alt="`截图 ${index + 1}`" />
              </div>
            </div>
          </section>

          <!-- 详细描述 -->
          <section class="de-section">
            <h3 class="de-section-title">
              <i data-lucide="file-text"></i>
              详细介绍
            </h3>
            <div class="de-description" v-html="formattedDescription"></div>
          </section>

          <!-- 功能特性列表 -->
          <section v-if="features.length > 0" class="de-section">
            <h3 class="de-section-title">
              <i data-lucide="check-circle"></i>
              核心功能
            </h3>
            <ul class="de-features">
              <li v-for="(feature, index) in features" :key="index" class="de-feature-item">
                <i data-lucide="check"></i>
                <span>{{ feature }}</span>
              </li>
            </ul>
          </section>

          <!-- 配置参数 -->
          <section v-if="hasConfigSchema" class="de-section">
            <h3 class="de-section-title">
              <i data-lucide="settings-2"></i>
              配置选项
            </h3>
            <div class="de-config-preview">
              <pre><code>{{ JSON.stringify(plugin.config_schema, null, 2) }}</code></pre>
            </div>
          </section>

          <!-- 版本更新日志 -->
          <section class="de-section">
            <h3 class="de-section-title">
              <i data-lucide="git-commit"></i>
              更新记录
            </h3>
            <div class="de-changelog">
              <div v-for="(log, index) in changelog" :key="index" class="de-changelog-item">
                <div class="de-log-header">
                  <span class="de-log-version">v{{ log.version }}</span>
                  <time class="de-log-date">{{ formatDate(log.date) }}</time>
                </div>
                <ul class="de-log-changes">
                  <li v-for="(change, idx) in log.changes" :key="idx">{{ change }}</li>
                </ul>
              </div>
            </div>
          </section>

          <!-- 评价区域 -->
          <section class="de-section">
            <div class="de-reviews-header">
              <h3 class="de-section-title">
                <i data-lucide="message-square"></i>
                用户评价 ({{ reviewPagination.total || plugin.stats?.review_count || 0 }})
              </h3>
              <div class="de-rating-summary">
                <div class="de-rating-big">
                  <span class="de-rating-number">{{ plugin.stats?.avg_rating?.toFixed(1) || '-' }}</span>
                  <div class="de-stars">
                    <i
                      v-for="star in 5"
                      :key="star"
                      data-lucide="star"
                      :class="{ filled: star <= Math.floor(plugin.stats?.avg_rating || 0) }"
                    ></i>
                  </div>
                </div>
              </div>
            </div>

            <!-- 操作栏：写评价 + 排序筛选 -->
            <div class="de-reviews-toolbar">
              <button 
                v-if="isInstalled && !hasReviewed" 
                @click="showReviewForm = true" 
                class="de-btn de-btn-primary de-btn-sm"
              >
                <i data-lucide="edit-3"></i>
                {{ myReview ? '编辑评价' : '写评价' }}
              </button>

              <div class="de-reviews-filters">
                <!-- 排序 -->
                <select 
                  v-model="reviewSortBy" 
                  @change="changeSortBy(reviewSortBy)"
                  class="de-select de-select-sm"
                >
                  <option value="newest">最新</option>
                  <option value="oldest">最早</option>
                  <option value="rating_high">高评分</option>
                  <option value="rating_low">低评分</option>
                  <option value="helpful">最有用</option>
                </select>

                <!-- 星级筛选 -->
                <select 
                  :value="reviewRatingFilter ?? ''"
                  @change="filterByRating(($event.target as HTMLSelectElement).value ? Number(($event.target as HTMLSelectElement).value) : null)"
                  class="de-select de-select-sm"
                >
                  <option value="">全部星级</option>
                  <option value="5">⭐ 5星</option>
                  <option value="4">⭐ 4星</option>
                  <option value="3">⭐ 3星</option>
                  <option value="2">⭐ 2星</option>
                  <option value="1">⭐ 1星</option>
                </select>
              </div>
            </div>

            <!-- 加载中状态 -->
            <div v-if="reviewLoading && reviews.length === 0" class="de-loading-state">
              <div class="de-spinner-small"></div>
              <p>正在加载评价...</p>
            </div>

            <!-- 评价列表 -->
            <div v-else class="de-reviews-list">
              <article v-for="review in reviews" :key="review.id" class="de-review-card">
                <div class="de-review-header">
                  <div class="de-reviewer-avatar">
                    {{ (review.user_id || 'U').charAt(0).toUpperCase() }}
                  </div>
                  <div class="de-reviewer-info">
                    <strong>用户{{ review.id.toString().slice(-4) }}</strong>
                    <div class="de-review-stars">
                      <i
                        v-for="star in 5"
                        :key="star"
                        data-lucide="star"
                        :class="{ filled: star <= review.rating }"
                      ></i>
                    </div>
                  </div>
                  <time class="de-review-date">{{ formatTimeAgo(review.created_at) }}</time>
                  
                  <!-- 已购买标识 -->
                  <span v-if="review.is_verified_purchase" class="de-verified-badge">
                    <i data-lucide="badge-check"></i>
                    已购买
                  </span>
                </div>

                <h4 v-if="review.title" class="de-review-title">{{ review.title }}</h4>
                <p class="de-review-content">{{ review.content }}</p>

                <div class="de-review-footer">
                  <button 
                    @click="handleMarkHelpful(review.id)" 
                    class="de-helpful-btn"
                  >
                    <i data-lucide="thumbs-up"></i>
                    有帮助 ({{ review.helpful_count }})
                  </button>
                </div>
              </article>

              <!-- 空状态 -->
              <div v-if="!reviewLoading && reviews.length === 0" class="de-empty-reviews">
                <i data-lucide="message-circle-off"></i>
                <p>暂无评价</p>
                <p class="de-empty-hint">成为第一个评价的用户吧！</p>
              </div>

              <!-- 加载更多 -->
              <div 
                v-if="!reviewLoading && reviews.length > 0 && reviewPagination.page < reviewPagination.total_pages" 
                class="de-load-more"
              >
                <button @click="loadMoreReviews" class="de-btn de-btn-outline de-btn-block">
                  加载更多评价 ({{ reviewPagination.total - reviews.length }})
                </button>
              </div>

              <!-- 加载更多时的loading -->
              <div v-if="reviewLoading && reviews.length > 0" class="de-loading-more">
                <div class="de-spinner-small"></div>
                <span>加载中...</span>
              </div>
            </div>
          </section>
        </main>

        <!-- 右侧边栏 -->
        <aside class="de-sidebar">
          <!-- 快速操作卡片 -->
          <div class="de-action-card">
            <!-- 价格和安装按钮 -->
            <div class="de-price-box" v-if="plugin.pricing_model !== 'free'">
              <div class="de-price-label">价格</div>
              <div class="de-price-value">
                <template v-if="(plugin.price_monthly ?? 0) > 0">
                  <span class="de-currency">¥</span>
                  <span class="de-amount">{{ plugin.price_monthly }}</span>
                  <span class="de-period">/月</span>
                </template>
                <template v-else>
                  <span class="de-free-text">免费使用</span>
                </template>
              </div>
            </div>

            <div class="de-action-buttons">
              <template v-if="!isInstalled">
                <button
                  @click="$emit('install')"
                  class="de-btn de-btn-primary de-btn-block"
                  :disabled="installing"
                >
                  <template v-if="!installing">
                    <i data-lucide="download"></i>
                    立即安装
                  </template>
                  <template v-else>
                    <div class="de-spinner-small"></div>
                    安装中...
                  </template>
                </button>
              </template>

              <template v-else>
                <button
                  @click="$emit('configure')"
                  class="de-btn de-btn-secondary de-btn-block"
                >
                  <i data-lucide="settings"></i>
                  配置插件
                </button>
                <button
                  @click="handleUninstall"
                  class="de-btn de-btn-danger-outline de-btn-block"
                >
                  <i data-lucide="trash-2"></i>
                  卸载
                </button>
              </template>
            </div>

            <!-- 收藏按钮 -->
            <button
              @click="toggleFavorite"
              class="de-favorite-btn"
              :class="{ active: isFavorite }"
            >
              <i :data-lucide="isFavorite ? 'heart' : 'heart'"></i>
              {{ isFavorite ? '已收藏' : '收藏' }}
            </button>
          </div>

          <!-- 统计信息卡片 -->
          <div class="de-stats-card">
            <h4 class="de-sidebar-title">统计数据</h4>
            <div class="de-stat-list">
              <div class="de-stat-row">
                <i data-lucide="download"></i>
                <span>下载量</span>
                <strong>{{ formatNumber(plugin.stats?.download_count) }}</strong>
              </div>
              <div class="de-stat-row">
                <i data-lucide="users"></i>
                <span>活跃用户</span>
                <strong>{{ formatNumber(plugin.stats?.active_users) }}</strong>
              </div>
              <div class="de-stat-row">
                <i data-lucide="clock"></i>
                <span>平均响应</span>
                <strong>{{ plugin.stats?.avg_execution_time_ms }}ms</strong>
              </div>
              <div class="de-stat-row">
                <i data-lucide="check-circle"></i>
                <span>成功率</span>
                <strong>{{ ((plugin.stats?.success_rate || 0) * 100).toFixed(1) }}%</strong>
              </div>
            </div>
          </div>

          <!-- 作者信息卡片 -->
          <div class="de-author-card">
            <h4 class="de-sidebar-title">开发者</h4>
            <div class="de-author-profile">
              <div class="de-author-avatar">
                {{ (plugin.author_name || '?').charAt(0).toUpperCase() }}
              </div>
              <div class="de-author-details">
                <p class="de-author-name">{{ plugin.author_name || '未知作者' }}</p>
                <p v-if="plugin.author_email" class="de-author-email">{{ plugin.author_email }}</p>
                <a href="#" class="de-view-more-link">查看更多作品 →</a>
              </div>
            </div>
          </div>

          <!-- 依赖关系 -->
          <div v-if="(plugin.dependencies?.length ?? 0) > 0" class="de-deps-card">
            <h4 class="de-sidebar-title">依赖项</h4>
            <ul class="de-deps-list">
              <li v-for="dep in plugin.dependencies" :key="dep" class="de-dep-item">
                <i data-lucide="package"></i>
                <code>{{ dep }}</code>
              </li>
            </ul>
          </div>

          <!-- 安全与权限 -->
          <div class="de-security-card">
            <h4 class="de-sidebar-title">安全信息</h4>
            <div class="de-security-item" v-if="plugin.permissions_required?.length === 0">
              <i data-lucide="shield-check" class="de-security-icon-safe"></i>
              <span>无需特殊权限</span>
            </div>
            <div v-else class="de-permissions-list">
              <div
                v-for="perm in plugin.permissions_required"
                :key="perm"
                class="de-permission-badge"
              >
                <i data-lucide="key"></i>
                {{ perm }}
              </div>
            </div>
            <div class="de-audit-info">
              <i data-lucide="badge-check"></i>
              <span>已通过平台安全审核</span>
            </div>
          </div>

          <!-- 相关推荐 -->
          <div v-if="relatedPlugins.length > 0" class="de-related-card">
            <h4 class="de-sidebar-title">相关推荐</h4>
            <div class="de-related-list">
              <div
                v-for="related in relatedPlugins.slice(0, 3)"
                :key="related.id"
                class="de-related-item"
                @click="$emit('view-detail', related)"
              >
                <span class="de-related-icon">{{ related.display_icon || '📦' }}</span>
                <div class="de-related-info">
                  <span class="de-related-name">{{ related.name }}</span>
                  <span class="de-related-cat">{{ getCategoryLabel(related.category) }}</span>
                </div>
                <i data-lucide="chevron-right" class="de-related-arrow"></i>
              </div>
            </div>
          </div>
        </aside>
      </div>

      <!-- 底部固定操作栏（移动端） -->
      <div class="de-mobile-actions">
        <button
          v-if="!isInstalled"
          @click="$emit('install')"
          class="de-btn de-btn-primary de-btn-block"
        >
          <i data-lucide="download"></i>
          立即安装
        </button>
        <button
          v-else
          @click="$emit('configure')"
          class="de-btn de-btn-secondary de-btn-block"
        >
          <i data-lucide="settings"></i>
          配置
        </button>
      </div>

      <!-- 评价表单对话框 -->
      <Teleport to="body">
        <div v-if="showReviewForm" class="de-modal-overlay" @click.self="showReviewForm = false">
          <div class="de-modal">
            <div class="de-modal-header">
              <h3>撰写评价</h3>
              <button @click="showReviewForm = false" class="de-modal-close">
                <i data-lucide="x"></i>
              </button>
            </div>
            <div class="de-modal-body">
              <div class="de-form-group">
                <label>评分</label>
                <div class="de-star-input">
                  <button
                    v-for="star in 5"
                    :key="star"
                    type="button"
                    @click="newReview.rating = star"
                    class="de-star-btn"
                    :class="{ active: star <= newReview.rating }"
                  >
                    <i data-lucide="star"></i>
                  </button>
                </div>
              </div>

              <div class="de-form-group">
                <label>标题（可选）</label>
                <input
                  v-model="newReview.title"
                  type="text"
                  placeholder="用一句话总结你的体验"
                  class="de-input"
                />
              </div>

              <div class="de-form-group">
                <label>详细评价</label>
                <textarea
                  v-model="newReview.content"
                  rows="5"
                  placeholder="分享你的使用体验、建议..."
                  class="de-textarea"
                ></textarea>
              </div>
            </div>
            <div class="de-modal-footer">
              <button @click="showReviewForm = false" class="de-btn de-btn-secondary">取消</button>
              <button 
                @click="submitReview" 
                class="de-btn de-btn-primary" 
                :disabled="submittingReview"
              >
                <template v-if="!submittingReview">提交评价</template>
                <template v-else>
                  <div class="de-spinner-small"></div>
                  提交中...
                </template>
              </button>
            </div>
          </div>
        </div>
      </Teleport>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import type { Plugin, PluginCategory, PricingModel, PluginReview } from '@/api/plugins'
import { pluginsApi } from '@/api/plugins'

// ==================== Props & Emits ====================
interface Props {
  plugin: Plugin
  isInstalled?: boolean
  installing?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  isInstalled: false,
  installing: false,
})

const emit = defineEmits<{
  close: []
  install: []
  configure: []
  uninstall: []
  'view-detail': [plugin: Plugin]
}>()

// ==================== 响应式状态 =======
const currentScreenshot = ref(0)
const showReviewForm = ref(false)
const isFavorite = ref(false)
const hasReviewed = ref(false)

const newReview = ref({
  rating: 5,
  title: '',
  content: '',
})

// ==================== 评论系统状态 ====================
const reviews = ref<PluginReview[]>([])
const reviewLoading = ref(false)
const reviewPagination = ref({
  page: 1,
  page_size: 10,
  total: 0,
  total_pages: 0,
})
const reviewSortBy = ref<'newest' | 'oldest' | 'rating_high' | 'rating_low' | 'helpful'>('newest')
const reviewRatingFilter = ref<number | null>(null)
const myReview = ref<PluginReview | null>(null)
const submittingReview = ref(false)

// ==================== 截图数据（可从API扩展）=======
const screenshots = ref([
  { thumb: 'https://via.placeholder.com/200x150/e0e7ff/6366f1?text=截图1', full: '' },
  { thumb: 'https://via.placeholder.com/200x150/dcfce7/16a34a?text=截图2', full: '' },
  { thumb: 'https://via.placeholder.com/200x150fef3c7d97706?text=截图3', full: '' },
])

const features = computed(() => {
  // 根据分类生成示例功能列表
  const featureMap: Record<string, string[]> = {
    workflow_node: [
      '支持自定义工作流节点',
      '可视化配置界面',
      '实时执行状态监控',
      '错误自动重试机制',
      '丰富的输入输出类型',
    ],
    datasource: [
      '多数据源接入能力',
      '定时数据同步任务',
      '增量更新策略',
      '数据格式转换',
      '异常告警通知',
    ],
    platform: [
      '一键多平台发布',
      '图文/视频全格式支持',
      '发布队列管理',
      '失败重试机制',
      '发布效果统计',
    ],
    integration: [
      '第三方服务集成',
      'Webhook触发器',
      'API代理转发',
      '消息推送通知',
      '自动化工作流联动',
    ],
  }
  return featureMap[props.plugin.category] || ['核心功能一', '核心功能二', '核心功能三']
})

const changelog = ref([
  {
    version: '1.2.0',
    date: props.plugin.updated_at || new Date().toISOString(),
    changes: [
      '新增批量处理功能',
      '优化性能，响应速度提升30%',
      '修复已知问题',
    ],
  },
  {
    version: '1.1.0',
    date: new Date(Date.now() - 30 * 24 * 60 * 60 * 1000).toISOString(),
    changes: [
      '新增UI主题切换',
      '支持更多数据格式',
      '改进错误提示信息',
    ],
  },
  {
    version: '1.0.0',
    date: props.plugin.created_at || new Date().toISOString(),
    changes: [
      '初始版本发布',
      '包含基础功能集',
    ],
  },
])

const relatedPlugins = ref<Plugin[]>([])

// ==================== 评论API调用方法 ====================

/**
 * 加载评论列表
 */
async function loadReviews(resetPage = false) {
  if (resetPage) {
    reviewPagination.value.page = 1
  }

  reviewLoading.value = true
  try {
    const response = await pluginsApi.getReviews(props.plugin.id, {
      page: reviewPagination.value.page,
      page_size: reviewPagination.value.page_size,
      sort_by: reviewSortBy.value,
      rating_filter: reviewRatingFilter.value ?? undefined,
    })

    if (response.success) {
      reviews.value = response.data.reviews
      reviewPagination.value = {
        ...reviewPagination.value,
        ...response.data.pagination,
      }
      
      // 更新插件的评分统计（如果API返回了）
      if (response.data.summary.avg_rating && !props.plugin.stats?.avg_rating) {
        props.plugin.stats = {
          ...props.plugin.stats,
          avg_rating: response.data.summary.avg_rating,
          review_count: response.data.summary.total_reviews,
        } as any
      }
    }
  } catch (error) {
    console.error('[PluginDetailEnhanced] Failed to load reviews:', error)
  } finally {
    reviewLoading.value = false
  }
}

/**
 * 加载当前用户的评价（用于显示"已评价"状态）
 */
async function loadMyReview() {
  try {
    const review = await pluginsApi.getMyReview(props.plugin.id)
    myReview.value = review
    hasReviewed.value = !!review
    
    // 如果已评价，填充到编辑表单
    if (review) {
      newReview.value = {
        rating: review.rating,
        title: review.title || '',
        content: review.content || '',
      }
    }
  } catch (error) {
    console.error('[PluginDetailEnhanced] Failed to load my review:', error)
  }
}

/**
 * 提交评价（创建或更新）
 */
async function submitReview() {
  if (newReview.value.rating === 0) {
    alert('请选择评分')
    return
  }

  submittingReview.value = true
  try {
    if (myReview.value) {
      // 更新现有评价
      await pluginsApi.updateReview(
        props.plugin.id,
        myReview.value.id,
        newReview.value
      )
      alert('评价更新成功！')
    } else {
      // 创建新评价
      await pluginsApi.createReview(props.plugin.id, newReview.value)
      alert('评价提交成功！感谢您的反馈。')
    }

    showReviewForm.value = false
    hasReviewed.value = true
    
    // 刷新评论列表和我的评价
    await Promise.all([loadReviews(), loadMyReview()])
  } catch (error: any) {
    console.error('[PluginDetailEnhanced] Failed to submit review:', error)
    alert(error.response?.data?.detail || '提交失败，请稍后重试')
  } finally {
    submittingReview.value = false
  }
}

/**
 * 标记评论为有用
 */
async function handleMarkHelpful(reviewId: number) {
  try {
    const result = await pluginsApi.markHelpful(props.plugin.id, reviewId)
    
    // 更新本地状态
    const review = reviews.value.find(r => r.id === reviewId)
    if (review) {
      review.helpful_count = result.helpful_count
    }
  } catch (error) {
    console.error('[PluginDetailEnhanced] Failed to mark helpful:', error)
  }
}

/**
 * 切换排序方式
 */
function changeSortBy(sortBy: typeof reviewSortBy.value) {
  reviewSortBy.value = sortBy
  loadReviews(true)
}

/**
 * 切换星级筛选
 */
function filterByRating(rating: number | null) {
  reviewRatingFilter.value = rating
  loadReviews(true)
}

/**
 * 加载更多评论（分页）
 */
function loadMoreReviews() {
  if (reviewPagination.value.page < reviewPagination.value.total_pages) {
    reviewPagination.value.page++
    loadReviews()
  }
}

// ==================== 生命周期钩子 ====================
onMounted(() => {
  // 加载评论数据
  loadReviews()
  loadMyReview()
})

// ==================== 计算属性 =======
const formattedDescription = computed(() => {
  // 将换行符转换为HTML段落
  return props.plugin.description
    .split('\n\n')
    .map(p => `<p>${p}</p>`)
    .join('')
})

const hasConfigSchema = computed(() => {
  return (
    props.plugin.config_schema &&
    Object.keys(props.plugin.config_schema).length > 0
  )
})

// ==================== 方法 =======
function getCategoryGradient(category: PluginCategory): string {
  const gradients: Record<PluginCategory, string> = {
    platform: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
    datasource: 'linear-gradient(135deg, #11998e 0%, #38ef7d 100%)',
    workflow_node: 'linear-gradient(135deg, #4facfe 0%, #00f2fe 100%)',
    ui_theme: 'linear-gradient(135deg, #fa709a 0%, #fee140 100%)',
    analytics: 'linear-gradient(135deg, #a18cd1 0%, #fbc2eb 100%)',
    utility: 'linear-gradient(135deg, #fccb90 0%, #d57eeb 100%)',
    integration: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
    ai_model: 'linear-gradient(135deg, #a18cd1 0%, #fbc2eb 100%)',
    tool: 'linear-gradient(135deg, #ffecd2 0%, #fcb69f 100%)',
    theme: 'linear-gradient(135deg, #ff9a9e 0%, #fecfef 100%)',
  }
  return gradients[category] || gradients.workflow_node
}

function getCategoryLabel(category: PluginCategory): string {
  const labels: Record<PluginCategory, string> = {
    platform: '平台发布',
    datasource: '数据源',
    workflow_node: '工作流节点',
    ui_theme: 'UI主题',
    analytics: '数据分析',
    utility: '工具类',
    integration: '集成类',
    ai_model: 'AI模型',
    tool: '工具',
    theme: '主题',
  }
  return labels[category] || category
}

function getPriceLabel(model: PricingModel): string {
  const labels: Record<PricingModel, string> = {
    free: '免费',
    freemium: '免费增值',
    paid: '付费',
    subscription: '订阅制',
  }
  return labels[model] || model
}

function formatNumber(num?: number): string {
  if (!num) return '0'
  if (num >= 10000) return (num / 10000).toFixed(1) + 'w'
  if (num >= 1000) return (num / 1000).toFixed(1) + 'k'
  return num.toString()
}

function formatDate(dateStr: string): string {
  try {
    const date = new Date(dateStr)
    return date.toLocaleDateString('zh-CN', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    })
  } catch {
    return dateStr
  }
}

function formatTimeAgo(dateStr: string): string {
  try {
    const date = new Date(dateStr)
    const now = new Date()
    const diff = now.getTime() - date.getTime()
    const days = Math.floor(diff / (1000 * 60 * 60 * 24))

    if (days === 0) return '今天'
    if (days === 1) return '昨天'
    if (days < 7) return `${days}天前`
    if (days < 30) return `${Math.floor(days / 7)}周前`
    return formatDate(dateStr)
  } catch {
    return dateStr
  }
}

async function toggleFavorite() {
  isFavorite.value = !isFavorite.value
  // TODO: 调用收藏API
}

async function handleUninstall() {
  if (confirm('确定要卸载此插件吗？')) {
    emit('uninstall')
  }
}

</script>

<style scoped>
/* ===== 容器布局 ===== */
.detail-enhanced {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
  backdrop-filter: blur(8px);
  z-index: 3000;
  overflow-y: auto;
  animation: fadeIn 0.3s ease;
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

.de-container {
  max-width: 1200px;
  margin: 20px auto;
  background: white;
  border-radius: 20px;
  overflow: hidden;
  box-shadow: 0 25px 80px rgba(0, 0, 0, 0.35);
  animation: slideUp 0.4s ease;
}

@keyframes slideUp {
  from {
    opacity: 0;
    transform: translateY(40px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/* ===== Hero区域 ===== */
.de-hero {
  padding: 48px 40px;
  color: white;
  position: relative;
  overflow: hidden;
}

.de-hero::before {
  content: '';
  position: absolute;
  inset: 0;
  background: url("data:image/svg+xml,%3Csvg width='60' height='60' viewBox='0 0 60 60' xmlns='http://www.w3.org/2000/svg'%3E%3Cg fill='none' fill-rule='evenodd'%3E%3Cg fill='%23ffffff' fill-opacity='0.05'%3E%3Cpath d='M36 34v-4h-2v4h-4v2h4v4h2v-4h4v-2h-4zm0-30V0h-2v4h-4v2h4v4h2V6h4V4h-4zM6 34v-4H4v4H0v2h4v4h2v-4h4v-2H6zM6 4V0H4v4H0v2h4v4h2V6h4V4H6z'/%3E%3C/g%3E%3C/g%3E%3C/svg%3E");
  opacity: 0.5;
}

.de-hero-content {
  position: relative;
  z-index: 1;
}

.de-close-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 10px 18px;
  background: rgba(255, 255, 255, 0.15);
  border: 1px solid rgba(255, 255, 255, 0.25);
  border-radius: 10px;
  color: white;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.3s;
  margin-bottom: 28px;
  backdrop-filter: blur(10px);
}

.de-close-btn:hover {
  background: rgba(255, 255, 255, 0.25);
  transform: translateX(-4px);
}

.de-hero-main {
  display: flex;
  gap: 28px;
  align-items: flex-start;
}

.de-icon-wrapper {
  width: 96px;
  height: 96px;
  background: rgba(255, 255, 255, 0.15);
  border-radius: 22px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 48px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.15);
  backdrop-filter: blur(10px);
  flex-shrink: 0;
}

.de-plugin-icon {
  filter: drop-shadow(0 2px 4px rgba(0, 0, 0, 0.2));
}

.de-hero-info {
  flex: 1;
}

.de-title {
  font-size: 36px;
  font-weight: 800;
  margin: 0 0 12px 0;
  line-height: 1.2;
  text-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
}

.de-subtitle {
  font-size: 17px;
  line-height: 1.6;
  opacity: 0.95;
  margin: 0 0 20px 0;
  max-width: 600px;
}

.de-meta-tags {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.de-tag {
  padding: 6px 14px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 600;
  backdrop-filter: blur(10px);
}

.de-tag-builtin {
  background: rgba(251, 191, 36, 0.9);
  color: #78350f;
}

.de-tag-category {
  background: rgba(255, 255, 255, 0.2);
  border: 1px solid rgba(255, 255, 255, 0.3);
}

.de-tag-price-free {
  background: rgba(16, 185, 129, 0.9);
  color: #064e3b;
}

.de-tag-price-freemium {
  background: rgba(245, 158, 11, 0.9);
  color: #78350f;
}

.de-tag-price-paid,
.de-tag-price-subscription {
  background: rgba(239, 68, 68, 0.9);
  color: #7f1d1d;
}

.de-tag-version {
  background: rgba(255, 255, 255, 0.15);
  border: 1px solid rgba(255, 255, 255, 0.25);
  font-family: monospace;
}

/* ===== 主内容区域 ===== */
.de-body {
  display: grid;
  grid-template-columns: 1fr 340px;
  gap: 32px;
  padding: 40px;
}

@media (max-width: 1024px) {
  .de-body {
    grid-template-columns: 1fr;
  }

  .de-sidebar {
    order: -1;
  }
}

.de-main {
  min-width: 0;
}

/* ===== 区块通用样式 ===== */
.de-section {
  margin-bottom: 40px;
}

.de-section:last-child {
  margin-bottom: 0;
}

.de-section-title {
  font-size: 20px;
  font-weight: 700;
  color: #111827;
  margin: 0 0 20px 0;
  display: flex;
  align-items: center;
  gap: 10px;
}

.de-section-title i {
  width: 22px;
  height: 22px;
  color: #6366f1;
}

/* ===== 截图画廊 ===== */
.de-screenshots {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 14px;
}

.de-screenshot {
  aspect-ratio: 4/3;
  border-radius: 12px;
  overflow: hidden;
  cursor: pointer;
  border: 3px solid transparent;
  transition: all 0.3s;
  position: relative;
}

.de-screenshot:hover {
  transform: translateY(-4px);
  box-shadow: 0 8px 20px rgba(0, 0, 0, 0.15);
}

.de-screenshot.active {
  border-color: #6366f1;
  box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.2);
}

.de-screenshot img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

/* ===== 描述 ===== */
.de-description {
  font-size: 15px;
  line-height: 1.8;
  color: #374151;
}

.de-description :deep(p) {
  margin-bottom: 16px;
}

.de-description :deep(p:last-child) {
  margin-bottom: 0;
}

/* ===== 功能列表 ===== */
.de-features {
  list-style: none;
  padding: 0;
  margin: 0;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
  gap: 14px;
}

.de-feature-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 14px 18px;
  background: linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%);
  border-radius: 10px;
  font-size: 14px;
  color: #166534;
  transition: all 0.2s;
}

.de-feature-item:hover {
  transform: translateX(4px);
  box-shadow: 0 4px 12px rgba(16, 185, 129, 0.15);
}

.de-feature-item i {
  width: 18px;
  height: 18px;
  color: #16a34a;
  flex-shrink: 0;
  margin-top: 2px;
}

/* ===== 配置预览 ===== */
.de-config-preview {
  background: #1e293b;
  border-radius: 12px;
  padding: 20px;
  overflow-x: auto;
}

.de-config-preview pre {
  margin: 0;
}

.de-config-preview code {
  font-family: 'Monaco', 'Menlo', monospace;
  font-size: 13px;
  color: #e2e8f0;
  line-height: 1.6;
}

/* ===== 更新日志 ===== */
.de-changelog {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.de-changelog-item {
  padding: 20px;
  background: #f9fafb;
  border-radius: 12px;
  border-left: 4px solid #6366f1;
}

.de-log-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.de-log-version {
  font-size: 16px;
  font-weight: 700;
  color: #111827;
}

.de-log-date {
  font-size: 13px;
  color: #6b7280;
}

.de-log-changes {
  list-style: none;
  padding: 0;
  margin: 0;
}

.de-log-changes li {
  padding: 6px 0;
  padding-left: 20px;
  position: relative;
  font-size: 14px;
  color: #4b5563;
}

.de-log-changes li::before {
  content: '+';
  position: absolute;
  left: 0;
  color: #16a34a;
  font-weight: 700;
}

/* ===== 评价区域 ===== */
.de-reviews-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 20px;
}

.de-rating-big {
  text-align: right;
}

.de-rating-number {
  font-size: 42px;
  font-weight: 800;
  color: #111827;
  line-height: 1;
  display: block;
  margin-bottom: 6px;
}

.de-stars {
  display: flex;
  gap: 3px;
  justify-content: flex-end;
}

.de-stars i {
  width: 18px;
  height: 18px;
  color: #d1d5db;
  fill: none;
}

.de-stars i.filled {
  color: #fbbf24;
  fill: #fbbf24;
}

.de-review-card {
  padding: 20px;
  background: #f9fafb;
  border-radius: 12px;
  margin-bottom: 16px;
  transition: all 0.2s;
}

.de-review-card:hover {
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.06);
}

.de-review-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 14px;
}

.de-reviewer-avatar {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  font-size: 16px;
  flex-shrink: 0;
}

.de-reviewer-info {
  flex: 1;
}

.de-reviewer-info strong {
  font-size: 14px;
  color: #111827;
  display: block;
  margin-bottom: 4px;
}

.de-review-stars {
  display: flex;
  gap: 2px;
}

.de-review-stars i {
  width: 14px;
  height: 14px;
  color: #d1d5db;
  fill: none;
}

.de-review-stars i.filled {
  color: #fbbf24;
  fill: #fbbf24;
}

.de-review-date {
  font-size: 13px;
  color: #9ca3af;
  flex-shrink: 0;
}

.de-review-title {
  font-size: 16px;
  font-weight: 600;
  color: #111827;
  margin: 0 0 8px 0;
}

.de-review-content {
  font-size: 14px;
  line-height: 1.7;
  color: #4b5563;
  margin: 0 0 12px 0;
}

.de-review-footer {
  display: flex;
  justify-content: flex-end;
}

.de-helpful-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  background: white;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  font-size: 13px;
  color: #6b7280;
  cursor: pointer;
  transition: all 0.2s;
}

.de-helpful-btn:hover,
.de-helpful-btn.active {
  background: #eff6ff;
  border-color: #3b82f6;
  color: #2563eb;
}

.de-helpful-btn i {
  width: 14px;
  height: 14px;
}

.de-empty-reviews {
  text-align: center;
  padding: 48px 20px;
  color: #9ca3af;
}

.de-empty-reviews i {
  width: 48px;
  height: 48px;
  margin: 0 auto 12px;
  opacity: 0.4;
}

.de-empty-reviews p {
  margin: 0 0 4px 0;
  font-size: 15px;
}

.de-empty-hint {
  font-size: 13px !important;
}

/* ===== 侧边栏 ===== */
.de-sidebar {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.de-sidebar-title {
  font-size: 15px;
  font-weight: 700;
  color: #111827;
  margin: 0 0 14px 0;
  display: flex;
  align-items: center;
  gap: 8px;
}

/* 操作卡片 */
.de-action-card {
  background: linear-gradient(135deg, #f9fafb 0%, #ffffff 100%);
  border: 1px solid #e5e7eb;
  border-radius: 16px;
  padding: 24px;
  position: sticky;
  top: 20px;
}

.de-price-box {
  margin-bottom: 20px;
  padding-bottom: 20px;
  border-bottom: 1px solid #e5e7eb;
}

.de-price-label {
  font-size: 13px;
  color: #6b7280;
  margin-bottom: 6px;
}

.de-price-value {
  display: flex;
  align-items: baseline;
  gap: 2px;
}

.de-currency {
  font-size: 20px;
  font-weight: 700;
  color: #111827;
}

.de-amount {
  font-size: 36px;
  font-weight: 800;
  color: #111827;
  line-height: 1;
}

.de-period {
  font-size: 14px;
  color: #6b7280;
}

.de-free-text {
  font-size: 24px;
  font-weight: 700;
  color: #16a34a;
}

.de-action-buttons {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-bottom: 16px;
}

.de-favorite-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  width: 100%;
  padding: 11px;
  background: transparent;
  border: 2px solid #e5e7eb;
  border-radius: 10px;
  font-size: 14px;
  font-weight: 600;
  color: #6b7280;
  cursor: pointer;
  transition: all 0.3s;
}

.de-favorite-btn:hover,
.de-favorite-btn.active {
  border-color: #ec4899;
  color: #ec4899;
  background: #fdf2f8;
}

.de-favorite-btn.active i {
  fill: #ec4899;
}

/* 统计卡片 */
.de-stats-card,
.de-author-card,
.de-deps-card,
.de-security-card,
.de-related-card {
  background: #f9fafb;
  border: 1px solid #e5e7eb;
  border-radius: 14px;
  padding: 20px;
}

.de-stat-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.de-stat-row {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 14px;
  color: #4b5563;
}

.de-stat-row i {
  width: 18px;
  height: 18px;
  color: #6366f1;
  flex-shrink: 0;
}

.de-stat-row strong {
  margin-left: auto;
  color: #111827;
  font-weight: 600;
}

/* 作者信息 */
.de-author-profile {
  display: flex;
  gap: 14px;
  align-items: center;
}

.de-author-avatar {
  width: 48px;
  height: 48px;
  border-radius: 50%;
  background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  font-size: 18px;
  flex-shrink: 0;
}

.de-author-details {
  flex: 1;
}

.de-author-name {
  font-size: 15px;
  font-weight: 600;
  color: #111827;
  margin: 0 0 4px 0;
}

.de-author-email {
  font-size: 13px;
  color: #6b7280;
  margin: 0 0 6px 0;
}

.de-view-more-link {
  font-size: 13px;
  color: #6366f1;
  text-decoration: none;
  font-weight: 500;
}

.de-view-more-link:hover {
  text-decoration: underline;
}

/* 依赖项 */
.de-deps-list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.de-dep-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: #4b5563;
}

.de-dep-item i {
  width: 16px;
  height: 16px;
  color: #f59e0b;
  flex-shrink: 0;
}

.de-dep-item code {
  font-family: 'Monaco', monospace;
  font-size: 12px;
  background: white;
  padding: 2px 8px;
  border-radius: 4px;
}

/* 安全信息 */
.de-security-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px;
  background: #ecfdf5;
  border-radius: 8px;
  font-size: 14px;
  color: #065f46;
  margin-bottom: 12px;
}

.de-security-icon-safe {
  color: #16a34a !important;
}

.de-permissions-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 12px;
}

.de-permission-badge {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  background: #fffbeb;
  border: 1px solid #fde68a;
  border-radius: 8px;
  font-size: 13px;
  color: #92400e;
}

.de-permission-badge i {
  width: 16px;
  height: 16px;
  color: #f59e0b;
  flex-shrink: 0;
}

.de-audit-info {
  display: flex;
  align-items: center;
  gap: 8px;
  padding-top: 12px;
  border-top: 1px solid #e5e7eb;
  font-size: 13px;
  color: #059669;
  font-weight: 500;
}

.de-audit-info i {
  width: 16px;
  height: 16px;
}

/* 相关推荐 */
.de-related-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.de-related-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  background: white;
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.2s;
}

.de-related-item:hover {
  background: #f3f4f6;
  transform: translateX(4px);
}

.de-related-icon {
  font-size: 24px;
  flex-shrink: 0;
}

.de-related-info {
  flex: 1;
  min-width: 0;
}

.de-related-name {
  display: block;
  font-size: 14px;
  font-weight: 500;
  color: #111827;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.de-related-cat {
  font-size: 12px;
  color: #6b7280;
}

.de-related-arrow {
  width: 16px;
  height: 16px;
  color: #9ca3af;
  flex-shrink: 0;
}

/* ===== 按钮 ===== */
.de-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 12px 24px;
  border: none;
  border-radius: 10px;
  font-size: 15px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.3s ease;
  white-space: nowrap;
}

.de-btn-primary {
  background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
  color: white;
  box-shadow: 0 4px 14px rgba(99, 102, 241, 0.4);
}

.de-btn-primary:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 6px 20px rgba(99, 102, 241, 0.5);
}

.de-btn-primary:disabled {
  opacity: 0.7;
  cursor: not-allowed;
}

.de-btn-secondary {
  background: #f3f4f6;
  color: #374151;
  border: 1px solid #d1d5db;
}

.de-btn-secondary:hover {
  background: #e5e7eb;
}

.de-btn-danger-outline {
  background: transparent;
  color: #dc2626;
  border: 2px solid #fecaca;
}

.de-btn-danger-outline:hover {
  background: #fef2f2;
  border-color: #ef4444;
}

.de-btn-outline {
  background: transparent;
  color: #6366f1;
  border: 2px solid #c7d2fe;
}

.de-btn-outline:hover {
  background: #eef2ff;
}

.de-btn-block {
  width: 100%;
}

.de-spinner-small {
  width: 16px;
  height: 16px;
  border: 2px solid currentColor;
  border-top-color: transparent;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  display: inline-block;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* ===== 移动端底部操作栏 ===== */
.de-mobile-actions {
  display: none;
  padding: 16px 20px;
  background: white;
  border-top: 1px solid #e5e7eb;
  position: sticky;
  bottom: 0;
}

@media (max-width: 768px) {
  .de-mobile-actions {
    display: block;
  }

  .de-hero {
    padding: 32px 24px;
  }

  .de-hero-main {
    flex-direction: column;
    align-items: center;
    text-align: center;
  }

  .de-title {
    font-size: 28px;
  }

  .de-body {
    padding: 24px;
  }

  .de-action-card {
    position: static;
  }
}

/* ===== 评价表单模态框 ===== */
.de-modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  z-index: 4000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
}

.de-modal {
  background: white;
  border-radius: 16px;
  width: 100%;
  max-width: 520px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
}

.de-modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 24px;
  border-bottom: 1px solid #e5e7eb;
}

.de-modal-header h3 {
  font-size: 18px;
  font-weight: 700;
  margin: 0;
}

.de-modal-close {
  background: none;
  border: none;
  cursor: pointer;
  padding: 6px;
  border-radius: 8px;
  color: #6b7280;
}

.de-modal-close:hover {
  background: #f3f4f6;
}

.de-modal-body {
  padding: 24px;
}

.de-form-group {
  margin-bottom: 20px;
}

.de-form-group label {
  display: block;
  font-size: 14px;
  font-weight: 600;
  color: #374151;
  margin-bottom: 8px;
}

.de-star-input {
  display: flex;
  gap: 6px;
}

.de-star-btn {
  background: none;
  border: none;
  cursor: pointer;
  padding: 4px;
  color: #d1d5db;
  transition: all 0.2s;
}

.de-star-btn i {
  width: 28px;
  height: 28px;
}

.de-star-btn.active,
.de-star-btn:hover {
  color: #fbbf24;
  transform: scale(1.1);
}

.de-star-btn.active i {
  fill: #fbbf24;
}

.de-input,
.de-textarea {
  width: 100%;
  padding: 12px 16px;
  border: 2px solid #e5e7eb;
  border-radius: 10px;
  font-size: 14px;
  font-family: inherit;
  transition: all 0.3s;
  box-sizing: border-box;
}

.de-input:focus,
.de-textarea:focus {
  outline: none;
  border-color: #6366f1;
  box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.1);
}

.de-textarea {
  resize: vertical;
  min-height: 100px;
}

.de-modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding: 20px 24px;
  border-top: 1px solid #e5e7eb;
  background: #f9fafb;
}

/* ===== 评论系统增强样式 ===== */

/* 工具栏 */
.de-reviews-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  padding: 16px;
  background: #f9fafb;
  border-radius: 12px;
  border: 1px solid #e5e7eb;
}

.de-reviews-filters {
  display: flex;
  gap: 12px;
}

.de-select-sm {
  height: 32px;
  font-size: 13px;
  padding: 0 12px;
}

.de-btn-sm {
  height: 32px;
  font-size: 13px;
  padding: 0 12px;
}

/* 加载状态 */
.de-loading-state,
.de-loading-more {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 40px 20px;
  color: #6b7280;
  font-size: 14px;
}

.de-loading-more {
  padding: 20px;
}

.de-spinner-small {
  width: 18px;
  height: 18px;
  border: 2px solid #e5e7eb;
  border-top-color: #6366f1;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* 已购买标识 */
.de-verified-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: #059669;
  background: #d1fae5;
  padding: 2px 8px;
  border-radius: 9999px;
  font-weight: 600;
}

/* 加载更多按钮 */
.de-load-more {
  margin-top: 24px;
  padding-top: 24px;
  border-top: 1px solid #f3f4f6;
}

/* 响应式：小屏幕工具栏堆叠 */
@media (max-width: 640px) {
  .de-reviews-toolbar {
    flex-direction: column;
    gap: 12px;
  }
  
  .de-reviews-filters {
    width: 100%;
    flex-direction: column;
  }
  
  .de-select-sm {
    width: 100%;
  }
}
</style>