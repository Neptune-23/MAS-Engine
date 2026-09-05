# 🚀 MAS-Engine

**Deterministic Multi-Agent Self-Healing Engine with Pluggable Language Adapters & Local Multi-LoRA Runtime.**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python: 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![Tests: 10 Passed](https://img.shields.io/badge/Tests-10%20Passed-success.svg)](tests/)
[![Code Style: Ruff](https://img.shields.io/badge/Code%20Style-Ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![MCP Protocol](https://img.shields.io/badge/Protocol-Model%20Context%20Protocol-green.svg)](https://modelcontextprotocol.io/)

---

## 📖 简介

**MAS-Engine** 是一套面向企业级软件工程的**确定性多智能体协同与自愈引擎**。

针对传统 AI Coding 代理“大文件上下文迷失、死循环反复试错、测试断言篡改（Reward Hacking）及商用 API 账单不可控”等核心痛点，MAS-Engine 结合 **7 阶有限状态机（FSM）**、**可插拔多语言适配器（Pluggable Adapters）** 以及 **物理编译器/单测闭环**，实现了从自然语言从 0 到 1 架构与代码构建（Coding Free），到已有项目缺陷自动化闭环自愈。

> 📘 **需要详细的新手保姆级使用教程？**  
> 请查阅：**[👉 MAS-Engine 团队新手完全使用手册 (docs/USER_MANUAL.md)](docs/USER_MANUAL.md)**

---

## ✨ 核心架构与四大杀手锏特性

                           ┌────────────────────────────────────────────────────────┐
                           │                 MAS-Engine 调度微内核                   │
                           └───────────────────────────┬────────────────────────────┘
                                                       │ 7阶生命周期状态机流转
                                                       ▼
            ┌──────────────────────────────────────────────────────────────────────────────────────┐
            │                               多角色专职协同流水线                                    │
            ├──────────────────┬──────────────────┬──────────────────┬──────────────────┬──────────┤
            │ mas-architect    │ mas-developer    │ mas-tester       │ mas-fixer        │mas-auditor
            │ 架构与文件树规划 │ 业务代码全量构建 │ 物理单测捕获报错 │ AST精准切片自愈  │安全门禁交付
            └──────────────────┴──────────────────┴──────────────────┴──────────────────┴──────────┘

1. **🛡️ 7 阶确定性有限状态机（FSM Guardrails）**
   - 生命周期状态机：`需求分析 ➔ 代码构建 ➔ 物理测试 ➔ 自愈修复 ➔ 交付审计`；
   - 建立状态与角色双维度的工具最小权限白名单，内建 3 次重试自动熔断机制，彻底杜绝死锁与逻辑脱轨。
2. **⚡ AST 精准切片与 Token 降噪（Code Slicing）**
   - 拒绝大文件全量倾倒；基于语法树精准截取目标故障函数、依赖 `use/import` 签名与带标尺代码块；
   - 单次推理 **Token 开销直降 90% ~ 96.5%**，根治模型注意力迷失。
3. **🔌 纯插拔式多语言适配器（Pluggable Adapters）**
   - 核心状态机与具体语言彻底解耦；
   - 原生支持 **Python**（`ast.parse` 静态门禁 + `pytest`）与 **PHP**（Composer + `php -l` 原生检查 + `phpunit`），并可通过实现 `BaseLanguageAdapter` 无限横向扩展（Go、Rust、TypeScript）。
4. **🔄 物理编译器闭环驱动的自演化数据飞轮（Self-Evolution Flywheel）**
   - 以真实的物理单测（Pytest / PHPUnit）报错 Traceback 为负样本，物理验证全通为正样本；
   - 无人工标注成本自动捕获并沉淀 **ShareGPT 格式 SFT 数据集** 与 **DPO 成对偏好数据集**，持续喂养模型迭代。

---

## ⚡ 极速上手（30秒体验）

### 1. 安装
```bash
git clone [https://github.com/Neptune-23/MAS-Engine.git](https://github.com/Neptune-23/MAS-Engine.git)
cd MAS-Engine
pip install -e ".[dev]"
2. 场景 A：从 0 到 1 全自动构建新项目（绿地模式 --create）
Bash
# 自动规划架构、编写完整代码并执行语法门禁自检
python mcp-server/server.py --create "D:/my_new_app" --lang php --task "编写一个返回系统运行状态的PHP应用"
3. 场景 B：已有工程一键测试诊断与缺陷自愈（棕地模式 --project）
Bash
# 自动运行单测捕获缺陷，激活 mas-fixer 完成代码自愈并回归验证
python mcp-server/server.py --project "./test_sandbox_project"
4. 场景 C：启动标准 MCP 服务（供 Cursor / Cline / VS Code 挂载）
Bash
python mcp-server/server.py
🧪 自动化测试与工程自证
MAS-Engine 的底层确定性由全套自动化测试套件捍卫：

Bash
# 运行全量 10 项核心单元测试（涵盖状态机流转、AST 切片降噪比、反测试作弊拦截、适配器等）
pytest -v
collected 10 items
tests/test_adapters.py::test_adapter_registry_and_selection PASSED      [ 10%]
tests/test_code_slicer.py::test_ast_code_slicing_precision PASSED       [ 50%]
tests/test_code_slicer.py::test_token_reduction_ratio_benchmark PASSED  [ 60%]
tests/test_anti_reward_hacking.py::test_anti_reward_hacking_detection PASSED [ 40%]
tests/test_state_machine.py::test_healing_max_retries_circuit_breaker PASSED [ 90%]
============================== 10 passed in 1.28s ==============================
🗺️ 架构路线图
[x] v0.1.0：7 阶状态机调度与 FastMCP 协议集成

[x] v0.2.0：AST 代码精准切片与单卡 8GB 显存 7B 多 LoRA 毫秒级运行时

[x] v0.3.0：可插拔语言适配器体系（Python + PHP）与从 0 到 1 自动构建

[ ] v0.4.0：DSH（DeepSeek Harness）风格 Local WebUI 可视化交互看板

[ ] v0.5.0：混合设备指纹（IP + 硬件Hash）与企业级数据自动回收中枢

📄 开源许可证
本项目采用 MIT License 协议开源。


---