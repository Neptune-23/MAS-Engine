import sys
from pathlib import Path
from memory import retrieve_memory

# 将项目根目录添加到 Python 路径（让 utils、config 可导入）
sys.path.insert(0, str(Path(__file__).parent.parent))

sys.stdout = sys.stderr

import os
import shutil
import subprocess
import threading
import uuid
import time
import logging
import json
from dotenv import load_dotenv
# from playwright.sync_api import sync_playwright
from datetime import datetime
from fastmcp import FastMCP
from state_machine import TaskStateMachine, AgentState
from tool_dispatcher import DynamicToolDispatcher
from tool_dispatcher import AgentRole
from functools import wraps
from utils.logger import setup_logger
from config.settings import DB_CONFIG
from utils.security import validate_path
from tools.edit_tools import edit_file

# 导入工具实现函数（从 tools 包）
from tools.meta_tools import (
    search_tools_impl,
    get_tool_details_impl,
    orchestrate_task_impl,
    get_next_message_impl,
    auto_respond_impl,
    init_meta_tools,
    get_rules_impl,
)
from tools.analysis_tools import (
    analyze_project_structure_impl,
    infer_build_steps_impl,
)
from tools.scan_tools import (
    scan_code_batch_impl,
    scan_backend_batch_impl,
    scan_admin_batch_impl,
    run_code_check_impl,
    check_code_quality_impl,
)
from tools.fix_tools import (
    batch_fix_console_logs_impl,
    batch_fix_backend_issues_impl,
)
from tools.pipeline_tools import (
    run_quality_pipeline_impl,
    run_backend_pipeline_impl,
    run_admin_pipeline_impl,
    get_pipeline_status_impl,
    run_web_audit_impl,
    init_pipeline_tools,
)
from tools.exec_tools import (
    execute_shell_command_impl,
)

# ===== 路径定义 =====
BASE_DIR = Path(__file__).parent.parent
TEMPLATES_DIR = BASE_DIR / "assets" / "templates"
REFS_DIR = BASE_DIR / "references"
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

# ===== 日志配置 =====
logger = setup_logger()

# ===== 任务存储 =====
pipeline_tasks = {}
task_lock = threading.Lock()

# ===== Agent 间消息队列 =====
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

# ===== MCP 实例 =====
mcp = FastMCP("Company Dev Toolkit")

# ===== 状态机 =====
state_machine = TaskStateMachine(DB_CONFIG)

# ===== 注入依赖到工具模块 =====
init_meta_tools(
    mcp_instance=mcp,
    state_machine_instance=state_machine,
    refs_dir=REFS_DIR,
    logger_instance=logger,
    agent_queue=agent_message_queue,
    msg_lock=message_lock,
    send_msg_func=send_message,
    validate_func=validate_path,
)

init_pipeline_tools(
    pipeline_tasks_dict=pipeline_tasks,
    task_lock_obj=task_lock,
    logger_obj=logger,
    state_machine_obj=state_machine,
    agent_state_cls=AgentState,
    send_msg_func=send_message,
    log_dir=LOG_DIR,
)

# ===== 加载 .env =====
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)
    sys.stderr.write(f"[Config] 已加载 .env 文件: {env_path}\n")
else:
    sys.stderr.write("[Config] 警告: .env 文件不存在，将使用系统环境变量\n")

# ============================================================
# 工具注册（包装调用）
# ============================================================

@mcp.tool()
@validate_path
def search_tools(task_id: str, query: str = "", category: str = "", role: str = "developer") -> str:
    return search_tools_impl(task_id, query, category, role)

@mcp.tool()
@validate_path
def get_tool_details(tool_name: str) -> str:
    return get_tool_details_impl(tool_name)

@mcp.tool()
def orchestrate_task(task_id: str, description: str) -> str:
    return orchestrate_task_impl(task_id, description)

@mcp.tool()
def get_next_message(task_id: str, role: str) -> str:
    return get_next_message_impl(task_id, role)

@mcp.tool()
def auto_respond(task_id: str, role: str) -> str:
    return auto_respond_impl(task_id, role)

@mcp.tool()
def analyze_project_structure(project_path: str) -> str:
    return analyze_project_structure_impl(project_path)

@mcp.tool()
def infer_build_steps(fingerprint_json: str) -> str:
    return infer_build_steps_impl(fingerprint_json)

@mcp.tool()
@validate_path
def scan_code_batch(project_path: str, offset: int = 0, limit: int = 20) -> str:
    return scan_code_batch_impl(project_path, offset, limit)

@mcp.tool()
@validate_path
def scan_backend_batch(project_path: str, offset: int = 0, limit: int = 20) -> str:
    return scan_backend_batch_impl(project_path, offset, limit)

@mcp.tool()
@validate_path
def scan_admin_batch(project_path: str, offset: int = 0, limit: int = 20) -> str:
    return scan_admin_batch_impl(project_path, offset, limit)

@mcp.tool()
def run_code_check(project_path: str) -> str:
    return run_code_check_impl(project_path)

@mcp.tool()
def check_code_quality(project_path: str, auto_fix: bool = False) -> str:
    return check_code_quality_impl(project_path, auto_fix)

@mcp.tool()
def batch_fix_console_logs(file_paths: list, dry_run: bool = True) -> str:
    return batch_fix_console_logs_impl(file_paths, dry_run)

@mcp.tool()
def batch_fix_backend_issues(file_paths: list, dry_run: bool = True) -> str:
    return batch_fix_backend_issues_impl(file_paths, dry_run)

@mcp.tool()
def run_quality_pipeline(project_path: str, fix: bool = False) -> str:
    return run_quality_pipeline_impl(project_path, fix)

@mcp.tool()
def run_backend_pipeline(project_path: str, fix: bool = False) -> str:
    return run_backend_pipeline_impl(project_path, fix)

@mcp.tool()
def run_admin_pipeline(project_path: str, fix: bool = False) -> str:
    return run_admin_pipeline_impl(project_path, fix)

@mcp.tool()
def get_pipeline_status(task_id: str) -> str:
    return get_pipeline_status_impl(task_id)

@mcp.tool()
def run_web_audit(task_id: str, url: str, wait_time: int = 3) -> str:
    return run_web_audit_impl(task_id, url, wait_time)

@mcp.tool()
def get_rules(task_id: str = None, language: str = None) -> str:
    return get_rules_impl(task_id, language)

@mcp.tool()
def execute_shell_command(command: str, cwd: str = None) -> str:
    """执行 shell 命令并返回 JSON 格式结果。用于执行构建、测试、运行等命令。"""
    return execute_shell_command_impl(command, cwd)

# ===== 共享工作区文件读写工具 =====
def read_shared_file(project_path, filename):
    """从工作区读取约定文件"""
    path = os.path.join(project_path, filename)
    if not os.path.exists(path):
        return None
    with open(path, 'r', encoding='utf-8') as f:
        return json.loads(f.read())

def write_shared_file(project_path, filename, data):
    """写入共享工作区文件"""
    path = os.path.join(project_path, filename)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)


# ============================================================
# 启动入口
# ============================================================
if __name__ == "__main__":
    import argparse
    import json
    import re
    from llm_provider import get_llm_provider

    parser = argparse.ArgumentParser(description="MAS-Engine MCP Server")
    parser.add_argument("--http", action="store_true", help="启动 HTTP 模式（SSE）")
    parser.add_argument("--standalone", action="store_true", help="独立运行模式（不依赖 Cline）")
    #快捷启动
    parser.add_argument("--project", type=str, default=None, help="独立模式下指定项目路径，自动完成分析、推理、构建")
    # ==========
    parser.add_argument("--task", type=str, default="", help="独立模式下要执行的任务描述")
    args = parser.parse_args()

    # ===== 强制 stdout 重定向（仅 MCP 模式） =====
    if not args.standalone and not args.http:
        sys.stdout = sys.stderr
        sys.stderr.write("[MCP] stdout redirected to stderr for MCP protocol\n")

    # ===== 独立运行模式 / 快捷模式 =====
    if args.standalone or args.project:
        logger.info("===== MAS-Engine 独立运行模式 =====")

        # 如果使用了 --project，自动生成标准任务描述
        if args.project:
            args.standalone = True
            args.task = f"分析 {args.project} 项目结构，推理构建步骤，然后执行构建"
            sys.stderr.write(f"🔧 快捷模式：自动生成任务描述 -> {args.task}\n")

        if not args.task:
            sys.stderr.write("❌ 错误: --standalone 模式需要指定 --task 参数\n")
            sys.stderr.write("示例: python server.py --standalone --task '创建一个用户登录页面'\n")
            sys.exit(1)

        task_description = args.task
        task_id = f"standalone_{int(time.time())}"

        sys.stderr.write(f"📋 任务描述: {task_description}\n")
        sys.stderr.write(f"🆔 任务 ID: {task_id}\n")

        # 1. 初始化状态机（如果任务不存在则创建）
        task_data = state_machine.get_task_state(task_id)
        if task_data is None:
            # 直接由 Developer 开场
            initial_state = AgentState.CODE_CONSTRUCTION
            initial_role = "developer"

            state_machine.update_task_state(
                task_id,
                initial_state,
                {"description": task_description, "current_role": initial_role, "completed_steps": []}
            )
            sys.stderr.write(f"📌 任务已创建: 初始状态={initial_state}, 角色={initial_role}\n")
        else:
            sys.stderr.write(f"📌 任务已存在: 当前状态={task_data.get('current_state')}\n")

        # ===== Agent 循环 =====
        max_iterations = 15
        iteration = 0
        last_tool = None
        repeat_count = 0

        # 工具映射表（直接使用已注册的函数）
        tool_map = {
            "search_tools": search_tools,
            "get_tool_details": get_tool_details,
            "get_rules": get_rules,
            "get_pipeline_status": get_pipeline_status,
            "scan_code_batch": scan_code_batch,
            "scan_backend_batch": scan_backend_batch,
            "scan_admin_batch": scan_admin_batch,
            "batch_fix_console_logs": batch_fix_console_logs,
            "batch_fix_backend_issues": batch_fix_backend_issues,
            "run_quality_pipeline": run_quality_pipeline,
            "run_backend_pipeline": run_backend_pipeline,
            "run_admin_pipeline": run_admin_pipeline,
            "run_web_audit": run_web_audit,
            "orchestrate_task": orchestrate_task,
            "get_next_message": get_next_message,
            "analyze_project_structure": analyze_project_structure,
            "infer_build_steps": infer_build_steps,
            "execute_shell_command": execute_shell_command,
            "edit_file": edit_file,
        }

        # 基础工具列表（供 LLM 参考）
        all_tools = [
            {"name": "search_tools", "description": "搜索可用的工具"},
            {"name": "get_tool_details", "description": "获取工具详情"},
            {"name": "get_rules", "description": "获取开发规则（可指定语言）"},
            {"name": "get_pipeline_status", "description": "查询流水线状态"},
            {"name": "scan_code_batch", "description": "分批扫描代码质量"},
            {"name": "scan_backend_batch", "description": "扫描后端代码"},
            {"name": "scan_admin_batch", "description": "扫描后台代码"},
            {"name": "batch_fix_console_logs", "description": "修复 console.log"},
            {"name": "batch_fix_backend_issues", "description": "修复后端问题"},
            {"name": "run_quality_pipeline", "description": "运行质量流水线"},
            {"name": "run_backend_pipeline", "description": "运行后端流水线"},
            {"name": "run_admin_pipeline", "description": "运行后台流水线"},
            {"name": "run_web_audit", "description": "执行网页审计"},
            {"name": "orchestrate_task", "description": "任务编排"},
            {"name": "get_next_message", "description": "获取下一条消息"},
            {"name": "analyze_project_structure", "description": "分析项目结构指纹"},
            {"name": "infer_build_steps", "description": "推理构建步骤"},
            {"name": "execute_shell_command", "description": "执行 shell 命令（如构建、测试、运行等）"},
            {"name": "edit_file", "description": "通用文件编辑工具：在文件中查找并替换字符串。适用于修复代码错误。"},
        ]

        # ===== 初始化 LLM 提供者 =====
        try:
            llm_provider = get_llm_provider()
        except ValueError as e:
            sys.stderr.write(f"❌ LLM 配置错误: {e}\n")
            sys.exit(1)

            # 确保 project_path 在上下文中
if args.project:
    task_data = state_machine.get_task_state(task_id)
    if task_data:
        ctx = task_data.get("context", {})
        if not ctx.get("project_path"):
            ctx["project_path"] = args.project
            state_machine.update_task_state(task_id, task_data["current_state"], ctx)
            sys.stderr.write(f"📁 已注入项目路径：{args.project}\n")

        while iteration < max_iterations:
            iteration += 1
            sys.stderr.write(f"\n🔄 第 {iteration} 轮决策\n")

            # 2. 获取当前状态和上下文
            task_data = state_machine.get_task_state(task_id)
            if task_data is None:
                sys.stderr.write("⚠️ 任务状态丢失，退出循环\n")
                break
            
            current_state = task_data.get("current_state")
            context = task_data.get("context", {})
            current_role = context.get("current_role", "developer")
            completed_steps = context.get("completed_steps", [])

            # 2. 提取项目路径（现在 context 已定义）
            project_path = context.get("project_path")

            if current_state == AgentState.CODE_CONSTRUCTION:
                current_role = "developer"
            elif current_state == AgentState.WEB_TESTING:
                current_role = "tester"
            elif current_state == AgentState.SELF_HEALING:
                current_role = "fixer"

            elif current_state == AgentState.FIX_APPLY:
                current_role = "developer"
                context["current_role"] = current_role
                instruction_file = os.path.join(project_path, "fix_instruction.json")
                
                if os.path.exists(instruction_file):
                    with open(instruction_file, 'r', encoding='utf-8') as f:
                        instruction = json.load(f)
                    sys.stderr.write(f"📌 执行修复指令: {instruction}\n")
                    
                    target_file = instruction.get("target_file")
                    old_string = instruction.get("old_string")
                    new_string = instruction.get("new_string")
                    
                    fix_success = False
                    fix_error = None
                    
                    if target_file and os.path.exists(target_file):
                        try:
                            with open(target_file, 'r', encoding='utf-8') as f:
                                content = f.read()
                            
                            # ---------- 尝试1：精确匹配 ----------
                            if old_string in content:
                                new_content = content.replace(old_string, new_string)
                                with open(target_file, 'w', encoding='utf-8') as f:
                                    f.write(new_content)
                                fix_success = True
                                sys.stderr.write(f"✅ 精确替换成功: {target_file}\n")
                            else:
                                # ---------- 尝试2：忽略注释再匹配 ----------
                                old_string_no_comment = old_string.split('#')[0].rstrip()
                                if old_string_no_comment:
                                    lines = content.splitlines(keepends=True)
                                    new_lines = []
                                    replaced = False
                                    for line in lines:
                                        if not replaced and old_string_no_comment in line:
                                            # 用 new_string 替换该行（保留原始缩进和注释）
                                            # 但 new_string 可能不带缩进，我们保留原行的缩进
                                            indent = line[:len(line) - len(line.lstrip())]
                                            # 如果 new_string 没有缩进，补上
                                            if not new_string.lstrip() == new_string:
                                                # new_string 已有缩进，直接替换
                                                new_line = line.replace(old_string_no_comment, new_string)
                                            else:
                                                new_line = indent + new_string + '\n'
                                            new_lines.append(new_line)
                                            replaced = True
                                            sys.stderr.write(f"✅ 使用忽略注释方式替换: {line.strip()} -> {new_string}\n")
                                        else:
                                            new_lines.append(line)
                                    if replaced:
                                        new_content = ''.join(new_lines)
                                        with open(target_file, 'w', encoding='utf-8') as f:
                                            f.write(new_content)
                                        fix_success = True
                                    else:
                                        fix_error = f"未找到匹配行（原始: {old_string}, 忽略注释: {old_string_no_comment}）"
                                        sys.stderr.write(f"❌ {fix_error}\n")
                                else:
                                    fix_error = "old_string 为空"
                        except Exception as e:
                            fix_error = str(e)
                            sys.stderr.write(f"❌ 文件操作失败: {e}\n")
                    else:
                        fix_error = f"目标文件不存在: {target_file}"
                        sys.stderr.write(f"❌ {fix_error}\n")
                    
                    # 写入修复结果
                    fix_applied = {
                        "success": fix_success,
                        "error": fix_error,
                        "target_file": target_file
                    }
                    with open(os.path.join(project_path, "fix_applied.json"), 'w', encoding='utf-8') as f:
                        json.dump(fix_applied, f, indent=2)
                    
                    if fix_success:
                        # 删除旧的 .build_success 文件，强制重新构建
                        build_success_file = os.path.join(project_path, ".build_success")
                        if os.path.exists(build_success_file):
                            os.remove(build_success_file)
                            sys.stderr.write("🗑️ 已删除旧的 .build_success，强制重新构建\n")
                        
                        # 设置重新构建标志
                        context["require_rebuild"] = True
                        context["fix_applied"] = True
                        
                        # 删除指令文件，切换到 CODE_CONSTRUCTION
                        if os.path.exists(instruction_file):
                            os.remove(instruction_file)
                        state_machine.update_task_state(task_id, AgentState.CODE_CONSTRUCTION, context)
                        sys.stderr.write("🔄 修复已应用，切换回 Developer 重新构建\n")
                        continue
                    else:
                        # 修复失败，删除失效的指令，增加计数
                        os.remove(instruction_file)  # 清除失效指令
                        context["fixer_instruction_written"] = False  # 让 Fixer 重新生成
                        context["last_error"] = f"FIX_APPLY 失败: {fix_error}"
                        context["fix_attempt_count"] = context.get("fix_attempt_count", 0) + 1
                        if context["fix_attempt_count"] >= 3:
                            sys.stderr.write("❌ 修复尝试达到上限，标记任务失败\n")
                            state_machine.update_task_state(task_id, AgentState.HUMAN_INTERRUPT, context)
                            break
                        else:
                            sys.stderr.write(f"⚠️ 修复失败，重试次数: {context['fix_attempt_count']}/3，重新生成指令\n")
                            state_machine.update_task_state(task_id, AgentState.SELF_HEALING, context)
                            continue
                else:
                    sys.stderr.write("⚠️ 未找到修复指令，跳过 FIX_APPLY\n")
                    state_machine.update_task_state(task_id, AgentState.SELF_HEALING, context)
                    continue
            else:
                current_role = context.get("current_role", "developer")
            context["current_role"] = current_role

            sys.stderr.write(f"📌 当前状态: {current_state}, 角色: {current_role}\n")
            sys.stderr.write(f"📌 已完成步骤: {', '.join(completed_steps) if completed_steps else '暂无'}\n")

            if current_state == AgentState.DELIVERY_COMPLETED:
                sys.stderr.write("✅ 任务已标记为完成\n")
                break

            # ===== 3. 构建进度提示（强化版） =====
            progress_hint = ""
            if completed_steps:
                progress_hint = f"\n✅ 已完成步骤: {', '.join(completed_steps)}"
                # 情况1：分析已完成，但推理未完成
                if "analyze_project_structure" in completed_steps and "infer_build_steps" not in completed_steps:
                    progress_hint += "\n🚨 重要：你已经完成了项目结构分析。下一步必须调用 `infer_build_steps`，不要再调用 `analyze_project_structure`。"
                    fingerprint = context.get("fingerprint")
                    if fingerprint:
                        preview = fingerprint[:200] + "..." if len(fingerprint) > 200 else fingerprint
                        progress_hint += f"\n📌 上一步分析得到的指纹为：{preview}"
                        progress_hint += f"\n📌 调用 `infer_build_steps` 时，请将完整的指纹 JSON 作为 `fingerprint_json` 参数传入。"
                    else:
                        progress_hint += f"\n📌 调用示例：{{\"tool\": \"infer_build_steps\", \"arguments\": {{\"fingerprint_json\": \"<上一步返回的完整 JSON 字符串>\", \"task_id\": \"{task_id}\"}}}}"
                # 情况2：推理已完成，但执行未完成
                elif "infer_build_steps" in completed_steps and "execute_shell_command" not in completed_steps:
                    build_command = context.get("build_command")
                    if build_command:
                        progress_hint += f"\n🚀 下一步：调用 `execute_shell_command` 执行构建命令。建议命令：`{build_command}`，工作目录：`{context.get('project_path', 'D:/test_rust_project')}`。"
                    else:
                        progress_hint += "\n🚀 下一步：调用 `execute_shell_command` 执行构建命令（请根据推理结果构造命令）。"
                    progress_hint += "\n📌 执行完构建后，请确认构建结果，然后返回 `tool: none` 结束任务。"
                # 情况3：执行已完成（判断构建是否成功）
                elif "execute_shell_command" in completed_steps:
                    # 检查是否强制重新构建
                    require_rebuild = context.get("require_rebuild", False)
                    
                    if require_rebuild:
                        # 强制重新构建
                        build_command = context.get("build_command")
                        if build_command:
                            progress_hint += f"\n🚨 由于修复已应用，必须重新执行构建命令：`{build_command}`。"
                            progress_hint += f"\n📌 工作目录：`{context.get('project_path')}`。"
                            progress_hint += "\n📌 即使 `execute_shell_command` 已在已完成步骤中，也必须重新执行。"
                        else:
                            progress_hint += "\n🚨 由于修复已应用，必须重新执行构建命令。请调用 `execute_shell_command`。"
                        progress_hint += "\n📌 构建成功后，不要返回 `none`，等待状态机自动跳转。"
                    else:
                        last_build = context.get("last_build_result", {})
                        if last_build.get("success") is False:
                            error_msg = last_build.get("stderr", "")[:300]
                            progress_hint += f"\n⚠️ 构建执行失败！错误信息：{error_msg}..."
                            progress_hint += "\n🔧 请分析错误信息，调用 `execute_shell_command` 执行修复命令（如配置镜像、安装工具链），然后重新执行构建。"
                            progress_hint += f"\n📌 如果修复完成，再次调用 `execute_shell_command` 执行构建命令：`{context.get('build_command', 'cargo build')}`。"
                            progress_hint += "\n📌 最多尝试修复 2 次，若仍失败则返回错误报告。"
                        else:
                            progress_hint += "\n✅ 所有步骤已完成。请返回 `{\"tool\": \"none\", \"message\": \"任务已完成\"}` 结束任务。"
                else:
                    pass
            else:
                progress_hint = "\n📌 当前未完成任何步骤，**必须**先调用 `analyze_project_structure`。"
            if project_path:
                progress_hint += f"\n   参数示例：`{{\"tool\": \"analyze_project_structure\", \"arguments\": {{\"project_path\": \"{project_path}\"}}}}`"
            else:
                progress_hint += "\n   请确保传入正确的 `project_path`。"
                progress_hint += "\n   **禁止返回 `none`，直到你至少执行了一次工具调用。**"

            if completed_steps:
                completed_tools_str = ", ".join(completed_steps)
                progress_hint += f"\n⚠️ 禁止重复调用已完成的步骤：{completed_tools_str}。"

            # ===== 4. 构建错误提示（用于 self_healing 状态） =====
            error_hint = ""
            if current_state == AgentState.SELF_HEALING:
                last_error = context.get("last_error", "")
                failed_tool = context.get("failed_tool", "")
                last_diag = context.get("last_diagnostic_result", {})
                build_cmd = context.get("build_command")
                build_retry_count = context.get("build_retry_count", 0)

                if last_error:
                    error_hint = f"\n⚠️ 警告：上一轮调用 {failed_tool} 时失败，错误信息：{last_error}"

                    # 如果诊断命令已经成功执行过，则引导重新构建
                    if last_diag.get("success") is True:
                        error_hint += "\n✅ 诊断命令已成功执行（工具链可能已就绪）。"
                        if build_cmd:
                            error_hint += f"\n🚀 请立即调用 `execute_shell_command` 执行构建命令：`{build_cmd}`。"
                        else:
                            error_hint += "\n🚀 请立即执行构建命令（`cargo build`）。"
                        error_hint += "\n📌 注意：在自我修复状态下，可以重复调用构建命令，即使它已出现在已完成步骤中。"
                        error_hint += "\n📌 禁止再次重复执行已经成功的诊断命令。"
                    else:
                        # 如果已经连续失败 2 次以上，并且没有成功诊断，给出明确诊断建议
                        if build_retry_count >= 2:
                            error_hint += "\n🔧 已经连续多次构建失败，建议先执行以下诊断命令安装 MSVC 工具链："
                            error_hint += "\n   `rustup toolchain install stable-x86_64-pc-windows-msvc`"
                            error_hint += "\n   然后再执行 `cargo build`。"
                        else:
                            # 原有的错误类型分析
                            if "could not find `Cargo.toml`" in last_error:
                                error_hint += "\n🔧 原因：执行命令时工作目录不正确。请使用 `cd` 切换到正确目录，或指定 `workdir` 参数。"
                            elif "connection timed out" in last_error or "failed to connect" in last_error:
                                error_hint += "\n🔧 原因：网络连接问题（可能是 crates.io 被墙）。请执行以下命令配置清华镜像源："
                                error_hint += "\n   `echo \"[source.crates-io]\\nreplace-with = 'tuna'\\n[source.tuna]\\nregistry = 'https://mirrors.tuna.tsinghua.edu.cn/git/crates.io-index.git'\" > ~/.cargo/config.toml`"
                            elif "linker 'cc' not found" in last_error or "link.exe not found" in last_error:
                                error_hint += "\n🔧 原因：缺少 C 编译器 / MSVC 链接器。请执行以下命令安装 MSVC 工具链："
                                error_hint += "\n   `rustup toolchain install stable-x86_64-pc-windows-msvc`"
                                error_hint += "\n   或者安装 Visual Studio Build Tools（包含 C++ 开发工作负载）。"
                            else:
                                error_hint += "\n🔧 请分析错误并调用 `execute_shell_command` 执行修复命令，然后重新构建。"
                            error_hint += "\n📌 修复完成后，再次调用 `execute_shell_command` 执行构建命令。"
                else:
                    error_hint = "\n⚠️ 当前处于自我修复阶段，请检查之前的错误并调整策略。"

            # ===== 5. 构建明确的“上一轮执行摘要 + 行动指引” =====
            # 根据当前角色，给出不同的“产出要求”指引
            action_guidance = ""
            if current_role == "developer":
                action_guidance = "\n🚀 你是 Developer。请按以下顺序执行任务："
                action_guidance += "\n  1. 先调用 `analyze_project_structure` 分析项目（使用上方提供的项目路径）。"
                action_guidance += "\n  2. 然后调用 `infer_build_steps` 推理构建命令（将上一步返回的完整 JSON 作为参数）。"
                action_guidance += "\n  3. 最后调用 `execute_shell_command` 执行推理出的构建命令。"
                action_guidance += "\n  4. **构建成功后**，系统会自动检测到 `.build_success` 文件，状态才会推进。"
                action_guidance += "\n  5. **在未完成上述三步之前，禁止返回 `{\"tool\": \"none\"}`。**"
            elif current_role == "tester":
                action_guidance = "\n🚀 你是 Tester。你的任务是执行测试，**并确保在项目目录下生成 `test_report.json` 文件**（内容包含 {\"status\": \"pass\"} 或 {\"status\": \"fail\"}）。"
            elif current_role == "fixer":
                action_guidance = """
🚀 你是 Fixer。你的任务是根据测试报告修复代码，**必须**按以下步骤执行：

1. **先调用 `edit_file` 修复代码错误**（你需要从测试报告中找到错误信息和具体代码位置）。
   示例调用：
   {"tool": "edit_file", "arguments": {"file_path": "D:/test_multi_agent_py/test_main.py", "replace_pattern": "assert add(2, 2) == 5", "replace_with": "assert add(2, 2) == 4"}}

2. **修复完成后，调用 `execute_shell_command` 重新运行测试**（例如 `pytest -v`）。
   测试成功后，系统会自动生成 `fix_result.json`。

3. **只有 `fix_result.json` 存在且内容为 `{"success": true}` 时，你才能返回 `{"tool": "none"}`**。

⚠️ 在未执行上述三步之前，禁止返回 `none`。
"""
            else:
                # 兜底
                action_guidance = "\n📌 请分析项目结构并执行构建。"

            # ===== 构造系统提示（根据角色分流） =====
            if current_role == "tester":
                role_specific_instruction = "你是一个 Tester 角色。系统会自动执行测试并生成报告文件，你只需根据文件内容返回对应的 `none` 消息。"
            elif current_role == "fixer":
                role_specific_instruction = """
你是一个 Fixer 角色。系统已经为你提供了测试报告和源代码内容（见下方的“情报摘要”）。

你的任务：
1. 分析情报摘要中的错误信息和代码内容。
2. 找出需要修复的字符串。
3. 调用 `edit_file` 工具执行修复。
   - 参数示例：`{"file_path": "D:/test_multi_agent_py/test_main.py", "replace_pattern": "assert add(2, 2) == 5", "replace_with": "assert add(2, 2) == 4"}`

修复完成后，调用 `execute_shell_command` 执行测试命令（如 `pytest`）验证修复效果。
只有测试通过，才能返回 `{"tool": "none", "message": "修复成功"}`。
"""
            else:
                role_specific_instruction = """
你是一个 Developer 角色。负责执行构建命令，确保构建成功。
执行步骤：
1. 调用 `execute_shell_command` 执行构建命令。
2. 构建成功后，返回 `{"tool": "none", "message": "任务已完成"}`。
"""

            # ---- 新增：明确项目路径和第一步动作 ----
                project_path = context.get("project_path")
            if project_path is None and args.project:
                project_path = args.project
                context["project_path"] = project_path
                state_machine.update_task_state(task_id, current_state, context)

            if project_path:
                first_step_hint = f"\n📁 项目路径已确定为：`{project_path}`"
                first_step_hint += f"\n🔧 **你首先必须调用 `analyze_project_structure`**，参数为 `{{'project_path': '{project_path}'}}`。"
                first_step_hint += "\n   调用示例：`{\"tool\": \"analyze_project_structure\", \"arguments\": {\"project_path\": \"...\"}}`"
            else:
                first_step_hint = "\n⚠️ 未检测到项目路径，请先调用 `analyze_project_structure` 并传入正确的路径。"

            system_prompt = f"""你是一个 AI 开发助手，当前角色是 {current_role}，任务 ID 是 {task_id}。
            {first_step_hint}
            

⚡ 绝对规则：你的回答必须只包含一个有效的 JSON 对象，不要有任何额外文字。
⚡ 不要输出任何解释、标题、描述、思考过程、Markdown 格式。
⚡ 只输出 JSON 字典，例如：{{"tool": "analyze_project_structure", "arguments": {{"project_path": "D:/..."}}}}

当前状态: {current_state}
当前角色: {current_role}
{action_guidance}
{progress_hint}
{error_hint}
{role_specific_instruction}

你可以调用以下工具来完成任务：
{json.dumps(all_tools, indent=2, ensure_ascii=False)}

用户任务: {task_description}

重要规则：
- 你的回答必须只包含一个有效的 JSON 对象，不要有任何额外文字
- 所有工具调用都必须包含 task_id 参数（值 {task_id}）
- JSON 格式: {{"tool": "工具名", "arguments": {{"参数1": "值1", "task_id": "{task_id}"}}}}
- 如果任务已完成，返回 {{"tool": "none", "message": "任务已完成"}}
- 如果某个工具已经出现在“已完成步骤”列表中，则严禁再次调用该工具，必须执行下一步。
- 如果你是 Fixer，禁止调用 analyze_project_structure、infer_build_steps 等已完成步骤。你只需要调用 edit_file 和 execute_shell_command。
"""

            # ===== 6. 智能诊断干预（根据语言规则） =====
            force_diagnostic = False
            diagnostic_attempted = context.get("diagnostic_attempted", False)
            if current_state == AgentState.SELF_HEALING and not diagnostic_attempted:
                build_retry_count = context.get("build_retry_count", 0)
                last_diag = context.get("last_diagnostic_result", {})
                if build_retry_count >= 2 and not last_diag.get("success"):
                    force_diagnostic = True

            if force_diagnostic:
                language = context.get("language") or "Rust"
                rules_json = get_rules_impl(task_id, language)
                try:
                    rules_data = json.loads(rules_json)
                    diag_rules = rules_data.get("diagnostic_rules", {})
                    if diag_rules:
                        diag_cmd = diag_rules.get("diagnostic_command")
                        if diag_cmd:
                            sys.stderr.write(f"🔧 自动触发诊断命令：{diag_cmd}\n")
                            clean_args = {
                                "command": diag_cmd,
                                "cwd": context.get("project_path", "D:/test_rust_project")
                            }
                            tool_func = tool_map.get("execute_shell_command")
                            if tool_func:
                                try:
                                    result = tool_func(**clean_args)
                                    parsed = json.loads(result)
                                    context["last_diagnostic_result"] = parsed
                                    context["diagnostic_attempted"] = True

                                    # -------- 诊断失败时，直接执行修复命令 --------
                                    if not parsed.get("success"):
                                        sys.stderr.write("⚠️ 诊断命令失败，将执行修复命令安装 MSVC 工具链。\n")
                                        fix_cmd = "rustup toolchain install stable-x86_64-pc-windows-msvc --force"
                                        fix_args = {
                                            "command": fix_cmd,
                                            "cwd": context.get("project_path", "D:/test_rust_project")
                                        }
                                        fix_result = tool_func(**fix_args)
                                        fix_parsed = json.loads(fix_result)
                                        context["last_fix_result"] = fix_parsed
                                        if fix_parsed.get("success"):
                                            sys.stderr.write("✅ 修复成功！重置构建计数器，准备重新构建。\n")
                                            context["build_retry_count"] = 0
                                            context["diagnostic_attempted"] = True
                                        else:
                                            sys.stderr.write("⚠️ 修复失败，错误信息：" + fix_parsed.get("stderr", "")[:200] + "\n")
                                    else:
                                        sys.stderr.write("✅ 诊断命令成功，现在可以重新构建\n")
                                        context["build_retry_count"] = 0
                                    # -----------------------------------------------------------------
                                except Exception as e:
                                    sys.stderr.write(f"❌ 诊断命令执行异常: {e}\n")
                                    context["last_diagnostic_result"] = {"success": False, "stderr": str(e)}
                                    context["diagnostic_attempted"] = True
                                state_machine.update_task_state(task_id, current_state, context)
                            else:
                                sys.stderr.write("⚠️ 未找到 execute_shell_command 工具\n")
                        else:
                            sys.stderr.write("⚠️ 该语言未配置诊断命令，跳过自动诊断\n")
                    else:
                        sys.stderr.write("⚠️ 未找到该语言的诊断规则，跳过自动诊断\n")
                except Exception as e:
                    sys.stderr.write(f"❌ 解析诊断规则失败: {e}\n")
                    context["diagnostic_attempted"] = True
                    state_machine.update_task_state(task_id, current_state, context)

                # 强制诊断后，跳过本轮 LLM 调用，直接进入下一轮
                continue

                        # ===== 状态机硬跳转逻辑（基于产出文件验证） =====
            project_path = context.get("project_path")
            
            # ---- 新增：如果项目路径还未确定，跳过本轮硬跳转 ----
            if not project_path:
                # 路径还没拿到，让 Agent 继续执行第一轮分析
                pass
            else:
                # 1. 如果 Developer 构建成功且生成了产物文件
                if current_role == "developer":
                    last_build = context.get("last_build_result", {})
                    # 检查构建是否成功，且产出文件（.build_success）存在
                    build_success_file = os.path.join(project_path, ".build_success")
                    if last_build.get("success") is True and os.path.exists(build_success_file):
                        state_machine.update_task_state(task_id, AgentState.WEB_TESTING, context)
                        sys.stderr.write("🔄 检测到构建产物，切换至 Tester 角色进行测试\n")
                        continue

                # 2. 如果 Tester 测试产出报告并失败，切换到 Fixer
                elif current_role == "tester":
                    report_file = os.path.join(project_path, "test_report.json")
                    if os.path.exists(report_file):
                        try:
                            with open(report_file, 'r', encoding='utf-8') as f:
                                report = json.load(f)
                            if report.get("status") == "fail":
                                state_machine.update_task_state(task_id, AgentState.SELF_HEALING, context)
                                sys.stderr.write("🔄 检测到测试失败报告，切换至 Fixer 角色进行修复\n")
                                continue
                            elif report.get("status") == "pass":
                                sys.stderr.write("✅ 检测到测试通过报告，任务完成。\n")
                                state_machine.update_task_state(task_id, AgentState.DELIVERY_COMPLETED, context)
                                break
                        except:
                            pass

                # 3. 如果 Fixer 修复成功且生成了修复产物
                elif current_role == "fixer":
                    fix_file = os.path.join(project_path, "fix_result.json")
                    if os.path.exists(fix_file):
                        try:
                            with open(fix_file, 'r') as f:
                                fix_data = json.load(f)
                            if fix_data.get("success") is True:
                                state_machine.update_task_state(task_id, AgentState.CODE_CONSTRUCTION, context)
                                sys.stderr.write("🔄 检测到修复成功文件，切换回 Developer 角色重新构建\n")
                                continue
                            # 4. 如果存在修复指令且尚未应用，切换到 FIX_APPLY
                            if current_role == "fixer" and context.get("fixer_instruction_written") and context.get("awaiting_fix_apply"):
                                state_machine.update_task_state(task_id, AgentState.FIX_APPLY, context)
                                sys.stderr.write("🔄 检测到修复指令，切换至 FIX_APPLY 状态\n")
                                context["awaiting_fix_apply"] = False
                                state_machine.update_task_state(task_id, AgentState.FIX_APPLY, context)
                                continue
                        except:
                            pass
            # ==============================================

                        # ===== 6.6 系统层情报先行（为 Fixer 提供决策依据） =====
            project_path = context.get("project_path")
            if project_path:
                # ---------- 如果是 Tester，执行测试 ----------
                if current_role == "tester":
                    report_file = os.path.join(project_path, "test_report.json")
                    if not os.path.exists(report_file):
                        sys.stderr.write("🧩 Tester 接管：执行测试\n")
                        test_steps = context.get("test_steps", [])
                        if not test_steps:
                            # 根据语言 fallback
                            lang = context.get("language", "").lower()
                            if "python" in lang:
                                test_steps = ["pytest -v"]
                            elif "node" in lang or "javascript" in lang:
                                test_steps = ["npm test"]
                            elif "rust" in lang:
                                test_steps = ["cargo test"]
                        if test_steps:
                            test_cmd = f"cd /d {project_path} && {test_steps[0]}"
                            result = tool_map["execute_shell_command"](command=test_cmd, cwd=project_path)
                            parsed = json.loads(result)
                            if parsed.get("success"):
                                report = {"status": "pass"}
                            else:
                                report = {"status": "fail", "error": parsed.get("stderr", "")[:500]}
                            write_shared_file(project_path, "test_report.json", report)
                            context["test_report"] = report
                            state_machine.update_task_state(task_id, current_state, context)
                        continue

                # ---------- 如果是 Fixer，系统代为侦查 ----------
                if current_role == "fixer":
                    report_file = os.path.join(project_path, "test_report.json")
                    if os.path.exists(report_file):
                        # 读取测试报告
                        try:
                            with open(report_file, 'r') as f:
                                report_data = json.load(f)
                            report_summary = f"测试报告: {report_data}"
                            sys.stderr.write("🧩 Fixer 情报侦查：读取测试报告成功\n")
                        except Exception as e:
                            report_summary = f"读取测试报告失败: {e}"
                            sys.stderr.write(f"⚠️ Fixer 情报侦查异常: {e}\n")
                    else:
                        report_summary = "未找到测试报告，可能测试未执行。"
                        sys.stderr.write("⚠️ Fixer 情报侦查：未找到测试报告\n")

                    # 读取源代码（例如 test_main.py，可根据上下文调整）
                    code_file = os.path.join(project_path, "test_main.py")
                    if os.path.exists(code_file):
                        try:
                            with open(code_file, 'r') as f:
                                code_content = f.read()
                            code_summary = f"代码文件 (test_main.py) 内容:\n{code_content}"
                            sys.stderr.write("🧩 Fixer 情报侦查：读取代码成功\n")
                        except Exception as e:
                            code_summary = f"读取代码文件失败: {e}"
                            sys.stderr.write(f"⚠️ Fixer 情报侦查异常: {e}\n")
                    else:
                        code_summary = "未找到 test_main.py 文件。"
                        sys.stderr.write("⚠️ Fixer 情报侦查：未找到 test_main.py\n")

                    # 将情报注入上下文，让 LLM 在下一轮直接看到
                    context["fixer_intel"] = f"""
                    === 情报摘要 ===
                    {report_summary}

                    {code_summary}
                    """
                state_machine.update_task_state(task_id, current_state, context)
                    # 不继续，让下一轮 LLM 看到这些情报并决策

                # ===== Fixer 分析并输出修复指令到共享工作区 =====
                if current_role == "fixer" and not context.get("fixer_instruction_written"):
                    # 构造 Fixer 提示，强制输出 JSON
                    fixer_prompt = f"""
                你是一个 Fixer 角色。根据以下测试报告和源代码，输出修复指令。

                测试报告：
                {report_summary}

                源代码：
                {code_summary}

                请输出 JSON 格式的修复指令，只输出 JSON，不要有任何额外文字：
                {{"type": "fix_instruction", "target_file": "文件路径", "operation": "replace", "old_string": "要替换的原文（必须是代码中的精确字符串，包括缩进和空格）", "new_string": "替换后的新内容", "reason": "修复原因"}}
                """
                    # 调用 LLM
                    fixer_response = llm_provider.generate_response(
                        system_prompt="你是一个 Fixer 角色，只输出 JSON。",
                        user_prompt=fixer_prompt,
                        temperature=0.1
                    )
                    sys.stderr.write(f"🧩 Fixer 生成指令: {fixer_response}\n")
                    
                    # 验证并写入
                    try:
                        fixer_instruction = json.loads(fixer_response)
                        if fixer_instruction.get("type") == "fix_instruction":
                            # 写入共享工作区
                            instruction_file = os.path.join(project_path, "fix_instruction.json")
                            with open(instruction_file, 'w', encoding='utf-8') as f:
                                json.dump(fixer_instruction, f, indent=2)
                            sys.stderr.write(f"✅ 修复指令已写入: {instruction_file}\n")
                            context["fixer_instruction_written"] = True
                            # 立即切换到 FIX_APPLY 状态
                            state_machine.update_task_state(task_id, AgentState.SELF_HEALING, context)
                            # 设置一个标记，让下一轮状态机识别
                            context["awaiting_fix_apply"] = True
                            state_machine.update_task_state(task_id, AgentState.SELF_HEALING, context)
                            # 强制继续下一轮
                            continue
                    except json.JSONDecodeError:
                        sys.stderr.write(f"❌ Fixer 输出无效 JSON: {fixer_response}\n")
                        # 写入失败标记
                        context["fixer_instruction_written"] = False
                        state_machine.update_task_state(task_id, current_state, context)

            # ===== 7. 调用 LLM =====
            try:
                 raw_text = llm_provider.generate_response(
                    system_prompt=system_prompt,
                    user_prompt=f"请继续执行任务: {task_description}",
                    temperature=0.1
                )
            except RuntimeError as e:
                sys.stderr.write(f"❌ LLM 调用失败: {e}\n")
                break

            sys.stderr.write(f"📝 LLM 原始响应: {raw_text}\n")

            # 8. 解析 JSON
            json_match = re.search(r'\{.*\}', raw_text, re.DOTALL)
            if not json_match:
                sys.stderr.write("⚠️ 未找到 JSON 块，无法解析，尝试重试（本轮跳过）\n")
                context["last_error"] = "LLM 输出格式错误"
                state_machine.update_task_state(task_id, AgentState.REQUIREMENT_EXTRACTION, context)
                continue  # 跳过本轮，下一轮重新调用 LLM
            json_str = json_match.group(0)
            try:
                decision = json.loads(json_str)
            except json.JSONDecodeError:
                sys.stderr.write(f"⚠️ JSON 解析失败: {json_str}\n")
                # 记录错误，让下一轮重新尝试
                context["last_error"] = f"LLM返回的JSON格式错误: {json_str[:200]}"
                state_machine.update_task_state(task_id, current_state, context)
                continue  # 不退出，重试

            tool_name = decision.get("tool")
            arguments = decision.get("arguments", {})

            # 9. 如果 LLM 返回 "none"，任务完成
            if tool_name == "none":
                sys.stderr.write(f"⏩ Agent 提交完成信号，等待状态机硬跳转验证...\n")
            # 不在这里做任何验证，让状态机硬跳转逻辑根据文件存在性处理
                continue

            # 10. 自动注入 task_id
            if "task_id" not in arguments:
                arguments["task_id"] = task_id
                sys.stderr.write(f"🔧 自动注入 task_id\n")

            sys.stderr.write(f"📌 解析结果: tool={tool_name}, args={arguments}\n")

            # 11. 参数过滤
            tool_params = {
                "search_tools": ["task_id", "query", "category", "role"],
                "get_tool_details": ["tool_name"],
                "get_rules": ["task_id", "language"],
                "get_pipeline_status": ["task_id"],
                "scan_code_batch": ["project_path", "offset", "limit"],
                "scan_backend_batch": ["project_path", "offset", "limit"],
                "scan_admin_batch": ["project_path", "offset", "limit"],
                "batch_fix_console_logs": ["file_paths", "dry_run"],
                "batch_fix_backend_issues": ["file_paths", "dry_run"],
                "run_quality_pipeline": ["project_path", "fix"],
                "run_backend_pipeline": ["project_path", "fix"],
                "run_admin_pipeline": ["project_path", "fix"],
                "run_web_audit": ["task_id", "url", "wait_time"],
                "orchestrate_task": ["task_id", "description"],
                "get_next_message": ["task_id", "role"],
                "analyze_project_structure": ["project_path"],
                "infer_build_steps": ["fingerprint_json"],
                "execute_shell_command": ["command", "cwd", "workdir"],   # 添加 workdir 别名
            }
            allowed_params = tool_params.get(tool_name, [])
            clean_args = {k: v for k, v in arguments.items() if k in allowed_params}

            # 特殊映射：将 workdir 映射到 cwd（execute_shell_command 需要 cwd）
            if tool_name == "execute_shell_command":
                if "workdir" in clean_args and "cwd" not in clean_args:
                    clean_args["cwd"] = clean_args.pop("workdir")
                    sys.stderr.write("🔧 已将 workdir 映射到 cwd\n")
                # 如果 cwd 仍然不存在，尝试从上下文中获取项目路径
                if "cwd" not in clean_args or clean_args.get("cwd") is None:
                    project_path = context.get("project_path")
                    if project_path:
                        clean_args["cwd"] = project_path
                        sys.stderr.write(f"🔧 自动设置 cwd: {project_path}\n")

            sys.stderr.write(f"📌 清洗后参数: {json.dumps(clean_args, indent=2, ensure_ascii=False)}\n")

            # 12. 特殊处理 infer_build_steps
            if tool_name == "infer_build_steps":
                    try:
                        steps = json.loads(result)
                        if "error" not in steps:
                            build_steps = steps.get("build_steps", [])
                            if build_steps:
                                context["build_command"] = build_steps[0]
                                sys.stderr.write(f"📌 已保存构建命令: {context['build_command']}\n")

                            # ===== 保存测试步骤到上下文 =====
                            test_steps = steps.get("test_steps", [])
                            if test_steps:
                                context["test_steps"] = test_steps
                                sys.stderr.write(f"📌 已保存测试命令: {test_steps[0]}\n")

                            # ===== 【关键修复】立刻持久化上下文，防止切换时丢失 =====
                            state_machine.update_task_state(task_id, current_state, context)

                                # ------- 调试: 打印当前上下文中的 test_steps -------
                            sys.stderr.write(f"DEBUG [保存后]: context['test_steps'] = {context.get('test_steps')}\n")
                            # ===================================
                            
                            sys.stderr.write("📌 已保存构建和测试步骤\n")
                    except Exception as e:
                        sys.stderr.write(f"⚠️ 解析 infer_build_steps 结果失败: {e}\n")

            # ========== 13. 执行工具 ==========
            # ---- 特殊参数转换：infer_build_steps 的 fingerprint_json 应为字符串 ----
            if tool_name == "infer_build_steps" and "fingerprint_json" in clean_args:
                if isinstance(clean_args["fingerprint_json"], dict):
                    clean_args["fingerprint_json"] = json.dumps(clean_args["fingerprint_json"], ensure_ascii=False)
                    sys.stderr.write("🔧 已将 fingerprint_json 从 dict 转为 JSON 字符串\n")
            tool_func = tool_map.get(tool_name)
            if not tool_func:
                sys.stderr.write(f"⚠️ 未知工具: {tool_name}\n")
                continue

            try:
                result = tool_func(**clean_args)
                sys.stderr.write(f"✅ 工具执行成功\n")
                sys.stderr.write(f"📊 结果摘要: {str(result)[:500]}...\n")

                                # -------- 保存执行结果（区分构建命令与诊断命令） --------
                if tool_name == "execute_shell_command":
                    try:
                        parsed_result = json.loads(result)
                        build_cmd = context.get("build_command")
                        current_cmd = clean_args.get("command")
                        # === 注意：先定义 is_build，再使用它 ===
                        is_build = build_cmd and current_cmd and build_cmd in current_cmd
                        
                        # ===== 系统根据执行结果自动生成产出文件 =====
                        project_path = context.get("project_path")
                        if project_path:
                            if current_role == "developer" and is_build and parsed_result.get("success"):
                                # Developer 构建成功 → 自动创建 .build_success
                                build_success_file = os.path.join(project_path, ".build_success")
                                try:
                                    with open(build_success_file, 'w') as f:
                                        f.write("DONE")
                                    sys.stderr.write(f"📌 系统自动创建构建产物: {build_success_file}\n")
                                except Exception as e:
                                    sys.stderr.write(f"⚠️ 创建构建产物失败: {e}\n")

                                # 清除重新构建标志
                            if context.get("require_rebuild"):
                                context["require_rebuild"] = False
                                sys.stderr.write("📌 已清除 require_rebuild 标志\n")
                            
                            elif current_role == "tester" and not is_build:
                                # Tester 测试完成 → 自动创建 test_report.json
                                report_file = os.path.join(project_path, "test_report.json")
                                if parsed_result.get("success"):
                                    report = {"status": "pass"}
                                else:
                                    report = {"status": "fail", "error": parsed_result.get("stderr", "")[:500]}
                                try:
                                    with open(report_file, 'w') as f:
                                        json.dump(report, f, indent=2)
                                    sys.stderr.write(f"📌 系统自动创建测试报告: {report_file}\n")
                                except Exception as e:
                                    sys.stderr.write(f"⚠️ 创建测试报告失败: {e}\n")
                            
                            elif current_role == "fixer" and not is_build:
                                # Fixer 修复完成 → 自动创建 fix_result.json
                                fix_file = os.path.join(project_path, "fix_result.json")
                                if parsed_result.get("success"):
                                    fix_data = {"success": True}
                                else:
                                    fix_data = {"success": False, "error": parsed_result.get("stderr", "")[:500]}
                                try:
                                    with open(fix_file, 'w') as f:
                                        json.dump(fix_data, f, indent=2)
                                    sys.stderr.write(f"📌 系统自动创建修复结果: {fix_file}\n")
                                except Exception as e:
                                    sys.stderr.write(f"⚠️ 创建修复结果失败: {e}\n")
                        # ===================================================
                        
                        if is_build:
                            context["last_build_result"] = parsed_result
                            # 更新构建重试次数
                            if parsed_result.get("success") is False:
                                context["build_retry_count"] = context.get("build_retry_count", 0) + 1
                            else:
                                context["build_retry_count"] = 0
                            sys.stderr.write(f"📌 已保存构建结果，重试次数: {context.get('build_retry_count', 0)}\n")
                        else:
                            context["last_diagnostic_result"] = parsed_result
                            sys.stderr.write("📌 已保存诊断结果到 context['last_diagnostic_result']\n")
                        # 如果构建失败，切换到自我修复状态
                        if is_build and parsed_result.get("success") is False:
                            # ======= 【新增】记忆库检索与自动修复开始 =======
                            language = context.get("language", "Rust")
                            stderr = parsed_result.get("stderr", "")
                            
                            # 1. 检索记忆库
                            memories = retrieve_memory(
                                task_type=f"{language.lower()}_build",
                                error_message=stderr,
                                environment_tags=["windows", language.lower()]
                            )
                            
                            if memories:
                                best_memory = memories[0]
                                fix_cmd = best_memory.get("fix_command")
                                if fix_cmd:
                                    sys.stderr.write(f"🧠 [记忆库] 发现历史修复方案: {best_memory.get('fix_description', '')}\n")
                                    sys.stderr.write(f"🔧 自动应用修复: {fix_cmd}\n")
                                    # 直接执行修复命令（复用 tool_func，即 execute_shell_command）
                                    fix_args = {
                                        "command": fix_cmd, 
                                        "cwd": context.get("project_path", "D:/test_rust_project")
                                    }
                                    try:
                                        fix_res = tool_func(**fix_args)
                                        fix_parsed = json.loads(fix_res)
                                        if fix_parsed.get("success"):
                                            sys.stderr.write("✅ 记忆库修复成功！重置构建计数器。\n")
                                            context["build_retry_count"] = 0
                                            # 让 Agent 在下一轮直接重新构建
                                        else:
                                            sys.stderr.write(f"⚠️ 记忆库修复命令执行失败: {fix_parsed.get('stderr', '')[:200]}\n")
                                    except Exception as e:
                                        sys.stderr.write(f"❌ 执行记忆库修复命令异常: {e}\n")
                            # ======= 【新增】记忆库检索与自动修复结束 =======

                            sys.stderr.write("⚠️ 构建执行失败，切换到自我修复状态\n")
                            context["last_error"] = parsed_result.get("stderr", "")[:500]
                            context["failed_tool"] = tool_name
                            state_machine.update_task_state(
                                task_id,
                                AgentState.SELF_HEALING,
                                context
                            )
                    except Exception as e:
                        sys.stderr.write(f"⚠️ 解析 execute_shell_command 结果失败: {e}\n")
                        context["last_diagnostic_result"] = {"success": False, "stderr": result[:200]}
                # -----------------------------------------------------------------

                if tool_name not in completed_steps:
                    completed_steps.append(tool_name)
                    context["completed_steps"] = completed_steps

                if tool_name == "analyze_project_structure":
                    context["fingerprint"] = result
                    context["fingerprint_summary"] = result[:300] if len(result) > 300 else result
                    if "project_path" in clean_args:
                        context["project_path"] = clean_args["project_path"]
                    #如果返回了 error 字段就记录到上下文中
                    try:
                        data = json.loads(result)
                        if "error" in data:
                            context["analysis_error"] = data["error"]
                            sys.stderr.write(f"⚠️ 分析失败：{data['error']}\n")
                    except:
                        pass
                    # 保存语言信息
                    try:
                        fingerprint_data = json.loads(result)
                        if "language" in fingerprint_data:
                            context["language"] = fingerprint_data["language"]
                            sys.stderr.write(f"📌 已保存语言: {context['language']}\n")
                    except:
                        pass
                    sys.stderr.write("📌 已保存指纹结果到上下文\n")

                # ===== 在 execute_shell_command 之前，确保 build_command 已保存 =====
                if tool_name == "infer_build_steps" and "result" in locals():
                    try:
                        steps = json.loads(result)
                        if "error" not in steps:
                            build_steps = steps.get("build_steps", [])
                            if build_steps:
                                context["build_command"] = build_steps[0]
                                sys.stderr.write(f"📌 已保存构建命令: {context['build_command']}\n")
                            else:
                                sys.stderr.write("⚠️ 推理结果中没有 build_steps，无法设置构建命令\n")
                    except:
                        pass

                # 更新状态（如果执行成功，或者 execute_shell_command 失败但已提前更新）
                if not (tool_name == "execute_shell_command" and context.get("last_build_result", {}).get("success") is False):
                    state_machine.update_task_state(task_id, current_state, context)
                sys.stderr.write(f"📌 进度更新: 已完成步骤 {', '.join(completed_steps)}\n")

            except Exception as e:
                sys.stderr.write(f"❌ 工具执行失败: {e}\n")
                context["last_error"] = str(e)
                context["failed_tool"] = tool_name
                state_machine.update_task_state(
                    task_id,
                    AgentState.SELF_HEALING,
                    {**context, "error": str(e), "failed_tool": tool_name}
                )
                continue

            # ========== 14. 检查是否陷入重复调用 ==========
            if last_tool == tool_name:
                # 如果当前工具是 execute_shell_command，且命令是诊断命令（非构建命令），则计入重复次数
                if tool_name == "execute_shell_command":
                    current_cmd = clean_args.get("command")
                    build_cmd = context.get("build_command")
                    # 如果当前命令等于构建命令，则不视为重复（允许重试）
                    if build_cmd and current_cmd and current_cmd.strip() == build_cmd.strip():
                        repeat_count = 0  # 构建命令不触发重复检测
                    else:
                        # 诊断命令：如果已经成功执行过一次，则计数置为0（引导转向构建）
                        last_diag = context.get("last_diagnostic_result", {})
                        if last_diag.get("success") is True and current_cmd == last_diag.get("command"):
                            # 诊断已成功，禁止重复，强制退出循环（但这里我们让计数器+1，尽早触发强制切换）
                            repeat_count += 1
                        else:
                            repeat_count += 1
                else:
                    repeat_count += 1
            else:
                repeat_count = 0
                last_tool = tool_name

            if repeat_count >= 2:  # 诊断命令连续重复2次即触发中断（原为3）
                sys.stderr.write(f"⚠️ 连续 2 次调用同一诊断工具 ({tool_name})，可能存在循环，尝试中断\n")
                if tool_name not in completed_steps:
                    completed_steps.append(tool_name)
                    context["completed_steps"] = completed_steps

                if current_state == AgentState.SELF_HEALING:
                    target_state = AgentState.WEB_TESTING
                elif current_state == AgentState.CODE_CONSTRUCTION:
                    target_state = AgentState.WEB_TESTING
                elif current_state == AgentState.WEB_TESTING:
                    target_state = AgentState.SELF_HEALING
                else:
                    target_state = AgentState.WEB_TESTING

                state_machine.update_task_state(
                    task_id,
                    target_state,
                    {**context, "force_proceed": True, "repeat_tool": tool_name}
                )
                sys.stderr.write(f"📌 强制推进状态机: {current_state} → {target_state}\n")
                repeat_count = 0
                continue

        # 循环结束
        if iteration >= max_iterations:
            sys.stderr.write(f"⚠️ 达到最大迭代次数 ({max_iterations})，任务失败。\n")
            # 将失败原因写入上下文，方便后续输出
            failure_reason = f"任务因达到最大迭代次数 ({max_iterations}) 而终止，构建仍未成功。"
            # 附加最后一次构建的错误摘要
            last_build = context.get("last_build_result", {})
            if last_build.get("success") is False:
                failure_reason += f"\n最后一次构建错误摘要：{last_build.get('stderr', '')[:500]}"
            context["failure_reason"] = failure_reason
            state_machine.update_task_state(
                task_id,
                AgentState.HUMAN_INTERRUPT,
                {**context, "reason": failure_reason}
            )
        # ===== 生成任务报告 =====
        report_lines = []
        report_lines.append("\n" + "=" * 50)
        report_lines.append("📋 MAS-Engine 任务报告")
        report_lines.append("=" * 50)
        
        # 1. 任务 ID
        report_lines.append(f"任务 ID        : {task_id}")
        
        # 2. 项目路径
        project_path = context.get('project_path', '未指定')
        report_lines.append(f"项目路径      : {project_path}")
        
        # 3. 分析状态（新增）
        analysis_error = context.get('analysis_error', '')
        if analysis_error:
            report_lines.append(f"项目分析      : ❌ 失败 - {analysis_error}")
        else:
            report_lines.append(f"项目分析      : ✅ 成功")
        
        # 4. 最终状态
        final_state = context.get('current_state', 'unknown')
        last_build = context.get('last_build_result', {})

        # 优先根据构建结果判断状态，再根据状态机判断
        if last_build.get('success') is True:
            status = "✅ 成功"
        elif final_state == AgentState.HUMAN_INTERRUPT:
            status = "⚠️ 失败/中断"
        elif final_state == AgentState.DELIVERY_COMPLETED:
            status = "✅ 成功"
        else:
            status = "⏹️ 未完成/未知"
        report_lines.append(f"最终状态      : {status}")
        
        # 5. 构建命令
        build_cmd = context.get('build_command', '未推理')
        report_lines.append(f"构建命令      : {build_cmd}")
        
        # 6. 构建结果（如果项目不存在或分析失败，这里会是空值）
        last_build = context.get('last_build_result', {})
        if last_build:
            if last_build.get('success') is True:
                report_lines.append(f"构建结果      : ✅ 成功")
                stdout_preview = last_build.get('stdout', '').strip()
                if stdout_preview:
                    report_lines.append(f"构建输出摘要  : {stdout_preview[:200]}")
            elif last_build.get('success') is False:
                report_lines.append(f"构建结果      : ❌ 失败 (退出码 {last_build.get('exit_code', '?')})")
                stderr_preview = last_build.get('stderr', '').strip()
                if stderr_preview:
                    report_lines.append(f"错误摘要      : {stderr_preview[:200]}")
            else:
                report_lines.append(f"构建结果      : 未执行构建")
        else:
            # 如果没有执行构建，检查是否因为分析失败导致的
            if analysis_error:
                report_lines.append(f"构建结果      : ⚠️ 因项目分析失败，未执行构建")
            else:
                report_lines.append(f"构建结果      : 未执行构建")
        
        # 7. 重试次数
        retry_count = context.get('build_retry_count', 0)
        report_lines.append(f"构建重试次数  : {retry_count}")
        
        # 8. 失败原因（如果有）
        failure_reason = context.get('failure_reason', '')
        if failure_reason:
            report_lines.append(f"失败原因      : {failure_reason}")
        
        report_lines.append("=" * 50)
        sys.stderr.write("\n".join(report_lines) + "\n")
        sys.exit(0)

    # ===== MCP 模式 =====
    if args.http:
        import uvicorn
        app = mcp.sse_app()
        if hasattr(app, "routes"):
            for route in app.routes:
                sys.stderr.write(f"路由: {route.path}\n")
        uvicorn.run(app, host="0.0.0.0", port=8000)
    else:
        logger.info("启动 MCP 服务在 stdio 模式")
        mcp.run()