import sys
from pathlib import Path

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
            if any(kw in task_description for kw in ["创建", "新建", "生成"]):
                initial_state = AgentState.CODE_CONSTRUCTION
                initial_role = "developer"
            elif any(kw in task_description for kw in ["测试", "验证", "检查"]):
                initial_state = AgentState.WEB_TESTING
                initial_role = "tester"
            elif any(kw in task_description for kw in ["修复", "fix"]):
                initial_state = AgentState.SELF_HEALING
                initial_role = "fixer"
            else:
                initial_state = AgentState.REQUIREMENT_EXTRACTION
                initial_role = "analyst"

            state_machine.update_task_state(
                task_id,
                initial_state,
                {"description": task_description, "current_role": initial_role, "completed_steps": []}
            )
            sys.stderr.write(f"📌 任务已创建: 初始状态={initial_state}, 角色={initial_role}\n")
        else:
            sys.stderr.write(f"📌 任务已存在: 当前状态={task_data.get('current_state')}\n")

        # ===== Agent 循环 =====
        max_iterations = 20
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
        ]

        # ===== 初始化 LLM 提供者 =====
        try:
            llm_provider = get_llm_provider()
        except ValueError as e:
            sys.stderr.write(f"❌ LLM 配置错误: {e}\n")
            sys.exit(1)

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

            sys.stderr.write(f"📌 当前状态: {current_state}, 角色: {current_role}\n")
            sys.stderr.write(f"📌 已完成步骤: {', '.join(completed_steps) if completed_steps else '暂无'}\n")

            # ===== 新增：如果上一轮构建已成功，直接标记任务完成并退出 =====
            last_build = context.get("last_build_result", {})
            if last_build.get("success") is True:
                sys.stderr.write("✅ 上一轮构建已成功，任务完成。\n")
                state_machine.update_task_state(
                    task_id,
                    AgentState.DELIVERY_COMPLETED,
                    {**context, "completed": True, "message": "构建成功，任务完成"}
                )
                break

            if current_state == AgentState.DELIVERY_COMPLETED:
                sys.stderr.write("✅ 任务已标记为完成\n")
                break

            # ===== 新增：如果修复成功但 linker 问题仍然存在，则直接报告失败并退出 =====
            last_fix = context.get("last_fix_result", {})
            if last_fix.get("success") is True and last_build.get("success") is False:
                stderr_preview = last_build.get("stderr", "")
                if "link.exe not found" in stderr_preview:
                    sys.stderr.write("🚨 修复无效，link.exe 仍然缺失，任务失败。\n")
                    failure_reason = "MSVC 链接器 (link.exe) 缺失，且自动修复未能解决问题。请手动安装 Visual Studio Build Tools 或切换到 GNU 工具链。"
                    context["failure_reason"] = failure_reason
                    state_machine.update_task_state(task_id, AgentState.HUMAN_INTERRUPT, {**context, "reason": failure_reason})
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
                progress_hint = "\n📌 当前未完成任何步骤，请从 `analyze_project_structure` 开始。"

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
            action_guidance = ""
            last_build = context.get("last_build_result", {})
            last_fix = context.get("last_fix_result", {})
            if last_build:
                if last_build.get("success") is True:
                    action_guidance = "\n✅ 上一轮构建已成功。请返回 `{\"tool\": \"none\", \"message\": \"任务已完成\"}` 结束任务。"
                elif last_build.get("success") is False:
                    exit_code = last_build.get("exit_code")
                    stderr_preview = last_build.get("stderr", "")[:500]
                    action_guidance = f"\n❌ 上一轮构建失败（退出码 {exit_code}）。\n错误摘要：{stderr_preview}\n"
                    # 如果修复命令已成功执行，但仍然出现 linker 错误，说明修复无效
                    if last_fix.get("success") is True and "link.exe not found" in stderr_preview:
                        action_guidance += "\n🚨 修复命令已执行成功，但 linker `link.exe` 仍然未找到。这可能是环境变量未生效或需要手动安装 Visual Studio Build Tools。请报告任务失败并手动解决。"
                    elif last_fix.get("success") is True:
                        action_guidance += "\n✅ 修复命令已成功执行。请立即调用 `execute_shell_command` 执行构建命令，无需再获取规则。"
                    else:
                        # 根据重试次数给出不同建议
                        retry_count = context.get("build_retry_count", 0)
                        if retry_count < 3:
                            action_guidance += "\n🔧 建议：调用 `get_rules(language=<当前语言>)` 获取诊断规则，根据错误类型执行修复命令。"
                        elif retry_count < 5:
                            action_guidance += "\n🔧 建议：直接调用 `execute_shell_command` 执行已知的修复命令（例如安装 MSVC 工具链）。"
                        else:
                            action_guidance += "\n🚨 已经多次重试，建议调用 `execute_shell_command` 执行 `cargo clean` 后重试，或报告任务失败。"
            else:
                action_guidance = "\n📌 尚未执行构建命令。请开始分析并执行构建。"

            # 将摘要合并到系统提示中（放在最前面，让Agent第一时间看到）
            system_prompt = f"""你是一个 AI 开发助手，当前任务 ID 是 {task_id}。
当前状态: {current_state}
当前角色: {current_role}
{action_guidance}
{progress_hint}
{error_hint}

你可以调用以下工具来完成任务：
{json.dumps(all_tools, indent=2, ensure_ascii=False)}

用户任务: {task_description}

重要规则：
当 `execute_shell_command` 返回 `success=false` 时，你必须按以下步骤操作：

1. **获取诊断规则**：调用 `get_rules(language=<当前语言>)` 获取该语言的诊断规则（JSON格式）。
2. **匹配错误模式**：将 `stderr` 内容与规则中的 `error_pattern`（正则表达式）进行匹配。
3. **执行修复**：
   - 如果匹配成功，立即调用 `execute_shell_command` 执行对应的 `fix_command`。
   - 如果匹配失败，则执行该语言的 `diagnostic_command`（如 `cargo check --verbose`），收集更详细的错误日志，然后再次尝试匹配或报告无法修复。
4. **重新构建**：修复完成后，必须再次调用 `execute_shell_command` 执行构建命令（`cargo build`）。

- 所有工具调用都必须包含 task_id 参数（值 {task_id}）
- 你的回答必须只包含一个有效的 JSON 对象，不要有任何额外文字
- JSON 格式: {{"tool": "工具名", "arguments": {{"参数1": "值1", "task_id": "{task_id}"}}}}
- 如果任务已完成，返回 {{"tool": "none", "message": "任务已完成"}}
- 如果某个工具已经出现在“已完成步骤”列表中，则严禁再次调用该工具，必须执行下一步。
- **特别提醒**：在自我修复状态（self_healing）下，如果诊断命令（如 `rustup`）已经成功执行过一次，则不允许再次调用相同的诊断命令。**必须立即执行构建命令**（`cargo build`）。
- **如果 `get_rules` 已经出现在“已完成步骤”列表中，则严禁再次调用 `get_rules`**。你已经在之前轮次获取了诊断规则，直接使用这些规则即可，无需重复获取。
- **如果修复命令已经成功执行，请立即执行构建命令**，不要再重复获取规则或诊断。
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
                sys.stderr.write("⚠️ 未找到 JSON 块，无法解析，退出循环\n")
                break
            json_str = json_match.group(0)
            try:
                decision = json.loads(json_str)
            except json.JSONDecodeError:
                sys.stderr.write(f"⚠️ JSON 解析失败: {json_str}\n")
                break

            tool_name = decision.get("tool")
            arguments = decision.get("arguments", {})

            # 9. 如果 LLM 返回 "none"，任务完成
            if tool_name == "none":
                # 在 self_healing 状态下，如果构建尚未成功，不允许完成任务
                if current_state == AgentState.SELF_HEALING:
                    last_build = context.get("last_build_result", {})
                    if last_build.get("success") is not True:
                        sys.stderr.write("⚠️ 构建尚未成功，不允许返回 none，继续修复\n")
                        continue
                sys.stderr.write(f"✅ 任务完成: {decision.get('message', '')}\n")
                state_machine.update_task_state(
                    task_id,
                    AgentState.DELIVERY_COMPLETED,
                    {**context, "completed": True, "message": decision.get("message", "")}
                )
                break

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

            # 12. 特殊处理 infer_build_steps 缺少参数
            if tool_name == "infer_build_steps":
                fp_value = clean_args.get("fingerprint_json")
                if not fp_value or fp_value == "{}" or fp_value == '""' or fp_value == "":
                    fingerprint = context.get("fingerprint")
                    if fingerprint:
                        sys.stderr.write("🔧 自动注入 fingerprint_json（来自上一步分析结果）\n")
                        clean_args["fingerprint_json"] = fingerprint
                    else:
                        sys.stderr.write("⚠️ 没有可用的 fingerprint_json，请先调用 analyze_project_structure\n")
                        context["last_error"] = "需要先调用 analyze_project_structure 获取指纹"
                        context["failed_tool"] = tool_name
                        state_machine.update_task_state(
                            task_id,
                            AgentState.SELF_HEALING,
                            {**context, "error": context["last_error"], "failed_tool": tool_name}
                        )
                        continue

            # ========== 13. 执行工具 ==========
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
                        is_build = build_cmd and current_cmd and current_cmd.strip() == build_cmd.strip()
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

                if tool_name == "infer_build_steps":
                    try:
                        steps = json.loads(result)
                        build_steps = steps.get("build_steps", [])
                        if build_steps:
                            context["build_command"] = build_steps[0]
                            sys.stderr.write(f"📌 已保存构建命令: {context['build_command']}\n")
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