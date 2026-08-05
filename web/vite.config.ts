import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import AutoImport from 'unplugin-auto-import/vite'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'
import path from 'path'
import { createSvgIconsPlugin } from 'vite-plugin-svg-icons'

const pathResolve = (pathStr: string) => {
  return path.resolve(__dirname, pathStr)
}

// https://vitejs.dev/config/
export default defineConfig({
  build: {
    rollupOptions: {
      input: {
        multialpha: pathResolve('./multialpha.html'),
        predict: pathResolve('./predict.html'),
        anaAgents: pathResolve('./ana-agents.html'),
        hiagentChat: pathResolve('./hiagent-chat.html'),
        artifact: pathResolve('./artifact.html'),
      },
    },
  },
  plugins: [
    vue(),
    createSvgIconsPlugin({
      iconDirs: [pathResolve('./src/assets/icon')],
      symbolId: 'icon-[dir]-[name]',
    }),
    AutoImport({
      resolvers: [ElementPlusResolver()],
    }),
    Components({
      resolvers: [ElementPlusResolver()],
    }),
  ],
  define: {
    'global': 'window'
  },
  server: {
    host: true,
    port: 8080,
    open: 'artifact.html',
    watch: {
      usePolling: true,
      interval: 1000
    },
    proxy: {
      '/traces': 'http://localhost:19899',
      '/trace': 'http://localhost:19899',
      '/predict': 'http://localhost:19899',
      '/upload': 'http://localhost:19899',
      '/control': 'http://localhost:19899',
      '/logs': 'http://localhost:19899',
      '/stdout': 'http://localhost:19899',
      '/health': 'http://localhost:19899',
      '/api': 'http://localhost:19899',
	      '/api/hiagent': 'http://localhost:19899',
    },
  },
  resolve: {
    alias: {
      '@': pathResolve('./src')
    }
  }
})
