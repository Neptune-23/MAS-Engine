import sys
import os
import shutil
import subprocess
import threading
import uuid
import time
import logging
import json
from playwright.sync_api import sync_playwright
from datetime import datetime
from pathlib import Path
from mcp.server.fastmcp import FastMCP
# 引入我们刚刚写的模块
from state_machine import TaskStateMachine, AgentState
from tool_dispatcher import DynamicToolDispatcher
from tool_dispatcher import AgentRole  # 新增
from functools import wraps

# Agent 间消息协议（内存队列）
agent_message_queue = []
message_lock = threading.Lock()

def send_message(from_role: str, to_role: str, action: str, payload: dict):
    """发送 Agent 间消息（内存队列）"""
    with message_lock:
        agent_message_queue.append({
            "from": from_role,
            "to": to_role,
            "action": action,
            "payload": payload,
            "timestamp": datetime.now().isoformat()
        })

def validate_path(func):
    """
    装饰器：自动校验工具中的 project_path 参数是否安全。
    如果参数名不是 project_path，则跳过校验。
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        # 获取 project_path 参数（如果存在）
        project_path = kwargs.get("project_path")
        if project_path is None:
            # 尝试从位置参数获取（需要函数签名支持）
            import inspect
            sig = inspect.signature(func)
            param_names = list(sig.parameters.keys())
            if "project_path" in param_names:
                idx = param_names.index("project_path")
                if idx < len(args):
                    project_path = args[idx]
        
        # 如果存在 project_path 参数，进行校验
        if project_path:
            if not validate_project_path(project_path):
                return f"❌ 安全拦截：路径 {project_path} 被系统保护，禁止操作。"
        
        # 执行原函数
        return func(*args, **kwargs)
    return wrapper

# ---------- 安全校验 ----------
def validate_project_path(project_path: str) -> bool:
    """检查路径是否安全（禁止操作 mcp-server 等系统目录）"""
    path = Path(project_path).resolve()
    # 系统保护目录列表（绝对路径）
    forbidden = [
        BASE_DIR / "mcp-server",
        BASE_DIR / "assets",
        BASE_DIR / "references",
        BASE_DIR / "skills",
        BASE_DIR / "logs",
        BASE_DIR / ".venv"
    ]
    for f in forbidden:
        if path == f or f in path.parents:
            return False
    return True

# 任务存储
pipeline_tasks = {}
task_lock = threading.Lock()

# 初始化 MCP 服务器（必须用 FastMCP）
mcp = FastMCP("Company Dev Toolkit")

# 获取当前脚本所在的根目录（自动定位到 company-ai-toolkit）
BASE_DIR = Path(__file__).parent.parent
TEMPLATES_DIR = BASE_DIR / "assets" / "templates"
REFS_DIR = BASE_DIR / "references"

# ---------- 日志配置 ----------
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(name)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.FileHandler(LOG_DIR / "mcp.log", encoding='utf-8'),
        logging.StreamHandler(sys.stderr)
    ],
    force=True   # 强制重新配置，避免被其他模块修改
)

logger = logging.getLogger("company-mcp")

# ========== P2 架构初始化 ==========
# --- 数据库配置（用于状态持久化） ---
DB_CONFIG = {
    "host": "127.0.0.1",
    "user": "root",
    "password": "0000",  # 记得填上你本地的密码
    "database": "agent_db",
    "charset": "utf8mb4"
}

# 🔴 修复1：加上这行实例化代码！
state_machine = TaskStateMachine(DB_CONFIG)

# ---------- 工具 1: 列出所有可用的模板 ----------
@mcp.tool()
def list_templates() -> str:
    """列出当前工具箱里所有可用的项目模板（前端、后端、后台）"""
    if not TEMPLATES_DIR.exists():
        return "错误：模板目录不存在！"
    
    templates = [d.name for d in TEMPLATES_DIR.iterdir() if d.is_dir()]
    if not templates:
        return "当前没有找到任何模板，请先将模板放入 assets/templates/ 下"
    
    return "可用的模板列表：\n" + "\n".join([f"- {t}" for t in templates])

# ---------- 测试类：Web 自动化测试闭环 (Playwright 引擎) ----------
@mcp.tool()
def run_web_audit(task_id: str, url: str, wait_time: int = 3) -> str:
    """
    全自动网页审查工具（Playwright 引擎）。
    Agent 可调用此工具自动打开指定的网页，监听并截获 Console 报错、Network 异常，并自动网页截图。
    
    Args:
        task_id: 当前任务的唯一标识 ID
        url: 需要测试的网页地址 (例如: http://localhost:5173 或 http://127.0.0.1:8000)
        wait_time: 页面加载后等待的秒数（默认 3 秒），用于等待异步请求或动画渲染完成
    """
    # 1. 严格的状态机越权拦截
    task_data = state_machine.get_task_state(task_id)
    if task_data and task_data.get('current_state'):
        current_state = task_data['current_state']
        # 规定：只有在 Web测试 或 自我修复 阶段，才允许大模型调用浏览器工具
        if current_state not in [AgentState.WEB_TESTING, AgentState.SELF_HEALING]:
            return f"⛔ [状态机拦截] 越权操作！当前处于【{current_state}】阶段。必须流转至 WEB_TESTING 阶段方可执行网页测试。"

    logger.info(f"[Playwright] 启动自动化审计，目标网页: {url}")
    
    # 初始化结构化诊断包
    diagnostics = {
        "url": url,
        "status": "success",
        "page_title": "",
        "console_errors": [],
        "network_errors": [],
        "screenshot_path": ""
    }

    try:
        with sync_playwright() as p:
            # 默认 headless=True (无头模式，不在电脑上弹浏览器窗口，纯后台跑)
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(viewport={'width': 1280, 'height': 720})
            page = context.new_page()

            # 🚀 核心：挂载事件监听器，截获所有的报错！
            # 1. 抓取 Console 控制台输出（过滤出 error 类型）
            page.on("console", lambda msg: diagnostics["console_errors"].append(f"[{msg.type}] {msg.text}") if msg.type == "error" else None)
            # 2. 抓取 Network 网络请求（截获 4xx 和 5xx 状态码）
            page.on("response", lambda response: diagnostics["network_errors"].append(f"[{response.status}] {response.url}") if response.status >= 400 else None)

            # 访问指定网页，等待网络空闲
            page.goto(url, wait_until="networkidle", timeout=20000)
            
            # 强制等待，让前端的异步 Ajax 请求和渲染彻底跑完
            time.sleep(wait_time)
            
            diagnostics["page_title"] = page.title()

            # 📸 截取当前网页快照（物理存盘，将来用于 Computer Use 视觉兜底）
            screenshot_name = f"audit_{task_id}_{int(time.time())}.png"
            screenshot_path = LOG_DIR / screenshot_name
            page.screenshot(path=str(screenshot_path))
            diagnostics["screenshot_path"] = str(screenshot_path)

            browser.close()

    except Exception as e:
        diagnostics["status"] = "failed"
        diagnostics["error_message"] = f"网页访问失败: {str(e)}"
        logger.error(f"[Playwright Error] {e}")

    # 封装返回结果，这部分数据将直接喂给大模型的大脑
    summary = f"🌐 网页审计完成: {url}\n"
    summary += f"📄 页面标题: {diagnostics['page_title']}\n"
    summary += f"📸 页面截图已存至: {diagnostics['screenshot_path']}\n\n"
    
    if diagnostics["console_errors"] or diagnostics["network_errors"] or diagnostics["status"] == "failed":
        summary += "⚠️ 【检测到页面异常】\n"
        if diagnostics["console_errors"]:
            summary += "🔴 Console 报错:\n" + "\n".join(diagnostics["console_errors"][:5]) + "\n" # 限制条数防爆Token
        if diagnostics["network_errors"]:
            summary += "📡 Network 异常:\n" + "\n".join(diagnostics["network_errors"][:5]) + "\n"
        if diagnostics.get("error_message"):
            summary += f"❌ 崩溃信息: {diagnostics['error_message']}\n"
        
        summary += "\n💡 提示: 请分析上述报错日志。如果有需要，可以通过 write_local_file 或 apply_code_fix 修复代码后重新测试。"
    else:
        summary += "✅ 完美！页面加载正常，未检测到任何 Console 报错和 Network 异常。"

    return summary

# ---------- 元工具 1: 搜索工具（支持角色过滤） ----------
@mcp.tool()
@validate_path
def search_tools(task_id: str, query: str = "", category: str = "", role: str = "developer") -> str:
    """
    搜索可用的 MCP 工具，返回工具名称和简短描述。
    
    Args:
        task_id: 当前 Agent 任务的唯一标识 ID
        query: 搜索关键词（如 "修复", "扫描", "模板"）
        category: 工具分类（"template", "project", "quality", "fix", "backend", "admin"）
        role: Agent 角色（"developer", "reviewer", "tester", "analyst", "architect", "fixer"）
    """
    # ==========================================
    # 1. 完整的工具目录（与之前保持一致）
    # ==========================================

    tools_catalog = {
         "orchestrate_task": {
            "category": "meta",
            "description": "任务编排入口：接收自然语言任务描述，自动设置状态和角色",
            "roles": ["developer", "reviewer", "tester", "analyst", "architect", "fixer"]
        },
         "get_next_message": {
            "category": "meta",
            "description": "获取发给当前角色的下一条消息（Agent 间通信）",
            "roles": ["developer", "reviewer", "tester", "analyst", "architect", "fixer"]
        },
        # ---------- 自动化测试类 ----------
        "run_web_audit": {
            "category": "quality",
            "description": "全自动网页审查引擎。能够自动打开网页并监听 Console 报错、Network 请求失败，并生成页面截图。",
            "roles": ["developer", "tester"]
        },
        # ---------- 元工具 ----------
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
        "list_templates": {
            "category": "template", 
            "description": "列出所有可用的项目模板",
            "roles": ["developer", "reviewer", "tester", "architect"]
        },
        "get_rules": {
            "category": "project",
            "description": "获取公司开发红线规则",
            "roles": ["developer", "reviewer", "tester", "analyst"]
        },
        "get_pipeline_status": {
            "category": "quality",
            "description": "查询异步流水线任务的执行状态",
            "roles": ["developer", "reviewer", "tester", "fixer"]
        },
        # ---------- 创建类 ----------
        "create_frontend_project": {
            "category": "template",
            "description": "基于 Vue 3 + uni-app 模板创建新前端项目",
            "roles": ["developer"]
        },
        "create_backend_project": {
            "category": "template",
            "description": "基于 ThinkPHP 模板创建新后端项目",
            "roles": ["developer"]
        },
        "create_admin_project": {
            "category": "template",
            "description": "基于 FastAdmin 模板创建新后台项目",
            "roles": ["developer"]
        },
        # ---------- 扫描类 ----------
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
        # ---------- 修复类 ----------

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
        # ---------- 流水线类 ----------
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
        # ---------- 已废弃 ----------
        "check_code_quality": {
            "category": "quality",
            "description": "【已弃用】深度质量检查（可能超时），请改用 scan_code_batch 或 run_quality_pipeline",
            "roles": ["developer", "reviewer", "tester"]
        },
        "run_code_check": {
            "category": "quality",
            "description": "【已弃用】Prettier 格式检查（可能超时），请改用 run_quality_pipeline",
            "roles": ["developer", "reviewer", "tester"]
        }
    }

    # ==========================================
    # 2. 构建工具列表（供调度器使用）
    # ==========================================
    all_tools_list = [
        {"name": name, "description": info.get("description", "")}
        for name, info in tools_catalog.items()
    ]

    # ==========================================
    # 3. 状态机拦截：获取当前状态
    # ==========================================
    task_data = state_machine.get_task_state(task_id)
    if task_data and task_data.get('current_state'):
        current_state = task_data['current_state']
    else:
        # 新任务默认给予需求提取状态
        current_state = AgentState.REQUIREMENT_EXTRACTION

    # ==========================================
    # 4. 调用调度器，根据状态 + 角色过滤工具
    # ==========================================
    dispatcher = DynamicToolDispatcher(all_tools_list)
    active_tools_from_state = dispatcher.get_active_tools_for_state(current_state, role=role)
    allowed_tool_names = [t["name"] for t in active_tools_from_state]

    # ==========================================
    # 5. 开始检索（按角色、分类、关键词）
    # ==========================================
    results = []
    for name, info in tools_catalog.items():
        # 状态机白名单过滤
        if name not in allowed_tool_names:
            continue
        # 角色过滤（第二层保险，但 dispatcher 已处理，此处可省略）
        # 但保留以兼容未使用状态机的情况
        if role not in info.get("roles", ["developer"]):
            continue
        # 分类过滤
        if category and info["category"] != category:
            continue
        # 关键词搜索
        if query:
            query_lower = query.lower()
            if query_lower not in name.lower() and query_lower not in info["description"].lower():
                continue
        results.append(f"- **{name}** ({info['category']}): {info['description']}")

    # ==========================================
    # 6. 返回结果（含状态和角色信息）
    # ==========================================
    if not results:
        return (
            f"💡 [状态机拦截] 未找到匹配的工具。\n"
            f"⚠️ 注意：当前任务处于【{current_state}】阶段，角色【{role}】仅允许部分工具。\n"
            f"可用分类：template, project, quality, fix, backend, admin\n"
            f"当前角色：{role}"
        )

    return f"找到 {len(results)} 个可用工具（当前状态：{current_state} | 角色：{role}）：\n\n" + "\n".join(results)

# ---------- 元工具 2: 获取工具详情（按需加载完整 Schema） ----------
@mcp.tool()
@validate_path
def get_tool_details(tool_name: str) -> str:
    tool_schemas = {
    # 前端工具
    "scan_code_batch": {
        "description": "分批扫描 Vue/uni-app 项目的代码质量问题",
        "parameters": {
            "project_path": "项目的绝对路径（如 D:/workspace/test-vue-app）",
            "offset": "从第几个文件开始扫描（默认 0）",
            "limit": "本次扫描多少个文件（建议 20-30）"
        },
        "returns": "扫描进度、本批次发现的问题列表、下一个 offset",
        "example": 'scan_code_batch(project_path="D:/workspace/test-vue-app", offset=0, limit=20)'
    },
    "batch_fix_console_logs": {
        "description": "批量修复多个文件中的 console.log，自动添加环境判断",
        "parameters": {
            "file_paths": '要修复的文件绝对路径列表（如 ["D:/workspace/index.vue"]）',
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
        "description": "获取公司开发红线规则",
        "parameters": {},
        "returns": "完整的红线规则文档（Markdown 格式）",
        "example": 'get_rules()'
    },
    "create_frontend_project": {
        "description": "基于 Vue 3 + uni-app 模板创建新项目",
        "parameters": {
            "target_path": "创建项目的目标目录（如 D:/workspace）",
            "project_name": "新项目名称（如 my-admin-ui）"
        },
        "returns": "创建结果，包含路径和后续操作提示",
        "example": 'create_frontend_project(target_path="D:/workspace", project_name="my-app")'
    },
    "list_templates": {
        "description": "列出所有可用的项目模板",
        "parameters": {},
        "returns": "模板名称列表",
        "example": 'list_templates()'
    },
    # 后端工具
    "scan_backend_batch": {
        "description": "分批扫描 ThinkPHP 后端项目的代码质量问题",
        "parameters": {
            "project_path": "项目的绝对路径（如 D:/workspace/my-api）",
            "offset": "从第几个文件开始扫描（默认 0）",
            "limit": "本次扫描多少个文件（建议 20-30）"
        },
        "returns": "扫描进度、本批次发现的问题列表、下一个 offset",
        "example": 'scan_backend_batch(project_path="D:/workspace/my-api", offset=0, limit=20)'
    },
    "batch_fix_backend_issues": {
        "description": "批量修复 ThinkPHP 后端代码中的常见问题（标记硬编码密码、移除 echo/dump、注释 die/exit）",
        "parameters": {
            "file_paths": '需要修复的文件绝对路径列表（如 ["D:/workspace/my-api/app/controller/User.php"]）',
            "dry_run": "True 为预览，False 为执行"
        },
        "returns": "修复报告，包含已修复和跳过的文件数",
        "example": 'batch_fix_backend_issues(file_paths=["D:/workspace/my-api/app/controller/User.php"], dry_run=False)'
    },
    "run_backend_pipeline": {
        "description": "全自动后端质量检查流水线（异步），立即返回任务 ID",
        "parameters": {
            "project_path": "项目的绝对路径",
            "fix": "是否自动修复发现的问题（True/False）"
        },
        "returns": "任务 ID，用于后续查询状态",
        "example": 'run_backend_pipeline(project_path="D:/workspace/my-api", fix=True)'
    },
    "create_backend_project": {
        "description": "基于 ThinkPHP 模板创建新后端项目",
        "parameters": {
            "target_path": "创建项目的目标目录（如 D:/workspace）",
            "project_name": "新项目名称（如 my-api）"
        },
        "returns": "创建结果，包含路径和后续操作提示",
        "example": 'create_backend_project(target_path="D:/workspace", project_name="my-api")'
    },
    # 后台工具
    "create_admin_project": {
        "description": "基于 FastAdmin 模板创建新后台项目（后台管理）",
        "parameters": {
            "target_path": "创建项目的目标目录（如 D:/workspace）",
            "project_name": "新项目名称（如 my-admin）"
        },
        "returns": "创建结果，包含路径和后续操作提示",
        "example": 'create_admin_project(target_path="D:/workspace", project_name="my-admin")'
    },
    "scan_admin_batch": {
        "description": "分批扫描 FastAdmin 后台代码，检查插件规范、权限、SQL 注入等",
        "parameters": {
            "project_path": "项目的绝对路径（如 D:/workspace/my-admin）",
            "offset": "从第几个文件开始扫描（默认 0）",
            "limit": "本次扫描多少个文件（建议 20-30）"
        },
        "returns": "扫描进度、本批次发现的问题列表、下一个 offset",
        "example": 'scan_admin_batch(project_path="D:/workspace/my-admin", offset=0, limit=20)'
    },
    "run_admin_pipeline": {
        "description": "全自动后台质量检查流水线（异步），立即返回任务 ID",
        "parameters": {
            "project_path": "项目的绝对路径",
            "fix": "是否自动修复发现的问题（True/False）"
        },
        "returns": "任务 ID，用于后续查询状态",
        "example": 'run_admin_pipeline(project_path="D:/workspace/my-admin", fix=True)'
    },
    # ---------- 元工具（新增） ----------
    "orchestrate_task": {
        "description": "任务编排入口：接收自然语言任务描述，自动设置状态和角色",
        "parameters": {
            "task_id": "任务的唯一标识 ID（如 test_001）",
            "description": "自然语言任务描述（如 '创建一个用户登录页面并测试'）"
        },
        "returns": "任务编排结果，包含任务 ID、推断类型、当前状态、当前角色和下一步建议",
        "example": 'orchestrate_task(task_id="test_001", description="创建一个用户登录页面")'
    },
    "get_next_message": {
        "description": "获取发给当前角色的下一条消息（用于 Agent 间通信）",
        "parameters": {
            "task_id": "当前任务 ID",
            "role": "当前角色（tester、reviewer、fixer 等）"
        },
        "returns": "下一条消息的 JSON 格式内容，若无消息则返回 '暂无消息'",
        "example": 'get_next_message(task_id="test_001", role="tester")'
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

# ---------- 工具 2: 创建前端 Vue 项目（核心功能） ----------
@mcp.tool()
def create_frontend_project(target_path: str, project_name: str) -> str:
    """
    基于公司标准的 Vue 3 + JS 前端模板，创建一个新的前端项目。
    
    Args:
        target_path: 要把项目创建在哪里（例如 D:/workspace）
        project_name: 新项目的文件夹名称（例如 my-admin-ui）
    """
    source_template = TEMPLATES_DIR / "frontend-boilerplate"
    
    # 1. 检查源模板是否存在
    if not source_template.exists():
        return f"错误：找不到前端模板，请确认 assets/templates/frontend-boilerplate 存在"
    
    # 2. 拼接目标完整路径
    target_full_path = Path(target_path) / project_name
    
    # 3. 防止覆盖已有项目
    if target_full_path.exists():
        return f"错误：目标路径 {target_full_path} 已存在，请删除或更换项目名"
    
    try:
        # 4. 执行复制（把整个模板拷贝过去）
        shutil.copytree(source_template, target_full_path)
        
        # 5. 自动执行 npm install（如果系统安装了 Node.js）
        # 使用 shutil.which 查找 node/npm 的完整路径，避免 PATH 环境变量问题
        node_path = shutil.which("node")
        npm_path = shutil.which("npm")
        
        if node_path and npm_path:
            try:
                install_result = subprocess.run(
                    [npm_path, "install"],
                    capture_output=True, text=True, cwd=str(target_full_path), timeout=300
                )
                if install_result.returncode == 0:
                    return f"✅ 前端项目创建成功！\n路径：{target_full_path}\n依赖已自动安装（npm install）\n请 cd {target_full_path} 然后运行 npm run dev"
                else:
                    return f"✅ 前端项目创建成功！但 npm install 执行失败，请手动进入目录执行 npm install。\n错误信息：{install_result.stderr}"
            except subprocess.TimeoutExpired:
                return f"✅ 前端项目创建成功！但 npm install 超时，请手动进入目录执行 npm install。\n路径：{target_full_path}"
            except Exception as e:
                return f"✅ 前端项目创建成功！但 npm install 执行异常，请手动进入目录执行 npm install。\n路径：{target_full_path}\n错误信息：{str(e)}"
        else:
            return f"✅ 前端项目创建成功！\n路径：{target_full_path}\n注意：未检测到 Node.js，请手动安装依赖（npm install）"
            
    except Exception as e:
        return f"❌ 创建失败：{str(e)}"

# ---------- 工具 3: 读取开发红线规则（供 AI 参考） ----------
@mcp.tool()
def get_rules() -> str:
    """获取公司最新的开发约束和红线规则（Vue/ThinkPHP/FastAdmin）"""
    rule_files = [
        ("前端规则", REFS_DIR / "mandatory-rules.md"),
        ("后端规则", REFS_DIR / "mandatory-rules-backend.md"),
        ("后台规则", REFS_DIR / "mandatory-rules-admin.md"),
    ]
    content_parts = []
    for title, path in rule_files:
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
                content_parts.append(f"## {title}\n{content}\n")
    if not content_parts:
        return "错误：未找到任何规则文件"
    return f"【公司开发红线】\n\n" + "\n\n".join(content_parts)

# ---------- 工具 4: 代码规范检查（Prettier / ESLint） ----------
@mcp.tool()
def run_code_check(project_path: str) -> str:
    """
    对指定的 Vue/uni-app 项目执行代码规范检查（Prettier + ESLint）。
    如果项目未安装依赖，会自动执行 npm install。
    
    Args:
        project_path: 项目的绝对路径（例如 D:/workspace/test-vue-app）
    """
    path = Path(project_path)
    if not path.exists():
        return f"❌ 错误：路径 {project_path} 不存在"

    package_json = path / "package.json"
    if not package_json.exists():
        return "❌ 错误：该目录中没有 package.json，不是 Node.js 项目"

    # 1. 检查 node_modules 是否存在，若不存在则自动安装依赖（修复环境问题）
    node_modules = path / "node_modules"
    if not node_modules.exists():
        try:
            subprocess.run(["npm", "install"], cwd=project_path, shell=False, timeout=300)
        except Exception as e:
            return f"⚠️ 依赖安装失败，请手动执行 npm install。错误：{str(e)}"

    # 2. 执行 Prettier 检查（只检查 .vue, .js, .json 文件，不修改）
    try:
        # 注意：如果模板里没有 prettier 脚本，我们用 npx 直接跑
        # 优先使用项目内的 npm script
        result = subprocess.run(
            ["npx", "prettier", "--check", "\"{pages,sheep,components}/**/*.{js,json,vue,html}\""],
            capture_output=True, text=True, cwd=project_path, shell=True, timeout=60
        )
        
        if result.returncode == 0:
            return f"✅ 代码规范检查通过！\n{result.stdout}"
        else:
            # 有格式问题，返回具体的错误文件和行数
            return f"❌ 代码存在格式问题（Prettier）：\n{result.stdout}\n{result.stderr}"
            
    except Exception as e:
        return f"❌ 执行检查时出错：{str(e)}"

# ---------- 工具 5: 深度代码质量检查（红线扫描 + 格式检查） ----------
@mcp.tool()
def check_code_quality(project_path: str, auto_fix: bool = False) -> str:
    """
    对 Vue/uni-app 项目进行深度质量检查，包括：
    1. 红线违规扫描（console.log、选项式API、命名问题等）
    2. Prettier 格式检查
    3. 返回详细的问题清单和位置
    
    Args:
        project_path: 项目的绝对路径
        auto_fix: 是否自动修复格式问题（默认 False）
    """
    path = Path(project_path)
    if not path.exists():
        return f"❌ 错误：路径 {project_path} 不存在"
    
    results = []
    fix_count = 0
    
    # 1. 扫描 Vue 文件中的红线违规
    vue_files = list(path.rglob("*.vue"))
    js_files = list(path.rglob("*.js"))
    all_files = vue_files + js_files
    
    issues = []
    
    for file in all_files:
        # 跳过 node_modules
        if "node_modules" in str(file) or "dist" in str(file):
            continue
            
        with open(file, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
            lines = content.split("\n")
            
            # 检查 1: console.log 未保护
            for i, line in enumerate(lines, 1):
                if "console.log" in line and "import.meta.env" not in content:
                    issues.append(f"  📍 {file.relative_to(path)}: 第 {i} 行 - console.log 未加环境判断")
                    break  # 每个文件只报一次，避免刷屏
            
            # 检查 2: 选项式 API（data() 方法）
            if "data()" in content and "script setup" not in content:
                issues.append(f"  📍 {file.relative_to(path)} - 使用了 data() 选项式写法，建议改用 <script setup>")
            
            # 检查 3: Vue 组件是否多单词命名
            if file.name.endswith(".vue") and not file.name.endswith(".vue"):
                name = file.stem
                if name.lower() == name:  # 全小写，单单词
                    issues.append(f"  📍 {file.relative_to(path)} - 组件名 '{name}' 是单单词，建议多单词命名")
    
    # 2. 执行 Prettier 格式检查
    try:
        prettier_result = subprocess.run(
            ["npx", "prettier", "--check", "\"{pages,sheep,components}/**/*.{js,json,vue,html}\""],
            capture_output=True, text=True, cwd=project_path, shell=True, timeout=120
        )
        if prettier_result.returncode != 0:
            issues.append(f"\n📦 Prettier 格式问题：\n{prettier_result.stdout}")
    except Exception as e:
        issues.append(f"\n⚠️ Prettier 检查失败：{str(e)}")
    
    # 3. 生成报告
    if not issues:
        return "✅ 代码质量检查通过！未发现红线违规或格式问题。"
    
    report = "🚨 代码质量检查发现问题：\n\n" + "\n".join(issues)
    
    # 4. 自动修复（如果开启）
    if auto_fix:
        try:
            subprocess.run(
                ["npx", "prettier", "--write", "\"{pages,sheep,components}/**/*.{js,json,vue,html}\""],
                capture_output=True, text=True, cwd=project_path, shell=True, timeout=120
            )
            report += f"\n\n✅ 已自动执行 Prettier 格式化修复。"
        except Exception as e:
            report += f"\n\n❌ 自动修复失败：{str(e)}"
    
    return report

# ---------- 工具 6: 分批代码扫描（解决超时问题） ----------
@mcp.tool()
def scan_code_batch(project_path: str, offset: int = 0, limit: int = 20) -> str:
    """
    分批扫描 Vue/uni-app 项目的代码质量问题。
    每次只扫描指定数量的文件，适合大规模项目逐批处理。
    
    Args:
        project_path: 项目的绝对路径
        offset: 从第几个文件开始扫描（用于翻页）
        limit: 本次扫描多少个文件（建议 20-30）
    """
    path = Path(project_path)
    if not path.exists():
        return f"❌ 错误：路径 {project_path} 不存在"
    
    # 1. 收集所有需要检查的文件（只关注源码目录）
    target_dirs = ["pages", "sheep", "components"]
    all_files = []
    
    for dir_name in target_dirs:
        target_dir = path / dir_name
        if target_dir.exists():
            for ext in ["*.vue", "*.js"]:
                all_files.extend(target_dir.rglob(ext))
    
    # 去重并排序（保证每次顺序一致）
    all_files = sorted(set(all_files), key=lambda p: str(p))
    
    # 过滤掉 node_modules
    all_files = [f for f in all_files if "node_modules" not in str(f)]
    
    total = len(all_files)
    
    # 2. 切片：获取当前批次
    batch_files = all_files[offset:offset + limit]
    
    if not batch_files:
        return f"✅ 所有文件已检查完毕！共扫描了 {total} 个文件。"
    
    # 3. 扫描当前批次
    issues = []
    for file in batch_files:
        with open(file, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
            lines = content.split("\n")
            
            # 检查 1: console.log
            if "console.log" in content and "import.meta.env" not in content:
                for i, line in enumerate(lines, 1):
                    if "console.log" in line:
                        issues.append(f"  📍 {file.relative_to(path)}: 第 {i} 行 - console.log 未加环境判断")
                        break
            
            # 检查 2: data() 选项式
            if "data()" in content and "<script setup" not in content:
                issues.append(f"  📍 {file.relative_to(path)} - 使用了 data() 选项式写法")
            
            # 检查 3: 组件命名
            if file.suffix == ".vue":
                name = file.stem
                if name.lower() == name and "_" not in name and "-" not in name:
                    issues.append(f"  📍 {file.relative_to(path)} - 组件名 '{name}' 是单单词")
    
    # 4. 构建返回报告（包含分页信息）
    next_offset = offset + limit
    has_more = total > next_offset
    
    report = f"📊 扫描进度：{next_offset if next_offset < total else total}/{total} 个文件\n"
    if issues:
        report += f"🚨 本批次发现 {len(issues)} 个问题：\n" + "\n".join(issues)
    else:
        report += "✅ 本批次未发现问题。"
    
    if has_more:
        report += f"\n\n🔄 还有剩余文件待检查，请继续调用 scan_code_batch，offset={next_offset}, limit={limit}"
    else:
        report += "\n\n🎉 全部扫描完成！"
    
    return report

# ---------- 工具 7: 批量修复 console.log（并行处理） ----------
@mcp.tool()
def batch_fix_console_logs(file_paths: list, dry_run: bool = True) -> str:
    """
    批量修复多个文件中的 console.log，自动添加环境判断。
    
    Args:
        file_paths: 需要修复的文件绝对路径列表（例如 ["D:/workspace/.../index.vue"]）
        dry_run: 如果为 True，只预览修改内容，不实际写入；为 False 时执行写入。
    """
    if not file_paths:
        return "❌ 错误：文件列表为空"
    
    results = []
    total_files = len(file_paths)
    fixed_count = 0
    skipped_count = 0
    
    def fix_console_in_file(file_path):
        path = Path(file_path)
        if not path.exists():
            return {"file": str(path), "status": "skipped", "reason": "文件不存在"}
        
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        
        if "console.log" not in content:
            return {"file": str(path), "status": "skipped", "reason": "无 console.log"}
        
        lines = content.split('\n')
        new_lines = []
        modified = False
        for line in lines:
            if 'console.log' in line and 'import.meta.env' not in line:
                stripped = line.lstrip()
                indent = line[:len(line)-len(stripped)]
                if stripped.startswith('console.log'):
                    new_line = indent + 'if (import.meta.env.MODE !== "production") {\n' + \
                               indent + '    ' + stripped + '\n' + \
                               indent + '}'
                    new_lines.append(new_line)
                    modified = True
                else:
                    new_lines.append(line)
            else:
                new_lines.append(line)
        
        if not modified:
            return {"file": str(path), "status": "skipped", "reason": "未找到可修复的 console.log"}
        
        new_content = '\n'.join(new_lines)
        
        if dry_run:
            return {"file": str(path), "status": "preview", "diff": new_content[:500] + "..."}
        else:
            with open(path, "w", encoding="utf-8") as f:
                f.write(new_content)
            return {"file": str(path), "status": "fixed"}
    
    from concurrent.futures import ThreadPoolExecutor, as_completed
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(fix_console_in_file, fp): fp for fp in file_paths}
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            if result["status"] == "fixed":
                fixed_count += 1
            elif result["status"] == "skipped":
                skipped_count += 1
    
    report = f"📊 批量修复完成。总文件数: {total_files}，已修复: {fixed_count}，跳过: {skipped_count}\n"
    if dry_run:
        report += "⚠️ 当前为预览模式（dry_run=True），未实际修改文件。如需执行，请设置 dry_run=False。\n"
    report += "详细结果：\n"
    for r in results:
        if r["status"] == "fixed":
            report += f"  ✅ {r['file']}\n"
        elif r["status"] == "skipped":
            report += f"  ⏭️ {r['file']}（{r.get('reason', '')}）\n"
        elif r["status"] == "preview":
            report += f"  👁️ {r['file']}（预览修改）\n"
    return report

# ---------- 工具 8: 全自动质量检查流水线（异步版本） ----------
@mcp.tool()
def run_quality_pipeline(project_path: str, fix: bool = False) -> str:
    """
    启动全自动质量检查流水线（异步），立即返回任务 ID。
    使用 get_pipeline_status(task_id) 查询进度和结果。
    """
    path = Path(project_path)
    if not path.exists():
        return f"❌ 错误：路径 {project_path} 不存在"
    
    task_id = str(uuid.uuid4())[:8]
    
    with task_lock:
        pipeline_tasks[task_id] = {
            "status": "pending",
            "project_path": project_path,
            "fix": fix,
            "result": None,
            "error": None,
            "progress": "任务已创建，等待启动...",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }
    
    # 启动后台线程执行实际工作
    def worker():
        try:
            with task_lock:
                pipeline_tasks[task_id]["status"] = "running"
                pipeline_tasks[task_id]["progress"] = "开始执行流水线..."
                pipeline_tasks[task_id]["updated_at"] = datetime.now().isoformat()
            
            import re
            from concurrent.futures import ThreadPoolExecutor, as_completed
            
            path_obj = Path(project_path)
            all_issues = []
            total_files = 0
            offset = 0
            limit = 30
            
            # 阶段一：全量扫描
            with task_lock:
                pipeline_tasks[task_id]["progress"] = "正在全量扫描代码..."
                pipeline_tasks[task_id]["updated_at"] = datetime.now().isoformat()
            
            while True:
                batch_result = scan_code_batch(project_path, offset, limit)
                if "✅ 所有文件已检查完毕" in batch_result:
                    all_issues.append(batch_result)
                    break
                all_issues.append(batch_result)
                match = re.search(r'offset=(\d+)', batch_result)
                if match:
                    offset = int(match.group(1))
                else:
                    break
            
            # 提取总文件数
            for issue in all_issues:
                match = re.search(r'(\d+)/(\d+)', issue)
                if match:
                    total_files = int(match.group(2))
                    break
            
            # 阶段二：提取需要修复的文件
            console_log_files = []
            for issue in all_issues:
                lines = issue.split('\n')
                for line in lines:
                    if 'console.log' in line and ('.vue' in line or '.js' in line):
                        match = re.search(r'📍 (.+?):', line)
                        if match:
                            console_log_files.append(match.group(1))
            console_log_files = list(set(console_log_files))
            
            with task_lock:
                pipeline_tasks[task_id]["progress"] = f"扫描完成，发现 {len(console_log_files)} 个含 console.log 的文件"
                pipeline_tasks[task_id]["updated_at"] = datetime.now().isoformat()
            
            # 阶段三：自动修复
            fix_log = []
            if fix and console_log_files:
                with task_lock:
                    pipeline_tasks[task_id]["progress"] = f"正在修复 {len(console_log_files)} 个文件中的 console.log..."
                    pipeline_tasks[task_id]["updated_at"] = datetime.now().isoformat()
                
                abs_files = [str(path_obj / f) for f in console_log_files]
                fix_result = batch_fix_console_logs(abs_files, dry_run=False)
                fix_log.append(fix_result)
                
                # 执行 Prettier 格式化
                try:
                    subprocess.run(
                        ["npx", "prettier", "--write", "."],
                        cwd=project_path,
                        shell=True,
                        timeout=120,
                        capture_output=True
                    )
                    fix_log.append("✅ 已执行 Prettier 格式化")
                except Exception as e:
                    fix_log.append(f"⚠️ 格式化执行失败：{str(e)}")
                
                with task_lock:
                    pipeline_tasks[task_id]["progress"] = "修复完成，正在进行二次验证..."
                    pipeline_tasks[task_id]["updated_at"] = datetime.now().isoformat()
            else:
                fix_log.append("⏭️ 未开启自动修复或无需修复")
            
            # 阶段四：二次验证
            verify_result = scan_code_batch(project_path, 0, 30)
            
            # 生成最终报告
            report = "=" * 60 + "\n"
            report += "📊 质量检查流水线报告\n"
            report += "=" * 60 + "\n\n"
            report += f"📁 项目路径：{project_path}\n"
            report += f"📄 总文件数：{total_files}\n"
            report += f"🚨 发现红线违规文件数：{len(console_log_files)}\n\n"
            
            if console_log_files:
                report += "📋 红线违规文件（前20个）：\n"
                for f in console_log_files[:20]:
                    report += f"  - {f}\n"
                if len(console_log_files) > 20:
                    report += f"  ... 还有 {len(console_log_files) - 20} 个\n"
            else:
                report += "✅ 未发现红线违规\n"
            
            if fix:
                report += "\n🛠️ 修复操作：\n"
                report += "\n".join(fix_log)
            
            report += f"\n\n📌 验证结果（首批）：\n{verify_result[:600]}...\n"
            
            if fix:
                report += "\n🎉 流水线执行完成！请检查修复效果。"
            else:
                report += "\n💡 提示：设置 fix=True 可自动修复发现的问题。"
            
            # ---------- 新增：保存完整报告到文件 ----------
            reports_dir = path_obj / "reports"
            reports_dir.mkdir(exist_ok=True)
            report_file = reports_dir / f"{task_id}_report.txt"
            with open(report_file, "w", encoding="utf-8") as f:
                f.write(report)
            
            # 生成摘要信息（只保留关键数据）
            summary = f"""✅ 流水线执行完成！

📁 项目路径：{project_path}
📄 总文件数：{total_files}
🚨 发现问题文件数：{len(console_log_files)}
📊 修复操作：{'已执行' if fix else '未开启'}

📄 完整报告已保存至：{report_file}
💡 如需查看详情，请打开该文件。
"""
            
            # 更新任务状态为完成（使用摘要）
            with task_lock:
                pipeline_tasks[task_id]["status"] = "completed"
                pipeline_tasks[task_id]["result"] = summary
                pipeline_tasks[task_id]["progress"] = "流水线执行完成"
                pipeline_tasks[task_id]["updated_at"] = datetime.now().isoformat()

            send_message(
                from_role="fixer",
                to_role="tester",
                action="reverify",
                payload={"project_path": project_path, "task_id": task_id}
                )
            # 推进状态机
            state_machine.update_task_state(task_id, AgentState.WEB_TESTING, {"last_pipeline": task_id})
            logger.info(f"流水线 {task_id} 完成，已通知测试 Agent")
            logger.info(f"流水线任务 {task_id} 完成，报告保存至 {report_file}")
        
        except Exception as e:
            with task_lock:
                pipeline_tasks[task_id]["status"] = "failed"
                pipeline_tasks[task_id]["error"] = str(e)
                pipeline_tasks[task_id]["progress"] = f"执行失败：{str(e)}"
                pipeline_tasks[task_id]["updated_at"] = datetime.now().isoformat()
            logger.error(f"流水线任务 {task_id} 失败: {e}")
    
    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    
    return f"✅ 流水线任务已启动，任务 ID: {task_id}\n请使用 get_pipeline_status('{task_id}') 查询进度。"

# ---------- 元工具: 获取下一条消息 ----------
@mcp.tool()
def get_next_message(task_id: str, role: str) -> str:
    """
    获取发给当前角色的下一条消息（用于 Agent 间通信）
    
    Args:
        task_id: 当前任务 ID
        role: 当前角色（tester、reviewer、fixer 等）
    """
    with message_lock:
        for i, msg in enumerate(agent_message_queue):
            if msg["to"] == role:
                # 检查消息是否属于当前任务（通过 payload 中的 task_id 匹配）
                if msg.get("payload", {}).get("task_id") == task_id:
                    agent_message_queue.pop(i)
                    return json.dumps(msg, indent=2, ensure_ascii=False)
                # 如果消息不属于当前任务，但也是发给这个角色的，先跳过
                # 但简单起见，这里只匹配 task_id
        return "暂无消息"

# ---------- 元工具: 自动响应消息（Agent 自主决策） ----------
@mcp.tool()
def auto_respond(task_id: str, role: str) -> str:
    """
    自动响应消息：获取当前角色的下一条消息，根据 action 自动执行对应工具。
    支持的动作：
      - code_ready: 执行 run_web_audit 进行测试
      - reverify: 执行 run_quality_pipeline 重新验证
      - test_complete: 记录测试完成状态
    
    Args:
        task_id: 当前任务 ID
        role: 当前角色
    """
    # 1. 获取消息
    msg_result = get_next_message(task_id, role)
    
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
    
    # 2. 根据动作类型自动执行
    response_msg = ""
    
    if action == "code_ready":
        # 代码构建完成 → 启动网页测试
        project_path = payload.get("project_path")
        if not project_path:
            return "❌ 消息缺少 project_path 参数"
        
        logger.info(f"[AutoRespond] 自动触发网页测试: {project_path}")
        
        # 调用 run_web_audit（需要 URL 和 task_id）
        # 注意：这里需要推测 URL，简化处理，使用默认端口
        test_url = "http://localhost:5173"  # 默认 Vite 开发服务器
        result = run_web_audit(task_id, test_url)
        
        # 发送测试完成消息给原发送方
        send_message(
            from_role=role,
            to_role=from_role,
            action="test_complete",
            payload={
                "task_id": task_id,
                "result": result[:200] + "..." if len(result) > 200 else result
            }
        )
        response_msg = f"✅ 已自动响应 code_ready 动作，执行测试完成。\n\n{result}"
        
    elif action == "reverify":
        # 修复完成 → 重新验证
        project_path = payload.get("project_path")
        if not project_path:
            return "❌ 消息缺少 project_path 参数"
        
        logger.info(f"[AutoRespond] 自动触发重新验证: {project_path}")
        
        # 调用 run_quality_pipeline
        result = run_quality_pipeline(project_path, fix=False)
        
        response_msg = f"✅ 已自动响应 reverify 动作，重新验证完成。\n\n{result}"
        
    elif action == "test_complete":
        # 测试完成 → 记录状态并推进状态机
        state_machine.update_task_state(
            task_id,
            AgentState.DELIVERY_COMPLETED,
            {"test_result": payload.get("result"), "completed_by": role}
        )
        response_msg = f"✅ 测试已完成，任务 {task_id} 流转至 DELIVERY_COMPLETED 状态。"
        
    else:
        response_msg = f"⚠️ 未知动作: {action}，请手动处理。"
    
    return response_msg

# ---------- 工具 9: 查询流水线任务状态 ----------
@mcp.tool()
def get_pipeline_status(task_id: str) -> str:
    """
    查询异步流水线任务的执行状态和结果。
    返回状态：pending（等待）、running（运行中）、completed（完成）、failed（失败）。
    """
    with task_lock:
        task = pipeline_tasks.get(task_id)
        if not task:
            return f"❌ 错误：未找到任务 ID {task_id}"
    
    status = task["status"]
    progress = task.get("progress", "")
    updated_at = task.get("updated_at", "")
    
    if status == "pending":
        return f"⏳ 任务等待中...\n进度：{progress}\n更新时间：{updated_at}"
    elif status == "running":
        return f"🔄 任务执行中...\n进度：{progress}\n更新时间：{updated_at}"
    elif status == "completed":
        result = task.get("result", "无结果")
        return f"✅ 任务已完成！\n\n{result}"
    elif status == "failed":
        error = task.get("error", "未知错误")
        return f"❌ 任务失败：{error}\n进度：{progress}"
    else:
        return f"⚠️ 未知状态：{status}"

# ---------- 工具 10: 分批扫描 ThinkPHP 后端代码 ----------
@mcp.tool()
def scan_backend_batch(project_path: str, offset: int = 0, limit: int = 20) -> str:
    """
    分批扫描 ThinkPHP 后端项目的代码质量问题。
    检查：原生 SQL、硬编码敏感信息、未校验输入、直接输出、未捕获异常等。
    
    Args:
        project_path: 项目的绝对路径
        offset: 从第几个文件开始扫描
        limit: 本次扫描多少个文件（建议 20-30）
    """
    path = Path(project_path)
    if not path.exists():
        return f"❌ 错误：路径 {project_path} 不存在"
    
    # 扫描 PHP 文件（支持 app/ 和 application/ 目录，兼容 ThinkPHP 和 FastAdmin）
    target_dirs = ["app", "application"]
    all_files = []
    
    for dir_name in target_dirs:
        target_dir = path / dir_name
        if target_dir.exists():
            all_files.extend(target_dir.rglob("*.php"))
    
    # 过滤掉 vendor 目录（依赖包）
    all_files = [f for f in all_files if "vendor" not in str(f)]
    all_files = sorted(set(all_files), key=lambda p: str(p))
    
    total = len(all_files)
    batch_files = all_files[offset:offset + limit]
    
    if not batch_files:
        return f"✅ 所有文件已检查完毕！共扫描了 {total} 个 PHP 文件。"
    
    issues = []
    for file in batch_files:
        with open(file, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
            lines = content.split("\n")
            
            # 检查 1: 硬编码敏感信息（密码、密钥等）
            if "password" in content.lower() and "env(" not in content and "getenv(" not in content:
                # 简单检测：如果存在 'password' 且不包含 env 调用
                for i, line in enumerate(lines, 1):
                    if "password" in line.lower() and "env" not in line:
                        issues.append(f"  📍 {file.relative_to(path)}: 第 {i} 行 - 疑似硬编码密码/密钥（建议使用 .env）")
                        break
            
            # 检查 2: 原生 SQL 拼接（未使用参数绑定）
            # 匹配类似 "select * from user where id = $id" 或 "where('id', $id)" 但未绑定
            if "Db::query" in content or "Db::execute" in content:
                # 进一步检查是否有参数绑定
                if "::query" in content and "?" not in content and ":" not in content:
                    # 简单判断：存在 query 但未使用占位符
                    issues.append(f"  📍 {file.relative_to(path)} - 使用了 Db::query 但疑似未使用参数绑定（建议使用参数绑定）")
            
            # 检查 3: 直接 echo / dump / var_dump（不应出现在控制器中）
            if "echo " in content or "dump(" in content or "var_dump(" in content:
                if "controller" in str(file).lower() or "api" in str(file).lower():
                    issues.append(f"  📍 {file.relative_to(path)} - 控制器/API 中不应使用 echo/dump/var_dump（应返回 JSON）")
            
            # 检查 4: 未使用验证器（input 直接使用）
            if "input(" in content and "validate" not in content:
                # 简单判断：存在 input 但未出现 validate 关键词
                issues.append(f"  📍 {file.relative_to(path)} - 使用了 input() 但未发现验证器（建议使用验证器校验）")
            
            # 检查 5: die / exit 在控制器中
            if "die" in content or "exit" in content:
                if "controller" in str(file).lower():
                    issues.append(f"  📍 {file.relative_to(path)} - 控制器中不应使用 die/exit（应使用异常处理）")
    
    next_offset = offset + limit
    has_more = total > next_offset
    
    report = f"📊 后端扫描进度：{next_offset if next_offset < total else total}/{total} 个 PHP 文件\n"
    if issues:
        report += f"🚨 本批次发现 {len(issues)} 个问题：\n" + "\n".join(issues)
    else:
        report += "✅ 本批次未发现问题。"
    
    if has_more:
        report += f"\n\n🔄 还有剩余文件待检查，请继续调用 scan_backend_batch，offset={next_offset}, limit={limit}"
    else:
        report += "\n\n🎉 全部扫描完成！"
    
    return report

# ---------- 工具 11: 批量修复后端常见问题 ----------
@mcp.tool()
def batch_fix_backend_issues(file_paths: list, dry_run: bool = True) -> str:
    """
    批量修复 ThinkPHP 后端代码中的常见问题：
    1. 将硬编码密码替换为 env('DB_PASSWORD') 占位符（仅标记，不自动替换）
    2. 将 echo/dump 替换为 return $this->success()
    3. 移除 die/exit（注释掉）
    
    Args:
        file_paths: 需要修复的文件绝对路径列表
        dry_run: True 为预览，False 为执行
    """
    if not file_paths:
        return "❌ 错误：文件列表为空"
    
    results = []
    for file_path in file_paths:
        path = Path(file_path)
        if not path.exists():
            results.append(f"⏭️ {path} 文件不存在")
            continue
        
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        
        original_content = content
        modified = False
        
        # 修复 1: 将 echo/dump 替换为 return $this->success()（仅在控制器中）
        if "controller" in str(path).lower():
            if "echo " in content or "dump(" in content:
                # 简单替换：将 echo 行替换为 return $this->success()
                lines = content.split('\n')
                new_lines = []
                for line in lines:
                    if "echo " in line or "dump(" in line:
                        # 保留注释？可以替换
                        new_lines.append("        return $this->success('操作成功'); // 原 echo/dump 已替换")
                        modified = True
                    else:
                        new_lines.append(line)
                content = '\n'.join(new_lines)
        
        # 修复 2: 移除 die/exit（注释掉）
        if "die" in content or "exit" in content:
            lines = content.split('\n')
            new_lines = []
            for line in lines:
                if "die" in line or "exit" in line:
                    new_lines.append("// " + line + " // 已注释 die/exit")
                    modified = True
                else:
                    new_lines.append(line)
            content = '\n'.join(new_lines)
        
        # 修复 3: 硬编码密码（标记为 TODO）
        if "password" in content.lower() and "env(" not in content:
            lines = content.split('\n')
            new_lines = []
            for line in lines:
                if "password" in line.lower() and "env" not in line:
                    new_lines.append(line + " // TODO: 将硬编码密码移至 .env")
                    modified = True
                else:
                    new_lines.append(line)
            content = '\n'.join(new_lines)
        
        if not modified:
            results.append(f"⏭️ {path} 无需修改")
            continue
        
        if not dry_run:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            results.append(f"✅ {path} 已修复")
        else:
            results.append(f"👁️ {path} 预览修改（未实际修改）")
    
    report = f"📊 后端批量修复完成。\n" + "\n".join(results)
    if dry_run:
        report += "\n⚠️ 预览模式，未实际修改。设置 dry_run=False 执行修复。"
    return report

# ---------- 工具 12: 全自动后端质量检查流水线（异步） ----------
@mcp.tool()
def run_backend_pipeline(project_path: str, fix: bool = False) -> str:
    """
    启动全自动后端质量检查流水线（异步），立即返回任务 ID。
    包括：扫描 PHP 代码、检测常见问题、自动修复（如果开启）、二次验证。
    """
    path = Path(project_path)
    if not path.exists():
        return f"❌ 错误：路径 {project_path} 不存在"
    
    task_id = str(uuid.uuid4())[:8]
    
    with task_lock:
        pipeline_tasks[task_id] = {
            "status": "pending",
            "project_path": project_path,
            "fix": fix,
            "result": None,
            "error": None,
            "progress": "后端任务已创建，等待启动...",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }
    
    def worker():
        try:
            with task_lock:
                pipeline_tasks[task_id]["status"] = "running"
                pipeline_tasks[task_id]["progress"] = "开始执行后端扫描..."
                pipeline_tasks[task_id]["updated_at"] = datetime.now().isoformat()
            
            import re
            all_issues = []
            total_files = 0
            offset = 0
            limit = 30
            
            # 阶段一：全量扫描
            while True:
                batch_result = scan_backend_batch(project_path, offset, limit)
                if "✅ 所有文件已检查完毕" in batch_result:
                    all_issues.append(batch_result)
                    break
                all_issues.append(batch_result)
                match = re.search(r'offset=(\d+)', batch_result)
                if match:
                    offset = int(match.group(1))
                else:
                    break
            
            # 提取总文件数
            for issue in all_issues:
                match = re.search(r'(\d+)/(\d+)', issue)
                if match:
                    total_files = int(match.group(2))
                    break
            
            # 提取问题文件列表
            problem_files = []
            for issue in all_issues:
                lines = issue.split('\n')
                for line in lines:
                    if '📍' in line:
                        match = re.search(r'📍 (.+?):', line)
                        if match:
                            problem_files.append(match.group(1))
            problem_files = list(set(problem_files))
            
            with task_lock:
                pipeline_tasks[task_id]["progress"] = f"扫描完成，发现 {len(problem_files)} 个有问题的文件"
                pipeline_tasks[task_id]["updated_at"] = datetime.now().isoformat()
            
            fix_log = []
            if fix and problem_files:
                abs_files = [str(Path(project_path) / f) for f in problem_files]
                fix_result = batch_fix_backend_issues(abs_files, dry_run=False)
                fix_log.append(fix_result)
                
                with task_lock:
                    pipeline_tasks[task_id]["progress"] = "修复完成，正在进行二次验证..."
                    pipeline_tasks[task_id]["updated_at"] = datetime.now().isoformat()
            else:
                fix_log.append("⏭️ 未开启自动修复或无需修复")
            
            # 二次验证
            verify_result = scan_backend_batch(project_path, 0, 30)
            
            # 报告
            report = "=" * 60 + "\n"
            report += "📊 后端质量检查流水线报告\n"
            report += "=" * 60 + "\n\n"
            report += f"📁 项目路径：{project_path}\n"
            report += f"📄 总 PHP 文件数：{total_files}\n"
            report += f"🚨 发现问题文件数：{len(problem_files)}\n\n"
            
            if problem_files:
                report += "📋 问题文件（前20个）：\n"
                for f in problem_files[:20]:
                    report += f"  - {f}\n"
                if len(problem_files) > 20:
                    report += f"  ... 还有 {len(problem_files)-20} 个\n"
            else:
                report += "✅ 未发现问题\n"
            
            if fix:
                report += "\n🛠️ 修复操作：\n" + "\n".join(fix_log)
            
            report += f"\n\n📌 验证结果（首批）：\n{verify_result[:600]}...\n"
            
            if fix:
                report += "\n🎉 后端流水线执行完成！请检查修复效果。"
            else:
                report += "\n💡 提示：设置 fix=True 可自动修复发现的问题。"
            
            with task_lock:
                pipeline_tasks[task_id]["status"] = "completed"
                pipeline_tasks[task_id]["result"] = report
                pipeline_tasks[task_id]["progress"] = "后端流水线执行完成"
                pipeline_tasks[task_id]["updated_at"] = datetime.now().isoformat()
        
        except Exception as e:
            with task_lock:
                pipeline_tasks[task_id]["status"] = "failed"
                pipeline_tasks[task_id]["error"] = str(e)
                pipeline_tasks[task_id]["progress"] = f"执行失败：{str(e)}"
                pipeline_tasks[task_id]["updated_at"] = datetime.now().isoformat()
    
    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    
    return f"✅ 后端流水线任务已启动，任务 ID: {task_id}\n请使用 get_pipeline_status('{task_id}') 查询进度。"

# ---------- 工具 13: 创建 ThinkPHP 后端项目 ----------
@mcp.tool()
def create_backend_project(target_path: str, project_name: str) -> str:
    """
    基于公司标准的 ThinkPHP 后端模板，创建一个新的后端项目。
    
    Args:
        target_path: 要把项目创建在哪里（例如 D:/workspace）
        project_name: 新项目的文件夹名称（例如 my-api）
    """
    source_template = TEMPLATES_DIR / "backend-boilerplate"
    
    # 1. 检查源模板是否存在
    if not source_template.exists():
        return f"错误：找不到后端模板，请确认 assets/templates/backend-boilerplate 存在"
    
    # 2. 拼接目标完整路径
    target_full_path = Path(target_path) / project_name
    
    # 3. 防止覆盖已有项目
    if target_full_path.exists():
        return f"错误：目标路径 {target_full_path} 已存在，请删除或更换项目名"
    
    try:
        # 4. 执行复制
        shutil.copytree(source_template, target_full_path)
        
        # 5. 自动执行 composer install（如果系统安装了 PHP）
        php_check = subprocess.run(["php", "-v"], capture_output=True, text=True, shell=True)
        if php_check.returncode == 0:
            # 检查是否存在 composer.json
            composer_file = target_full_path / "composer.json"
            if composer_file.exists():
                install_result = subprocess.run(
                    ["composer", "install", "--no-dev"], 
                    capture_output=True, text=True, 
                    cwd=target_full_path, timeout=300, shell=True
                )
                if install_result.returncode == 0:
                    return f"✅ 后端项目创建成功！\n路径：{target_full_path}\n依赖已自动安装（composer install）"
                else:
                    return f"✅ 后端项目创建成功！但 composer install 执行失败，请手动进入目录执行 composer install。\n错误信息：{install_result.stderr}"
            else:
                return f"✅ 后端项目创建成功！\n路径：{target_full_path}\n未检测到 composer.json，请确认项目结构。"
        else:
            return f"✅ 后端项目创建成功！\n路径：{target_full_path}\n注意：未检测到 PHP/Composer，请手动安装依赖（composer install）"
            
    except Exception as e:
        return f"❌ 创建失败：{str(e)}"

# ---------- 工具 14: 创建 FastAdmin 后台项目 ----------
@mcp.tool()
def create_admin_project(target_path: str, project_name: str) -> str:
    """
    基于公司标准的 FastAdmin 后台模板，创建一个新的后台项目。
    
    Args:
        target_path: 要把项目创建在哪里（例如 D:/workspace）
        project_name: 新项目的文件夹名称（例如 my-admin）
    """
    source_template = TEMPLATES_DIR / "admin-boilerplate"
    
    if not source_template.exists():
        return f"错误：找不到后台模板，请确认 assets/templates/admin-boilerplate 存在"
    
    target_full_path = Path(target_path) / project_name
    if target_full_path.exists():
        return f"错误：目标路径 {target_full_path} 已存在，请删除或更换项目名"
    
    try:
        shutil.copytree(source_template, target_full_path)
        
        php_check = subprocess.run(["php", "-v"], capture_output=True, text=True, shell=True)
        if php_check.returncode == 0:
            composer_file = target_full_path / "composer.json"
            if composer_file.exists():
                install_result = subprocess.run(
                    ["composer", "install", "--no-dev"], 
                    capture_output=True, text=True, 
                    cwd=target_full_path, timeout=300, shell=True
                )
                if install_result.returncode == 0:
                    return f"✅ 后台项目创建成功！\n路径：{target_full_path}\n依赖已自动安装（composer install）\n请配置 .env 文件，然后访问 public/index.php"
                else:
                    return f"✅ 后台项目创建成功！但 composer install 执行失败，请手动进入目录执行 composer install。\n错误信息：{install_result.stderr}"
            else:
                return f"✅ 后台项目创建成功！\n路径：{target_full_path}\n未检测到 composer.json，请确认项目结构。"
        else:
            return f"✅ 后台项目创建成功！\n路径：{target_full_path}\n注意：未检测到 PHP/Composer，请手动安装依赖（composer install）"
            
    except Exception as e:
        return f"❌ 创建失败：{str(e)}"

# ---------- 工具 15: 分批扫描 FastAdmin 后台代码 ----------
@mcp.tool()
def scan_admin_batch(project_path: str, offset: int = 0, limit: int = 20) -> str:
    """
    分批扫描 FastAdmin 后台项目的代码质量问题。
    检查：插件规范、权限硬编码、SQL 注入、前端资源路径等。
    
    Args:
        project_path: 项目的绝对路径
        offset: 从第几个文件开始扫描
        limit: 本次扫描多少个文件（建议 20-30）
    """
    path = Path(project_path)
    if not path.exists():
        return f"❌ 错误：路径 {project_path} 不存在"
    
    # 扫描 application/ 和 addons/ 下的 PHP 文件
    target_dirs = ["application", "addons"]
    all_files = []
    
    for dir_name in target_dirs:
        target_dir = path / dir_name
        if target_dir.exists():
            all_files.extend(target_dir.rglob("*.php"))
    
    # 过滤 vendor 和 runtime
    all_files = [f for f in all_files if "vendor" not in str(f) and "runtime" not in str(f)]
    all_files = sorted(set(all_files), key=lambda p: str(p))
    
    total = len(all_files)
    batch_files = all_files[offset:offset + limit]
    
    if not batch_files:
        return f"✅ 所有文件已检查完毕！共扫描了 {total} 个 PHP 文件。"
    
    issues = []
    for file in batch_files:
        with open(file, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
            lines = content.split("\n")
            
            # 检查 1: 插件是否缺少 info.ini
            if "addons" in str(file) and "info.ini" not in str(content):
                # 如果插件目录下没有 info.ini
                plugin_dir = file.parent
                if not (plugin_dir / "info.ini").exists():
                    issues.append(f"  📍 {file.relative_to(path)} - 插件目录缺少 info.ini 文件")
            
            # 检查 2: 硬编码权限判断（如 if( $user->id == 1)）
            if "==" in content and ("admin" in content or "id" in content):
                for i, line in enumerate(lines, 1):
                    if "==" in line and ("admin" in line or "is_admin" in line or "role" in line):
                        if "config" not in line and "auth" not in line:
                            issues.append(f"  📍 {file.relative_to(path)}: 第 {i} 行 - 疑似硬编码权限判断（建议使用 FastAdmin 权限模块）")
                            break
            
            # 检查 3: 直接 SQL 查询（未使用 Model）
            if "Db::query" in content or "Db::execute" in content:
                if "bind" not in content and "?" not in content:
                    issues.append(f"  📍 {file.relative_to(path)} - 使用了 Db::query 但疑似未使用参数绑定")
            
            # 检查 4: 前端资源路径错误（未使用 __PUBLIC__ 或 asset 函数）
            if "src=" in content or "href=" in content:
                if "__PUBLIC__" not in content and "asset(" not in content and "cdn" not in content:
                    issues.append(f"  📍 {file.relative_to(path)} - 前端资源路径未使用 __PUBLIC__ 或 asset()（建议使用 FastAdmin 资源加载方式）")
    
    next_offset = offset + limit
    has_more = total > next_offset
    
    report = f"📊 后台扫描进度：{next_offset if next_offset < total else total}/{total} 个 PHP 文件\n"
    if issues:
        report += f"🚨 本批次发现 {len(issues)} 个问题：\n" + "\n".join(issues)
    else:
        report += "✅ 本批次未发现问题。"
    
    if has_more:
        report += f"\n\n🔄 还有剩余文件待检查，请继续调用 scan_admin_batch，offset={next_offset}, limit={limit}"
    else:
        report += "\n\n🎉 全部扫描完成！"
    
    return report

# ---------- 工具 16: 全自动后台质量检查流水线（异步） ----------
@mcp.tool()
def run_admin_pipeline(project_path: str, fix: bool = False) -> str:
    """
    启动全自动 FastAdmin 后台质量检查流水线（异步），立即返回任务 ID。
    包括：扫描 PHP 代码、检测插件规范、权限问题、二次验证。
    """
    path = Path(project_path)
    if not path.exists():
        return f"❌ 错误：路径 {project_path} 不存在"
    
    task_id = str(uuid.uuid4())[:8]
    
    with task_lock:
        pipeline_tasks[task_id] = {
            "status": "pending",
            "project_path": project_path,
            "fix": fix,
            "result": None,
            "error": None,
            "progress": "后台任务已创建，等待启动...",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }
    
    def worker():
        try:
            with task_lock:
                pipeline_tasks[task_id]["status"] = "running"
                pipeline_tasks[task_id]["progress"] = "开始执行后台扫描..."
                pipeline_tasks[task_id]["updated_at"] = datetime.now().isoformat()
            
            import re
            all_issues = []
            total_files = 0
            offset = 0
            limit = 30
            
            # 阶段一：全量扫描
            while True:
                batch_result = scan_admin_batch(project_path, offset, limit)
                if "✅ 所有文件已检查完毕" in batch_result:
                    all_issues.append(batch_result)
                    break
                all_issues.append(batch_result)
                match = re.search(r'offset=(\d+)', batch_result)
                if match:
                    offset = int(match.group(1))
                else:
                    break
            
            for issue in all_issues:
                match = re.search(r'(\d+)/(\d+)', issue)
                if match:
                    total_files = int(match.group(2))
                    break
            
            problem_files = []
            for issue in all_issues:
                lines = issue.split('\n')
                for line in lines:
                    if '📍' in line:
                        match = re.search(r'📍 (.+?):', line)
                        if match:
                            problem_files.append(match.group(1))
            problem_files = list(set(problem_files))
            
            with task_lock:
                pipeline_tasks[task_id]["progress"] = f"扫描完成，发现 {len(problem_files)} 个有问题的文件"
                pipeline_tasks[task_id]["updated_at"] = datetime.now().isoformat()
            
            # 后台自动修复目前只做标记（更保守）
            fix_log = []
            if fix and problem_files:
                fix_log.append("⚠️ 后台自动修复功能较保守，请根据扫描报告手动处理问题。")
                # 可以添加一些简单的修复（如注释硬编码）
            
            verify_result = scan_admin_batch(project_path, 0, 30)
            
            report = "=" * 60 + "\n"
            report += "📊 后台质量检查流水线报告\n"
            report += "=" * 60 + "\n\n"
            report += f"📁 项目路径：{project_path}\n"
            report += f"📄 总 PHP 文件数：{total_files}\n"
            report += f"🚨 发现问题文件数：{len(problem_files)}\n\n"
            
            if problem_files:
                report += "📋 问题文件（前20个）：\n"
                for f in problem_files[:20]:
                    report += f"  - {f}\n"
                if len(problem_files) > 20:
                    report += f"  ... 还有 {len(problem_files)-20} 个\n"
            else:
                report += "✅ 未发现问题\n"
            
            if fix:
                report += "\n🛠️ 修复操作：\n" + "\n".join(fix_log)
            
            report += f"\n\n📌 验证结果（首批）：\n{verify_result[:600]}...\n"
            
            if fix:
                report += "\n🎉 后台流水线执行完成！请检查修复效果。"
            else:
                report += "\n💡 提示：设置 fix=True 可尝试自动修复（当前仅做标记）。"
            
            with task_lock:
                pipeline_tasks[task_id]["status"] = "completed"
                pipeline_tasks[task_id]["result"] = report
                pipeline_tasks[task_id]["progress"] = "后台流水线执行完成"
                pipeline_tasks[task_id]["updated_at"] = datetime.now().isoformat()
        
        except Exception as e:
            with task_lock:
                pipeline_tasks[task_id]["status"] = "failed"
                pipeline_tasks[task_id]["error"] = str(e)
                pipeline_tasks[task_id]["progress"] = f"执行失败：{str(e)}"
                pipeline_tasks[task_id]["updated_at"] = datetime.now().isoformat()
    
    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    
    logger.info(f"✅ 后台流水线任务已启动，任务 ID: {task_id}")
    return f"✅ 后台流水线任务已启动，任务 ID: {task_id}\n请使用 get_pipeline_status('{task_id}') 查询进度。"

# ---------- 元工具: 任务编排入口 ----------
@mcp.tool()
def orchestrate_task(task_id: str, description: str) -> str:
    """
    任务编排入口：接收自然语言任务描述，分析任务类型并建议执行路径。

    Args:
        task_id: 当前任务 ID
        description: 任务描述（如 "创建一个用户登录页面并测试"）
    """
    logger.info(f"[Orchestrator] 收到任务: {description}")

    # 简单规则判断任务类型
    task_type = "unknown"
    if any(kw in description for kw in ["创建", "新建", "生成", "开发"]):
        task_type = "construction"
        state_machine.update_task_state(
            task_id,
            AgentState.CODE_CONSTRUCTION,
            {"task_type": task_type, "description": description, "current_role": "developer"}
        )
        # ========== 新增：自动通知测试 Agent ==========
        send_message(
            from_role="developer",
            to_role="tester",
            action="code_ready",
            payload={"task_id": task_id, "description": description}
        )
        logger.info(f"[Orchestrator] 已通知 tester 角色进行测试")
        # ========== 新增结束 ==========
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
        # 默认进入需求分析
        state_machine.update_task_state(
            task_id,
            AgentState.REQUIREMENT_ANALYSIS,
            {"task_type": task_type, "description": description, "current_role": "analyst"}
        )

    # 获取更新后的状态
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
   - 如需切换角色，请调用 update_task_role(task_id, "角色名")
"""

# ---------- 启动服务器 ----------
if __name__ == "__main__":
    logger.info("===== MCP 服务器启动 =====")
    # 强制刷新所有日志句柄
    for handler in logging.getLogger().handlers:
        handler.flush()
    if "--http" in sys.argv:
        # HTTP 模式（用于代理）
        logger.info("启动 MCP 服务在 HTTP 模式，端口 8000")
        mcp.run(transport="sse", host="0.0.0.0", port=8000)
    else:
        # stdio 模式（默认）
        logger.info("启动 MCP 服务在 stdio 模式")
        mcp.run()