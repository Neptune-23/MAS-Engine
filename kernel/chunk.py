from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class ActionType(str, Enum):
    WRITE_FILE = "write_file"
    READ_SLICE = "read_slice"
    VALIDATE_SYNTAX = "validate_syntax"
    RUN_COMMAND = "run_command"


class ChunkStatus(str, Enum):
    COMPLETED = "completed"
    BARRIER_TRIGGERED = "barrier_triggered"  # 触发物理门禁中断（如单测报错/语法异常）
    FAILED = "failed"


@dataclass
class ActionPrimitive:
    """原子操作原语"""

    action_type: ActionType
    target_file: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)
    description: str = ""


@dataclass
class ActionChunk:
    """自适应动作块（大模型单次推理产出，或由技能库直接合成）"""

    chunk_id: str
    intent: str
    primitives: List[ActionPrimitive]
    stop_barrier: str = "physical_error"  # 遇到物理编译/单测失败即刻安全让渡


@dataclass
class ChunkExecutionResult:
    """动作块执行结果与物理轨迹"""

    chunk_id: str
    status: ChunkStatus
    executed_count: int
    total_count: int
    halt_reason: Optional[str] = None
    step_traces: List[Dict[str, Any]] = field(default_factory=list)
