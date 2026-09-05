from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple


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
