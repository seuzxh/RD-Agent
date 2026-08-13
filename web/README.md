# Multiαlpha Web

Vite + Vue 3 + TypeScript 前端，多页应用（MPA）结构。当前生产构建仅输出
**Multiα1pha 量化决策终端**入口。

## 环境要求

- Node.js 18+（建议 20 LTS）
- npm（随 Node 安装）

后端 API 默认监听 `http://localhost:19899`，启动前端前请先确认后端服务已就绪。

## 安装依赖

```bash
npm install
```

## 本地开发

```bash
npm run dev
```

- 开发服务器监听 `http://localhost:8080`，并自动打开 Multiα1pha 入口。
- Multiα1pha API 请求通过 Vite 代理转发到 `http://localhost:19899`，覆盖以下路径：
  `/traces` `/trace` `/predict` `/upload` `/control` `/logs` `/stdout` `/health`

入口地址：

| 入口 | 开发访问地址 | 说明 |
| --- | --- | --- |
| Multiα1pha | http://localhost:8080/multialpha.html | 当前主入口，`dev` 默认打开 |
| Finance Prediction | http://localhost:8080/predict.html | 股池预测，独立页面，与主页平级 |
| AI 投研圆桌 | http://localhost:8080/ana-agents.html | 六智能体观点总览 |
| 智能体观点详情 | http://localhost:8080/ana-agent-detail.html | 单智能体观点详情，由总览页携带参数进入 |

> 旧 R&D-Agent 页面源码仍保留在 `src/views/`、`src/router/`、`src/main.ts` 和
> `src/App.vue`，但已移除 HTML 入口，不参与开发入口和生产构建。

## 生产构建

```bash
# 构建到 ./dist
npm run build

# 构建到 ../git_ignore_folder/static，供 Flask 同源服务
npm run build:flask
```

两种命令的产物一致，均包含 `multialpha.html`、`predict.html`、`ana-agents.html`、
`ana-agent-detail.html` 和 `assets/`，只是输出目录不同。

## 本地预览生产构建

```bash
npm run preview
```

## API 地址行为

前端使用相对路径发起请求（如 `fetch('/traces')`）。

- **开发**：由 `vite.config.ts` 的 `server.proxy` 转发到 `http://localhost:19899`。
- **生产**：使用当前页面同源地址。若前端由同样暴露 `/upload` `/trace` `/control`
  等接口的 Flask 服务器提供，则无需额外配置，前端会自动调用服务该页面的同主机同端口。

## 项目结构

```
web/
├── multialpha.html         # MultiAlpha 入口（主入口，参与生产构建）
├── predict.html            # 股池预测入口
├── ana-agents.html         # 六智能体观点总览入口
├── ana-agent-detail.html   # 单智能体观点详情入口
├── vite.config.ts          # Vite 配置：MPA 入口、代理、端口、自动打开
├── package.json            # 脚本：dev / build / build:flask / preview
└── src/
    ├── main.ts             # 已废弃的 R&D-Agent 启动源码（无 HTML 入口）
    ├── views/              # 已废弃的 R&D-Agent 页面源码
    ├── router/             # 已废弃的 R&D-Agent 路由源码
    ├── multialpha/         # MultiAlpha 应用入口与逻辑
    ├── predict/            # 股池预测应用入口与逻辑
    ├── ana-agents/         # 六智能体总览及详情页逻辑
    └── services/           # API 封装（rdagent-api.ts），相对路径请求
```

## 推荐 IDE 配置

- [VS Code](https://code.visualstudio.com/) + [Vue - Official](https://marketplace.visualstudio.com/items?itemName=Vue.volar)（原 Volar），并禁用 Vetur。
- 使用 [vue-tsc](https://github.com/vuejs/language-tools/tree/master/packages/tsc) 进行命令行类型检查。
