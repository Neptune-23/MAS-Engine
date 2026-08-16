import subprocess
import json
from pathlib import Path

def scan_code_batch_impl(project_path: str, offset: int = 0, limit: int = 20) -> str:
    """分批扫描前端代码的实现"""
    path = Path(project_path)
    if not path.exists():
        return f"❌ 错误：路径 {project_path} 不存在"

    target_dirs = ["pages", "sheep", "components"]
    all_files = []

    for dir_name in target_dirs:
        target_dir = path / dir_name
        if target_dir.exists():
            for ext in ["*.vue", "*.js"]:
                all_files.extend(target_dir.rglob(ext))

    all_files = sorted(set(all_files), key=lambda p: str(p))
    all_files = [f for f in all_files if "node_modules" not in str(f)]

    total = len(all_files)
    batch_files = all_files[offset:offset + limit]

    if not batch_files:
        return f"✅ 所有文件已检查完毕！共扫描了 {total} 个文件。"

    issues = []
    for file in batch_files:
        with open(file, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
            lines = content.split("\n")

            if "console.log" in content and "import.meta.env" not in content:
                for i, line in enumerate(lines, 1):
                    if "console.log" in line:
                        issues.append(f"  📍 {file.relative_to(path)}: 第 {i} 行 - console.log 未加环境判断")
                        break

            if "data()" in content and "<script setup" not in content:
                issues.append(f"  📍 {file.relative_to(path)} - 使用了 data() 选项式写法")

            if file.suffix == ".vue":
                name = file.stem
                if name.lower() == name and "_" not in name and "-" not in name:
                    issues.append(f"  📍 {file.relative_to(path)} - 组件名 '{name}' 是单单词")

    next_offset = offset + limit
    has_more = total > next_offset

    report = f"📊 扫描进度：{next_offset if next_offset < total else total}/{total} 个文件\n"
    if issues:
        report += f"🚨 本批次发现 {len(issues)} 个问题：\n" + "\n".join(issues)
    else:
        report += "✅ 本批次未发现问题。"

    if has_more:
        report += f"\n\n🔄 还有剩余文件待检查，请继续调用 scan_code_batch，offset={next_offset}, limit={limit}"
    else:
        report += "\n\n🎉 全部扫描完成！"

    return report


def scan_backend_batch_impl(project_path: str, offset: int = 0, limit: int = 20) -> str:
    """分批扫描后端代码的实现"""
    path = Path(project_path)
    if not path.exists():
        return f"❌ 错误：路径 {project_path} 不存在"

    target_dirs = ["app", "application"]
    all_files = []

    for dir_name in target_dirs:
        target_dir = path / dir_name
        if target_dir.exists():
            all_files.extend(target_dir.rglob("*.php"))

    all_files = [f for f in all_files if "vendor" not in str(f)]
    all_files = sorted(set(all_files), key=lambda p: str(p))

    total = len(all_files)
    batch_files = all_files[offset:offset + limit]

    if not batch_files:
        return f"✅ 所有文件已检查完毕！共扫描了 {total} 个 PHP 文件。"

    issues = []
    for file in batch_files:
        with open(file, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
            lines = content.split("\n")

            if "password" in content.lower() and "env(" not in content and "getenv(" not in content:
                for i, line in enumerate(lines, 1):
                    if "password" in line.lower() and "env" not in line:
                        issues.append(f"  📍 {file.relative_to(path)}: 第 {i} 行 - 疑似硬编码密码/密钥（建议使用 .env）")
                        break

            if "Db::query" in content or "Db::execute" in content:
                if "::query" in content and "?" not in content and ":" not in content:
                    issues.append(f"  📍 {file.relative_to(path)} - 使用了 Db::query 但疑似未使用参数绑定")

            if "echo " in content or "dump(" in content or "var_dump(" in content:
                if "controller" in str(file).lower() or "api" in str(file).lower():
                    issues.append(f"  📍 {file.relative_to(path)} - 控制器/API 中不应使用 echo/dump/var_dump")

            if "input(" in content and "validate" not in content:
                issues.append(f"  📍 {file.relative_to(path)} - 使用了 input() 但未发现验证器")

            if "die" in content or "exit" in content:
                if "controller" in str(file).lower():
                    issues.append(f"  📍 {file.relative_to(path)} - 控制器中不应使用 die/exit")

    next_offset = offset + limit
    has_more = total > next_offset

    report = f"📊 后端扫描进度：{next_offset if next_offset < total else total}/{total} 个 PHP 文件\n"
    if issues:
        report += f"🚨 本批次发现 {len(issues)} 个问题：\n" + "\n".join(issues)
    else:
        report += "✅ 本批次未发现问题。"

    if has_more:
        report += f"\n\n🔄 还有剩余文件待检查，请继续调用 scan_backend_batch，offset={next_offset}, limit={limit}"
    else:
        report += "\n\n🎉 全部扫描完成！"

    return report


def scan_admin_batch_impl(project_path: str, offset: int = 0, limit: int = 20) -> str:
    """分批扫描后台代码的实现"""
    path = Path(project_path)
    if not path.exists():
        return f"❌ 错误：路径 {project_path} 不存在"

    target_dirs = ["application", "addons"]
    all_files = []

    for dir_name in target_dirs:
        target_dir = path / dir_name
        if target_dir.exists():
            all_files.extend(target_dir.rglob("*.php"))

    all_files = [f for f in all_files if "vendor" not in str(f) and "runtime" not in str(f)]
    all_files = sorted(set(all_files), key=lambda p: str(p))

    total = len(all_files)
    batch_files = all_files[offset:offset + limit]

    if not batch_files:
        return f"✅ 所有文件已检查完毕！共扫描了 {total} 个 PHP 文件。"

    issues = []
    for file in batch_files:
        with open(file, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
            lines = content.split("\n")

            if "addons" in str(file) and "info.ini" not in str(content):
                plugin_dir = file.parent
                if not (plugin_dir / "info.ini").exists():
                    issues.append(f"  📍 {file.relative_to(path)} - 插件目录缺少 info.ini 文件")

            if "==" in content and ("admin" in content or "id" in content):
                for i, line in enumerate(lines, 1):
                    if "==" in line and ("admin" in line or "is_admin" in line or "role" in line):
                        if "config" not in line and "auth" not in line:
                            issues.append(f"  📍 {file.relative_to(path)}: 第 {i} 行 - 疑似硬编码权限判断")
                            break

            if "Db::query" in content or "Db::execute" in content:
                if "bind" not in content and "?" not in content:
                    issues.append(f"  📍 {file.relative_to(path)} - 使用了 Db::query 但疑似未使用参数绑定")

            if "src=" in content or "href=" in content:
                if "__PUBLIC__" not in content and "asset(" not in content and "cdn" not in content:
                    issues.append(f"  📍 {file.relative_to(path)} - 前端资源路径未使用 __PUBLIC__ 或 asset()")

    next_offset = offset + limit
    has_more = total > next_offset

    report = f"📊 后台扫描进度：{next_offset if next_offset < total else total}/{total} 个 PHP 文件\n"
    if issues:
        report += f"🚨 本批次发现 {len(issues)} 个问题：\n" + "\n".join(issues)
    else:
        report += "✅ 本批次未发现问题。"

    if has_more:
        report += f"\n\n🔄 还有剩余文件待检查，请继续调用 scan_admin_batch，offset={next_offset}, limit={limit}"
    else:
        report += "\n\n🎉 全部扫描完成！"

    return report


def run_code_check_impl(project_path: str) -> str:
    """代码规范检查的实现"""
    path = Path(project_path)
    if not path.exists():
        return f"❌ 错误：路径 {project_path} 不存在"

    package_json = path / "package.json"
    if not package_json.exists():
        return "❌ 错误：该目录中没有 package.json，不是 Node.js 项目"

    node_modules = path / "node_modules"
    if not node_modules.exists():
        try:
            subprocess.run(["npm", "install"], cwd=project_path, shell=False, timeout=300)
        except Exception as e:
            return f"⚠️ 依赖安装失败，请手动执行 npm install。错误：{str(e)}"

    try:
        result = subprocess.run(
            ["npx", "prettier", "--check", "\"{pages,sheep,components}/**/*.{js,json,vue,html}\""],
            capture_output=True, text=True, cwd=project_path, shell=True, timeout=60
        )
        if result.returncode == 0:
            return f"✅ 代码规范检查通过！\n{result.stdout}"
        else:
            return f"❌ 代码存在格式问题（Prettier）：\n{result.stdout}\n{result.stderr}"
    except Exception as e:
        return f"❌ 执行检查时出错：{str(e)}"


def check_code_quality_impl(project_path: str, auto_fix: bool = False) -> str:
    """深度代码质量检查的实现"""
    path = Path(project_path)
    if not path.exists():
        return f"❌ 错误：路径 {project_path} 不存在"

    vue_files = list(path.rglob("*.vue"))
    js_files = list(path.rglob("*.js"))
    all_files = vue_files + js_files

    issues = []

    for file in all_files:
        if "node_modules" in str(file) or "dist" in str(file):
            continue

        with open(file, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
            lines = content.split("\n")

            for i, line in enumerate(lines, 1):
                if "console.log" in line and "import.meta.env" not in content:
                    issues.append(f"  📍 {file.relative_to(path)}: 第 {i} 行 - console.log 未加环境判断")
                    break

            if "data()" in content and "script setup" not in content:
                issues.append(f"  📍 {file.relative_to(path)} - 使用了 data() 选项式写法")

            if file.name.endswith(".vue"):
                name = file.stem
                if name.lower() == name:
                    issues.append(f"  📍 {file.relative_to(path)} - 组件名 '{name}' 是单单词")

    try:
        prettier_result = subprocess.run(
            ["npx", "prettier", "--check", "\"{pages,sheep,components}/**/*.{js,json,vue,html}\""],
            capture_output=True, text=True, cwd=project_path, shell=True, timeout=120
        )
        if prettier_result.returncode != 0:
            issues.append(f"\n📦 Prettier 格式问题：\n{prettier_result.stdout}")
    except Exception as e:
        issues.append(f"\n⚠️ Prettier 检查失败：{str(e)}")

    if not issues:
        return "✅ 代码质量检查通过！未发现红线违规或格式问题。"

    report = "🚨 代码质量检查发现问题：\n\n" + "\n".join(issues)

    if auto_fix:
        try:
            subprocess.run(
                ["npx", "prettier", "--write", "\"{pages,sheep,components}/**/*.{js,json,vue,html}\""],
                capture_output=True, text=True, cwd=project_path, shell=True, timeout=120
            )
            report += f"\n\n✅ 已自动执行 Prettier 格式化修复。"
        except Exception as e:
            report += f"\n\n❌ 自动修复失败：{str(e)}"

    return report