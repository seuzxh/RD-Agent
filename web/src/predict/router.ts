import { createRouter, createWebHashHistory } from 'vue-router'
import PredictDashboard from './PredictDashboard.vue'

export default createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', name: 'predict-home', component: PredictDashboard },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})
