import os
from pathlib import Path

from dotenv import load_dotenv

# 项目根路径定位
BASE_DIR = Path(__file__).resolve().parent.parent

# 优先加载根目录下的 .env
env_path = BASE_DIR / ".env"
if env_path.exists():
    load_dotenv(env_path)
else:
    load_dotenv()

# ============================================================
# 数据库配置（带强默认值与环境隔离）
# ============================================================
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "127.0.0.1"),
    "port": int(os.getenv("DB_PORT", "3306")),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", "0000"),
    "database": os.getenv("DB_NAME", "agent_db"),
    "charset": os.getenv("DB_CHARSET", "utf8mb4"),
    "connect_timeout": int(os.getenv("DB_TIMEOUT", "5")),
}

# ============================================================
# 引擎与缓存参数
# ============================================================
ENGINE_CONFIG = {
    "cache_ttl": int(os.getenv("CACHE_TTL", "5")),
    "max_self_healing_retries": int(os.getenv("MAX_HEALING_RETRIES", "3")),
    "code_slice_context_window": int(os.getenv("CODE_SLICE_WINDOW", "15")),
}

# ============================================================
# 目录路径常量
# ============================================================
LOGS_DIR = BASE_DIR / "logs"
REFERENCES_DIR = BASE_DIR / "references"
TEMPLATES_DIR = BASE_DIR / "assets" / "templates"

LOGS_DIR.mkdir(exist_ok=True)
