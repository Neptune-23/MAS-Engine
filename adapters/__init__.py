from pathlib import Path
from typing import Dict

from adapters.base import BaseLanguageAdapter
from adapters.php_adapter import PHPAdapter
from adapters.python_adapter import PythonAdapter

# 注册支持的语言适配器
_REGISTRY: Dict[str, BaseLanguageAdapter] = {
    "python": PythonAdapter(),
    "php": PHPAdapter(),
}


def get_adapter(language: str) -> BaseLanguageAdapter:
    """根据语言名称获取适配器（默认降级为 Python）"""
    key = str(language).lower().strip()
    return _REGISTRY.get(key, _REGISTRY["python"])


def detect_adapter(project_path: str) -> BaseLanguageAdapter:
    """根据项目目录结构与特征文件，自动探测并返回对应的语言适配器"""
    path = Path(project_path)
    if not path.exists():
        return _REGISTRY["python"]

    # 优先检测 PHP
    if _REGISTRY["php"].match_project(path):
        return _REGISTRY["php"]

    # 其次检测 Python
    if _REGISTRY["python"].match_project(path):
        return _REGISTRY["python"]

    # 默认兜底 Python
    return _REGISTRY["python"]


__all__ = ["BaseLanguageAdapter", "PythonAdapter", "PHPAdapter", "get_adapter", "detect_adapter"]
