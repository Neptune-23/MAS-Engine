from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

import json
import re

class BaseAdapter:
    # ...
    def clean_format_code(self, raw_resp: str) -> str:
        if not raw_resp or not isinstance(raw_resp, str):
            return ""
        
        text = raw_resp.strip()

        # 1. 优先尝试解析 JSON 信封（处理 {"fixed_content": "...", ...}）
        try:
            # 去除外部可能包裹的 ```json ... ```
            json_candidate = text
            if json_candidate.startswith("```json"):
                json_candidate = json_candidate[7:]
            elif json_candidate.startswith("```"):
                json_candidate = json_candidate[3:]
            if json_candidate.endswith("```"):
                json_candidate = json_candidate[:-3]
            json_candidate = json_candidate.strip()

            if json_candidate.startswith("{") and json_candidate.endswith("}"):
                data = json.loads(json_candidate)
                if isinstance(data, dict):
                    for key in ["fixed_content", "code", "content", "source", "fixed_code"]:
                        if key in data and isinstance(data[key], str):
                            text = data[key].strip()
                            break
        except Exception:
            pass

        # 2. 提取 Markdown 代码块（如 ```python ... ```）
        code_block_match = re.search(r"```(?:[a-zA-Z0-9_\+\-]+)?\n([\s\S]*?)```", text)
        if code_block_match:
            return code_block_match.group(1).strip()

        # 3. 若无标记则返回净化后的纯文本
        return text


class BaseLanguageAdapter(ABC):
    """所有语言适配器的统一抽象契约 (SPI)"""

    @property
    @abstractmethod
    def name(self) -> str:
        """语言唯一标识，如 'python', 'php'"""
        pass

    @property
    @abstractmethod
    def default_entry_file(self) -> str:
        """从 0 创建时的默认入口文件名，如 'main.py', 'index.php'"""
        pass

    @property
    @abstractmethod
    def source_patterns(self) -> List[str]:
        """源文件 glob 匹配模式，如 ['**/*.py']"""
        pass

    @property
    @abstractmethod
    def exclude_dirs(self) -> Set[str]:
        """扫描时需要排除的目录集合"""
        pass

    @abstractmethod
    def match_project(self, project_path: Path) -> bool:
        """检测目标项目是否属于该语言"""
        pass

    @abstractmethod
    def classify_files(self, file_paths: List[str]) -> Tuple[List[str], List[str]]:
        """将文件列表分为：(source_files, test_files)"""
        pass

    @abstractmethod
    def get_test_command(self, project_path: Path) -> str:
        """获取测试执行命令（如 pytest 或 phpunit）"""
        pass

    @abstractmethod
    def get_code_slice(self, file_path: Path, target_line: int, window: int = 15) -> Dict[str, Any]:
        """精准代码切片提取"""
        pass

    @abstractmethod
    def validate_syntax(self, file_path: str, code_content: str) -> Tuple[bool, str]:
        """静态语法门禁：验证代码是否具有语法错误"""
        pass

    @abstractmethod
    def clean_format_code(self, raw_code: str) -> str:
        """语言特定的代码后处理（修复粘连、补齐标签等）"""
        pass

BaseAdapter = BaseLanguageAdapter