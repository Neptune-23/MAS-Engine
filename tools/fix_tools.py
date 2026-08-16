import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

def batch_fix_console_logs_impl(file_paths: list, dry_run: bool = True) -> str:
    """批量修复 console.log 的实现"""
    if not file_paths:
        return "❌ 错误：文件列表为空"

    results = []
    total_files = len(file_paths)
    fixed_count = 0
    skipped_count = 0

    def fix_console_in_file(file_path):
        path = Path(file_path)
        if not path.exists():
            return {"file": str(path), "status": "skipped", "reason": "文件不存在"}

        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        if "console.log" not in content:
            return {"file": str(path), "status": "skipped", "reason": "无 console.log"}

        lines = content.split('\n')
        new_lines = []
        modified = False
        for line in lines:
            if 'console.log' in line and 'import.meta.env' not in line:
                stripped = line.lstrip()
                indent = line[:len(line)-len(stripped)]
                if stripped.startswith('console.log'):
                    new_line = indent + 'if (import.meta.env.MODE !== "production") {\n' + \
                               indent + '    ' + stripped + '\n' + \
                               indent + '}'
                    new_lines.append(new_line)
                    modified = True
                else:
                    new_lines.append(line)
            else:
                new_lines.append(line)

        if not modified:
            return {"file": str(path), "status": "skipped", "reason": "未找到可修复的 console.log"}

        new_content = '\n'.join(new_lines)

        if dry_run:
            return {"file": str(path), "status": "preview", "diff": new_content[:500] + "..."}
        else:
            with open(path, "w", encoding="utf-8") as f:
                f.write(new_content)
            return {"file": str(path), "status": "fixed"}

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(fix_console_in_file, fp): fp for fp in file_paths}
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            if result["status"] == "fixed":
                fixed_count += 1
            elif result["status"] == "skipped":
                skipped_count += 1

    report = f"📊 批量修复完成。总文件数: {total_files}，已修复: {fixed_count}，跳过: {skipped_count}\n"
    if dry_run:
        report += "⚠️ 当前为预览模式（dry_run=True），未实际修改文件。如需执行，请设置 dry_run=False。\n"
    report += "详细结果：\n"
    for r in results:
        if r["status"] == "fixed":
            report += f"  ✅ {r['file']}\n"
        elif r["status"] == "skipped":
            report += f"  ⏭️ {r['file']}（{r.get('reason', '')}）\n"
        elif r["status"] == "preview":
            report += f"  👁️ {r['file']}（预览修改）\n"
    return report


def batch_fix_backend_issues_impl(file_paths: list, dry_run: bool = True) -> str:
    """批量修复后端问题的实现"""
    if not file_paths:
        return "❌ 错误：文件列表为空"

    results = []
    for file_path in file_paths:
        path = Path(file_path)
        if not path.exists():
            results.append(f"⏭️ {path} 文件不存在")
            continue

        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        modified = False

        if "controller" in str(path).lower():
            if "echo " in content or "dump(" in content:
                lines = content.split('\n')
                new_lines = []
                for line in lines:
                    if "echo " in line or "dump(" in line:
                        new_lines.append("        return $this->success('操作成功'); // 原 echo/dump 已替换")
                        modified = True
                    else:
                        new_lines.append(line)
                content = '\n'.join(new_lines)

        if "die" in content or "exit" in content:
            lines = content.split('\n')
            new_lines = []
            for line in lines:
                if "die" in line or "exit" in line:
                    new_lines.append("// " + line + " // 已注释 die/exit")
                    modified = True
                else:
                    new_lines.append(line)
            content = '\n'.join(new_lines)

        if "password" in content.lower() and "env(" not in content:
            lines = content.split('\n')
            new_lines = []
            for line in lines:
                if "password" in line.lower() and "env" not in line:
                    new_lines.append(line + " // TODO: 将硬编码密码移至 .env")
                    modified = True
                else:
                    new_lines.append(line)
            content = '\n'.join(new_lines)

        if not modified:
            results.append(f"⏭️ {path} 无需修改")
            continue

        if not dry_run:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            results.append(f"✅ {path} 已修复")
        else:
            results.append(f"👁️ {path} 预览修改（未实际修改）")

    report = f"📊 后端批量修复完成。\n" + "\n".join(results)
    if dry_run:
        report += "\n⚠️ 预览模式，未实际修改。设置 dry_run=False 执行修复。"
    return report