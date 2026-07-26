import { createApp } from 'vue'
import MultiAlphaApp from './MultiAlphaApp.vue'
import './styles/detail.css'
import './styles/detail-results.css'
import './styles/formula.css'
import './styles/log-console.css'
import './styles/landing.css'
import './styles/tokens.css'
import './styles/shell.css'
import './styles/responsive.css'
import router from './router'
import 'element-plus/dist/index.css'
import 'katex/dist/katex.min.css'
import { setupVitals } from './vitals'

createApp(MultiAlphaApp).use(router).mount('#multialpha-app')

// web-vitals 采集（开发期控制台输出 + localStorage，用于性能优化前后对比）
setupVitals()
