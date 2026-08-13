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
    path: '/workbench',
    name: 'Workbench',
    component: () => import('@/views/WorkbenchView.vue'),
    meta: { requiresAuth: true }
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
  } else {
    next()
  }
})

export default router