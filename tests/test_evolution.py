import json
import sys
import tempfile
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir))

from kernel.evolution.miner import TrajectoryMiner
from kernel.evolution.registry import EvolvedSkillRegistry
from kernel.evolution.synthesizer import SkillSynthesizer


def test_trajectory_mining_and_skill_synthesis():
    """测试 1：从真实遥测数据挖掘模式，并成功合成为 Python 宏代码"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        telemetry_dir = Path(tmp_dir) / "telemetry"
        skills_dir = Path(tmp_dir) / "skills"
        telemetry_dir.mkdir(parents=True)
        skills_dir.mkdir(parents=True)

        # 模拟一份成功的遥测会话
        session_data = {
            "trace_id": "trace_mock_001",
            "final_verdict": "SUCCESS",
            "task_meta": {"language": "python", "task_description": "assert 120.0 == 80.0"},
            "steps": [
                {
                    "step_idx": 1,
                    "role": "fixer",
                    "passed": True,
                    "error_input": "AssertionError: assert 120.0 == 80.0",
                    "source_slice": "return price * (1.0 + discount)",
                    "response": "def calculate(price, discount):\n    return price * (1.0 - discount)\n",
                }
            ],
        }
        with open(telemetry_dir / "session_1.json", "w", encoding="utf-8") as f:
            json.dump(session_data, f)

        # 1. 挖掘模式
        miner = TrajectoryMiner(telemetry_dir=telemetry_dir)
        patterns = miner.mine_successful_patterns(min_frequency=1)
        assert len(patterns) == 1
        pat = patterns[0]
        assert pat.language == "python"

        # 2. 合成程序化技能
        synthesizer = SkillSynthesizer(output_skills_dir=skills_dir)
        skill_file = synthesizer.synthesize_skill(pat)
        assert skill_file is not None
        assert skill_file.exists()


def test_rsi_fast_path_zero_token_fix():
    """测试 2：RSI 零 Token 快车道自愈验证 (直接命中宏技能)"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        skills_dir = Path(tmp_dir) / "skills"
        skills_dir.mkdir(parents=True)

        # 手动向技能库注册一个宏技能文件
        err_msg = "AssertionError: assert 120.0 == 80.0"
        sig = TrajectoryMiner.extract_error_signature(err_msg)

        skill_code = f"""
SKILL_META = {{
    "pattern_id": "pat_test_001",
    "language": "python",
    "error_signature": "{sig}"
}}

def execute_macro_fix(source_content: str, error_context: dict) -> tuple[bool, str]:
    return True, "def calculate():\\n    return 80.0\\n"
"""
        (skills_dir / f"auto_skill_python_{sig}.py").write_text(skill_code, encoding="utf-8")

        # 装载注册中心
        registry = EvolvedSkillRegistry(skills_dir=skills_dir)
        assert len(registry._loaded_skills) == 1

        # 执行极速自愈探测
        hit, fixed_code, skill_id = registry.try_fast_path_fix(
            language="python",
            error_message=err_msg,
            source_content="def calculate(): return 120.0",
        )

        # 验证 100% 命中，且产出了正确的修复结果
        assert hit is True
        assert skill_id == "pat_test_001"
        assert "return 80.0" in fixed_code
