import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir))
sys.path.insert(0, str(root_dir / "mcp_server"))

from llm_provider import LocalLLMProvider
from memory import TaskReflexionBuffer

from adapters.python_adapter import PythonAdapter


def validate_code_syntax(file_path, code_content=None):
  return PythonAdapter().validate_syntax(file_path, code_content)

COMPLEX_BENCHMARK_CASES = [
    {
        "tier": "Tier 1 (复杂控制流与边界值)",
        "name": "merge_intervals",
        "description": "区间合并算法：当两区间相邻或部分重叠时未能正确合并",
        "buggy_source": """def merge_intervals(intervals: list) -> list:
    if not intervals:
        return []
    intervals.sort(key=lambda x: x[0])
    merged = [intervals[0]]
    for current in intervals[1:]:
        prev = merged[-1]
        if current[0] > prev:
            merged.append(current)
        else:
            prev = current
    return merged
""",
        "test_code": """from main import merge_intervals

def test_merge_overlap():
    intervals = [list(x) for x in [(1, 3), (2, 6), (8, 10)]]
    expected = [list(x) for x in [(1, 6), (8, 10)]]
    assert merge_intervals(intervals) == expected

def test_merge_touching():
    intervals = [list(x) for x in [(1, 4), (4, 5)]]
    expected = [list(x) for x in [(1, 5)]]
    assert merge_intervals(intervals) == expected

def test_merge_contained():
    intervals = [list(x) for x in [(1, 5), (2, 3)]]
    expected = [list(x) for x in [(1, 5)]]
    assert merge_intervals(intervals) == expected
""",
    },
    {
        "tier": "Tier 2 (跨函数联动与下层契约失效)",
        "name": "user_order_calculator",
        "description": "上层计算器依赖下层折扣工具，下层函数返回了错误的数据类型导致上层崩溃",
        "buggy_source": """def calculate_discount(amount: float, is_vip: bool):
    if is_vip:
        return 0.2
    return "0.0"

def calculate_final_price(prices: list, is_vip: bool) -> float:
    total = sum(prices)
    discount = calculate_discount(total, is_vip)
    final_price = total * (1.0 - float(discount))
    return round(final_price, 2)
""",
        "test_code": """from main import calculate_final_price

def test_vip_discount():
    assert calculate_final_price([100.0, 50.0], is_vip=True) == 120.0

def test_regular_price():
    assert calculate_final_price([100.0, 50.0], is_vip=False) == 150.0
""",
    },
    {
        "tier": "Tier 3 (AST 方法级精准修复)",
        "name": "lru_cache_get_fix",
        "description": "LRU 缓存：通过 AST 切片锁定 get 方法，修复访问时未更新访问顺序的 Bug",
        "buggy_source": """class SimpleLRU:
    def __init__(self, capacity: int):
        self.capacity = capacity
        self.cache = {}
        self.order = []

    def get(self, key: str):
        if key not in self.cache:
            return -1
        # BUG: 访问后漏掉了 self.order.remove(key) 和 self.order.append(key)
        return self.cache[key]

    def put(self, key: str, value: int):
        if key in self.cache:
            self.cache[key] = value
            self.order.remove(key)
            self.order.append(key)
        else:
            if len(self.cache) >= self.capacity:
                oldest = self.order.pop(0)
                del self.cache[oldest]
            self.cache[key] = value
            self.order.append(key)
""",
        "test_code": """from main import SimpleLRU

def test_lru_cache_policy():
    lru = SimpleLRU(2)
    lru.put("a", 1)
    lru.put("b", 2)
    assert lru.get("a") == 1
    lru.put("c", 3)
    assert lru.get("b") == -1
    assert lru.get("a") == 1
    assert lru.get("c") == 3
""",
    },
]


def extract_code_from_llm_response(raw_text: str) -> str:
    """提取生成的纯代码"""
    text = raw_text.strip()
    json_match = re.search(r"\{.*\}", text, re.DOTALL)
    if json_match:
        try:
            data = json.loads(json_match.group(0), strict=False)
            val = data.get("fixed_content", "") or data.get("code", "")
            if val and ("def " in val or "class " in val):
                return val.strip()
        except Exception:
            pass

    code_match = re.search(r"```(?:python)?\s*(.*?)\s*```", text, re.DOTALL)
    if code_match:
        val = code_match.group(1).strip()
        if "def " in val or "class " in val:
            return val

    def_match = re.search(r"(?:from\s+\w+|import\s+\w+|def\s+\w+|class\s+\w+)[\s\S]*", text)
    if def_match:
        return def_match.group(0).strip()

    return text


def run_benchmark():
    print("=" * 60)
    print("🎯 MAS-Engine 多轮自反思自愈压测 (Max Retries = 3)")
    print("=" * 60 + "\n")

    try:
      provider = LocalLLMProvider(
          base_url="http://127.0.0.1:8000/v1",
          default_model="mas-fixer-specialist",
      )
    except Exception as e:
      print(f"❌ 无法连接本地推理服务: {e}")
      sys.exit(1)

    results = []

    for idx, case in enumerate(COMPLEX_BENCHMARK_CASES, start=1):
        print(f"[{idx}/3] 正在测试: {case['tier']} -> {case['name']}")
        print(f"      说明: {case['description']}")

        temp_dir = Path(tempfile.mkdtemp(prefix=f"bench_{case['name']}_"))
        main_file = temp_dir / "main.py"
        test_file = temp_dir / "test_main.py"

        with open(main_file, "w", encoding="utf-8") as f:
            f.write(case["buggy_source"])
        with open(test_file, "w", encoding="utf-8") as f:
            f.write(case["test_code"])

        # 初始化单任务反思缓冲区 (最多重试 3 轮)
        reflexion_buffer = TaskReflexionBuffer(max_retries=3)
        task_passed = False
        attempts_used = 0
        start_total_t = time.time()

        try:
            while not reflexion_buffer.is_exceeded():
                attempts_used += 1

                # 1. 运行测试捕获当前报错
                current_test = subprocess.run(
                    [sys.executable, "-m", "pytest", str(test_file)],
                    cwd=str(temp_dir),
                    capture_output=True,
                    text=True,
                )
                if current_test.returncode == 0:
                    task_passed = True
                    break

                error_output = current_test.stdout or current_test.stderr

                # 2. 注入历史反思提示词（负向约束）
                negative_prompt = reflexion_buffer.format_negative_prompt()

                system_prompt = "你是一个代码修复专家 Fixer。必须输出完整且正确的 Python 替换代码。"
                user_prompt = (
                    f"项目文件: main.py\n"
                    f"当前报错信息:\n{error_output[:400]}\n"
                    f"当前源码:\n{case['buggy_source']}\n"
                    f"{negative_prompt}"
                )

                t0 = time.time()
                raw_response = provider.generate_response(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    temperature=0.2 if attempts_used > 1 else 0.1,  # 重试时略微提高探索性
                )
                step_lat = round(time.time() - t0, 2)

                fixed_code = extract_code_from_llm_response(raw_response)

                # 3. 语法门禁
                syntax_ok, syntax_err = validate_code_syntax("main.py", fixed_code)
                if not syntax_ok:
                    print(f"      ⚠️ [尝试 #{attempts_used}] 语法拦截拦截无效代码 ({step_lat}s)")
                    reflexion_buffer.record_failure(
                        patch_code=raw_response[:200],
                        error_type="SYNTAX_ERROR",
                        error_detail=syntax_err,
                    )
                    continue

                # 4. 写入并验证
                with open(main_file, "w", encoding="utf-8") as f:
                    f.write(fixed_code)

                verify_test = subprocess.run(
                    [sys.executable, "-m", "pytest", str(test_file)],
                    cwd=str(temp_dir),
                    capture_output=True,
                    text=True,
                )

                if verify_test.returncode == 0:
                    task_passed = True
                    print(
                        f"      ✅ [尝试 #{attempts_used}] 修复成功并通过单测！(耗时 {step_lat}s)"
                    )
                    break
                else:
                    fail_msg = (verify_test.stdout or verify_test.stderr)[-200:]
                    print(
                        f"      🔄 [尝试 #{attempts_used}] 未通过单测，进入下一轮反思自愈 ({step_lat}s)"
                    )
                    reflexion_buffer.record_failure(
                        patch_code=fixed_code[:200],
                        error_type="TEST_FAILED",
                        error_detail=fail_msg,
                    )

            total_lat = round(time.time() - start_total_t, 2)
            status_icon = "✅ PASS" if task_passed else "❌ FAIL"
            print(
                f"      🏁 最终结果: {status_icon} (总耗时: {total_lat}s, 尝试轮次: {attempts_used}/3)"
            )

            results.append(
                {
                    "tier": case["tier"],
                    "name": case["name"],
                    "passed": task_passed,
                    "attempts": attempts_used,
                    "latency_sec": total_lat,
                }
            )
            print("-" * 60)

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    pass_count = sum(1 for r in results if r["passed"])
    pass_rate = round((pass_count / len(results)) * 100, 1)

    print("\n" + "=" * 60)
    print(f"📊 多轮自反思自愈总战报: 最终通过率 = {pass_rate}% ({pass_count}/{len(results)})")
    print("=" * 60)
    for r in results:
        mark = "✅" if r["passed"] else "❌"
        print(
            f"  {mark} [{r['tier']}] {r['name']}: {r['attempts']} 轮尝试 -> {'通过' if r['passed'] else '失败'} ({r['latency_sec']}s)"
        )
    print("=" * 60)


if __name__ == "__main__":
    run_benchmark()
