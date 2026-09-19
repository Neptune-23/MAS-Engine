import importlib.util
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

from kernel.evolution.miner import TrajectoryMiner


class EvolvedSkillRegistry:
    """自演化技能注册中心：实现宏技能的动态装配与 0-Token 极速自愈路由"""

    def __init__(self, skills_dir: Path = None):
        self.skills_dir = Path(skills_dir or "kernel/skills")
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        # 映射表: error_signature -> callable_skill_func
        self._loaded_skills: Dict[str, Tuple[Dict[str, Any], Callable]] = {}
        self.reload_skills()

    def reload_skills(self) -> int:
        """热加载 skills/ 目录下所有自动合成的 Python 技能文件"""
        self._loaded_skills.clear()
        count = 0

        for py_file in self.skills_dir.glob("auto_skill_*.py"):
            try:
                module_name = py_file.stem
                spec = importlib.util.spec_from_file_location(module_name, py_file)
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)

                    meta = getattr(mod, "SKILL_META", {})
                    fn = getattr(mod, "execute_macro_fix", None)

                    if meta and callable(fn):
                        sig = meta.get("error_signature")
                        if sig:
                            self._loaded_skills[sig] = (meta, fn)
                            count += 1
            except Exception:
                continue

        return count

    def try_fast_path_fix(
        self, language: str, error_message: str, source_content: str
    ) -> Tuple[bool, str, Optional[str]]:
        """
        RSI 核心：尝试走 0-Token 极速自愈快车道
        返回: (是否命中并成功修复, 修复后的代码, 命中的技能ID)
        """
        sig = TrajectoryMiner.extract_error_signature(error_message)

        if sig in self._loaded_skills:
            meta, skill_func = self._loaded_skills[sig]
            # 校验语言是否匹配
            if meta.get("language", "").lower() == language.lower():
                try:
                    success, fixed_code = skill_func(source_content, {"error": error_message})
                    if success:
                        return True, fixed_code, meta.get("pattern_id")
                except Exception:
                    pass

        return False, source_content, None
