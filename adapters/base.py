from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Tuple


class BaseLanguageAdapter(ABC):
  """专职语言适配器抽象基类"""

  @property
  def name(self) -> str:
    return "base"

  @property
  def file_extensions(self) -> List[str]:
    return []

  @property
  def default_entry_file(self) -> str:
    return "main.py"

  @abstractmethod
  def match_project(self, project_path: Path) -> bool:
    pass

  @abstractmethod
  def validate_syntax(
      self, file_path_or_code: str, code_content: str = None
  ) -> Tuple[bool, str]:
    pass

  @abstractmethod
  def get_code_slice(
      self,
      file_path: Path,
      target_line: int = None,
      context_window: int = 15,
      symbol_name: str = None,
  ) -> Dict[str, Any]:
    pass

  @abstractmethod
  def get_test_command(self, project_path: Path) -> str:
    pass

  def clean_format_code(self, raw_resp: str) -> str:
    """通用代码清洗实现"""
    if not raw_resp:
      return ""
    return raw_resp.strip()


BaseAdapter = BaseLanguageAdapter
