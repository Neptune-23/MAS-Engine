import os
from pathlib import Path
from dotenv import load_dotenv

env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "127.0.0.1"),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "agent_db"),
    "charset": os.getenv("DB_CHARSET", "utf8mb4")
}

CACHE_TTL = int(os.getenv("CACHE_TTL", "5"))
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
