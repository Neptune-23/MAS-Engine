import sys
from typing import Any, Dict, List

from state_machine import AgentState


# ==========================================
# 1. 角色定义
# ==========================================
class AgentRole:
    ANALYST = "analyst"
    ARCHITECT = "architect"
    DEVELOPER = "developer"
    TESTER = "tester"
    REVIEWER = "reviewer"
    FIXER = "fixer"


# ==========================================
# 2. 状态 + 角色 → 工具白名单（已注入新工具）
# ==========================================
ROLE_TOOL_REGISTRY = {
    AgentState.REQUIREMENT_EXTRACTION: {
        AgentRole.ANALYST: ["search_tools", "get_tool_details", "get_rules"],
        "default": [
            "search_tools",
            "get_tool_details",
            "orchestrate_task",
            "get_next_message",
            "infer_build_steps",
        ],
    },
    AgentState.REQUIREMENT_ANALYSIS: {
        AgentRole.ANALYST: [
            "search_tools",
            "get_tool_details",
            "get_rules",
            "infer_build_steps",
            "get_code_slice",
        ],
        "default": [
            "search_tools",
            "get_tool_details",
            "orchestrate_task",
            "get_next_message",
            "analyze_project_structure",
            "infer_build_steps",
            "get_code_slice",
        ],
    },
    AgentState.RESOURCE_LOADING: {
        AgentRole.ARCHITECT: ["search_tools", "get_tool_details"],
        "default": [
            "search_tools",
            "get_tool_details",
            "orchestrate_task",
            "get_next_message",
            "infer_build_steps",
        ],
    },
    AgentState.CODE_CONSTRUCTION: {
        AgentRole.DEVELOPER: [
            "search_tools",
            "get_tool_details",
            "scan_code_batch",
            "orchestrate_task",
            "get_next_message",
            "analyze_project_structure",
            "get_code_slice",
            "validate_code_syntax",
        ],
        AgentRole.REVIEWER: [
            "search_tools",
            "get_tool_details",
            "scan_code_batch",
            "scan_backend_batch",
            "scan_admin_batch",
            "orchestrate_task",
            "get_next_message",
            "infer_build_steps",
            "get_code_slice",
            "validate_code_syntax",
        ],
        "default": [
            "search_tools",
            "get_tool_details",
            "orchestrate_task",
            "get_next_message",
            "infer_build_steps",
            "get_code_slice",
            "validate_code_syntax",
        ],
    },
    AgentState.WEB_TESTING: {
        AgentRole.TESTER: [
            "search_tools",
            "get_tool_details",
            "run_web_audit",
            "scan_code_batch",
            "get_pipeline_status",
            "orchestrate_task",
            "get_next_message",
            "infer_build_steps",
            "get_code_slice",
        ],
        "default": [
            "search_tools",
            "get_tool_details",
            "run_web_audit",
            "orchestrate_task",
            "get_next_message",
            "infer_build_steps",
            "get_code_slice",
        ],
    },
    AgentState.SELF_HEALING: {
        AgentRole.FIXER: [
            "search_tools",
            "get_tool_details",
            "scan_code_batch",
            "scan_backend_batch",
            "scan_admin_batch",
            "batch_fix_console_logs",
            "batch_fix_backend_issues",
            "run_quality_pipeline",
            "run_backend_pipeline",
            "run_admin_pipeline",
            "get_pipeline_status",
            "run_web_audit",
            "orchestrate_task",
            "get_next_message",
            "infer_build_steps",
            "get_code_slice",  # 新增：代码精准切片
            "validate_code_syntax",  # 新增：静态语法安全校验
        ],
        AgentRole.REVIEWER: [
            "search_tools",
            "get_tool_details",
            "scan_code_batch",
            "scan_backend_batch",
            "scan_admin_batch",
            "get_pipeline_status",
            "orchestrate_task",
            "get_next_message",
            "infer_build_steps",
            "get_code_slice",
            "validate_code_syntax",
        ],
        "default": [
            "search_tools",
            "get_tool_details",
            "scan_code_batch",
            "get_pipeline_status",
            "orchestrate_task",
            "get_next_message",
            "infer_build_steps",
            "get_code_slice",
            "validate_code_syntax",
        ],
    },
    # 【新增补齐】修复落盘状态白名单
    AgentState.FIX_APPLY: {
        AgentRole.FIXER: [
            "search_tools",
            "get_tool_details",
            "batch_fix_console_logs",
            "batch_fix_backend_issues",
            "validate_code_syntax",
            "orchestrate_task",
            "get_next_message",
        ],
        "default": [
            "search_tools",
            "get_tool_details",
            "validate_code_syntax",
            "orchestrate_task",
            "get_next_message",
        ],
    },
    AgentState.DELIVERY_COMPLETED: {"default": []},
    AgentState.HUMAN_INTERRUPT: {
        "default": ["search_tools", "get_tool_details", "get_next_message"]
    },
}


# ==========================================
# 3. 动态调度器
# ==========================================
class DynamicToolDispatcher:
    def __init__(self, all_registered_tools: List[Dict[str, Any]]):
        self.all_registered_tools = all_registered_tools

    def get_active_tools_for_state(
        self, current_state: str, role: str = None
    ) -> List[Dict[str, Any]]:
        """
        根据当前状态和角色返回允许的工具列表。
        如果 role 未指定或不在配置中，使用 'default' 降级。
        """
        state_config = ROLE_TOOL_REGISTRY.get(current_state, {})

        if role and role in state_config:
            allowed_names = state_config[role]
        else:
            allowed_names = state_config.get("default", [])

        active_tools = [
            tool for tool in self.all_registered_tools if tool.get("name") in allowed_names
        ]

        # 关键规范：使用 stderr 输出调试信息，不污染 MCP 的 stdout 通信
        sys.stderr.write(
            f"[Dispatcher] 状态 {current_state}, 角色 {role or 'default'} -> 允许 {len(active_tools)} 个工具\n"
        )
        sys.stderr.flush()
        return active_tools

    def is_tool_allowed(self, current_state: str, tool_name: str, role: str = None) -> bool:
        """检查特定工具在当前状态/角色下是否允许被调用"""
        state_config = ROLE_TOOL_REGISTRY.get(current_state, {})
        if role and role in state_config:
            allowed_names = state_config[role]
        else:
            allowed_names = state_config.get("default", [])
        return tool_name in allowed_names
