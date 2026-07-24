import { createRouter, createWebHashHistory } from 'vue-router'

export default createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', name: 'multialpha-home', component: { template: '<span />' } },
    { path: '/predict', name: 'multialpha-predict', component: { template: '<span />' } },
    { path: '/tasks/:traceId', name: 'multialpha-task', component: { template: '<span />' }, props: true },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})
