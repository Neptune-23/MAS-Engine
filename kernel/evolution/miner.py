import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List


@dataclass
class InducedPattern:
    """从成功轨迹中提炼出的自愈模式"""

    pattern_id: str
    language: str
    error_signature: str
    error_sample: str
    source_slice: str
    fixed_code: str
    occurrence_count: int
    sample_trace_id: str


class TrajectoryMiner:
    """经验轨迹挖掘器：从历史遥测数据中提炼高频成功自愈链"""

    def __init__(self, telemetry_dir: Path = None):
        self.telemetry_dir = Path(telemetry_dir or "data/telemetry")

    @staticmethod
    def extract_error_signature(error_msg: str) -> str:
        """从杂乱的报错信息中提取确定性的结构化指纹 (Error Signature)"""
        if not error_msg:
            return "unknown_error"

        # 匹配标准异常类型 (如 AssertionError, SyntaxError, TypeError, PHP Parse error)
        exc_match = re.search(r"([A-Za-z0-9_]+Error|[A-Za-z0-9_]+Exception|Parse error)", error_msg)
        exc_type = exc_match.group(1) if exc_match else "GenericError"

        # 匹配断言失败特征 (如 assert 120.0 == 80.0)
        assert_match = re.search(r"assert\s+([^\n]+)", error_msg)
        if assert_match:
            # 泛化数字与字符串，保留操作结构
            generalized_assert = re.sub(r"\d+", "N", assert_match.group(1).strip())
            raw_sig = f"{exc_type}::{generalized_assert}"
        else:
            first_line = error_msg.strip().split("\n")[-1][:80]
            generalized_line = re.sub(r"\d+", "N", first_line)
            raw_sig = f"{exc_type}::{generalized_line}"

        return hashlib.md5(raw_sig.encode("utf-8")).hexdigest()[:12]

    def mine_successful_patterns(self, min_frequency: int = 1) -> List[InducedPattern]:
        """扫描所有遥测会话，聚类出能够被程序化固化的高价值自愈模式"""
        if not self.telemetry_dir.exists():
            return []

        clusters: Dict[str, List[Dict[str, Any]]] = {}

        for json_file in self.telemetry_dir.glob("*.json"):
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    session = json.load(f)

                if session.get("final_verdict") != "SUCCESS":
                    continue

                lang = session.get("task_meta", {}).get("language", "python")
                steps = session.get("steps", [])

                # 寻找修好 Bug 的关键步骤
                for step in steps:
                    if step.get("role") == "fixer" and step.get("passed"):
                        err_msg = step.get("error_input", "") or session.get("task_meta", {}).get(
                            "task_description", ""
                        )
                        sig = self.extract_error_signature(err_msg)
                        cluster_key = f"{lang}@@{sig}"

                        if cluster_key not in clusters:
                            clusters[cluster_key] = []

                        clusters[cluster_key].append(
                            {
                                "session_id": session.get("trace_id", json_file.stem),
                                "language": lang,
                                "signature": sig,
                                "error_msg": err_msg,
                                "source_slice": step.get("source_slice", ""),
                                "fixed_code": step.get("response", ""),
                            }
                        )
            except Exception:
                continue

        # 聚类转换为候选模式
        patterns = []
        for key, records in clusters.items():
            if len(records) >= min_frequency:
                representative = records[-1]
                lang, sig = key.split("@@")
                patterns.append(
                    InducedPattern(
                        pattern_id=f"pat_{lang}_{sig}",
                        language=lang,
                        error_signature=sig,
                        error_sample=representative["error_msg"][:200],
                        source_slice=representative["source_slice"],
                        fixed_code=representative["fixed_code"],
                        occurrence_count=len(records),
                        sample_trace_id=representative["session_id"],
                    )
                )

        return patterns
