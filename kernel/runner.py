import subprocess
from pathlib import Path
from typing import Any, Dict

from adapters import BaseLanguageAdapter, detect_adapter
from kernel.chunk import ActionChunk, ActionPrimitive, ActionType, ChunkExecutionResult, ChunkStatus


class ActionChunkRunner:
    """快执行环（Act More）：在内存与物理沙箱中连续链式批处理执行，遇到物理红灯即刻阻断"""

    def __init__(self, default_adapter: BaseLanguageAdapter = None):
        self.default_adapter = default_adapter

    def execute(self, chunk: ActionChunk, sandbox_path: Path) -> ChunkExecutionResult:
        sandbox_path = Path(sandbox_path)
        traces = []
        executed = 0

        for primitive in chunk.primitives:
            executed += 1
            adapter = self.default_adapter or detect_adapter(str(sandbox_path))
            step_result = self._dispatch_primitive(primitive, sandbox_path, adapter)
            traces.append({"primitive": primitive.description or primitive.action_type.value, "result": step_result})

            # 动态物理门禁拦截（Dynamic Barrier Check - 防止盲目批处理雪崩）
            if not step_result.get("success", False):
                return ChunkExecutionResult(
                    chunk_id=chunk.chunk_id,
                    status=ChunkStatus.BARRIER_TRIGGERED,
                    executed_count=executed,
                    total_count=len(chunk.primitives),
                    halt_reason=step_result.get("error", "物理门禁触发中断"),
                    step_traces=traces,
                )

        return ChunkExecutionResult(
            chunk_id=chunk.chunk_id,
            status=ChunkStatus.COMPLETED,
            executed_count=executed,
            total_count=len(chunk.primitives),
            step_traces=traces,
        )

    def _dispatch_primitive(
        self,
        primitive: ActionPrimitive,
        sandbox_path: Path,
        adapter: BaseLanguageAdapter,
    ) -> Dict[str, Any]:
      """原子执行原语"""
      try:
        # ============================================================
        # 1. 统一沙箱越界防御（在任何物理写/读操作前拦截）
        # ============================================================
        target = (sandbox_path / primitive.target_file).resolve()
        sandbox_resolved = sandbox_path.resolve()
        if not str(target).startswith(str(sandbox_resolved)):
          return {
              "success": False,
              "error": (
                  f"安全拦截：目标路径 {primitive.target_file} 超出工作区沙箱边界"
              ),
          }

        # ============================================================
        # 2. WRITE_FILE 分支
        # ============================================================
        if primitive.action_type == ActionType.WRITE_FILE:
          target.parent.mkdir(parents=True, exist_ok=True)
          content = primitive.payload.get("content", "")

          # 写入前先由适配器进行静态语法预检
          is_valid, err = adapter.validate_syntax(
              primitive.target_file, content
          )
          if not is_valid:
            return {"success": False, "error": f"语法门禁拦截: {err}"}

          with open(target, "w", encoding="utf-8") as f:
            f.write(content)
          return {
              "success": True,
              "written_bytes": len(content.encode("utf-8")),
          }

        # ============================================================
        # 3. READ_SLICE 分支
        # ============================================================
        elif primitive.action_type == ActionType.READ_SLICE:
          line = primitive.payload.get("target_line", 1)
          slice_data = adapter.get_code_slice(target, target_line=line)
          return {"success": True, "slice": slice_data}

        # ============================================================
        # 4. RUN_COMMAND 分支
        # ============================================================
        elif primitive.action_type == ActionType.RUN_COMMAND:
          cmd = primitive.payload.get("command", "")
          res = subprocess.run(
              cmd,
              shell=True,
              cwd=str(sandbox_path),
              capture_output=True,
              text=True,
              timeout=15,
          )
          success = res.returncode == 0
          return {
              "success": success,
              "exit_code": res.returncode,
              "stdout": res.stdout[:500],
              "stderr": res.stderr[:500],
          }

        # ============================================================
        # 5. 补齐 VALIDATE_SYNTAX 原语分支（从 payload 取 content 并返回 dict）
        # ============================================================
        elif primitive.action_type == ActionType.VALIDATE_SYNTAX:
          content = primitive.payload.get("content", "")
          if not content and target.exists():
            content = target.read_text(encoding="utf-8", errors="ignore")

          is_valid, msg = adapter.validate_syntax(
              primitive.target_file, content
          )
          if is_valid:
            return {"success": True, "message": msg}
          else:
            return {"success": False, "error": msg}

        return {
            "success": False,
            "error": f"未知动作原语: {primitive.action_type}",
        }

      except Exception as e:
        return {"success": False, "error": str(e)}
