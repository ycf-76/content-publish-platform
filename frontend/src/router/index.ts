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
    path: '/login',
    name: 'Login',
    component: () => import('@/views/LoginView.vue'),
    meta: { requiresAuth: false }
  },
  {
    path: '/workflow',
    name: 'WorkflowShowcase',
    component: () => import('@/views/WorkflowShowcaseView.vue'),
    meta: {
      title: '工作流',
      requiresAuth: true
    }
  },
  {
    path: '/workbench/:workflowId?',
    name: 'Workbench',
    component: () => import('@/views/WorkbenchView.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/workflow-templates',
    name: 'WorkflowTemplates',
    component: () => import('@/views/WorkflowTemplatesView.vue'),
    meta: { 
      title: '工作流模板 - 动态编排',
      requiresAuth: true 
    }
  },
  {
    path: '/workflow-editor',
    name: 'WorkflowEditor',
    component: () => import('@/views/WorkflowEditorView.vue'),
    meta: { 
      title: '可视化工作流编辑器',
      requiresAuth: true 
    }
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

// 路由守卫：requiresAuth 路由未登录跳 /login
router.beforeEach((to, _from, next) => {
  const token = localStorage.getItem('token')
  // DEV: 登录验证已暂停，无 token 也放行
  if (to.name === 'Login' && token && !to.query.force) {
    const redirect = (to.query.redirect as string) || sessionStorage.getItem('redirect_after_login') || '/workflow'
    sessionStorage.removeItem('redirect_after_login')
    next(redirect)
  } else {
    next()
  }
})

export default router