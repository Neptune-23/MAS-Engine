import os
from pathlib import Path
from dotenv import load_dotenv

# 加载 .env
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)

def get_db_config():
    """获取数据库配置"""
    return {
        "host": os.getenv("DB_HOST", "127.0.0.1"),
        "user": os.getenv("DB_USER", "root"),
        "password": os.getenv("DB_PASSWORD", "0000"),
        "database": os.getenv("DB_NAME", "agent_db"),
        "charset": os.getenv("DB_CHARSET", "utf8mb4")
    }