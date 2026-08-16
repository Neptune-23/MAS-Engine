import subprocess
import threading
import uuid
import time
import json
import re
from pathlib import Path
from datetime import datetime
#from playwright.sync_api import sync_playwright

# 这些变量将在 server.py 中注入
pipeline_tasks = None
task_lock = None
logger = None
state_machine = None
AgentState = None
send_message = None
LOG_DIR = None


def init_pipeline_tools(pipeline_tasks_dict, task_lock_obj, logger_obj,
                        state_machine_obj, agent_state_cls, send_msg_func, log_dir):
    """注入依赖"""
    global pipeline_tasks, task_lock, logger, state_machine, AgentState, send_message, LOG_DIR
    pipeline_tasks = pipeline_tasks_dict
    task_lock = task_lock_obj
    logger = logger_obj
    state_machine = state_machine_obj
    AgentState = agent_state_cls
    send_message = send_msg_func
    LOG_DIR = log_dir


def run_quality_pipeline_impl(project_path: str, fix: bool = False) -> str:
    """启动质量检查流水线的实现"""
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

    def worker():
        try:
            with task_lock:
                pipeline_tasks[task_id]["status"] = "running"
                pipeline_tasks[task_id]["progress"] = "开始执行流水线..."
                pipeline_tasks[task_id]["updated_at"] = datetime.now().isoformat()

            from tools.scan_tools import scan_code_batch_impl
            from tools.fix_tools import batch_fix_console_logs_impl

            path_obj = Path(project_path)
            all_issues = []
            total_files = 0
            offset = 0
            limit = 30

            while True:
                batch_result = scan_code_batch_impl(project_path, offset, limit)
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

            fix_log = []
            if fix and console_log_files:
                abs_files = [str(path_obj / f) for f in console_log_files]
                fix_result = batch_fix_console_logs_impl(abs_files, dry_run=False)
                fix_log.append(fix_result)

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
            else:
                fix_log.append("⏭️ 未开启自动修复或无需修复")

            verify_result = scan_code_batch_impl(project_path, 0, 30)

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

            reports_dir = path_obj / "reports"
            reports_dir.mkdir(exist_ok=True)
            report_file = reports_dir / f"{task_id}_report.txt"
            with open(report_file, "w", encoding="utf-8") as f:
                f.write(report)

            summary = f"""✅ 流水线执行完成！

📁 项目路径：{project_path}
📄 总文件数：{total_files}
🚨 发现问题文件数：{len(console_log_files)}
📊 修复操作：{'已执行' if fix else '未开启'}

📄 完整报告已保存至：{report_file}
💡 如需查看详情，请打开该文件。
"""

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


def run_backend_pipeline_impl(project_path: str, fix: bool = False) -> str:
    """启动后端质量检查流水线的实现"""
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

            from tools.scan_tools import scan_backend_batch_impl
            from tools.fix_tools import batch_fix_backend_issues_impl

            all_issues = []
            total_files = 0
            offset = 0
            limit = 30

            while True:
                batch_result = scan_backend_batch_impl(project_path, offset, limit)
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

            fix_log = []
            if fix and problem_files:
                abs_files = [str(Path(project_path) / f) for f in problem_files]
                fix_result = batch_fix_backend_issues_impl(abs_files, dry_run=False)
                fix_log.append(fix_result)

            verify_result = scan_backend_batch_impl(project_path, 0, 30)

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


def run_admin_pipeline_impl(project_path: str, fix: bool = False) -> str:
    """启动后台质量检查流水线的实现"""
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

            from tools.scan_tools import scan_admin_batch_impl

            all_issues = []
            total_files = 0
            offset = 0
            limit = 30

            while True:
                batch_result = scan_admin_batch_impl(project_path, offset, limit)
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

            fix_log = []
            if fix and problem_files:
                fix_log.append("⚠️ 后台自动修复功能较保守，请根据扫描报告手动处理问题。")

            verify_result = scan_admin_batch_impl(project_path, 0, 30)

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


def get_pipeline_status_impl(task_id: str) -> str:
    """查询流水线状态的实现"""
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


def run_web_audit_impl(task_id: str, url: str, wait_time: int = 3) -> str:
    """网页审计的实现"""
    task_data = state_machine.get_task_state(task_id)
    if task_data and task_data.get('current_state'):
        current_state = task_data['current_state']
        if current_state not in [AgentState.WEB_TESTING, AgentState.SELF_HEALING]:
            return f"⛔ [状态机拦截] 越权操作！当前处于【{current_state}】阶段。必须流转至 WEB_TESTING 阶段方可执行网页测试。"

    logger.info(f"[Playwright] 启动自动化审计，目标网页: {url}")

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
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(viewport={'width': 1280, 'height': 720})
            page = context.new_page()

            page.on("console", lambda msg: diagnostics["console_errors"].append(f"[{msg.type}] {msg.text}") if msg.type == "error" else None)
            page.on("response", lambda response: diagnostics["network_errors"].append(f"[{response.status}] {response.url}") if response.status >= 400 else None)

            page.goto(url, wait_until="networkidle", timeout=20000)
            time.sleep(wait_time)

            diagnostics["page_title"] = page.title()

            screenshot_name = f"audit_{task_id}_{int(time.time())}.png"
            screenshot_path = LOG_DIR / screenshot_name
            page.screenshot(path=str(screenshot_path))
            diagnostics["screenshot_path"] = str(screenshot_path)

            browser.close()

    except Exception as e:
        diagnostics["status"] = "failed"
        diagnostics["error_message"] = f"网页访问失败: {str(e)}"
        logger.error(f"[Playwright Error] {e}")

    summary = f"🌐 网页审计完成: {url}\n"
    summary += f"📄 页面标题: {diagnostics['page_title']}\n"
    summary += f"📸 页面截图已存至: {diagnostics['screenshot_path']}\n\n"

    if diagnostics["console_errors"] or diagnostics["network_errors"] or diagnostics["status"] == "failed":
        summary += "⚠️ 【检测到页面异常】\n"
        if diagnostics["console_errors"]:
            summary += "🔴 Console 报错:\n" + "\n".join(diagnostics["console_errors"][:5]) + "\n"
        if diagnostics["network_errors"]:
            summary += "📡 Network 异常:\n" + "\n".join(diagnostics["network_errors"][:5]) + "\n"
        if diagnostics.get("error_message"):
            summary += f"❌ 崩溃信息: {diagnostics['error_message']}\n"
        summary += "\n💡 提示: 请分析上述报错日志。"
    else:
        summary += "✅ 完美！页面加载正常，未检测到任何 Console 报错和 Network 异常。"

    return summary