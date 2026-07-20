# Qlib Docker 镜像（local_qlib）

本目录包含 RD-Agent 量化场景（因子挖掘 / 模型训练 / 研报复现）使用的标准化 Docker 执行镜像。

## 镜像说明

| 项 | 配置 |
|---|---|
| 镜像名 | `local_qlib:v2.0` |
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

## 文件说明

| 文件 | 说明 |
|---|---|
| `Dockerfile` | 镜像构建文件 |
| `requirements.lock.txt` | 由 `local_qlib:v2.0` 容器对比基础镜像生成，包含 161 个新增/升级包的精确版本，用于避免 pip 实时解析导致的版本漂移 |
| `qlib-src.tar.gz` | qlib 官方 commit `2fb9380b` 的源码归档（**未入 Git**，见根目录 `.gitignore`）。构建前需自行准备 |

## 如何构建

### 准备 qlib 源码包

由于网络环境限制，Dockerfile 不再从 GitHub 实时 clone，而是使用本地源码包：

```bash
# 在项目根目录或本目录下载
wget -O qlib-src.tar.gz \
  https://github.com/microsoft/qlib/archive/2fb9380b342556ddb50a4b24e4fe8655d548b2b8.tar.gz
```

### 构建镜像

```bash
docker build -t local_qlib:v2.0 \
  /path/to/RD-Agent/rdagent/scenarios/qlib/docker
```

### 派生镜像 `local_qlib:v2.1`（mlflow file-store 修复）

mlflow 3.14.0 默认禁用 `./mlruns` filesystem tracking backend（进入 maintenance mode），导致 qrun 训练时报 `MlflowException`。Dockerfile 已加 `ENV MLFLOW_ALLOW_FILE_STORE=true` 修复。

无需完整重建——可基于 v2.0 秒级派生：

```bash
echo 'FROM local_qlib:v2.0
ENV MLFLOW_ALLOW_FILE_STORE=true' | docker build -t local_qlib:v2.1 -
```

然后在 `.env` 把 `QLIB_DOCKER_IMAGE` 改为 `local_qlib:v2.1`。

## 如何使用（最快方式）

RD-Agent 默认会尝试从 Dockerfile 重新构建镜像。为提升启动速度，在 `.env` 中显式指定使用已有镜像并禁用重建：

```ini
MODEL_CoSTEER_ENV_TYPE=docker
QLIB_DOCKER_IMAGE=local_qlib:v2.1
QLIB_DOCKER_BUILD_FROM_DOCKERFILE=False
```

启动时 `DockerEnv.prepare()` 会直接检查本地是否存在 `local_qlib:v2.0`，存在则立即使用，不触发 `docker build` / `docker pull`。

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
