import sys
import tempfile
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir))

from utils.telemetry import TelemetryCollector, get_device_fingerprint


def test_device_fingerprint_generation():
    """测试 1：混合设备指纹生成的唯一性与字段完整性"""
    fp = get_device_fingerprint()

    assert "device_id" in fp
    assert len(fp["device_id"]) == 16, "device_id 必须为 16 位十六进制短哈希"
    assert "local_ip" in fp
    assert "mac_address" in fp
    assert "hostname" in fp
    assert "os" in fp
    print(f"\n[指纹自测] 本地设备 ID: {fp['device_id']} | 局域网 IP: {fp['local_ip']}")


def test_telemetry_session_recording_and_export():
    """测试 2：会话记录落盘与 SFT / DPO 自动转换导出"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        collector = TelemetryCollector(data_dir=tmp_dir)

        sample_steps = [
            {
                "step_idx": 1,
                "role": "fixer",
                "system_prompt": "你是一个代码修复专家",
                "user_prompt": "修复函数 add",
                "response": "def add(a, b): return a - b",  # 失败尝试
                "passed": False,
            },
            {
                "step_idx": 2,
                "role": "fixer",
                "system_prompt": "你是一个代码修复专家",
                "user_prompt": "修复函数 add",
                "response": "def add(a, b): return a + b",  # 成功修复
                "passed": True,
            },
        ]

        # 记录一次会话
        session_file = collector.record_task_session(
            task_id="test_task_telemetry_001",
            project_name="demo_calc",
            language="python",
            task_description="修复计算器加法Bug",
            is_create_mode=False,
            steps=sample_steps,
            final_verdict="SUCCESS",
        )

        assert session_file.exists()

        # 统计检查
        stats = collector.get_collection_stats()
        assert stats["total_sessions"] == 1
        assert stats["sft_samples_count"] == 1
        assert stats["dpo_pairs_count"] == 1

        # 导出检查
        sft_path = Path(tmp_dir) / "sft.json"
        dpo_path = Path(tmp_dir) / "dpo.json"
        sft_count, dpo_count = collector.export_sft_and_dpo(str(sft_path), str(dpo_path))

        assert sft_count == 1
        assert dpo_count == 1
