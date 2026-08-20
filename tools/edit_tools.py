import os
import json
from utils.security import validate_path

@validate_path
def edit_file(file_path: str, replace_pattern: str, replace_with: str) -> str:
    """
    通用文件编辑工具：在文件中查找并替换字符串。
    不依赖任何语言，纯文本操作。
    """
    try:
        if not os.path.exists(file_path):
            return json.dumps({"success": False, "error": f"文件不存在: {file_path}"})
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        if replace_pattern not in content:
            return json.dumps({"success": False, "error": f"未找到替换模式: {replace_pattern}"})
        new_content = content.replace(replace_pattern, replace_with)
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        return json.dumps({"success": True, "message": "文件编辑成功"})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})