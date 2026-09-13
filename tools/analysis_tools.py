import ast
import json
import os
from pathlib import Path


def analyze_project_structure_impl(project_path: str) -> str:
    """分析项目指纹的实现"""
    path = Path(project_path)
    if not path.exists():
        return json.dumps({"error": f"路径不存在: {project_path}"}, ensure_ascii=False)

    FINGERPRINT_RULES = {
        "go.mod": {"language": "Go", "package_manager": "go mod", "build_tool": "go build"},
        "Cargo.toml": {"language": "Rust", "package_manager": "cargo", "build_tool": "cargo build"},
        "pom.xml": {"language": "Java", "package_manager": "maven", "build_tool": "mvn compile"},
        "build.gradle": {
            "language": "Java",
            "package_manager": "gradle",
            "build_tool": "gradle build",
        },
        "package.json": {
            "language": "Node.js",
            "package_manager": "npm",
            "build_tool": "npm run build",
        },
        "composer.json": {
            "language": "PHP",
            "package_manager": "composer",
            "build_tool": "composer install",
        },
        "requirements.txt": {
            "language": "Python",
            "package_manager": "pip",
            "build_tool": "pip install -r requirements.txt",
        },
        "pyproject.toml": {
            "language": "Python",
            "package_manager": "poetry",
            "build_tool": "poetry install",
        },
    }

    fingerprint = {
        "language": None,
        "package_manager": None,
        "build_tool": None,
        "framework": None,
        "config_files": [],
        "entry_files": [],
        "project_type": "unknown",
        "file_tree": [],
        "test_files": [],
        "source_files": [],
    }

    for file, info in FINGERPRINT_RULES.items():
        if (path / file).exists():
            fingerprint["language"] = info["language"]
            fingerprint["package_manager"] = info["package_manager"]
            fingerprint["build_tool"] = info["build_tool"]
            fingerprint["config_files"].append(file)

    for entry in [
        "main.go",
        "main.rs",
        "src/main.rs",
        "index.js",
        "src/index.js",
        "app.py",
        "main.py",
        "index.php",
        "public/index.php",
    ]:
        if (path / entry).exists():
            fingerprint["entry_files"].append(entry)

    if fingerprint["language"] == "Node.js" and fingerprint["entry_files"]:
        fingerprint["project_type"] = "web_app"
    elif fingerprint["language"] == "Python" and "app.py" in fingerprint["entry_files"]:
        fingerprint["project_type"] = "web_app"
    elif fingerprint["language"] == "Go" and "main.go" in fingerprint["entry_files"]:
        fingerprint["project_type"] = "cli_app"

        # ===== 扫描项目所有 Python 和 PHP 文件，自动排除无关目录 =====
    all_code_files = []
    EXCLUDE_DIRS = {
        "venv",
        "__pycache__",
        ".pytest_cache",
        "vendor",
        "node_modules",
        "storage",
        ".git",
    }

    for ext_pattern in ["**/*.py", "**/*.php"]:
        for file_path in path.glob(ext_pattern):
            if any(part in EXCLUDE_DIRS for part in file_path.parts):
                continue
            rel_path = str(file_path.relative_to(path)).replace("\\", "/")
            all_code_files.append(rel_path)

    test_files = []
    source_files = []
    for f in all_code_files:
        basename = os.path.basename(f)
        # 支持 Python (test_*.py, *_test.py) 和 PHP (*Test.php, test_*.php, *_test.php)
        if (
            basename.startswith("test_")
            or basename.endswith("_test.py")
            or basename.endswith("Test.php")
            or basename.endswith("_test.php")
        ):
            test_files.append(f)
        else:
            source_files.append(f)

    # 如果有 composer.json 但没识别出语言，自动标记为 PHP
    if (path / "composer.json").exists() or any(f.endswith(".php") for f in all_code_files):
        fingerprint["language"] = "PHP"
        fingerprint["package_manager"] = "composer"
        fingerprint["build_tool"] = "composer install"

    fingerprint["file_tree"] = all_code_files
    fingerprint["test_files"] = test_files
    fingerprint["source_files"] = source_files

    if not fingerprint["config_files"]:
        fingerprint["error"] = "未识别到任何已知的项目指纹文件"

    return json.dumps(fingerprint, indent=2, ensure_ascii=False)


def infer_build_steps_impl(fingerprint_json: str) -> str:
    """推理构建步骤的实现"""
    try:
        fingerprint = json.loads(fingerprint_json)
    except json.JSONDecodeError:
        return json.dumps({"error": "无效的指纹 JSON"}, ensure_ascii=False)

    if "error" in fingerprint:
        return json.dumps({"error": fingerprint["error"]}, ensure_ascii=False)

    language = fingerprint.get("language")
    package_manager = fingerprint.get("package_manager")
    entry_files = fingerprint.get("entry_files", [])

    build_steps = []
    test_steps = []
    run_steps = []

    if language == "Rust":
        build_steps = ["cargo build"]
        test_steps = ["cargo test"]
        run_steps = ["cargo run"]
    elif language == "Go":
        build_steps = ["go build -o app"]
        test_steps = ["go test ./..."]
        run_steps = ["./app"] if any("main.go" in f for f in entry_files) else ["go run main.go"]
    elif language == "Node.js":
        build_steps = ["npm install", "npm run build"]
        test_steps = ["npm test"]
        run_steps = ["npm start"]
    elif language == "Python":
        if package_manager == "poetry":
            build_steps = ["poetry install"]
            test_steps = ["poetry run pytest"]
            run_steps = [
                "poetry run python main.py"
                if "main.py" in entry_files
                else "poetry run python app.py"
            ]
        else:
            build_steps = ["pip install -r requirements.txt"]
            test_steps = ["pytest"]
            run_steps = ["python main.py" if "main.py" in entry_files else "python app.py"]
    elif language == "PHP":
        build_steps = ["composer install --no-interaction"]
        test_steps = ["vendor/bin/phpunit --colors=never"]
        run_steps = [
            "php -S 0.0.0.0:8000 -t public"
            if any("public" in f for f in entry_files)
            else "php -S 0.0.0.0:8000"
        ]
    elif language == "Java":
        if package_manager == "maven":
            build_steps = ["mvn compile"]
            test_steps = ["mvn test"]
            run_steps = ["mvn exec:java -Dexec.mainClass=Main"]
        elif package_manager == "gradle":
            build_steps = ["gradle build"]
            test_steps = ["gradle test"]
            run_steps = ["gradle run"]
        else:
            build_steps = ["javac Main.java"]
            test_steps = ["未检测到测试配置"]
            run_steps = ["java Main"]
    else:
        return json.dumps(
            {"error": f"未识别的语言: {language}", "suggestion": "请检查项目指纹是否正确"},
            ensure_ascii=False,
        )

    if not run_steps:
        run_steps = ["未检测到运行命令"]

    return json.dumps(
        {
            "language": language,
            "package_manager": package_manager,
            "build_steps": build_steps,
            "test_steps": test_steps,
            "run_steps": run_steps,
            "estimated_time": "约 30 秒" if len(build_steps) > 1 else "约 10 秒",
        },
        indent=2,
        ensure_ascii=False,
    )


# ============================================================
# 3. 代码精准切片引擎（AST + 行号窗口定位，大幅降低 Token）
# ============================================================
def get_code_slice_impl(
    file_path: str, target_line: int = None, context_window: int = 15, symbol_name: str = None
) -> str:
    """
    根据行号或符号名称进行精准代码切片，提取目标函数块及依赖，降低 60%-80% 的 Token 消耗。
    """
    path = Path(file_path)
    if not path.exists():
        return json.dumps({"error": f"文件不存在: {file_path}"}, ensure_ascii=False)

    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
    except Exception as e:
        return json.dumps({"error": f"读取文件失败: {e}"}, ensure_ascii=False)

    total_lines = len(lines)
    if total_lines == 0:
        return json.dumps({"error": "文件内容为空"}, ensure_ascii=False)

    ext = path.suffix.lower()
    content = "".join(lines)

    enclosing_symbol = None
    start_line = 1
    end_line = total_lines
    imports = []

    # 1. 针对 Python 文件：使用 AST 提取函数/类块与顶级 Imports
    if ext == ".py":
        try:
            tree = ast.parse(content)

            # 提取所有顶级 import（提供上下文依赖）
            for node in tree.body:
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    import_line = ast.get_source_segment(content, node)
                    if import_line:
                        imports.append(import_line)

            # 按 target_line 定位包含该行号的最深函数或类
            if target_line is not None:
                matched_node = None
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                        if hasattr(node, "lineno") and hasattr(node, "end_lineno"):
                            if node.lineno <= target_line <= node.end_lineno:
                                matched_node = node

                if matched_node:
                    start_line = max(1, matched_node.lineno)
                    end_line = min(total_lines, matched_node.end_lineno)
                    node_type = "class" if isinstance(matched_node, ast.ClassDef) else "function"
                    enclosing_symbol = f"{node_type} {matched_node.name}"

            # 按 symbol_name 定位
            elif symbol_name:
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                        if node.name == symbol_name:
                            start_line = max(1, node.lineno)
                            end_line = min(total_lines, node.end_lineno)
                            node_type = "class" if isinstance(node, ast.ClassDef) else "function"
                            enclosing_symbol = f"{node_type} {node.name}"
                            break

        except SyntaxError:
            pass  # 若存在语法错误无法构建 AST，自动降级为滑动窗口切片

    # 1.5 针对 PHP 文件：提取 namespace 和 use 依赖
    elif ext == ".php":
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("namespace ") or stripped.startswith("use "):
                imports.append(stripped)

    # 2. 兜底策略：非 Python 或未命中独立函数，使用目标行前后滑动窗口
    if enclosing_symbol is None and target_line is not None:
        start_line = max(1, target_line - context_window)
        end_line = min(total_lines, target_line + context_window)
        enclosing_symbol = f"window_lines_{start_line}_{end_line}"

    # 3. 构建带行号标注的切片代码（精准标出报错行 👉）
    sliced_raw_lines = lines[start_line - 1 : end_line]
    sliced_code_with_lineno = []
    for idx, line_text in enumerate(sliced_raw_lines, start=start_line):
        marker = "👉 " if (target_line and idx == target_line) else "   "
        sliced_code_with_lineno.append(f"{marker}{idx:4d} | {line_text.rstrip()}")

    token_saving = max(0, round((1 - len(sliced_raw_lines) / max(1, total_lines)) * 100, 1))

    result = {
        "file_path": str(path),
        "total_lines": total_lines,
        "slice_range": [start_line, end_line],
        "enclosing_symbol": enclosing_symbol,
        "imports": imports,
        "sliced_code": "\n".join(sliced_code_with_lineno),
        "raw_slice": "".join(sliced_raw_lines),
        "token_saving_percent": f"{token_saving}%",
    }

    return json.dumps(result, indent=2, ensure_ascii=False)
