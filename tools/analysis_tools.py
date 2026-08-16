import json
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
        "build.gradle": {"language": "Java", "package_manager": "gradle", "build_tool": "gradle build"},
        "package.json": {"language": "Node.js", "package_manager": "npm", "build_tool": "npm run build"},
        "composer.json": {"language": "PHP", "package_manager": "composer", "build_tool": "composer install"},
        "requirements.txt": {"language": "Python", "package_manager": "pip", "build_tool": "pip install -r requirements.txt"},
        "pyproject.toml": {"language": "Python", "package_manager": "poetry", "build_tool": "poetry install"},
    }

    fingerprint = {
        "language": None,
        "package_manager": None,
        "build_tool": None,
        "framework": None,
        "config_files": [],
        "entry_files": [],
        "project_type": "unknown"
    }

    for file, info in FINGERPRINT_RULES.items():
        if (path / file).exists():
            fingerprint["language"] = info["language"]
            fingerprint["package_manager"] = info["package_manager"]
            fingerprint["build_tool"] = info["build_tool"]
            fingerprint["config_files"].append(file)

    for entry in ["main.go", "main.rs", "src/main.rs", "index.js", "src/index.js", "app.py", "main.py", "index.php", "public/index.php"]:
        if (path / entry).exists():
            fingerprint["entry_files"].append(entry)

    if fingerprint["language"] == "Node.js" and fingerprint["entry_files"]:
        fingerprint["project_type"] = "web_app"
    elif fingerprint["language"] == "Python" and "app.py" in fingerprint["entry_files"]:
        fingerprint["project_type"] = "web_app"
    elif fingerprint["language"] == "Go" and "main.go" in fingerprint["entry_files"]:
        fingerprint["project_type"] = "cli_app"

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
            run_steps = ["poetry run python main.py" if "main.py" in entry_files else "poetry run python app.py"]
        else:
            build_steps = ["pip install -r requirements.txt"]
            test_steps = ["pytest"]
            run_steps = ["python main.py" if "main.py" in entry_files else "python app.py"]
    elif language == "PHP":
        build_steps = ["composer install"]
        test_steps = ["composer test"]
        run_steps = ["php -S localhost:8000 -t public"]
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
        return json.dumps({
            "error": f"未识别的语言: {language}",
            "suggestion": "请检查项目指纹是否正确"
        }, ensure_ascii=False)

    if not run_steps:
        run_steps = ["未检测到运行命令"]

    return json.dumps({
        "language": language,
        "package_manager": package_manager,
        "build_steps": build_steps,
        "test_steps": test_steps,
        "run_steps": run_steps,
        "estimated_time": "约 30 秒" if len(build_steps) > 1 else "约 10 秒"
    }, indent=2, ensure_ascii=False)