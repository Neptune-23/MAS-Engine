import json
import sys
import tempfile
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir))
sys.path.insert(0, str(root_dir / "mcp-server"))

from tools.analysis_tools import get_code_slice_impl


def test_ast_code_slicing_precision():
    """测试 1：AST 代码切片对嵌套函数与顶级 Imports 的精准定位"""
    sample_code = (
        """import os
import sys
from datetime import datetime

class PaymentGateway:
    def __init__(self):
        self.timeout = 30

    def process_transaction(self, order_id: str, amount: float):
        # 故障行：假设第 11 行抛出异常
        if amount <= 0:
            raise ValueError("Invalid amount")
        return {"status": "success", "order_id": order_id}

    def refund(self, order_id: str):
        return True
"""
        + "\n# 填充额外代码模拟大型工程文件\n" * 100
    )

    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False, encoding="utf-8") as f:
        f.write(sample_code)
        tmp_file = f.name

    try:
        # 定位第 11 行
        res_json = get_code_slice_impl(tmp_file, target_line=11)
        res = json.loads(res_json)

        assert "error" not in res
        assert res["enclosing_symbol"] == "function process_transaction"
        assert "from datetime import datetime" in res["imports"]
        assert "👉   11 |         if amount <= 0:" in res["sliced_code"]
    finally:
        if Path(tmp_file).exists():
            Path(tmp_file).unlink()


def test_token_reduction_ratio_benchmark():
    """测试 2：硬核指标断言 —— Token 降噪削减率必须大于 85%"""
    large_code = "def dummy():\n    pass\n" * 200  # 400 行大文件
    target_func = "\ndef target_critical_bug():\n    x = 1 / 0\n    return x\n"
    full_content = large_code + target_func + large_code

    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False, encoding="utf-8") as f:
        f.write(full_content)
        tmp_file = f.name

    try:
        # 找到目标函数所在行号（大约第 402 行）
        lines = full_content.splitlines()
        target_line = [i for i, line in enumerate(lines, 1) if "1 / 0" in line][0]

        res_json = get_code_slice_impl(tmp_file, target_line=target_line)
        res = json.loads(res_json)

        saving_ratio = float(res["token_saving_percent"].replace("%", ""))
        assert saving_ratio >= 85.0, (
            f"Token 削减率未达到工业级标准 (要求 >= 85%，实际 {saving_ratio}%)"
        )
    finally:
        if Path(tmp_file).exists():
            Path(tmp_file).unlink()
