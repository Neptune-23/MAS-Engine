import subprocess
import time
import json
from pathlib import Path

def execute_shell_command_impl(command: str, cwd: str = None) -> str:
    """
    执行 shell 命令，返回 JSON 格式结果。
    
    Args:
        command: 要执行的命令（如 "cargo build"）
        cwd: 工作目录（可选）
    
    Returns:
        JSON 字符串，包含 success, exit_code, stdout, stderr, elapsed_seconds
    """
    start = time.time()
    try:
        cwd_path = Path(cwd) if cwd else None
        result = subprocess.run(
            command,
            shell=True,
            cwd=cwd_path,
            capture_output=True,
            text=True,
            timeout=600  # 10 分钟超时
        )
        elapsed = time.time() - start
        return json.dumps({
            "success": result.returncode == 0,
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "elapsed_seconds": round(elapsed, 2),
            "command": command,
            "cwd": cwd
        }, indent=2, ensure_ascii=False)
    except subprocess.TimeoutExpired as e:
        return json.dumps({
            "success": False,
            "error": f"Command timed out after {e.timeout} seconds",
            "command": command,
            "cwd": cwd
        })
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": str(e),
            "command": command,
            "cwd": cwd
        })