# 📖 MAS-Engine 新手完全使用手册与实战教程

> **MAS-Engine** 是一套基于 **7 阶确定性有限状态机（FSM）** 和 **可插拔多语言适配器** 构建的自主智能体系统。支持全自动从 0 到 1 架构与代码生成（Coding Free），以及已有代码项目的自动化单测捕获与 AST 切片自愈修复。

---

## 目录

- 一、 极速安装与环境配置
- 二、 大模型后端准备（二选一）
- 三、 常用命令大全（开箱即用新手教程）
  - 场景 1：从 0 到 1 自动构建新项目（绿地模式 `--create`）
  - 场景 2：已有项目一键排错与自愈（棕地模式 `--project`）
  - 场景 3：挂载项目个性化规范（Pi-Style `AGENTS.md`）
  - 场景 4：作为标准 MCP 服务供 IDE 调用（Cursor / Cline）
  - 场景 5：自动化数据采集飞轮（产出 SFT / DPO 数据）
  - 场景 6：代码质量检查与全量单元自测
- 四、 命令行参数速查表
- 五、 常见报错与排查指南 (FAQ)

---

## 一、 极速安装与环境配置

### 1. 克隆代码库并进入项目

```bash
git clone https://github.com/Neptune-23/mas-engine.git
cd mas-engine
```

### 2. 创建并激活虚拟环境（推荐 Python 3.10+）

```powershell
# Windows
python -m venv venv
.\venv\Scripts\activate

# Linux / macOS / WSL
python3 -m venv venv
source venv/bin/activate
```

### 3. 一键以可编辑模式安装全部依赖

```bash
pip install -e ".[dev]"
```

### 4. 配置 `.env` 环境变量

在项目根目录下创建 `.env` 文件：

```ini
# 数据库配置（用于状态机持久化与历史记忆）
DB_HOST=127.0.0.1
DB_PORT=3306
DB_USER=root
DB_PASSWORD=0000
DB_NAME=agent_db

# 模型后端配置：本地 GPU 推理（推荐）或云端 API
LLM_PROVIDER=local
LOCAL_LLM_URL=http://127.0.0.1:8000/v1
LOCAL_LLM_MODEL=mas-developer

# 若使用云端 DeepSeek 兜底，取消下行注释并填入 Key
# DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx
```

---

## 二、 大模型后端准备（二选一）

MAS-Engine 支持 **本地单卡 GPU 专职模型** 或 **云端 API**：

### 选项 A：使用本地 7B 多 LoRA 运行时（单卡 8GB 显存，推荐）

在 WSL2 终端中启动模型服务（显存常驻约 4.2GB，带并发排队锁）：

```bash
python /mnt/d/Python/Agent/LLM/serve_adapters.py
```

*启动后，服务将监听在 [http://127.0.0.1:8000](http://127.0.0.1:8000)，挂载 Architect / Developer / Tester / Fixer / Auditor 5 大专职适配器。*

### 选项 B：使用云端 DeepSeek / OpenAI API

直接在 `.env` 中修改：

```ini
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=你的DeepSeek_API_KEY
```

---

## 三、 常用命令大全（开箱即用新手教程）

### 场景 1：从 0 到 1 自动构建新项目（绿地模式 `--create`）

> **适用场景**：你只有一个点子或一段话，需要 Agent 自主完成架构设计、模块规划、源文件编写并进行语法门禁自检。

#### 1. 自动创建 Python 项目

```powershell
python mcp-server/server.py --create "D:\my_python_tool" --task "编写一个多线程批量图片压缩工具，包含参数解析和错误处理"
```

#### 2. 自动创建 PHP 项目（指定 `--lang php`）

```powershell
python mcp-server/server.py --create "D:\my_php_api" --lang php --task "编写一个简单的用户权限验证API，包含Token生成与检验"
```

执行后，MAS 会自动经历：
`🧠 Architect (规划文件树) ➔ 💻 Developer (生成完整代码) ➔ 🧪 Tester (语法门禁自检) ➔ 🎉 Auditor (交付)`。

---

### 场景 2：已有项目一键排错与自愈（棕地模式 `--project`）

> **适用场景**：本地有一个报错或单测通不过的项目，需要 Agent 自动定位根因并安全修补。

#### 1. 一键诊断修复 Python 项目（自动探测）

```powershell
python mcp-server/server.py --project "D:\my_work_project"
```

#### 2. 一键诊断修复 PHP 项目（自动探测并调用 PHPUnit）

```powershell
python mcp-server/server.py --project "D:\my_php_service"
```

执行后，MAS 会自动经历：
`🧪 Tester (物理执行 pytest/phpunit 捕获堆栈) ➔ 🔧 Fixer (AST 切片精准自愈) ➔ 🛡️ 语法门禁拦截 ➔ 🔄 回归验证 ➔ 🎉 交付`。

---

### 场景 3：挂载项目个性化规范（Pi-Style `AGENTS.md`）

如果你希望 MAS-Engine 遵循你的团队专属开发规范（如必须使用特定框架、禁用某个函数）：

只需在目标项目根目录下放一个 **`AGENTS.md`**：

```markdown
# AGENTS.md
- 代码中所有函数必须添加完整 Type Hints 类型注解。
- 数据库操作必须使用 PDO 预处理语句，严禁字符串拼接 SQL。
- 错误信息必须统一用中文输出。
```

运行 `--create` 或 `--project` 时，系统会自动识别并注入：
`📄 [Pi-Core] 已成功挂载项目专属 AGENTS.md 声明式规则`。

---

### 场景 4：作为标准 MCP 服务供 IDE 调用（Cursor / Cline）

如果你希望在 VS Code、Cursor 或 Cline 中把 MAS 当作底层工具箱：

#### 1. stdio 模式（供 VS Code / Cursor 插件子进程直接调用）

```powershell
python mcp-server/server.py
```

#### 2. HTTP / SSE 模式（供远程或局域网客户端连接）

```powershell
python mcp-server/server.py --http
```

*将在 [http://0.0.0.0:8000](http://0.0.0.0:8000) 启动 SSE 协议服务。*

---

### 场景 5：自动化数据采集飞轮（产出 SFT / DPO 数据）

无需人工标注，自动将真实的编译器/单测报错与自愈成功的物理闭环转换成可直接微调大模型的数据集：

```powershell
python scripts/generate_training_data.py
```

#### 输出产物：

- `dataset_sft.json`：符合 ShareGPT / ChatML 格式的微调训练集；
- `dataset_dpo.json`：自动将重试失败作为 `rejected`、物理跑通作为 `chosen` 的强化学习偏好对。

---

### 场景 6：代码质量检查与全量单元自测

在对系统做任何改动后，执行以下命令验证底层确定性：

```powershell
# 1. 自动执行代码规范扫描与一键修复
ruff check . --fix

# 2. 自动格式化代码
ruff format .

# 3. 运行全量 10 项单元测试（涵盖状态机白名单、AST 切片降噪、反测试作弊等）
pytest -v
```

*当终端显示 `10 passed` 且 `All checks passed!` 时，表示全系统 100% 健康。*

---

## 四、 命令行参数速查表

| 参数选项 | 说明 | 示例 |
| --- | --- | --- |
| **`--create <目录>`** | **绿地构建**：从 0 到 1 自动创建新项目 | `--create "D:\new_app"` |
| **`--project <目录>`** | **棕地维护**：对已有项目执行测试、诊断与自愈 | `--project "./test_sandbox"` |
| **`--task "<需求>"`** | 指定要执行的自然语言任务描述 | `--task "创建一个计算器页面"` |
| **`--lang <语言>`** | 显式装配专职语言适配器（`python` / `php`） | `--lang php` |
| **`--standalone`** | 强制开启独立命令行运行模式 | `--standalone` |
| **`--http`** | 启动 HTTP/SSE 模式的 MCP 服务器 | `--http` |

---

## 五、 常见报错与排查指南 (FAQ)

### 1. 报错 `Connection error / 502 Bad Gateway`？

- **原因**：本地网络代理软件（如 Clash、VPN）劫持了 `127.0.0.1` 端口。
- **解决**：在代理软件设置中将 `127.0.0.1` 和 `localhost` 加入直连白名单，或在终端临时关闭代理。

### 2. 报错 `No module named pytest` 或 `php: command not found`？

- **解决**：
  - Python 项目测试依赖：`pip install pytest`；
  - PHP 项目运行依赖：确保系统已安装 PHP CLI 并在系统 PATH 中（运行 `php -v` 验证）。

### 3. 提示 `⚠️ 达到最大迭代次数 (5)，任务失败`？

- **原因**：Bug 较为复杂，Fixer 连续 3 次尝试修改后仍未通过单测，状态机自动触发熔断以防止死循环。
- **排查**：打开项目目录下的 `test_report.json`，查看未通过的详细断言与堆栈信息。

### 4. 出现语法门禁拦截 `⚠️ AST 语法门禁拦截无效修复`？

- **说明**：这是系统的物理安全保护机制在起作用，表明大模型生成的代码存在语法破损，系统已自动拦截并防止损坏原工程文件。
