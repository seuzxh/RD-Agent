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
| R&D-Agent | http://localhost:8080/ | 原 R&D-Agent 应用，仅开发模式可访问 |

> 生产构建目前不输出 `index.html`，R&D-Agent 入口仅在 `npm run dev` 下可用。
> Multiα1pha 与 Finance Prediction 是两个相互独立的 Vue 应用（各自 `createApp`），主页通过"📊 预测"按钮跨页跳转到 `predict.html`。

## 生产构建

```bash
# 构建到 ./dist
npm run build

# 构建到 ../git_ignore_folder/static，供 Flask 同源服务
npm run build:flask
```

两种命令的产物一致，均为 `multialpha.html` + `assets/`，只是输出目录不同。

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
├── index.html              # R&D-Agent 入口（仅开发模式）
├── multialpha.html         # MultiAlpha 入口（主入口，参与生产构建）
├── vite.config.ts          # Vite 配置：MPA 入口、代理、端口、自动打开
├── package.json            # 脚本：dev / build / build:flask / preview
└── src/
    ├── main.ts             # R&D-Agent 应用入口
    ├── multialpha/         # MultiAlpha 应用入口与逻辑
    └── services/           # API 封装（rdagent-api.ts），相对路径请求
```

## 推荐 IDE 配置

- [VS Code](https://code.visualstudio.com/) + [Vue - Official](https://marketplace.visualstudio.com/items?itemName=Vue.volar)（原 Volar），并禁用 Vetur。
- 使用 [vue-tsc](https://github.com/vuejs/language-tools/tree/master/packages/tsc) 进行命令行类型检查。
