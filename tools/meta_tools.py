# tools/meta_tools.py
import json
import sys
from pathlib import Path
from datetime import datetime
from mcp.server.fastmcp import FastMCP
from state_machine import TaskStateMachine, AgentState
from tool_dispatcher import DynamicToolDispatcher

# 这些变量将在 server.py 中设置
mcp = None
state_machine = None
REFS_DIR = None
logger = None
agent_message_queue = None
message_lock = None
send_message = None
validate_path = None

def init_meta_tools(mcp_instance, state_machine_instance, refs_dir, logger_instance,
                    agent_queue, msg_lock, send_msg_func, validate_func):
    """注入依赖"""
    global mcp, state_machine, REFS_DIR, logger, agent_message_queue, message_lock, send_message, validate_path
    mcp = mcp_instance
    state_machine = state_machine_instance
    REFS_DIR = refs_dir
    logger = logger_instance
    agent_message_queue = agent_queue
    message_lock = msg_lock
    send_message = send_msg_func
    validate_path = validate_func


def search_tools_impl(task_id: str, query: str = "", category: str = "", role: str = "developer") -> str:
    """搜索工具的实现"""
    tools_catalog = {
        "orchestrate_task": {
            "category": "meta",
            "description": "任务编排入口：接收自然语言任务描述，自动设置状态和角色",
            "roles": ["developer", "reviewer", "tester", "analyst", "architect", "fixer"]
        },
        "analyze_project_structure": {
            "category": "project",
            "description": "扫描项目根目录，识别技术栈指纹，返回语言、包管理器和构建工具信息",
            "roles": ["developer", "reviewer", "tester", "analyst", "architect"]
        },
        "infer_build_steps": {
            "category": "project",
            "description": "根据项目指纹 JSON 推理构建、测试、启动命令序列",
            "roles": ["developer", "reviewer", "tester", "analyst", "architect"]
        },
        "get_next_message": {
            "category": "meta",
            "description": "获取发给当前角色的下一条消息（Agent 间通信）",
            "roles": ["developer", "reviewer", "tester", "analyst", "architect", "fixer"]
        },
        "run_web_audit": {
            "category": "quality",
            "description": "全自动网页审查引擎。能够自动打开网页并监听 Console 报错、Network 请求失败，并生成页面截图。",
            "roles": ["developer", "tester"]
        },
        "search_tools": {
            "category": "meta",
            "description": "搜索所有可用的 MCP 工具",
            "roles": ["developer", "reviewer", "tester", "analyst", "architect", "fixer"]
        },
        "get_tool_details": {
            "category": "meta",
            "description": "获取指定工具的完整定义（参数、返回格式、示例）",
            "roles": ["developer", "reviewer", "tester", "analyst", "architect", "fixer"]
        },
        "get_rules": {
            "category": "project",
            "description": "获取开发红线规则",
            "roles": ["developer", "reviewer", "tester", "analyst"]
        },
        "get_pipeline_status": {
            "category": "quality",
            "description": "查询异步流水线任务的执行状态",
            "roles": ["developer", "reviewer", "tester", "fixer"]
        },
        "scan_code_batch": {
            "category": "quality",
            "description": "分批扫描代码，检查 console.log、选项式 API、命名问题",
            "roles": ["developer", "reviewer", "tester"]
        },
        "scan_backend_batch": {
            "category": "backend",
            "description": "分批扫描 ThinkPHP 后端代码，检查 SQL 注入、硬编码密码等",
            "roles": ["developer", "reviewer", "tester"]
        },
        "scan_admin_batch": {
            "category": "admin",
            "description": "分批扫描 FastAdmin 后台代码，检查插件规范、权限、SQL 注入等",
            "roles": ["developer", "reviewer", "tester"]
        },
        "batch_fix_console_logs": {
            "category": "fix",
            "description": "批量修复多个文件中的 console.log，添加环境判断",
            "roles": ["developer", "tester", "fixer"]
        },
        "batch_fix_backend_issues": {
            "category": "backend",
            "description": "批量修复后端问题（标记硬编码密码、移除 echo/dump、注释 die/exit）",
            "roles": ["developer", "tester", "fixer"]
        },
        "run_quality_pipeline": {
            "category": "quality",
            "description": "全自动质量检查流水线（异步），包含扫描、修复、验证",
            "roles": ["developer", "reviewer", "tester", "fixer"]
        },
        "run_backend_pipeline": {
            "category": "backend",
            "description": "全自动后端质量检查流水线（异步），包含扫描、修复、验证",
            "roles": ["developer", "reviewer", "tester", "fixer"]
        },
        "run_admin_pipeline": {
            "category": "admin",
            "description": "全自动后台质量检查流水线（异步），包含扫描、验证",
            "roles": ["developer", "reviewer", "tester", "fixer"]
        },
        "check_code_quality": {
            "category": "quality",
            "description": "【已弃用】深度质量检查（可能超时），请改用 scan_code_batch",
            "roles": ["developer", "reviewer", "tester"]
        },
        "run_code_check": {
            "category": "quality",
            "description": "【已弃用】Prettier 格式检查（可能超时），请改用 run_quality_pipeline",
            "roles": ["developer", "reviewer", "tester"]
        }
    }

    all_tools_list = [
        {"name": name, "description": info.get("description", "")}
        for name, info in tools_catalog.items()
    ]

    task_data = state_machine.get_task_state(task_id)
    if task_data and task_data.get('current_state'):
        current_state = task_data['current_state']
    else:
        current_state = AgentState.REQUIREMENT_EXTRACTION

    dispatcher = DynamicToolDispatcher(all_tools_list)
    active_tools_from_state = dispatcher.get_active_tools_for_state(current_state, role=role)
    allowed_tool_names = [t["name"] for t in active_tools_from_state]

    results = []
    for name, info in tools_catalog.items():
        if name not in allowed_tool_names:
            continue
        if role not in info.get("roles", ["developer"]):
            continue
        if category and info["category"] != category:
            continue
        if query:
            query_lower = query.lower()
            if query_lower not in name.lower() and query_lower not in info["description"].lower():
                continue
        results.append(f"- **{name}** ({info['category']}): {info['description']}")

    if not results:
        return (
            f"💡 [状态机拦截] 未找到匹配的工具。\n"
            f"⚠️ 注意：当前任务处于【{current_state}】阶段，角色【{role}】仅允许部分工具。\n"
            f"可用分类：template, project, quality, fix, backend, admin\n"
            f"当前角色：{role}"
        )

    return f"找到 {len(results)} 个可用工具（当前状态：{current_state} | 角色：{role}）：\n\n" + "\n".join(results)


def get_tool_details_impl(tool_name: str) -> str:
    """获取工具详情的实现"""
    tool_schemas = {
        "scan_code_batch": {
            "description": "分批扫描 Vue/uni-app 项目的代码质量问题",
            "parameters": {
                "project_path": "项目的绝对路径",
                "offset": "从第几个文件开始扫描（默认 0）",
                "limit": "本次扫描多少个文件（建议 20-30）"
            },
            "returns": "扫描进度、本批次发现的问题列表、下一个 offset",
            "example": 'scan_code_batch(project_path="D:/workspace/test-vue-app", offset=0, limit=20)'
        },
        "batch_fix_console_logs": {
            "description": "批量修复多个文件中的 console.log，自动添加环境判断",
            "parameters": {
                "file_paths": '要修复的文件绝对路径列表',
                "dry_run": "True 为预览，False 为执行"
            },
            "returns": "修复报告，包含已修复和跳过的文件数",
            "example": 'batch_fix_console_logs(file_paths=["D:/workspace/index.vue"], dry_run=False)'
        },
        "run_quality_pipeline": {
            "description": "全自动质量检查流水线（异步），立即返回任务 ID",
            "parameters": {
                "project_path": "项目的绝对路径",
                "fix": "是否自动修复发现的问题（True/False）"
            },
            "returns": "任务 ID，用于后续查询状态",
            "example": 'run_quality_pipeline(project_path="D:/workspace/test-vue-app", fix=True)'
        },
        "get_pipeline_status": {
            "description": "查询异步流水线任务的执行状态和结果",
            "parameters": {
                "task_id": "run_quality_pipeline 返回的任务 ID"
            },
            "returns": "任务状态（pending/running/completed/failed）和结果"
        },
        "get_rules": {
            "description": "获取开发红线规则",
            "parameters": {},
            "returns": "完整的红线规则文档",
            "example": 'get_rules()'
        },
        "get_next_message": {
            "description": "获取发给当前角色的下一条消息（Agent 间通信）",
            "parameters": {
                "task_id": "当前任务 ID",
                "role": "当前角色"
            },
            "returns": "下一条消息的 JSON 格式内容",
            "example": 'get_next_message(task_id="test_001", role="tester")'
        },
        "orchestrate_task": {
            "description": "任务编排入口：接收自然语言任务描述，自动设置状态和角色",
            "parameters": {
                "task_id": "任务的唯一标识 ID",
                "description": "自然语言任务描述"
            },
            "returns": "任务编排结果，包含任务 ID、推断类型、当前状态、当前角色和下一步建议",
            "example": 'orchestrate_task(task_id="test_001", description="创建一个用户登录页面")'
        },
        "analyze_project_structure": {
            "description": "扫描项目根目录，识别技术栈指纹",
            "parameters": {
                "project_path": "项目的绝对路径"
            },
            "returns": "技术栈指纹 JSON",
            "example": 'analyze_project_structure(project_path="D:/project")'
        },
        "infer_build_steps": {
            "description": "根据项目指纹 JSON 推理构建、测试、启动命令序列",
            "parameters": {
                "fingerprint_json": "analyze_project_structure 返回的 JSON 字符串"
            },
            "returns": "构建步骤 JSON",
            "example": 'infer_build_steps(fingerprint_json="...")'
        }
    }

    if tool_name not in tool_schemas:
        available = ", ".join(tool_schemas.keys())
        return f"❌ 未找到工具 '{tool_name}'。可用工具：{available}"

    schema = tool_schemas[tool_name]
    result = f"📋 工具：{tool_name}\n"
    result += f"📝 描述：{schema['description']}\n"
    if schema.get('parameters'):
        result += f"📌 参数：\n"
        for param, desc in schema['parameters'].items():
            result += f"  - {param}: {desc}\n"
    else:
        result += "📌 无参数\n"
    result += f"📤 返回：{schema.get('returns', '无描述')}\n"
    if schema.get('example'):
        result += f"💡 示例：{schema['example']}\n"
    return result


def orchestrate_task_impl(task_id: str, description: str) -> str:
    """任务编排入口实现"""
    logger.info(f"[Orchestrator] 收到任务: {description}")

    task_type = "unknown"
    if any(kw in description for kw in ["创建", "新建", "生成", "开发"]):
        task_type = "construction"
        state_machine.update_task_state(
            task_id,
            AgentState.CODE_CONSTRUCTION,
            {"task_type": task_type, "description": description, "current_role": "developer"}
        )
        send_message(
            from_role="developer",
            to_role="tester",
            action="code_ready",
            payload={"task_id": task_id, "description": description}
        )
        logger.info(f"[Orchestrator] 已通知 tester 角色进行测试")
    elif any(kw in description for kw in ["测试", "验证", "检查", "audit"]):
        task_type = "testing"
        state_machine.update_task_state(
            task_id,
            AgentState.WEB_TESTING,
            {"task_type": task_type, "description": description, "current_role": "tester"}
        )
    elif any(kw in description for kw in ["修复", "解决", "fix"]):
        task_type = "healing"
        state_machine.update_task_state(
            task_id,
            AgentState.SELF_HEALING,
            {"task_type": task_type, "description": description, "current_role": "fixer"}
        )
    else:
        task_type = "unknown"
        state_machine.update_task_state(
            task_id,
            AgentState.REQUIREMENT_ANALYSIS,
            {"task_type": task_type, "description": description, "current_role": "analyst"}
        )

    task_data = state_machine.get_task_state(task_id)
    current_state = task_data.get("current_state")
    current_role = task_data.get("context", {}).get("current_role", "developer")

    return f"""
🧠 任务编排完成：
   - 任务 ID: {task_id}
   - 描述: {description}
   - 推断类型: {task_type}
   - 当前状态: {current_state}
   - 当前角色: {current_role}
   - 下一步：请使用 search_tools(task_id="{task_id}", role="{current_role}") 查看可用工具
"""


def get_next_message_impl(task_id: str, role: str) -> str:
    """获取下一条消息的实现"""
    with message_lock:
        for i, msg in enumerate(agent_message_queue):
            if msg["to"] == role:
                if msg.get("payload", {}).get("task_id") == task_id:
                    agent_message_queue.pop(i)
                    return json.dumps(msg, indent=2, ensure_ascii=False)
        return "暂无消息"


def auto_respond_impl(task_id: str, role: str) -> str:
    """自动响应消息的实现"""
    msg_result = get_next_message_impl(task_id, role)

    if msg_result == "暂无消息":
        return "📭 暂无待响应的消息"

    try:
        msg = json.loads(msg_result)
    except json.JSONDecodeError:
        return f"❌ 无法解析消息: {msg_result}"

    action = msg.get("action")
    payload = msg.get("payload", {})
    from_role = msg.get("from")

    logger.info(f"[AutoRespond] 角色 {role} 收到来自 {from_role} 的动作: {action}")

    if action == "code_ready":
        project_path = payload.get("project_path")
        if not project_path:
            return "❌ 消息缺少 project_path 参数"

        logger.info(f"[AutoRespond] 自动触发网页测试: {project_path}")
        test_url = "http://localhost:5173"
        # 注意：这里需要调用 run_web_audit_impl，但为了避免循环导入，可以在 server.py 中注入
        # 由于 run_web_audit_impl 在 pipeline_tools 中，这里先返回提示
        return "✅ 已自动响应 code_ready 动作，但 run_web_audit_impl 尚未注入。"
    elif action == "reverify":
        project_path = payload.get("project_path")
        if not project_path:
            return "❌ 消息缺少 project_path 参数"
        logger.info(f"[AutoRespond] 自动触发重新验证: {project_path}")
        return "✅ 已自动响应 reverify 动作，但 run_quality_pipeline_impl 尚未注入。"
    elif action == "test_complete":
        state_machine.update_task_state(
            task_id,
            AgentState.DELIVERY_COMPLETED,
            {"test_result": payload.get("result"), "completed_by": role}
        )
        return f"✅ 测试已完成，任务 {task_id} 流转至 DELIVERY_COMPLETED 状态。"
    else:
        return f"⚠️ 未知动作: {action}，请手动处理。"


def get_rules_impl(task_id: str = None, language: str = None) -> str:
    """获取开发规则（编码规范 + 诊断规则）—— 返回纯 JSON"""

    # 1. 收集 Markdown 规范
    markdown_parts = []

    common_rules = REFS_DIR / "common" / "best_practices.md"
    if common_rules.exists():
        with open(common_rules, "r", encoding="utf-8") as f:
            markdown_parts.append(f"## 通用规则\n{f.read()}\n")
    else:
        old_rule = REFS_DIR / "mandatory-rules.md"
        if old_rule.exists():
            with open(old_rule, "r", encoding="utf-8") as f:
                markdown_parts.append(f"## 开发规则\n{f.read()}\n")

    if language:
        # 语言名称规范化（映射到文件夹名）
        lang_to_dir = {
            "node.js": "nodejs",
            "nodejs": "nodejs",
            "javascript": "nodejs",
            "python": "python",
            "php": "php",
            "thinkphp": "php",
            "vue": "frontend",
            "react": "frontend",
            "rust": "rust",   # 注意：Rust 文件夹可能不存在，但为了诊断规则我们单独处理
        }
        lang_dir = lang_to_dir.get(language.lower(), language.lower())

        possible_files = ["style_guide.md", "eslint_rules.md", "rules.md"]
        for fname in possible_files:
            lang_rules = REFS_DIR / lang_dir / fname
            if lang_rules.exists():
                with open(lang_rules, "r", encoding="utf-8") as f:
                    markdown_parts.append(f"## {language} 特定规则\n{f.read()}\n")
                break
        else:
            if language.lower() in ["php", "thinkphp"]:
                backend_rules = REFS_DIR / "mandatory-rules-backend.md"
                if backend_rules.exists():
                    with open(backend_rules, "r", encoding="utf-8") as f:
                        markdown_parts.append(f"## PHP 特定规则\n{f.read()}\n")
            elif language.lower() in ["javascript", "nodejs", "vue", "react"]:
                frontend_rules = REFS_DIR / "frontend" / "vue_rules.md"
                if frontend_rules.exists():
                    with open(frontend_rules, "r", encoding="utf-8") as f:
                        markdown_parts.append(f"## JavaScript 特定规则\n{f.read()}\n")

    markdown_content = "\n\n".join(markdown_parts) if markdown_parts else "未找到任何规则文件"

    # 2. 读取诊断规则
    diagnostic_file = REFS_DIR / "diagnostic_rules.json"
    diagnostic_rules = {}
    if diagnostic_file.exists():
        try:
            with open(diagnostic_file, "r", encoding="utf-8") as f:
                all_rules = json.load(f)
                # 规范化语言名称：将 language 转换为 JSON 中的键（例如 "rust" -> "Rust"）
                if language:
                    # 尝试匹配常见写法
                    key_map = {
                        "rust": "Rust",
                        "nodejs": "Node.js",
                        "python": "Python",
                        "javascript": "Node.js",
                        "php": "PHP",
                        "vue": "Vue",
                        "react": "React",
                    }
                    lang_key = key_map.get(language.lower(), language.capitalize())
                    if lang_key in all_rules:
                        diagnostic_rules = all_rules[lang_key]
                    else:
                        # 如果找不到精确匹配，直接返回所有规则
                        diagnostic_rules = all_rules
                else:
                    diagnostic_rules = all_rules
        except Exception as e:
            diagnostic_rules = {"error": f"加载诊断规则失败: {str(e)}"}
    else:
        diagnostic_rules = {"error": "诊断规则文件未找到，请创建 references/diagnostic_rules.json"}

    # 3. 构造返回 JSON
    result = {
        "markdown": markdown_content,
        "diagnostic_rules": diagnostic_rules
    }
    return json.dumps(result, indent=2, ensure_ascii=False)