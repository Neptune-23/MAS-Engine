import shutil
import sys
import tempfile
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir))

from utils.trajectory_logger import AgentTrajectoryLogger


def test_trajectory_recording_and_sft_dpo_export():
    """测试轨迹记录与 SFT / DPO 数据集自动转换"""
    tmp_log_dir = tempfile.mkdtemp(prefix="test_traj_")

    try:
        logger = AgentTrajectoryLogger(log_dir=tmp_log_dir)
        task_id = "task_traj_001"

        # 1. 记录一次失败尝试 (Rejected)
        logger.record_step(
            task_id=task_id,
            state="self_healing",
            agent_role="fixer",
            system_prompt="sys prompt",
            user_prompt="fix error",
            environment_context={"err": "TypeError"},
            llm_raw_response="def wrong_fix(): pass",
            step_success=False,
            error_feedback="AssertionError",
        )

        # 2. 记录一次成功修复 (Chosen)
        logger.record_step(
            task_id=task_id,
            state="delivery_completed",
            agent_role="fixer",
            system_prompt="sys prompt",
            user_prompt="fix error",
            environment_context={"err": "TypeError"},
            llm_raw_response="def correct_fix(): return True",
            step_success=True,
        )

        # 3. 验证 JSONL 文件已生成
        jsonl_path = Path(tmp_log_dir) / f"{task_id}.jsonl"
        assert jsonl_path.exists()

        # 4. 验证 SFT 导出 (conversations 是列表: 0 为 system, 1 为 user, 2 为 assistant)
        sft_output = Path(tmp_log_dir) / "sft.json"
        sft_items = logger.export_to_sft_format(str(sft_output))
        assert len(sft_items) == 1

        conv_list = sft_items[0]["conversations"]
        assistant_reply = [m["value"] for m in conv_list if m.get("from") == "assistant"][0]
        assert assistant_reply == "def correct_fix(): return True"

        # 5. 验证 DPO 偏好对导出
        dpo_output = Path(tmp_log_dir) / "dpo.json"
        dpo_items = logger.export_to_dpo_format(str(dpo_output))
        assert len(dpo_items) == 1
        assert dpo_items[0]["chosen"] == "def correct_fix(): return True"
        assert dpo_items[0]["rejected"] == "def wrong_fix(): pass"

    finally:
        shutil.rmtree(tmp_log_dir, ignore_errors=True)
