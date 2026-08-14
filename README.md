```markdown
# MAS-Engine

**MCP-based Multi-Agent System orchestration engine with 7-stage state machine, progressive tool discovery, and self-healing automation.**

[![MIT License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![MCP](https://img.shields.io/badge/MCP-1.11.0-green.svg)](https://modelcontextprotocol.io/)

---

## 📖 简介

MAS-Engine 是一套基于 **Model Context Protocol (MCP)** 构建的**系统级自主 Agent 工具链**
用于驱动 AI 完成从需求提取、代码构建、自动测试到自我修复的完整开发闭环。

与常规 AI 助手不同，MAS-Engine 通过显式的 **状态机编排** 和 **角色驱动的工具过滤**
让 AI 能像一支工程团队一样协同工作，而不仅仅是回答问题的“对话机器人”。

---

## ✨ 核心特性

| 特性 | 说明 |
|------|------|
| 🎯 **7阶状态机编排** | `需求提取 → 分析 → 资源加载 → 代码构建 → Web测试 → 自我修复 → 交付完成` |
| 🔧 **16个MCP工具矩阵** | 覆盖项目创建、代码扫描、批量修复、异步流水线、网页审计 |
| 💰 **渐进式工具发现** | 通过元工具动态加载工具 Schema，Token 消耗降低 **85%** |
| 👥 **6种角色协同** | `analyst / architect / developer / tester / reviewer / fixer` 按状态自动切换 |
| 💬 **Agent间消息通信** | 支持角色间异步消息传递（`send_message` + `get_next_message`），实现协同闭环 |
| 🧪 **双引擎测试闭环** | Playwright 静默监听 + 视觉验证，自动捕获 Console/Network 异常并截图 |
| 🔄 **Self-Healing 自我修复** | 异常捕获 → 诊断包 → 热重载 → 回归测试，形成自动修复回路 |

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

```bash
git clone https://github.com/Neptune-23/mas-engine.git
cd mas-engine/mcp-server
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 配置

复制环境变量模板并填入配置：

```bash
cp .env.example .env
```

编辑 `.env` 文件：

```env
DB_HOST=127.0.0.1
DB_USER=root
DB_PASSWORD=your_password
DB_NAME=agent_db
```

### 启动

```bash
python server.py
```

---

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

---

## 🏗️ 架构设计

```text
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
```

### 状态机流转

```text
需求提取 → 需求分析 → 资源加载 → 代码构建 → Web测试 → 自我修复 → 交付完成
                                              ↑           ↓
                                              └───── 修复循环 ─────┘
```

### 角色体系

| 角色 | 职责 |
|------|------|
| `analyst` | 需求分析与拆解 |
| `architect` | 技术选型与资源加载 |
| `developer` | 代码生成与构建 |
| `tester` | 自动化测试与验证 |
| `reviewer` | 代码审查与质量检查 |
| `fixer` | 自动修复与回归验证 |

---

## 📌 版本说明

本仓库为 **开源演示版本**，展示 MAS-Engine 的核心框架能力：

- ✅ 状态机编排
- ✅ MCP 工具调度
- ✅ 多角色协同
- ✅ 渐进式工具发现
- ✅ Agent 间消息通信
- ✅ 异步流水线
- ✅ 网页自动化测试

完整版（包含业务模板、企业级配置、定制化规则）为闭源维护，仅用于内部开发。

---

## 🗺️ 路线图

| 版本 | 时间 | 核心内容 |
|------|------|----------|
| v1.0.0 | 2026.08 | 初始开源发布：状态机 + 16 个工具 + 渐进式发现 |
| v1.1.0 | 2026 Q3 | 通用指纹识别模块（`analyze_project_structure`） |
| v1.2.0 | 2026 Q4 | 基础自我演化能力（日志分析 + 经验复用） |
| v2.0.0 | 2027 Q1 | 多 Agent 完整协作网络 + Web 管理界面 |

---

## 🤝 贡献

欢迎任何形式的贡献！

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/amazing-feature`)
3. 提交修改 (`git commit -m 'feat: add amazing feature'`)
4. 推送分支 (`git push origin feature/amazing-feature`)
5. 提交 Pull Request

请阅读 [CONTRIBUTING.md](CONTRIBUTING.md) 了解详细规范。

---

## 📄 许可证

本项目采用 **MIT License**，可自由使用、修改、分发，包括商业用途。详见 [LICENSE](LICENSE) 文件。

---

## 👤 作者

**李天昊**
- GitHub: [@Neptune-23](https://github.com/Neptune-23)
- 技术方向：AI Agent基础设施、MCP协议、Multi-Agent System

---

## ⭐ 支持

如果你觉得这个项目对你有帮助，请给它一个 Star！

你的 Star 是对作者最大的鼓励。❤️
```

---
