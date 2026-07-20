# Qlib Docker 镜像（local_qlib）

本目录包含 RD-Agent 量化场景（因子挖掘 / 模型训练 / 研报复现）使用的标准化 Docker 执行镜像。

## 镜像说明

| 项 | 配置 |
|---|---|
| 镜像名 | `local_qlib:v2.1` |
| 基础镜像 | `pytorch/pytorch:2.2.1-cuda12.1-cudnn8-runtime` |
| Python | 3.10 |
| qlib 版本 | commit [`2fb9380b`](https://github.com/microsoft/qlib/commit/2fb9380b342556ddb50a4b24e4fe8655d548b2b8)，运行时显示 `0.9.7` |
| numpy | 1.26.3（与官方上游一致） |
| torch | 2.2.1 |
| pandas | 2.3.3 |
| scipy | 1.15.3 |
| lightgbm | 4.6.0 |
| pyarrow | 24.0.0 |
| mlflow | 3.14.0 |
| mlflow 配置 | `ENV MLFLOW_ALLOW_FILE_STORE=true`（v2.1 新增，允许 mlflow 使用本地 file store） |

## 文件说明

| 文件 | 说明 |
|---|---|
| `Dockerfile` | 镜像构建文件 |
| `requirements.lock.txt` | 由 `local_qlib:v2.1` 容器对比基础镜像生成，包含 161 个新增/升级包的精确版本，用于避免 pip 实时解析导致的版本漂移 |
| `qlib-src.tar.gz` | qlib 官方 commit `2fb9380b` 的源码归档（**已入 Git**，4.7MB）。直接用仓库自带文件即可，无需另行下载 |

## 如何使用镜像（三种路径，任选其一）

### 路径 1：加载镜像 tar（最快上手，跳过构建）

适合：网络可传大文件、想立刻运行、不想等 20-40 分钟构建。

```bash
# 1. 拿到镜像 tar 文件（由项目维护者通过网盘 / 内网文件服务器分发，不入 Git）
docker load < local_qlib-v2.1.tar.gz

# 2. 确认镜像存在
docker images | grep local_qlib    # 预期看到 local_qlib  v2.1

# 3. 直接跳到下方「配置 RD-Agent 使用镜像」
```

镜像 tar 不入 Git（太大），由维护者用以下命令生成并外部分发：
```bash
# 维护者导出命令（记录在此供复现）
docker save local_qlib:v2.1 | gzip > local_qlib-v2.1.tar.gz
sha256sum local_qlib-v2.1.tar.gz    # 把校验值一并分发，接收方加载后可核对
```
v2.1 参考值：压缩后 **5.1 GB**，sha256 `2a60687559ecf707dfc3f5c7b473d3a0f667802c8e93115e83bf4a193ffb7393`。

### 路径 2：从源码构建（可定制）

适合：想定制镜像内容、网络可承受 pip 拉取、或拿不到镜像 tar。

```bash
# qlib-src.tar.gz 已随仓库提供（4.7MB），无需额外下载。
# （可选）校验完整性：
sha256sum rdagent/scenarios/qlib/docker/qlib-src.tar.gz
# 预期：9a83b91054b088b9055d8056b16cbbbeb6b4df1123aba85ec55819bd63463bbd

# 构建镜像（约 20-40 分钟，取决于网络；主要耗时在 pip install requirements.lock.txt）
docker build -t local_qlib:v2.1 rdagent/scenarios/qlib/docker
```

若仓库自带的 `qlib-src.tar.gz` 缺失或想换 qlib commit，可自行下载：
```bash
wget -O rdagent/scenarios/qlib/docker/qlib-src.tar.gz \
  https://github.com/microsoft/qlib/archive/2fb9380b342556ddb50a4b24e4fe8655d548b2b8.tar.gz
```

### 路径 3：配置 RD-Agent 使用镜像

无论路径 1 还是路径 2，拿到镜像后在 `.env` 中显式指定：

```ini
MODEL_CoSTEER_ENV_TYPE=docker
QLIB_DOCKER_IMAGE=local_qlib:v2.1
QLIB_DOCKER_BUILD_FROM_DOCKERFILE=False
```

`QLIB_DOCKER_BUILD_FROM_DOCKERFILE=False` 让 `DockerEnv.prepare()` 直接检查本地是否存在 `local_qlib:v2.1`，存在则立即使用，不触发 `docker build` / `docker pull`。

## 数据挂载

容器启动时会通过 `QlibDockerConf.extra_volumes` 将宿主 `/home/zxh/qlib_data` 只读挂载到容器的 `/root/.qlib/qlib_data/cn_data`。镜像内同时创建了软链：

```
/home/zxh/qlib_data -> /root/.qlib/qlib_data/cn_data
```

这保证了 `conf.yaml` 里写 `provider_uri: "/home/zxh/qlib_data"` 时，在容器内也能解析到真实数据。

## 何时需要重新构建？

- 修改了 `Dockerfile`
- 修改了 `requirements.lock.txt`
- 更新了 `qlib-src.tar.gz` 到新的 commit
- 需要切换 numpy / torch / Python 版本

建议每次重新构建时使用新的 tag（如 `v2.1`），保留旧镜像以便回滚。
