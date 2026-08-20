# memory.py
import sys
from pathlib import Path

# 将项目根目录添加到 Python 路径（让 config 可导入）
sys.path.insert(0, str(Path(__file__).parent.parent))

import hashlib
import re
import json
import pymysql
from config.settings import DB_CONFIG

# ============================================================
# 1. 错误签名生成算法
# ============================================================
def generate_error_signature(task_type: str, stderr: str) -> str:
    if not stderr:
        return f"{task_type}_unknown_error"

    # 1. 将错误信息转为小写，并移除反引号、换行符等干扰
    clean_stderr = stderr.lower().replace("`", "").replace("\n", " ")

    # 2. 定义关键错误词库（覆盖更多情况）
    patterns = {
        "linker_missing": r"link\.exe not found|linker 'cc' not found|linker `link\.exe` not found",
        "dependency_conflict": r"failed to select a version for",
        "cargo_toml_missing": r"could not find `cargo\.toml`",
        "json_parse_error": r"npm error code ejsonparse|invalid package\.json",
        "python_module_missing": r"modulenotfounderror|no module named",
        "cargo_not_installed": r"cargo not found|'cargo' .* not recognized",
        "npm_not_installed": r"npm not found|'npm' .* not recognized",
        "toml_format_error": r"unexpected key or value|expected newline, `#`",
    }

    error_keyword = "unknown_error"
    for keyword, pattern in patterns.items():
        if re.search(pattern, clean_stderr, re.IGNORECASE):
            error_keyword = keyword
            break

    return f"{task_type}_{error_keyword}"


# ============================================================
# 2. 记忆写入函数
# ============================================================
def save_memory_record(task_type: str, stderr: str, fix_command: str, fix_description: str, tags: list):
    try:
        # 生成签名
        error_signature = generate_error_signature(task_type, stderr)
        
        conn = pymysql.connect(
            host=DB_CONFIG["host"],
            user=DB_CONFIG["user"],
            password=DB_CONFIG["password"],
            database=DB_CONFIG["database"],
            charset=DB_CONFIG["charset"],
            autocommit=True
        )
        cursor = conn.cursor()
        sql = """
            INSERT INTO memory_records 
            (task_type, error_signature, error_message, fix_command, fix_description, tags, last_used_at) 
            VALUES (%s, %s, %s, %s, %s, %s, NOW())
        """
        tags_json = json.dumps(tags)
        cursor.execute(sql, (task_type, error_signature, stderr[:500], fix_command, fix_description, tags_json))
        conn.close()
        print(f"[Memory] 成功记录记忆: {error_signature}")
        return True
    except Exception as e:
        print(f"[Memory] 记忆写入失败: {e}")
        return False


# ============================================================
# 3. 检索与匹配引擎（第二阶段核心）
# ============================================================
def get_memory_by_signature(task_type: str, error_signature: str):
    """第一层：按错误签名精确匹配"""
    try:
        conn = pymysql.connect(
            host=DB_CONFIG["host"],
            user=DB_CONFIG["user"],
            password=DB_CONFIG["password"],
            database=DB_CONFIG["database"],
            charset=DB_CONFIG["charset"],
            autocommit=True
        )
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        sql = """
            SELECT * FROM memory_records 
            WHERE task_type = %s AND error_signature = %s
            ORDER BY success_count DESC, last_used_at DESC
            LIMIT 1
        """
        cursor.execute(sql, (task_type, error_signature))
        row = cursor.fetchone()
        conn.close()
        return row
    except Exception as e:
        print(f"[Memory] 精确检索失败: {e}")
        return None

def get_memory_by_tags(task_type: str, tags: list):
    if not tags:
        return []
    try:
        conn = pymysql.connect(
            host=DB_CONFIG["host"],
            user=DB_CONFIG["user"],
            password=DB_CONFIG["password"],
            database=DB_CONFIG["database"],
            charset=DB_CONFIG["charset"],
            autocommit=True
        )
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        # 使用 JSON_CONTAINS 匹配任意一个标签（MySQL 5.7+ 支持）
        # 构造多个 OR 条件，每个条件使用参数化占位符
        conditions = []
        params = [task_type]
        for tag in tags:
            conditions.append("JSON_CONTAINS(tags, %s, '$')")
            params.append(json.dumps(tag))
        sql = f"""
            SELECT * FROM memory_records 
            WHERE task_type = %s AND ({' OR '.join(conditions)})
            ORDER BY success_count DESC, last_used_at DESC
            LIMIT 3
        """
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        conn.close()
        return rows
    except Exception as e:
        print(f"[Memory] 标签检索失败: {e}")
        return []

def retrieve_memory(task_type: str, error_message: str, environment_tags: list = None, top_k: int = 3):
    """记忆检索路由（三层匹配逻辑）"""
    if environment_tags is None:
        environment_tags = []

    # 1. 生成签名并精确匹配
    error_signature = generate_error_signature(task_type, error_message)
    print(f"[Memory] 检索签名: {error_signature}")
    
    exact_match = get_memory_by_signature(task_type, error_signature)
    if exact_match:
        print("[Memory] ✅ 命中精确匹配")
        return [exact_match]

    # 2. 标签过滤（兜底检索）
    print("[Memory] 🔍 未命中精确匹配，尝试标签过滤...")
    tag_matches = get_memory_by_tags(task_type, environment_tags)
    if tag_matches:
        print(f"[Memory] ✅ 命中标签匹配，找到 {len(tag_matches)} 条记录")
        return tag_matches

    # 3. 语义相似度检索（预留未来扩展）
    print("[Memory] ⚠️ 未找到匹配记录")
    return []