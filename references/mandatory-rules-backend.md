# ThinkPHP 后端开发绝对红线（第一版）

## 1. 技术栈铁律
- 框架必须使用 **ThinkPHP 5.x**，严禁使用 ThinkPHP 6.0 以上版本。
- 编码语言必须使用 **PHP 7.3+**，严禁使用7.4 以上版本。
- 数据库操作必须使用 **ThinkPHP 数据库链式操作** 或 **模型（Model）**，**严禁使用原生 SQL 字符串拼接**。
- API 返回格式必须统一为 `{ code: 0, msg: '', data: [] }`，严禁自定义错误格式。

## 2. 安全红线（硬性）
- **严禁硬编码** 数据库密码、API 密钥、Token 等敏感信息。必须使用 `.env` 环境变量。
- **所有用户输入**（`input()`、`$request->param()` 等）必须经过 **参数校验（Validate）**，严禁直接使用。
- **严禁使用 `eval()`、`system()`、`exec()` 等执行系统命令**（除非绝对必要且经过审批）。
- **所有 SQL 查询**必须使用 **参数绑定**（`where('id', $id)` 或 `Db::table()->where('id', '=', $id)->find()`），**严禁拼接字符串**。
- **所有文件上传**必须进行 **文件类型校验**（MIME、后缀），并存储到非 Web 可访问目录。

## 3. 代码规范
- 控制器类名必须使用 **大驼峰命名**（如 `UserController`），方法名使用 **小驼峰**（如 `getUserInfo`）。
- 模型类名必须使用 **大驼峰**（如 `UserModel`），对应数据表名使用 **小写+下划线**（如 `user_info`）。
- 所有控制器方法必须 **返回 JSON 数据**（`return $this->success()` / `$this->error()`），**严禁直接 `echo` 或 `dump`**。
- 所有异常必须使用 **Try-Catch 捕获**，并记录日志，**严禁直接 `die` 或 `exit`**。
- 所有业务逻辑必须放在 **Service 层** 或 **Model 层**，**严禁在控制器中写大量 SQL 或复杂业务逻辑**。

## 4. 错误与日志规范
- 必须使用 **ThinkPHP 内置日志**（`Log::info()` / `Log::error()`）记录关键操作和错误，**严禁使用 `var_dump` 或 `print_r` 输出调试信息到响应中**。
- 开发环境可使用 `debug` 模式，生产环境必须关闭 `app_debug`。

## 5. 项目结构约束
- 控制器必须放在 `app/controller/` 下，按模块分目录（如 `app/controller/api/`）。
- 模型必须放在 `app/model/` 下。
- 验证器必须放在 `app/validate/` 下。
- 配置文件必须放在 `config/` 下，环境变量放在 `.env` 文件。