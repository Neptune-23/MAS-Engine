---
name: demo-assistant
description: 演示 Skill 示例，展示 MAS 系统的 Skill 机制如何工作
version: 1.0.0
triggers:
  - 创建示例
  - 演示 Skill
---

# 演示助手 Skill

## 核心原则

这是一个演示 Skill，用于展示 MAS 系统如何通过 Skill 文件指导 Agent 执行任务。

## 工作流程

### 步骤 1：确认任务类型
- 如果是"创建项目"，调用 `create_frontend_project`
- 如果是"扫描代码"，调用 `scan_code_batch`
- 如果是"运行流水线"，调用 `run_quality_pipeline`

### 步骤 2：执行对应工具
根据任务类型调用相应的 MCP 工具。

### 步骤 3：验证结果
执行完成后，检查工具返回的状态，如有问题则报告。

## 参考资源
- 规则文档：`references/` 目录下的通用规则