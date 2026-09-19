import ast
from pathlib import Path
from typing import Optional

from kernel.evolution.miner import InducedPattern


class SkillSynthesizer:
    """程序化技能合成器：将高频成功轨迹泛化编译为确定性 Python 宏脚本"""

    def __init__(self, output_skills_dir: Path = None):
        self.output_skills_dir = Path(output_skills_dir or "kernel/skills")
        self.output_skills_dir.mkdir(parents=True, exist_ok=True)

    def synthesize_skill(self, pattern: InducedPattern) -> Optional[Path]:
        """将模式合成为自洽的 Python 技能脚本"""
        skill_filename = f"auto_skill_{pattern.language}_{pattern.error_signature}.py"
        target_path = self.output_skills_dir / skill_filename

        # 提取关键替换逻辑 (去除标记，只提取核心内容)
        clean_fix = pattern.fixed_code.replace("Ġ", " ").replace("Ċ", "\n").replace("ĉ", "\t").strip()
        code_body = clean_fix.replace("\\", "\\\\").replace('"', '\\"')

        # 生成确定性宏技能源码模板
        synthesized_py = f'''# -*- coding: utf-8 -*-
"""
MAS-RSI 自演化程序化技能: {pattern.pattern_id}
触发特征签名: {pattern.error_signature}
历史聚类验证次数: {pattern.occurrence_count}
"""
import re

SKILL_META = {{
    "pattern_id": "{pattern.pattern_id}",
    "language": "{pattern.language}",
    "error_signature": "{pattern.error_signature}",
    "auto_generated": True
}}

def execute_macro_fix(source_content: str, error_context: dict) -> tuple[bool, str]:
    """
    确定性宏修复逻辑 (0 Token 消耗，直接执行物理修补)
    """
    fixed = """{code_body}"""
    if fixed and fixed != source_content:
        return True, fixed
    return False, source_content
'''

        # 静态语法校验：确保合成的代码本身没有语法破损
        try:
            ast.parse(synthesized_py)
        except SyntaxError:
            return None

        with open(target_path, "w", encoding="utf-8") as f:
            f.write(synthesized_py)

        return target_path
