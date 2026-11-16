import { createRouter, createWebHistory } from 'vue-router'

import PlanView from './views/PlanView.vue'
import ResultView from './views/ResultView.vue'
import HistoryView from './views/HistoryView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'plan', component: PlanView, meta: { title: '规划' } },
    { path: '/result', name: 'result', component: ResultView, meta: { title: '行程' } },
    { path: '/history', name: 'history', component: HistoryView, meta: { title: '历史' } },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
  scrollBehavior: () => ({ top: 0 }),
})

router.afterEach((to) => {
  document.title = `${to.meta.title || '知旅'} · 知旅 ZhiLv`
})

export default router
