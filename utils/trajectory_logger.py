import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


class AgentTrajectoryLogger:
    """Agent 交互轨迹记录器：捕获环境状态、Prompt、原始响应与最终物理验证结果"""

    def __init__(self, log_dir: str = "trajectories"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True, parents=True)

    def record_step(
        self,
        task_id: str,
        state: str,
        agent_role: str,
        system_prompt: str,
        user_prompt: str,
        environment_context: Dict[str, Any],
        llm_raw_response: str,
        step_success: bool = True,
        error_feedback: Optional[str] = None,
    ):
        """记录单步决策轨迹到对应任务的 jsonl 文件中"""
        step_data = {
            "timestamp": time.time(),
            "task_id": task_id,
            "state": state,
            "agent_role": agent_role,
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "environment_context": environment_context,
            "llm_raw_response": llm_raw_response,
            "step_success": step_success,
            "error_feedback": error_feedback,
        }

        task_file = self.log_dir / f"{task_id}.jsonl"
        with open(task_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(step_data, ensure_ascii=False) + "\n")

    def export_to_sft_format(self, output_file: str = "dataset_sft.json") -> List[Dict[str, Any]]:
        """
        导出为标准 SFT 训练格式（ShareGPT / ChatML 格式）
        只筛选最终通过测试（is_success=True）的高质量正样本
        """
        sft_dataset = []

        for jsonl_file in self.log_dir.glob("*.jsonl"):
            with open(jsonl_file, "r", encoding="utf-8") as f:
                steps = [json.loads(line) for line in f if line.strip()]

            # 检查该任务最终是否成功交付
            task_success = any(
                s.get("state") == "delivery_completed" or s.get("step_success") is True
                for s in steps
            )
            if not task_success:
                continue

            for step in steps:
                if step.get("agent_role") == "fixer" and step.get("step_success"):
                    conversation = {
                        "id": f"{step['task_id']}_{int(step['timestamp'])}",
                        "conversations": [
                            {"from": "system", "value": step["system_prompt"]},
                            {"from": "user", "value": step["user_prompt"]},
                            {"from": "assistant", "value": step["llm_raw_response"]},
                        ],
                    }
                    sft_dataset.append(conversation)

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(sft_dataset, f, indent=2, ensure_ascii=False)

        return sft_dataset

    def export_to_dpo_format(self, output_file: str = "dataset_dpo.json") -> List[Dict[str, Any]]:
        """
        导出为 DPO 偏好对齐数据集：
        自动将“重试失败的尝试”作为 rejected，将“最终通过的尝试”作为 chosen
        """
        dpo_dataset = []

        for jsonl_file in self.log_dir.glob("*.jsonl"):
            with open(jsonl_file, "r", encoding="utf-8") as f:
                steps = [json.loads(line) for line in f if line.strip()]

            fixer_steps = [s for s in steps if s.get("agent_role") == "fixer"]
            successful_steps = [s for s in fixer_steps if s.get("step_success")]
            failed_steps = [s for s in fixer_steps if not s.get("step_success")]

            if successful_steps and failed_steps:
                chosen = successful_steps[-1]
                for rejected in failed_steps:
                    dpo_item = {
                        "system": chosen["system_prompt"],
                        "prompt": chosen["user_prompt"],
                        "chosen": chosen["llm_raw_response"],
                        "rejected": rejected["llm_raw_response"],
                    }
                    dpo_dataset.append(dpo_item)

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(dpo_dataset, f, indent=2, ensure_ascii=False)

        return dpo_dataset
