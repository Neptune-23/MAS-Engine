import hashlib
import json
import os
import platform
import socket
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ============================================================
# 1. 混合设备指纹提取器 (IP + MAC + Machine UUID + Hostname)
# ============================================================
def get_mac_address() -> str:
    """获取网卡物理 MAC 地址"""
    node = uuid.getnode()
    mac = ":".join(f"{(node >> i) & 0xFF:02x}" for i in range(0, 48, 8)[::-1])
    return mac


def get_machine_uuid() -> str:
    """跨平台获取机器底层硬件 UUID (支持 Windows 与 Linux/WSL)"""
    sys_name = platform.system().lower()
    try:
        if sys_name == "windows":
            res = subprocess.run(
                ["powershell", "-Command", "(Get-CimInstance Win32_ComputerSystemProduct).UUID"],
                capture_output=True,
                text=True,
                timeout=2,
            )
            val = res.stdout.strip()
            if val:
                return val
        elif sys_name == "linux":
            for path in ["/etc/machine-id", "/var/lib/dbus/machine-id"]:
                if os.path.exists(path):
                    with open(path, "r", encoding="utf-8") as f:
                        return f.read().strip()
    except Exception:
        pass
    # 兜底：使用系统节点与平台标识生成哈希伪 UUID
    raw = f"{platform.node()}_{platform.processor()}_{platform.version()}"
    return hashlib.md5(raw.encode()).hexdigest()


def get_local_ip() -> str:
    """获取本机局域网真实 IPv4 地址"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # 不实际发送数据包，用于路由探测真实出网网卡 IP
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


def get_device_fingerprint() -> Dict[str, str]:
    """生成混合设备指纹"""
    hostname = socket.gethostname()
    mac = get_mac_address()
    mach_uuid = get_machine_uuid()
    local_ip = get_local_ip()
    os_info = f"{platform.system()} {platform.release()}"

    # 混合哈希特征串
    raw_signature = f"{hostname}@@{mac}@@{mach_uuid}@@{platform.architecture()[0]}"
    device_id = hashlib.sha256(raw_signature.encode("utf-8")).hexdigest()[:16]

    return {
        "device_id": device_id,
        "hostname": hostname,
        "local_ip": local_ip,
        "mac_address": mac,
        "machine_uuid": mach_uuid[:18] + "...",
        "os": os_info,
    }


# ============================================================
# 2. 全生命周期数据回收中枢 (Telemetry Collector)
# ============================================================
class TelemetryCollector:
    """交互数据回收中枢：结构化存储全生命周期轨迹，并自动导出 SFT 与 DPO 数据"""

    def __init__(self, data_dir: str = "data/telemetry"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.fingerprint = get_device_fingerprint()

    def record_task_session(
        self,
        task_id: str,
        project_name: str,
        language: str,
        task_description: str,
        is_create_mode: bool,
        steps: List[Dict[str, Any]],
        final_verdict: str,
        user_feedback: Optional[str] = None,
    ) -> Path:
        """完整归档单次任务会话"""
        session_record = {
            "trace_id": f"trace_{int(time.time())}_{task_id[:12]}",
            "recorded_at": time.time(),
            "device": self.fingerprint,
            "task_meta": {
                "task_id": task_id,
                "project_name": project_name,
                "language": language,
                "task_description": task_description,
                "is_create_mode": is_create_mode,
            },
            "steps": steps,
            "final_verdict": final_verdict,
            "user_feedback": user_feedback or "auto_accepted",
        }

        target_file = self.data_dir / f"{task_id}.json"
        with open(target_file, "w", encoding="utf-8") as f:
            json.dump(session_record, f, indent=2, ensure_ascii=False)

        return target_file

    def get_collection_stats(self) -> Dict[str, Any]:
        """统计当前数据沉淀总量"""
        records = list(self.data_dir.glob("*.json"))
        total_sessions = len(records)
        unique_devices = set()
        total_sft_candidates = 0
        total_dpo_pairs = 0

        for r_path in records:
            try:
                with open(r_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                dev_id = data.get("device", {}).get("device_id")
                if dev_id:
                    unique_devices.add(dev_id)

                steps = data.get("steps", [])
                fixer_success = [s for s in steps if s.get("role") == "fixer" and s.get("passed")]
                fixer_fails = [s for s in steps if s.get("role") == "fixer" and not s.get("passed")]

                total_sft_candidates += len(fixer_success)
                if fixer_success and fixer_fails:
                    total_dpo_pairs += len(fixer_fails)
            except Exception:
                continue

        return {
            "device_id": self.fingerprint["device_id"],
            "total_sessions": total_sessions,
            "unique_devices_count": len(unique_devices),
            "sft_samples_count": total_sft_candidates,
            "dpo_pairs_count": total_dpo_pairs,
        }

    def export_sft_and_dpo(
        self, sft_out: str = "dataset_sft_team.json", dpo_out: str = "dataset_dpo_team.json"
    ) -> Tuple[int, int]:
        """将回收的物理闭环轨迹自动清洗为 SFT 与 DPO 训练文件"""
        sft_data = []
        dpo_data = []

        for r_path in self.data_dir.glob("*.json"):
            try:
                with open(r_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                steps = data.get("steps", [])
                # 提取成功的正样本用于 SFT
                for s in steps:
                    if s.get("passed") and s.get("role") in ["fixer", "developer"]:
                        conv = {
                            "id": f"{data.get('trace_id')}_{s.get('step_idx')}",
                            "conversations": [
                                {"from": "system", "value": s.get("system_prompt", "")},
                                {"from": "user", "value": s.get("user_prompt", "")},
                                {"from": "assistant", "value": s.get("response", "")},
                            ],
                        }
                        sft_data.append(conv)

                # 提取 (chosen, rejected) 偏好对用于 DPO
                fixer_success = [s for s in steps if s.get("role") == "fixer" and s.get("passed")]
                fixer_fails = [s for s in steps if s.get("role") == "fixer" and not s.get("passed")]

                if fixer_success and fixer_fails:
                    chosen = fixer_success[-1]
                    for rejected in fixer_fails:
                        dpo_entry = {
                            "system": chosen.get("system_prompt", ""),
                            "prompt": chosen.get("user_prompt", ""),
                            "chosen": chosen.get("response", ""),
                            "rejected": rejected.get("response", ""),
                        }
                        dpo_data.append(dpo_entry)
            except Exception:
                continue

        with open(sft_out, "w", encoding="utf-8") as f:
            json.dump(sft_data, f, indent=2, ensure_ascii=False)
        with open(dpo_out, "w", encoding="utf-8") as f:
            json.dump(dpo_data, f, indent=2, ensure_ascii=False)

        return len(sft_data), len(dpo_data)
