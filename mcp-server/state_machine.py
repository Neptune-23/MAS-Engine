import time
import json
import os
import sys
from typing import Optional, Dict, Any
from pathlib import Path

try:
    import pymysql
except ImportError:
    pymysql = None

try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
    else:
        load_dotenv()
except ImportError:
    pass


def _log(msg: str):
    """输出到 stderr，不影响 MCP stdio 通信"""
    sys.stderr.write(f"[StateMachine] {msg}\n")
    sys.stderr.flush()


class AgentState:
    REQUIREMENT_EXTRACTION = "requirement_extraction"
    REQUIREMENT_ANALYSIS = "requirement_analysis"
    RESOURCE_LOADING = "resource_loading"
    CODE_CONSTRUCTION = "code_construction"
    WEB_TESTING = "web_testing"
    SELF_HEALING = "self_healing"
    DELIVERY_COMPLETED = "delivery_completed"
    HUMAN_INTERRUPT = "human_interrupt"


class TaskStateMachine:
    def __init__(self, db_config: Optional[Dict[str, Any]] = None):
        if db_config:
            self.host = db_config.get("host", "127.0.0.1")
            self.user = db_config.get("user", "root")
            self.password = db_config.get("password", "")
            self.database = db_config.get("database", "agent_db")
            self.charset = db_config.get("charset", "utf8mb4")
        else:
            self.host = os.getenv("DB_HOST", "127.0.0.1")
            self.user = os.getenv("DB_USER", "root")
            self.password = os.getenv("DB_PASSWORD", "")
            self.database = os.getenv("DB_NAME", "agent_db")
            self.charset = os.getenv("DB_CHARSET", "utf8mb4")

        self._cache = {}
        self._cache_ttl = int(os.getenv("CACHE_TTL", "5"))
        self._db_available = False
        self._db_error = None

        # 在初始化时打印连接参数（密码脱敏）
        _log(f"初始化数据库连接: host={self.host}, user={self.user}, database={self.database}")
        self._ensure_table()

    def _get_connection(self):
        if pymysql is None:
            raise ImportError("pymysql not installed")
        return pymysql.connect(
            host=self.host,
            user=self.user,
            password=self.password,
            database=self.database,
            charset=self.charset,
            autocommit=True,
            connect_timeout=5
        )

    def _ensure_table(self):
        _log("_ensure_table 被调用")
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS task_states (
                    task_id VARCHAR(64) PRIMARY KEY,
                    current_state VARCHAR(64) NOT NULL,
                    context JSON DEFAULT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    INDEX idx_current_state (current_state)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            conn.close()
            self._db_available = True
            self._db_error = None
            _log("数据库连接成功，表已就绪，_db_available 设为 True")
        except Exception as e:
            self._db_available = False
            self._db_error = str(e)
            _log(f"警告：数据库连接失败，将降级为内存存储。错误: {e}")

    def _get_from_db(self, task_id: str):
        if not self._db_available:
            _log(f"_get_from_db: _db_available=False，跳过查询")
            return None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT current_state, context FROM task_states WHERE task_id = %s",
                (task_id,)
            )
            row = cursor.fetchone()
            conn.close()
            if row:
                context = {}
                if row[1]:
                    try:
                        context = json.loads(row[1])
                    except json.JSONDecodeError:
                        context = {}
                _log(f"_get_from_db: 找到 task_id={task_id}, state={row[0]}")
                return {"current_state": row[0], "context": context}
            else:
                _log(f"_get_from_db: 未找到 task_id={task_id}")
            return None
        except Exception as e:
            _log(f"查询失败: {e}")
            self._db_available = False
            return None

    def _update_db(self, task_id: str, state: str, context: Dict[str, Any]):
        _log(f"_update_db 被调用: task_id={task_id}, state={state}, _db_available={self._db_available}")
        if not self._db_available:
            _log("_db_available=False，跳过写入")
            return False
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            sql = """INSERT INTO task_states (task_id, current_state, context)
                     VALUES (%s, %s, %s)
                     ON DUPLICATE KEY UPDATE
                     current_state = VALUES(current_state),
                     context = VALUES(context)"""
            cursor.execute(
                sql,
                (task_id, state, json.dumps(context, ensure_ascii=False))
            )
            _log(f"SQL 执行成功，影响行数: {cursor.rowcount}")
            conn.close()
            return True
        except Exception as e:
            _log(f"更新失败: {e}")
            self._db_available = False
            return False

    def get_task_state(self, task_id: str):
        _log(f"get_task_state 被调用: task_id={task_id}")
        if task_id in self._cache:
            cached = self._cache[task_id]
            if time.time() - cached["timestamp"] < self._cache_ttl:
                _log(f"从缓存返回: state={cached['state']}")
                return {"current_state": cached["state"], "context": cached.get("context", {})}
            else:
                del self._cache[task_id]

        result = self._get_from_db(task_id)
        if result is None:
            return None

        self._cache[task_id] = {
            "state": result["current_state"],
            "context": result.get("context", {}),
            "timestamp": time.time()
        }
        return result

    def update_task_state(self, task_id: str, state: str, context: Optional[Dict[str, Any]] = None):
        context = context or {}
        _log(f"update_task_state 被调用: task_id={task_id}, state={state}")
        success = self._update_db(task_id, state, context)
        self._cache[task_id] = {
            "state": state,
            "context": context,
            "timestamp": time.time()
        }
        _log(f"update_task_state 完成, success={success}")
        return success

    def is_db_available(self) -> bool:
        return self._db_available

    def get_db_error(self) -> Optional[str]:
        return self._db_error

    def clear_cache(self, task_id: Optional[str] = None):
        if task_id:
            self._cache.pop(task_id, None)
        else:
            self._cache.clear()

    def health_check(self) -> Dict[str, Any]:
        return {
            "db_available": self._db_available,
            "db_error": self._db_error,
            "cache_size": len(self._cache),
            "cache_ttl": self._cache_ttl
        }