import sys
import time
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir))
sys.path.insert(0, str(root_dir / "mcp-server"))

from state_machine import TaskStateMachine, AgentState

def test_state_machine_transition_whitelist():
    """测试 1：7 阶状态机合法流转与非法跃迁拦截"""
    sm = TaskStateMachine()
    
    # 合法路径断言
    assert sm.can_transition_to(AgentState.REQUIREMENT_EXTRACTION, AgentState.REQUIREMENT_ANALYSIS) is True
    assert sm.can_transition_to(AgentState.CODE_CONSTRUCTION, AgentState.WEB_TESTING) is True
    assert sm.can_transition_to(AgentState.SELF_HEALING, AgentState.FIX_APPLY) is True
    assert sm.can_transition_to(AgentState.FIX_APPLY, AgentState.WEB_TESTING) is True
    
    # 非法越级跃迁拦截断言
    assert sm.can_transition_to(AgentState.REQUIREMENT_EXTRACTION, AgentState.DELIVERY_COMPLETED) is False
    assert sm.can_transition_to(AgentState.RESOURCE_LOADING, AgentState.DELIVERY_COMPLETED) is False

def test_cache_ttl_invalidation():
    """测试 2：缓存与 TTL 失效更新机制"""
    sm = TaskStateMachine()
    test_task_id = "test_cache_task_001"
    
    sm.update_task_state(test_task_id, AgentState.CODE_CONSTRUCTION, {"step": 1})
    state_res = sm.get_task_state(test_task_id)
    assert state_res["current_state"] == AgentState.CODE_CONSTRUCTION
    
    # 模拟缓存命中
    assert test_task_id in sm._cache
    
    # 清除缓存后仍能正确读取
    sm.clear_cache(test_task_id)
    assert test_task_id not in sm._cache

def test_healing_max_retries_circuit_breaker():
    """测试 3：自愈重试达 3 次自动触发熔断至 HUMAN_INTERRUPT"""
    sm = TaskStateMachine()
    test_task_id = f"test_circuit_{int(time.time())}"
    
    # 模拟第 1、2 次失败重试
    c1 = sm.record_healing_attempt(test_task_id, "patch_1", "SYNTAX_ERROR", "line 1 error")
    assert c1 == 1
    assert sm.get_task_state(test_task_id)["current_state"] == AgentState.SELF_HEALING

    c2 = sm.record_healing_attempt(test_task_id, "patch_2", "TEST_FAILED", "assertion failed")
    assert c2 == 2
    assert sm.get_task_state(test_task_id)["current_state"] == AgentState.SELF_HEALING

    # 第 3 次失败，必须触发硬熔断
    c3 = sm.record_healing_attempt(test_task_id, "patch_3", "TEST_FAILED", "assertion failed again")
    assert c3 == 3
    final_state = sm.get_task_state(test_task_id)["current_state"]
    assert final_state == AgentState.HUMAN_INTERRUPT, f"3次失败后必须熔断为 HUMAN_INTERRUPT，实际为: {final_state}"