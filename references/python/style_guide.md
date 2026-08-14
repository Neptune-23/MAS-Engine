# Python 开发规则

## 1. 代码风格
- 遵循 PEP 8 规范
- 使用 4 个空格缩进
- 行宽限制：88 字符（Black 默认）
- 使用 Black 或 Ruff 作为格式化工具

## 2. 类型注解
- 所有函数参数和返回值必须有类型注解
- 使用 `typing` 模块提供复杂类型
- 使用 `mypy` 进行静态类型检查

## 3. 文档字符串
- 所有公共函数、类、模块必须有 docstring
- 推荐使用 Google 风格或 NumPy 风格
- 文档应包含功能描述、参数说明、返回值说明

## 4. 依赖管理
- 使用 `requirements.txt` 或 `pyproject.toml` 管理依赖
- 区分生产依赖和开发依赖（`requirements-dev.txt`）
- 锁定依赖版本

## 5. 错误处理
- 使用 try-except 捕获特定异常
- 严禁使用裸 except
- 异常信息应包含足够的上下文

## 6. 测试
- 使用 pytest 或 unittest 编写测试
- 测试覆盖核心功能
- 测试文件命名：`test_*.py` 或 `*_test.py`

## 7. 项目结构
- 源码放在 `src/` 或项目根目录
- 测试放在 `tests/` 目录
- 配置文件放在 `config/` 或项目根目录
