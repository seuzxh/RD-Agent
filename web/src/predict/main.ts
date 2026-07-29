import { createApp } from 'vue'
import PredictApp from './PredictApp.vue'
import './styles/predict.css'
import 'element-plus/dist/index.css'
import 'katex/dist/katex.min.css'
import router from './router'

createApp(PredictApp).use(router).mount('#predict-app')
