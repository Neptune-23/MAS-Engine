import pytest


def test_mcp_server_import_and_prerequisites():
  """冒烟测试：验证核心包导出完整且主服务入口能被正常导入"""
  try:
    from kernel.evolution import (
        EvolvedSkillRegistry,
        SkillSynthesizer,
        TrajectoryMiner,
    )

    assert EvolvedSkillRegistry is not None
    assert SkillSynthesizer is not None
    assert TrajectoryMiner is not None
  except ImportError as e:
    pytest.fail(f"kernel.evolution 导入失败，请检查 __init__.py: {e}")

  try:
    from mcp_server import server

    assert hasattr(server, "main")
  except Exception as e:
    pytest.fail(f"mcp_server.server 导入失败: {e}")
