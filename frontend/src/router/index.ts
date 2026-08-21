import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    name: 'Landing',
    component: () => import('@/views/LandingView.vue'),
    meta: { requiresAuth: false }
  },
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/LoginView.vue'),
    meta: { requiresAuth: false }
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
    path: '/card-editor',
    name: 'CardEditor',
    component: () => import('@/views/CardEditorView.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/esther-factory',
    name: 'EstherFactory',
    component: () => import('@/views/EstherFactoryView.vue'),
    meta: { requiresAuth: true }
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
    path: '/wechat-bot-test',
    name: 'WeChatBotTest',
    component: () => import('@/pages/WeChatBotTest.vue'),
    meta: {
      requiresAuth: true,
      title: '微信机器人测试 - Phase 2'
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
  if (to.meta.requiresAuth && !token) {
    next({ name: 'Login', query: { redirect: to.fullPath } })
  } else if (to.name === 'Login' && token && !to.query.force) {
    const redirect = (to.query.redirect as string) || sessionStorage.getItem('redirect_after_login') || '/workbench'
    sessionStorage.removeItem('redirect_after_login')
    next(redirect)
  } else {
    next()
  }
})

export default router