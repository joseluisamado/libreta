import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    name: 'dashboard',
    component: () => import('./views/DashboardView.vue'),
  },
  {
    path: '/w/:path(.*)*',
    name: 'page',
    component: () => import('./views/PageView.vue'),
  },
  {
    path: '/history/:path(.*)*',
    name: 'history',
    component: () => import('./views/HistoryView.vue'),
  },
  {
    path: '/edit/:path(.*)*',
    name: 'editor',
    component: () => import('./views/EditorView.vue'),
  },
  {
    path: '/diff/:path(.*)*',
    name: 'diff',
    component: () => import('./views/DiffView.vue'),
  },
  {
    path: '/search',
    name: 'search',
    component: () => import('./views/SearchView.vue'),
  },
  {
    path: '/watch/:label/:path(.*)*',
    name: 'watched-page',
    component: () => import('./views/WatchedPageView.vue'),
  },
  {
    path: '/edit-watch/:label/:path(.*)*',
    name: 'watched-editor',
    component: () => import('./views/WatchedEditorView.vue'),
  },
]

export const router = createRouter({
  history: createWebHistory(),
  routes,
})
