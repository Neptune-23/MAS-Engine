import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

from adapters.base import BaseLanguageAdapter


class PHPAdapter(BaseLanguageAdapter):
    """PHP 语言插拔式适配器"""

    @property
    def name(self) -> str:
        return "php"

    @property
    def default_entry_file(self) -> str:
        return "index.php"

    @property
    def source_patterns(self) -> List[str]:
        return ["**/*.php"]

    @property
    def exclude_dirs(self) -> Set[str]:
        return {"vendor", "storage", "node_modules", ".git", "runtime", "cache"}

    def match_project(self, project_path: Path) -> bool:
        if not project_path.exists():
            return False
        if (project_path / "composer.json").exists():
            return True
        return any(project_path.glob("*.php"))

    def classify_files(self, file_paths: List[str]) -> Tuple[List[str], List[str]]:
        test_files = []
        source_files = []
        for f in file_paths:
            basename = os.path.basename(f)
            if (
                basename.endswith("Test.php")
                or basename.startswith("test_")
                or basename.endswith("_test.php")
            ):
                test_files.append(f)
            else:
                source_files.append(f)
        return source_files, test_files

    def get_test_command(self, project_path: Path) -> str:
        vendor_bin = project_path / "vendor" / "bin"
        if (vendor_bin / "phpunit").exists():
            return "vendor/bin/phpunit --colors=never"
        elif (vendor_bin / "phpunit.bat").exists():
            return ".\\vendor\\bin\\phpunit.bat --colors=never"
        return "phpunit --colors=never"

    def get_code_slice(self, file_path: Path, target_line: int, window: int = 15) -> Dict[str, Any]:
        if not file_path.exists():
            return {"error": f"文件不存在: {file_path}"}

        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()

        total_lines = len(lines)
        imports = []

        for line in lines:
            stripped = line.strip()
            if stripped.startswith("namespace ") or stripped.startswith("use "):
                imports.append(stripped)

        start_line = max(1, target_line - window)
        end_line = min(total_lines, target_line + window)

        sliced_raw = lines[start_line - 1 : end_line]
        sliced_code = []
        for idx, line_text in enumerate(sliced_raw, start=start_line):
            marker = "👉 " if idx == target_line else "   "
            sliced_code.append(f"{marker}{idx:4d} | {line_text.rstrip()}")

        token_saving = max(0, round((1 - len(sliced_raw) / max(1, total_lines)) * 100, 1))
        return {
            "total_lines": total_lines,
            "slice_range": [start_line, end_line],
            "imports": imports,
            "sliced_code": "\n".join(sliced_code),
            "token_saving_percent": f"{token_saving}%",
        }

    def validate_syntax(self, file_path: str, code_content: str) -> Tuple[bool, str]:
        check_content = code_content.strip()
        if not check_content.startswith("<?php") and not check_content.startswith("<?"):
            check_content = "<?php\n" + check_content

        with tempfile.NamedTemporaryFile(suffix=".php", mode="w", delete=False, encoding="utf-8") as f:
            f.write(check_content)
            tmp_path = f.name

        try:
            res = subprocess.run(["php", "-l", tmp_path], capture_output=True, text=True, timeout=5)
            if res.returncode == 0:
                return True, ""
            err_msg = (res.stdout or res.stderr).replace(tmp_path, file_path).strip()
            return False, f"PHP Lint Error: {err_msg}"
        except FileNotFoundError:
            if check_content.count("{") != check_content.count("}"):
                return False, "PHP 基础校验失败: 花括号 {} 不闭合"
            return True, "Warning: 未安装 PHP CLI，跳过 php -l 检查"
        except Exception as e:
            return True, f"Warning: PHP lint error: {e}"
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def clean_format_code(self, raw_code: str) -> str:
        code = raw_code.replace("Ġ", " ").replace("Ċ", "\n").replace("ĉ", "\t").strip()
        code_match = re.search(r"```(?:php)?\s*(.*?)\s*```", code, re.DOTALL)
        if code_match:
            code = code_match.group(1).strip()

        # 确保包含 <?php 标签
        if not code.startswith("<?php") and not code.startswith("<?"):
            code = "<?php\n" + code
        return code
