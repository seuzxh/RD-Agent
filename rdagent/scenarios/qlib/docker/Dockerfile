FROM pytorch/pytorch:2.2.1-cuda12.1-cudnn8-runtime

# For GPU support, please choose the proper tag from https://hub.docker.com/r/pytorch/pytorch/tags

# 配置 apt 使用阿里云镜像源
RUN sed -i 's@//.*archive.ubuntu.com@//mirrors.aliyun.com@g' /etc/apt/sources.list && \
    sed -i 's@//.*security.ubuntu.com@//mirrors.aliyun.com@g' /etc/apt/sources.list

RUN apt-get clean && apt-get update && apt-get install -y \  
    curl \  
    vim \  
    git \  
    build-essential \
    coreutils \
    && rm -rf /var/lib/apt/lists/* 

# 配置 pip 使用阿里云镜像源
RUN pip config set global.index-url https://mirrors.aliyun.com/pypi/simple && \
    pip config set global.trusted-host mirrors.aliyun.com

# 按 lock 文件安装所有依赖（避免 pip 实时解析导致版本漂移）
# lock 文件由 local_qlib:v2.0 容器内 `pip list --format=freeze` 生成
COPY requirements.lock.txt /tmp/requirements.lock.txt
RUN python -m pip install -r /tmp/requirements.lock.txt && rm /tmp/requirements.lock.txt

# 从本地源码包安装 pyqlib（对应官方 commit 2fb9380b）
# GitHub 归档不含 .git，setuptools-scm 无法推断版本；显式声明与 v0.9.7 一致的版本号
COPY qlib-src.tar.gz /tmp/qlib-src.tar.gz
RUN mkdir -p /workspace && \
    tar -xzf /tmp/qlib-src.tar.gz -C /workspace && \
    mv /workspace/qlib-2fb9380b342556ddb50a4b24e4fe8655d548b2b8 /workspace/qlib && \
    rm /tmp/qlib-src.tar.gz

WORKDIR /workspace/qlib
ENV SETUPTOOLS_SCM_PRETEND_VERSION_FOR_PYQLIB=0.9.7
RUN python -m pip install --no-deps -e .

# 注：原 0.8 项目此处有 `ln -s /root/.qlib/qlib_data/cn_data /home/zxh/qlib_data` 软链，
# 意图让 conf.yaml 里 provider_uri: /home/zxh/qlib_data 在容器内能解析。但实际所有
# provider_uri 都是 ~/.qlib/qlib_data/cn_data（容器内 /root/.qlib/qlib_data/cn_data），
# 从不读 /home/zxh/qlib_data，该软链是冗余的。且当宿主也有软链 ~/.qlib/qlib_data/cn_data
# -> /home/zxh/qlib_data 时，三者叠加会形成符号链接死循环，故删除。
# 数据挂载改由 QlibDockerConf.extra_volumes 直接把宿主 /home/zxh/qlib_data 挂到
# 容器 /root/.qlib/qlib_data/cn_data（见 rdagent/utils/env.py QlibDockerConf）。
