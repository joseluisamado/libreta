import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  { path: '/', redirect: '/w/index' },
  {
    path: '/w/:path(.*)*',
    name: 'page',
    component: () => import('./views/PageView.vue'),
  },
  {
    path: '/edit/:path(.*)*',
    name: 'editor',
    component: () => import('./views/EditorView.vue'),
  },
]

export const router = createRouter({
  history: createWebHistory(),
  routes,
})
