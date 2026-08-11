# FastAdmin 后台开发绝对红线（基于 ThinkPHP 5.x）

## 1. 技术栈铁律
- 框架必须使用 **FastAdmin**（基于 ThinkPHP 5.x），严禁自行修改核心框架代码。
- 插件开发必须遵循 **FastAdmin 插件规范**，插件目录必须放在 `addons/` 下。
- 数据库操作必须使用 **FastAdmin 的 Model 或 Db 类**，严禁使用原生 SQL 拼接。
- API 返回格式必须统一为 `{ code: 0, msg: '', data: [] }`。

## 2. 安全红线
- **严禁修改 `public/` 下的核心入口文件**（`index.php`、`admin.php` 等）。
- 所有用户输入必须经过 **FastAdmin 的验证器（Validate）** 或 **Token 验证**。
- 管理员后台的菜单、权限配置必须通过 **FastAdmin 的权限管理模块**，严禁硬编码权限判断。
- 严禁在插件中直接执行 `system()`、`exec()` 等命令。

## 3. 代码规范
- 插件控制器必须继承 `addons\Base` 或 `app\common\controller\Backend`。
- 模型必须放在 `application/common/model/` 或 `addons/xxx/model/` 下。
- 视图文件必须放在 `application/admin/view/` 或 `addons/xxx/view/` 下。
- 前端 JS/CSS 必须放在 `public/assets/` 下，并按模块组织。

## 4. 项目结构约束
- `application/`：核心应用目录（严禁在 `application/` 下直接修改 FastAdmin 核心文件）。
- `addons/`：所有插件必须放在此目录下，按插件名分目录。
- `public/assets/`：前端资源目录（JS/CSS/图片），严禁直接修改 FastAdmin 的 `public/assets/libs/` 依赖库。
- `runtime/`：日志和缓存目录（必须加入 `.gitignore`）。

## 5. 插件开发规范
- 插件必须包含 `info.ini` 文件（插件名称、版本、作者等信息）。
- 插件安装脚本必须放在 `install.sql` 或 `install.php` 中。
- 插件配置必须通过 FastAdmin 的配置接口（`config` 表）存储，严禁硬编码。

## 6. 代码示例（正确 vs 错误）

### 6.1 权限判断
✅ **正确**（使用权限节点）
```php
if (!$this->auth->check('user/add')) {
    $this->error('无权限');
}
```
❌ **错误**（硬编码角色 ID）
```php
if ($user->role_id == 1) {
    // 允许操作
}
```

### 6.2 SQL 查询
✅ **正确**（使用参数绑定）
```php
Db::name('fa_user')->where('id', $id)->find();
```
❌ **错误**（字符串拼接）
```php
Db::query("SELECT * FROM fa_user WHERE id={$id}");
```

### 6.3 资源引用
✅ **正确**（使用 `__PUBLIC__` 常量）
```php
<img src="__PUBLIC__/assets/img/logo.png">
```
❌ **错误**（绝对路径）
```php
<img src="/static/img/logo.png">  // 可能导致路径错误
```

### 6.4 输入校验
✅ **正确**（使用验证器）
```php
$validate = new \app\admin\validate\User();
if (!$validate->check($data)) {
    $this->error($validate->getError());
}
```
❌ **错误**（直接使用未过滤输入）
```php
$name = input('name');  // 未校验
Db::name('user')->insert(['name' => $name]);
```

### 6.5 插件信息
✅ **正确**（包含 `info.ini`）
```ini
name = myplugin
title = 我的插件
version = 1.0.0
author = 你的名字
description = 插件功能描述
```
❌ **错误**（缺少 `info.ini` 文件）——插件将无法被 FastAdmin 识别。

## 7. 总结
以上规则和示例，结合 `get_rules` 工具，AI 将能够在生成或审查代码时，自动对照这些规范，确保后台代码的合规性和安全性。
```