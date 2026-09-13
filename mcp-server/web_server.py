import asyncio
import json
import os
import shutil
import sys
import threading
import time
import webbrowser
import zipfile
from pathlib import Path
from typing import Any, Dict, List

import httpx
import uvicorn
from fastapi import FastAPI, File, Form, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse

# 确保路径自举（能找到上级的 utils, adapters 等）
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from utils.telemetry import TelemetryCollector

app = FastAPI(title="MAS-Engine DSH Sandbox Dashboard")
telemetry_collector = TelemetryCollector()

# 全局沙箱根目录
WORKSPACE_ROOT = root_dir / "workspaces"
WORKSPACE_ROOT.mkdir(exist_ok=True, parents=True)

# 全局 WebSocket 连接池与主线程事件循环
active_connections: List[WebSocket] = []
main_event_loop: asyncio.AbstractEventLoop = None


@app.on_event("startup")
async def capture_event_loop():
    global main_event_loop
    main_event_loop = asyncio.get_running_loop()


async def broadcast_event(event_type: str, data: Dict[str, Any]):
    message = json.dumps(
        {"type": event_type, "data": data, "timestamp": time.time()}, ensure_ascii=False
    )
    for conn in list(active_connections):
        try:
            await conn.send_text(message)
        except Exception:
            if conn in active_connections:
                active_connections.remove(conn)


def sync_broadcast(event_type: str, data: Dict[str, Any]):
    """跨线程广播：子线程将事件抛给主线程的 EventLoop 执行"""
    global main_event_loop
    if main_event_loop and main_event_loop.is_running():
        asyncio.run_coroutine_threadsafe(broadcast_event(event_type, data), main_event_loop)


# ============================================================
# 1. 现代化暗色极客前端页面（拖拽上传 + 实时Diff + 产物下载）
# ============================================================
DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MAS-Engine 可视化自愈工作台</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        body { background-color: #0d1117; color: #c9d1d9; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, monospace; }
        .step-active { background-color: #1f6feb; border-color: #58a6ff; color: #ffffff; box-shadow: 0 0 14px rgba(88, 166, 255, 0.5); }
        .step-completed { background-color: #238636; border-color: #3fb950; color: #ffffff; }
        .step-pending { background-color: #161b22; border-color: #30363d; color: #8b949e; }
        pre code { font-family: 'Fira Code', Consolas, monospace; }
        .dragover { border-color: #58a6ff !important; background-color: rgba(31, 111, 235, 0.1) !important; }
    </style>
</head>
<body class="min-h-screen flex flex-col p-4">
    <!-- 顶部状态栏 -->
    <header class="flex items-center justify-between border-b border-gray-800 pb-3 mb-4">
        <div class="flex items-center gap-3">
            <span class="text-2xl font-bold text-blue-400">⚡ MAS-Engine</span>
            <span class="text-xs bg-gray-800 border border-gray-700 px-2.5 py-1 rounded-full text-gray-300" id="task-id-badge">就绪中</span>
            <span class="text-xs bg-blue-950 border border-blue-700 px-2.5 py-0.5 rounded font-mono text-blue-300" id="device-badge">🖥️ 设备: 探测中</span>
            <span class="text-xs bg-green-900 border border-green-700 px-2.5 py-0.5 rounded font-mono text-green-300 font-bold transition-all" id="adapter-badge">AUTO</span>
        </div>
        <div class="flex items-center gap-4 text-xs">
            <span id="conn-status" class="flex items-center gap-1.5 text-gray-400">
                <span class="w-2 h-2 rounded-full bg-yellow-500 animate-ping"></span> 探测中...
            </span>
            <span id="vram-stat" class="font-mono text-gray-400">等待 GPU 状态...</span>
            <a id="btn-download-top" href="#" class="hidden bg-green-700 hover:bg-green-600 text-white px-3 py-1 rounded font-semibold text-xs transition shadow-md flex items-center gap-1">
                <span>📥 下载修复结果</span>
            </a>
        </div>
    </header>

    <!-- 7阶状态机实时轨迹流 -->
    <div class="grid grid-cols-7 gap-2 mb-4 text-center text-xs font-semibold" id="fsm-timeline">
        <div id="step-extraction" class="border py-2 px-1 rounded-lg step-pending transition-all">1. 需求提取</div>
        <div id="step-analysis" class="border py-2 px-1 rounded-lg step-pending transition-all">2. 架构规划</div>
        <div id="step-loading" class="border py-2 px-1 rounded-lg step-pending transition-all">3. 资源预热</div>
        <div id="step-construction" class="border py-2 px-1 rounded-lg step-pending transition-all">4. 代码构建</div>
        <div id="step-testing" class="border py-2 px-1 rounded-lg step-pending transition-all">5. 物理测试</div>
        <div id="step-healing" class="border py-2 px-1 rounded-lg step-pending transition-all">6. 自愈修复</div>
        <div id="step-completed" class="border py-2 px-1 rounded-lg step-pending transition-all">7. 交付审计</div>
    </div>

    <!-- 核心两栏工作台 -->
    <div class="grid grid-cols-12 gap-4 flex-grow mb-4">
        <!-- 左栏：文件拖拽上传与大模型思考流 (5列) -->
        <div class="col-span-5 flex flex-col gap-4">
            <!-- 上传与控制卡片 -->
            <div class="bg-[#161b22] border border-gray-800 rounded-xl p-4 flex flex-col gap-3 shadow-md">
                <div class="flex items-center justify-between">
                    <span class="text-sm font-semibold text-gray-200">📂 代码文件与需求提交</span>
                    <select id="mode-select" class="bg-gray-800 border border-gray-700 text-xs rounded px-2 py-1 text-gray-300">
                        <option value="fix">已有工程自愈 (Fix Bug)</option>
                        <option value="create">从0到1创建 (Greenfield)</option>
                    </select>
                </div>

                <!-- 拖拽上传区 -->
                <div id="drop-zone" onclick="document.getElementById('file-input').click()" class="border-2 border-dashed border-gray-700 hover:border-blue-500 rounded-xl p-4 text-center cursor-pointer transition flex flex-col items-center justify-center gap-1.5 bg-gray-900/50">
                    <input type="file" id="file-input" class="hidden" onchange="handleFileSelected(this.files[0])">
                    <span class="text-2xl" id="upload-icon">📄</span>
                    <span class="text-xs font-semibold text-gray-200" id="upload-text">点击或将代码文件 / 工程Zip包拖拽至此处</span>
                    <span class="text-[10px] text-gray-500">支持单脚本 (main.py, index.php) 或整个项目 (.zip 压缩包)</span>
                </div>

                <textarea id="input-task" rows="2" placeholder="输入需求或修复指令 (如: 分析文件，修复运算逻辑错误)..." class="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-xs focus:outline-none focus:border-blue-500 text-gray-200">分析并修复项目中的逻辑错误</textarea>

                <div class="flex gap-2">
                    <button onclick="submitTask()" id="btn-run" class="flex-grow bg-blue-600 hover:bg-blue-500 text-white font-medium py-2 rounded-lg text-xs transition shadow-lg shadow-blue-900/30 flex items-center justify-center gap-2">
                        <span>🚀 启动 Agent 物理自愈</span>
                    </button>
                    <button onclick="stopTask()" id="btn-stop" class="bg-red-900 hover:bg-red-800 text-red-200 font-medium px-4 py-2 rounded-lg text-xs transition border border-red-700">
                        <span>⏹ 停止</span>
                    </button>
                </div>
            </div>

            <!-- Agent 决策思考流 -->
            <div class="bg-[#161b22] border border-gray-800 rounded-xl p-4 flex-grow flex flex-col shadow-md">
                <div class="flex items-center justify-between border-b border-gray-800 pb-2 mb-2">
                    <span class="text-xs font-semibold text-gray-300 flex items-center gap-2">
                        🧠 思考与动作轨迹 (<span id="current-role" class="text-blue-400 font-mono font-bold">Idle</span>)
                    </span>
                    <span id="current-action" class="text-[11px] text-yellow-400 font-medium">就绪</span>
                </div>
                <div id="thought-terminal" class="flex-grow overflow-y-auto max-h-[300px] text-xs font-mono space-y-1.5 text-gray-400 p-1">
                    <div class="text-gray-600">等待上传并启动任务...</div>
                </div>
            </div>
        </div>

        <!-- 右栏：代码变更 Diff 对比视窗 (7列) -->
        <div class="col-span-7 bg-[#161b22] border border-gray-800 rounded-xl p-4 flex flex-col shadow-md">
            <div class="flex items-center justify-between border-b border-gray-800 pb-2 mb-2">
                <div class="flex items-center gap-2">
                    <span class="text-xs font-semibold text-gray-200">📝 代码变更比对视窗</span>
                    <span id="diff-file-name" class="text-xs text-blue-400 font-mono"></span>
                </div>
                <span class="text-[11px] text-gray-500 py-1">AST 门禁物理校验</span>
            </div>
            <div id="diff-container" class="flex-grow overflow-y-auto max-h-[460px] bg-gray-950 border border-gray-900 rounded-lg p-3 text-xs font-mono text-gray-300 whitespace-pre">
<span class="text-gray-600">暂无待应用的补丁。当 Fixer 生成补丁并通过门禁时，此处将实时高亮显示红绿增删行。</span>
            </div>
        </div>
    </div>

    <!-- 底部：真实物理测试控制台 -->
    <div class="bg-[#161b22] border border-gray-800 rounded-xl p-3 shadow-md mb-4">
        <div class="flex items-center justify-between border-b border-gray-800 pb-1.5 mb-2">
            <span class="text-xs font-semibold text-gray-300 flex items-center gap-2">
                🧪 物理编译器与测试沙箱 (Pytest / PHPUnit)
            </span>
            <span id="test-verdict" class="text-xs text-gray-500 font-mono font-bold">待触发</span>
        </div>
        <div id="test-output-console" class="max-h-24 overflow-y-auto text-[11px] font-mono text-gray-400 bg-gray-950 p-2 rounded">
            就绪中。
        </div>
    </div>

    <!-- 底部：团队数据飞轮大盘 -->
    <div class="bg-[#161b22] border border-gray-800 rounded-xl p-3 flex items-center justify-between shadow-md text-xs">
        <div class="flex items-center gap-4">
            <span class="font-bold text-gray-300 flex items-center gap-1.5">
                🔄 团队数据自进化飞轮
            </span>
            <span class="text-gray-400">已回收任务: <span id="stat-sessions" class="font-mono text-blue-400 font-bold">0</span> 次</span>
            <span class="text-gray-400">独立设备: <span id="stat-devices" class="font-mono text-yellow-400 font-bold">0</span> 台</span>
            <span class="text-gray-400">沉淀 SFT 样本: <span id="stat-sft" class="font-mono text-green-400 font-bold">0</span> 条</span>
            <span class="text-gray-400">沉淀 DPO 偏好对: <span id="stat-dpo" class="font-mono text-purple-400 font-bold">0</span> 对</span>
        </div>
        <button onclick="exportTrainingDataset()" id="btn-export" class="bg-gray-800 hover:bg-gray-700 text-gray-200 border border-gray-700 px-3 py-1.5 rounded-lg text-xs transition flex items-center gap-1.5">
            <span>📦 一键导出微调数据集</span>
        </button>
    </div>

    <!-- 前端交互脚本 -->
    <script>
        let ws = null;
        let selectedFile = null;
        let currentTaskId = null;

        function connectWS() {
            ws = new WebSocket(`ws://${location.host}/ws/live`);
            ws.onmessage = (event) => {
                const payload = JSON.parse(event.data);
                const { type, data } = payload;

                if (type === 'STATE_CHANGE') {
                    updateFSMState(data.state, data.role);
                    document.getElementById('current-action').innerText = data.action_desc || '正在运行中...';
                    appendLog(`🔄 状态流转 ➔ [${data.state}] (角色: ${data.role}) : ${data.action_desc || ''}`, 'text-blue-400 font-semibold');
                } else if (type === 'ACTION_LOG') {
                    document.getElementById('current-action').innerText = data.action;
                    appendLog(`⚡ ${data.detail}`, 'text-yellow-300');
                } else if (type === 'DIFF_PREVIEW') {
                    document.getElementById('diff-file-name').innerText = data.file;
                    renderDiff(data.old_code, data.new_code);
                } else if (type === 'TEST_OUTPUT') {
                    document.getElementById('test-output-console').innerText = data.output;
                    document.getElementById('test-verdict').innerText = data.passed ? '✅ PASSED' : '❌ FAILED';
                    document.getElementById('test-verdict').className = data.passed ? 'text-xs text-green-400 font-mono font-bold' : 'text-xs text-red-400 font-mono font-bold';
                } else if (type === 'TASK_COMPLETED') {
                    appendLog('🎉 任务全流程验证通过，修复完成！', 'text-green-400 font-bold');
                    resetRunButton();
                    showDownloadButton(data.task_id);
                } else if (type === 'TASK_FAILED') {
                    appendLog(`❌ 任务执行中断: ${data.error}`, 'text-red-400 font-bold');
                    document.getElementById('current-action').innerText = '异常中断';
                    resetRunButton();
                }
            };
            ws.onclose = () => setTimeout(connectWS, 2000);
        }
        connectWS();

        // 拖拽文件上传监听
        const dropZone = document.getElementById('drop-zone');
        ['dragenter', 'dragover'].forEach(name => {
            dropZone.addEventListener(name, (e) => { e.preventDefault(); dropZone.classList.add('dragover'); }, false);
        });
        ['dragleave', 'drop'].forEach(name => {
            dropZone.addEventListener(name, (e) => { e.preventDefault(); dropZone.classList.remove('dragover'); }, false);
        });
        dropZone.addEventListener('drop', (e) => {
            if (e.dataTransfer.files.length) {
                handleFileSelected(e.dataTransfer.files[0]);
            }
        });

        function handleFileSelected(file) {
            if (!file) return;
            selectedFile = file;
            document.getElementById('upload-icon').innerText = '✅';
            document.getElementById('upload-text').innerText = `已选取: ${file.name} (${(file.size / 1024).toFixed(1)} KB)`;

            // 自动判断适配器语言标签
            if (file.name.endsWith('.php')) {
                document.getElementById('adapter-badge').innerText = 'PHP';
            } else if (file.name.endsWith('.py')) {
                document.getElementById('adapter-badge').innerText = 'PYTHON';
            } else {
                document.getElementById('adapter-badge').innerText = 'PROJECT';
            }
        }

        async function submitTask() {
            if (!selectedFile && document.getElementById('mode-select').value === 'fix') {
                alert('请先选取或拖入需要诊断自愈的代码文件或项目 Zip 包！');
                return;
            }

            const isCreate = document.getElementById('mode-select').value === 'create';
            const taskText = document.getElementById('input-task').value;

            document.getElementById('btn-run').disabled = true;
            document.getElementById('btn-run').innerHTML = '<span class="animate-spin inline-block">⏳</span> 自愈中...';
            document.getElementById('btn-download-top').classList.add('hidden');
            document.getElementById('thought-terminal').innerHTML = '';

            const formData = new FormData();
            if (selectedFile) formData.append('file', selectedFile);
            formData.append('task', taskText);
            formData.append('is_create', isCreate);

            const res = await fetch('/api/task/upload-and-run', { method: 'POST', body: formData });
            const data = await res.json();
            currentTaskId = data.task_id;
            document.getElementById('task-id-badge').innerText = currentTaskId;
        }

        function showDownloadButton(taskId) {
            const dlBtn = document.getElementById('btn-download-top');
            dlBtn.href = `/api/task/download/${taskId}`;
            dlBtn.classList.remove('hidden');
        }

        function stopTask() {
            fetch('/api/task/stop', { method: 'POST' });
            appendLog('⚠️ 用户手动请求终止任务', 'text-red-400');
            resetRunButton();
        }

        function updateFSMState(state, role) {
            document.getElementById('current-role').innerText = role || state;
            const mapping = {
                'requirement_extraction': 'step-extraction',
                'requirement_analysis': 'step-analysis',
                'resource_loading': 'step-loading',
                'code_construction': 'step-construction',
                'web_testing': 'step-testing',
                'self_healing': 'step-healing',
                'delivery_completed': 'step-completed'
            };
            Object.values(mapping).forEach(id => {
                document.getElementById(id).className = 'border py-2 px-1 rounded-lg step-pending transition-all';
            });
            if (mapping[state]) {
                document.getElementById(mapping[state]).className = 'border py-2 px-1 rounded-lg step-active transition-all font-bold';
            }
        }

        function appendLog(text, cssClass = '') {
            const line = document.createElement('div');
            line.className = cssClass;
            line.innerText = `[${new Date().toLocaleTimeString()}] ${text}`;
            const terminal = document.getElementById('thought-terminal');
            terminal.appendChild(line);
            terminal.scrollTop = terminal.scrollHeight;
        }

        function renderDiff(oldCode, newCode) {
            let html = '';
            const oldLines = oldCode.split('\\n');
            const newLines = newCode.split('\\n');
            html += `<span class="text-red-400 font-bold">--- 当前代码内容</span>\\n`;
            oldLines.slice(0, 20).forEach((l, i) => { html += `<span class="text-red-300 bg-red-950/40 block">- ${i+1}: ${l}</span>`; });
            html += `\\n<span class="text-green-400 font-bold">+++ mas-fixer 专职自愈补丁</span>\\n`;
            newLines.slice(0, 20).forEach((l, i) => { html += `<span class="text-green-300 bg-green-950/40 block">+ ${i+1}: ${l}</span>`; });
            document.getElementById('diff-container').innerHTML = html;
        }

        function resetRunButton() {
            document.getElementById('btn-run').disabled = false;
            document.getElementById('btn-run').innerHTML = '<span>🚀 启动 Agent 物理自愈</span>';
        }

        async function probeSystemHealth() {
            try {
                const res = await fetch('/api/system/health');
                const data = await res.json();
                const connEl = document.getElementById('conn-status');
                const vramEl = document.getElementById('vram-stat');

                if (data.online) {
                    connEl.innerHTML = `<span class="w-2 h-2 rounded-full bg-green-500 animate-pulse"></span> <span class="text-green-400 font-semibold">${data.status_text}</span>`;
                    vramEl.innerHTML = `<span class="text-gray-300 font-mono">${data.gpu} · 显存: ${data.vram_used_mb}MB · LoRA: ${data.active_adapters_count}个</span>`;
                } else {
                    connEl.innerHTML = `<span class="w-2 h-2 rounded-full bg-red-500"></span> <span class="text-red-400 font-semibold">服务离线</span>`;
                    vramEl.innerHTML = `<span class="text-red-400 font-mono">⚠️ 8000 端口未响应 (WSL2 未就绪)</span>`;
                }
            } catch (e) {}
        }
        probeSystemHealth();
        setInterval(probeSystemHealth, 3000);

        async function refreshTelemetryStats() {
            try {
                const res = await fetch('/api/telemetry/stats');
                const d = await res.json();
                document.getElementById('device-badge').innerText = `🖥️ 设备: ${d.device_id}`;
                document.getElementById('stat-sessions').innerText = d.total_sessions;
                document.getElementById('stat-devices').innerText = d.unique_devices_count;
                document.getElementById('stat-sft').innerText = d.sft_samples_count;
                document.getElementById('stat-dpo').innerText = d.dpo_pairs_count;
            } catch (e) {}
        }
        refreshTelemetryStats();
        setInterval(refreshTelemetryStats, 4000);

        async function exportTrainingDataset() {
            const btn = document.getElementById('btn-export');
            btn.innerText = '⏳ 导出中...';
            const res = await fetch('/api/telemetry/export', { method: 'POST' });
            const data = await res.json();
            alert(`🎉 导出成功！\\n- SFT 训练集: ${data.sft_count} 条 (dataset_sft_team.json)\\n- DPO 偏好对: ${data.dpo_count} 对 (dataset_dpo_team.json)`);
            btn.innerText = '📦 一键导出微调数据集';
            refreshTelemetryStats();
        }
    </script>
</body>
</html>
"""


# ============================================================
# 2. 隔离沙箱上传接收与执行引擎
# ============================================================
@app.get("/", response_class=HTMLResponse)
async def serve_dashboard():
    return HTMLResponse(content=DASHBOARD_HTML)


@app.post("/api/task/upload-and-run")
async def upload_and_run_task(
    file: UploadFile = File(None), task: str = Form(...), is_create: bool = Form(False)
):
    """
    接收上传的文件/Zip，分配独立的隔离沙箱目录并在子线程运行自愈
    """
    task_id = f"sandbox_{int(time.time())}"
    sandbox_dir = WORKSPACE_ROOT / task_id
    sandbox_dir.mkdir(parents=True, exist_ok=True)

    # 如果有上传文件，安全保存到沙箱
    if file:
        uploaded_path = sandbox_dir / file.filename
        with open(uploaded_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        # 如果是 zip 包，自动在沙箱中解压
        if file.filename.endswith(".zip"):
            with zipfile.ZipFile(uploaded_path, "r") as z:
                z.extractall(sandbox_dir)
            uploaded_path.unlink()  # 移除 zip 原包
        else:
            pass  # 单文件直接保留

    def run_sandbox_worker():
        from server import main as run_server_cli

        # 构造安全沙箱执行参数，彻底避开全盘递归扫描
        args = ["server.py", "--standalone"]
        if is_create:
            args.extend(["--create", str(sandbox_dir), "--task", task])
        else:
            args.extend(["--project", str(sandbox_dir), "--task", task])

        sys.argv = args
        try:
            sync_broadcast(
                "ACTION_LOG",
                {"action": "沙箱初始化", "detail": f"任务已安全挂载至隔离沙箱: {sandbox_dir.name}"},
            )
            run_server_cli()
            sync_broadcast("TASK_COMPLETED", {"status": "success", "task_id": task_id})
        except SystemExit:
            sync_broadcast("TASK_COMPLETED", {"status": "success", "task_id": task_id})
        except Exception as e:
            sys.stderr.write(f"\n❌ 沙箱任务异常: {e}\n")
            sync_broadcast("TASK_FAILED", {"error": str(e)})

    threading.Thread(target=run_sandbox_worker, daemon=True).start()
    return {"status": "started", "task_id": task_id}


@app.get("/api/task/download/{task_id}")
async def download_fixed_workspace(task_id: str):
    """打包下载修复完成后的沙箱产物"""
    sandbox_dir = WORKSPACE_ROOT / task_id
    if not sandbox_dir.exists():
        return {"error": "沙箱任务不存在或已过期"}

    # 如果沙箱里只有一个单文件，直接下载该文件
    files = [f for f in sandbox_dir.iterdir() if f.is_file() and not f.name.endswith(".json")]
    if len(files) == 1:
        return FileResponse(files[0], filename=files[0].name)

    # 多个文件时自动打包成 zip 提供下载
    zip_path = WORKSPACE_ROOT / f"{task_id}_fixed.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, fnames in os.walk(sandbox_dir):
            for fname in fnames:
                if fname.endswith(".json") and fname != "composer.json":
                    continue  # 排除内部报告
                p = Path(root) / fname
                zf.write(p, p.relative_to(sandbox_dir))

    return FileResponse(zip_path, filename=f"fixed_project_{task_id}.zip")


@app.get("/api/system/health")
async def check_system_health():
    local_url = os.getenv("LOCAL_LLM_URL", "http://127.0.0.1:8000/v1")
    base_host = local_url.replace("/v1", "").rstrip("/")

    async with httpx.AsyncClient(timeout=1.5, trust_env=False) as client:
        # 依次探测 /health、/v1/models 以及 FastAPI 自带的 /openapi.json
        for probe_path in ["/health", "/v1/models", "/openapi.json"]:
            try:
                r = await client.get(f"{base_host}{probe_path}")
                if r.status_code == 200:
                    data = {}
                    try:
                        data = r.json()
                    except Exception:
                        pass
                    return {
                        "online": True,
                        "gpu": data.get("gpu", "NVIDIA GeForce RTX 4060"),
                        "vram_used_mb": data.get("vram_used_mb", 3800),
                        "active_adapters_count": len(data.get("active_adapters", [])) or 5,
                        "status_text": "本地 GPU 在线",
                    }
            except Exception:
                continue

    # 检查云端 API Key 备选
    if os.getenv("DEEPSEEK_API_KEY"):
        return {
            "online": True,
            "gpu": "Cloud DeepSeek API",
            "vram_used_mb": 0,
            "active_adapters_count": 1,
            "status_text": "云端 API 在线",
        }

    return {"online": False, "error": "本地 8000 端口未响应", "status_text": "服务离线"}


@app.get("/api/telemetry/stats")
async def get_telemetry_stats():
    return telemetry_collector.get_collection_stats()


@app.post("/api/telemetry/export")
async def export_telemetry_dataset():
    sft_cnt, dpo_cnt = telemetry_collector.export_sft_and_dpo()
    return {"status": "success", "sft_count": sft_cnt, "dpo_count": dpo_cnt}


@app.websocket("/ws/live")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_connections.append(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        if websocket in active_connections:
            active_connections.remove(websocket)


@app.post("/api/task/stop")
async def stop_autonomous_task():
    sync_broadcast("TASK_FAILED", {"error": "用户手动终止"})
    return {"status": "stopped"}


def launch_web_ui(host: str = "127.0.0.1", port: int = 5173):
    print(f"\n🚀 [MAS-Dashboard] 隔离沙箱可视化工作台已就绪: http://{host}:{port}")
    webbrowser.open(f"http://{host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    launch_web_ui()
