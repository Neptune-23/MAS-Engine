# MAS-Engine

**MCP-based Multi-Agent System orchestration engine with 7-stage state machine, progressive tool discovery, and self-healing automation.**

[![MIT License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![MCP](https://img.shields.io/badge/MCP-1.11.0-green.svg)](https://modelcontextprotocol.io/)

---

## 📖 简介

MAS-Engine 是一套基于 **Model Context Protocol (MCP)** 构建的**系统级自主 Agent 工具链**。它旨在驱动 AI 完成从需求提取、代码构建、自动测试到自我修复的完整开发闭环。

**全新升级：独立运行模式 (`--standalone`)**  
无需依赖任何 IDE 或客户端，你可以直接通过命令行让 Agent 独立完成项目识别、构建步骤推理、命令执行、自诊断修复与闭环交付。已验证支持 **Rust** 和 **Node.js** 项目的端到端自动化构建。

---

## ✨ 核心特性

| 特性 | 说明 |
|------|------|
| 🎯 **7阶状态机编排** | `需求提取 → 分析 → 资源加载 → 代码构建 → Web测试 → 自我修复 → 交付完成` |
| 🔧 **16个MCP工具矩阵** | 覆盖项目扫描、批量修复、异步流水线、网页审计等 |
| 💰 **渐进式工具发现** | 通过元工具动态加载工具 Schema，Token 消耗降低 **85%** |
| 👥 **6种角色协同** | `analyst / architect / developer / tester / reviewer / fixer` 按状态自动切换 |
| 💬 **Agent间消息通信** | 支持角色间异步消息传递（`send_message` + `get_next_message`），实现协同闭环 |
| 🚀 **独立运行模式 (`--standalone`)** | 脱离 Cline/IDE，单机命令行即可完成“感知 → 推理 → 执行 → 闭环”全流程 |
| 🔄 **Self-Healing 自我修复** | 自动捕获命令执行异常，利用结构化规则库（`diagnostic_rules.json`）进行诊断匹配与热修复；已验证解决 Rust 链接器缺失等环境问题 |
| 🧪 **双引擎测试闭环** | Playwright 静默监听 + 视觉验证，自动捕获 Console/Network 异常并截图 *（注：该功能需额外安装依赖，独立构建模式无需开启）* |

---

## 🚀 快速开始

### 环境要求

| 依赖 | 版本要求 |
|------|----------|
| Python | 3.11+ |
| MySQL | 5.7+ |
| Node.js | 16+（前端项目需要） |
| PHP | 7.4+（后端/后台项目需要） |

### 安装


git clone https://github.com/Neptune-23/mas-engine.git
cd mas-engine/mcp-server
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt


### 配置

复制环境变量模板并填入配置：
cp .env.example .env


编辑 `.env` 文件：


DB_HOST=127.0.0.1
DB_USER=root
DB_PASSWORD=your_password
DB_NAME=agent_db
DEEPSEEK_API_KEY=your_key_here


### 运行独立模式（建议使用）


# 1. 分析 Rust 项目结构，自动执行构建
python server.py --standalone --task "分析 D:/test_rust_project 项目结构，推理构建步骤，然后执行构建"

# 2. 分析 Node.js 项目结构，自动执行构建
python server.py --standalone --task "分析 D:/test_node_project 项目结构，推理构建步骤，然后执行构建"


### 启动 MCP 服务（供 Cline 等客户端调用）


python server.py


## 🧠 工具矩阵

| 工具名 | 分类 | 说明 |
|--------|------|------|
| `search_tools` | 元工具 | 渐进式工具发现，按状态+角色动态过滤 |
| `orchestrate_task` | 元工具 | 任务编排入口，自然语言驱动 |
| `get_next_message` | 元工具 | Agent间通信收件箱 |
| `create_frontend_project` | 模板 | 创建 Vue 3 + uni-app 项目 |
| `create_backend_project` | 模板 | 创建 ThinkPHP 后端项目 |
| `create_admin_project` | 模板 | 创建 FastAdmin 后台项目 |
| `scan_code_batch` | 质量 | 分批代码扫描，避免超时 |
| `run_quality_pipeline` | 流水线 | 全自动异步质量检查 |
| `run_web_audit` | 测试 | Playwright 网页审计 |
| `execute_shell_command` | 执行 | 系统级安全命令执行（白名单过滤） |
| `get_rules` | 规则 | 获取多语言诊断规则（结构化 JSON） |



## 🏗️ 架构设计


┌─────────────────────────────────────────────────────┐
│                   用户层（VS Code + Cline）          │
├─────────────────────────────────────────────────────┤
│                  Agent 层（LLM + 工具调度）          │
├─────────────────────────────────────────────────────┤
│                  MCP 服务层（server.py）             │
│  ┌───────────┐  ┌───────────┐  ┌──────────────┐   │
│  │ 元工具层   │  │ 业务工具层 │  │ 流水线层     │   │
│  └───────────┘  └───────────┘  └──────────────┘   │
├─────────────────────────────────────────────────────┤
│              状态机层（7阶状态 + 6种角色）          │
├─────────────────────────────────────────────────────┤
│                   数据层（MySQL + 文件系统）         │
└─────────────────────────────────────────────────────┘


### 状态机流转
<img width="3533" height="458" alt="deepseek_mermaid_20260816_01ed13" src="https://github.com/user-attachments/assets/577dedc2-449b-4954-acb9-8863feaa8de0" />

### 角色体系

| 角色 | 职责 |
|------|------|
| `analyst` | 需求分析与拆解 |
| `architect` | 技术选型与资源加载 |
| `developer` | 代码生成与构建 |
| `tester` | 自动化测试与验证 |
| `reviewer` | 代码审查与质量检查 |
| `fixer` | 自动修复与回归验证 |


## 📌 版本说明

本仓库为 **开源演示版本**，展示 MAS-Engine 的核心框架能力：

- ✅ 独立运行模式（`--standalone` 端到端构建闭环）
- ✅ 状态机编排
- ✅ MCP 工具调度
- ✅ 多角色协同
- ✅ 渐进式工具发现
- ✅ Agent 间消息通信
- ✅ 异步流水线
- ✅ 网页自动化测试

完整版（包含业务模板、企业级配置、定制化规则）为闭源维护，仅用于内部开发。

## 🧭 技术方向：从单 Agent 到群体智能

MAS-Engine 的终极目标是 **“群体 Agent 自我演化”** —— 即多个 Agent 在协作中通过积累记忆和评估反馈，不断优化自身行为，形成类似人类团队的协同进化能力。

当前阶段，我们已经实现了 **单 Agent 的独立构建闭环**（`--standalone` 模式），让单个 Agent 能够感知项目、推理构建、执行修复并交付成果。这是群体演化的“个体单元”基础。

接下来的演进路线将分为三层：

1. **个体智能 (已完成)**：单个 Agent 能够独立完成从需求到交付的完整生命周期，并具备基础的自诊断与修复能力。
2. **协作智能 (进行中)**：多个角色（`developer`、`tester`、`reviewer` 等）通过消息通信形成轻量级协作网络，共同完成复杂任务。  
   *（当前已支持 Agent 间消息传递 `send_message` + `get_next_message`）*
3. **群体演化 (远期目标)**：建立共享记忆库（`memory_records` 表），让成功修复的经验被所有 Agent 复用；引入评估员 Agent 审核行为，通过强化反馈驱动集体行为优化，最终实现“经历即经验，经验即智慧”的自我演化闭环。

## 🗺️ 路线图

| 版本 | 时间 | 核心内容 |
|------|------|----------|
| v1.0.0 | 2026.08 | **已发布**：状态机 + 工具矩阵 + 多语言独立构建闭环 |
| v1.1.0 | 2026 Q3 | 通用指纹识别模块（`analyze_project_structure` 增强） |
| v1.2.0 | 2026 Q4 | 基础自我演化能力（日志分析 + 经验复用） |
| v2.0.0 | 2027 Q1 | 多 Agent 完整协作网络 + Web 管理界面 |


## 🤝 贡献

欢迎任何形式的贡献！

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/amazing-feature`)
3. 提交修改 (`git commit -m 'feat: add amazing feature'`)
4. 推送分支 (`git push origin feature/amazing-feature`)
5. 提交 Pull Request

请阅读 [CONTRIBUTING.md](CONTRIBUTING.md) 了解详细规范。


## 📄 许可证

本项目采用 **MIT License**，可自由使用、修改、分发，包括商业用途。详见 [LICENSE](LICENSE) 文件。


## 👤 作者

**李天昊**
- GitHub: [@Neptune-23](https://github.com/Neptune-23)
- 技术方向：AI Agent基础设施、MCP协议、Multi-Agent System、Multi-Agent Evolve


## ⭐ 支持

如果你觉得这个项目对你有帮助，请给它一个 Star！

你的 Star 是对作者最大的鼓励。❤️
