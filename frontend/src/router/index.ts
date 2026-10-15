import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  {
    path: '/particle',
    name: 'ParticleHome',
    component: () => import('@/views/ParticleHomeView.vue'),
    meta: { requiresAuth: false }
  },
  {
    path: '/',
    name: 'Home',
    component: () => import('@/views/HomeView.vue'),
    meta: { requiresAuth: true, title: '数据看板' },
  },
  {
    path: '/chat',
    name: 'Chat',
    component: () => import('@/views/ChatViewPage.vue'),
    meta: { requiresAuth: true, title: '对话' },
  },
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/LoginView.vue'),
    meta: { requiresAuth: false }
  },
  {
    path: '/eco',
    name: 'Eco',
    component: () => import('@/views/EcoView.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/topic-pool',
    name: 'TopicPool',
    component: () => import('@/views/TopicPoolView.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/topic-pool/:id',
    name: 'TopicPoolDetail',
    component: () => import('@/views/TopicPoolDetailView.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/mcp-bridge',
    name: 'McpBridge',
    component: () => import('@/views/McpBridgeView.vue'),
    meta: { requiresAuth: false }
  },
  {
    path: '/settings',
    name: 'Settings',
    component: () => import('@/views/SettingsView.vue'),
    meta: {
      requiresAuth: true,
      title: '设置'
    }
  },

  {
    path: '/my-works',
    name: 'MyWorks',
    component: () => import('@/views/MyWorksView.vue'),
    meta: {
      requiresAuth: true,
      title: '我的作品'
    }
  },
  {
    path: '/task-plans',
    name: 'TaskPlans',
    component: () => import('@/views/TaskPlanView.vue'),
    meta: {
      requiresAuth: true,
      title: '任务清单'
    }
  },
  {
    path: '/portfolio',
    name: 'Portfolio',
    component: () => import('@/views/PortfolioView.vue'),
    meta: {
      requiresAuth: true,
      title: '作品集'
    }
  },
  {
    path: '/portfolio/:id',
    name: 'PortfolioDetail',
    component: () => import('@/views/PortfolioDetailView.vue'),
    meta: {
      requiresAuth: true,
      title: '作品详情'
    }
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

router.beforeEach((to, _from, next) => {
  const token = localStorage.getItem('token')
  if (to.name === 'Login' && token && !to.query.force) {
    const redirect = (to.query.redirect as string) || sessionStorage.getItem('redirect_after_login') || '/'
    sessionStorage.removeItem('redirect_after_login')
    next(redirect)
  } else {
    next()
  }
})

export default router