import ast
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

from adapters.base import BaseLanguageAdapter


class PythonAdapter(BaseLanguageAdapter):

    def validate_syntax(
            self, file_path_or_code: str, code_content: str = None
        ) -> tuple[bool, str]:
        """校验 Python 代码语法，并防御裸字典 AST（未解包 JSON）"""
        if code_content is None:
            code = file_path_or_code
        else:
            code = code_content

        if not code or not code.strip():
            return False, "代码内容为空"

        try:
            tree = ast.parse(code)
            # 核心守卫：如果 AST 仅包含单个字典表达式，判定为泄漏的 JSON 报文，拒绝放行
            if (
                len(tree.body) == 1
                and isinstance(tree.body[0], ast.Expr)
                and isinstance(tree.body[0].value, ast.Dict)
            ):
                return (
                False,
                "语法校验拦截：检测到内容为纯字典字面量，疑似未解包的 JSON 信封",
            )

            return True, "Python 语法校验通过"
        except SyntaxError as e:
            return False, f"Python 语法错误: {e}"


    """Python 语言插拔式适配器"""

    @property
    def name(self) -> str:
        return "python"

    @property
    def default_entry_file(self) -> str:
        return "main.py"

    @property
    def source_patterns(self) -> List[str]:
        return ["**/*.py"]

    @property
    def exclude_dirs(self) -> Set[str]:
        return {"venv", ".venv", "__pycache__", ".pytest_cache", ".git", "build", "dist"}

    def match_project(self, project_path: Path) -> bool:
        if not project_path.exists():
            return False
        markers = ["requirements.txt", "pyproject.toml", "setup.py", "Pipfile"]
        if any((project_path / m).exists() for m in markers):
            return True
        # 探测是否存在 .py 文件
        return any(project_path.glob("*.py"))

    def classify_files(self, file_paths: List[str]) -> Tuple[List[str], List[str]]:
        test_files = []
        source_files = []
        for f in file_paths:
            basename = os.path.basename(f)
            if basename.startswith("test_") or basename.endswith("_test.py"):
                test_files.append(f)
            else:
                source_files.append(f)
        return source_files, test_files

    def get_test_command(self, project_path: Path) -> str:
        return "pytest -v --tb=short"

    def get_code_slice(self, file_path: Path, target_line: int, window: int = 15) -> Dict[str, Any]:
        if not file_path.exists():
            return {"error": f"文件不存在: {file_path}"}

        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()

        total_lines = len(lines)
        imports = []
        content = "".join(lines)
        enclosing_symbol = None
        start_line = 1
        end_line = total_lines

        try:
            tree = ast.parse(content)
            for node in tree.body:
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    seg = ast.get_source_segment(content, node)
                    if seg:
                        imports.append(seg)

            if target_line is not None:
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                        if hasattr(node, "lineno") and hasattr(node, "end_lineno"):
                            if node.lineno <= target_line <= node.end_lineno:
                                start_line = max(1, node.lineno)
                                end_line = min(total_lines, node.end_lineno)
                                enclosing_symbol = f"function/class {node.name}"
        except SyntaxError:
            pass

        if enclosing_symbol is None and target_line is not None:
            start_line = max(1, target_line - window)
            end_line = min(total_lines, target_line + window)
            enclosing_symbol = f"window_lines_{start_line}_{end_line}"

        sliced_raw = lines[start_line - 1 : end_line]
        sliced_code = []
        for idx, line_text in enumerate(sliced_raw, start=start_line):
            marker = "👉 " if idx == target_line else "   "
            sliced_code.append(f"{marker}{idx:4d} | {line_text.rstrip()}")

        token_saving = max(0, round((1 - len(sliced_raw) / max(1, total_lines)) * 100, 1))
        return {
            "total_lines": total_lines,
            "slice_range": [start_line, end_line],
            "enclosing_symbol": enclosing_symbol,
            "imports": imports,
            "sliced_code": "\n".join(sliced_code),
            "token_saving_percent": f"{token_saving}%",
        }

    def clean_format_code(self, raw_code: str) -> str:
        code = raw_code.replace("Ġ", " ").replace("Ċ", "\n").replace("ĉ", "\t").strip()
        code_match = re.search(r"```(?:python)?\s*(.*?)\s*```", code, re.DOTALL)
        if code_match:
            code = code_match.group(1).strip()

        # 自动修复 Python 关键字粘连与缩进
        code = re.sub(r"\bdef([a-zA-Z_])", r"def \1", code)
        code = re.sub(r"\breturn([a-zA-Z0-9_\(\*\-\s])", r"return \1", code)
        code = re.sub(r"\bimport([a-zA-Z_])", r"import \1", code)
        code = re.sub(r"\bfrom([a-zA-Z_])", r"from \1", code)
        code = re.sub(r":\s*return\b", r":\n    return", code)
        return code
