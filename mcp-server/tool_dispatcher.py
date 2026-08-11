import sys
from typing import List, Dict, Any
from state_machine import AgentState


# ==========================================
# 1. 角色定义（新增）
# ==========================================
class AgentRole:
    ANALYST = "analyst"
    ARCHITECT = "architect"
    DEVELOPER = "developer"
    TESTER = "tester"
    REVIEWER = "reviewer"
    FIXER = "fixer"


# ==========================================
# 2. 状态 + 角色 → 工具白名单
# ==========================================
ROLE_TOOL_REGISTRY = {
    AgentState.REQUIREMENT_EXTRACTION: {
        AgentRole.ANALYST: ["search_tools", "get_tool_details", "get_rules"],
        "default": ["search_tools", "get_tool_details", "orchestrate_task", "get_next_message"]
    },
    AgentState.REQUIREMENT_ANALYSIS: {
        AgentRole.ANALYST: ["search_tools", "get_tool_details", "get_rules", "list_templates"],
        "default": ["search_tools", "get_tool_details", "orchestrate_task", "get_next_message"]
    },
    AgentState.RESOURCE_LOADING: {
        AgentRole.ARCHITECT: ["search_tools", "get_tool_details", "list_templates"],
        "default": ["search_tools", "get_tool_details", "list_templates", "orchestrate_task", "get_next_message"]
    },
    AgentState.CODE_CONSTRUCTION: {
        AgentRole.DEVELOPER: [
            "search_tools",
            "get_tool_details",
            "list_templates",
            "create_frontend_project",
            "create_backend_project",
            "create_admin_project",
            "scan_code_batch",
            "orchestrate_task",
            "get_next_message"
        ],
        AgentRole.REVIEWER: [
            "search_tools",
            "get_tool_details",
            "scan_code_batch",
            "scan_backend_batch",
            "scan_admin_batch",
            "orchestrate_task",
            "get_next_message"
        ],
        "default": ["search_tools", "get_tool_details", "list_templates", "orchestrate_task", "get_next_message"]
    },
    AgentState.WEB_TESTING: {
        AgentRole.TESTER: [
            "search_tools",
            "get_tool_details",
            "run_web_audit",
            "scan_code_batch",
            "get_pipeline_status",
            "orchestrate_task",
            "get_next_message"
        ],
        "default": ["search_tools", "get_tool_details", "run_web_audit", "orchestrate_task", "get_next_message"]
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
            "get_next_message"
        ],
        AgentRole.REVIEWER: [
            "search_tools",
            "get_tool_details",
            "scan_code_batch",
            "scan_backend_batch",
            "scan_admin_batch",
            "get_pipeline_status",
            "orchestrate_task",
            "get_next_message"
        ],
        "default": ["search_tools", "get_tool_details", "scan_code_batch", "get_pipeline_status", "orchestrate_task", "get_next_message"]
    },
    AgentState.DELIVERY_COMPLETED: {
        "default": []
    },
    AgentState.HUMAN_INTERRUPT: {
        "default": []
    }
}


# ==========================================
# 3. 动态调度器（扩展角色支持）
# ==========================================
class DynamicToolDispatcher:
    def __init__(self, all_registered_tools: List[Dict[str, Any]]):
        self.all_registered_tools = all_registered_tools

    def get_active_tools_for_state(
        self,
        current_state: AgentState,
        role: str = None
    ) -> List[Dict[str, Any]]:
        """
        根据当前状态和角色返回允许的工具列表。
        如果 role 未指定或不在配置中，使用 "default" 降级。
        """
        state_config = ROLE_TOOL_REGISTRY.get(current_state, {})

        if role and role in state_config:
            allowed_names = state_config[role]
        else:
            allowed_names = state_config.get("default", [])

        active_tools = [
            tool for tool in self.all_registered_tools
            if tool.get("name") in allowed_names
        ]

        # 关键修复：使用 stderr，不污染 stdout（MCP 协议要求 stdout 仅为 JSON-RPC）
        sys.stderr.write(f"[Dispatcher] 状态 {current_state}, 角色 {role or 'default'} -> 允许 {len(active_tools)} 个工具\n")
        return active_tools