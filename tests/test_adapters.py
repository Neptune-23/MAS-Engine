import sys
import tempfile
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir))

from adapters import detect_adapter, get_adapter


def test_adapter_registry_and_selection():
    """测试 1：工厂方法按名称提取适配器"""
    py_adapter = get_adapter("python")
    php_adapter = get_adapter("php")

    assert py_adapter.name == "python"
    assert php_adapter.name == "php"
    assert py_adapter.default_entry_file == "main.py"
    assert php_adapter.default_entry_file == "index.php"


def test_python_syntax_and_code_clean():
    """测试 2：Python 适配器的语法门禁与粘连修复"""
    adapter = get_adapter("python")

    # 语法校验
    ok, _ = adapter.validate_syntax("test.py", "def hello():\n    return 'ok'")
    bad, err = adapter.validate_syntax("test.py", "def hello(\n broken")
    assert ok is True
    assert bad is False

    # 粘连修复
    cleaned = adapter.clean_format_code("defcalculate(a):returna+1")
    assert "def calculate(a):" in cleaned
    assert "return a+1" in cleaned or "return a + 1" in cleaned


def test_php_syntax_and_detection():
    """测试 3：PHP 适配器的项目检测与代码标签自动补齐"""
    adapter = get_adapter("php")

    # 自动标签补齐
    cleaned = adapter.clean_format_code("echo 'hello';")
    assert cleaned.startswith("<?php")

    # 模拟 PHP 项目自动探测
    with tempfile.TemporaryDirectory() as tmp_dir:
        p = Path(tmp_dir)
        (p / "composer.json").write_text("{}", encoding="utf-8")
        detected = detect_adapter(str(p))
        assert detected.name == "php"
