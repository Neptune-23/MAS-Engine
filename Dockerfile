FROM python:3.11-slim

# 设置工作目录与环境变量
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# 安装系统级基础依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖与项目配置
COPY pyproject.toml README.md ./
COPY config/ config/
COPY mcp-server/ mcp-server/
COPY tools/ tools/
COPY utils/ utils/
COPY references/ references/
COPY tests/ tests/
COPY scripts/ scripts/

# 安装 Python 依赖及开发套件
RUN pip install --no-cache-dir -e ".[dev]"

# 默认执行全量单元测试
CMD ["pytest", "-v"]