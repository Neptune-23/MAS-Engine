---
name: generic-scanner
description: 通用代码扫描 Skill，根据语言指纹自动选择扫描工具
version: 1.0.0
triggers:
  - 扫描代码
  - 检查代码质量
---

# 通用代码扫描 Skill

## 核心原则

根据 `analyze_project_structure` 返回的语言指纹，动态决定使用哪种扫描工具。

## 工作流程

### 步骤 1：获取项目指纹
- 调用 `analyze_project_structure(project_path)`

### 步骤 2：根据语言选择扫描策略
- Python → 使用 `pylint` 或 `flake8`
- Node.js → 使用 `eslint` 或 `npm run lint`
- 其他语言 → 使用通用文本检查

### 步骤 3：执行扫描并报告结果
- 收集扫描输出
- 生成结构化报告

