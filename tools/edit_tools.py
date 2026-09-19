
from utils.security import validate_path


@validate_path
def edit_file(
    file_path: str = None,
    target_file: str = None,
    old_string: str = None,
    new_string: str = None,
    replace_pattern: str = None,
    replace_with: str = None,
    **kwargs,
) -> dict:
  """编辑文件内容：兼容支持 old_string/new_string 与 replace_pattern/replace_with 两套入参"""
  # 兼容文件路径入参
  path_to_edit = file_path or target_file
  if not path_to_edit:
    return {"success": False, "error": "缺少目标文件路径 (file_path/target_file)"}

  # 兼容查找/替换内容入参
  find_str = old_string if old_string is not None else replace_pattern
  repl_str = new_string if new_string is not None else replace_with

  if find_str is None or repl_str is None:
    return {
        "success": False,
        "error": (
            "缺少替换参数，需提供 old_string/new_string 或"
            " replace_pattern/replace_with"
        ),
    }

  from pathlib import Path

  target = Path(path_to_edit)
  if not target.exists():
    return {"success": False, "error": f"文件不存在: {path_to_edit}"}

  try:
    content = target.read_text(encoding="utf-8")
    if find_str not in content:
      return {
          "success": False,
          "error": f"在 {path_to_edit} 中未找到指定的待替换文本",
      }

    new_content = content.replace(find_str, repl_str, 1)
    target.write_text(new_content, encoding="utf-8")
    return {"success": True, "message": f"成功更新 {path_to_edit}"}
  except Exception as e:
    return {"success": False, "error": f"文件编辑失败: {str(e)}"}
