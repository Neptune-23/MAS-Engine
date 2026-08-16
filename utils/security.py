from functools import wraps
from pathlib import Path

def validate_path(func):
    """装饰器：自动校验工具中的 project_path 参数是否安全"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        import inspect
        from server import BASE_DIR
        project_path = kwargs.get("project_path")
        if project_path is None:
            sig = inspect.signature(func)
            param_names = list(sig.parameters.keys())
            if "project_path" in param_names:
                idx = param_names.index("project_path")
                if idx < len(args):
                    project_path = args[idx]
        
        if project_path:
            if not _validate_project_path(project_path):
                return f"❌ 安全拦截：路径 {project_path} 被系统保护，禁止操作。"
        
        return func(*args, **kwargs)
    return wrapper

def _validate_project_path(project_path: str) -> bool:
    """内部函数：检查路径是否安全（禁止操作系统目录）"""
    from server import BASE_DIR
    path = Path(project_path).resolve()
    forbidden = [
        BASE_DIR / "mcp-server",
        BASE_DIR / "assets",
        BASE_DIR / "references",
        BASE_DIR / "skills",
        BASE_DIR / "logs",
        BASE_DIR / ".venv"
    ]
    for f in forbidden:
        if path == f or f in path.parents:
            return False
    return True