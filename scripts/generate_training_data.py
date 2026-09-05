import json
import random
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir))
sys.path.insert(0, str(root_dir / "mcp-server"))

from utils.trajectory_logger import AgentTrajectoryLogger

# ============================================================
# 1. 基础标准算法种子库（包含正确的源码与单元测试）
# ============================================================
SEED_BANK = [
    {
        "name": "math_add",
        "source": "def add(a: int, b: int) -> int:\n    return a + b\n",
        "test": "from main import add\n\ndef test_add():\n    assert add(2, 3) == 5\n    assert add(-1, 1) == 0\n",
        "bug_mutation": ("return a + b", "return a - b"),
    },
    {
        "name": "str_reverse",
        "source": "def reverse_str(s: str) -> str:\n    return s[::-1]\n",
        "test": "from main import reverse_str\n\ndef test_reverse():\n    assert reverse_str('hello') == 'olleh'\n    assert reverse_str('') == ''\n",
        "bug_mutation": ("return s[::-1]", "return s"),
    },
    {
        "name": "find_max",
        "source": "def find_max(numbers: list) -> int:\n    if not numbers:\n        return None\n    return max(numbers)\n",
        "test": "from main import find_max\n\ndef test_max():\n    assert find_max() == 5\n    assert find_max([]) is None\n",
        "bug_mutation": ("return max(numbers)", "return min(numbers)"),
    },
    {
        "name": "is_even",
        "source": "def is_even(n: int) -> bool:\n    return n % 2 == 0\n",
        "test": "from main import is_even\n\ndef test_is_even():\n    assert is_even(4) is True\n    assert is_even(7) is False\n",
        "bug_mutation": ("return n % 2 == 0", "return n % 2 == 1"),
    },
    {
        "name": "filter_positive",
        "source": "def filter_positive(nums: list) -> list:\n    return [x for x in nums if x > 0]\n",
        "test": "from main import filter_positive\n\ndef test_filter():\n    assert filter_positive() ==\n",
        "bug_mutation": ("if x > 0", "if x >= 0"),
    },
    {
        "name": "php_calc_discount",
        "source": "<?php\nfunction calculateDiscount(float $price, float $discount): float {\n    return $price * (1.0 - $discount);\n}\n",
        "test": "<?php\nuse PHPUnit\\Framework\\TestCase;\nrequire_once 'main.php';\n\nclass DiscountTest extends TestCase {\n    public function testDiscount() {\n        $this->assertEquals(80.0, calculateDiscount(100.0, 0.2));\n    }\n}\n",
        "bug_mutation": ("return $price * (1.0 - $discount);", "return $price * (1.0 + $discount);"),
    },
    {
        "name": "php_array_filter",
        "source": "<?php\nfunction filterEvenNumbers(array $nums): array {\n    return array_values(array_filter($nums, fn($n) => $n % 2 === 0));\n}\n",
        "test": "<?php\nuse PHPUnit\\Framework\\TestCase;\nrequire_once 'main.php';\n\nclass FilterTest extends TestCase {\n    public function testFilter() {\n        $this->assertEquals(, filterEvenNumbers());\n    }\n}\n",
        "bug_mutation": ("$n % 2 === 0", "$n % 2 !== 0"),
    },
]


def run_data_synthesis_pipeline(num_samples: int = 5):
    """自动化合成与轨迹采集流水线"""
    logger = AgentTrajectoryLogger(log_dir="trajectories")
    print(f"🚀 开始启动数据合成采集流水线，目标样本数: {num_samples} ...\n")

    collected_count = 0

    for i in range(num_samples):
        seed = random.choice(SEED_BANK)
        task_id = f"synth_{seed['name']}_{int(time.time())}_{i}"
        temp_dir = Path(tempfile.mkdtemp(prefix=f"bug_repo_{i}_"))

        try:
            # 1. 注入缺陷代码
            old_str, bug_str = seed["bug_mutation"]
            buggy_source = seed["source"].replace(old_str, bug_str)

            main_file = temp_dir / "main.py"
            test_file = temp_dir / "test_main.py"

            with open(main_file, "w", encoding="utf-8") as f:
                f.write(buggy_source)
            with open(test_file, "w", encoding="utf-8") as f:
                f.write(seed["test"])

            print(f"[{i + 1}/{num_samples}] 注入缺陷: 模块 {seed['name']} (变异: '{bug_str}')")

            # 2. 运行初始测试，捕获错误堆栈
            test_res = subprocess.run(
                [sys.executable, "-m", "pytest", str(test_file)],
                cwd=str(temp_dir),
                capture_output=True,
                text=True,
            )

            if test_res.returncode == 0:
                print("  ⏭️ 变异未导致单测报错，跳过")
                continue

            error_stack = test_res.stdout or test_res.stderr

            # 3. 模拟 Agent 修复与轨迹记录
            system_prompt = "你是一个代码修复专家 Fixer，请输出正确的修复代码。"
            user_prompt = (
                f"项目文件: main.py\n报错信息:\n{error_stack[:400]}\n源码:\n{buggy_source}"
            )

            # 模拟一次错误尝试（生成负样本）
            failed_fix = "def dummy_wrong_fix(): pass"
            logger.record_step(
                task_id=task_id,
                state="self_healing",
                agent_role="fixer",
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                environment_context={"source_file": "main.py", "error": error_stack[:300]},
                llm_raw_response=json.dumps(
                    {"target_file": "main.py", "fixed_content": failed_fix}
                ),
                step_success=False,
                error_feedback="Syntax / logic verification failed",
            )

            # 模拟正确修复（生成正样本）
            correct_fix = seed["source"]
            # 真实将正确代码写回验证
            with open(main_file, "w", encoding="utf-8") as f:
                f.write(correct_fix)

            verify_res = subprocess.run(
                [sys.executable, "-m", "pytest", str(test_file)],
                cwd=str(temp_dir),
                capture_output=True,
                text=True,
            )
            passed = verify_res.returncode == 0

            if passed:
                logger.record_step(
                    task_id=task_id,
                    state="fix_apply",
                    agent_role="fixer",
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    environment_context={"source_file": "main.py", "error": error_stack[:300]},
                    llm_raw_response=json.dumps(
                        {"target_file": "main.py", "fixed_content": correct_fix}
                    ),
                    step_success=True,
                )
                collected_count += 1
                print(f"  ✅ 验证通过！成功捕获一条物理验证闭环轨迹 -> {task_id}.jsonl")

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    # 4. 自动导出 SFT 与 DPO 数据集
    sft_data = logger.export_to_sft_format("dataset_sft.json")
    dpo_data = logger.export_to_dpo_format("dataset_dpo.json")

    print("\n" + "=" * 50)
    print(f"🎉 数据飞轮运行完成！共捕获 {collected_count} 条有效闭环轨迹")
    print(f"📁 导出 SFT 训练集: dataset_sft.json (共 {len(sft_data)} 条样本)")
    print(f"📁 导出 DPO 偏好集: dataset_dpo.json (共 {len(dpo_data)} 对偏好对)")
    print("=" * 50)


if __name__ == "__main__":
    run_data_synthesis_pipeline(num_samples=5)
