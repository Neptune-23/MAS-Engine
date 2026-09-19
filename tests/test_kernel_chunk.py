import sys
import tempfile
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir))

from kernel.chunk import ActionChunk, ActionPrimitive, ActionType, ChunkStatus
from kernel.runner import ActionChunkRunner


def test_action_chunk_continuous_execution():
    """测试 1：动作块一次性批处理完成文件写入与切片"""
    runner = ActionChunkRunner()

    with tempfile.TemporaryDirectory() as tmp_dir:
        sandbox = Path(tmp_dir)

        chunk = ActionChunk(
            chunk_id="chk_001",
            intent="构建并切片",
            primitives=[
                ActionPrimitive(
                    action_type=ActionType.WRITE_FILE,
                    target_file="app.py",
                    payload={"content": "def add(a, b):\n    return a + b\n"},
                    description="写入核心算法",
                ),
                ActionPrimitive(
                    action_type=ActionType.READ_SLICE,
                    target_file="app.py",
                    payload={"target_line": 2},
                    description="切片验证",
                ),
            ],
        )

        result = runner.execute(chunk, sandbox)
        assert result.status == ChunkStatus.COMPLETED
        assert result.executed_count == 2
        assert (sandbox / "app.py").exists()


def test_action_chunk_barrier_interception():
    """测试 2：动作块遇到语法破损时，物理门禁即刻切断后续动作，避免雪崩"""
    runner = ActionChunkRunner()

    with tempfile.TemporaryDirectory() as tmp_dir:
        sandbox = Path(tmp_dir)

        chunk = ActionChunk(
            chunk_id="chk_002",
            intent="异常动作块",
            primitives=[
                ActionPrimitive(
                    action_type=ActionType.WRITE_FILE,
                    target_file="broken.py",
                    payload={"content": "def broken_syntax(\n"},  # 故意破损语法
                    description="写入破损代码",
                ),
                ActionPrimitive(
                    action_type=ActionType.WRITE_FILE,
                    target_file="should_not_run.py",
                    payload={"content": "print('never run')"},
                    description="不该执行的后续步骤",
                ),
            ],
        )

        result = runner.execute(chunk, sandbox)
        # 验证门禁触发，且后续操作被物理阻断
        assert result.status == ChunkStatus.BARRIER_TRIGGERED
        assert result.executed_count == 1
        assert not (sandbox / "should_not_run.py").exists()
