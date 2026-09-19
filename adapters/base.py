import json
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple


class BaseLanguageAdapter:

  def clean_format_code(self, raw_resp: str) -> str:
    """清洗大模型输出，剥离 Markdown 代码块或 JSON 信封"""
    if not raw_resp or not isinstance(raw_resp, str):
      return ""

    text = raw_resp.strip()

    # 1. 优先提取 Markdown 代码块
    code_block_match = re.search(
        r"```(?:[a-zA-Z0-9_\+\-]+)?\n([\s\S]*?)```", text
    )
    if code_block_match:
      text = code_block_match.group(1).strip()

    # 2. 检查是否包裹在 JSON 信封中 (如 {"fixed_content": "..."})
    if text.startswith("{") and text.endswith("}"):
      try:
        data = json.loads(text)
        if isinstance(data, dict):
          for key in [
              "fixed_content",
              "code",
              "content",
              "source",
              "fixed_code",
          ]:
            if key in data and isinstance(data[key], str):
              text = data[key].strip()
              break
      except Exception:
        pass

    # 3. 再次解开可能嵌套的代码块
    inner_block = re.search(r"```(?:[a-zA-Z0-9_\+\-]+)?\n([\s\S]*?)```", text)
    if inner_block:
      text = inner_block.group(1).strip()

    return text


# 兼容别名
BaseAdapter = BaseLanguageAdapter


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
