import sys
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from memory import retrieve_memory
from web_server import sync_broadcast

sys.stdout = sys.stderr

import json
import os
import time

# from playwright.sync_api import sync_playwright
from dotenv import load_dotenv
from fastmcp import FastMCP
from state_machine import AgentState, TaskStateMachine

from adapters import detect_adapter, get_adapter
from config.settings import DB_CONFIG
from tools.analysis_tools import (
    analyze_project_structure_impl,
    get_code_slice_impl,
    infer_build_steps_impl,
)
from tools.edit_tools import edit_file as edit_file_impl
from tools.exec_tools import (
    execute_shell_command_impl,
)
from utils.logger import setup_logger
from utils.telemetry import TelemetryCollector

# ===== 日志与基础路径 =====
BASE_DIR = Path(__file__).parent.parent
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)
logger = setup_logger()

# ===== MCP 实例与 7 阶状态机 =====
mcp = FastMCP("Company Dev Toolkit")
state_machine = TaskStateMachine(DB_CONFIG)

# ===== 加载 .env =====
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)
    sys.stderr.write(f"[Config] 已加载 .env 文件: {env_path}\n")
else:
    sys.stderr.write("[Config] 警告: .env 文件不存在，将使用系统环境变量\n")

# ============================================================
# 核心 MCP 工具原语注册 (只保留真正执行的 5 大金刚)
# ============================================================


@mcp.tool()
def analyze_project_structure(project_path: str) -> str:
    """分析项目结构与特征指纹"""
    return analyze_project_structure_impl(project_path)


@mcp.tool()
def infer_build_steps(fingerprint_json: str) -> str:
    """根据指纹推理构建与测试指令"""
    return infer_build_steps_impl(fingerprint_json)


@mcp.tool()
def execute_shell_command(command: str, cwd: str = None) -> str:
    """执行底层 Shell 命令并返回结果（物理构建与测试执行器）"""
    return execute_shell_command_impl(command, cwd)


@mcp.tool()
def get_code_slice(
    file_path: str, target_line: int = None, context_window: int = 15, symbol_name: str = None
) -> str:
    """根据行号精准切片代码，提取局部函数与依赖上下文（Token 降噪 90%+）"""
    return get_code_slice_impl(file_path, target_line, context_window, symbol_name)


@mcp.tool()
def edit_file(file_path: str, old_string: str, new_string: str) -> str:
    """在文件中精准查找并替换代码内容"""
    return edit_file_impl(file_path, old_string, new_string)


# ===== 共享工作区文件读写工具 =====
def read_shared_file(project_path, filename):
    """从工作区读取约定文件"""
    path = os.path.join(project_path, filename)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.loads(f.read())


def write_shared_file(project_path, filename, data):
    """写入共享工作区文件"""
    path = os.path.join(project_path, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


# ============================================================
# 启动入口
# ============================================================
def main():
    import argparse
    import json
    import re

    from llm_provider import get_llm_provider

    parser = argparse.ArgumentParser(description="MAS-Engine MCP Server")
    parser.add_argument("--http", action="store_true", help="启动 HTTP 模式（SSE）")
    parser.add_argument("--standalone", action="store_true", help="独立运行模式（不依赖 Cline）")
    # 快捷启动
    parser.add_argument(
        "--project", type=str, default=None, help="独立模式下指定项目路径，自动完成分析、推理、构建"
    )
    parser.add_argument("--create", type=str, default=None, help="从 0 到 1 创建新项目的目标目录")
    parser.add_argument(
        "--lang", type=str, default=None, help="显式指定语言适配器 (如 python, php)，留空则自动探测"
    )
    parser.add_argument(
        "--ui", action="store_true", help="启动 DSH 风格的本地可视化 Web 控制台 (自动打开浏览器)"
    )
    # ==========
    parser.add_argument("--task", type=str, default="", help="独立模式下要执行的任务描述")
    args = parser.parse_args()

    # 如果指定了 --ui，直接拉起 Web 可视化控制台
    if args.ui:
        from web_server import launch_web_ui

        launch_web_ui()
        sys.exit(0)

    # 只要使用了 --project 或 --create，自动开启 standalone 独立模式
    if args.project or args.create:
        args.standalone = True

    # ===== 强制 stdout 重定向（仅纯 MCP 协议 stdio 模式） =====
    if not args.standalone and not args.http:
        sys.stdout = sys.stderr
        sys.stderr.write("[MCP] stdout redirected to stderr for MCP protocol\n")

    # ===== 独立运行模式 / 快捷模式 =====
    if args.standalone:
        logger.info("===== MAS-Engine 独立运行模式 =====")

        # 如果使用了 --project，仅在用户没有输入 task 时才自动生成默认描述
        if args.project:
            args.project = os.path.abspath(args.project)
            args.standalone = True
            if not args.task:
                args.task = f"分析 {args.project} 项目结构，推理构建步骤，然后执行构建"
            sys.stderr.write(f"🔧 确认任务描述 -> {args.task}\n")

        if not args.task:
            sys.stderr.write("❌ 错误: --standalone 模式需要指定 --task 参数\n")
            sys.stderr.write("示例: python server.py --standalone --task '创建一个用户登录页面'\n")
            sys.exit(1)

        task_description = args.task
        task_id = f"standalone_{int(time.time())}"
        telemetry_collector = TelemetryCollector()
        telemetry_steps = []
        step_idx_counter = 0

        # ===== 模式分流：创建新项目 (--create) vs 诊断修复现有项目 (--project) =====
        is_create_mode = bool(args.create)
        raw_path = (
            str(args.create if is_create_mode else (args.project or "."))
            .strip()
            .strip('"')
            .strip("'")
        )
        abs_path = os.path.abspath(raw_path)

        # 1. 自动识别输入的是单文件还是文件夹
        specific_file = None
        if os.path.isfile(abs_path):
            specific_file = os.path.basename(abs_path)  # 锁定单文件：如 通用网站爬虫简易版.py
            target_dir = os.path.dirname(abs_path)  # 所在目录：D:\Python
        else:
            target_dir = abs_path

        # 2. 只有从 0 创建新项目时才新建文件夹；已有项目只做存在性检查
        if is_create_mode:
            os.makedirs(target_dir, exist_ok=True)
        else:
            if not os.path.exists(abs_path):
                sys.stderr.write(f"❌ 错误：目标路径不存在 -> {abs_path}\n")
                sys.exit(1)

        if is_create_mode:
            task_description = args.task or "根据需求创建全新的项目"
            initial_state = (
                AgentState.REQUIREMENT_ANALYSIS
            )  # 👈 从 0 创建：第一步必须是 Architect 架构分析
            initial_role = "architect"
            sys.stderr.write(f"🏗️ [创建模式] 正在启动从 0 到 1 项目构建: {target_dir}\n")
        else:
            task_description = args.task or f"分析并修复 {target_dir} 项目"
            initial_state = AgentState.WEB_TESTING  # 👈 诊断模式：直接进入测试捕获 Bug
            initial_role = "tester"
            sys.stderr.write(f"🔧 [诊断模式] 正在对现有项目进行测试与自愈: {target_dir}\n")

        # 动态装配语言适配器 (支持 --lang 显式指定，或根据目标目录自动探测)
        adapter = (
            get_adapter(args.lang) if getattr(args, "lang", None) else detect_adapter(target_dir)
        )
        sys.stderr.write(f"🔌 [Adapter] 已成功装配专职语言适配器: [{adapter.name.upper()}]\n")
        task_id = f"standalone_{int(time.time())}"
        sys.stderr.write(f"📋 任务描述: {task_description}\n")
        sys.stderr.write(f"🆔 任务 ID: {task_id}\n")

        # 初始化状态机
        state_machine.update_task_state(
            task_id,
            initial_state,
            {
                "description": task_description,
                "current_role": initial_role,
                "completed_steps": [],
                "project_path": target_dir,
                "specific_file": specific_file,
                "is_create_mode": is_create_mode,
                "language": adapter.name,
            },
        )
        sys.stderr.write(f"📌 任务已创建: 初始状态={initial_state}, 角色={initial_role}\n")

        # 初始广播使用 initial_state
        sync_broadcast("STATE_CHANGE", {"state": initial_state, "role": initial_role})

        # ===== Agent 循环 =====
        max_iterations = 5
        iteration = 0
        last_tool = None
        repeat_count = 0

        def load_agents_instructions(project_path: str) -> str:
            """如果在项目目录下存在 AGENTS.md，则自动加载项目个性化规范，否则返回空"""
            if not project_path:
                return ""
            agents_file = os.path.join(project_path, "AGENTS.md")
            if os.path.exists(agents_file):
                try:
                    with open(agents_file, "r", encoding="utf-8") as f:
                        content = f.read().strip()
                        if content:
                            sys.stderr.write(
                                "📄 [Pi-Core] 已成功挂载项目专属 AGENTS.md 声明式规则\n"
                            )
                            return f"\n【项目定制规范 (AGENTS.md)】:\n{content}\n"
                except Exception:
                    pass
            return ""

        # 工具映射表 (仅保留 5 个核心工具)
        tool_map = {
            "analyze_project_structure": analyze_project_structure,
            "infer_build_steps": infer_build_steps,
            "execute_shell_command": execute_shell_command,
            "get_code_slice": get_code_slice,
            "edit_file": edit_file,
        }

        # 传递给大模型的极简工具清单 (极大降低 Prompt 开销)
        all_tools = [
            {"name": "analyze_project_structure", "description": "分析项目结构指纹与源文件列表"},
            {"name": "infer_build_steps", "description": "根据项目结构推理构建和测试指令"},
            {"name": "execute_shell_command", "description": "执行物理命令 (如构建、测试、编译等)"},
            {"name": "get_code_slice", "description": "提取局部目标函数块及依赖，降低 Token 消耗"},
            {"name": "edit_file", "description": "在目标文件中查找并替换修复代码"},
        ]

        # 核心参数白名单过滤器
        tool_params = {
            "analyze_project_structure": ["project_path"],
            "infer_build_steps": ["fingerprint_json"],
            "execute_shell_command": ["command", "cwd", "workdir"],
            "get_code_slice": ["file_path", "target_line", "context_window", "symbol_name"],
            "edit_file": ["file_path", "old_string", "new_string"],
        }

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
            sync_broadcast("STATE_CHANGE", {"state": current_state, "role": current_role})

            # ===== 状态无进展检测（熔断） =====
            last_fix_state = context.get("last_fix_state")
            if (
                last_fix_state == AgentState.FIX_APPLY
                and current_state == AgentState.CODE_CONSTRUCTION
            ):
                loop_count = context.get("fix_apply_loop_count", 0) + 1
                context["fix_apply_loop_count"] = loop_count
                sys.stderr.write(f"⚠️ 检测到修复-构建循环: {loop_count}/3\n")
                if loop_count >= 3:
                    sys.stderr.write("❌ 修复-构建循环超过3次，判定为死循环，强制终止\n")
                    state_machine.update_task_state(
                        task_id,
                        AgentState.HUMAN_INTERRUPT,
                        {**context, "failure_reason": "修复-构建循环超过3次，可能是无解问题"},
                    )
                    break
            else:
                # 如果状态改变，重置计数器
                if current_state in [AgentState.FIX_APPLY, AgentState.CODE_CONSTRUCTION]:
                    context["last_fix_state"] = current_state
                else:
                    context["last_fix_state"] = None
                    context["fix_apply_loop_count"] = 0

            # 2. 提取项目路径、挂载 AGENTS.md 并获取当前适配器
            project_path = context.get("project_path")
            custom_rules = load_agents_instructions(project_path)
            adapter = get_adapter(context.get("language", "python"))

            # ============================================================
            # 【基于 Pluggable Adapter 的确定性状态机微内核】
            # ============================================================

            # ------------------------------------------------------------
            # 阶段 0: REQUIREMENT_ANALYSIS (Architect 规划文件树)
            # ------------------------------------------------------------
            if current_state == AgentState.REQUIREMENT_ANALYSIS:
                current_role = "architect"
                context["current_role"] = current_role
                sys.stderr.write("🧠 [Architect] 正在规划项目架构与文件树...\n")

                arch_system = "你是一个架构师 Architect。请根据需求分析并规划项目文件列表，只输出严格的 JSON 对象。"
                arch_prompt = f"""需求: {context.get("description", "")}
目标目录: {project_path}
语言环境: {adapter.name.upper()}
{custom_rules}
请规划需要创建的文件相对路径。严格格式如下：
{{"files": ["{adapter.default_entry_file}", "README.md"], "description": "项目概要"}}"""

                arch_resp = llm_provider.generate_response(
                    system_prompt=arch_system,
                    user_prompt=arch_prompt,
                    temperature=0.1,
                    current_state=AgentState.REQUIREMENT_ANALYSIS,
                )

                planned_files = []
                json_match = re.search(r"\{.*\}", arch_resp, re.DOTALL)
                if json_match:
                    try:
                        arch_data = json.loads(json_match.group(0), strict=False)
                        planned_files = arch_data.get("files", [])
                    except Exception:
                        pass

                if not planned_files:
                    planned_files = [adapter.default_entry_file]

                context["planned_files"] = planned_files
                sys.stderr.write(f"📋 Architect 规划完成，待生成文件清单: {planned_files}\n")
                sys.stderr.write(
                    "🔄 状态机推进: REQUIREMENT_ANALYSIS ──> CODE_CONSTRUCTION (激活 mas-developer)\n"
                )
                state_machine.update_task_state(task_id, AgentState.CODE_CONSTRUCTION, context)
                continue

            # ------------------------------------------------------------
            # 阶段 1: CODE_CONSTRUCTION (Developer 逐文件生成)
            # ------------------------------------------------------------
            elif current_state == AgentState.CODE_CONSTRUCTION and context.get("is_create_mode"):
                current_role = "developer"
                context["current_role"] = current_role
                planned_files = context.get("planned_files", [adapter.default_entry_file])
                sys.stderr.write(f"💻 [Developer] 正在逐个构建 {len(planned_files)} 个源文件...\n")

                for rel_file in planned_files:
                    file_full_path = os.path.join(project_path, rel_file)
                    os.makedirs(os.path.dirname(file_full_path), exist_ok=True)

                    dev_system = f"你是一个精通 {adapter.name.upper()} 的高级开发工程师 Developer。请直接输出目标文件的完整源码，放在 ``` 代码块中。"
                    dev_prompt = f"""需求: {context.get("description", "")}
正在编写文件: {rel_file}
{custom_rules}
请给出该文件的完整、高质量、可运行代码。"""

                    dev_resp = llm_provider.generate_response(
                        system_prompt=dev_system,
                        user_prompt=dev_prompt,
                        temperature=0.1,
                        current_state=AgentState.CODE_CONSTRUCTION,
                    )

                    # 由适配器统一处理代码清洗与格式规范
                    file_code = adapter.clean_format_code(dev_resp)

                    with open(file_full_path, "w", encoding="utf-8") as f:
                        f.write(file_code)
                    sys.stderr.write(f"  ✅ [Developer] 已成功生成并写入: {rel_file}\n")

                sys.stderr.write("🔄 状态机推进: CODE_CONSTRUCTION ──> WEB_TESTING (静态验证)\n")
                state_machine.update_task_state(task_id, AgentState.WEB_TESTING, context)
                continue

            # ------------------------------------------------------------
            # 阶段 2: WEB_TESTING (适配器驱动的测试执行与语法门禁)
            # ------------------------------------------------------------
            elif current_state == AgentState.WEB_TESTING:
                current_role = "tester"
                context["current_role"] = current_role
                sys.stderr.write("🧪 [Tester] 正在执行验证门禁...\n")

                # 如果是从 0 创建模式且没有测试用例，执行全量生成文件的静态语法门禁
                if context.get("is_create_mode") and not context.get("test_files"):
                    syntax_all_pass = True
                    for rel_file in context.get("planned_files", []):
                        f_path = os.path.join(project_path, rel_file)
                        if os.path.exists(f_path):
                            with open(f_path, "r", encoding="utf-8") as f:
                                content = f.read()
                            ok, msg = adapter.validate_syntax(rel_file, content)
                            if not ok:
                                sys.stderr.write(f"❌ 语法校验不通过 ({rel_file}): {msg}\n")
                                syntax_all_pass = False
                                break

                    if syntax_all_pass:
                        sys.stderr.write("✅ [Tester] 全量生成文件经适配器静态门禁验证通过！\n")
                        state_machine.update_task_state(
                            task_id, AgentState.DELIVERY_COMPLETED, context
                        )
                        continue

                # 真实物理测试执行（命令完全由适配器提供，零硬编码）
                test_cmd = adapter.get_test_command(Path(project_path))
                test_res_raw = tool_map["execute_shell_command"](command=test_cmd, cwd=project_path)
                test_res = json.loads(test_res_raw)

                if test_res.get("success") and test_res.get("exit_code") == 0:
                    sys.stderr.write("✅ [Tester] 物理测试全量验证通过！\n")
                    state_machine.update_task_state(task_id, AgentState.DELIVERY_COMPLETED, context)
                    continue
                else:
                    err_msg = test_res.get("stdout", "") + test_res.get("stderr", "")
                    sys.stderr.write(f"❌ [Tester] 捕获到测试失败:\n{err_msg[-300:]}\n")
                    report_data = {
                        "status": "fail",
                        "error_message": err_msg[-500:],
                        "exit_code": test_res.get("exit_code"),
                    }
                    write_shared_file(project_path, "test_report.json", report_data)
                    context["test_report"] = report_data
                    state_machine.update_task_state(task_id, AgentState.SELF_HEALING, context)
                    # 推送单测结果到 Web 界面
                    sync_broadcast(
                        "TEST_OUTPUT",
                        {
                            "output": (
                                test_res.get("stdout", "") + test_res.get("stderr", "")
                            ).strip(),
                            "passed": bool(
                                test_res.get("success") and test_res.get("exit_code") == 0
                            ),
                        },
                    )
                    continue

            # ------------------------------------------------------------
            # 阶段 3: SELF_HEALING (适配器驱动的自愈与语法门禁拦截)
            # ------------------------------------------------------------
            elif current_state == AgentState.SELF_HEALING:
                current_role = "fixer"
                context["current_role"] = current_role
                sys.stderr.write("🔧 [Fixer] 正在调用本地 mas-fixer 专职模型生成修复方案...\n")

                source_files = context.get("source_files", [])
                target_rel_file = context.get("specific_file") or (
                    source_files[0] if source_files else adapter.default_entry_file
                )
                source_file_path = os.path.join(project_path, target_rel_file)

                source_content = ""
                if os.path.exists(source_file_path):
                    with open(source_file_path, "r", encoding="utf-8") as f:
                        source_content = f.read()

                report_data = context.get("test_report", {})
                fixer_system = f"你是一个代码修复专家 Fixer。请修复 {adapter.name.upper()} 代码缺陷，直接输出替换代码放入 ``` 代码块中。"
                fixer_user_prompt = f"文件: {target_rel_file}\n报错信息:\n{report_data.get('error_message', '')[:400]}\n源码:\n{source_content}"

                fixer_resp = llm_provider.generate_response(
                    system_prompt=fixer_system,
                    user_prompt=fixer_user_prompt,
                    temperature=0.1,
                    current_state=AgentState.SELF_HEALING,
                )

                # 适配器自动代码后处理（修复 BPE 乱码、补齐标签）
                fixed_code = adapter.clean_format_code(fixer_resp)

                # 适配器静态语法门禁检验
                syntax_ok, syntax_err = adapter.validate_syntax(target_rel_file, fixed_code)
                if not syntax_ok:
                    sys.stderr.write(f"⚠️ AST 语法门禁拦截无效修复: {syntax_err}\n")
                    continue

                with open(source_file_path, "w", encoding="utf-8") as f:
                    f.write(fixed_code)
                sys.stderr.write(f"✅ 修复补丁已成功应用至: {source_file_path}\n")
                sys.stderr.write("🔄 状态机推进: SELF_HEALING ──> WEB_TESTING (回归测试)\n")
                state_machine.update_task_state(task_id, AgentState.WEB_TESTING, context)
                # 推送左右分栏代码 Diff 到 Web 界面
                sync_broadcast(
                    "DIFF_PREVIEW",
                    {"file": target_rel_file, "old_code": source_content, "new_code": fixed_code},
                )
                continue

            # ------------------------------------------------------------
            # 阶段 4: DELIVERY_COMPLETED (成功完成交付)
            # ------------------------------------------------------------
            elif current_state == AgentState.DELIVERY_COMPLETED:
                sys.stderr.write("🎉 [Auditor] 任务全量验证就绪，成功交付！\n")
                # 自动归档数据飞轮
                telemetry_collector.record_task_session(
                    task_id=task_id,
                    project_name=os.path.basename(project_path or "unnamed"),
                    language=adapter.name,
                    task_description=task_description,
                    is_create_mode=is_create_mode,
                    steps=telemetry_steps,
                    final_verdict="SUCCESS",
                )
                break

            # ===== 7. 调用 LLM =====
            system_prompt = f"你是一个 AI 开发助手，当前角色是 {current_role}，任务 ID 是 {task_id}。请根据当前上下文输出工具调用的 JSON。"
            try:
                raw_text = llm_provider.generate_response(
                    system_prompt=system_prompt,
                    user_prompt=f"请继续执行任务: {task_description}",
                    temperature=0.1,
                    current_state=current_state,
                )
            except RuntimeError as e:
                sys.stderr.write(f"❌ LLM 调用失败: {e}\n")
                break

            sys.stderr.write(f"📝 LLM 原始响应: {raw_text}\n")

            # 8. 解析 JSON (使用 raw_decode 提取首个合法 JSON 字典，无视尾部冗余)
            decision = None
            # 截断可能的自回归提示标记
            clean_text = raw_text.split("###Instruction")[0].split("```")[0].strip()

            start_idx = clean_text.find("{")
            if start_idx != -1:
                try:
                    decision, _ = json.JSONDecoder().raw_decode(clean_text[start_idx:])
                except json.JSONDecodeError:
                    pass

            # 兜底：如果 clean_text 没解出来，尝试全局非贪婪正则
            if not decision:
                json_match = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", raw_text, re.DOTALL)
                if json_match:
                    try:
                        decision = json.loads(json_match.group(0), strict=False)
                    except Exception:
                        pass

            if not decision:
                sys.stderr.write(f"⚠️ JSON 解析失败，原始文本: {raw_text[:200]}\n")
                context["last_error"] = "LLM 输出格式错误"
                state_machine.update_task_state(task_id, current_state, context)
                continue

            tool_name = decision.get("tool")
            arguments = decision.get("arguments", {})

            # 9. 如果 LLM 返回 "none"，任务完成
            if tool_name == "none":
                if current_role == "fixer":
                    sys.stderr.write("❌ Fixer 错误地返回了 none，但测试尚未通过，强制中断任务\n")
                    state_machine.update_task_state(
                        task_id,
                        AgentState.HUMAN_INTERRUPT,
                        {**context, "failure_reason": "Fixer 未生成修复指令"},
                    )
                    break
                else:
                    sys.stderr.write("⏩ Agent 提交完成信号，等待状态机硬跳转验证...\n")
                    continue

            # 10. 自动注入 task_id
            if "task_id" not in arguments:
                arguments["task_id"] = task_id
                sys.stderr.write("🔧 自动注入 task_id\n")

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
                "execute_shell_command": ["command", "cwd", "workdir"],
                "get_code_slice": ["file_path", "target_line", "context_window", "symbol_name"],
                "validate_code_syntax": ["file_path", "code_content"],
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

            sys.stderr.write(
                f"📌 清洗后参数: {json.dumps(clean_args, indent=2, ensure_ascii=False)}\n"
            )

            # ========== 13. 执行工具 ==========
            # ---- 特殊参数转换：infer_build_steps 的 fingerprint_json 应为字符串 ----
            if tool_name == "infer_build_steps" and "fingerprint_json" in clean_args:
                if isinstance(clean_args["fingerprint_json"], dict):
                    clean_args["fingerprint_json"] = json.dumps(
                        clean_args["fingerprint_json"], ensure_ascii=False
                    )
                    sys.stderr.write("🔧 已将 fingerprint_json 从 dict 转为 JSON 字符串\n")
            tool_func = tool_map.get(tool_name)
            if not tool_func:
                sys.stderr.write(f"⚠️ 未知工具: {tool_name}\n")
                continue

            try:
                result = tool_func(**clean_args)
                sys.stderr.write("✅ 工具执行成功\n")
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
                            if (
                                current_role == "developer"
                                and is_build
                                and parsed_result.get("success")
                            ):
                                # Developer 构建成功 → 自动创建 .build_success
                                build_success_file = os.path.join(project_path, ".build_success")
                                try:
                                    with open(build_success_file, "w") as f:
                                        f.write("DONE")
                                    sys.stderr.write(
                                        f"📌 系统自动创建构建产物: {build_success_file}\n"
                                    )
                                except Exception as e:
                                    sys.stderr.write(f"⚠️ 创建构建产物失败: {e}\n")

                                # 清除重新构建标志
                            if context.get("require_rebuild"):
                                context["require_rebuild"] = False
                                sys.stderr.write("📌 已清除 require_rebuild 标志\n")

                            elif current_role == "tester" and not is_build:
                                report_file = os.path.join(project_path, "test_report.json")
                                if parsed_result.get("success"):
                                    report = {"status": "pass"}
                                else:
                                    stderr = parsed_result.get("stderr", "")
                                    report = {
                                        "status": "fail",
                                        "error": stderr[:2000],
                                        "full_stderr": stderr,
                                        "full_stdout": parsed_result.get("stdout", "")[:2000],
                                    }

                                write_shared_file(project_path, "test_report.json", report)
                                try:
                                    with open(report_file, "w") as f:
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
                                    fix_data = {
                                        "success": False,
                                        "error": parsed_result.get("stderr", "")[:500],
                                    }
                                try:
                                    with open(fix_file, "w") as f:
                                        json.dump(fix_data, f, indent=2)
                                    sys.stderr.write(f"📌 系统自动创建修复结果: {fix_file}\n")
                                except Exception as e:
                                    sys.stderr.write(f"⚠️ 创建修复结果失败: {e}\n")
                        # ===================================================

                        if is_build:
                            context["last_build_result"] = parsed_result
                            # 更新构建重试次数
                            if parsed_result.get("success") is False:
                                context["build_retry_count"] = (
                                    context.get("build_retry_count", 0) + 1
                                )
                            else:
                                context["build_retry_count"] = 0
                            sys.stderr.write(
                                f"📌 已保存构建结果，重试次数: {context.get('build_retry_count', 0)}\n"
                            )
                        else:
                            context["last_diagnostic_result"] = parsed_result
                            sys.stderr.write(
                                "📌 已保存诊断结果到 context['last_diagnostic_result']\n"
                            )
                        # 如果构建失败，切换到自我修复状态
                        if is_build and parsed_result.get("success") is False:
                            # ======= 【新增】记忆库检索与自动修复开始 =======
                            language = context.get("language", "Rust")
                            stderr = parsed_result.get("stderr", "")

                            # 1. 检索记忆库
                            memories = retrieve_memory(
                                task_type=f"{language.lower()}_build",
                                error_message=stderr,
                                environment_tags=["windows", language.lower()],
                            )

                            if memories:
                                best_memory = memories[0]
                                fix_cmd = best_memory.get("fix_command")
                                if fix_cmd:
                                    sys.stderr.write(
                                        f"🧠 [记忆库] 发现历史修复方案: {best_memory.get('fix_description', '')}\n"
                                    )
                                    sys.stderr.write(f"🔧 自动应用修复: {fix_cmd}\n")
                                    # 直接执行修复命令（复用 tool_func，即 execute_shell_command）
                                    fix_args = {
                                        "command": fix_cmd,
                                        "cwd": context.get("project_path", "D:/test_rust_project"),
                                    }
                                    try:
                                        fix_res = tool_func(**fix_args)
                                        fix_parsed = json.loads(fix_res)
                                        if fix_parsed.get("success"):
                                            sys.stderr.write(
                                                "✅ 记忆库修复成功！重置构建计数器。\n"
                                            )
                                            context["build_retry_count"] = 0
                                            # 让 Agent 在下一轮直接重新构建
                                        else:
                                            sys.stderr.write(
                                                f"⚠️ 记忆库修复命令执行失败: {fix_parsed.get('stderr', '')[:200]}\n"
                                            )
                                    except Exception as e:
                                        sys.stderr.write(f"❌ 执行记忆库修复命令异常: {e}\n")
                            # ======= 【新增】记忆库检索与自动修复结束 =======

                            sys.stderr.write("⚠️ 构建执行失败，切换到自我修复状态\n")
                            context["last_error"] = parsed_result.get("stderr", "")[:500]
                            context["failed_tool"] = tool_name
                            state_machine.update_task_state(
                                task_id, AgentState.SELF_HEALING, context
                            )
                    except Exception as e:
                        sys.stderr.write(f"⚠️ 解析 execute_shell_command 结果失败: {e}\n")
                        context["last_diagnostic_result"] = {
                            "success": False,
                            "stderr": result[:200],
                        }
                # -----------------------------------------------------------------

                if tool_name not in completed_steps:
                    completed_steps.append(tool_name)
                    context["completed_steps"] = completed_steps

                if tool_name == "analyze_project_structure":
                    context["fingerprint"] = result
                    context["fingerprint_summary"] = result[:300] if len(result) > 300 else result
                    if "project_path" in clean_args:
                        context["project_path"] = clean_args["project_path"]
                    # 如果返回了 error 字段就记录到上下文中
                    try:
                        data = json.loads(result)
                        if "error" in data:
                            context["analysis_error"] = data["error"]
                            sys.stderr.write(f"⚠️ 分析失败：{data['error']}\n")
                    except Exception:
                        pass
                    # 保存语言信息
                    try:
                        fingerprint_data = json.loads(result)
                        if "language" in fingerprint_data:
                            context["language"] = fingerprint_data["language"]
                            sys.stderr.write(f"📌 已保存语言: {context['language']}\n")
                    except Exception:
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
                    except Exception:
                        pass

                # 更新状态（如果执行成功，或者 execute_shell_command 失败但已提前更新）
                if not (
                    tool_name == "execute_shell_command"
                    and context.get("last_build_result", {}).get("success") is False
                ):
                    state_machine.update_task_state(task_id, current_state, context)
                sys.stderr.write(f"📌 进度更新: 已完成步骤 {', '.join(completed_steps)}\n")

            except Exception as e:
                sys.stderr.write(f"❌ 工具执行失败: {e}\n")
                context["last_error"] = str(e)
                context["failed_tool"] = tool_name
                state_machine.update_task_state(
                    task_id,
                    AgentState.SELF_HEALING,
                    {**context, "error": str(e), "failed_tool": tool_name},
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
                        if last_diag.get("success") is True and current_cmd == last_diag.get(
                            "command"
                        ):
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
                sys.stderr.write(
                    f"⚠️ 连续 2 次调用同一诊断工具 ({tool_name})，可能存在循环，尝试中断\n"
                )
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
                    {**context, "force_proceed": True, "repeat_tool": tool_name},
                )
                sys.stderr.write(f"📌 强制推进状态机: {current_state} → {target_state}\n")
                repeat_count = 0
                continue

        # 循环结束
        if iteration >= max_iterations:
            sys.stderr.write(f"⚠️ 达到最大迭代次数 ({max_iterations})，任务失败。\n")

            # ===== 检查最后一次测试结果，决定是成功还是失败 =====
            last_test_report = context.get("test_report", {})
            if last_test_report.get("status") == "pass":
                sys.stderr.write("✅ 最后一次测试已通过，视为成功交付\n")
                state_machine.update_task_state(task_id, AgentState.DELIVERY_COMPLETED, context)
            else:
                sys.stderr.write("❌ 最后一次测试未通过，任务失败\n")
                failure_reason = f"达到最大迭代次数 ({max_iterations})，测试未通过"
                last_build = context.get("last_build_result", {})
                if last_build.get("success") is False:
                    failure_reason += (
                        f"\n最后一次构建错误摘要：{last_build.get('stderr', '')[:500]}"
                    )
                context["failure_reason"] = failure_reason
                state_machine.update_task_state(
                    task_id, AgentState.HUMAN_INTERRUPT, {**context, "reason": failure_reason}
                )

            # 将失败原因写入上下文，方便后续输出
            failure_reason = f"任务因达到最大迭代次数 ({max_iterations}) 而终止，构建仍未成功。"
            # 附加最后一次构建的错误摘要
            last_build = context.get("last_build_result", {})
            if last_build.get("success") is False:
                failure_reason += f"\n最后一次构建错误摘要：{last_build.get('stderr', '')[:500]}"
            context["failure_reason"] = failure_reason
            state_machine.update_task_state(
                task_id, AgentState.HUMAN_INTERRUPT, {**context, "reason": failure_reason}
            )
        # ===== 生成任务报告 =====
        report_lines = []
        report_lines.append("\n" + "=" * 50)
        report_lines.append("📋 MAS-Engine 任务报告")
        report_lines.append("=" * 50)

        # 1. 任务 ID
        report_lines.append(f"任务 ID        : {task_id}")

        # 2. 项目路径
        project_path = context.get("project_path", "未指定")
        report_lines.append(f"项目路径      : {project_path}")

        # 3. 分析状态（新增）
        analysis_error = context.get("analysis_error", "")
        if analysis_error:
            report_lines.append(f"项目分析      : ❌ 失败 - {analysis_error}")
        else:
            report_lines.append("项目分析      : ✅ 成功")

        # 4. 最终状态
        task_data = state_machine.get_task_state(task_id) or {}
        final_state = task_data.get("current_state", "unknown")
        last_build = context.get("last_build_result", {})

        # 优先根据构建结果判断状态，再根据状态机判断
        if last_build.get("success") is True:
            status = "✅ 成功"
        elif final_state == AgentState.HUMAN_INTERRUPT:
            status = "⚠️ 失败/中断"
        elif final_state == AgentState.DELIVERY_COMPLETED:
            status = "✅ 成功"
        else:
            status = "⏹️ 未完成/未知"
        report_lines.append(f"最终状态      : {status}")

        # 5. 构建命令
        build_cmd = context.get("build_command", "未推理")
        report_lines.append(f"构建命令      : {build_cmd}")

        # 6. 构建结果（如果项目不存在或分析失败，这里会是空值）
        last_build = context.get("last_build_result", {})
        if last_build:
            if last_build.get("success") is True:
                report_lines.append("构建结果      : ✅ 成功")
                stdout_preview = last_build.get("stdout", "").strip()
                if stdout_preview:
                    report_lines.append(f"构建输出摘要  : {stdout_preview[:200]}")
            elif last_build.get("success") is False:
                report_lines.append(
                    f"构建结果      : ❌ 失败 (退出码 {last_build.get('exit_code', '?')})"
                )
                stderr_preview = last_build.get("stderr", "").strip()
                if stderr_preview:
                    report_lines.append(f"错误摘要      : {stderr_preview[:200]}")
            else:
                report_lines.append("构建结果      : 未执行构建")
        else:
            # 如果没有执行构建，检查是否因为分析失败导致的
            if analysis_error:
                report_lines.append("构建结果      : ⚠️ 因项目分析失败，未执行构建")
            else:
                report_lines.append("构建结果      : 未执行构建")

        # 7. 重试次数
        retry_count = context.get("build_retry_count", 0)
        report_lines.append(f"构建重试次数  : {retry_count}")

        # 8. 失败原因（如果有）
        failure_reason = context.get("failure_reason", "")
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


if __name__ == "__main__":
    main()
